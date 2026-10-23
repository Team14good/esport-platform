"""competition 的資料表、schema 與列舉。"""

from enum import StrEnum


class MatchStatus(StrEnum):
    """場次狀態：待開打、進行中、申訴期、申訴中、已確認、已取消（AD-11）。"""

    SCHEDULED = "scheduled"
    LIVE = "live"
    APPEAL_WINDOW = "appeal_window"
    APPEALED = "appealed"
    CONFIRMED = "confirmed"
    VOIDED = "voided"


class MatchOutcome(StrEnum):
    """場次結果類型：正常完賽、一方棄權、雙方棄權、輪空、取消資格判負。"""

    PLAYED = "played"
    FORFEIT = "forfeit"
    DOUBLE_FORFEIT = "double_forfeit"
    WALKOVER = "walkover"
    DISQUALIFIED = "disqualified"
