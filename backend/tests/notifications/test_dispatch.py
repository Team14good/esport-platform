"""Story 1.6：事件類型登錄機制的分派、去重、略過與一般通知的 Email 組成。

以測試專用的事件類型驗證（AC 3），不依賴其他 Story 的業務事件。
"""

import uuid
from collections.abc import Callable, Iterator, Sequence

import pytest
from sqlmodel import Session, func, select

from app.core import events
from app.core.config import settings
from app.core.errors import BusinessError
from app.core.events import Event, OutboxEvent
from app.modules.identity.models import Account
from app.modules.notifications import registry, service
from app.modules.notifications.models import (
    DeliveryStatus,
    EmailDelivery,
    Notification,
)
from app.modules.identity.models import VerificationEmailRequested
from app.modules.notifications.registry import NotificationDraft, RecipientsNotFound
from app.worker import run_once
from app.worker.jobs import dispatch_outbox, make_send_email_job
from tests.conftest import FakeEmailSender, FrozenClock
from tests.helpers import make_account


class WidgetPolished(Event):
    """測試專用事件：`recipients` 由測試決定，`fail` 讓 resolver 模擬查不到實體。"""

    widget_id: uuid.UUID
    recipients: tuple[uuid.UUID, ...] = ()
    fail: str | None = None


def _resolve(_session: Session, event: WidgetPolished) -> Sequence[NotificationDraft]:
    if event.fail == "business":
        raise BusinessError("WIDGET_NOT_FOUND", "找不到這個零件。", status_code=404)
    if event.fail == "lookup":
        raise RecipientsNotFound("widget gone")
    if event.fail == "keyerror":
        # 程式錯誤（例如字典取值寫錯）：不能被當成查不到而略過
        raise KeyError("captain")
    if event.fail == "boom":
        raise RuntimeError("database exploded")
    return [
        NotificationDraft(
            account_id=account_id,
            title="零件已拋光",
            body=f"零件 {event.widget_id} 已拋光完成。",
            link=f"/widgets/{event.widget_id}",
        )
        for account_id in event.recipients
    ]


@pytest.fixture(autouse=True)
def widget_rule() -> Iterator[None]:
    registry.register(WidgetPolished, _resolve)
    try:
        yield
    finally:
        registry.unregister(WidgetPolished)


def _publish(
    session: Session, *recipients: Account, fail: str | None = None
) -> OutboxEvent:
    return events.publish(
        session,
        WidgetPolished(
            widget_id=uuid.uuid4(),
            recipients=tuple(r.id for r in recipients),
            fail=fail,
        ),
    )


def _notifications(session: Session, event_id: uuid.UUID) -> list[Notification]:
    statement = select(Notification).where(Notification.event_id == event_id)
    return list(session.exec(statement))


def _deliveries(session: Session, event_id: uuid.UUID) -> list[EmailDelivery]:
    statement = select(EmailDelivery).where(EmailDelivery.event_id == event_id)
    return list(session.exec(statement))


def test_registered_event_creates_a_notification_and_email_per_recipient(
    session: Session, frozen_clock: FrozenClock
) -> None:
    alice, bob = make_account(session), make_account(session)
    event = _publish(session, alice, bob)

    service.dispatch_event(session, event)

    notifications = _notifications(session, event.id)
    assert {n.account_id for n in notifications} == {alice.id, bob.id}
    widget_id = event.payload["widget_id"]
    for notification in notifications:
        assert notification.type == "WidgetPolished"
        assert notification.title == "零件已拋光"
        assert notification.body == f"零件 {widget_id} 已拋光完成。"
        assert notification.link == f"/widgets/{widget_id}"
        assert notification.created_at == frozen_clock.now()
        assert notification.read_at is None
    deliveries = _deliveries(session, event.id)
    assert {d.account_id for d in deliveries} == {alice.id, bob.id}
    assert all(d.status == DeliveryStatus.PENDING for d in deliveries)


def test_dispatching_twice_does_not_duplicate(session: Session) -> None:
    alice, bob = make_account(session), make_account(session)
    event = _publish(session, alice, bob)

    service.dispatch_event(session, event)
    service.dispatch_event(session, event)

    assert len(_notifications(session, event.id)) == 2
    assert len(_deliveries(session, event.id)) == 2


def test_same_recipient_twice_gets_one_notification(session: Session) -> None:
    alice = make_account(session)
    event = _publish(session, alice, alice)

    service.dispatch_event(session, event)

    assert len(_notifications(session, event.id)) == 1
    assert len(_deliveries(session, event.id)) == 1


@pytest.mark.parametrize("fail", ["business", "lookup"])
def test_missing_entity_is_skipped_and_event_marked_processed(
    session: Session, session_factory: Callable[[], Session], fail: str
) -> None:
    alice = make_account(session)
    event = _publish(session, alice, fail=fail)
    session.commit()

    run_once([dispatch_outbox], session_factory=session_factory)

    session.expire_all()
    assert _notifications(session, event.id) == []
    assert _deliveries(session, event.id) == []
    stored = session.get(OutboxEvent, event.id)
    assert stored is not None and stored.processed_at is not None


