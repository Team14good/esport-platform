"""registration 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator
from pydantic_core import PydanticCustomError
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from app.core import clock
from app.core.events import Event
from app.modules.tournaments.models import RankTierRead


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


TEAM_NAME_MAX_LENGTH = 30
INVITE_TOKEN_MAX_LENGTH = 64
GAME_ACCOUNT_ID_MAX_LENGTH = 50
RANK_TIER_MAX_LENGTH = 50
RANK_SCREENSHOT_KEY_MAX_LENGTH = 64
RANK_SCREENSHOT_NAME_MAX_LENGTH = 100


# ---------------------------------------------------------------- 資料表


class Team(SQLModel, table=True):
    """隊伍：只屬於一個賽事。邀請 token 要能重複顯示給隊員，所以明文儲存（UNIQUE）。"""

    # 同賽事內隊名不分大小寫不可重複
    __table_args__ = (
        Index(
            "ix_team_tournament_id_lower_name",
            "tournament_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    name: str = Field(max_length=TEAM_NAME_MAX_LENGTH)
    invite_token: str = Field(max_length=INVITE_TOKEN_MAX_LENGTH, unique=True)
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )


class TeamMember(SQLModel, table=True):
    """隊員。（tournament_id, account_id）唯一：同一帳號在同一賽事只能在一支隊伍。

    參賽資料（Story 3.2）：遊戲 ID、段位與其積分、段位截圖的檔案鍵值與清理過的原始
    檔名；尚未填寫時為 null。截圖鍵值只留在資料庫，不出現在任何 API 回應。
    """

    __tablename__ = "team_member"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "account_id",
            name="uq_team_member_tournament_id_account_id",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id")
    account_id: uuid.UUID = Field(foreign_key="account.id", index=True)
    role: MemberRole = Field(sa_type=String(16))
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
    game_account_id: str | None = Field(
        default=None, max_length=GAME_ACCOUNT_ID_MAX_LENGTH
    )
    rank_tier: str | None = Field(default=None, max_length=RANK_TIER_MAX_LENGTH)
    rank_score: int | None = Field(default=None)
    rank_screenshot_key: str | None = Field(
        default=None, max_length=RANK_SCREENSHOT_KEY_MAX_LENGTH
    )
    rank_screenshot_name: str | None = Field(
        default=None, max_length=RANK_SCREENSHOT_NAME_MAX_LENGTH
    )


class Registration(SQLModel, table=True):
    """報名：建立隊伍時同時產生（組隊中）；狀態只能經 `service.mark_status()` 修改。

    送出時的快照（Story 3.3）：學校、全隊（含替補）平均段位積分、送出時間；組隊中為
    null，送出後不再變動（分配只看快照，AD-12）。
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", unique=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    status: RegistrationStatus = Field(sa_type=String(32))
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
    school_id: uuid.UUID | None = Field(default=None, foreign_key="school.id")
    # 段位積分上限是 PostgreSQL integer 上限，numeric(6,2) 會溢位
    avg_rank_score: Decimal | None = Field(default=None, sa_type=Numeric(12, 2))
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class PriorityWindowSettlement(SQLModel, table=True):
    """優先期結算紀錄（Story 3.4）：一場賽事一筆，存在就代表已結算，worker 不再處理。

    `priority_school_ids`＝參加優先期結算的報名的學校（可為空），先搶期的候補順位用它
    判斷「優先期有報名的學校」（FR-15、FR-17）。
    """

    __tablename__ = "priority_window_settlement"

    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", primary_key=True)
    settled_at: datetime = Field(sa_type=DateTime(timezone=True))
    priority_school_ids: list[uuid.UUID] = Field(
        sa_column=Column(ARRAY(Uuid()), nullable=False)
    )


# ---------------------------------------------------------------- 事件


class RegistrationAllocated(Event):
    """報名已分配為正取或候補（3.4 優先期結算；3.5、3.6 沿用）。"""

    registration_id: uuid.UUID
    team_id: uuid.UUID
    tournament_id: uuid.UUID
    status: RegistrationStatus


# ---------------------------------------------------------------- API schema


def _require_str(value: object) -> object:
    if not isinstance(value, str):
        raise PydanticCustomError("string_required", "請輸入文字")
    return value


def _validate_team_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise PydanticCustomError("team_name_required", "請輸入隊名")
    if len(name) > TEAM_NAME_MAX_LENGTH:
        raise PydanticCustomError(
            "team_name_too_long", f"隊名最多 {TEAM_NAME_MAX_LENGTH} 個字"
        )
    return name


TeamNameField = Annotated[
    str, BeforeValidator(_require_str), AfterValidator(_validate_team_name)
]

# 邀請連結的狀態：可加入、隊伍已滿、報名已截止（不在報名期間）、名單已鎖定（報名已送出）
# 優先順序：locked > closed > full > active
InviteStatus = Literal["active", "full", "closed", "locked"]


class TeamCreate(BaseModel):
    """S16 建立隊伍。"""

    name: TeamNameField


# 參賽資料缺漏的欄位代碼（固定依此順序列出）
MissingProfileField = Literal["game_account_id", "rank_tier", "rank_screenshot"]

