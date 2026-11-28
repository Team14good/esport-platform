"""壓力測試的種子資料：在 backend 容器內執行，只經各模組 service 的公開函式建立資料。

用法（由 run.sh 呼叫；在 repo 根目錄，用 stdin 把腳本送進容器，不必改 image）：

    docker compose -p flow-load ... exec -T backend python - <指令> < scripts/load/seed.py

指令（結果是 stdout 最後一行的 JSON，log 走 stderr）：

- base          ：確認示範賽事（32 隊、已抽籤）存在，建立 200 個登入測試帳號。可重複執行。
- registration  ：每次新建一場名額 32 的先搶期賽事，200 支一人隊伍都已填完資料、等著送出報名。
- checkin       ：每次新建一場 32 隊已抽籤的賽事，把第一輪 16 場改到現在＋32 分鐘（約 2 分鐘後開放報到），
                  輸出 32 位隊長各自該去報到的場次。報到窗口約 45 分鐘（到棄權期限為止），要在跑壓測前才建立。

帳號一律是 `load-*@<DEMO_EMAIL_DOMAIN>`，密碼固定為 LOAD_PASSWORD；僅供本機測試，不要用在任何非本機環境。
"""

import io
import json
import logging
import sys
import uuid
from datetime import timedelta

from sqlmodel import Session, col, select

from app.core import clock
from app.core.config import settings
from app.core.db import engine
from app.demo_data.accounts import DEMO_SCHOOL_NAME
from app.demo_data.registration import DEMO_SCREENSHOT
from app.demo_data.tournaments import DEMO_TOURNAMENT_NAME
from app.modules.competition import service as competition_service
from app.modules.identity import service as identity_service
from app.modules.identity.models import School
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    GameIn,
    RankTierIn,
    ScoreType,
    TournamentCreate,
)

# 僅供本機測試
LOAD_PASSWORD = "LoadTest-2026-local-only"
LOGIN_ACCOUNTS = 200
REGISTRATION_TEAMS = 200
REGISTRATION_CAPACITY = 32
CHECKIN_TEAMS = 32
GAME_NAME = "壓力測試用 一對一"

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)


def _email(prefix: str, number: int) -> str:
    return f"load-{prefix}-{number:03d}@{settings.DEMO_EMAIL_DOMAIN}"


def _school_names(session: Session) -> list[str]:
    return [s.name for s in session.exec(select(School).order_by(col(School.id)))]


def _ensure_accounts(session: Session, prefix: str, count: int) -> list[str]:
    schools = _school_names(session)
    emails = []
    for i in range(1, count + 1):
        email = _email(prefix, i)
        identity_service.ensure_demo_account(
            session,
            email=email,
            password=LOAD_PASSWORD,
            display_name=f"壓測 {prefix}{i}",
            school_name=schools[i % len(schools)] if schools else DEMO_SCHOOL_NAME,
        )
        emails.append(email)
    session.commit()
    return emails


def _account_id(session: Session, email: str) -> uuid.UUID:
    found = identity_service.find_account_id_by_email(session, email)
    assert found is not None, email
    return found


def _organizer_id(session: Session) -> uuid.UUID:
    return _account_id(session, f"organizer@{settings.DEMO_EMAIL_DOMAIN}")


def _admin_id(session: Session) -> uuid.UUID:
    return _account_id(session, settings.FIRST_ADMIN_EMAIL)


def _ensure_game(session: Session) -> uuid.UUID:
    """一人一隊的遊戲（先發 1、無替補），讓 200 支隊伍不必各自組隊。"""
    for game in tournaments_service.list_games(session):
        if game.name == GAME_NAME:
            return game.id
    game = tournaments_service.create_game(
        session,
        actor_id=_admin_id(session),
        data=GameIn(
            name=GAME_NAME,
            starters=1,
            substitutes=0,
            default_bo=1,
            game_minutes=30,
            score_type=ScoreType.WIN_LOSS,
            rank_tiers=[RankTierIn(name="鑽石", score=30)],
        ),
    )
    session.commit()
    return game.id


def _new_tournament(
    session: Session, *, label: str, capacity: int, game_id: uuid.UUID
) -> uuid.UUID:
    """先搶期的賽事（優先期 0 小時）：報名已開始、開賽在 7 天後。"""
    now = clock.now()
    created = tournaments_service.create_tournament(
        session,
        organizer_id=_organizer_id(session),
        data=TournamentCreate(
            name=f"壓測 {label} {uuid.uuid4().hex[:6]}",
            game_id=game_id,
            capacity=capacity,
            registration_start=now - timedelta(hours=1),
            registration_end=now + timedelta(days=3),
            priority_hours=0,
            start_at=now + timedelta(days=7),
            round_interval_minutes=180,
        ),
    )
    session.commit()
    return created.id