def test_malformed_payload_is_skipped(session: Session) -> None:
    alice = make_account(session)
    event = _publish(session, alice)
    event.payload = {"widget_id": "not-a-uuid"}
    session.add(event)
    session.flush()

    service.dispatch_event(session, event)

    assert _notifications(session, event.id) == []
    assert _deliveries(session, event.id) == []


def test_unexpected_errors_propagate(session: Session) -> None:
    # 其他例外照常往外拋：worker 的交易回滾，下一輪重試
    alice = make_account(session)
    event = _publish(session, alice, fail="boom")

    with pytest.raises(RuntimeError, match="database exploded"):
        service.dispatch_event(session, event)


@pytest.mark.parametrize("fail", ["boom", "keyerror"])
def test_unexpected_error_leaves_event_unprocessed(
    session: Session, session_factory: Callable[[], Session], fail: str
) -> None:
    # KeyError 是 LookupError 的子類別，也要回滾重試，不能標為已處理
    alice = make_account(session)
    event = _publish(session, alice, fail=fail)
    session.commit()

    run_once([dispatch_outbox], session_factory=session_factory)

    session.expire_all()
    assert _notifications(session, event.id) == []
    stored = session.get(OutboxEvent, event.id)
    assert stored is not None and stored.processed_at is None


def test_failing_event_does_not_block_account_emails(
    session: Session,
    session_factory: Callable[[], Session],
    fake_email_sender: FakeEmailSender,
) -> None:
    # 較早的一般事件每輪都分派失敗；較晚的驗證信事件仍在下一輪寄出
    alice, bob = make_account(session), make_account(session)
    stuck = _publish(session, alice, fail="boom")
    session.commit()
    verification = events.publish(
        session, VerificationEmailRequested(account_id=bob.id, token="t" * 43)
    )
    session.commit()
    jobs = [dispatch_outbox, make_send_email_job(fake_email_sender)]

    for _ in range(2):
        run_once(jobs, session_factory=session_factory)

    session.expire_all()
    stored_stuck = session.get(OutboxEvent, stuck.id)
    assert stored_stuck is not None and stored_stuck.processed_at is None
    stored_verification = session.get(OutboxEvent, verification.id)
    assert stored_verification is not None
    assert stored_verification.processed_at is not None
    [delivery] = _deliveries(session, verification.id)
    assert delivery.account_id == bob.id


def test_unregistered_event_creates_nothing(session: Session) -> None:
    class GadgetTwisted(Event):
        gadget_id: uuid.UUID

    event = events.publish(session, GadgetTwisted(gadget_id=uuid.uuid4()))

    service.dispatch_event(session, event)

    assert _notifications(session, event.id) == []
    assert _deliveries(session, event.id) == []


def test_team_checked_in_is_not_registered() -> None:
    # 不在 FR-37 對照表的事件不登錄
    for event_type in ("TeamCheckedIn", "MatchResultSubmitted", "MatchResultConfirmed"):
        assert registry.get_rule(event_type) is None
    for event_type in ("VerificationEmailRequested", "PasswordResetRequested"):
        assert registry.get_rule(event_type) is None


def test_general_notification_email_uses_title_body_and_link(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    alice = make_account(session)
    event = _publish(session, alice)
    service.dispatch_event(session, event)

    assert service.send_next_email(session, sender=fake_email_sender) is True

    [message] = fake_email_sender.sent
    widget_id = event.payload["widget_id"]
    assert message.to == alice.email
    assert message.subject == "零件已拋光"
    assert f"零件 {widget_id} 已拋光完成。" in message.html
    assert "前往 FLOW 查看" in message.html
    assert f"{settings.FRONTEND_HOST}/widgets/{widget_id}" in message.html
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.SENT
    # 一般事件的 payload 不帶 token，寄出後不改動
    assert "widget_id" in event.payload


def test_email_link_ignores_trailing_slash_on_frontend_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FRONTEND_HOST", "http://localhost:5173/")

    assert service.notification_link("/teams/1") == "http://localhost:5173/teams/1"


def test_delivery_without_notification_is_retried(
    session: Session, fake_email_sender: FakeEmailSender
) -> None:
    alice = make_account(session)
    event = _publish(session, alice)
    # 只有 EmailDelivery、沒有 Notification（理論上不會發生）：LookupError 走重試
    session.add(EmailDelivery(event_id=event.id, account_id=alice.id))
    session.flush()

    assert service.send_next_email(session, sender=fake_email_sender) is True

    assert fake_email_sender.sent == []
    [delivery] = _deliveries(session, event.id)
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.attempts == 1
    assert delivery.last_error is not None and "LookupError" in delivery.last_error


def test_worker_round_trip_creates_and_sends_once(
    session: Session,
    session_factory: Callable[[], Session],
    fake_email_sender: FakeEmailSender,
) -> None:
    alice, bob = make_account(session), make_account(session)
    event = _publish(session, alice, bob)
    session.commit()
    jobs = [dispatch_outbox, make_send_email_job(fake_email_sender)]

    for _ in range(3):
        run_once(jobs, session_factory=session_factory)

    assert sorted(m.to for m in fake_email_sender.sent) == sorted(
        [alice.email, bob.email]
    )
    count = session.exec(
        select(func.count())
        .select_from(Notification)
        .where(Notification.event_id == event.id)
    ).one()
    assert count == 2
