"""Story 3.1：真實 PostgreSQL 上平行加入隊伍不會超收。

人數上限沒有資料庫約束，只靠 `lock_tournament` 的列鎖讓加入依序執行；所以這裡用多條
連線、多執行緒同時加入，資料要真正提交，另一條連線才看得到。

被只增不改的操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫（每次執行 pytest 重建一次，同一輪之後的測試都看得到這些列），
比照 1.8 的併發測試；隊伍、隊員與報名在結束時刪除。make_game 建立的平台管理員在提交前
先取消管理員身分，避免影響其他以「平台管理員人數」為前提的測試。
"""

import threading
import uuid

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.modules.identity.models import Account
from app.modules.registration import repository, service
from app.modules.registration.models import Registration, Team, TeamMember
from tests.helpers import make_account, make_game, make_tournament

JOINERS = 5


def _demote_game_creator(session: Session, game_id: uuid.UUID) -> None:
    """make_game 以新建的平台管理員建立遊戲；提交前取消他的管理員身分。"""
    log = session.exec(
        select(AuditLog).where(
            AuditLog.entity_id == game_id, AuditLog.action == "game.created"
        )
    ).one()
    assert log.actor_id is not None
    admin = session.get(Account, log.actor_id)
    assert admin is not None
    admin.is_platform_admin = False
    session.add(admin)
    session.flush()


def test_parallel_joins_never_exceed_team_size() -> None:
    """6 人隊伍已有 4 人，5 人同時加入：恰 2 人成功，其餘 409 `TEAM_FULL`。"""
    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        tournament = make_tournament(setup, game=game, starters=5, substitutes=1)
        captain = make_account(setup)
        team = service.create_team(
            setup, tournament_id=tournament.id, account_id=captain.id, name="併發隊"
        )
        for _ in range(3):
            service.join_team(
                setup,
                token=team.invite_token,
                account_id=make_account(setup).id,
            )
        joiner_ids = [make_account(setup).id for _ in range(JOINERS)]
        setup.commit()
        team_id, token = team.id, team.invite_token

    start = threading.Barrier(JOINERS)
    outcomes: dict[uuid.UUID, str] = {}
    outcomes_lock = threading.Lock()

    def _join(account_id: uuid.UUID) -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                service.join_team(db, token=token, account_id=account_id)
                db.commit()
                result = "ok"
            except BusinessError as exc:
                result = exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                result = repr(exc)
        with outcomes_lock:
            outcomes[account_id] = result

    threads: list[threading.Thread] = []
    try:
        assert team.max_members == 6
        threads = [threading.Thread(target=_join, args=(i,)) for i in joiner_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        results = sorted(outcomes.values())
        assert results == ["TEAM_FULL"] * 3 + ["ok"] * 2, outcomes
        with Session(engine) as check:
            assert repository.count_members(check, team_id) == 6
            joined = {
                member.account_id for member in repository.list_members(check, team_id)
            }
            succeeded = {i for i, result in outcomes.items() if result == "ok"}
            assert succeeded <= joined
            assert not (set(joiner_ids) - succeeded) & joined
            # 只有成功加入的人留下操作紀錄（另 3 筆是 setup 時的隊員）
            joined_logs = check.exec(
                select(AuditLog).where(
                    AuditLog.action == "team.member_joined",
                    AuditLog.entity_id == team_id,
                    col(AuditLog.actor_id).in_(joiner_ids),
                )
            ).all()
            assert len(joined_logs) == 2
            assert {log.actor_id for log in joined_logs} == succeeded
    finally:
        for thread in threads:
            thread.join(timeout=10)
        with Session(engine) as cleanup:
            cleanup.execute(
                delete(TeamMember).where(col(TeamMember.team_id) == team_id)
            )
            cleanup.execute(
                delete(Registration).where(col(Registration.team_id) == team_id)
            )
            cleanup.execute(delete(Team).where(col(Team.id) == team_id))
            cleanup.commit()
