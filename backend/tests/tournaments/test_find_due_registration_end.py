"""Story 3.6：`find_due_registration_end_id` 找報名截止已到、仍為開放報名的賽事。

`frozen_clock` 固定在 2026-10-18 11:00 UTC。測試資料庫裡有併發測試真正提交、仍為開放
報名的賽事（tests/registration/test_settlement_concurrency.py，報名截止 2026-10-25
11:00），所以這裡的報名截止時間與時鐘都早於它（報名開始＋3 小時）。
"""

import uuid
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.modules.tournaments import service
from app.modules.tournaments.models import Tournament, TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.helpers import make_tournament


def _tournament(
    session: Session, frozen_clock: FrozenClock, *, end_hours: float = 2
) -> TournamentRead:
    """報名 1 小時前開始、`end_hours` 小時後截止的開放報名賽事。"""
    now = frozen_clock.now()
    return make_tournament(
        session,
        registration_start=(now - timedelta(hours=1)).isoformat(),
        registration_end=(now + timedelta(hours=end_hours)).isoformat(),
        priority_hours=1,
    )


def _set_status(
    session: Session, tournament_id: uuid.UUID, status: TournamentStatus
) -> None:
    row = session.get(Tournament, tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.flush()


def test_due_tournament_is_found_at_registration_end(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)

    frozen_clock.set(tournament.registration_end - timedelta(microseconds=1))
    assert service.find_due_registration_end_id(session) is None

    frozen_clock.set(tournament.registration_end)
    assert service.find_due_registration_end_id(session) == tournament.id


@pytest.mark.parametrize(
    "status", [s for s in TournamentStatus if s != TournamentStatus.OPEN]
)
def test_tournament_not_open_is_not_found(
    session: Session, frozen_clock: FrozenClock, status: TournamentStatus
) -> None:
    tournament = _tournament(session, frozen_clock)
    _set_status(session, tournament.id, status)

    frozen_clock.set(tournament.registration_end + timedelta(hours=1))

    assert service.find_due_registration_end_id(session) is None


def test_earliest_registration_end_comes_first(
    session: Session, frozen_clock: FrozenClock
) -> None:
    later = _tournament(session, frozen_clock, end_hours=3)
    earlier = _tournament(session, frozen_clock, end_hours=2)
    frozen_clock.set(later.registration_end + timedelta(minutes=1))

    assert service.find_due_registration_end_id(session) == earlier.id

    _set_status(session, earlier.id, TournamentStatus.CLOSED)
    assert service.find_due_registration_end_id(session) == later.id


def test_same_registration_end_is_ordered_by_id(
    session: Session, frozen_clock: FrozenClock
) -> None:
    first = _tournament(session, frozen_clock)
    second = _tournament(session, frozen_clock)
    assert first.registration_end == second.registration_end
    frozen_clock.set(first.registration_end)

    assert service.find_due_registration_end_id(session) == min(first.id, second.id)
