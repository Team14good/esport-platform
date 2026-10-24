"""事件 outbox（AD-6）：與業務資料同一個交易寫入，由 worker 逐則消化。

service 呼叫 `publish(session, event)`，事件與業務資料一起 commit；交易回滾時
事件也不存在。worker 以 `next_unprocessed()` 取一則未處理的事件（加鎖、略過
其他 worker 已鎖住的），交給 notifications 分派後以 `mark_processed()` 標記。
"""

import re
import uuid
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Session, SQLModel, col, select

from app.core import clock

# PascalCase、至少兩個字（名詞＋過去式動詞，例如 MatchResultConfirmed、BracketDrawn）；
# 不規則動詞（Drawn、Won）無法以字尾判斷，過去式由命名審查把關
_EVENT_NAME_PATTERN = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$")


class Event(BaseModel):
    """事件基底：類別名稱就是事件名稱（過去式 PascalCase），欄位就是 payload。

    payload 只帶實體 id 與事件特有的資料，不帶收件人（收件人由 notifications 決定）。
    """

    model_config = ConfigDict(frozen=True)

    event_type: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not _EVENT_NAME_PATTERN.fullmatch(cls.__name__):
            raise ValueError(
                f"Event name must be PascalCase with at least two words: {cls.__name__!r}"
            )
        cls.event_type = cls.__name__


class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_event"
    __table_args__ = (
        Index("ix_outbox_event_processed_at_created_at", "processed_at", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    type: str = Field(max_length=100)
    payload: dict[str, Any] = Field(sa_type=JSONB)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    # worker 處理完成的時間；None 代表尚未處理
    processed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


def publish(session: Session, event: Event) -> OutboxEvent:
    """在目前的交易裡寫入一則事件；不 commit。"""
    row = OutboxEvent(
        type=event.event_type,
        payload=event.model_dump(mode="json"),
        created_at=clock.now(),
    )
    session.add(row)
    session.flush()
    return row


def get(session: Session, event_id: uuid.UUID) -> OutboxEvent | None:
    return session.get(OutboxEvent, event_id)


def next_unprocessed(session: Session) -> OutboxEvent | None:
    """取最舊的一則未處理事件並加鎖；其他交易已鎖住的事件略過。"""
    statement = (
        select(OutboxEvent)
        .where(col(OutboxEvent.processed_at).is_(None))
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return session.exec(statement).first()


def drop_payload_keys(session: Session, event: OutboxEvent, *keys: str) -> None:
    """從事件 payload 移除不再需要的欄位（例如寄出後的 token 明文）。"""
    if not any(key in event.payload for key in keys):
        return
    # 換成新的 dict，SQLAlchemy 才會偵測到 JSONB 欄位有變動
    event.payload = {k: v for k, v in event.payload.items() if k not in keys}
    session.add(event)
    session.flush()


def mark_processed(session: Session, event: OutboxEvent) -> None:
    event.processed_at = clock.now()
    session.add(event)
    session.flush()
