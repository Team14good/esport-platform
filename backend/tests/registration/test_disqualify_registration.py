"""Story 6.5 第一階段：registration `disqualify_registration`（competition 取消資格用）。"""

import secrets
import uuid

import pytest
from sqlmodel import Session

from app.core import audit
from app.core.errors import BusinessError
from app.modules.competition import registration_port
from app.modules.registration import service
from app.modules.registration.models import Registration, RegistrationStatus, Team
from app.modules.tournaments.models import TournamentRead
from tests.conftest import FrozenClock
from tests.worker.test_priority_window_allocation import (
    _in_window,
    _school,
    _submitted,
    _tournament,
)

R = RegistrationStatus


def _registration(
    session: Session, frozen_clock: FrozenClock, status: RegistrationStatus
) -> tuple[TournamentRead, Registration]:
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    registration.status = status
    session.add(registration)
    session.flush()
    return tournament, registration


def _status_logs(session: Session, tournament: TournamentRead) -> list[audit.AuditLog]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "registration.status_changed"
    ]


@pytest.mark.parametrize("status", [R.PENDING, R.ACCEPTED, R.WAITLISTED, R.DRAWN])
def test_disqualifies_submitted_or_drawn_registration(
    session: Session, frozen_clock: FrozenClock, status: RegistrationStatus
) -> None:
    tournament, registration = _registration(session, frozen_clock, status)

    result = service.disqualify_registration(
        session, team_id=registration.team_id, actor_id=tournament.organizer_id
    )

    assert result.id == registration.id
    assert result.status == R.DISQUALIFIED
    session.refresh(registration)
    assert registration.status == R.DISQUALIFIED
    logs = _status_logs(session, tournament)
    assert (logs[-1].entity_id, logs[-1].actor_id) == (
        registration.id,
        tournament.organizer_id,
    )
    assert (logs[-1].before, logs[-1].after) == (
        {"status": status.value},
        {"status": "disqualified"},
    )


def test_already_disqualified_is_409(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, registration = _registration(session, frozen_clock, R.DRAWN)
    service.disqualify_registration(
        session, team_id=registration.team_id, actor_id=tournament.organizer_id
    )
    logs_before = len(_status_logs(session, tournament))

    with pytest.raises(BusinessError) as caught:
        service.disqualify_registration(
            session, team_id=registration.team_id, actor_id=tournament.organizer_id
        )

    assert (caught.value.code, caught.value.status_code) == (
        "TEAM_ALREADY_DISQUALIFIED",
        409,
    )
    assert caught.value.message == "這支隊伍已被取消資格。"
    assert len(_status_logs(session, tournament)) == logs_before


def test_forming_registration_cannot_be_disqualified(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    team = Team(
        tournament_id=tournament.id,
        name="組隊中",
        invite_token=secrets.token_urlsafe(24),
    )
    session.add(team)
    session.flush()
    session.add(
        Registration(team_id=team.id, tournament_id=tournament.id, status=R.FORMING)
    )
    session.flush()

    with pytest.raises(BusinessError) as caught:
        service.disqualify_registration(
            session, team_id=team.id, actor_id=tournament.organizer_id
        )

    assert caught.value.code == "REGISTRATION_INVALID_TRANSITION"
    assert _status_logs(session, tournament) == []


def test_missing_registration_is_404(session: Session) -> None:
    with pytest.raises(BusinessError) as caught:
        service.disqualify_registration(
            session, team_id=uuid.uuid4(), actor_id=uuid.uuid4()
        )

    assert (caught.value.code, caught.value.status_code) == (
        "REGISTRATION_NOT_FOUND",
        404,
    )


def test_competition_port_reads_state_and_disqualifies(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, registration = _registration(session, frozen_clock, R.DRAWN)

    state = registration_port.get_registration_state(
        session, team_id=registration.team_id
    )
    assert state == registration_port.RegistrationState(
        tournament_id=tournament.id, disqualified=False
    )

    registration_port.disqualify_registration(
        session, team_id=registration.team_id, actor_id=tournament.organizer_id
    )

    state = registration_port.get_registration_state(
        session, team_id=registration.team_id
    )
    assert state.disqualified is True
