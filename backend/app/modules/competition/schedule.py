"""場次時間規則（Story 4.3 第一階段）。

全部是不碰資料庫、不讀時鐘的純函式；「現在」由呼叫端傳入。
所有 datetime 必須帶時區，內部一律先轉 UTC 再加減，回傳 UTC。
分鐘數一律為整數。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, NamedTuple

RescheduleReason = Literal[
    "no_valid_time", "before_now", "before_feeder", "after_next_match"
]


@dataclass(frozen=True)
class RoundStart:
    """某一輪的開始時間。

    required_gap 為規則要求的最小間隔（上一輪的最小間隔，分鐘），delayed_by 為
    因最小間隔大於每輪間隔而多順延的分鐘數；第 1 輪兩者皆為 0。
    """

    round_no: int
    start_at: datetime
    required_gap: int
    delayed_by: int

    @property
    def is_delayed(self) -> bool:
        return self.delayed_by > 0


class RescheduleWindow(NamedTuple):
    """修改時間的允許範圍。latest 為 None 表示沒有上限。"""

    earliest: datetime
    latest: datetime | None

    @property
    def is_empty(self) -> bool:
        return self.latest is not None and self.earliest > self.latest


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime 必須帶時區")
    return value.astimezone(UTC)


def _check_minutes(**values: int) -> None:
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} 不可為負數")


def round_min_gap(
    *, forfeit_minutes: int, best_of: int, game_minutes: int, appeal_minutes: int
) -> int:
    """某輪的最小間隔＝棄權時限＋BO × 每局預估時間＋申訴期（分鐘）。"""
    _check_minutes(
        forfeit_minutes=forfeit_minutes,
        game_minutes=game_minutes,
        appeal_minutes=appeal_minutes,
    )
    if best_of < 1:
        raise ValueError("best_of 必須至少為 1")
    return forfeit_minutes + best_of * game_minutes + appeal_minutes


def plan_round_starts(
    *,
    start_at: datetime,
    rounds: int,
    interval_minutes: int,
    best_of: int | Sequence[int],
    forfeit_minutes: int,
    game_minutes: int,
    appeal_minutes: int,
) -> list[RoundStart]:
    """計算各輪開始時間。

    第 1 輪＝start_at；第 r+1 輪＝第 r 輪開始＋max(每輪間隔, 第 r 輪最小間隔)。
    best_of 可為單一整數或依輪傳入的序列。同輪所有場次（含季軍賽與決賽）
    共用該輪的開始時間，不自動分批。回傳的時間皆為 UTC，顯示時由呼叫端轉換。
    """
    if rounds < 1:
        raise ValueError("rounds 必須至少為 1")
    if interval_minutes < 1:
        raise ValueError("每輪間隔必須至少 1 分鐘")
    if isinstance(best_of, int):
        bo_list = [best_of] * rounds
    else:
        bo_list = list(best_of)
        if len(bo_list) != rounds:
            raise ValueError("best_of 的數量必須等於輪數")
    gaps = [
        round_min_gap(
            forfeit_minutes=forfeit_minutes,
            best_of=bo,
            game_minutes=game_minutes,
            appeal_minutes=appeal_minutes,
        )
        for bo in bo_list
    ]
    current = _utc(start_at)
    result = [RoundStart(1, current, 0, 0)]
    for r in range(2, rounds + 1):
        min_gap = gaps[r - 2]
        current = current + timedelta(minutes=max(interval_minutes, min_gap))
        result.append(
            RoundStart(r, current, min_gap, max(0, min_gap - interval_minutes))
        )
    return result


def forfeit_deadline(
    *, scheduled_at: datetime, both_known_at: datetime, forfeit_minutes: int
) -> datetime:
    """棄權期限＝max(預定開始時間, 兩隊確定的時間)＋棄權時限。

    只在兩隊都確定後才呼叫；兩隊未確定的場次不設棄權期限。
    """
    _check_minutes(forfeit_minutes=forfeit_minutes)
    base = max(_utc(scheduled_at), _utc(both_known_at))
    return base + timedelta(minutes=forfeit_minutes)


def reschedule_window(
    *,
    now: datetime,
    next_match_at: datetime | None,
    own_min_gap: int,
    feeder_times: Sequence[datetime],
    feeder_min_gap: int,
) -> RescheduleWindow:
    """修改時間的允許範圍（含邊界）。

    最早＝max(現在, 前一輪場次最晚的預定時間＋該輪最小間隔)；第一輪沒有
    前一輪（feeder_times 為空）。最晚＝下一場預定時間－本場最小間隔；
    決賽與季軍賽 next_match_at 為 None，沒有上限。
    """
    _check_minutes(own_min_gap=own_min_gap, feeder_min_gap=feeder_min_gap)
    earliest = _utc(now)
    if feeder_times:
        feeder_end = max(_utc(t) for t in feeder_times) + timedelta(
            minutes=feeder_min_gap
        )
        earliest = max(earliest, feeder_end)
    latest = (
        None
        if next_match_at is None
        else _utc(next_match_at) - timedelta(minutes=own_min_gap)
    )
    return RescheduleWindow(earliest, latest)


def check_reschedule(
    new_at: datetime,
    *,
    now: datetime,
    next_match_at: datetime | None,
    own_min_gap: int,
    feeder_times: Sequence[datetime],
    feeder_min_gap: int,
) -> RescheduleReason | None:
    """檢查新時間；允許回傳 None，否則回傳原因代碼。

    代碼：no_valid_time、before_now、before_feeder、after_next_match。
    """
    new = _utc(new_at)
    window = reschedule_window(
        now=now,
        next_match_at=next_match_at,
        own_min_gap=own_min_gap,
        feeder_times=feeder_times,
        feeder_min_gap=feeder_min_gap,
    )
    if window.is_empty:
        return "no_valid_time"
    if new < _utc(now):
        return "before_now"
    if new < window.earliest:
        return "before_feeder"
    if window.latest is not None and new > window.latest:
        return "after_next_match"
    return None
