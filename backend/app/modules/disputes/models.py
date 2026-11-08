"""disputes 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import DateTime, Index, String, Text
from sqlmodel import Field, SQLModel

from app.core.events import Event


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


REPORT_DESCRIPTION_MAX_LENGTH = 1000
REPORT_ATTACHMENT_KEY_MAX_LENGTH = 64


# ---------------------------------------------------------------- 資料表


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


class ReportFiled(Event):
    """隊長提出檢舉（Story 6.4）；期中只發事件，不通知。"""

    report_id: uuid.UUID
    tournament_id: uuid.UUID
    reported_team_id: uuid.UUID


# ---------------------------------------------------------------- API schema


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


class ReportableTeam(BaseModel):
    """S20 檢舉對象選單的一項；`has_open_report`＝本隊對它已有處理中的檢舉。"""

    id: uuid.UUID
    name: str
    has_open_report: bool
