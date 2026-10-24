"""Story 1.3：驗證信的分派、去重、寄送與重試（I/O 矩陣的 notifications 部分）。"""

import time
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlmodel import Session, func, select

from app.core import events
from app.core.config import settings
from app.core.events import OutboxEvent
from app.modules.identity import service as identity_service
from app.modules.notifications import service
from app.modules.notifications.email import (
    EmailSendError,
    SmtpEmailSender,
    render_email,
)
from app.modules.notifications.models import DeliveryStatus, EmailDelivery
from tests.conftest import FakeEmailSender, FrozenClock


def _register(session: Session, redirect: str | None = None) -> tuple[str, OutboxEvent]:
    email = f"{uuid.uuid4().hex}@example.com"
    account = identity_service.register(
        session,
        email=email,
        password="password-123",
        display_name="收信測試",
        school_id=None,
        redirect=redirect,
    )
    event = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "VerificationEmailRequested")
    ).all()
    [mine] = [e for e in event if e.payload["account_id"] == str(account.id)]
    return email, mine


def _deliveries(session: Session, event_id: uuid.UUID) -> list[EmailDelivery]:
    return list(
        session.exec(select(EmailDelivery).where(EmailDelivery.event_id == event_id))
    )


def test_dispatch_creates_one_pending_delivery_for_the_account(
    session: Session, frozen_clock: FrozenClock
) -> None:
    _email, event = _register(session)

    service.dispatch_event(session, event)

    [delivery] = _deliveries(session, event.id)
    assert str(delivery.account_id) == event.payload["account_id"]
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.attempts == 0
    assert delivery.last_error is None
    assert delivery.created_at == frozen_clock.now()


