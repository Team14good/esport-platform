"""disputes 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel
from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlmodel import Field, SQLModel

from app.core.events import Event
from app.modules.competition.models import (
    GameScoreIn,
    MatchOutcome,
    MatchStatus,
    PublicGame,
    PublicTeamRef,
)
from app.modules.tournaments.models import ScoreType


class AppealStatus(StrEnum):
    """申訴狀態：處理中、已結案。"""

    OPEN = "open"
    CLOSED = "closed"


class AppealDecision(StrEnum):
    """申訴處理結果：維持原結果、更正結果、重新比賽（只用於棄權判定）、取消資格。

    `disqualified`：檢舉屬實取消資格（6.5）時，受影響場次的未結案申訴一併以此結案。
    """

    UPHELD = "upheld"
    CORRECTED = "corrected"
    REMATCH = "rematch"
    DISQUALIFIED = "disqualified"


class ReportStatus(StrEnum):
    """檢舉狀態：處理中、駁回、屬實。"""

    OPEN = "open"
    DISMISSED = "dismissed"
    SUBSTANTIATED = "substantiated"


REPORT_DESCRIPTION_MAX_LENGTH = 1000
REPORT_ATTACHMENT_KEY_MAX_LENGTH = 64
# 申訴說明的字數上限（以 code point 計算；前端以 UTF-16 計，emoji 等字元兩邊算法不同）
APPEAL_DESCRIPTION_MAX_LENGTH = 1000
# 處理理由的字數上限（同上，以 code point 計算）
APPEAL_REASON_MAX_LENGTH = 1000
# 同一隊對同一場只能有一筆未結案申訴（部分唯一索引）
OPEN_APPEAL_INDEX = "uq_appeal_open_match_team"
# 檢舉處理理由的字數上限（以 code point 計算，與前端一致）
REPORT_REASON_MAX_LENGTH = 1000


# ---------------------------------------------------------------- 資料表


class Appeal(SQLModel, table=True):
    """隊長對申訴期內的場次結果提出的申訴（6.1）；處理欄位由 6.2 寫入。

    同一隊對同一場只能有一筆未結案申訴（`status='open'` 的部分唯一索引），也是併發
    重複送出的最後防線；重新比賽後上一輪的申訴已結案，原申訴隊可以對新結果再申訴。
    申訴內容與附件不出現在任何公開 API。
    """

    __tablename__ = "appeal"
    __table_args__ = (
        Index(
            OPEN_APPEAL_INDEX,
            "match_id",
            "team_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    # competition 的表：只建外鍵，disputes 不直接讀寫；依場次查申訴用索引
    match_id: uuid.UUID = Field(foreign_key="match.id", index=True)
    # 隊伍屬 registration，不建跨模組外鍵（比照 match、check_in）
    team_id: uuid.UUID
    filed_by: uuid.UUID = Field(foreign_key="account.id")
    filed_at: datetime = Field(sa_type=DateTime(timezone=True))
    description: str = Field(max_length=APPEAL_DESCRIPTION_MAX_LENGTH)
    # core.storage 的鍵值；只有該賽事主辦方能下載（AD-15）
    attachment_key: str | None = Field(default=None, max_length=64)
    status: AppealStatus = Field(sa_type=String(16))
    decision: AppealDecision | None = Field(default=None, sa_type=String(16))
    # 處理理由，6.2 結案時必填
    reason: str | None = Field(default=None, sa_type=Text)
    handled_by: uuid.UUID | None = Field(default=None, foreign_key="account.id")
    handled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    # 6.3 逾期提醒（期中擱置）；期中一律 None
    reminded_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class Report(SQLModel, table=True):
    """檢舉（Story 6.4 建立；6.5 只寫入處理欄位 `status`、`reason`、`handled_by`、`handled_at`）。

    `attachment_key` 是 `core.storage` 的鍵值，只留在資料庫，不出現在任何 API 回應。
    """

    __table_args__ = (
        Index(
            "ix_report_reporter_team_id_reported_team_id",
            "reporter_team_id",
            "reported_team_id",
        ),
        # 6.5 取消資格後要結案「對同一隊的其他未結案檢舉」
        Index("ix_report_reported_team_id_status", "reported_team_id", "status"),
        # service 已擋 REPORT_SELF；資料庫再擋一次，避免繞過 service 的寫入
        CheckConstraint(
            "reporter_team_id <> reported_team_id",
            name="ck_report_reporter_not_reported",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    reporter_team_id: uuid.UUID = Field(foreign_key="team.id")
    filed_by: uuid.UUID = Field(foreign_key="account.id")
    reported_team_id: uuid.UUID = Field(foreign_key="team.id")
    filed_at: datetime = Field(sa_type=DateTime(timezone=True))
    description: str = Field(max_length=REPORT_DESCRIPTION_MAX_LENGTH)
    attachment_key: str | None = Field(
        default=None, max_length=REPORT_ATTACHMENT_KEY_MAX_LENGTH
    )
    status: ReportStatus = Field(sa_type=String(32))
    # 處理理由要寫查證經過，與申訴的 reason 同樣用 Text；長度上限由 6.5 的 service 驗證
    reason: str | None = Field(default=None, sa_type=Text)
    handled_by: uuid.UUID | None = Field(default=None, foreign_key="account.id")
    handled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


# ---------------------------------------------------------------- 事件


class AppealFiled(Event):
    """隊長提出申訴（6.1）。"""

    appeal_id: uuid.UUID
    match_id: uuid.UUID
    team_id: uuid.UUID


class AppealResolved(Event):
    """主辦方處理同一場次的申訴（6.2，同一場一次）。"""

    match_id: uuid.UUID
    decision: AppealDecision


class ReportFiled(Event):
    """隊長提出檢舉（Story 6.4）；期中只發事件，不通知。"""

    report_id: uuid.UUID
    tournament_id: uuid.UUID
    reported_team_id: uuid.UUID


class ReportResolved(Event):
    """主辦方處理檢舉（Story 6.5）：駁回或屬實；期中只發事件，不通知。"""

    report_id: uuid.UUID
    substantiated: bool


# ---------------------------------------------------------------- API schema


class AppealRead(BaseModel):
    """一筆申訴（給提出的隊長與主辦方；不出現在公開 API）。

    附件只回 `has_attachment`，不回鍵值（AD-15）；主辦方經下載 API 取得檔案。
    """

    id: uuid.UUID
    tournament_id: uuid.UUID
    match_id: uuid.UUID
    team_id: uuid.UUID
    filed_by: uuid.UUID
    filed_at: datetime
    description: str
    has_attachment: bool
    status: AppealStatus
    decision: AppealDecision | None
    reason: str | None
    handled_by: uuid.UUID | None
    handled_at: datetime | None


AppealStateReason = Literal[
    "not_captain", "not_appealable", "deadline_passed", "already_filed"
]


class AppealState(BaseModel):
    """登入者對某場次的申訴狀態（S4 入口），和提出申訴 API 用同一套檢查。

    只回登入者本隊的狀態，不透露另一隊有沒有申訴。
    `reason` 與 API 錯誤碼一一對應：`not_captain`→`CAPTAIN_REQUIRED`、
    `not_appealable`→`APPEAL_NOT_ALLOWED`、`deadline_passed`→`APPEAL_DEADLINE_PASSED`、
    `already_filed`→`APPEAL_ALREADY_FILED`；可以提出時為 None。
    """

    can_file: bool
    already_filed: bool
    deadline: datetime | None  # 場次在申訴期、申訴中時為申訴截止時間，其他為 None
    reason: AppealStateReason | None


class AppealItem(AppealRead):
    """S32 列表的一筆申訴：加上提出隊伍的隊名。"""

    team_name: str


class AppealGroup(BaseModel):
    """S32 依場次分組的申訴（只給該賽事主辦方）；同一場次的申訴一次處理。"""

    match_id: uuid.UUID
    match_code: str
    round_name: str
    is_third_place: bool
    scheduled_at: datetime
    match_status: MatchStatus
    outcome: MatchOutcome | None
    winner_id: uuid.UUID | None
    wins_a: int
    wins_b: int
    # 更正結果的輸入依比分型態與本輪 BO
    score_type: ScoreType
    best_of: int
    # 目前已登錄的各局（更正時的預設值）
    games: list[PublicGame]
    team_a: PublicTeamRef | None
    team_b: PublicTeamRef | None
    # 有未結案的申訴（可以處理）
    has_open: bool
    # 依提出時間
    appeals: list[AppealItem]


class AppealResolveIn(BaseModel):
    """處理申訴的請求：`corrected` 要給整組新的 `games`；`rematch` 要給帶時區的 `replay_at`。"""

    decision: AppealDecision
    # 去頭尾空白後 1～1000 字，由 service 驗證（422 指向 reason）
    reason: str
    # 最多 7 局（BO7 是最大的 BO）
    games: list[GameScoreIn] | None = Field(default=None, max_length=7)
    replay_at: AwareDatetime | None = None


class PublicAppealResult(BaseModel):
    """公開的申訴處理結果（S4）；不含申訴內容（AD-19）。未經申訴處理或重新比賽為 None。

    `disqualified`：檢舉屬實取消資格時一併結案（6.5）。
    """

    decision: Literal["upheld", "corrected", "disqualified"] | None


class OpenDisputeItem(BaseModel):
    """S27 待處理清單的一筆：申訴（`match_id`、`match_code`）或檢舉（`team_name`）。"""

    kind: Literal["appeal", "report"]
    id: uuid.UUID
    # 申訴的場次；檢舉為 None
    match_id: uuid.UUID | None
    match_code: str | None
    filed_at: datetime
    # 處理期限。申訴：等待結果的下一場預定時間，決賽與季軍賽為提出後 1 小時。
    # 檢舉：被檢舉隊伍下一場待開打場次的預定時間；沒有下一場時為 None
    deadline: datetime | None
    # 檢舉：被檢舉隊伍的隊名；申訴為 None
    team_name: str | None = None


class OpenDisputes(BaseModel):
    """S27 待處理：未結案申訴數、檢舉數與每一筆。

    依處理期限由近到遠（同期限依提出時間）；沒有期限的檢舉排在最後、依提出時間。
    `earliest_deadline` 只看有期限的項目。
    """

    appeals: int
    reports: int
    earliest_deadline: datetime | None
    items: list[OpenDisputeItem]


class ReportRead(BaseModel):
    """檢舉內容；不含附件鍵值，只以 `has_attachment` 表示有沒有附件。"""

    id: uuid.UUID
    tournament_id: uuid.UUID
    reporter_team_id: uuid.UUID
    reporter_team_name: str
    reported_team_id: uuid.UUID
    reported_team_name: str
    filed_by: uuid.UUID
    filed_at: datetime
    description: str
    has_attachment: bool
    status: ReportStatus
    reason: str | None
    handled_by: uuid.UUID | None
    handled_at: datetime | None


class ReportResolveIn(BaseModel):
    """處理檢舉的請求（S33）：`substantiated` 為 false 是駁回、true 是屬實。"""

    substantiated: bool
    # 去頭尾空白後 1～1000 字，由 service 驗證（422 指向 reason）
    reason: str


class ReportableTeam(BaseModel):
    """S20 檢舉對象選單的一項；`has_open_report`＝本隊對它已有處理中的檢舉。"""

    id: uuid.UUID
    name: str
    has_open_report: bool
