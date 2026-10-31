"""Story 1.8：平台管理員審核主辦方申請（I/O 矩陣的後端各列、操作紀錄、事件、分頁、併發）。"""

import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.core.security import create_access_token
from app.modules.identity import service
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
ADMIN_LIST = f"{API}/admin/organizer-applications"
SUBMIT = f"{API}/organizer-applications"
MINE = f"{API}/accounts/me/organizer-application"
NOT_PENDING = {
    "detail": {"code": "APPLICATION_NOT_PENDING", "message": "這筆申請已經審核過了。"}
}
NOT_FOUND = {
    "detail": {"code": "APPLICATION_NOT_FOUND", "message": "找不到這筆主辦方申請。"}
}
ADMIN_REQUIRED = {
    "detail": {
        "code": "PLATFORM_ADMIN_REQUIRED",
        "message": "只有平台管理員可以使用這個功能。",
    }
}
REVIEW_ACTIONS = ("organizer_application.approved", "organizer_application.rejected")
REVIEW_EVENTS = ("OrganizerApplicationApproved", "OrganizerApplicationRejected")


def _make_account(
    session: Session,
    *,
    admin: bool = False,
    organizer: bool = False,
    display_name: str = "小安",
) -> Account:
    account = Account(
        email=f"{uuid.uuid4().hex}@example.com",
        hashed_password="x",
        email_verified=True,
        display_name=display_name,
        is_platform_admin=admin,
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


def _make_application(
    session: Session,
    applicant: Account,
    *,
    status: ApplicationStatus = ApplicationStatus.PENDING,
    created_at: datetime | None = None,
    club_name: str = "電競社",
) -> OrganizerApplication:
    """直接寫入一筆申請（不經 1.7 的送出 API，可以指定狀態與送出時間）。"""
    application = OrganizerApplication(
        account_id=applicant.id,
        club_name=club_name,
        school_id=_school(session).id,
        status=status,
        reject_reason="原因" if status == ApplicationStatus.REJECTED else None,
    )
    if created_at is not None:
        application.created_at = created_at
    session.add(application)
    session.flush()
    return application


def _approve(client: TestClient, admin: Account, application_id: object) -> Any:
    return client.post(
        f"{ADMIN_LIST}/{application_id}/approval", headers=_headers(admin)
    )


def _reject(
    client: TestClient, admin: Account, application_id: object, reason: object
) -> Any:
    return client.post(
        f"{ADMIN_LIST}/{application_id}/rejection",
        json={"reason": reason},
        headers=_headers(admin),
    )


def _review_audits(session: Session, entity_id: uuid.UUID) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.entity_id == entity_id)
            .where(col(AuditLog.action).in_(REVIEW_ACTIONS))
        )
    )


def _review_events(session: Session, application_id: uuid.UUID) -> list[OutboxEvent]:
    return [
        event
        for event in session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type).in_(REVIEW_EVENTS))
        )
        if event.payload.get("application_id") == str(application_id)
    ]


def _snapshot(session: Session, application: OrganizerApplication) -> tuple[Any, ...]:
    """審核相關資料的快照：用來確認失敗的請求沒有改任何資料。"""
    session.expire_all()
    stored = session.get(OrganizerApplication, application.id)
    applicant = session.get(Account, application.account_id)
    assert stored is not None
    assert applicant is not None
    return (
        stored.status,
        stored.reject_reason,
        applicant.is_organizer,
        len(_review_audits(session, application.id)),
        len(_review_events(session, application.id)),
    )


# ---------------------------------------------------------------- 列表、篩選與分頁


