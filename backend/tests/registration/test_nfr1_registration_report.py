"""Story 7.3（NFR-1）：校園賽優先期內平行送出 200 筆報名，優先期結束分配後比對正取數與名額。

200 支 1 人隊伍分屬初始資料的學校（同校可能有多隊），32 條連線同時送出；優先期結束時
直接呼叫 `settle_priority_window`（worker 的 `allocate_priority_windows` 會挑測試資料庫裡
所有到期的賽事，這裡只結算自己的賽事）。確認報名一筆都沒少、沒有重複，正取不超過名額、
每校最多一隊（FR-14 代表隊），並把數字記給測試報告。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture。被只增不改的
操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫（比照 test_settlement_concurrency.py），
賽事改為已取消；隊伍、隊員、報名、結算紀錄與事件在結束時刪除。學校用初始資料裡的
（不新增，學校清單的測試會檢查總數）。
"""

import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import create_engine, delete, update
from sqlmodel import Session, col, select

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
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.conftest import FrozenClock
from tests.helpers import make_account, make_game, make_tournament
from tests.registration.test_submit_registration import _fill
from tests.registration.test_team_concurrency import _demote_game_creator
from tests.report_support import record_nfr1

TEAMS = 200
CAPACITY = 32
CONNECTIONS = 32


def test_200_parallel_submissions_then_priority_allocation(
    frozen_clock: FrozenClock,
) -> None:
    with Session(engine) as setup:
        event_ids_before = set(setup.exec(select(OutboxEvent.id)).all())
        game = make_game(setup, starters=1, substitutes=0)
        _demote_game_creator(setup, game.id)
        tournament = make_tournament(
            setup,
            game=game,
            capacity=CAPACITY,
            registration_start=(frozen_clock.now() - timedelta(hours=1)).isoformat(),
            priority_hours=2,
        )
        schools = list(setup.exec(select(School.id).order_by(col(School.id))))
        submitters: list[tuple[uuid.UUID, uuid.UUID]] = []
        for i in range(TEAMS):
            # 密碼雜湊很慢，這裡用不到登入，給一個假的雜湊
            captain = make_account(
                setup, school_id=schools[i % len(schools)], hashed_password="-"
            )
            team = service.create_team(
                setup,
                tournament_id=tournament.id,
                account_id=captain.id,
                name=f"NFR1-{i:03d}-{uuid.uuid4().hex[:6]}",
            )
            _fill(setup, team.id, captain, rank_score=10 + (i * 7) % 21)
            submitters.append((team.id, captain.id))
        setup.commit()
        tournament_id = tournament.id
    team_ids = [team_id for team_id, _ in submitters]

    pool = create_engine(engine.url, pool_size=CONNECTIONS, max_overflow=0)
    go = threading.Event()

    def _submit(team_id: uuid.UUID, captain_id: uuid.UUID) -> str:
        go.wait(timeout=30)
        with Session(pool) as db:
            try:
                service.submit_registration(db, team_id=team_id, account_id=captain_id)
                db.commit()
                return "ok"
            except BusinessError as exc:
                return exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                return repr(exc)

    try:
        with ThreadPoolExecutor(max_workers=CONNECTIONS) as executor:
            futures = [executor.submit(_submit, *pair) for pair in submitters]
            go.set()
            outcomes = [future.result(timeout=120) for future in futures]

        frozen_clock.set(tournament.priority_end)
        with Session(engine) as db:
            assert service.settle_priority_window(db, tournament_id=tournament_id)
            db.commit()

        with Session(engine) as check:
            registrations = list(
                check.exec(
                    select(Registration).where(
                        Registration.tournament_id == tournament_id
                    )
                )
            )
        statuses = Counter(r.status for r in registrations)
        accepted = [r for r in registrations if r.status == RegistrationStatus.ACCEPTED]
        submitted_schools = {r.school_id for r in registrations}
        record_nfr1(
            "優先期內平行送出 200 筆報名，優先期結束分配",
            submitted=TEAMS,
            succeeded=outcomes.count("ok"),
            registrations=len(registrations),
            capacity=CAPACITY,
            accepted=len(accepted),
            waitlisted=statuses[RegistrationStatus.WAITLISTED],
            schools=len(submitted_schools),
        )

        assert outcomes == ["ok"] * TEAMS, Counter(outcomes)
        # 沒有遺失、沒有重複：每隊剛好一筆報名
        assert sorted(r.team_id for r in registrations) == sorted(team_ids)
        assert len(accepted) == min(CAPACITY, len(submitted_schools))
        assert len(accepted) <= CAPACITY
        # 優先期每校只有一支代表隊能正取
        assert len({r.school_id for r in accepted}) == len(accepted)
        assert statuses[RegistrationStatus.WAITLISTED] == TEAMS - len(accepted)
    finally:
        pool.dispose()
        with Session(engine) as cleanup:
            new_events = [
                event_id
                for event_id in cleanup.exec(select(OutboxEvent.id)).all()
                if event_id not in event_ids_before
            ]
            cleanup.execute(
                delete(OutboxEvent).where(col(OutboxEvent.id).in_(new_events))
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
            cleanup.execute(
                delete(TeamMember).where(col(TeamMember.team_id).in_(team_ids))
            )
            cleanup.execute(delete(Team).where(col(Team.id).in_(team_ids)))
            cleanup.execute(
                update(Tournament)
                .where(col(Tournament.id) == tournament_id)
                .values(status=TournamentStatus.CANCELLED)
            )
            cleanup.commit()
