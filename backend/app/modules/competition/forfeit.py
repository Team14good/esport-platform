"""逾時判棄權的規則（Story 5.2 第一階段）：不碰資料庫、不讀時鐘的純函式。

第二階段的 worker 工作用 `list_forfeit_due` 選出場次、`lock_match` 鎖住後，
再呼叫 `judge_forfeit` 重新檢查並依結果寫入；申訴期截止時間用 `appeal_deadline` 算。
「現在」與「判定時間」一律由呼叫端傳入，回傳的時間一律是 UTC。
"""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.modules.competition.models import MatchOutcome, MatchStatus


@dataclass(frozen=True)
class ForfeitVerdict[T: Hashable]:
    """判棄權的結果。

    `forfeit`：已報到的隊伍獲勝，`forfeited` 只含未報到的一隊。
    `double_forfeit`：沒有勝隊，`forfeited` 依序為 a、b 兩隊。
    """

    outcome: MatchOutcome
    winner: T | None
    forfeited: tuple[T, ...]


def _to_utc(value: datetime, name: str) -> datetime:
    """確認 datetime 帶時區並轉成 UTC；沒有時區拋 ValueError。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必須帶時區")
    return value.astimezone(UTC)


def judge_forfeit[T: Hashable](
    *,
    now: datetime,
    tournament_cancelled: bool,
    status: MatchStatus,
    team_a: T | None,
    team_b: T | None,
    forfeit_deadline: datetime | None,
    checked_in: Iterable[T],
) -> ForfeitVerdict[T] | None:
    """判斷這場現在該不該判棄權；不判回傳 None，要判回傳結果。

    依序檢查：賽事已取消、場次不是待開打、兩隊有任一隊未確定、
    現在早於棄權期限、兩隊都已報到；任一成立就回傳 None。
    剛好等於棄權期限就判棄權（與 5.1「剛好等於期限就不能報到」一致）。

    以下視為呼叫端錯誤，拋 ValueError：datetime 沒有時區、兩隊是同一隊、
    報到名單有不屬於這場的隊伍、兩隊已確定卻沒有棄權期限。
    """
    now_utc = _to_utc(now, "now")
    deadline_utc = (
        None
        if forfeit_deadline is None
        else _to_utc(forfeit_deadline, "forfeit_deadline")
    )
    if team_a is not None and team_a == team_b:
        raise ValueError("team_a 與 team_b 不能是同一隊")
    teams = {team for team in (team_a, team_b) if team is not None}
    checked = frozenset(checked_in)
    if not checked <= teams:
        raise ValueError("checked_in 含有不屬於這場的隊伍")
    if team_a is not None and team_b is not None and deadline_utc is None:
        raise ValueError("兩隊已確定時必須提供 forfeit_deadline")

    if tournament_cancelled:
        return None
    if status != MatchStatus.SCHEDULED:
        return None
    if team_a is None or team_b is None or deadline_utc is None:
        return None
    if now_utc < deadline_utc:
        return None

    a_checked = team_a in checked
    b_checked = team_b in checked
    if a_checked and b_checked:
        return None
    if a_checked:
        return ForfeitVerdict(MatchOutcome.FORFEIT, team_a, (team_b,))
    if b_checked:
        return ForfeitVerdict(MatchOutcome.FORFEIT, team_b, (team_a,))
    return ForfeitVerdict(MatchOutcome.DOUBLE_FORFEIT, None, (team_a, team_b))


def appeal_deadline(*, decided_at: datetime, appeal_minutes: int) -> datetime:
    """回傳申訴期截止時間（UTC）＝判定時間＋申訴時限（分鐘）。

    依 FR-30，申訴期從判棄權時起算，所以 worker 延遲時兩隊仍有完整的申訴期。
    `appeal_minutes` 必須是正整數，否則拋 ValueError。
    """
    if (
        isinstance(appeal_minutes, bool)
        or not isinstance(appeal_minutes, int)
        or appeal_minutes <= 0
    ):
        raise ValueError("appeal_minutes 必須是正整數")
    return _to_utc(decided_at, "decided_at") + timedelta(minutes=appeal_minutes)
