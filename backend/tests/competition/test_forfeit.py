"""Story 5.2 逾時判棄權規則的單元測試：I/O 矩陣、邊界、性質測試與 import 限制。"""

import ast
import random
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.modules.competition import forfeit
from app.modules.competition.forfeit import (
    ForfeitVerdict,
    appeal_deadline,
    judge_forfeit,
)
from app.modules.competition.models import MatchOutcome, MatchStatus

TAIPEI = timezone(timedelta(hours=8))
DEADLINE = datetime(2026, 11, 1, 13, 15, tzinfo=TAIPEI)


def at(hour: int, minute: int, second: int = 0) -> datetime:
    """2026-11-01 台北時間的某個時刻。"""
    return datetime(2026, 11, 1, hour, minute, second, tzinfo=TAIPEI)


def judge(
    *,
    now: datetime = at(13, 16),
    checked_in: Iterable[str] = (),
    tournament_cancelled: bool = False,
    status: MatchStatus = MatchStatus.SCHEDULED,
    team_a: str | None = "a",
    team_b: str | None = "b",
    forfeit_deadline: datetime | None = DEADLINE,
) -> ForfeitVerdict[str] | None:
    """預設為兩隊確定、待開打、期限 13:15、現在 13:16 的場次。"""
    return judge_forfeit(
        now=now,
        tournament_cancelled=tournament_cancelled,
        status=status,
        team_a=team_a,
        team_b=team_b,
        forfeit_deadline=forfeit_deadline,
        checked_in=checked_in,
    )


# --- I/O 矩陣 ---


def test_one_team_checked_in_other_forfeits() -> None:
    assert judge(checked_in={"a"}) == ForfeitVerdict(MatchOutcome.FORFEIT, "a", ("b",))


def test_no_team_checked_in_is_double_forfeit() -> None:
    assert judge(checked_in=()) == ForfeitVerdict(
        MatchOutcome.DOUBLE_FORFEIT, None, ("a", "b")
    )


def test_exactly_at_deadline_forfeits() -> None:
    assert judge(now=at(13, 15), checked_in={"b"}) == ForfeitVerdict(
        MatchOutcome.FORFEIT, "b", ("a",)
    )


def test_before_deadline_is_none() -> None:
    assert judge(now=at(13, 14), checked_in={"b"}) is None
    assert judge(now=at(13, 14)) is None


@pytest.mark.parametrize(
    ("offset", "expected_none"),
    [
        (timedelta(seconds=-1), True),
        (timedelta(0), False),
        (timedelta(seconds=1), False),
    ],
)
def test_one_second_around_deadline(offset: timedelta, expected_none: bool) -> None:
    verdict = judge(now=DEADLINE + offset, checked_in={"a"})

    assert (verdict is None) is expected_none


def test_both_checked_in_is_none() -> None:
    assert judge(checked_in={"a", "b"}) is None


def test_teams_pending_is_none() -> None:
    # 兩隊未確定時沒有期限；即使已過「預定＋時限」也不判
    assert judge(team_b=None, forfeit_deadline=None, now=at(18, 0)) is None
    assert judge(team_a=None, forfeit_deadline=None, now=at(18, 0)) is None
    assert judge(team_a=None, team_b=None, forfeit_deadline=None) is None


def test_teams_pending_with_checked_in_known_team_is_none() -> None:
    assert judge(team_b=None, forfeit_deadline=None, checked_in={"a"}) is None


def test_teams_pending_with_stale_deadline_is_none() -> None:
    assert judge(team_b=None, forfeit_deadline=DEADLINE) is None


def test_cancelled_tournament_is_none_before_everything() -> None:
    assert judge(tournament_cancelled=True, checked_in={"a"}) is None
    assert judge(tournament_cancelled=True) is None


@pytest.mark.parametrize(
    "status", [s for s in MatchStatus if s is not MatchStatus.SCHEDULED]
)
def test_not_scheduled_is_none(status: MatchStatus) -> None:
    assert judge(status=status, checked_in={"a"}) is None
    assert judge(status=status) is None


def test_missing_deadline_with_known_teams_raises() -> None:
    with pytest.raises(ValueError, match="forfeit_deadline"):
        judge(forfeit_deadline=None)
    # 呼叫端錯誤不因賽事已取消而被略過
    with pytest.raises(ValueError, match="forfeit_deadline"):
        judge(forfeit_deadline=None, tournament_cancelled=True)


def test_outsider_in_checked_in_raises() -> None:
    with pytest.raises(ValueError, match="checked_in"):
        judge(checked_in={"a", "c"})
    with pytest.raises(ValueError, match="checked_in"):
        judge(team_b=None, forfeit_deadline=None, checked_in={"b"})


def test_same_team_raises() -> None:
    with pytest.raises(ValueError, match="同一隊"):
        judge(team_a="a", team_b="a")


def test_appeal_deadline_adds_minutes_from_decision_time() -> None:
    result = appeal_deadline(decided_at=at(13, 16), appeal_minutes=60)

    assert result == datetime(2026, 11, 1, 6, 16, tzinfo=UTC)
    assert result == at(14, 16)
    assert result.tzinfo is UTC


@pytest.mark.parametrize("minutes", [0, -1, -60, 1.5, 60.0, "60", None, True, False])
def test_appeal_deadline_rejects_invalid_minutes(minutes: Any) -> None:
    with pytest.raises(ValueError, match="appeal_minutes"):
        appeal_deadline(decided_at=at(13, 16), appeal_minutes=minutes)


