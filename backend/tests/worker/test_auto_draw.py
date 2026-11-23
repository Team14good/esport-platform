"""Story 4.2：worker 一輪內「報名截止 → 截止補位 → 自動抽籤」接得起來（真的 registration）。

以 `frozen_clock` 推進到報名截止時間（AD-13），跑 `JOBS` 中到 `auto_draw_closed` 為止的工作
（不含寄信）。報名資料沿用 tests/worker/test_registration_deadline.py 的 helper；
報名截止時間要早於其他併發測試留下的開放報名賽事（見該檔說明）。
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session, col, select

from app.core import audit
from app.core.events import OutboxEvent
from app.modules.competition import service as competition_service
from app.modules.registration import service as registration_service
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from app.worker import run_once
from app.worker.jobs import (
    JOBS,
    auto_draw_closed,
    close_registrations,
    start_due_tournaments,
)
from tests.conftest import FrozenClock
from tests.worker.test_priority_window_allocation import (
    _in_window,
    _school,
    _statuses,
    _submitted,
)
from tests.worker.test_registration_deadline import (
    _due_tournament,
    _set,
    _settled,
    _status,
)

A = RegistrationStatus.ACCEPTED
W = RegistrationStatus.WAITLISTED
D = RegistrationStatus.DRAWN

# 一輪 worker 中到自動抽籤為止的工作（不含判棄權、事件分派與寄信）
ROUND = JOBS[: JOBS.index(auto_draw_closed) + 1]


def _round(session_factory: Callable[[], Session]) -> None:
    run_once(ROUND, session_factory=session_factory)


def _events(
    session: Session, tournament: TournamentRead, event_type: str
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.type == event_type)
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
    )
    return [r.payload for r in rows if r.payload["tournament_id"] == str(tournament.id)]


def _status_changes(session: Session, tournament: TournamentRead) -> list[Any]:
    return [
        (log.actor_id, log.after)
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "tournament.status_changed"
    ]


def test_job_runs_right_after_close_registrations() -> None:
    position = JOBS.index(auto_draw_closed)
    assert position == JOBS.index(close_registrations) + 1
    assert position < JOBS.index(start_due_tournaments)


def test_deadline_fill_then_draw_in_one_worker_round(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 名額 3、已結算；2 隊正取、1 隊候補：截止補位把候補補上，同一輪抽籤 3 隊
    tournament = _due_tournament(session, frozen_clock, capacity=3)
    t = _in_window(tournament)
    a1 = _submitted(session, tournament, _school(session), score="90", submitted_at=t)
    a2 = _submitted(session, tournament, _school(session), score="80", submitted_at=t)
    w1 = _submitted(session, tournament, _school(session), score="70", submitted_at=t)
    _set(session, a1, A)
    _set(session, a2, A)
    _set(session, w1, W)
    _settled(session, tournament)
    session.commit()

    frozen_clock.set(tournament.registration_end)
    _round(session_factory)

    assert _status(session, tournament) == TournamentStatus.PUBLISHED
    assert _statuses(session, tournament) == {a1.id: D, a2.id: D, w1.id: D}
    bracket = competition_service.get_bracket(session, tournament_id=tournament.id)
    assert bracket is not None
    assert {
        team
        for m in bracket.matches
        for team in (m.team_a_id, m.team_b_id)
        if team is not None
    } == {a1.team_id, a2.team_id, w1.team_id}
    # 報名截止與抽籤都由系統執行
    assert _status_changes(session, tournament) == [
        (None, {"status": "closed"}),
        (None, {"status": "published"}),
    ]
    drawn_logs = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "bracket.drawn"
    ]
    assert [log.actor_id for log in drawn_logs] == [None]
    assert len(_events(session, tournament, "BracketDrawn")) == 1

    # 再跑兩輪：不會再抽一次
    _round(session_factory)
    _round(session_factory)
    assert len(_events(session, tournament, "BracketDrawn")) == 1
    assert len(_status_changes(session, tournament)) == 2


def test_not_enough_teams_after_fill_stays_closed_and_notifies_once(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=4)
    only = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set(session, only, A)
    _settled(session, tournament)
    session.commit()

    frozen_clock.set(tournament.registration_end)
    _round(session_factory)

    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _statuses(session, tournament) == {only.id: A}
    assert competition_service.get_bracket(session, tournament_id=tournament.id) is None
    assert _events(session, tournament, "AutoDrawSkipped") == [
        {"tournament_id": str(tournament.id), "accepted_teams": 1}
    ]

    # 之後的週期不再發事件、不再改任何東西，worker 也不會一直重試這場
    for _ in range(3):
        _round(session_factory)
    assert len(_events(session, tournament, "AutoDrawSkipped")) == 1
    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _status_changes(session, tournament) == [(None, {"status": "closed"})]
    assert auto_draw_closed(session) is False


def _skipped_with_one_accepted(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> tuple[TournamentRead, Any]:
    """名額 2、只有一隊正取，截止後略過自動抽籤；回傳賽事與那筆報名。"""
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    a1 = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set(session, a1, A)
    _settled(session, tournament)
    session.commit()

    frozen_clock.set(tournament.registration_end)
    _round(session_factory)
    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert len(_events(session, tournament, "AutoDrawSkipped")) == 1
    return tournament, a1


def test_raise_capacity_after_skip_is_drawn_in_next_round(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament, a1 = _skipped_with_one_accepted(session, session_factory, frozen_clock)
    # 目前截止時已用候補補滿，略過後不會有排得上的候補；這裡直接寫入一筆候補，
    # 模擬之後正取來源增加（3.10 自訂模式），遞補與抽籤走真的 raise_capacity 與 worker
    w1 = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set(session, w1, W)
    session.commit()

    registration_service.raise_capacity(
        session,
        tournament_id=tournament.id,
        capacity=3,
        actor_id=tournament.organizer_id,
    )
    session.commit()
    assert auto_draw_closed(session) is True
    session.commit()

    assert _status(session, tournament) == TournamentStatus.PUBLISHED
    assert _statuses(session, tournament) == {a1.id: D, w1.id: D}
    assert len(_events(session, tournament, "BracketDrawn")) == 1
    # 沒有第二則「正取不足」
    assert len(_events(session, tournament, "AutoDrawSkipped")) == 1
    # 下一輪沒有東西可處理
    assert auto_draw_closed(session) is False
    _round(session_factory)
    assert len(_events(session, tournament, "BracketDrawn")) == 1


def test_still_not_enough_after_skip_is_not_locked_nor_notified(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament, a1 = _skipped_with_one_accepted(session, session_factory, frozen_clock)
    locked: list[object] = []
    real_auto_draw = competition_service.auto_draw

    def spy(session: Session, *, tournament_id: Any, **kwargs: Any) -> Any:
        locked.append(tournament_id)
        return real_auto_draw(session, tournament_id=tournament_id, **kwargs)

    monkeypatch.setattr(competition_service, "auto_draw", spy)

    for _ in range(3):
        _round(session_factory)

    # 預先排除生效：仍不足的賽事不進 auto_draw（不鎖）
    assert tournament.id not in locked

    assert auto_draw_closed(session) is False
    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _statuses(session, tournament)[a1.id] == A
    assert len(_events(session, tournament, "AutoDrawSkipped")) == 1
    assert _events(session, tournament, "BracketDrawn") == []
