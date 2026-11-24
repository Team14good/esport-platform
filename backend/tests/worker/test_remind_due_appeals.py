"""Story 6.3：worker 對快到處理期限的申訴提醒主辦方，同一筆只提醒一次。

各種情境的測試在 tests/disputes/test_appeal_reminder.py；這裡確認工作已註冊，並經
`run_once` 走兩輪真正的 worker 迴圈（提醒、分派、寄信），主辦方只收到一則站內通知與一封 Email。
"""

# ruff: noqa: F811  (從 test_score_entry 匯入 fixture，參數同名是 pytest 的用法)

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.modules.notifications.models import EmailDelivery, Notification
from app.worker import run_once
from app.worker.jobs import (
    JOBS,
    dispatch_outbox,
    make_send_email_job,
    remind_due_appeals,
)
from tests.competition.conftest import (  # noqa: F401
    FakeRegistration,
    fake_registration,
)
from tests.competition.test_score_entry import (  # noqa: F401
    Factory,
    Setup,
    make_setup,
    setup,
)
from tests.conftest import FakeEmailSender, FrozenClock
from tests.disputes.test_resolve_appeals import (
    _appealed,
    _seat,
    _set_time,
    _third_place_code,
)

FINAL_AT = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


def test_remind_due_appeals_runs_before_dispatch_outbox() -> None:
    names = [getattr(job, "__name__", "") for job in JOBS]

    assert names.index("confirm_expired_appeals") < names.index("remind_due_appeals")
    assert names.index("remind_due_appeals") < names.index("dispatch_outbox")


def test_job_returns_false_when_nothing_is_due(session: Session) -> None:
    assert remind_due_appeals(session) is False


def test_two_rounds_notify_organizer_once_in_app_and_by_email(
    session: Session,
    session_factory: Callable[[], Session],
    setup: Setup,
    frozen_clock: FrozenClock,
    fake_email_sender: FakeEmailSender,
) -> None:
    semi = setup.next_code("M1")
    _seat(session, setup, semi)
    frozen_clock.set(FINAL_AT - timedelta(hours=3))
    _appealed(session, setup, code=semi, teams="a")
    _set_time(session, setup, setup.next_code(semi), FINAL_AT)
    _set_time(session, setup, _third_place_code(setup), FINAL_AT + timedelta(hours=1))
    jobs = [remind_due_appeals, dispatch_outbox, make_send_email_job(fake_email_sender)]

    frozen_clock.set(FINAL_AT - timedelta(hours=1))
    run_once(jobs, session_factory=session_factory)
    frozen_clock.advance(timedelta(seconds=30))
    run_once(jobs, session_factory=session_factory)
    session.expire_all()

    notifications = session.exec(
        select(Notification).where(Notification.type == "AppealReminded")
    ).all()
    assert [(n.account_id, n.link) for n in notifications] == [
        (
            setup.organizer.id,
            f"/organizer/tournaments/{setup.tournament_id}/appeals",
        )
    ]
    deliveries = session.exec(
        select(EmailDelivery).where(EmailDelivery.account_id == setup.organizer.id)
    ).all()
    assert len(deliveries) == 1
    assert [(m.to, m.subject) for m in fake_email_sender.sent] == [
        (setup.organizer.email, "申訴待處理")
    ]
