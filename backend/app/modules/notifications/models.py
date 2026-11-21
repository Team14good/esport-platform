"""notifications 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core import clock

# S14 每頁筆數；與其他分頁 API 相同
PAGE_SIZE = 20
# 與 identity 的分頁上限相同；超過回 422
MAX_PAGE = 100_000
NOTIFICATION_TITLE_MAX_LENGTH = 200
NOTIFICATION_BODY_MAX_LENGTH = 1000
NOTIFICATION_LINK_MAX_LENGTH = 500


class DeliveryStatus(StrEnum):
    """Email 寄送狀態：待寄、已寄出、失敗。"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class EmailDelivery(SQLModel, table=True):
    """一封要寄給某個帳號的 Email；信件內容在寄送時依來源事件的 payload 重組。"""

    __tablename__ = "email_delivery"
    __table_args__ = (
        # 同一事件不會重複寄給同一人
        UniqueConstraint(
            "event_id", "account_id", name="uq_email_delivery_event_id_account_id"
        ),
        Index("ix_email_delivery_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="outbox_event.id")
    account_id: uuid.UUID = Field(foreign_key="account.id")
    status: DeliveryStatus = Field(default=DeliveryStatus.PENDING, sa_type=String(16))
    attempts: int = 0
    last_error: str | None = Field(default=None, sa_type=Text)
    # 下一次可以嘗試寄送的時間；失敗後往後延，同一輪不會重試同一封
    next_attempt_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )


class Notification(SQLModel, table=True):
    """一則站內通知：某個事件發給某個帳號（Story 1.6）。

    `title` 顯示在介面上、也是 Email 主旨；`body` 是 Email 內文的一段說明；
    `link` 是站內路徑（例如 `/teams/<id>`），Email 按鈕連到 `FRONTEND_HOST + link`。
    """

    __table_args__ = (
        # 同一事件不會重複通知同一人
        UniqueConstraint(
            "event_id", "account_id", name="uq_notification_event_id_account_id"
        ),
        Index("ix_notification_account_id_created_at", "account_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    account_id: uuid.UUID = Field(foreign_key="account.id")
    event_id: uuid.UUID = Field(foreign_key="outbox_event.id")
    # 來源事件類型（例如 OrganizerApplicationApproved）
    type: str = Field(max_length=100)
    title: str = Field(max_length=NOTIFICATION_TITLE_MAX_LENGTH)
    body: str = Field(max_length=NOTIFICATION_BODY_MAX_LENGTH)
    link: str = Field(max_length=NOTIFICATION_LINK_MAX_LENGTH)
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
    # 標為已讀的時間；None 代表未讀
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


# ---------------------------------------------------------------- API schema


class NotificationRead(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    link: str
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    """通知的分頁結果，依 `created_at` 由新到舊；`page` 超過總頁數時 `items` 為空。"""

    items: list[NotificationRead]
    total: int
    page: int
    page_size: int


class UnreadCount(BaseModel):
    count: int
