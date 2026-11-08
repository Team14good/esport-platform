"""Story 6.1：competition 的 `mark_appealed`（B 新增，D 審查）。

申訴期 → 申訴中；已是申訴中不動；其他狀態 409 `MATCH_INVALID_TRANSITION`、不改資料；
不改 `appeal_deadline`。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.competition import service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from tests.competition.conftest import FakeRegistration, draw_with
from tests.conftest import FrozenClock

pytestmark = pytest.mark.usefixtures("frozen_clock")

DEADLINE = datetime(2026, 10, 18, 11, 30, tzinfo=UTC)


def _final(session: Session, fake: FakeRegistration, status: MatchStatus) -> Match:
    _tournament, bracket = draw_with(session, fake, 2)
    final = session.get(Match, bracket.matches[0].id)
    assert final is not None
    final.status = status
    if status in (MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED):
        final.outcome = MatchOutcome.PLAYED
        final.winner_id = fake.teams[0]
        final.appeal_deadline = DEADLINE
    session.add(final)
    session.flush()
    return final


def test_appeal_window_becomes_appealed_keeping_deadline(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClock,
) -> None:
    final = _final(session, fake_registration, MatchStatus.APPEAL_WINDOW)
    frozen_clock.advance(timedelta(minutes=5))

    read = service.mark_appealed(session, match_id=final.id)

    assert read.status == MatchStatus.APPEALED
    assert read.appeal_deadline == DEADLINE
    assert read.outcome == MatchOutcome.PLAYED
    session.refresh(final)
    assert final.status == MatchStatus.APPEALED
    assert final.appeal_deadline == DEADLINE
    # 狀態改變會更新 updated_at，S4 據此重抓申訴狀態
    assert final.updated_at == frozen_clock.now()


def test_already_appealed_is_unchanged(
    session: Session, fake_registration: FakeRegistration, frozen_clock: FrozenClock
) -> None:
    final = _final(session, fake_registration, MatchStatus.APPEALED)
    before = final.updated_at
    frozen_clock.advance(timedelta(minutes=5))

    read = service.mark_appealed(session, match_id=final.id)

    assert read.status == MatchStatus.APPEALED
    assert read.appeal_deadline == DEADLINE
    session.refresh(final)
    assert final.updated_at == before


@pytest.mark.parametrize(
    "status",
    [
        MatchStatus.SCHEDULED,
        MatchStatus.LIVE,
        MatchStatus.CONFIRMED,
        MatchStatus.VOIDED,
    ],
)
def test_other_statuses_are_rejected(
    session: Session, fake_registration: FakeRegistration, status: MatchStatus
) -> None:
    final = _final(session, fake_registration, status)

    with pytest.raises(BusinessError) as caught:
        service.mark_appealed(session, match_id=final.id)

    assert caught.value.code == "MATCH_INVALID_TRANSITION"
    assert caught.value.status_code == 409
    session.refresh(final)
    assert final.status == status


def test_missing_match_is_not_found(session: Session) -> None:
    with pytest.raises(BusinessError) as caught:
        service.mark_appealed(session, match_id=uuid.uuid4())

    assert caught.value.code == "MATCH_NOT_FOUND"


def test_worker_does_not_confirm_appealed_match(
    session: Session, fake_registration: FakeRegistration, frozen_clock: FrozenClock
) -> None:
    final = _final(session, fake_registration, MatchStatus.APPEAL_WINDOW)
    service.mark_appealed(session, match_id=final.id)
    frozen_clock.set(DEADLINE + timedelta(minutes=1))

    assert service.auto_confirm_expired(session) is False
    session.refresh(final)
    assert final.status == MatchStatus.APPEALED
