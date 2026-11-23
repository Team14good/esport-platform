"""Story 3.10：真實 PostgreSQL 上自訂模式平行送出不超收（I/O 矩陣「最後一個名額」）。

自訂模式送出時靠 `lock_tournament` 的列鎖讓判定依序執行，`_custom_locked` 在鎖內讀最新
狀態；把鎖換成不加鎖的讀取時，同時送出的隊伍都會看到有空位而超收，這裡的斷言就會失敗。

沿用 test_first_come_concurrency.py 的做法：資料真正提交（不用外層交易的 `session`
fixture、不凍結時鐘），送出用另建的 engine 與 20 條執行緒（`_submit_all`）。賽事建立後
直接把賽事列改成自訂模式。隊長一半沒有設定學校、一半同校：自訂模式不檢查學校、沒有
每校上限，所以正取可以全部同校。結束時刪除事件、報名、隊員與隊伍，賽事改為已取消
（被只增不改的操作紀錄參照，刪不掉）。
"""

import secrets
import uuid
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from sqlmodel import Session, col, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.db import engine
from app.modules.identity.models import School
from app.modules.registration import service
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
)
from app.modules.tournaments.models import Tournament, TournamentMode, TournamentRead
from tests.helpers import make_account, make_game, make_tournament
from tests.registration.test_first_come_concurrency import (
    _cleanup,
    _events,
    _submit_all,
)
from tests.registration.test_settlement_concurrency import _cancel
from tests.registration.test_submit_registration import _fill
from tests.registration.test_team_concurrency import _demote_game_creator

S = RegistrationStatus


def _setup_custom(
    *, capacity: int, teams: int, preset_accepted: int = 0
) -> tuple[TournamentRead, list[uuid.UUID], list[tuple[uuid.UUID, uuid.UUID]]]:
    """建立報名中的自訂賽事與 `teams` 支填完資料的一人隊伍。

    第 i 隊的隊長在 i 為偶數時沒有學校，奇數時都屬初始資料的第一所學校。
    `preset_accepted` 支已正取的隊伍直接寫入（不經送出，學校快照為 null）。
    回傳賽事、全部隊伍 id 與（隊伍 id, 隊長 id）。
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
            priority_hours=1,
        )
        row = setup.get(Tournament, tournament.id)
        assert row is not None
        row.mode = TournamentMode.CUSTOM
        setup.add(row)
        school = setup.exec(select(School).order_by(col(School.id))).first()
        assert school is not None
        team_ids: list[uuid.UUID] = []
        for i in range(preset_accepted):
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
                    status=S.ACCEPTED,
                    avg_rank_score=Decimal(30),
                    submitted_at=tournament.registration_start
                    + timedelta(minutes=i + 1),
                )
            )
            team_ids.append(team.id)
        submitters: list[tuple[uuid.UUID, uuid.UUID]] = []
        for i in range(teams):
            # 不雜湊密碼，200 個帳號才不會拖慢測試
            captain = make_account(
                setup,
                school_id=None if i % 2 == 0 else school.id,
                hashed_password="x",
            )
            created = service.create_team(
                setup,
                tournament_id=tournament.id,
                account_id=captain.id,
                name=f"自訂隊-{i}",
            )
            _fill(setup, created.id, captain)
            team_ids.append(created.id)
            submitters.append((created.id, captain.id))
        setup.commit()
        return service._get_tournament(setup, tournament.id), team_ids, submitters


def _check_custom(
    tournament: TournamentRead,
    submitters: list[tuple[uuid.UUID, uuid.UUID]],
    *,
    capacity: int,
) -> dict[uuid.UUID, Registration]:
    """正取不超過名額、全部填滿；正取就是依（送出時間, id）的前幾支；沒有遺失或重複。"""
    with Session(engine) as check:
        registrations = {
            r.team_id: r
            for r in check.exec(
                select(Registration).where(Registration.tournament_id == tournament.id)
            ).all()
        }
        submitted = [registrations[team_id] for team_id, _ in submitters]
        assert {r.status for r in submitted} <= {S.ACCEPTED, S.WAITLISTED}
        assert all(r.school_id is None for r in submitted)
        accepted = [r for r in registrations.values() if r.status == S.ACCEPTED]
        assert len(accepted) == min(capacity, len(registrations))

        # 公平性：依送出時間（同時再依 id）先到先得，不看學校
        submitted_ids = {r.id for r in submitted}
        preset = [r for r in accepted if r.id not in submitted_ids]
        ordered = sorted(submitted, key=lambda r: (r.submitted_at, r.id))
        expected = {r.id for r in ordered[: capacity - len(preset)]}
        assert {r.id for r in accepted if r.id in submitted_ids} == expected

        logs = check.exec(
            select(AuditLog).where(AuditLog.tournament_id == tournament.id)
        ).all()
        changed = Counter(
            log.entity_id for log in logs if log.action == "registration.status_changed"
        )
        assert {r.id: changed[r.id] for r in submitted} == {r.id: 2 for r in submitted}
        assert not [
            log for log in logs if log.action == "registration.priority_window_settled"
        ]
        assert not check.exec(
            select(PriorityWindowSettlement).where(
                PriorityWindowSettlement.tournament_id == tournament.id
            )
        ).all()

        events = [
            e
            for e in _events(check, tournament.id)
            if e.type == "RegistrationAllocated"
        ]
        assert sorted(e.payload["registration_id"] for e in events) == sorted(
            str(r.id) for r in submitted
        )
        return registrations


SUBMISSIONS = 200
CAPACITY = 32


def test_custom_200_parallel_submissions_never_exceed_capacity() -> None:
    """名額 32、200 隊（一半沒有學校、一半同校）平行送出：正取 32、其餘候補，順位連續。"""
    tournament, team_ids, submitters = _setup_custom(
        capacity=CAPACITY, teams=SUBMISSIONS
    )
    try:
        outcomes = _submit_all(submitters, barrier=False)

        assert Counter(outcomes) == {
            "accepted": CAPACITY,
            "waitlisted": SUBMISSIONS - CAPACITY,
        }, outcomes
        registrations = _check_custom(tournament, submitters, capacity=CAPACITY)
        assert len(registrations) == SUBMISSIONS
        assert len({r.id for r in registrations.values()}) == SUBMISSIONS
        # 候補全部有順位，依送出時間 1..N 連續
        with Session(engine) as db:
            waiting = sorted(
                (r for r in registrations.values() if r.status == S.WAITLISTED),
                key=lambda r: (r.submitted_at, r.id),
            )
            phase, order = service._waitlist_order(
                db, tournament, list(registrations.values())
            )
            assert phase == "custom"
            assert [order[r.id].position for r in waiting] == list(
                range(1, len(waiting) + 1)
            )
    finally:
        _cleanup(tournament.id, team_ids)
        _cancel(tournament.id)


LAST_SEAT_RACERS = 10


def test_custom_last_seat_goes_to_exactly_one_of_simultaneous_submissions() -> None:
    """名額 2、已有 1 隊正取，10 隊同時送出：只有 1 隊正取。"""
    tournament, team_ids, submitters = _setup_custom(
        capacity=2, teams=LAST_SEAT_RACERS, preset_accepted=1
    )
    try:
        outcomes = _submit_all(submitters, barrier=True)

        assert Counter(outcomes) == {
            "accepted": 1,
            "waitlisted": LAST_SEAT_RACERS - 1,
        }, outcomes
        registrations = _check_custom(tournament, submitters, capacity=2)
        assert sum(1 for r in registrations.values() if r.status == S.ACCEPTED) == 2
    finally:
        _cleanup(tournament.id, team_ids)
        _cancel(tournament.id)
