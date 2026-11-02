"""Story 5.1 報到時間規則的單元測試：I/O 矩陣、邊界、性質測試與 import 限制。"""

import ast
import random
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import get_args
from zoneinfo import ZoneInfo

import pytest

from app.modules.competition import checkin
from app.modules.competition.checkin import (
    CHECK_IN_LEAD,
    CheckInReason,
    check_check_in,
    check_in_opens_at,
    tournament_starts_at,
)

TAIPEI = timezone(timedelta(hours=8))
SCHEDULED = datetime(2026, 11, 1, 13, 0, tzinfo=TAIPEI)
DEADLINE = datetime(2026, 11, 1, 13, 15, tzinfo=TAIPEI)


def at(hour: int, minute: int) -> datetime:
    """2026-11-01 台北時間的某個時刻。"""
    return datetime(2026, 11, 1, hour, minute, tzinfo=TAIPEI)


def ready(now: datetime) -> CheckInReason | None:
    """兩隊確定、本隊未報到時的判斷結果。"""
    return check_check_in(
        now=now,
        scheduled_at=SCHEDULED,
        teams_known=True,
        already_checked_in=False,
        forfeit_deadline=DEADLINE,
    )


# --- I/O 矩陣 ---


def test_lead_is_thirty_minutes() -> None:
    assert CHECK_IN_LEAD == timedelta(minutes=30)


def test_reason_codes_are_exactly_the_four_in_spec() -> None:
    assert set(get_args(CheckInReason.__value__)) == {
        "teams_pending",
        "already_checked_in",
        "too_early",
        "closed",
    }


def test_opens_thirty_minutes_before_schedule() -> None:
    opens = check_in_opens_at(SCHEDULED)

    assert opens == at(12, 30)
    assert opens.tzinfo is UTC


def test_allowed_exactly_at_open_time() -> None:
    assert ready(at(12, 30)) is None


def test_too_early_one_minute_before_open() -> None:
    assert ready(at(12, 29)) == "too_early"


def test_too_early_one_microsecond_before_open() -> None:
    assert ready(at(12, 30) - timedelta(microseconds=1)) == "too_early"


def test_teams_pending_wins_over_every_other_reason() -> None:
    assert (
        check_check_in(
            now=at(12, 45),
            scheduled_at=SCHEDULED,
            teams_known=False,
            already_checked_in=False,
            forfeit_deadline=None,
        )
        == "teams_pending"
    )
    # 同時也已報到、也已過期限，仍以兩隊未確定為先
    assert (
        check_check_in(
            now=at(14, 0),
            scheduled_at=SCHEDULED,
            teams_known=False,
            already_checked_in=True,
            forfeit_deadline=DEADLINE,
        )
        == "teams_pending"
    )


def test_already_checked_in() -> None:
    assert (
        check_check_in(
            now=at(12, 45),
            scheduled_at=SCHEDULED,
            teams_known=True,
            already_checked_in=True,
            forfeit_deadline=DEADLINE,
        )
        == "already_checked_in"
    )


def test_already_checked_in_wins_over_too_early_and_closed() -> None:
    for now in (at(12, 0), at(14, 0)):
        assert (
            check_check_in(
                now=now,
                scheduled_at=SCHEDULED,
                teams_known=True,
                already_checked_in=True,
                forfeit_deadline=DEADLINE,
            )
            == "already_checked_in"
        )


def test_allowed_after_scheduled_time_before_deadline() -> None:
    assert ready(at(13, 10)) is None


def test_allowed_one_microsecond_before_deadline() -> None:
    assert ready(DEADLINE - timedelta(microseconds=1)) is None


def test_closed_exactly_at_deadline() -> None:
    assert ready(at(13, 15)) == "closed"


def test_closed_after_deadline() -> None:
    assert ready(at(13, 16)) == "closed"


def test_tournament_starts_thirty_minutes_before_earliest_match() -> None:
    starts = tournament_starts_at([at(13, 0), at(10, 0), at(11, 0)])

    assert starts == at(9, 30)
    assert starts.tzinfo is UTC


def test_tournament_starts_accepts_any_iterable() -> None:
    assert tournament_starts_at(t for t in [at(11, 0), at(10, 0)]) == at(9, 30)


def test_tournament_starts_compares_in_utc_across_timezones() -> None:
    # 台北 10:00 = UTC 02:00，比 UTC 03:00 早
    earliest = at(10, 0)
    later_utc = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)

    assert tournament_starts_at([later_utc, earliest]) == at(9, 30)


