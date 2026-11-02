from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.modules.competition.schedule import (
    RescheduleWindow,
    RoundStart,
    check_reschedule,
    forfeit_deadline,
    plan_round_starts,
    reschedule_window,
    round_min_gap,
)

START = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def t(h: int, m: int = 0) -> datetime:
    return datetime(2026, 11, 7, h, m, tzinfo=UTC)


def plan(**kw: Any) -> list[RoundStart]:
    args: dict[str, Any] = {
        "start_at": START,
        "rounds": 4,
        "interval_minutes": 120,
        "best_of": 1,
        "forfeit_minutes": 15,
        "game_minutes": 40,
        "appeal_minutes": 30,
    }
    args.update(kw)
    return plan_round_starts(**args)


def test_min_gap_example() -> None:
    assert (
        round_min_gap(forfeit_minutes=15, best_of=1, game_minutes=40, appeal_minutes=30)
        == 85
    )


def test_plan_sufficient_interval() -> None:
    result = plan()
    assert [r.round_no for r in result] == [1, 2, 3, 4]
    assert result[0].start_at == START
    for a, b in zip(result, result[1:], strict=False):
        assert b.start_at - a.start_at == timedelta(minutes=120)
    assert not any(r.is_delayed for r in result)
    assert all(r.delayed_by == 0 for r in result)
    assert result[0].required_gap == 0 and result[0].delayed_by == 0


def test_plan_delayed() -> None:
    result = plan(interval_minutes=90, best_of=3)
    for a, b in zip(result, result[1:], strict=False):
        assert b.start_at - a.start_at == timedelta(minutes=165)
    assert not result[0].is_delayed
    assert all(r.is_delayed and r.delayed_by == 75 for r in result[1:])
    assert result[1].required_gap == 165


def test_plan_per_round_best_of() -> None:
    result = plan(rounds=3, interval_minutes=90, best_of=[1, 1, 3])
    assert result[1].start_at - result[0].start_at == timedelta(minutes=90)
    assert result[2].start_at - result[1].start_at == timedelta(minutes=90)
    result = plan(rounds=4, interval_minutes=90, best_of=[1, 1, 3, 3])
    assert result[3].start_at - result[2].start_at == timedelta(minutes=165)
    assert result[3].delayed_by == 75 and not result[2].is_delayed


def test_plan_single_round() -> None:
    result = plan(rounds=1)
    assert len(result) == 1 and result[0].start_at == START


@pytest.mark.parametrize("rounds", range(1, 7))
@pytest.mark.parametrize("interval", [1, 60, 200])
@pytest.mark.parametrize("bo", [1, 3, 5])
def test_plan_invariants(rounds: int, interval: int, bo: int) -> None:
    result = plan(rounds=rounds, interval_minutes=interval, best_of=bo)
    assert len(result) == rounds
    gap = round_min_gap(
        forfeit_minutes=15, best_of=bo, game_minutes=40, appeal_minutes=30
    )
    for a, b in zip(result, result[1:], strict=False):
        assert b.start_at > a.start_at
        assert b.start_at - a.start_at >= timedelta(minutes=gap)
        assert b.required_gap == gap
        assert b.delayed_by == max(0, gap - interval)


def test_plan_invariants_per_round_best_of() -> None:
    bos = [1, 3, 5, 1, 3]
    result = plan(rounds=5, interval_minutes=100, best_of=bos)
    for i in range(1, 5):
        gap = round_min_gap(
            forfeit_minutes=15, best_of=bos[i - 1], game_minutes=40, appeal_minutes=30
        )
        assert result[i].required_gap == gap
        assert result[i].delayed_by == max(0, gap - 100)
        assert result[i].start_at - result[i - 1].start_at == timedelta(
            minutes=max(100, gap)
        )


def test_plan_dst_new_york() -> None:
    ny = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 7, 12, 0, tzinfo=ny)  # 隔天 3/8 切換夏令時間
    result = plan(start_at=start, rounds=3, interval_minutes=1440)
    for a, b in zip(result, result[1:], strict=False):
        assert b.start_at - a.start_at == timedelta(minutes=1440)
    assert result[1].start_at == datetime(2026, 3, 8, 17, 0, tzinfo=UTC)


def test_forfeit_deadline() -> None:
    assert forfeit_deadline(
        scheduled_at=t(13), both_known_at=t(13, 20), forfeit_minutes=15
    ) == t(13, 35)
    assert forfeit_deadline(
        scheduled_at=t(13), both_known_at=t(12), forfeit_minutes=15
    ) == t(13, 15)


KW: dict[str, Any] = {
    "now": t(10),
    "next_match_at": t(14),
    "own_min_gap": 85,
    "feeder_times": (),
    "feeder_min_gap": 0,
}


def test_reschedule_allowed_at_latest() -> None:
    assert check_reschedule(t(12, 35), **KW) is None


def test_reschedule_before_now() -> None:
    assert check_reschedule(t(9, 59), **KW) == "before_now"
    assert check_reschedule(t(10), **KW) is None


def test_reschedule_after_next() -> None:
    assert check_reschedule(t(12, 36), **KW) == "after_next_match"


