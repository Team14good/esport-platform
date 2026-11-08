"""Story 3.5：真實 PostgreSQL 上先搶期平行送出不超收（epics 3.5 驗收條件）。

先搶期判定靠 `lock_tournament` 的列鎖讓送出依序執行，`_first_come_locked` 在鎖內讀最新
狀態；把鎖換成不加鎖的讀取時，同時送出的隊伍都會看到有空位而超收，這裡的斷言就會失敗。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture，也不凍結時鐘：
賽事報名從 1 小時前開始、優先期 0 小時，真實時間下已在先搶期，`submitted_at` 各不相同。
送出用另建的 engine（20 條連線）與 `ThreadPoolExecutor(max_workers=20)`，避免占滿預設
engine 的連線池。被只增不改的操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫
（比照 test_team_concurrency.py）；事件、結算紀錄、報名、隊員與隊伍在結束時刪除。
學校用初始資料裡的 139 所（不新增，學校清單的測試會檢查總數）。
"""

import secrets
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine, delete
from sqlmodel import Session, col, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.identity.models import School
from app.modules.registration import service
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
    TeamMember,
)
from app.modules.tournaments.models import TournamentRead
from tests.helpers import make_account, make_game, make_tournament
from tests.registration.test_submit_registration import _fill
from tests.registration.test_team_concurrency import _demote_game_creator

WORKERS = 20


def _setup(
    *, capacity: int, teams: int, accepted_school_index: int | None = None
) -> tuple[TournamentRead, list[uuid.UUID], list[tuple[uuid.UUID, uuid.UUID]]]:
    """建立先搶期的賽事與 `teams` 支填完資料的一人隊伍，第 i 隊屬初始資料的第 i % 139 所學校。

    `accepted_school_index` 給定時，另直接寫入一支該校已在先搶期正取的隊伍（不經送出），
    送出的隊伍則從下一所學校開始分配。回傳賽事、全部隊伍 id 與（隊伍 id, 隊長 id）。
    """
    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        tournament = make_tournament(
            setup,
            game=game,
            capacity=capacity,
            starters=1,
            substitutes=0,
            registration_start=(clock.now() - timedelta(hours=1)).isoformat(),
            priority_hours=0,
        )
        schools = list(setup.exec(select(School).order_by(col(School.id))))
        assert len(schools) == 139
        team_ids: list[uuid.UUID] = []
        offset = 0
        if accepted_school_index is not None:
            team = Team(
                tournament_id=tournament.id,
                name=f"已正取-{uuid.uuid4().hex[:8]}",
                invite_token=secrets.token_urlsafe(24),
            )
            setup.add(team)
            setup.flush()
            setup.add(
                Registration(
                    team_id=team.id,
                    tournament_id=tournament.id,
                    status=RegistrationStatus.ACCEPTED,
                    school_id=schools[accepted_school_index].id,
                    avg_rank_score=Decimal(30),
                    submitted_at=tournament.priority_end + timedelta(minutes=1),
                )
            )
            team_ids.append(team.id)
            offset = accepted_school_index + 1
        submitters: list[tuple[uuid.UUID, uuid.UUID]] = []
        for i in range(teams):
            school = schools[(offset + i) % len(schools)]
            # 不雜湊密碼，200 個帳號才不會拖慢測試
            captain = make_account(setup, school_id=school.id, hashed_password="x")
            created = service.create_team(
                setup,
                tournament_id=tournament.id,
                account_id=captain.id,
                name=f"先搶隊-{i}",
            )
            _fill(setup, created.id, captain)
            team_ids.append(created.id)
            submitters.append((created.id, captain.id))
        setup.commit()
        return tournament, team_ids, submitters


def _submit_all(
    submitters: list[tuple[uuid.UUID, uuid.UUID]], *, barrier: bool
) -> list[str]:
    """平行送出，回傳每筆的結果（報名狀態或錯誤）。"""
    submit_engine = create_engine(engine.url, pool_size=WORKERS, max_overflow=0)
    start = threading.Barrier(len(submitters)) if barrier else None

    def _submit(team_id: uuid.UUID, captain_id: uuid.UUID) -> str:
        with Session(submit_engine) as db:
            try:
                if start is not None:
                    start.wait(timeout=10)
                detail = service.submit_registration(
                    db, team_id=team_id, account_id=captain_id
                )
                db.commit()
                return str(detail.registration_status)
            except BusinessError as exc:
                return exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                return repr(exc)

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = [executor.submit(_submit, t, c) for t, c in submitters]
            return [f.result(timeout=120) for f in futures]
    finally:
        submit_engine.dispose()


def _events(session: Session, tournament_id: uuid.UUID) -> list[OutboxEvent]:
    rows = session.exec(select(OutboxEvent)).all()
    return [
        row for row in rows if row.payload.get("tournament_id") == str(tournament_id)
    ]


