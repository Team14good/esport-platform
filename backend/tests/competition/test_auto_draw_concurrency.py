"""Story 4.2（AD-6、NFR-1）：真實 PostgreSQL 上手動抽籤與自動抽籤同時進行，只抽一次。

手動 `draw` 與自動 `auto_draw` 都先 `lock_tournament`，鎖內再檢查有沒有對戰表；後拿到鎖的
一方看到已抽籤，手動回 `BRACKET_ALREADY_DRAWN`，自動不做任何事。把自動抽籤的鎖換成
不加鎖的讀取時，兩邊同時讀到「還沒抽籤」就都會建立對戰表，後提交的一方撞到
`bracket.tournament_id` 唯一鍵，這裡的斷言（沒有非預期錯誤）就會失敗。Barrier 只讓各連線
同時起跑，不保證每次都交錯在「讀 → 寫」之間，所以這是機率性的偵測，不是每次必中。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture（比照
test_score_concurrency.py）：結束時刪除對戰表、場次、略過紀錄與新事件，賽事改為已取消，
worker 工作不會再挑到它；被操作紀錄參照的賽事與帳號留在測試資料庫。
"""

import random
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from app.core.audit import AuditLog
from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import service
from app.modules.competition.models import AutoDrawSkip, Bracket, Match
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, tournament_in
from tests.helpers import make_account
from tests.registration.test_team_concurrency import _demote_game_creator

pytestmark = pytest.mark.usefixtures("frozen_clock")

UNEXPECTED_PREFIX = "unexpected:"


class World:
    """已提交、報名截止的賽事；正取隊數由 `fake_registration` 決定。"""

    def __init__(self, fake: FakeRegistration, team_count: int) -> None:
        with Session(engine) as db:
            self.event_ids_before = set(db.exec(select(OutboxEvent.id)).all())
            organizer = make_account(db, organizer=True)
            tournament = tournament_in(db, TournamentStatus.CLOSED, organizer=organizer)
            _demote_game_creator(db, tournament.game_id)
            db.commit()
            self.tournament_id: uuid.UUID = tournament.id
            self.organizer_id: uuid.UUID = organizer.id
        fake.set_team_count(team_count)

    def manual(self, db: Session) -> None:
        service.draw(
            db,
            tournament_id=self.tournament_id,
            actor_id=self.organizer_id,
            rng=random.Random(1),
        )

    def auto(self, db: Session) -> None:
        service.auto_draw(db, tournament_id=self.tournament_id)

    def cleanup(self) -> None:
        with Session(engine) as db:
            db.execute(
                delete(Match).where(col(Match.tournament_id) == self.tournament_id)
            )
            db.execute(
                delete(Bracket).where(col(Bracket.tournament_id) == self.tournament_id)
            )
            db.execute(
                delete(AutoDrawSkip).where(
                    col(AutoDrawSkip.tournament_id) == self.tournament_id
                )
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
def make_world(fake_registration: FakeRegistration) -> Iterator[Callable[[int], World]]:
    worlds: list[World] = []

    def _make(team_count: int) -> World:
        world = World(fake_registration, team_count)
        worlds.append(world)
        return world

    try:
        yield _make
    finally:
        for world in worlds:
            world.cleanup()


@pytest.mark.parametrize(
    "roles",
    [
        ("manual", "auto"),
        ("auto", "auto"),
        ("auto", "manual", "auto", "manual"),
    ],
    ids=["manual-auto", "auto-auto", "mixed-4"],
)
def test_parallel_draws_create_one_bracket(
    make_world: Callable[[int], World],
    fake_registration: FakeRegistration,
    roles: tuple[str, ...],
) -> None:
    world = make_world(4)
    outcomes = _run_parallel([getattr(world, role) for role in roles])

    assert not [o for o in outcomes if o.startswith(UNEXPECTED_PREFIX)], outcomes
    # 自動抽籤輸了只是不做事（ok）；手動輸了回已抽籤
    assert all(o in ("ok", "BRACKET_ALREADY_DRAWN") for o in outcomes), outcomes
    with Session(engine) as check:
        brackets = check.exec(
            select(Bracket).where(Bracket.tournament_id == world.tournament_id)
        ).all()
        assert len(brackets) == 1
        drawn_logs = check.exec(
            select(AuditLog).where(
                AuditLog.tournament_id == world.tournament_id,
                AuditLog.action == "bracket.drawn",
            )
        ).all()
        assert len(drawn_logs) == 1
        events = [
            e
            for e in check.exec(
                select(OutboxEvent).where(OutboxEvent.type == "BracketDrawn")
            ).all()
            if e.payload["tournament_id"] == str(world.tournament_id)
        ]
        assert len(events) == 1
        status = check.exec(
            select(Tournament.status).where(Tournament.id == world.tournament_id)
        ).one()
        assert status == TournamentStatus.PUBLISHED
    assert len(fake_registration.drawn) == 1


def test_parallel_auto_draws_with_not_enough_teams_notify_once(
    make_world: Callable[[int], World],
) -> None:
    world = make_world(1)
    outcomes = _run_parallel([world.auto, world.auto, world.auto])

    assert outcomes == ["ok", "ok", "ok"], outcomes
    with Session(engine) as check:
        skips = check.exec(
            select(AutoDrawSkip).where(
                AutoDrawSkip.tournament_id == world.tournament_id
            )
        ).all()
        assert len(skips) == 1
        events = [
            e
            for e in check.exec(
                select(OutboxEvent).where(OutboxEvent.type == "AutoDrawSkipped")
            ).all()
            if e.payload["tournament_id"] == str(world.tournament_id)
        ]
        assert len(events) == 1
