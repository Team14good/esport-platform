"""Story 5.1（AD-6、NFR-1）：真實 PostgreSQL 上兩隊隊長同時報到同一場。

報到先鎖賽事、再鎖場次（AD-6），兩個交易由賽事鎖序列化：兩隊都應報到成功，
不會死結、不會出現重複的報到紀錄，也不會多出操作紀錄以外的副作用。

Barrier 只讓兩條連線同時起跑，不保證每次都交錯在「讀 → 寫」之間，所以這是機率性的偵測；
確定的先後順序在 test_check_in.py。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture（比照
test_retire_concurrency.py）：結束時刪除報到、對戰表、場次與新事件，賽事改為已取消。
報到的操作紀錄（只增不改）會留在測試資料庫；test_check_in.py 以全域筆數斷言
「沒有新紀錄」，依檔名順序它先於本檔執行。
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, service
from app.modules.competition.models import Bracket, CheckIn, Match
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, FrozenClockLike, draw_with
from tests.helpers import make_account
from tests.registration.test_team_concurrency import _demote_game_creator

pytestmark = pytest.mark.usefixtures("frozen_clock")

UNEXPECTED_PREFIX = "unexpected:"


class World:
    """已提交、賽程已公布的 4 隊賽事；M1 是隊伍 `a` 對隊伍 `b`（沒有候補）。"""

    def __init__(self, fake: FakeRegistration, frozen_clock: FrozenClockLike) -> None:
        with Session(engine) as db:
            self.event_ids_before = set(db.exec(select(OutboxEvent.id)).all())
            tournament, _bracket = draw_with(db, fake, 4)
            _demote_game_creator(db, tournament.game_id)
            self.tournament_id: uuid.UUID = tournament.id
            self.organizer_id: uuid.UUID = tournament.organizer_id
            self.captains = {t: make_account(db).id for t in fake.teams}
            for team_id, account_id in self.captains.items():
                fake.set_captain(team_id, account_id)
            match = db.exec(
                select(Match).where(
                    Match.tournament_id == tournament.id, Match.code == "M1"
                )
            ).one()
            assert match.team_a_id is not None and match.team_b_id is not None
            self.match_id: uuid.UUID = match.id
            self.team_a: uuid.UUID = match.team_a_id
            self.team_b: uuid.UUID = match.team_b_id
            self.opens_at = match.scheduled_at - timedelta(minutes=10)
            db.commit()
        # 報到要在開放時間內
        frozen_clock.set(self.opens_at)

    def check_in_a(self, db: Session) -> None:
        service.check_in(
            db,
            tournament_id=self.tournament_id,
            match_id=self.match_id,
            account_id=self.captains[self.team_a],
        )

    def check_in_b(self, db: Session) -> None:
        service.check_in(
            db,
            tournament_id=self.tournament_id,
            match_id=self.match_id,
            account_id=self.captains[self.team_b],
        )

    def cleanup(self) -> None:
        with Session(engine) as db:
            db.execute(delete(CheckIn).where(col(CheckIn.match_id) == self.match_id))
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
            except Exception as exc:
                result = f"{UNEXPECTED_PREFIX}{exc!r}"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=_run, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


@pytest.fixture
def world(
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[World]:
    monkeypatch.setattr(registration_port, "is_captain", fake_registration.is_captain)
    monkeypatch.setattr(registration_port, "is_member", fake_registration.is_member)
    result = World(fake_registration, frozen_clock)
    try:
        yield result
    finally:
        result.cleanup()


@pytest.mark.parametrize("_attempt", range(3))
def test_both_teams_check_in_at_the_same_time(world: World, _attempt: int) -> None:
    outcomes = _run_parallel([world.check_in_a, world.check_in_b])

    # 沒有死結、沒有非預期錯誤，兩隊都成功
    assert outcomes == ["ok", "ok"], outcomes
    with Session(engine) as check:
        check_ins = check.exec(
            select(CheckIn).where(CheckIn.match_id == world.match_id)
        ).all()
        # 每隊恰好一筆，沒有重複紀錄
        assert sorted(c.team_id for c in check_ins) == sorted(
            [world.team_a, world.team_b]
        )
