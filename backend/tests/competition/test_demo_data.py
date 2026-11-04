"""Story 7.1 示範資料的 competition 步驟：替示範賽事抽籤、冪等與略過行為。"""

import logging
import uuid
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.core import clock
from app.demo_data import STEPS, competition
from app.demo_data.context import DemoContext
from app.modules.competition import service
from app.modules.tournaments.models import TournamentStatus
from tests.competition.conftest import FakeRegistration, count_matches, tournament_in
from tests.helpers import make_account

pytestmark = pytest.mark.usefixtures("frozen_clock")


def _context(tournament_id: uuid.UUID | None, organizer_id: uuid.UUID) -> DemoContext:
    return DemoContext(
        password="demo-password",
        email_domain="demo.example.com",
        accounts={"organizer": organizer_id},
        tournament_to_draw=tournament_id,
    )


def _closed_tournament(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    organizer = make_account(session, organizer=True)
    tournament = tournament_in(session, TournamentStatus.CLOSED, organizer=organizer)
    return tournament.id, organizer.id


def test_competition_step_runs_last() -> None:
    assert STEPS[-1] is competition.seed


def test_no_tournament_to_draw_is_skipped(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        competition.seed(session, _context(None, uuid.uuid4()))

    assert "No demo tournament to draw" in caplog.text


def test_draws_demo_tournament_once(
    session: Session,
    fake_registration: FakeRegistration,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_registration.set_team_count(32)
    tournament_id, organizer_id = _closed_tournament(session)
    context = _context(tournament_id, organizer_id)

    competition.seed(session, context)
    bracket = service.get_bracket(session, tournament_id=tournament_id)
    assert bracket is not None
    assert len(bracket.matches) == 32
    matches_after_first = count_matches(session, tournament_id)

    with caplog.at_level(logging.INFO):
        competition.seed(session, context)

    assert count_matches(session, tournament_id) == matches_after_first
    assert "already drawn, skipped" in caplog.text


def test_fixed_seed_gives_same_bracket(
    session: Session, fake_registration: FakeRegistration
) -> None:
    teams = fake_registration.set_team_count(13)
    brackets = []
    for _ in range(2):
        tournament_id, organizer_id = _closed_tournament(session)
        competition.seed(session, _context(tournament_id, organizer_id))
        bracket = service.get_bracket(session, tournament_id=tournament_id)
        assert bracket is not None
        brackets.append(
            {
                m.code: (
                    None if m.team_a_id is None else teams.index(m.team_a_id),
                    None if m.team_b_id is None else teams.index(m.team_b_id),
                )
                for m in bracket.matches
            }
        )

    assert brackets[0] == brackets[1]


@pytest.mark.parametrize("reason", ["start_passed", "not_owner"])
def test_rejected_draw_is_skipped_and_keeps_earlier_data(
    session: Session,
    fake_registration: FakeRegistration,
    caplog: pytest.LogCaptureFixture,
    reason: str,
) -> None:
    fake_registration.set_team_count(8)
    organizer = make_account(session, organizer=True)
    start_at = clock.now() + timedelta(days=1)
    if reason == "start_passed":
        start_at = clock.now() - timedelta(hours=1)
    tournament = tournament_in(
        session, TournamentStatus.CLOSED, organizer=organizer, start_at=start_at
    )
    tournament_id = tournament.id
    organizer_id = organizer.id
    if reason == "not_owner":
        organizer_id = make_account(session, organizer=True).id
    earlier = make_account(session)  # 前面步驟寫入的資料

    with caplog.at_level(logging.WARNING):
        competition.seed(session, _context(tournament_id, organizer_id))

    assert service.get_bracket(session, tournament_id=tournament_id) is None
    assert "not drawn" in caplog.text
    session.refresh(earlier)  # savepoint 回滾只撤銷抽籤，前面的資料還在


@pytest.mark.usefixtures("registration_without_draw_functions")
def test_registration_unavailable_is_skipped(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    tournament_id, organizer_id = _closed_tournament(session)

    with caplog.at_level(logging.WARNING):
        competition.seed(session, _context(tournament_id, organizer_id))

    assert service.get_bracket(session, tournament_id=tournament_id) is None
    assert "REGISTRATION_UNAVAILABLE" in caplog.text
