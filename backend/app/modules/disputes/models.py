"""disputes 的資料表、schema 與列舉。"""

from enum import StrEnum


class AppealStatus(StrEnum):
    """申訴狀態：處理中、已結案。"""

    OPEN = "open"
    CLOSED = "closed"


class AppealDecision(StrEnum):
    """申訴處理結果：維持原結果、更正結果、重新比賽（只用於棄權判定）。"""

    UPHELD = "upheld"
    CORRECTED = "corrected"
    REMATCH = "rematch"


class ReportStatus(StrEnum):
    """檢舉狀態：處理中、駁回、屬實。"""

    OPEN = "open"
    DISMISSED = "dismissed"
    SUBSTANTIATED = "substantiated"