def test_list_returns_pending_oldest_first_with_applicant(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    first = _make_account(session, display_name="阿明")
    second = _make_account(session, display_name="小華")
    now = frozen_clock.now()
    newer = _make_application(session, second, created_at=now, club_name="清大電競")
    older = _make_application(
        session, first, created_at=now - timedelta(hours=1), club_name="臺大電競"
    )
    _make_application(
        session,
        _make_account(session),
        status=ApplicationStatus.APPROVED,
        created_at=now - timedelta(days=1),
    )

    response = client.get(
        ADMIN_LIST, params={"status": "pending"}, headers=_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["id"] for item in body["items"]] == [str(older.id), str(newer.id)]
    school = _school(session)
    assert body["items"][0] == {
        "id": str(older.id),
        "club_name": "臺大電競",
        "school_id": str(school.id),
        "school_name": school.name,
        "status": "pending",
        "reject_reason": None,
        "created_at": body["items"][0]["created_at"],
        "applicant_display_name": "阿明",
        "applicant_email": first.email,
    }
    assert datetime.fromisoformat(body["items"][0]["created_at"]) == older.created_at


def test_status_filter_and_all(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    now = frozen_clock.now()
    ids: dict[ApplicationStatus, str] = {}
    for offset, status in enumerate(ApplicationStatus):
        application = _make_application(
            session,
            _make_account(session),
            status=status,
            created_at=now + timedelta(minutes=offset),
        )
        ids[status] = str(application.id)

    for status in ApplicationStatus:
        body = client.get(
            ADMIN_LIST, params={"status": status.value}, headers=_headers(admin)
        ).json()
        assert [item["id"] for item in body["items"]] == [ids[status]]
        assert body["total"] == 1

    # 省略 status 表示全部
    body = client.get(ADMIN_LIST, headers=_headers(admin)).json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [
        ids[status] for status in ApplicationStatus
    ]
    assert body["items"][2]["reject_reason"] == "原因"


def test_pagination_is_20_per_page_and_beyond_last_page_is_empty(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    now = frozen_clock.now()
    created = [
        _make_application(
            session, _make_account(session), created_at=now + timedelta(minutes=i)
        )
        for i in range(21)
    ]

    def _page(page: int) -> Any:
        return client.get(
            ADMIN_LIST,
            params={"status": "pending", "page": page},
            headers=_headers(admin),
        )

    first = _page(1).json()
    assert len(first["items"]) == 20
    assert first["total"] == 21
    second = _page(2).json()
    assert [item["id"] for item in second["items"]] == [str(created[20].id)]
    assert second["page"] == 2
    beyond = _page(3).json()
    assert beyond == {"items": [], "total": 21, "page": 3, "page_size": 20}


@pytest.mark.parametrize("page", ["0", "-1", "abc"])
def test_invalid_page_is_422(client: TestClient, session: Session, page: str) -> None:
    admin = _make_account(session, admin=True)

    response = client.get(ADMIN_LIST, params={"page": page}, headers=_headers(admin))

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["query", "page"]


def test_invalid_status_filter_is_422(client: TestClient, session: Session) -> None:
    admin = _make_account(session, admin=True)

    response = client.get(
        ADMIN_LIST, params={"status": "deleted"}, headers=_headers(admin)
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "status"]


# ---------------------------------------------------------------- 權限


def test_non_admin_gets_403_on_every_review_endpoint(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, organizer=True)
    application = _make_application(session, _make_account(session))
    before = _snapshot(session, application)

    responses = [
        client.get(ADMIN_LIST, headers=_headers(account)),
        _approve(client, account, application.id),
        _reject(client, account, application.id, "不符資格"),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json() == ADMIN_REQUIRED
    assert _snapshot(session, application) == before


def test_list_without_token_is_401(client: TestClient) -> None:
    response = client.get(ADMIN_LIST)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


# ---------------------------------------------------------------- 核准


def test_approve_makes_applicant_organizer_with_audit_and_event(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    applicant = _make_account(session, display_name="阿明")
    application = _make_application(session, applicant)

    response = _approve(client, admin, application.id)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(application.id)
    assert body["status"] == "approved"
    assert body["reject_reason"] is None
    assert body["applicant_display_name"] == "阿明"
    assert body["applicant_email"] == applicant.email

    session.expire_all()
    stored = session.get(OrganizerApplication, application.id)
    assert stored is not None
    assert stored.status == ApplicationStatus.APPROVED
    reloaded = session.get(Account, applicant.id)
    assert reloaded is not None
    assert reloaded.is_organizer is True

    [audit] = _review_audits(session, application.id)
    assert audit.action == "organizer_application.approved"
    assert audit.actor_id == admin.id
    assert audit.tournament_id is None
    assert audit.entity_type == "organizer_application"
    assert audit.before == {"status": "pending"}
    assert audit.after == {
        "status": "approved",
        "reject_reason": None,
        "account_id": str(applicant.id),
        "is_organizer": True,
    }
    assert audit.at == frozen_clock.now()

    [event] = _review_events(session, application.id)
    assert event.type == "OrganizerApplicationApproved"
    # 事件只帶 application_id，不帶收件人
    assert event.payload == {"application_id": str(application.id)}
    assert event.processed_at is None


def test_approved_applicant_is_organizer_immediately(
    client: TestClient, session: Session
) -> None:
    admin = _make_account(session, admin=True)
    applicant = _make_account(session)
    application = _make_application(session, applicant)
    assert _approve(client, admin, application.id).status_code == 200

    me = client.get(f"{API}/accounts/me", headers=_headers(applicant)).json()
    assert me["is_organizer"] is True
    identities = client.get(
        f"{API}/accounts/me/identities", headers=_headers(applicant)
    ).json()
    assert identities == [
        {"key": "browse", "label": "瀏覽賽事", "home_path": "/"},
        {"key": "organizer", "label": "主辦方後台", "home_path": "/organizer"},
    ]
    mine = client.get(MINE, headers=_headers(applicant)).json()
    assert mine["status"] == "approved"
    # 需要「是主辦方」的檢查立即生效：不能再申請
    again = client.post(
        SUBMIT,
        json={"club_name": "電競社", "school_id": str(_school(session).id)},
        headers=_headers(applicant),
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ALREADY_ORGANIZER"


# ---------------------------------------------------------------- 退回與重送


def test_reject_records_trimmed_reason_with_audit_and_event(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    applicant = _make_account(session)
    application = _make_application(session, applicant)

    response = _reject(client, admin, application.id, "  請附上社團名稱全名  ")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "請附上社團名稱全名"

    session.expire_all()
    reloaded = session.get(Account, applicant.id)
    assert reloaded is not None
    assert reloaded.is_organizer is False

    [audit] = _review_audits(session, application.id)
    assert audit.action == "organizer_application.rejected"
    assert audit.actor_id == admin.id
    assert audit.before == {"status": "pending"}
    assert audit.after == {"status": "rejected", "reject_reason": "請附上社團名稱全名"}
    assert audit.at == frozen_clock.now()

    [event] = _review_events(session, application.id)
    assert event.type == "OrganizerApplicationRejected"
    assert event.payload == {"application_id": str(application.id)}

    mine = client.get(MINE, headers=_headers(applicant)).json()
    assert mine["status"] == "rejected"
    assert mine["reject_reason"] == "請附上社團名稱全名"


def test_resubmit_after_rejection_creates_new_pending_and_keeps_old(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    admin = _make_account(session, admin=True)
    applicant = _make_account(session)
    first = client.post(
        SUBMIT,
        json={"club_name": "電競社", "school_id": str(_school(session).id)},
        headers=_headers(applicant),
    ).json()
    assert _reject(client, admin, first["id"], "名稱不完整").status_code == 200
    frozen_clock.advance(timedelta(minutes=5))

    resubmitted = client.post(
        SUBMIT,
        json={"club_name": "政大電競社", "school_id": str(_school(session, 1).id)},
        headers=_headers(applicant),
    )

    assert resubmitted.status_code == 201
    mine = client.get(MINE, headers=_headers(applicant)).json()
    assert mine["id"] == resubmitted.json()["id"]
    assert mine["status"] == "pending"
    rows = list(
        session.exec(
            select(OrganizerApplication)
            .where(OrganizerApplication.account_id == applicant.id)
            .order_by(col(OrganizerApplication.created_at))
        )
    )
    assert [(row.status, row.reject_reason) for row in rows] == [
        (ApplicationStatus.REJECTED, "名稱不完整"),
        (ApplicationStatus.PENDING, None),
    ]


def test_reject_reason_of_200_characters_is_accepted(
    client: TestClient, session: Session
) -> None:
    admin = _make_account(session, admin=True)
    application = _make_application(session, _make_account(session))

    response = _reject(client, admin, application.id, "因" * 200)

    assert response.status_code == 200
    assert response.json()["reject_reason"] == "因" * 200


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        ("", "請輸入退回原因"),
        ("   ", "請輸入退回原因"),
        ("因" * 201, "退回原因最多 200 個字"),
        (123, "請輸入文字"),
        (None, "請輸入文字"),
    ],
)
def test_invalid_reject_reason_is_422_and_changes_nothing(
    client: TestClient, session: Session, reason: object, message: str
) -> None:
    admin = _make_account(session, admin=True)
    application = _make_application(session, _make_account(session))
    before = _snapshot(session, application)

    response = _reject(client, admin, application.id, reason)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "reason"]
    assert error["msg"] == message
    assert _snapshot(session, application) == before


# ---------------------------------------------------------------- 重複審核與不存在


@pytest.mark.parametrize(
    "status", [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]
)
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_reviewing_a_reviewed_application_is_409_and_changes_nothing(
    client: TestClient, session: Session, status: ApplicationStatus, action: str
) -> None:
    admin = _make_account(session, admin=True)
    application = _make_application(session, _make_account(session), status=status)
    before = _snapshot(session, application)

    if action == "approve":
        response = _approve(client, admin, application.id)
    else:
        response = _reject(client, admin, application.id, "再退一次")

    assert response.status_code == 409
    assert response.json() == NOT_PENDING
    assert _snapshot(session, application) == before


def test_second_approval_is_409(client: TestClient, session: Session) -> None:
    admin = _make_account(session, admin=True)
    application = _make_application(session, _make_account(session))
    assert _approve(client, admin, application.id).status_code == 200

    response = _approve(client, admin, application.id)

    assert response.status_code == 409
    assert response.json() == NOT_PENDING
    assert len(_review_audits(session, application.id)) == 1
    assert len(_review_events(session, application.id)) == 1


def test_unknown_application_is_404(client: TestClient, session: Session) -> None:
    admin = _make_account(session, admin=True)

    for response in (
        _approve(client, admin, uuid.uuid4()),
        _reject(client, admin, uuid.uuid4(), "不符資格"),
    ):
        assert response.status_code == 404
        assert response.json() == NOT_FOUND


def test_malformed_application_id_is_422(client: TestClient, session: Session) -> None:
    admin = _make_account(session, admin=True)

    response = _approve(client, admin, "not-a-uuid")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "application_id"]


def test_transition_only_allows_reviewed_targets(session: Session) -> None:
    application = _make_application(session, _make_account(session))

    with pytest.raises(ValueError):
        service._transition_application(application, ApplicationStatus.PENDING)
    assert application.status == ApplicationStatus.PENDING


# ---------------------------------------------------------------- 身分清單


def test_identities_order_is_browse_organizer_platform_admin(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, admin=True, organizer=True)

    response = client.get(f"{API}/accounts/me/identities", headers=_headers(account))

    assert [identity["key"] for identity in response.json()] == [
        "browse",
        "organizer",
        "platform_admin",
    ]


# ---------------------------------------------------------------- worker


def test_worker_marks_review_events_processed_without_sending_email(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    fake_email_sender: FakeEmailSender,
) -> None:
    admin = _make_account(session, admin=True)
    approved = _make_application(session, _make_account(session))
    rejected = _make_application(session, _make_account(session))
    assert _approve(client, admin, approved.id).status_code == 200
    assert _reject(client, admin, rejected.id, "不符資格").status_code == 200

    run_once(
        [dispatch_outbox, make_send_email_job(fake_email_sender)],
        session_factory=session_factory,
    )
    run_once(
        [dispatch_outbox, make_send_email_job(fake_email_sender)],
        session_factory=session_factory,
    )

    events = _review_events(session, approved.id) + _review_events(session, rejected.id)
    assert len(events) == 2
    for event in events:
        session.refresh(event)
        assert event.processed_at is not None
    assert fake_email_sender.sent == []
    assert list(session.exec(select(EmailDelivery))) == []


# ---------------------------------------------------------------- 同時審核


def test_concurrent_approve_and_reject_only_one_succeeds() -> None:
    """兩個真正的交易同時審核同一筆：核准先鎖住申請，退回要等它提交，之後看到已審核。

    這個測試需要真正提交的資料（另一條連線才看得到），結束時刪掉申請、申請人與事件；
    審核者帳號被只增不改的操作紀錄參照，留在測試資料庫（不是管理員，不影響其他測試）。
    """
    with Session(engine) as setup:
        school = _school(setup)
        reviewer = Account(
            email=f"{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            display_name="審核者",
        )
        applicant = Account(
            email=f"{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            display_name="申請人",
        )
        setup.add_all([reviewer, applicant])
        setup.flush()
        application = OrganizerApplication(
            account_id=applicant.id, club_name="電競社", school_id=school.id
        )
        setup.add(application)
        setup.commit()
        reviewer_id, applicant_id, application_id = (
            reviewer.id,
            applicant.id,
            application.id,
        )

    approval_locked = threading.Event()
    release_approval = threading.Event()
    outcome: dict[str, str] = {}

    def _approve_and_hold() -> None:
        with Session(engine) as db:
            service.approve_organizer_application(
                db, admin_id=reviewer_id, application_id=application_id
            )
            approval_locked.set()
            release_approval.wait(timeout=10)
            db.commit()
        outcome["approve"] = "ok"

    def _reject() -> None:
        with Session(engine) as db:
            try:
                service.reject_organizer_application(
                    db,
                    admin_id=reviewer_id,
                    application_id=application_id,
                    reason="同時退回",
                )
                db.commit()
                outcome["reject"] = "ok"
            except BusinessError as exc:
                outcome["reject"] = exc.code

    approver = threading.Thread(target=_approve_and_hold)
    rejecter = threading.Thread(target=_reject)
    try:
        approver.start()
        assert approval_locked.wait(timeout=10)
        rejecter.start()
        rejecter.join(timeout=0.5)
        # 退回卡在申請的列鎖上，等核准的交易結束
        assert rejecter.is_alive()
        release_approval.set()
        approver.join(timeout=10)
        rejecter.join(timeout=10)

        assert outcome == {"approve": "ok", "reject": "APPLICATION_NOT_PENDING"}
        with Session(engine) as check:
            stored = check.get(OrganizerApplication, application_id)
            stored_applicant = check.get(Account, applicant_id)
            assert stored is not None
            assert stored_applicant is not None
            assert stored.status == ApplicationStatus.APPROVED
            assert stored.reject_reason is None
            assert stored_applicant.is_organizer is True
            assert len(_review_audits(check, application_id)) == 1
            assert len(_review_events(check, application_id)) == 1
    finally:
        release_approval.set()
        approver.join(timeout=10)
        rejecter.join(timeout=10)
        with Session(engine) as cleanup:
            for event in _review_events(cleanup, application_id):
                cleanup.delete(event)
            cleanup.execute(
                delete(OrganizerApplication).where(
                    col(OrganizerApplication.id) == application_id
                )
            )
            cleanup.execute(delete(Account).where(col(Account.id) == applicant_id))
            cleanup.commit()
