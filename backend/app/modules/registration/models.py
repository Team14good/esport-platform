"""registration 的資料表、schema 與列舉。"""

from enum import StrEnum


class MemberRole(StrEnum):
    """隊員角色：隊長、選手。"""

    CAPTAIN = "captain"
    PLAYER = "player"


class RegistrationStatus(StrEnum):
    """報名狀態：組隊中、已送出・待分配、正取、候補、退回、撤回、已參賽、退賽、取消資格。"""

    FORMING = "forming"
    PENDING = "pending"
    ACCEPTED = "accepted"
    WAITLISTED = "waitlisted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    DRAWN = "drawn"
    RETIRED = "retired"
    DISQUALIFIED = "disqualified"
