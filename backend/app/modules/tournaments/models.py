"""tournaments 的資料表、schema 與列舉。"""

from enum import StrEnum


class ScoreType(StrEnum):
    """比分型態（AD-18）。"""

    WIN_LOSS = "win_loss"
    ROUNDS = "rounds"


class TournamentMode(StrEnum):
    """賽事模式（AD-20）：校園賽、自訂。"""

    CAMPUS = "campus"
    CUSTOM = "custom"


class TournamentStatus(StrEnum):
    """賽事狀態：尚未開放、開放報名、報名截止、賽程已公布、進行中、已結束、已取消。"""

    UPCOMING = "upcoming"
    OPEN = "open"
    CLOSED = "closed"
    PUBLISHED = "published"
    ONGOING = "ongoing"
    FINISHED = "finished"
    CANCELLED = "cancelled"
