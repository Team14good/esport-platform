"""AD-6：真實 PostgreSQL 上兩個 session 同時結算同一場賽事，只結算一次。

結算靠 `lock_tournament` 的列鎖讓兩邊依序執行；後到的一方在鎖內看到已有結算紀錄就
不再結算。把鎖換成不加鎖的讀取時，兩邊都會寫結算紀錄，後提交的一方撞到結算表主鍵
而失敗，這裡的斷言就會失敗。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture。被只增不改
的操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫（比照 test_team_concurrency.py）；
隊伍、報名、結算紀錄與事件在結束時刪除。學校用初始資料裡的（不新增，學校清單的測試
會檢查總數）。
"""

import secrets
import threading
import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.core.audit import AuditLog
from app.core.db import engine
from app.core.events import OutboxEvent
from app.modules.identity.models import School
from app.modules.registration import service
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
)
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.conftest import FrozenClock
from tests.helpers import make_game, make_tournament
from tests.registration.test_team_concurrency import _demote_game_creator

Settle = Callable[[Session, uuid.UUID, uuid.UUID], object]


def _worker(db: Session, tournament_id: uuid.UUID, _actor_id: uuid.UUID) -> object:
    return service.settle_priority_window(db, tournament_id=tournament_id)


def _draw(db: Session, tournament_id: uuid.UUID, actor_id: uuid.UUID) -> object:
    return service.finalize_for_draw(db, tournament_id=tournament_id, actor_id=actor_id)


def _close(db: Session, tournament_id: uuid.UUID, _actor_id: uuid.UUID) -> object:
    return service.close_registration(db, tournament_id=tournament_id)


@pytest.mark.parametrize(
    ("first", "second"),
    [(_worker, _worker), (_worker, _draw), (_close, _close), (_close, _draw)],
    ids=[
        "worker-worker",
        "worker-finalize_for_draw",
        "close-close",
        "close-finalize_for_draw",
    ],
)
def test_parallel_settlement_happens_once(
    frozen_clock: FrozenClock, first: Settle, second: Settle
) -> None:
    """名額 2、3 校各 1 隊優先期內送出：結算 2 正取、1 候補，補位沒有空位。

    報名截止（`close_registration`）的參數組把時鐘設在報名截止時間：另外確認賽事只轉
    一次「報名截止」、最後為 `closed`（抽籤先拿到鎖時只分配不轉狀態，截止工作再轉；
    截止工作先拿到鎖時賽事已不是開放報名，`finalize_for_draw` 不做任何事）。
    """
    at_deadline = _close in (first, second)
    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        tournament = make_tournament(
            setup,
            game=game,
            capacity=2,
            registration_start=(frozen_clock.now() - timedelta(hours=1)).isoformat(),
            priority_hours=2,
        )
        schools = list(setup.exec(select(School).order_by(col(School.id)).limit(3)))
        assert len(schools) == 3
        team_ids: list[uuid.UUID] = []
        for i, school in enumerate(schools):
            team = Team(
                tournament_id=tournament.id,
                name=f"併發結算-{uuid.uuid4().hex[:8]}",
                invite_token=secrets.token_urlsafe(24),
            )
            setup.add(team)
            setup.flush()
            setup.add(
                Registration(
                    team_id=team.id,
                    tournament_id=tournament.id,
                    status=RegistrationStatus.PENDING,
                    school_id=school.id,
                    avg_rank_score=Decimal(30 - i),
                    submitted_at=tournament.registration_start
                    + timedelta(minutes=10 + i),
                )
            )
            team_ids.append(team.id)
        setup.commit()
        tournament_id, organizer_id = tournament.id, tournament.organizer_id
    frozen_clock.set(
        tournament.registration_end if at_deadline else tournament.priority_end
    )

    start = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def _run(settle: Settle) -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                settle(db, tournament_id, organizer_id)
                db.commit()
                result = "ok"
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                result = repr(exc)
        with outcomes_lock:
            outcomes.append(result)

    threads: list[threading.Thread] = []
    try:
        threads = [threading.Thread(target=_run, args=(s,)) for s in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        assert outcomes == ["ok", "ok"], outcomes
        with Session(engine) as check:
            registrations = check.exec(
                select(Registration).where(Registration.tournament_id == tournament_id)
            ).all()
            assert sorted(r.status for r in registrations) == [
                RegistrationStatus.ACCEPTED,
                RegistrationStatus.ACCEPTED,
                RegistrationStatus.WAITLISTED,
            ]
            settlements = check.exec(
                select(PriorityWindowSettlement).where(
                    PriorityWindowSettlement.tournament_id == tournament_id
                )
            ).all()
            assert len(settlements) == 1
            logs = check.exec(
                select(AuditLog).where(AuditLog.tournament_id == tournament_id)
            ).all()
            summaries = [
                log
                for log in logs
                if log.action == "registration.priority_window_settled"
            ]
            assert len(summaries) == 1
            changed = [
                log.entity_id
                for log in logs
                if log.action == "registration.status_changed"
            ]
            # 每筆報名只改一次狀態
            assert sorted(changed) == sorted(r.id for r in registrations)
            if at_deadline:
                closed = [
                    log for log in logs if log.action == "tournament.status_changed"
                ]
                assert len(closed) == 1
                assert closed[0].after == {"status": "closed"}
                status = check.exec(
                    select(Tournament.status).where(Tournament.id == tournament_id)
                ).one()
                assert status == TournamentStatus.CLOSED
            events = _allocated_events(check, tournament_id)
            assert sorted(e.payload["registration_id"] for e in events) == sorted(
                str(r.id) for r in registrations
            )
    finally:
        for thread in threads:
            thread.join(timeout=10)
        with Session(engine) as cleanup:
            event_ids = [e.id for e in _allocated_events(cleanup, tournament_id)]
            cleanup.execute(
                delete(OutboxEvent).where(col(OutboxEvent.id).in_(event_ids))
            )
            cleanup.execute(
                delete(PriorityWindowSettlement).where(
                    col(PriorityWindowSettlement.tournament_id) == tournament_id
                )
            )
            cleanup.execute(
                delete(Registration).where(
                    col(Registration.tournament_id) == tournament_id
                )
            )
            cleanup.execute(delete(Team).where(col(Team.id).in_(team_ids)))
            cleanup.commit()


def _allocated_events(session: Session, tournament_id: uuid.UUID) -> list[OutboxEvent]:
    rows = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "RegistrationAllocated")
    ).all()
    return [row for row in rows if row.payload["tournament_id"] == str(tournament_id)]
