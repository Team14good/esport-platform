"""Story 4.5：抽籤後退賽與一對一遞補的兩個 registration 函式（`retire_registration`、
`backfill_drawn_from_waitlist`）與預估用的 `has_backfill_candidate`。

前置狀態直接寫入報名列（沿用 3.5 的 `_preset`）。賽事為賽程已公布，所以候補順位一定是
截止後的規則：平均段位積分高者先、同分送出早者先，每校正取與已參賽合計不超過 2 隊。
"""

import secrets
import uuid

import pytest
from sqlmodel import Session, col, select

from app.core import audit
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.identity.models import School
from app.modules.registration import service
from app.modules.registration.models import Registration, RegistrationStatus
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.helpers import make_account
from tests.registration.test_first_come_submission import (
    _first_come,
    _preset,
    _tournament,
)
from tests.registration.test_submit_registration import _school

S = RegistrationStatus


def _published(
    session: Session,
    frozen_clock: FrozenClock,
    *,
    mode: TournamentMode = TournamentMode.CAMPUS,
) -> TournamentRead:
    tournament = _tournament(session, frozen_clock)
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.status = TournamentStatus.PUBLISHED
    row.mode = mode
    row.invite_token = (
        secrets.token_urlsafe(32) if mode == TournamentMode.CUSTOM else None
    )
    session.add(row)
    session.flush()
    return service._get_tournament(session, tournament.id)


def _team(
    session: Session,
    tournament: TournamentRead,
    school: School,
    status: RegistrationStatus,
    *,
    score: str = "30",
    minutes: int = 1,
) -> Registration:
    return _preset(
        session,
        tournament,
        school,
        status,
        submitted_at=_first_come(tournament, minutes),
        score=score,
    )


def _status(session: Session, registration: Registration) -> RegistrationStatus:
    session.refresh(registration)
    return RegistrationStatus(registration.status)


def _backfilled_events(session: Session) -> list[OutboxEvent]:
    return list(
        session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == "RegistrationBackfilled")
        )
    )


# ---------------------------------------------------------------- 一對一遞補


def test_backfill_takes_the_highest_ranked_waitlisted_team(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    x, y, z = _school(session), _school(session), _school(session)
    _team(session, tournament, x, S.DRAWN)
    w1 = _team(session, tournament, y, S.WAITLISTED, score="80")
    w2 = _team(session, tournament, z, S.WAITLISTED, score="90")

    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == w2.team_id
    assert _status(session, w2) == S.DRAWN
    assert w2.backfilled_at is not None
    assert _status(session, w1) == S.WAITLISTED
    changes = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "registration.status_changed"
    ]
    assert [(log.entity_id, log.actor_id, log.after) for log in changes] == [
        (w2.id, None, {"status": "drawn"})
    ]
    # 不是「遞補為正取」，所以不發 RegistrationBackfilled
    assert _backfilled_events(session) == []


