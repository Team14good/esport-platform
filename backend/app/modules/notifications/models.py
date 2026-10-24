"""notifications 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core import clock


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
