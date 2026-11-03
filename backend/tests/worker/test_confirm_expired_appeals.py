"""Story 5.5：worker 在申訴期滿時自動確認場次並推進晉級。

各種情境的完整測試在 tests/competition/test_confirm_advance.py；這裡確認工作已註冊，
並經 `run_once` 走一次真正的 worker 迴圈（每筆一個交易、事件由同一輪分派）。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.events import OutboxEvent
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentStatus
from app.worker import run_once
from app.worker.jobs import JOBS, confirm_expired_appeals, dispatch_outbox
from tests.competition.conftest import (  # noqa: F401  fake_registration 是 fixture
    FakeRegistration,
    draw_with,
    fake_registration,
)
from tests.conftest import FrozenClock

pytestmark = pytest.mark.usefixtures("fake_registration")


def test_confirm_expired_appeals_is_registered() -> None:
    assert confirm_expired_appeals in JOBS


def test_job_returns_false_when_nothing_is_due(session: Session) -> None:
    assert confirm_expired_appeals(session) is False


def test_one_round_confirms_expired_final_and_dispatches_events(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,  # noqa: F811
    frozen_clock: FrozenClock,
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 2)
    final = session.get(Match, bracket.matches[0].id)
    assert final is not None
    final.status = MatchStatus.APPEAL_WINDOW
    final.outcome = MatchOutcome.PLAYED
    final.winner_id = fake_registration.teams[1]
    final.appeal_deadline = datetime(2026, 10, 18, 11, 30, tzinfo=UTC)
    session.add(final)
    session.commit()

    frozen_clock.advance(timedelta(minutes=30))
    run_once([confirm_expired_appeals, dispatch_outbox], session_factory=session_factory)
    session.expire_all()

    final = session.get(Match, bracket.matches[0].id)
    assert final is not None
    assert final.status == MatchStatus.CONFIRMED
    assert final.confirmed_at == datetime(2026, 10, 18, 11, 30, tzinfo=UTC)
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == TournamentStatus.FINISHED
    )
    # 抽籤與確認的事件都已由同一輪的 dispatch_outbox 處理
    pending = session.exec(
        select(OutboxEvent).where(OutboxEvent.processed_at == None)  # noqa: E711
    ).all()
    assert pending == []