def test_backfill_skips_a_school_that_is_at_the_limit(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    x, y = _school(session), _school(session)
    retiring = _team(session, tournament, x, S.DRAWN)
    _team(session, tournament, x, S.DRAWN)
    _team(session, tournament, x, S.DRAWN)
    w1 = _team(session, tournament, x, S.WAITLISTED, score="95")
    w2 = _team(session, tournament, y, S.WAITLISTED, score="70")

    service.retire_registration(
        session, team_id=retiring.team_id, actor_id=make_account(session).id
    )  # X 校剩 2 隊，仍在上限

    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == w2.team_id  # W1 同校已滿，略過
    assert _status(session, w1) == S.WAITLISTED


def test_backfill_gives_the_slot_to_a_schoolmate_after_the_retirement(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    x, y = _school(session), _school(session)
    retiring = _team(session, tournament, x, S.DRAWN)
    _team(session, tournament, x, S.DRAWN)
    w1 = _team(session, tournament, x, S.WAITLISTED, score="95")
    _team(session, tournament, y, S.WAITLISTED, score="70")
    # 退賽前 X 校已有 2 隊，W1 沒有順位；退賽後 X 校剩 1 隊
    service.retire_registration(
        session, team_id=retiring.team_id, actor_id=make_account(session).id
    )

    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == w1.team_id
    assert _status(session, w1) == S.DRAWN


def test_backfill_without_waitlist_returns_none_and_changes_nothing(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    _team(session, tournament, _school(session), S.DRAWN)
    logs = len(audit.list_for_tournament(session, tournament.id))

    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen is None
    assert len(audit.list_for_tournament(session, tournament.id)) == logs


def test_backfill_in_custom_mode_takes_earliest_submitted(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """自訂模式（Story 3.10）：最早送出的候補接手，不看積分、不受每校上限。"""
    tournament = _published(session, frozen_clock, mode=TournamentMode.CUSTOM)
    school = _school(session)
    leaving = _team(session, tournament, school, S.DRAWN)
    _team(session, tournament, school, S.DRAWN)
    _team(session, tournament, school, S.DRAWN)
    earliest = _team(session, tournament, school, S.WAITLISTED, score="10", minutes=2)
    later = _team(
        session, tournament, _school(session), S.WAITLISTED, score="90", minutes=3
    )

    assert service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=leaving.team_id
    )
    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == earliest.team_id
    assert _status(session, earliest) == S.DRAWN
    assert _status(session, later) == S.WAITLISTED


def test_backfill_ignores_the_tournament_capacity(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    # 正取（已參賽）本來就少於名額：一對一換位只遞補一隊，不會補滿空位
    assert tournament.capacity > 3
    for _ in range(2):
        _team(session, tournament, _school(session), S.DRAWN)
    first = _team(session, tournament, _school(session), S.WAITLISTED, score="90")
    second = _team(session, tournament, _school(session), S.WAITLISTED, score="80")

    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == first.team_id
    assert _status(session, second) == S.WAITLISTED


# ---------------------------------------------------------------- 預估


def test_has_backfill_candidate_counts_the_leaving_team_out(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    x = _school(session)
    leaving = _team(session, tournament, x, S.DRAWN)
    _team(session, tournament, x, S.DRAWN)
    waiting = _team(session, tournament, x, S.WAITLISTED, score="95")

    other = service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=waiting.team_id
    )
    after_leaving = service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=leaving.team_id
    )

    # 同校已有 2 隊已參賽，候補沒有順位；隊伍退賽後才有
    assert (other, after_leaving) == (False, True)
    assert _status(session, waiting) == S.WAITLISTED  # 預估不寫入


# ---------------------------------------------------------------- 退賽的報名


def test_retire_registration_moves_drawn_to_retired(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _published(session, frozen_clock)
    registration = _team(session, tournament, _school(session), S.DRAWN)
    actor = make_account(session).id

    result = service.retire_registration(
        session, team_id=registration.team_id, actor_id=actor
    )

    assert result.status == S.RETIRED
    assert _status(session, registration) == S.RETIRED
    change = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "registration.status_changed"
    ]
    assert [(log.actor_id, log.before, log.after) for log in change] == [
        (actor, {"status": "drawn"}, {"status": "retired"})
    ]


@pytest.mark.parametrize("status", [S.WAITLISTED, S.RETIRED, S.DISQUALIFIED])
def test_retire_registration_rejects_other_statuses(
    session: Session, frozen_clock: FrozenClock, status: RegistrationStatus
) -> None:
    tournament = _published(session, frozen_clock)
    registration = _team(session, tournament, _school(session), status)
    logs = len(audit.list_for_tournament(session, tournament.id))

    with pytest.raises(BusinessError) as raised:
        service.retire_registration(
            session, team_id=registration.team_id, actor_id=make_account(session).id
        )

    assert (raised.value.code, raised.value.status_code) == (
        "REGISTRATION_INVALID_TRANSITION",
        409,
    )
    assert _status(session, registration) == status
    assert len(audit.list_for_tournament(session, tournament.id)) == logs


def test_retire_registration_unknown_team_is_404(session: Session) -> None:
    with pytest.raises(BusinessError) as raised:
        service.retire_registration(
            session, team_id=uuid.uuid4(), actor_id=make_account(session).id
        )

    assert (raised.value.code, raised.value.status_code) == (
        "REGISTRATION_NOT_FOUND",
        404,
    )