def test_reschedule_before_feeder() -> None:
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": None,
        # 本場與前一輪的最小間隔不同（例如本場 BO5、前一輪 BO3），最早時間只看前一輪的
        "own_min_gap": 165,
        "feeder_times": [t(11), t(11, 30)],
        "feeder_min_gap": 85,
    }
    assert check_reschedule(t(12, 54), **kw) == "before_feeder"
    assert check_reschedule(t(12, 55), **kw) is None
    assert reschedule_window(**kw).earliest == t(12, 55)


def test_reschedule_window_single_instant() -> None:
    """最早剛好等於最晚：範圍只有一個時間點，不算空，而且那個時間點可以。"""
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": t(12),
        "own_min_gap": 120,
        "feeder_times": (),
        "feeder_min_gap": 0,
    }
    window = reschedule_window(**kw)
    assert window == RescheduleWindow(t(10), t(10)) and not window.is_empty
    assert check_reschedule(t(10), **kw) is None
    assert check_reschedule(t(10, 1), **kw) == "after_next_match"


def test_reschedule_empty_window() -> None:
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": t(11),
        "own_min_gap": 85,
        "feeder_times": (),
        "feeder_min_gap": 0,
    }
    assert reschedule_window(**kw).is_empty
    assert check_reschedule(t(10, 30), **kw) == "no_valid_time"
    assert check_reschedule(t(9), **kw) == "no_valid_time"


def test_reschedule_no_upper_bound() -> None:
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": None,
        "own_min_gap": 85,
        "feeder_times": (),
        "feeder_min_gap": 0,
    }
    window = reschedule_window(**kw)
    assert window == RescheduleWindow(t(10), None) and not window.is_empty
    assert check_reschedule(t(10) + timedelta(days=400), **kw) is None


def test_window_and_check_agree() -> None:
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": t(16),
        "own_min_gap": 85,
        "feeder_times": [t(11)],
        "feeder_min_gap": 85,
    }
    earliest, latest = reschedule_window(**kw)
    assert latest is not None
    for minute in range(0, 600, 5):
        cand = t(9) + timedelta(minutes=minute)
        inside = earliest <= cand <= latest
        assert (check_reschedule(cand, **kw) is None) == inside


def test_naive_datetime_rejected() -> None:
    naive = datetime(2026, 11, 7, 10, 0)
    with pytest.raises(ValueError):
        plan(start_at=naive)
    with pytest.raises(ValueError):
        forfeit_deadline(scheduled_at=naive, both_known_at=t(1), forfeit_minutes=1)
    with pytest.raises(ValueError):
        check_reschedule(naive, **KW)
    with pytest.raises(ValueError):
        reschedule_window(
            now=naive,
            next_match_at=None,
            own_min_gap=1,
            feeder_times=(),
            feeder_min_gap=0,
        )
    with pytest.raises(ValueError):
        reschedule_window(
            now=t(1),
            next_match_at=None,
            own_min_gap=1,
            feeder_times=[naive],
            feeder_min_gap=0,
        )


def test_non_utc_offsets_compare_by_instant() -> None:
    taipei = timezone(timedelta(hours=8))
    assert check_reschedule(datetime(2026, 11, 7, 20, 35, tzinfo=taipei), **KW) is None


@pytest.mark.parametrize(
    "kw",
    [
        {"rounds": 0},
        {"best_of": [1, 1]},
        {"best_of": 0},
        {"best_of": [1, 0, 1, 1]},
        {"interval_minutes": -5},
        {"interval_minutes": 0},
        {"forfeit_minutes": -1},
        {"game_minutes": -1},
        {"appeal_minutes": -1},
    ],
)
def test_plan_invalid_values(kw: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        plan(**kw)


def test_other_negative_minutes() -> None:
    with pytest.raises(ValueError):
        forfeit_deadline(scheduled_at=t(1), both_known_at=t(1), forfeit_minutes=-1)
    with pytest.raises(ValueError):
        reschedule_window(
            now=t(1),
            next_match_at=None,
            own_min_gap=-1,
            feeder_times=(),
            feeder_min_gap=0,
        )


def test_more_validation() -> None:
    naive = datetime(2026, 11, 7, 10, 0)
    with pytest.raises(ValueError):
        reschedule_window(
            now=t(1),
            next_match_at=None,
            own_min_gap=1,
            feeder_times=[t(1)],
            feeder_min_gap=-1,
        )
    with pytest.raises(ValueError):
        forfeit_deadline(scheduled_at=t(1), both_known_at=naive, forfeit_minutes=1)
    with pytest.raises(ValueError):
        reschedule_window(
            now=t(1),
            next_match_at=naive,
            own_min_gap=1,
            feeder_times=(),
            feeder_min_gap=0,
        )


def test_reason_precedence() -> None:
    kw: dict[str, Any] = {
        "now": t(10),
        "next_match_at": None,
        "own_min_gap": 85,
        "feeder_times": [t(11)],
        "feeder_min_gap": 85,
    }
    assert check_reschedule(t(9), **kw) == "before_now"
    # 範圍只因前一輪結束（12:25）晚於上限（11:35）而為空
    kw2: dict[str, Any] = {**kw, "next_match_at": t(13)}
    window = reschedule_window(**kw2)
    assert window.is_empty and window.earliest > t(10)
    assert check_reschedule(t(11), **kw2) == "no_valid_time"
