"""notifications 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。

通知中心（Story 1.6）一律要登入（`CurrentAccount`，未驗證 Email 也可以看）；
只能讀取、標記自己的通知。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.modules.identity.deps import CurrentAccount
from app.modules.notifications import service
from app.modules.notifications.models import (
    MAX_PAGE,
    NotificationPage,
    NotificationRead,
    UnreadCount,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(
    session: SessionDep,
    account: CurrentAccount,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
) -> NotificationPage:
    """自己的通知：依建立時間由新到舊、每頁 20 則。"""
    return service.list_notifications(session, account_id=account.id, page=page)


@router.get("/notifications/unread-count")
def get_unread_count(session: SessionDep, account: CurrentAccount) -> UnreadCount:
    """自己的未讀通知數（頂欄鈴鐺每 30 秒輪詢）。"""
    return service.unread_count(session, account_id=account.id)


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    session: SessionDep, account: CurrentAccount, notification_id: uuid.UUID
) -> NotificationRead:
    """把自己的一則通知標為已讀；別人的或不存在回 404 `NOTIFICATION_NOT_FOUND`。"""
    notification = service.mark_read(
        session, account_id=account.id, notification_id=notification_id
    )
    session.commit()
    return notification