def _create_ready_team(
    session: Session, *, tournament_id: uuid.UUID, email: str, name: str
) -> uuid.UUID:
    """建立隊伍（隊長就是唯一隊員）並填完參賽資料，還沒送出報名。"""
    captain_id = _account_id(session, email)
    team = registration_service.create_team(
        session, tournament_id=tournament_id, account_id=captain_id, name=name
    )
    registration_service.update_player_profile(
        session,
        team_id=team.id,
        account_id=captain_id,
        game_account_id=f"{name}#TW1",
        rank_tier="鑽石",
        screenshot=io.BytesIO(DEMO_SCREENSHOT),
        content_type="image/png",
        file_name="rank.png",
    )
    return team.id


def seed_base() -> dict[str, object]:
    with Session(engine) as session:
        organizer_id = _organizer_id(session)
        tournament_id = None
        for t in tournaments_service.list_organizer_tournaments(
            session, organizer_id=organizer_id
        ):
            if t.name == DEMO_TOURNAMENT_NAME:
                tournament_id = t.id
        if tournament_id is None:
            raise SystemExit(f"找不到示範賽事「{DEMO_TOURNAMENT_NAME}」，請確認 DEMO_PASSWORD 已設定")
        bracket = competition_service.get_public_bracket(
            session, tournament_id=tournament_id
        )
        if bracket is None:
            raise SystemExit("示範賽事尚未抽籤")
        emails = _ensure_accounts(session, "login", LOGIN_ACCOUNTS)
        return {
            "tournament_id": str(tournament_id),
            "match_ids": [str(m.id) for m in bracket.matches],
            "login_emails": emails,
            "password": LOAD_PASSWORD,
        }


def seed_registration() -> dict[str, object]:
    with Session(engine) as session:
        emails = _ensure_accounts(session, "reg", REGISTRATION_TEAMS)
        game_id = _ensure_game(session)
        tournament_id = _new_tournament(
            session, label="報名尖峰", capacity=REGISTRATION_CAPACITY, game_id=game_id
        )
        teams = []
        for i, email in enumerate(emails, start=1):
            team_id = _create_ready_team(
                session, tournament_id=tournament_id, email=email, name=f"報名隊{i:03d}"
            )
            teams.append({"team_id": str(team_id), "email": email})
        session.commit()
        return {
            "tournament_id": str(tournament_id),
            "capacity": REGISTRATION_CAPACITY,
            "teams": teams,
            "password": LOAD_PASSWORD,
        }


def seed_checkin() -> dict[str, object]:
    with Session(engine) as session:
        emails = _ensure_accounts(session, "ci", CHECKIN_TEAMS)
        game_id = _ensure_game(session)
        tournament_id = _new_tournament(
            session, label="報到尖峰", capacity=CHECKIN_TEAMS, game_id=game_id
        )
        captain_of_team: dict[uuid.UUID, str] = {}
        for i, email in enumerate(emails, start=1):
            team_id = _create_ready_team(
                session, tournament_id=tournament_id, email=email, name=f"報到隊{i:02d}"
            )
            registration_service.submit_registration(
                session, team_id=team_id, account_id=_account_id(session, email)
            )
            captain_of_team[team_id] = email
        session.commit()

        organizer_id = _organizer_id(session)
        competition_service.draw(
            session, tournament_id=tournament_id, actor_id=organizer_id
        )
        session.commit()

        bracket = competition_service.get_public_bracket(
            session, tournament_id=tournament_id
        )
        assert bracket is not None
        first_round = [
            m for m in bracket.matches if m.team_a is not None and m.team_b is not None
        ]
        # 修改時間的下限是「現在進位到整分＋30 分鐘」；多留 2 分鐘餘裕，報到在預定時間前 30 分鐘開放，
        # 所以約 2～3 分鐘後才能報到（run.sh 會等到開放）
        scheduled_at = clock.now() + timedelta(minutes=32)
        captains = []
        for match in first_round:
            competition_service.reschedule_match(
                session,
                tournament_id=tournament_id,
                match_id=match.id,
                actor_id=organizer_id,
                scheduled_at=scheduled_at,
            )
            for team in (match.team_a, match.team_b):
                assert team is not None
                captains.append(
                    {
                        "email": captain_of_team[team.id],
                        "match_id": str(match.id),
                        "team_id": str(team.id),
                    }
                )
        session.commit()
        return {
            "tournament_id": str(tournament_id),
            "matches": len(first_round),
            "opens_at": (scheduled_at - timedelta(minutes=30)).isoformat(),
            "captains": captains,
            "password": LOAD_PASSWORD,
        }


COMMANDS = {
    "base": seed_base,
    "registration": seed_registration,
    "checkin": seed_checkin,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(f"用法：seed.py <{'|'.join(COMMANDS)}>")
    print(json.dumps(COMMANDS[sys.argv[1]](), ensure_ascii=False))


main()
