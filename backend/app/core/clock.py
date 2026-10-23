"""後端唯一取得目前時間的地方（AD-13）。

程式一律呼叫 `clock.now()`，不要直接呼叫 `datetime.now()`。測試可以用
`freeze()` 把時鐘固定在某個時間點、用 `advance()` 推進，最後以 `reset()`
恢復真實時間（`tests/conftest.py` 的 `frozen_clock` fixture 已包好）。
"""

from datetime import UTC, datetime, timedelta

_frozen_at: datetime | None = None


def now() -> datetime:
    """回傳目前時間（帶 UTC 時區）。"""
    if _frozen_at is not None:
        return _frozen_at
    return datetime.now(UTC)


def freeze(at: datetime) -> None:
    """把時鐘固定在 `at`；`at` 必須帶時區，會轉成 UTC。"""
    global _frozen_at
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("clock.freeze() requires a timezone-aware datetime")
    _frozen_at = at.astimezone(UTC)


def advance(delta: timedelta) -> None:
    """把已凍結的時鐘往後推進 `delta`。"""
    global _frozen_at
    if _frozen_at is None:
        raise RuntimeError("clock.advance() requires a frozen clock")
    _frozen_at = _frozen_at + delta


def reset() -> None:
    """恢復使用真實時間。"""
    global _frozen_at
    _frozen_at = None