def test_naive_datetimes_raise() -> None:
    naive = datetime(2026, 11, 1, 13, 16)
    with pytest.raises(ValueError, match="now"):
        judge(now=naive)
    with pytest.raises(ValueError, match="forfeit_deadline"):
        judge(forfeit_deadline=datetime(2026, 11, 1, 13, 15))
    with pytest.raises(ValueError, match="decided_at"):
        appeal_deadline(decided_at=naive, appeal_minutes=60)


def test_deadline_compares_across_time_zones() -> None:
    # 13:15 台北 = 05:15 UTC；以 UTC 傳入的「現在」剛好等於期限
    now_utc = datetime(2026, 11, 1, 5, 15, tzinfo=UTC)
    assert judge(now=now_utc, checked_in={"a"}) is not None
    assert judge(now=now_utc - timedelta(microseconds=1), checked_in={"a"}) is None


def test_appeal_deadline_across_dst_is_absolute_minutes() -> None:
    # 2026-03-08 02:00 EST 跳到 03:00 EDT；01:30 EST + 60 分鐘 = 07:30 UTC
    decided = datetime(2026, 3, 8, 1, 30, tzinfo=ZoneInfo("America/New_York"))

    assert appeal_deadline(decided_at=decided, appeal_minutes=60) == datetime(
        2026, 3, 8, 7, 30, tzinfo=UTC
    )


def test_works_with_uuid_and_generator_checked_in() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    verdict = judge_forfeit(
        now=at(13, 16),
        tournament_cancelled=False,
        status=MatchStatus.SCHEDULED,
        team_a=a,
        team_b=b,
        forfeit_deadline=DEADLINE,
        checked_in=(team for team in [b]),
    )

    assert verdict == ForfeitVerdict(MatchOutcome.FORFEIT, b, (a,))


def test_verdict_is_frozen() -> None:
    verdict = judge(checked_in={"a"})
    assert verdict is not None

    with pytest.raises(AttributeError):
        verdict.winner = "b"  # type: ignore[misc]


# --- 性質測試：三條 Acceptance Criteria ---


def test_acceptance_criteria_hold_for_random_inputs() -> None:
    rng = random.Random(20261030)
    zones = [UTC, TAIPEI, ZoneInfo("America/New_York"), ZoneInfo("Europe/London")]
    base = datetime(2026, 3, 1, tzinfo=UTC)
    seen: set[MatchOutcome | None] = set()
    statuses = list(MatchStatus)

    for _ in range(5000):
        deadline = (base + timedelta(minutes=rng.randint(0, 60 * 24 * 60))).astimezone(
            rng.choice(zones)
        )
        now = (deadline + timedelta(seconds=rng.randint(-120, 120))).astimezone(
            rng.choice(zones)
        )
        cancelled = rng.random() < 0.15
        status = MatchStatus.SCHEDULED if rng.random() < 0.7 else rng.choice(statuses)
        team_a = "a" if rng.random() < 0.85 else None
        team_b = "b" if rng.random() < 0.85 else None
        known = [t for t in (team_a, team_b) if t is not None]
        checked = {t for t in known if rng.random() < 0.5}
        given_deadline = (
            deadline
            if (team_a is not None and team_b is not None) or rng.random() < 0.5
            else None
        )

        kwargs: dict[str, Any] = {
            "now": now,
            "tournament_cancelled": cancelled,
            "status": status,
            "team_a": team_a,
            "team_b": team_b,
            "forfeit_deadline": given_deadline,
            "checked_in": checked,
        }
        verdict = judge_forfeit(**kwargs)

        # 依 spec 的順序算出預期結果（AC1）
        expected: ForfeitVerdict[str] | None
        if (
            cancelled
            or status != MatchStatus.SCHEDULED
            or team_a is None
            or team_b is None
            or now.astimezone(UTC) < deadline.astimezone(UTC)
            or checked == {team_a, team_b}
        ):
            expected = None
        elif checked == {team_a}:
            expected = ForfeitVerdict(MatchOutcome.FORFEIT, team_a, (team_b,))
        elif checked == {team_b}:
            expected = ForfeitVerdict(MatchOutcome.FORFEIT, team_b, (team_a,))
        else:
            expected = ForfeitVerdict(
                MatchOutcome.DOUBLE_FORFEIT, None, (team_a, team_b)
            )
        assert verdict == expected

        # AC2：forfeit 的勝隊必定已報到，forfeited 只含另一隊
        if verdict is not None and verdict.outcome is MatchOutcome.FORFEIT:
            assert verdict.winner in checked
            assert len(verdict.forfeited) == 1
            assert verdict.forfeited[0] not in checked
            assert {verdict.winner, *verdict.forfeited} == {team_a, team_b}

        # AC3：同一組輸入重複呼叫結果相同
        assert judge_forfeit(**kwargs) == verdict
        seen.add(None if verdict is None else verdict.outcome)

    # 確認抽樣涵蓋不判、一方棄權與雙方棄權
    assert seen == {None, MatchOutcome.FORFEIT, MatchOutcome.DOUBLE_FORFEIT}


# --- import 限制 ---

ALLOWED_IMPORTS = {
    "collections.abc",
    "dataclasses",
    "datetime",
    "app.modules.competition.models",
}


def _tree() -> ast.Module:
    return ast.parse(Path(forfeit.__file__).read_text(encoding="utf-8"))


def test_module_imports_only_allowed_modules() -> None:
    imported: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "不允許相對 import"
            imported.add(node.module or "")

    assert imported, "AST 檢查沒有找到任何 import，檢查本身可能失效"
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS


def test_module_never_reads_the_clock() -> None:
    # 參數名稱 `now` 可以用，但不能呼叫 now()／utcnow()／today()
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute | ast.Name)
    }

    assert "astimezone" in called, "AST 檢查沒有看到已知的呼叫，檢查本身可能失效"
    assert not called & {"now", "utcnow", "today"}
