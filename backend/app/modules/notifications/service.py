"""notifications 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。

事件分派（目前只有 VerificationEmailRequested、PasswordResetRequested；事件類型登錄
機制在 Story 1.6）：
worker 每次取一則未處理事件呼叫 `dispatch_event`，再以 `send_next_email` 逐封寄出。
"""

import logging
from datetime import timedelta
from urllib.parse import urlencode

from pydantic import ValidationError
from sqlmodel import Session

from app.core import clock, events
from app.core.config import settings
from app.core.events import OutboxEvent
from app.modules.identity import service as identity_service
from app.modules.identity.models import (
    PasswordResetRequested,
    VerificationEmailRequested,
)
from app.modules.notifications import repository
from app.modules.notifications.email import EmailMessage, EmailSender, render_email
from app.modules.notifications.models import DeliveryStatus, EmailDelivery

logger = logging.getLogger(__name__)

# 事件名稱與 payload 結構都以 identity 的事件類別為準，不在這裡另寫一份
VERIFICATION_EMAIL_REQUESTED = VerificationEmailRequested.event_type
PASSWORD_RESET_REQUESTED = PasswordResetRequested.event_type
# 只寄 Email、不建立站內通知、只有一位收件人且 payload 帶 token 明文的事件
_ACCOUNT_TOKEN_EVENTS: dict[
    str, type[VerificationEmailRequested] | type[PasswordResetRequested]
] = {
    VERIFICATION_EMAIL_REQUESTED: VerificationEmailRequested,
    PASSWORD_RESET_REQUESTED: PasswordResetRequested,
}
# 第 5 次寄送失敗後標為 failed，不再重試
MAX_EMAIL_ATTEMPTS = 5
# 失敗後的重試間隔：1、2、4、8 分鐘
EMAIL_RETRY_BASE_DELAY = timedelta(minutes=1)
LAST_ERROR_MAX_LENGTH = 2000


def dispatch_event(session: Session, event: OutboxEvent) -> None:
    """依事件類型建立 EmailDelivery；重複處理同一事件不會多建。"""
    event_class = _ACCOUNT_TOKEN_EVENTS.get(event.type)
    if event_class is not None:
        try:
            payload = event_class.model_validate(event.payload)
        except ValidationError:
            # 內容壞掉的事件重試也不會成功；記錄後略過，免得卡住後面的事件
            logger.exception("Malformed %s event %s; skipped", event.type, event.id)
            return
        # 驗證信與重設密碼信只寄 Email、不建立站內通知
        repository.add_delivery_if_absent(
            session, event_id=event.id, account_id=payload.account_id, now=clock.now()
        )
        return
    # 其他事件類型的收件規則由之後的 Story 登錄
    logger.info("No handler for event type %s (%s); skipped", event.type, event.id)


def verification_link(token: str, redirect: str | None) -> str:
    params = {"token": token}
    if redirect:
        params["redirect"] = redirect
    # FRONTEND_HOST 設成結尾帶斜線時也不能變成 //verify-email
    host = settings.FRONTEND_HOST.rstrip("/")
    return f"{host}/verify-email?{urlencode(params)}"


def reset_password_link(token: str) -> str:
    host = settings.FRONTEND_HOST.rstrip("/")
    return f"{host}/reset-password?{urlencode({'token': token})}"


class _StaleEmail(Exception):
    """信件內容已經沒有意義（例如驗證連結已失效）：不寄出、也不重試。"""


def _compose(
    session: Session, delivery: EmailDelivery, event: OutboxEvent
) -> EmailMessage:
    """依來源事件的 payload 重組信件。"""
    contact = identity_service.get_account_contact(session, delivery.account_id)
    if contact is None:
        raise LookupError("recipient account no longer exists")
    if event.type == VERIFICATION_EMAIL_REQUESTED:
        payload = VerificationEmailRequested.model_validate(event.payload)
        if not identity_service.is_verification_token_active(session, payload.token):
            raise _StaleEmail(
                "skipped as stale: verification token was superseded, used or "
                "expired, or the account is already verified"
            )
        return render_email(
            to=contact.email,
            title="完成 FLOW 的 Email 驗證",
            body="點下方按鈕完成 Email 驗證，連結 24 小時內有效。",
            button_label="驗證 Email",
            button_url=verification_link(payload.token, payload.redirect),
        )
    if event.type == PASSWORD_RESET_REQUESTED:
        reset = PasswordResetRequested.model_validate(event.payload)
        if not identity_service.is_reset_token_active(session, reset.token):
            raise _StaleEmail(
                "skipped as stale: password reset token was superseded, used or expired"
            )
        return render_email(
            to=contact.email,
            title="重設 FLOW 的密碼",
            body=(
                "點下方按鈕設定新密碼，連結 1 小時內有效。"
                "如果你沒有申請重設密碼，可以忽略這封信。"
            ),
            button_label="設定新密碼",
            button_url=reset_password_link(reset.token),
        )
    raise LookupError(f"no email template for event type {event.type}")


def send_next_email(session: Session, *, sender: EmailSender) -> bool:
    """寄出一封到期的待寄 Email；回傳是否處理了一筆（沒有待寄的時回傳 False）。

    寄送失敗不往外拋：attempts＋1、記錄 last_error，延後到之後的輪詢再試；
    第 MAX_EMAIL_ATTEMPTS 次仍失敗就標為 failed。內容已過時的信（驗證或重設連結已失效）
    直接標為 failed、不寄出也不重試。到了最終狀態後，事件 payload 裡的 token 明文
    就不再需要，立即移除。
    """
    now = clock.now()
    delivery = repository.next_due_delivery(session, now)
    if delivery is None:
        return False

    event = events.get(session, delivery.event_id)
    try:
        if event is None:
            raise LookupError("source event no longer exists")
        message = _compose(session, delivery, event)
        # 至少寄一次（at-least-once）：寄信發生在鎖住這筆 delivery 的交易裡，
        # 寄出後若 commit 失敗，交易回滾、這筆仍是 pending，之後的輪詢會再寄一次。
        sender.send(message)
    except _StaleEmail as exc:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error = str(exc)
        logger.info("Email delivery %s skipped: %s", delivery.id, exc)
    except Exception as exc:
        delivery.attempts += 1
        delivery.last_error = f"{type(exc).__name__}: {exc}"[:LAST_ERROR_MAX_LENGTH]
        if delivery.attempts >= MAX_EMAIL_ATTEMPTS:
            delivery.status = DeliveryStatus.FAILED
            logger.error("Email delivery %s failed permanently", delivery.id)
        else:
            delivery.next_attempt_at = now + EMAIL_RETRY_BASE_DELAY * (
                2 ** (delivery.attempts - 1)
            )
            logger.warning(
                "Email delivery %s failed (attempt %d): %s",
                delivery.id,
                delivery.attempts,
                delivery.last_error,
            )
    else:
        delivery.attempts += 1
        delivery.status = DeliveryStatus.SENT
        delivery.last_error = None
    session.add(delivery)
    if (
        delivery.status != DeliveryStatus.PENDING
        and event is not None
        and event.type in _ACCOUNT_TOKEN_EVENTS
    ):
        # 驗證信與重設信只有一位收件人：這筆結束後 token 明文不再需要，不留在資料庫
        events.drop_payload_keys(session, event, "token")
    session.flush()
    return True
