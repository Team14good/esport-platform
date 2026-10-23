from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core import clock
from tests.conftest import FrozenClock


def test_now_is_utc_aware_by_default() -> None:
    before = datetime.now(UTC)
    current = clock.now()
    after = datetime.now(UTC)

    assert current.tzinfo is UTC
    assert before <= current <= after


def test_frozen_clock_returns_set_time_in_utc(frozen_clock: FrozenClock) -> None:
    moment = datetime(2026, 11, 1, 8, 30, tzinfo=UTC)

    frozen_clock.set(moment)

    assert clock.now() == moment
    assert clock.now().tzinfo is UTC


def test_frozen_clock_converts_other_timezones_to_utc(
    frozen_clock: FrozenClock,
) -> None:
    taipei = timezone(timedelta(hours=8))

    frozen_clock.set(datetime(2026, 10, 18, 19, 0, tzinfo=taipei))

    assert clock.now() == datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_frozen_clock_advances_without_waiting(frozen_clock: FrozenClock) -> None:
    start = clock.now()

    frozen_clock.advance(timedelta(minutes=30))

    assert clock.now() - start == timedelta(minutes=30)


def test_freeze_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        clock.freeze(datetime(2026, 10, 18, 11, 0))
