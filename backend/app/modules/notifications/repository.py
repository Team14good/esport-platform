"""notifications 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app.modules.notifications.models import (
    DeliveryStatus,
    EmailDelivery,
    Notification,
)


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


# ---------------------------------------------------------------- 站內通知（Story 1.6）


def add_notification_if_absent(
    session: Session,
    *,
    event_id: uuid.UUID,
    account_id: uuid.UUID,
    type: str,
    title: str,
    body: str,
    link: str,
    now: datetime,
) -> None:
    """建立一則未讀通知；（event_id, account_id）已存在時不做任何事。"""
    statement = (
        insert(Notification)
        .values(
            id=uuid.uuid4(),
            event_id=event_id,
            account_id=account_id,
            type=type,
            title=title,
            body=body,
            link=link,
            created_at=now,
            read_at=None,
        )
        .on_conflict_do_nothing(constraint="uq_notification_event_id_account_id")
    )
    session.connection().execute(statement)


def get_by_event_and_account(
    session: Session, *, event_id: uuid.UUID, account_id: uuid.UUID
) -> Notification | None:
    statement = (
        select(Notification)
        .where(Notification.event_id == event_id)
        .where(Notification.account_id == account_id)
    )
    return session.exec(statement).first()


def list_for_account(
    session: Session, account_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[Notification], int]:
    """某帳號的通知（依 created_at 由新到舊，同時間依 id）與總筆數。"""
    total = session.exec(
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == account_id)
    ).one()
    statement = (
        select(Notification)
        .where(Notification.account_id == account_id)
        .order_by(col(Notification.created_at).desc(), col(Notification.id).desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement)), total


def count_unread(session: Session, account_id: uuid.UUID) -> int:
    statement = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == account_id)
        .where(col(Notification.read_at).is_(None))
    )
    return session.exec(statement).one()


def get_for_account(
    session: Session,
    notification_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Notification | None:
    """只回傳屬於該帳號的通知；別人的或不存在時回傳 None。"""
    statement = (
        select(Notification)
        .where(Notification.id == notification_id)
        .where(Notification.account_id == account_id)
    )
    if for_update:
        # 同時標為已讀時，後到的看得到先到的 read_at，不會覆寫
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()
