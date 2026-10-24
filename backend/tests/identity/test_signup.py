"""Story 1.3：以 Email 註冊、驗證、重寄驗證信（I/O 矩陣的 identity 部分）。"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.events import OutboxEvent
from app.core.security import verify_password
from app.modules.identity import repository, service
from app.modules.identity.models import Account, AccountToken, School, TokenPurpose
from tests.conftest import FrozenClock

API = settings.API_V1_STR
PASSWORD = "eight-ch"


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _register(client: TestClient, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "email": _email(),
        "password": PASSWORD,
        "display_name": "小安",
        "school_id": None,
    }
    body.update(overrides)
    return client.post(f"{API}/accounts", json=body)


def _account(session: Session, email: str) -> Account | None:
    return session.exec(select(Account).where(Account.email == email)).first()


def _tokens(session: Session, account_id: uuid.UUID) -> list[AccountToken]:
    return list(
        session.exec(select(AccountToken).where(AccountToken.account_id == account_id))
    )


def _verification_events(session: Session, account_id: uuid.UUID) -> list[OutboxEvent]:
    return [
        event
        for event in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "VerificationEmailRequested")
        )
        if event.payload["account_id"] == str(account_id)
    ]


def _latest_token(session: Session, account_id: uuid.UUID) -> str:
    """從最新一則 VerificationEmailRequested 取出 token 明文（等同信件裡的連結）。"""
    latest = max(_verification_events(session, account_id), key=lambda e: e.created_at)
    return str(latest.payload["token"])


def _any_school(session: Session) -> School:
    school = session.exec(select(School).order_by(School.name)).first()
    assert school is not None
    return school


def _verify(client: TestClient, token: str) -> Any:
    return client.post(f"{API}/email-verifications", json={"token": token})


def _resend(client: TestClient, email: str) -> Any:
    return client.post(f"{API}/verification-emails", json={"email": email})


# ---------------------------------------------------------------- 註冊


def test_register_creates_unverified_account_token_and_event(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    school = _any_school(session)
    email = _email()

    response = _register(
        client,
        email=f"  {email.upper()} ",
        display_name="  小安  ",
        school_id=str(school.id),
        redirect="/tournaments/abc",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["email_verified"] is False
    assert body["school_id"] == str(school.id)
    assert body["display_name"] == "小安"
    assert "hashed_password" not in body and "password" not in body

    account = _account(session, email)
    assert account is not None
    assert account.email_verified is False
    assert account.school_id == school.id
    assert account.hashed_password != PASSWORD
    assert verify_password(PASSWORD, account.hashed_password)[0] is True

    [token] = _tokens(session, account.id)
    assert token.purpose == TokenPurpose.VERIFY_EMAIL
    assert token.used_at is None
    assert token.expires_at == frozen_clock.now() + timedelta(hours=24)

    [event] = _verification_events(session, account.id)
    assert event.processed_at is None
    assert set(event.payload) == {"account_id", "token", "redirect"}
    assert event.payload["redirect"] == "/tournaments/abc"
    # 資料庫只存雜湊，明文只在事件 payload
    plain = event.payload["token"]
    assert token.token_hash == service.hash_token(plain)
    assert token.token_hash != plain
    assert len(token.token_hash) == 64


def test_register_without_school_stores_null_school(
    client: TestClient, session: Session
) -> None:
    email = _email()

    response = _register(client, email=email)

    assert response.status_code == 201
    account = _account(session, email)
    assert account is not None
    assert account.school_id is None


@pytest.mark.parametrize(
    "variant", [lambda e: e.upper(), lambda e: f"  {e}  ", lambda e: f" {e.title()}"]
)
def test_email_differing_only_in_case_or_whitespace_is_already_registered(
    client: TestClient, session: Session, variant: Any
) -> None:
    email = _email()
    assert _register(client, email=email).status_code == 201

    response = _register(client, email=variant(email))

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "EMAIL_ALREADY_REGISTERED",
            "message": "這個 Email 已經註冊過。",
        }
    }
    count = session.exec(
        select(func.count()).select_from(Account).where(Account.email == email)
    ).one()
    assert count == 1


def test_database_rejects_emails_differing_only_in_case(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    email = _email()
    session.add(Account(email=email, hashed_password="x", display_name="a"))
    session.flush()
    session.add(Account(email=email.upper(), hashed_password="x", display_name="b"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_password_shorter_than_8_is_rejected_on_the_password_field(
    client: TestClient, session: Session
) -> None:
    email = _email()

    response = _register(client, email=email, password="1234567")

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "password"]
    assert error["msg"] == "密碼至少需要 8 個字元"
    assert _account(session, email) is None


def test_password_of_exactly_8_any_characters_is_accepted(client: TestClient) -> None:
    assert _register(client, password="        ").status_code == 201


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("email", "not-an-email", "請輸入有效的 Email"),
        ("display_name", "   ", "請輸入顯示名稱"),
        ("display_name", "名" * 51, "顯示名稱最多 50 個字"),
        ("redirect", "https://evil.example.com", "返回頁面的網址無效"),
        ("redirect", "//evil.example.com", "返回頁面的網址無效"),
        ("redirect", "/\t/evil.com", "返回頁面的網址無效"),
        ("redirect", "/\n/evil.com", "返回頁面的網址無效"),
        ("redirect", "/\\evil.com", "返回頁面的網址無效"),
        ("redirect", "/x\x7f", "返回頁面的網址無效"),
        ("redirect", "/a b", "返回頁面的網址無效"),
    ],
)
def test_invalid_fields_return_422_with_chinese_message(
    client: TestClient, field: str, value: str, message: str
) -> None:
    response = _register(client, **{field: value})

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", field]
    assert error["msg"] == message


def test_display_name_of_50_characters_is_accepted(client: TestClient) -> None:
    assert _register(client, display_name="名" * 50).status_code == 201


def test_unknown_school_returns_school_not_found_on_the_school_field(
    client: TestClient, session: Session
) -> None:
    email = _email()

    response = _register(client, email=email, school_id=str(uuid.uuid4()))

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
    assert _account(session, email) is None


def test_failure_before_commit_leaves_no_account_token_or_event(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _email()
    published: list[object] = []

    def _publish_then_fail(_session: Session, event: object) -> None:
        published.append(event)
        raise RuntimeError("crash before commit")

    monkeypatch.setattr(service.events, "publish", _publish_then_fail)

    with pytest.raises(RuntimeError):
        _register(client, email=email)

    assert published, "failure must happen after the account and token were written"
    assert _account(session, email) is None
    assert session.exec(select(func.count()).select_from(AccountToken)).one() == 0
    assert not [
        e
        for e in session.exec(select(OutboxEvent))
        if e.type == "VerificationEmailRequested"
    ]


def test_duplicate_email_race_is_reported_as_already_registered(
    session: Session,
) -> None:
    # 模擬兩個請求同時通過「Email 是否存在」的檢查：第二筆撞到唯一索引
    email = _email()
    session.add(Account(email=email, hashed_password="x", display_name="先到"))
    session.flush()

    from app.modules.identity import repository

    with pytest.raises(repository.DuplicateEmailError):
        repository.add_account(
            session, Account(email=email, hashed_password="x", display_name="後到")
        )
    # 外層交易仍可繼續使用
    assert _account(session, email) is not None


# ---------------------------------------------------------------- 驗證


def test_verify_within_24_hours_marks_account_verified_and_token_used(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    email = _email()
    _register(client, email=email)
    account = _account(session, email)
    assert account is not None
    token = _latest_token(session, account.id)

    frozen_clock.advance(timedelta(hours=23, minutes=59))
    response = _verify(client, token)

    assert response.status_code == 204
    session.expire_all()
    assert account.email_verified is True
    [record] = _tokens(session, account.id)
    assert record.used_at == frozen_clock.now()


def test_same_link_opened_twice_is_invalid(
    client: TestClient, session: Session
) -> None:
    email = _email()
    _register(client, email=email)
    account = _account(session, email)
    assert account is not None
    token = _latest_token(session, account.id)
    assert _verify(client, token).status_code == 204

    response = _verify(client, token)

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "VERIFICATION_LINK_INVALID",
            "message": "此驗證連結已失效。",
        }
    }


def test_expired_link_is_invalid(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    email = _email()
    _register(client, email=email)
    account = _account(session, email)
    assert account is not None
    token = _latest_token(session, account.id)

    frozen_clock.advance(timedelta(hours=24))
    response = _verify(client, token)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VERIFICATION_LINK_INVALID"
    session.expire_all()
    assert account.email_verified is False


def test_unknown_token_is_invalid(client: TestClient) -> None:
    response = _verify(client, "not-a-real-token")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VERIFICATION_LINK_INVALID"


# ---------------------------------------------------------------- 重寄


def test_resend_issues_new_token_and_invalidates_old_links(
    client: TestClient, session: Session
) -> None:
    email = _email()
    _register(client, email=email)
    account = _account(session, email)
    assert account is not None
    old_token = _latest_token(session, account.id)

    response = client.post(
        f"{API}/verification-emails",
        json={"email": f" {email.upper()} ", "redirect": "/tournaments/x"},
    )

    assert response.status_code == 202
    events = _verification_events(session, account.id)
    assert len(events) == 2
    new_token = _latest_token(session, account.id)
    assert new_token != old_token
    newest = max(events, key=lambda e: e.created_at)
    assert newest.payload["redirect"] == "/tournaments/x"
    [record] = _tokens(session, account.id)
    assert record.token_hash == service.hash_token(new_token)

    assert _verify(client, old_token).json()["detail"]["code"] == (
        "VERIFICATION_LINK_INVALID"
    )
    assert _verify(client, new_token).status_code == 204


def _event_and_token_counts(session: Session) -> tuple[int, int]:
    events = session.exec(select(func.count()).select_from(OutboxEvent)).one()
    tokens = session.exec(select(func.count()).select_from(AccountToken)).one()
    return events, tokens


def test_resend_response_is_identical_for_unknown_verified_and_unverified(
    client: TestClient, session: Session
) -> None:
    unverified = _email()
    _register(client, email=unverified)
    verified = _email()
    _register(client, email=verified)
    account = _account(session, verified)
    assert account is not None
    _verify(client, _latest_token(session, account.id))

    real = _resend(client, unverified)
    before = _event_and_token_counts(session)
    unknown = _resend(client, _email())
    already = _resend(client, verified)

    assert real.status_code == unknown.status_code == already.status_code == 202
    assert real.content == unknown.content == already.content
    assert real.headers.get("content-type") == unknown.headers.get("content-type")
    # 不存在或已驗證的 Email：不產生 token、不發事件
    assert _event_and_token_counts(session) == before


def test_check_then_insert_race_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 第二個請求的「Email 是否存在」檢查在第一個 commit 前就通過了：改由唯一索引擋下
    email = _email()
    assert _register(client, email=email).status_code == 201
    monkeypatch.setattr(repository, "get_account_by_email", lambda *_a, **_k: None)

    response = _register(client, email=email)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"


def _audit_rows(session: Session, account_id: uuid.UUID, action: str) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.entity_id == account_id)
            .where(AuditLog.action == action)
        )
    )


def test_signup_and_verification_write_audit_records(
    client: TestClient, session: Session
) -> None:
    school = _any_school(session)
    email = _email()
    _register(client, email=email, display_name="稽核", school_id=str(school.id))
    account = _account(session, email)
    assert account is not None

    [registered] = _audit_rows(session, account.id, "account.registered")
    assert registered.actor_id == account.id
    assert registered.tournament_id is None
    assert registered.entity_type == "account"
    assert registered.before is None
    assert registered.after == {
        "email": email,
        "display_name": "稽核",
        "school_id": str(school.id),
    }
    assert _audit_rows(session, account.id, "account.email_verified") == []

    assert _verify(client, _latest_token(session, account.id)).status_code == 204

    [verified] = _audit_rows(session, account.id, "account.email_verified")
    assert verified.actor_id == account.id
    assert verified.entity_id == account.id
    assert verified.before == {"email_verified": False}
    assert verified.after == {"email_verified": True}
    assert len(_audit_rows(session, account.id, "account.registered")) == 1