def _check(
    tournament: TournamentRead,
    submitters: list[tuple[uuid.UUID, uuid.UUID]],
    *,
    capacity: int,
) -> dict[uuid.UUID, Registration]:
    """Boundaries 的併發斷言；回傳以隊伍 id 為鍵的報名。"""
    with Session(engine) as check:
        registrations = {
            r.team_id: r
            for r in check.exec(
                select(Registration).where(Registration.tournament_id == tournament.id)
            ).all()
        }
        submitted = [registrations[team_id] for team_id, _ in submitters]
        assert {r.status for r in submitted} <= {
            RegistrationStatus.ACCEPTED,
            RegistrationStatus.WAITLISTED,
        }
        accepted = [
            r for r in registrations.values() if r.status == RegistrationStatus.ACCEPTED
        ]
        assert len(accepted) <= capacity
        assert max(Counter(r.school_id for r in accepted).values()) == 1

        # 公平性：沒有優先期學校時，正取就是依（送出時間, id）排序後、扣掉既有正取的
        # 名額與學校，前幾支學校不重複的隊伍。把取時間移到鎖之前，或把先搶期的排序
        # 改成只依 id，送出時間與正取對不上，這裡就會失敗。
        submitted_ids = {r.id for r in submitted}
        preset = [r for r in accepted if r.id not in submitted_ids]
        seen = {r.school_id for r in preset}
        expected: set[uuid.UUID] = set()
        for r in sorted(submitted, key=lambda r: (r.submitted_at, r.id)):
            if r.school_id not in seen and len(expected) < capacity - len(preset):
                seen.add(r.school_id)
                expected.add(r.id)
        assert {r.id for r in accepted if r.id in submitted_ids} == expected

        logs = check.exec(
            select(AuditLog).where(AuditLog.tournament_id == tournament.id)
        ).all()
        changed = Counter(
            log.entity_id for log in logs if log.action == "registration.status_changed"
        )
        assert {r.id: changed[r.id] for r in submitted} == {r.id: 2 for r in submitted}
        summaries = [
            log for log in logs if log.action == "registration.priority_window_settled"
        ]
        assert len(summaries) == 1
        settlements = check.exec(
            select(PriorityWindowSettlement).where(
                PriorityWindowSettlement.tournament_id == tournament.id
            )
        ).all()
        assert len(settlements) == 1

        events = [
            e
            for e in _events(check, tournament.id)
            if e.type == "RegistrationAllocated"
        ]
        assert sorted(e.payload["registration_id"] for e in events) == sorted(
            str(r.id) for r in submitted
        )
        return registrations


def _cleanup(tournament_id: uuid.UUID, team_ids: list[uuid.UUID]) -> None:
    with Session(engine) as cleanup:
        event_ids = [e.id for e in _events(cleanup, tournament_id)]
        cleanup.execute(delete(OutboxEvent).where(col(OutboxEvent.id).in_(event_ids)))
        cleanup.execute(
            delete(PriorityWindowSettlement).where(
                col(PriorityWindowSettlement.tournament_id) == tournament_id
            )
        )
        cleanup.execute(
            delete(Registration).where(col(Registration.tournament_id) == tournament_id)
        )
        cleanup.execute(delete(TeamMember).where(col(TeamMember.team_id).in_(team_ids)))
        cleanup.execute(delete(Team).where(col(Team.id).in_(team_ids)))
        cleanup.commit()


SUBMISSIONS = 200
CAPACITY = 32


def test_200_parallel_submissions_never_exceed_capacity() -> None:
    """名額 32、200 隊（139 所學校，其中 61 所各 2 隊）平行送出：正取 32、其餘候補。"""
    tournament, team_ids, submitters = _setup(capacity=CAPACITY, teams=SUBMISSIONS)
    try:
        outcomes = _submit_all(submitters, barrier=False)

        assert sorted(set(outcomes)) == ["accepted", "waitlisted"], outcomes
        assert Counter(outcomes) == {
            "accepted": CAPACITY,
            "waitlisted": SUBMISSIONS - CAPACITY,
        }
        registrations = _check(tournament, submitters, capacity=CAPACITY)
        assert len(registrations) == SUBMISSIONS
        assert len({r.id for r in registrations.values()}) == SUBMISSIONS
    finally:
        _cleanup(tournament.id, team_ids)


LAST_SEAT_RACERS = 10


def test_last_seat_goes_to_exactly_one_of_simultaneous_submissions() -> None:
    """名額 2、已有 1 隊正取，10 隊各屬其他學校同時送出：只有 1 隊正取。"""
    tournament, team_ids, submitters = _setup(
        capacity=2, teams=LAST_SEAT_RACERS, accepted_school_index=0
    )
    try:
        outcomes = _submit_all(submitters, barrier=True)

        assert Counter(outcomes) == {
            "accepted": 1,
            "waitlisted": LAST_SEAT_RACERS - 1,
        }, outcomes
        registrations = _check(tournament, submitters, capacity=2)
        accepted = [
            r for r in registrations.values() if r.status == RegistrationStatus.ACCEPTED
        ]
        assert len(accepted) == 2
    finally:
        _cleanup(tournament.id, team_ids)
