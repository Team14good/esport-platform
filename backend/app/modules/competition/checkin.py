"""隊長報到的時間規則（Story 5.1）：不碰資料庫、不讀時鐘的純函式。

第二階段的 `check_in()`、S4 Check-in panel 與 worker 的 `start_tournament`
都用這裡的規則，確保三處判斷一致。「現在」一律由呼叫端傳入。
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal

CHECK_IN_LEAD = timedelta(minutes=30)
"""報到在預定開始時間前多久開放。"""

type CheckInReason = Literal[
    "teams_pending", "already_checked_in", "too_early", "closed"
]
"""不能報到的原因代碼；`teams_pending` 對應 API 代碼 `MATCH_TEAMS_PENDING`。"""


def _to_utc(value: datetime, name: str) -> datetime:
    """確認 datetime 帶時區並轉成 UTC；沒有時區拋 ValueError。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必須帶時區")
    return value.astimezone(UTC)


def check_in_opens_at(scheduled_at: datetime) -> datetime:
    """回傳報到開放時間（UTC）＝預定開始時間－30 分鐘。"""
    return _to_utc(scheduled_at, "scheduled_at") - CHECK_IN_LEAD


def check_check_in(
    *,
    now: datetime,
    scheduled_at: datetime,
    teams_known: bool,
    already_checked_in: bool,
    forfeit_deadline: datetime | None,
) -> CheckInReason | None:
    """判斷現在能不能報到；可以回傳 None，不行回傳原因代碼。

    檢查順序：兩隊未確定、本隊已報到、太早、已過棄權期限。
    `forfeit_deadline` 在兩隊未確定時為 None；兩隊已確定卻沒給，
    或期限不晚於開放時間（報到窗口永遠不會打開）則拋 ValueError。
    剛好等於開放時間可以報到；剛好等於棄權期限就不能報到。
    """
    now_utc = _to_utc(now, "now")
    opens_at = check_in_opens_at(scheduled_at)
    deadline_utc = (
        None
        if forfeit_deadline is None
        else _to_utc(forfeit_deadline, "forfeit_deadline")
    )

    if not teams_known:
        return "teams_pending"
    if deadline_utc is None:
        raise ValueError("兩隊已確定時必須提供 forfeit_deadline")
    if deadline_utc <= opens_at:
        raise ValueError("forfeit_deadline 必須晚於報到開放時間")
    if already_checked_in:
        return "already_checked_in"
    if now_utc < opens_at:
        return "too_early"
    if now_utc >= deadline_utc:
        return "closed"
    return None


def tournament_starts_at(scheduled_times: Iterable[datetime]) -> datetime:
    """回傳賽事開始時間（UTC）＝最早場次的預定開始時間－30 分鐘。

    沒有場次時拋 ValueError。
    """
    times = [_to_utc(value, "scheduled_times") for value in scheduled_times]
    if not times:
        raise ValueError("沒有場次，無法決定賽事開始時間")
    return check_in_opens_at(min(times))
