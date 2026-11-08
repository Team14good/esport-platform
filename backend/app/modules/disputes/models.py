"""disputes 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.events import Event

# 申訴說明的字數上限（以 code point 計算，與前端一致）
APPEAL_DESCRIPTION_MAX_LENGTH = 1000


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


# ---------------------------------------------------------------- 資料表


class Appeal(SQLModel, table=True):
    """隊長對申訴期內的場次結果提出的申訴（6.1）；處理欄位由 6.2 寫入。

    `(match_id, team_id)` 唯一：每隊每場一次，也是併發重複送出的最後防線。
    申訴內容與附件不出現在任何公開 API。
    """

    __tablename__ = "appeal"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_appeal_match_team"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    # competition 的表：只建外鍵，disputes 不直接讀寫
    match_id: uuid.UUID = Field(foreign_key="match.id")
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


# ---------------------------------------------------------------- schema


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


# ---------------------------------------------------------------- 事件


class AppealFiled(Event):
    """隊長提出申訴（6.1）。"""

    appeal_id: uuid.UUID
    match_id: uuid.UUID
    team_id: uuid.UUID