# 不能送出報名的原因代碼；REGISTRATION_CLOSED 只用於畫面（送出時另回 409）
SubmitBlockerCode = Literal[
    "STARTERS_NOT_MET",
    "PROFILE_INCOMPLETE",
    "SCHOOL_MISSING",
    "SCHOOL_MISMATCH",
    "REGISTRATION_CLOSED",
]


# 候補沒有順位的原因代碼與計算順位時的階段；值與 `allocation.WaitlistReason`、
# `allocation.AllocationPhase` 相同（allocation 會 import 本檔，所以這裡用 Literal）
WaitlistReasonCode = Literal[
    "SCHOOL_NOT_ELIGIBLE", "LATER_THAN_SCHOOLMATE", "SCHOOL_LIMIT_REACHED"
]
WaitlistPhase = Literal["first_come", "after_deadline"]


class WaitlistFields(BaseModel):
    """S17、S12 共用的候補資訊（Story 3.4），只在 `waitlisted` 時有值，其他狀態皆為 null。

    `waitlist_position`：候補第 N 位，沒有順位時為 null 並帶 `waitlist_reason`；
    `representative_backfill`：代表隊退出時由同校遞補的補充；`waitlist_phase`：計算順位
    的階段（報名截止前為先搶期，之後為截止後），畫面依此顯示當下階段的遞補規則說明。
    """

    waitlist_position: int | None
    waitlist_reason: WaitlistReasonCode | None
    representative_backfill: bool | None
    waitlist_phase: WaitlistPhase | None


class SubmitBlocker(BaseModel):
    """S17「送出報名」停用的一項原因；`message` 與伺服器拒絕時的文字相同。"""

    code: SubmitBlockerCode
    message: str


class TeamMemberRead(BaseModel):
    account_id: uuid.UUID
    display_name: str
    role: MemberRole
    joined_at: datetime
    game_account_id: str | None
    rank_tier: str | None
    rank_score: int | None
    has_rank_screenshot: bool
    # 截圖原始檔名可能含個資，只在檢視者自己那列有值
    rank_screenshot_name: str | None
    # 尚未填寫的參賽資料，依 game_account_id、rank_tier、rank_screenshot 的順序
    missing_fields: list[MissingProfileField]


class TeamDetail(WaitlistFields):
    """S17 隊伍頁：只有隊員看得到（含邀請 token）。"""

    id: uuid.UUID
    name: str
    tournament_id: uuid.UUID
    tournament_name: str
    game_name: str
    starters: int
    substitutes: int
    # 隊伍人數上限＝先發＋替補
    max_members: int
    members: list[TeamMemberRead]
    registration_status: RegistrationStatus
    invite_token: str
    invite_status: InviteStatus
    # 目前檢視者在這支隊伍的角色
    my_role: MemberRole
    # 賽事快照的段位對照表（積分由高到低），S18 的段位選項
    rank_tiers: list[RankTierRead]
    # 已填段位成員（含替補）的平均段位積分，取到小數第二位；沒有人填時為 null
    avg_rank_score: float | None
    rank_filled_count: int
    # 報名期間（賽事開放且早於截止時間）且報名仍是組隊中時，隊員才能修改自己的參賽資料
    profile_editable: bool
    # 不能送出報名的原因（固定順序）；只在組隊中計算，其他狀態為空
    submit_blockers: list[SubmitBlocker]
    priority_end: datetime
    registration_end: datetime
    # 送出報名的時間：由 `submit_registration` 寫入；組隊中、或不經送出而離開組隊中
    # 的報名（例如撤回）為 null
    submitted_at: datetime | None


class TeamInvitePreview(BaseModel):
    """S19 加入隊伍前的公開預覽：不含隊員名單與任何個資（AD-19）。"""

    team_id: uuid.UUID
    team_name: str
    tournament_id: uuid.UUID
    tournament_name: str
    game_name: str
    member_count: int
    max_members: int
    invite_status: InviteStatus


class MyTeamCard(WaitlistFields):
    """S12 我的隊伍：每支隊伍一張 Registration status card。"""

    team_id: uuid.UUID
    team_name: str
    tournament_id: uuid.UUID
    tournament_name: str
    game_name: str
    registration_status: RegistrationStatus


class TeamMemberRole(BaseModel):
    account_id: uuid.UUID
    role: MemberRole


class TeamRead(BaseModel):
    """給其他模組使用的隊伍資料：隊名、隊員帳號與角色（判斷隊長請用 `registration.service.is_captain`）。"""

    id: uuid.UUID
    tournament_id: uuid.UUID
    name: str
    members: list[TeamMemberRole]


class TeamSummary(BaseModel):
    """給其他模組使用的隊伍摘要：只有 id 與隊名（Story 6.4 檢舉選單）。"""

    id: uuid.UUID
    name: str


class RegistrationRead(BaseModel):
    """給其他模組使用的報名資料。

    `school_id`、`avg_rank_score`、`submitted_at` 是送出時的快照，由 `submit_registration`
    寫入；組隊中為 None。不經送出而離開組隊中的報名（例如組隊中撤回、退回後回到組隊中）
    可能沒有快照，使用前要檢查。
    """

    id: uuid.UUID
    team_id: uuid.UUID
    tournament_id: uuid.UUID
    status: RegistrationStatus
    created_at: datetime
    school_id: uuid.UUID | None
    avg_rank_score: Decimal | None
    submitted_at: datetime | None
