"""Story 7.3（NFR-1）：真實 PostgreSQL 上同時登錄同一場次的比分，不會互相覆蓋或重複。

登錄與送出都先 `lock_match`（AD-6），多個請求依序執行；`(match_id, game_no)` 唯一鍵是
最後防線。這裡用多條連線、多個執行緒同時呼叫 service（比照 router：成功才 commit）。

- 同時登錄同一局：依 5.3 的規則，局號不大於目前局數是「覆寫」，所以後到的請求會依序覆寫
  而不是被拒絕；要確認的是只留一筆該局紀錄、沒有 500（唯一鍵衝突）、每次寫入都有操作紀錄，
  場次的勝局數與最後留下的那一局一致。
- 同時送出系列結果：只有一個成功，其餘收到業務錯誤；只有一筆送出紀錄與一個事件。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture。被只增不改的
操作紀錄參照的賽事與帳號刪不掉，留在測試資料庫（比照 tests/registration 的併發測試），
賽事改為已取消，worker 工作不會再挑到它；對戰表、場次、局、報到紀錄與事件在結束時刪除。
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, update
from sqlmodel import Session, col, func, select

from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import service
from app.modules.competition.models import (
    Bracket,
    CheckIn,
    GameScoreIn,
    Match,
    MatchGame,
    MatchStatus,
)
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration
from tests.competition.test_score_entry import Setup
from tests.registration.test_team_concurrency import _demote_game_creator
from tests.report_support import record_nfr1

pytestmark = pytest.mark.usefixtures("frozen_clock")

THREADS = 8


class World:
    """已提交的 8 隊賽事；M1 兩隊都已報到、未指派裁判（記分者是主辦方）。"""

    def __init__(self, fake: FakeRegistration) -> None:
        with Session(engine) as db:
            self.event_ids_before = set(db.exec(select(OutboxEvent.id)).all())
            setup = Setup(db, fake)
            game_id = db.exec(
                select(Tournament.game_id).where(Tournament.id == setup.tournament_id)
            ).one()
            _demote_game_creator(db, game_id)
            db.commit()
            self.tournament_id = setup.tournament_id
            self.match_id = setup.match_id("M1")
            self.organizer_id = setup.organizer.id

    def record(self, db: Session, game_no: int, winner: str) -> None:
        service.record_game(
            db,
            tournament_id=self.tournament_id,
            match_id=self.match_id,
            account_id=self.organizer_id,
            game_no=game_no,
            data=GameScoreIn(winner_side=winner),  # type: ignore[arg-type]
        )

    def cleanup(self) -> None:
        with Session(engine) as db:
            match_ids = list(
                db.exec(
                    select(Match.id).where(Match.tournament_id == self.tournament_id)
                ).all()
            )
            db.execute(delete(MatchGame).where(col(MatchGame.match_id).in_(match_ids)))
            db.execute(delete(CheckIn).where(col(CheckIn.match_id).in_(match_ids)))
            db.execute(
                delete(Match).where(col(Match.tournament_id) == self.tournament_id)
            )
            db.execute(
                delete(Bracket).where(col(Bracket.tournament_id) == self.tournament_id)
            )
            new_events = [
                event_id
                for event_id in db.exec(select(OutboxEvent.id)).all()
                if event_id not in self.event_ids_before
            ]
            db.execute(delete(OutboxEvent).where(col(OutboxEvent.id).in_(new_events)))
            db.execute(
                update(Tournament)
                .where(col(Tournament.id) == self.tournament_id)
                .values(status=TournamentStatus.CANCELLED)
            )
            db.commit()


@pytest.fixture
def world(fake_registration: FakeRegistration) -> Iterator[World]:
    created = World(fake_registration)
    try:
        yield created
    finally:
        created.cleanup()


def _run_parallel(actions: list[Callable[[Session], Any]]) -> list[str]:
    """每個動作各用一條連線同時開始；成功 commit 回 "ok"，業務錯誤回錯誤代碼。"""
    start = threading.Barrier(len(actions))
    outcomes: list[str] = []
    lock = threading.Lock()

    def _run(action: Callable[[Session], Any]) -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                action(db)
                db.commit()
                result = "ok"
            except BusinessError as exc:
                result = exc.code
            except Exception as exc:  # 讓非預期錯誤（例如唯一鍵衝突）出現在斷言訊息裡
                result = repr(exc)
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=_run, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


def _audits(db: Session, world: World, action: str) -> list[AuditLog]:
    return list(
        db.exec(
            select(AuditLog).where(
                AuditLog.entity_id == world.match_id, AuditLog.action == action
            )
        ).all()
    )


def test_parallel_records_of_the_same_game_keep_one_row(world: World) -> None:
    """8 個請求同時登錄 M1 第 1 局（勝隊 a、b 交錯）：只留一筆，每次寫入都有紀錄、沒有 500。"""
    winners = ["a" if i % 2 == 0 else "b" for i in range(THREADS)]
    outcomes = _run_parallel(
        [(lambda db, w=winner: world.record(db, 1, w)) for winner in winners]
    )

    with Session(engine) as check:
        rows = list(
            check.exec(select(MatchGame).where(MatchGame.match_id == world.match_id))
        )
        match = check.get(Match, world.match_id)
        logs = _audits(check, world, "match.game_recorded")
    succeeded = outcomes.count("ok")
    business_errors = [o for o in outcomes if o != "ok" and not o.startswith("<")]
    record_nfr1(
        "同時登錄同一場次同一局",
        submitted=THREADS,
        succeeded=succeeded,
        business_errors=len(business_errors),
        unexpected_errors=THREADS - succeeded - len(business_errors),
        rows=len(rows),
        expected_rows=1,
    )

    assert sorted(outcomes) == ["ok"] * THREADS, outcomes
    assert [row.game_no for row in rows] == [1]
    assert match is not None
    assert match.status == MatchStatus.LIVE
    # 勝局數跟最後留下的那一局一致（沒有被另一個請求的舊值蓋掉）
    assert (match.wins_a, match.wins_b) == (
        (1, 0) if rows[0].winner_side == "a" else (0, 1)
    )
    # 一次新增（含轉為進行中）＋其餘依序覆寫，每次寫入一筆紀錄
    assert len(logs) == THREADS
    created = [log for log in logs if log.before == {"status": "scheduled"}]
    assert len(created) == 1
    assert sorted(str(log.after["winner_side"]) for log in logs) == sorted(winners)


def test_parallel_submissions_of_the_same_match_happen_once(world: World) -> None:
    """系列已分出勝負（2:0），8 個送出請求同時到達：只有一個成功，其餘收到業務錯誤。"""
    with Session(engine) as db:
        world.record(db, 1, "a")
        world.record(db, 2, "a")
        db.commit()

    def _submit(db: Session) -> None:
        service.submit_result(
            db,
            tournament_id=world.tournament_id,
            match_id=world.match_id,
            account_id=world.organizer_id,
        )

    outcomes = _run_parallel([_submit] * THREADS)

    with Session(engine) as check:
        match = check.get(Match, world.match_id)
        logs = _audits(check, world, "match.result_submitted")
        games = check.exec(
            select(func.count()).where(MatchGame.match_id == world.match_id)
        ).one()
        events = [
            event
            for event in check.exec(
                select(OutboxEvent).where(OutboxEvent.type == "MatchResultSubmitted")
            )
            if event.payload.get("match_id") == str(world.match_id)
        ]
    business_errors = [o for o in outcomes if o != "ok" and not o.startswith("<")]
    record_nfr1(
        "同時送出同一場次的系列結果",
        submitted=THREADS,
        succeeded=outcomes.count("ok"),
        business_errors=len(business_errors),
        unexpected_errors=THREADS - outcomes.count("ok") - len(business_errors),
        rows=len(logs),
        expected_rows=1,
    )

    assert outcomes.count("ok") == 1, outcomes
    assert len(business_errors) == THREADS - 1, outcomes
    assert match is not None
    assert match.status == MatchStatus.APPEAL_WINDOW
    assert (match.wins_a, match.wins_b) == (2, 0)
    assert games == 2
    assert len(logs) == 1
    assert len(events) == 1
