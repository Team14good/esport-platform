"""Story 1.7：申請成為主辦方（I/O 矩陣的後端各列、操作紀錄、事件、部分唯一索引）。"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.events import OutboxEvent
from app.core.security import create_access_token
from app.modules.identity import repository, service
from app.modules.identity.models import (
    Account,
    ApplicationStatus,
    OrganizerApplication,
    School,
)
from app.modules.notifications.models import EmailDelivery
from app.worker import run_once
from app.worker.jobs import dispatch_outbox, make_send_email_job
from tests.conftest import FakeEmailSender, FrozenClock

API = settings.API_V1_STR
SUBMIT = f"{API}/organizer-applications"
MINE = f"{API}/accounts/me/organizer-application"
APPLICATION_PENDING = {
    "detail": {
        "code": "APPLICATION_PENDING",
        "message": "你已有一筆待審核的主辦方申請。",
    }
}


def _make_account(
    session: Session, *, verified: bool = True, organizer: bool = False
) -> Account:
    account = Account(
        email=f"{uuid.uuid4().hex}@example.com",
        hashed_password="x",
        email_verified=verified,
        display_name="小安",
        is_organizer=organizer,
    )
    session.add(account)
    session.flush()
    return account


def _headers(account: Account) -> dict[str, str]:
    token = create_access_token(
        account.id, timedelta(days=1), version=account.credentials_version
    )
    return {"Authorization": f"Bearer {token}"}


def _school(session: Session, index: int = 0) -> School:
    return list(session.exec(select(School).order_by(School.name).limit(index + 1)))[
        index
    ]


def _submit(
    client: TestClient, account: Account, school: School, **overrides: Any
) -> Any:
    body: dict[str, Any] = {"club_name": "電競社", "school_id": str(school.id)}
    body.update(overrides)
    return client.post(SUBMIT, json=body, headers=_headers(account))


def _applications(
    session: Session, account_id: uuid.UUID
) -> list[OrganizerApplication]:
    return list(
        session.exec(
            select(OrganizerApplication).where(
                OrganizerApplication.account_id == account_id
            )
        )
    )


def _audit_rows(session: Session, entity_id: uuid.UUID) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.entity_id == entity_id)
            .where(AuditLog.action == "organizer_application.submitted")
        )
    )


def _submitted_events(session: Session) -> list[OutboxEvent]:
    return list(
        session.exec(
            select(OutboxEvent).where(
                OutboxEvent.type == "OrganizerApplicationSubmitted"
            )
        )
    )


def _counts(session: Session) -> tuple[int, int, int]:
    applications = session.exec(
        select(func.count()).select_from(OrganizerApplication)
    ).one()
    audits = session.exec(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "organizer_application.submitted")
    ).one()
    return applications, audits, len(_submitted_events(session))


# ---------------------------------------------------------------- 送出申請


def test_submit_creates_pending_application_audit_record_and_event(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    school = _school(session)

    response = _submit(client, account, school, club_name="  政大電競社  ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "club_name",
        "school_id",
        "school_name",
        "status",
        "reject_reason",
        "created_at",
    }
    assert body["club_name"] == "政大電競社"
    assert body["school_id"] == str(school.id)
    assert body["school_name"] == school.name
    assert body["status"] == "pending"
    assert body["reject_reason"] is None
    assert datetime.fromisoformat(body["created_at"]) == frozen_clock.now()

    [application] = _applications(session, account.id)
    assert str(application.id) == body["id"]
    assert application.status == ApplicationStatus.PENDING
    assert application.club_name == "政大電競社"
    assert application.school_id == school.id

    [audit] = _audit_rows(session, application.id)
    assert audit.actor_id == account.id
    assert audit.tournament_id is None
    assert audit.entity_type == "organizer_application"
    assert audit.before is None
    assert audit.after == {
        "club_name": "政大電競社",
        "school_id": str(school.id),
        "status": "pending",
    }
    assert audit.at == frozen_clock.now()

    [event] = _submitted_events(session)
    # 事件只帶 application_id，不帶收件人
    assert event.payload == {"application_id": str(application.id)}
    assert event.processed_at is None


def test_club_name_of_50_characters_is_accepted(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)

    response = _submit(client, account, _school(session), club_name="社" * 50)

    assert response.status_code == 201
    assert response.json()["club_name"] == "社" * 50


def test_second_submit_while_pending_is_409_and_adds_nothing(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    assert _submit(client, account, _school(session)).status_code == 201
    before = _counts(session)

    response = _submit(client, account, _school(session, 1), club_name="另一個社團")

    assert response.status_code == 409
    assert response.json() == APPLICATION_PENDING
    assert _counts(session) == before


def test_organizer_cannot_apply_again(client: TestClient, session: Session) -> None:
    account = _make_account(session, organizer=True)
    before = _counts(session)

    response = _submit(client, account, _school(session))

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "ALREADY_ORGANIZER", "message": "你已經是主辦方。"}
    }
    assert _counts(session) == before


def test_unverified_account_gets_403_and_adds_nothing(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, verified=False)
    before = _counts(session)

    response = _submit(client, account, _school(session))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
    assert _counts(session) == before


def test_submit_without_token_is_401(client: TestClient, session: Session) -> None:
    response = client.post(
        SUBMIT, json={"club_name": "電競社", "school_id": str(_school(session).id)}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("club_name", "   ", "請輸入社團名稱"),
        ("club_name", "", "請輸入社團名稱"),
        ("club_name", "社" * 51, "社團名稱最多 50 個字"),
        ("club_name", 123, "請輸入文字"),
        ("school_id", None, "請選擇學校"),
        ("school_id", "", "請選擇學校"),
        ("school_id", "not-a-uuid", "找不到這間學校"),
    ],
)
def test_invalid_fields_return_422_on_the_field(
    client: TestClient, session: Session, field: str, value: object, message: str
) -> None:
    account = _make_account(session)
    before = _counts(session)

    response = _submit(client, account, _school(session), **{field: value})

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", field]
    assert error["msg"] == message
    assert _counts(session) == before


def test_unknown_school_returns_school_not_found_on_the_school_field(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    before = _counts(session)

    response = _submit(client, account, _school(session), school_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "SCHOOL_NOT_FOUND",
                "loc": ["body", "school_id"],
                "msg": "找不到這間學校",
            }
        ]
    }
    assert _counts(session) == before


def test_can_submit_again_after_rejection(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    assert _submit(client, account, _school(session)).status_code == 201
    # 模擬 Story 1.8 的退回
    [old] = _applications(session, account.id)
    old.status = ApplicationStatus.REJECTED
    old.reject_reason = "請附上社團名稱全名"
    session.add(old)
    session.flush()
    frozen_clock.advance(timedelta(minutes=5))

    response = _submit(client, account, _school(session, 1), club_name="新社團")

    assert response.status_code == 201
    assert len(_applications(session, account.id)) == 2
    latest = client.get(MINE, headers=_headers(account)).json()
    assert latest["id"] == response.json()["id"]
    assert latest["status"] == "pending"
    assert latest["club_name"] == "新社團"


# ---------------------------------------------------------------- 待審核只能一筆的保底


def test_partial_unique_index_rejects_second_pending_application(
    session: Session,
) -> None:
    account = _make_account(session)
    school = _school(session)
    repository.add_organizer_application(
        session,
        OrganizerApplication(account_id=account.id, club_name="A", school_id=school.id),
    )

    with pytest.raises(repository.DuplicatePendingApplicationError):
        repository.add_organizer_application(
            session,
            OrganizerApplication(
                account_id=account.id, club_name="B", school_id=school.id
            ),
        )
    # 外層交易仍可繼續使用，且非待審核的申請不受索引限制
    repository.add_organizer_application(
        session,
        OrganizerApplication(
            account_id=account.id,
            club_name="C",
            school_id=school.id,
            status=ApplicationStatus.REJECTED,
        ),
    )
    assert len(_applications(session, account.id)) == 2


def test_race_past_the_pending_check_is_reported_as_application_pending(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 模擬檢查時還沒有待審核、新增時才撞到部分唯一索引
    account = _make_account(session)
    assert _submit(client, account, _school(session)).status_code == 201
    before = _counts(session)
    monkeypatch.setattr(repository, "get_pending_application", lambda *_: None)

    response = _submit(client, account, _school(session))

    assert response.status_code == 409
    assert response.json() == APPLICATION_PENDING
    assert _counts(session) == before


# ---------------------------------------------------------------- 查詢自己的申請


def test_my_application_is_null_before_applying(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)

    response = client.get(MINE, headers=_headers(account))

    assert response.status_code == 200
    assert response.json() is None


def test_my_application_returns_the_submitted_summary(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    submitted = _submit(client, account, _school(session)).json()

    response = client.get(MINE, headers=_headers(account))

    assert response.status_code == 200
    assert response.json() == submitted


def test_unverified_account_can_read_its_application(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, verified=False)

    response = client.get(MINE, headers=_headers(account))

    assert response.status_code == 200
    assert response.json() is None


def test_my_application_only_shows_my_own(client: TestClient, session: Session) -> None:
    applicant = _make_account(session)
    other = _make_account(session)
    assert _submit(client, applicant, _school(session)).status_code == 201

    assert client.get(MINE, headers=_headers(other)).json() is None


def test_my_application_without_token_is_401(client: TestClient) -> None:
    response = client.get(MINE)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_service_returns_none_for_account_without_application(
    session: Session,
) -> None:
    account = _make_account(session)

    assert service.get_my_organizer_application(session, account.id) is None


# ---------------------------------------------------------------- worker


def test_worker_marks_event_processed_without_sending_email(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    fake_email_sender: FakeEmailSender,
) -> None:
    account = _make_account(session)
    assert _submit(client, account, _school(session)).status_code == 201

    run_once(
        [dispatch_outbox, make_send_email_job(fake_email_sender)],
        session_factory=session_factory,
    )

    [event] = _submitted_events(session)
    session.refresh(event)
    assert event.processed_at is not None
    assert fake_email_sender.sent == []
    assert list(session.exec(select(EmailDelivery))) == []