def test_tournament_starts_without_matches_raises() -> None:
    with pytest.raises(ValueError, match="沒有場次"):
        tournament_starts_at([])


# --- 沒有時區 ---

NAIVE = datetime(2026, 11, 1, 13, 0)


def test_opens_at_rejects_naive() -> None:
    with pytest.raises(ValueError, match="scheduled_at 必須帶時區"):
        check_in_opens_at(NAIVE)


@pytest.mark.parametrize("teams_known", [True, False])
@pytest.mark.parametrize("field", ["now", "scheduled_at", "forfeit_deadline"])
def test_check_rejects_naive_datetime(field: str, teams_known: bool) -> None:
    # 兩隊未確定時期限為 None，只有測 naive 期限時才傳入
    deadline = DEADLINE if teams_known or field == "forfeit_deadline" else None
    kwargs: dict[str, datetime | None] = {
        "now": at(12, 45),
        "scheduled_at": SCHEDULED,
        "forfeit_deadline": deadline,
    }
    kwargs[field] = NAIVE

    with pytest.raises(ValueError, match=f"{field} 必須帶時區"):
        check_check_in(
            now=kwargs["now"],  # type: ignore[arg-type]
            scheduled_at=kwargs["scheduled_at"],  # type: ignore[arg-type]
            teams_known=teams_known,
            already_checked_in=False,
            forfeit_deadline=kwargs["forfeit_deadline"],
        )


def test_tournament_starts_rejects_naive_among_aware() -> None:
    with pytest.raises(ValueError, match="scheduled_times 必須帶時區"):
        tournament_starts_at([at(10, 0), NAIVE])


class _NoOffset(tzinfo):
    """tzinfo 存在但 utcoffset() 回傳 None：等同沒有時區。"""

    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


def test_tzinfo_without_offset_counts_as_naive() -> None:
    with pytest.raises(ValueError, match="scheduled_at 必須帶時區"):
        check_in_opens_at(datetime(2026, 11, 1, 13, 0, tzinfo=_NoOffset()))


def test_teams_known_without_deadline_raises() -> None:
    with pytest.raises(ValueError, match="必須提供 forfeit_deadline"):
        check_check_in(
            now=at(12, 45),
            scheduled_at=SCHEDULED,
            teams_known=True,
            already_checked_in=False,
            forfeit_deadline=None,
        )


@pytest.mark.parametrize(
    "deadline", [at(12, 30), at(12, 0), datetime(2026, 11, 1, 4, 30, tzinfo=UTC)]
)
def test_deadline_not_after_open_time_raises(deadline: datetime) -> None:
    # 期限等於或早於開放時間，報到窗口永遠不會打開；最後一例是 UTC 表示的 12:30 台北
    with pytest.raises(ValueError, match="必須晚於報到開放時間"):
        check_check_in(
            now=at(14, 0),
            scheduled_at=SCHEDULED,
            teams_known=True,
            already_checked_in=False,
            forfeit_deadline=deadline,
        )


def test_deadline_one_microsecond_after_open_time_is_valid() -> None:
    assert (
        check_check_in(
            now=at(12, 30),
            scheduled_at=SCHEDULED,
            teams_known=True,
            already_checked_in=False,
            forfeit_deadline=at(12, 30) + timedelta(microseconds=1),
        )
        is None
    )


# --- 時區與日光節約 ---


def test_comparison_is_done_in_utc_across_timezones() -> None:
    # now 用 UTC 表示 12:30 台北，正好是開放時間
    now_utc = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)

    assert ready(now_utc) is None
    assert ready(now_utc - timedelta(seconds=1)) == "too_early"


def test_lead_across_dst_spring_forward_new_york() -> None:
    # 2026-03-08 02:00 EST 時鐘跳到 03:00 EDT；03:15 EDT = 07:15 UTC
    new_york = ZoneInfo("America/New_York")
    scheduled = datetime(2026, 3, 8, 3, 15, tzinfo=new_york)

    opens = check_in_opens_at(scheduled)

    # 實際經過 30 分鐘是 06:45 UTC（01:45 EST），不是牆上時間 02:45
    assert opens == datetime(2026, 3, 8, 6, 45, tzinfo=UTC)
    assert scheduled.astimezone(UTC) - opens == timedelta(minutes=30)

    deadline = datetime(2026, 3, 8, 3, 30, tzinfo=new_york)
    just_open = datetime(2026, 3, 8, 1, 45, tzinfo=new_york)
    before = datetime(2026, 3, 8, 1, 44, tzinfo=new_york)

    def result(now: datetime) -> CheckInReason | None:
        return check_check_in(
            now=now,
            scheduled_at=scheduled,
            teams_known=True,
            already_checked_in=False,
            forfeit_deadline=deadline,
        )

    assert result(just_open) is None
    assert result(before) == "too_early"


