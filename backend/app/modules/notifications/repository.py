"""notifications 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app.modules.notifications.models import DeliveryStatus, EmailDelivery


def add_delivery_if_absent(
    session: Session, *, event_id: uuid.UUID, account_id: uuid.UUID, now: datetime
) -> None:
    """建立一筆待寄的 EmailDelivery；（event_id, account_id）已存在時不做任何事。"""
    statement = (
        insert(EmailDelivery)
        .values(
            id=uuid.uuid4(),
            event_id=event_id,
            account_id=account_id,
            status=DeliveryStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_email_delivery_event_id_account_id")
    )
    session.connection().execute(statement)


def next_due_delivery(session: Session, now: datetime) -> EmailDelivery | None:
    """取一筆到了可寄時間的待寄 Email 並加鎖；其他交易已鎖住的略過。"""
    statement = (
        select(EmailDelivery)
        .where(EmailDelivery.status == DeliveryStatus.PENDING)
        .where(col(EmailDelivery.next_attempt_at) <= now)
        .order_by(col(EmailDelivery.next_attempt_at), col(EmailDelivery.created_at))
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return session.exec(statement).first()