def test_dispatching_the_same_event_twice_sends_a_single_email(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    email, event = _register(session)

    service.dispatch_event(session, event)
    service.dispatch_event(session, event)
    while service.send_next_email(session, sender=fake_email_sender):
        pass

    assert len(_deliveries(session, event.id)) == 1
    assert [m.to for m in fake_email_sender.sent] == [email]


def test_sent_verification_email_has_subject_body_and_link(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    email, event = _register(session, redirect="/tournaments/t-1")
    token = event.payload["token"]
    service.dispatch_event(session, event)

    assert service.send_next_email(session, sender=fake_email_sender) is True

    [message] = fake_email_sender.sent
    assert message.to == email
    assert message.subject == "完成 FLOW 的 Email 驗證"
    assert "點下方按鈕完成 Email 驗證，連結 24 小時內有效。" in message.html
    assert "驗證 Email" in message.html
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.attempts == 1

    link = service.verification_link(token, event.payload["redirect"])
    assert link.replace("&", "&amp;") in message.html
    parts = urlsplit(link)
    assert f"{parts.scheme}://{parts.netloc}" == settings.FRONTEND_HOST
    assert parts.path == "/verify-email"
    assert parse_qs(parts.query) == {
        "token": [token],
        "redirect": ["/tournaments/t-1"],
    }
    assert service.send_next_email(session, sender=fake_email_sender) is False

    # 寄出後 token 明文不再留在事件 payload（重新從資料庫讀取確認）
    session.expire_all()
    stored = session.get(OutboxEvent, event.id)
    assert stored is not None
    assert "token" not in stored.payload
    assert stored.payload["account_id"] == event.payload["account_id"]
    assert stored.payload["redirect"] == "/tournaments/t-1"


def test_link_without_redirect_has_only_token() -> None:
    link = service.verification_link("abc", None)

    assert link == f"{settings.FRONTEND_HOST}/verify-email?token=abc"


def test_verification_email_creates_no_in_app_notification(session: Session) -> None:
    # 本 Story 還沒有 Notification 表；分派只會寫 email_delivery
    _email, event = _register(session)
    before = session.exec(select(func.count()).select_from(EmailDelivery)).one()

    service.dispatch_event(session, event)

    assert session.exec(select(func.count()).select_from(EmailDelivery)).one() == (
        before + 1
    )
    assert "notification" not in EmailDelivery.metadata.tables


def test_send_failure_records_attempt_and_retries_on_later_polls(
    session: Session, fake_email_sender: FakeEmailSender, frozen_clock: FrozenClock
) -> None:
    _email, event = _register(session)
    service.dispatch_event(session, event)
    fake_email_sender.fail_with = ConnectionRefusedError("SMTP down")

    assert service.send_next_email(session, sender=fake_email_sender) is True
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.attempts == 1
    assert delivery.last_error is not None and "SMTP down" in delivery.last_error
    # 同一輪不會立刻重試同一封
    assert service.send_next_email(session, sender=fake_email_sender) is False

    # 重試間隔：第 1～4 次失敗後分別延後 1、2、4、8 分鐘
    for attempt, delay_minutes in [(1, 1), (2, 2), (3, 4), (4, 8)]:
        assert delivery.attempts == attempt
        assert delivery.status == DeliveryStatus.PENDING
        due = frozen_clock.now() + timedelta(minutes=delay_minutes)
        assert delivery.next_attempt_at == due
        frozen_clock.set(due - timedelta(seconds=1))
        assert service.send_next_email(session, sender=fake_email_sender) is False
        frozen_clock.set(due)
        assert service.send_next_email(session, sender=fake_email_sender) is True

    assert delivery.attempts == 5
    assert delivery.status == DeliveryStatus.FAILED
    # 最終失敗後也不再保留 token 明文
    assert "token" not in event.payload

    # 第 5 次失敗後不再重試
    frozen_clock.advance(timedelta(days=1))
    fake_email_sender.fail_with = None
    assert service.send_next_email(session, sender=fake_email_sender) is False
    assert fake_email_sender.calls == 5
    assert fake_email_sender.sent == []


def test_failure_then_success_marks_sent(
    session: Session, fake_email_sender: FakeEmailSender, frozen_clock: FrozenClock
) -> None:
    _email, event = _register(session)
    service.dispatch_event(session, event)
    fake_email_sender.fail_with = TimeoutError("slow")
    service.send_next_email(session, sender=fake_email_sender)

    fake_email_sender.fail_with = None
    frozen_clock.advance(timedelta(minutes=1))
    assert service.send_next_email(session, sender=fake_email_sender) is True

    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.attempts == 2
    assert delivery.last_error is None


def test_malformed_and_unknown_events_are_skipped_without_deliveries(
    session: Session,
) -> None:
    from app.core.events import Event

    class SomethingUnrelatedHappened(Event):
        value: int

    unknown = events.publish(session, SomethingUnrelatedHappened(value=1))
    malformed = OutboxEvent(
        type="VerificationEmailRequested",
        payload={"oops": True},
        created_at=unknown.created_at,
    )
    session.add(malformed)
    session.flush()

    service.dispatch_event(session, unknown)
    service.dispatch_event(session, malformed)

    assert _deliveries(session, unknown.id) == []
    assert _deliveries(session, malformed.id) == []


def test_render_email_escapes_html() -> None:
    message = render_email(
        to="a@example.com",
        title="<b>標題</b>",
        body="內文 & <script>",
        button_label="按鈕",
        button_url="https://example.com/?a=1&b=2",
    )

    assert "<script>" not in message.html
    assert "&lt;b&gt;標題&lt;/b&gt;" in message.html
    assert message.subject == "<b>標題</b>"


@pytest.mark.skipif(not settings.emails_enabled, reason="SMTP is not configured")
def test_smtp_sender_delivers_to_mailpit_from_flow() -> None:
    to = f"{uuid.uuid4().hex}@example.com"
    message = render_email(
        to=to,
        title="完成 FLOW 的 Email 驗證",
        body="點下方按鈕完成 Email 驗證，連結 24 小時內有效。",
        button_label="驗證 Email",
        button_url=f"{settings.FRONTEND_HOST}/verify-email?token=abc",
    )

    try:
        SmtpEmailSender().send(message)
    except OSError as exc:  # pragma: no cover - mailpit 沒有啟動
        pytest.skip(f"SMTP server unreachable: {exc}")

    api = f"http://{settings.SMTP_HOST}:8025/api/v1"
    found: list[dict[str, object]] = []
    for _ in range(20):
        found = httpx.get(f"{api}/search", params={"query": f"to:{to}"}).json()[
            "messages"
        ]
        if found:
            break
        time.sleep(0.1)
    [summary] = found
    assert summary["Subject"] == "完成 FLOW 的 Email 驗證"
    assert summary["From"] == {"Name": "FLOW", "Address": settings.EMAILS_FROM_EMAIL}
    detail = httpx.get(f"{api}/message/{summary['ID']}").json()
    assert f"{settings.FRONTEND_HOST}/verify-email?token=abc" in detail["HTML"]


def test_resend_before_first_email_is_sent_only_sends_the_newest_link(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    email, first = _register(session)
    identity_service.resend_verification(session, email=email)
    [second] = [
        e
        for e in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "VerificationEmailRequested")
        )
        if e.payload["account_id"] == first.payload["account_id"] and e.id != first.id
    ]
    new_token = second.payload["token"]
    service.dispatch_event(session, first)
    service.dispatch_event(session, second)

    while service.send_next_email(session, sender=fake_email_sender):
        pass

    [message] = fake_email_sender.sent
    assert new_token in message.html
    [stale] = _deliveries(session, first.id)
    assert stale.status == DeliveryStatus.FAILED
    assert stale.attempts == 0
    assert stale.last_error is not None and "stale" in stale.last_error
    [sent] = _deliveries(session, second.id)
    assert sent.status == DeliveryStatus.SENT
    assert "token" not in first.payload and "token" not in second.payload


def test_account_verified_before_send_sends_nothing(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    _email, event = _register(session)
    identity_service.verify_email(session, token=event.payload["token"])
    service.dispatch_event(session, event)

    assert service.send_next_email(session, sender=fake_email_sender) is True

    assert fake_email_sender.calls == 0
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.last_error is not None and "stale" in delivery.last_error
    assert service.send_next_email(session, sender=fake_email_sender) is False


def test_expired_token_is_not_sent(
    session: Session, fake_email_sender: FakeEmailSender, frozen_clock: FrozenClock
) -> None:
    _email, event = _register(session)
    service.dispatch_event(session, event)
    frozen_clock.advance(timedelta(hours=24))

    assert service.send_next_email(session, sender=fake_email_sender) is True

    assert fake_email_sender.calls == 0
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.FAILED


def test_smtp_sender_raises_when_response_is_unsuccessful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        success = False
        status_code = 550
        error = "mailbox unavailable"

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.invalid")
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setattr(
        "emails.message.Message.send", lambda *_args, **_kwargs: _Response()
    )
    message = render_email(
        to="a@example.com",
        title="標題",
        body="內文",
        button_label="按鈕",
        button_url="https://example.com",
    )

    with pytest.raises(EmailSendError, match="550"):
        SmtpEmailSender().send(message)