@pytest.mark.parametrize(("fold", "utc_hour"), [(0, 5), (1, 6)])
def test_lead_across_dst_fall_back_new_york(fold: int, utc_hour: int) -> None:
    # 2026-11-01 02:00 EDT 時鐘退回 01:00 EST；01:15 出現兩次
    # fold=0 是 01:15 EDT = 05:15 UTC，fold=1 是 01:15 EST = 06:15 UTC
    scheduled = datetime(
        2026, 11, 1, 1, 15, tzinfo=ZoneInfo("America/New_York"), fold=fold
    )
    assert scheduled.astimezone(UTC) == datetime(2026, 11, 1, utc_hour, 15, tzinfo=UTC)

    opens = check_in_opens_at(scheduled)

    assert opens == datetime(2026, 11, 1, utc_hour - 1, 45, tzinfo=UTC)
    assert scheduled.astimezone(UTC) - opens == timedelta(minutes=30)


# --- 性質測試：兩條 Acceptance Criteria ---


def test_acceptance_criteria_hold_for_random_inputs() -> None:
    rng = random.Random(20261029)
    zones = [UTC, TAIPEI, ZoneInfo("America/New_York"), ZoneInfo("Europe/London")]
    base = datetime(2026, 3, 1, tzinfo=UTC)
    seen: set[CheckInReason | None] = set()

    for _ in range(5000):
        scheduled = (base + timedelta(minutes=rng.randint(0, 60 * 24 * 60))).astimezone(
            rng.choice(zones)
        )
        # 期限必須晚於開放時間（更早的期限會拋 ValueError，另有測試）
        deadline = (scheduled + timedelta(minutes=rng.randint(-29, 120))).astimezone(
            rng.choice(zones)
        )
        now = (scheduled + timedelta(minutes=rng.randint(-90, 150))).astimezone(
            rng.choice(zones)
        )
        teams_known = rng.random() < 0.7
        checked_in = rng.random() < 0.3
        given_deadline = deadline if teams_known or rng.random() < 0.5 else None

        reason = check_check_in(
            now=now,
            scheduled_at=scheduled,
            teams_known=teams_known,
            already_checked_in=checked_in,
            forfeit_deadline=given_deadline,
        )

        # 依 spec 的順序算出確切的原因：AC2（teams_pending 優先）與
        # AC1（None 若且唯若 兩隊確定、未報到、開放時間 <= 現在 < 期限）
        opens_utc = scheduled.astimezone(UTC) - timedelta(minutes=30)
        now_utc = now.astimezone(UTC)
        expected: CheckInReason | None
        if not teams_known:
            expected = "teams_pending"
        elif checked_in:
            expected = "already_checked_in"
        elif now_utc < opens_utc:
            expected = "too_early"
        elif now_utc >= deadline.astimezone(UTC):
            expected = "closed"
        else:
            expected = None
        assert reason == expected
        seen.add(reason)

    # 確認抽樣涵蓋允許與每一種原因
    assert seen == {None, *get_args(CheckInReason.__value__)}


# --- import 限制 ---

ALLOWED_IMPORTS = {"collections.abc", "datetime", "typing"}


def test_module_imports_only_allowed_stdlib() -> None:
    tree = ast.parse(Path(checkin.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "不允許相對 import"
            imported.add(node.module or "")

    assert imported, "AST 檢查沒有找到任何 import，檢查本身可能失效"
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS


def test_module_never_reads_the_clock() -> None:
    tree = ast.parse(Path(checkin.__file__).read_text(encoding="utf-8"))
    # 參數名稱 `now` 可以用，但不能呼叫 now()／utcnow()／today()
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute | ast.Name)
    }

    assert "astimezone" in called, "AST 檢查沒有看到已知的呼叫，檢查本身可能失效"
    assert not called & {"now", "utcnow", "today"}
