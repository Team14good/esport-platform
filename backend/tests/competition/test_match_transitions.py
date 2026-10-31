"""Story 4.1 第二階段：場次狀態轉換、加鎖、查詢與棄權期限。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.competition import service
from app.modules.competition.models import Match, MatchStatus
from tests.competition.conftest import FakeRegistration, FrozenClockLike, draw_with

M = MatchStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

ALLOWED = {
    (M.SCHEDULED, M.LIVE),
    (M.SCHEDULED, M.APPEAL_WINDOW),
    (M.SCHEDULED, M.CONFIRMED),
    (M.SCHEDULED, M.VOIDED),
    (M.LIVE, M.APPEAL_WINDOW),
    (M.LIVE, M.CONFIRMED),
    (M.APPEAL_WINDOW, M.APPEALED),
    (M.APPEAL_WINDOW, M.CONFIRMED),
    (M.APPEALED, M.CONFIRMED),
    (M.APPEALED, M.SCHEDULED),
}
FORBIDDEN = [(a, b) for a in M for b in M if (a, b) not in ALLOWED]


def _first_match(session: Session, fake: FakeRegistration) -> Match:
    _tournament, bracket = draw_with(session, fake, 2)
    return service.lock_match(session, match_id=bracket.matches[0].id)


def _set_status(session: Session, match: Match, status: MatchStatus) -> None:
    match.status = status
    session.add(match)
    session.flush()


def test_forbidden_list_has_expected_size() -> None:
    assert len(FORBIDDEN) == 26


@pytest.mark.parametrize(("source", "target"), sorted(ALLOWED))
def test_allowed_transition_changes_status(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    source: MatchStatus,
    target: MatchStatus,
) -> None:
    match = _first_match(session, fake_registration)
    _set_status(session, match, source)
    frozen_clock.advance(timedelta(minutes=5))

    service.transition_match(session, match=match, to=target)

    fetched = service.get_match(session, match_id=match.id)
    assert fetched.status == target
    assert match.updated_at == datetime(2026, 10, 18, 11, 5, tzinfo=UTC)


@pytest.mark.parametrize(("source", "target"), FORBIDDEN)
def test_forbidden_transition_is_409(
    session: Session,
    fake_registration: FakeRegistration,
    source: MatchStatus,
    target: MatchStatus,
) -> None:
    match = _first_match(session, fake_registration)
    _set_status(session, match, source)

    with pytest.raises(BusinessError) as excinfo:
        service.transition_match(session, match=match, to=target)

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "MATCH_INVALID_TRANSITION",
        409,
    )
    assert service.get_match(session, match_id=match.id).status == source


def test_missing_match_is_404(session: Session) -> None:
    for call in (service.get_match, service.lock_match):
        with pytest.raises(BusinessError) as excinfo:
            call(session, match_id=uuid.uuid4())
        assert (excinfo.value.code, excinfo.value.status_code) == (
            "MATCH_NOT_FOUND",
            404,
        )


def test_lock_match_returns_latest_row(
    session: Session, fake_registration: FakeRegistration
) -> None:
    match = _first_match(session, fake_registration)

    locked = service.lock_match(session, match_id=match.id)

    assert locked is match
    assert (locked.code, locked.status) == ("M1", MatchStatus.SCHEDULED)


def test_list_team_matches_orders_by_round(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 3 隊：1 支輪空隊伍只在第二輪（M2），另外 2 隊只在第一輪（M1）
    tournament, bracket = draw_with(session, fake_registration, 3)
    final = next(m for m in bracket.matches if m.code == "M2")
    bye_team = final.team_a_id if final.bye_a else final.team_b_id
    assert bye_team is not None
    first = next(m for m in bracket.matches if m.code == "M1")
    assert first.team_a_id is not None

    assert [
        m.code
        for m in service.list_team_matches(
            session, tournament_id=tournament.id, team_id=bye_team
        )
    ] == ["M2"]
    assert [
        m.code
        for m in service.list_team_matches(
            session, tournament_id=tournament.id, team_id=first.team_a_id
        )
    ] == ["M1"]
    assert (
        service.list_team_matches(
            session, tournament_id=tournament.id, team_id=uuid.uuid4()
        )
        == []
    )


def test_start_forfeit_clock_requires_both_teams(
    session: Session, fake_registration: FakeRegistration
) -> None:
    _tournament, bracket = draw_with(session, fake_registration, 3)
    final = service.lock_match(
        session, match_id=next(m.id for m in bracket.matches if m.code == "M2")
    )

    with pytest.raises(BusinessError) as excinfo:
        service.start_forfeit_clock(session, match=final)

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "MATCH_TEAMS_NOT_SET",
        409,
    )
    assert final.forfeit_deadline is None


def test_start_forfeit_clock_after_scheduled_time_counts_from_now(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    match = _first_match(session, fake_registration)
    # 預定 2026-10-26 11:00；兩隊在 12:20 才確定 → 期限 12:35
    frozen_clock.set(datetime(2026, 10, 26, 12, 20, tzinfo=UTC))

    service.start_forfeit_clock(session, match=match)

    assert service.get_match(session, match_id=match.id).forfeit_deadline == (
        datetime(2026, 10, 26, 12, 35, tzinfo=UTC)
    )
