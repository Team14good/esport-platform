"""Story 1.5：忘記與重設密碼（I/O 矩陣的後端各列）。"""

import uuid
from datetime import timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.config import settings
from app.core.events import OutboxEvent
from app.core.security import ALGORITHM, get_password_hash, verify_password
from app.modules.identity import service
from app.modules.identity.models import Account, AccountToken, TokenPurpose
from tests.conftest import FrozenClock

API = settings.API_V1_STR
OLD_PASSWORD = "old-password"
NEW_PASSWORD = "new-password"
RESET_LINK_INVALID = {
    "detail": {"code": "RESET_LINK_INVALID", "message": "此重設連結已失效。"}
}


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _make_account(session: Session, *, verified: bool = True) -> Account:
    account = Account(
        email=_email(),
        hashed_password=get_password_hash(OLD_PASSWORD),
        email_verified=verified,
        display_name="小安",
    )
    session.add(account)
    session.flush()
    return account


def _request_reset(client: TestClient, email: str) -> Any:
    return client.post(f"{API}/password-reset-emails", json={"email": email})


def _check(client: TestClient, token: str) -> Any:
    return client.post(f"{API}/password-reset-checks", json={"token": token})


def _reset(client: TestClient, token: str, new_password: str = NEW_PASSWORD) -> Any:
    return client.post(
        f"{API}/password-resets",
        json={"token": token, "new_password": new_password},
    )


def _login(client: TestClient, email: str, password: str) -> Any:
    return client.post(
        f"{API}/access-tokens", json={"email": email, "password": password}
    )


def _reset_events(session: Session, account_id: uuid.UUID) -> list[OutboxEvent]:
    return [
        event
        for event in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "PasswordResetRequested")
        )
        if event.payload["account_id"] == str(account_id)
    ]


def _reset_tokens(session: Session, account_id: uuid.UUID) -> list[AccountToken]:
    return list(
        session.exec(
            select(AccountToken)
            .where(AccountToken.account_id == account_id)
            .where(AccountToken.purpose == TokenPurpose.RESET_PASSWORD)
        )
    )


def _latest_token(session: Session, account_id: uuid.UUID) -> str:
    """最新一封重設信的 token 明文（等同信件裡的連結）。

    重新申請會刪掉尚未使用的舊 token，所以還沒用過的那一個就是最新的；凍結時鐘下
    每則事件的 created_at 都相同，不能拿來排序。
    """
    unused = {
        record.token_hash
        for record in _reset_tokens(session, account_id)
        if record.used_at is None
    }
    tokens = [
        str(event.payload["token"])
        for event in _reset_events(session, account_id)
        if service.hash_token(str(event.payload["token"])) in unused
    ]
    assert len(tokens) == 1, tokens
    return tokens[0]


def _issue(client: TestClient, session: Session, account: Account) -> str:
    assert _request_reset(client, account.email).status_code == 202
    return _latest_token(session, account.id)


def _counts(session: Session) -> tuple[int, int]:
    events = session.exec(select(func.count()).select_from(OutboxEvent)).one()
    tokens = session.exec(select(func.count()).select_from(AccountToken)).one()
    return events, tokens


def _audit_rows(session: Session, account_id: uuid.UUID, action: str) -> list[AuditLog]:
    return list(
        session.exec(
            select(AuditLog)
            .where(AuditLog.entity_id == account_id)
            .where(AuditLog.action == action)
        )
    )


# ---------------------------------------------------------------- 申請重設信


@pytest.mark.parametrize(
    "variant", [lambda e: e, lambda e: e.upper(), lambda e: f"  {e.title()} "]
)
def test_request_for_registered_email_creates_token_and_event(
    client: TestClient, session: Session, frozen_clock: FrozenClock, variant: Any
) -> None:
    account = _make_account(session)

    response = _request_reset(client, variant(account.email))

    assert response.status_code == 202
    [token] = _reset_tokens(session, account.id)
    assert token.used_at is None
    assert token.expires_at == frozen_clock.now() + timedelta(hours=1)
    [event] = _reset_events(session, account.id)
    assert set(event.payload) == {"account_id", "token"}
    # 資料庫只存雜湊，明文只在事件 payload
    plain = event.payload["token"]
    assert token.token_hash == service.hash_token(plain)
    assert token.token_hash != plain
    assert len(token.token_hash) == 64


def test_request_response_is_identical_for_registered_and_unknown_email(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)

    registered = _request_reset(client, account.email)
    before = _counts(session)
    unknown = _request_reset(client, _email())

    assert registered.status_code == unknown.status_code == 202
    assert registered.content == unknown.content
    assert registered.headers.get("content-type") == unknown.headers.get("content-type")
    # 未註冊的 Email：不產生 token、不發事件
    assert _counts(session) == before


def test_unverified_account_can_request_a_reset(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, verified=False)

    assert _request_reset(client, account.email).status_code == 202

    assert len(_reset_tokens(session, account.id)) == 1
    assert len(_reset_events(session, account.id)) == 1


@pytest.mark.parametrize("email", ["", "   ", "not-an-email"])
def test_request_with_invalid_email_is_422_on_the_email_field(
    client: TestClient, session: Session, email: str
) -> None:
    before = _counts(session)

    response = _request_reset(client, email)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "email"]
    assert error["msg"] == "請輸入有效的 Email"
    assert _counts(session) == before


def test_requesting_again_invalidates_the_previous_link(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    first = _issue(client, session, account)

    second = _issue(client, session, account)

    assert second != first
    [record] = _reset_tokens(session, account.id)
    assert record.token_hash == service.hash_token(second)
    assert _check(client, first).json() == RESET_LINK_INVALID
    assert _reset(client, first).json() == RESET_LINK_INVALID
    assert _reset(client, second).status_code == 204


def test_request_does_not_touch_the_verification_token(
    client: TestClient, session: Session
) -> None:
    account = service.register(
        session,
        email=_email(),
        password=OLD_PASSWORD,
        display_name="小安",
        school_id=None,
    )

    _request_reset(client, account.email)

    purposes = sorted(
        token.purpose
        for token in session.exec(
            select(AccountToken).where(AccountToken.account_id == account.id)
        )
    )
    assert purposes == [TokenPurpose.RESET_PASSWORD, TokenPurpose.VERIFY_EMAIL]


# ---------------------------------------------------------------- 檢查連結


def test_check_valid_link_is_204_and_does_not_use_the_token(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)

    assert _check(client, token).status_code == 204
    assert _check(client, token).status_code == 204

    session.expire_all()
    [record] = _reset_tokens(session, account.id)
    assert record.used_at is None
    assert _reset(client, token).status_code == 204


def test_link_is_valid_for_exactly_one_hour(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)

    frozen_clock.advance(timedelta(minutes=59, seconds=59))
    assert _check(client, token).status_code == 204

    frozen_clock.advance(timedelta(seconds=1))
    response = _check(client, token)
    assert response.status_code == 400
    assert response.json() == RESET_LINK_INVALID
    assert _reset(client, token).json() == RESET_LINK_INVALID


def test_used_link_is_invalid(client: TestClient, session: Session) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)
    assert _reset(client, token).status_code == 204

    assert _check(client, token).json() == RESET_LINK_INVALID
    response = _reset(client, token, "another-password")
    assert response.status_code == 400
    assert response.json() == RESET_LINK_INVALID
    assert _login(client, account.email, "another-password").status_code == 401


def test_unknown_token_is_invalid(client: TestClient) -> None:
    assert _check(client, "not-a-real-token").json() == RESET_LINK_INVALID
    assert _reset(client, "not-a-real-token").json() == RESET_LINK_INVALID


@pytest.mark.parametrize("body", [{}, {"token": ""}, {"token": "x" * 201}])
def test_missing_or_malformed_token_is_422(
    client: TestClient, body: dict[str, str]
) -> None:
    response = client.post(f"{API}/password-reset-checks", json=body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "token"]


def test_verification_token_cannot_be_used_to_reset(
    client: TestClient, session: Session
) -> None:
    account = service.register(
        session,
        email=_email(),
        password=OLD_PASSWORD,
        display_name="小安",
        school_id=None,
    )
    [event] = [
        e
        for e in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "VerificationEmailRequested")
        )
        if e.payload["account_id"] == str(account.id)
    ]
    verification_token = event.payload["token"]

    assert _check(client, verification_token).json() == RESET_LINK_INVALID
    assert _reset(client, verification_token).json() == RESET_LINK_INVALID


def test_reset_token_cannot_be_used_to_verify_email(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, verified=False)
    token = _issue(client, session, account)

    response = client.post(f"{API}/email-verifications", json={"token": token})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VERIFICATION_LINK_INVALID"


# ---------------------------------------------------------------- 設定新密碼


def test_reset_sets_new_password_and_marks_token_used(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)
    frozen_clock.advance(timedelta(minutes=30))

    response = _reset(client, token)

    assert response.status_code == 204
    assert response.content == b""
    session.expire_all()
    [record] = _reset_tokens(session, account.id)
    assert record.used_at == frozen_clock.now()
    assert verify_password(NEW_PASSWORD, account.hashed_password)[0] is True
    assert account.credentials_version == 1

    old = _login(client, account.email, OLD_PASSWORD)
    assert old.status_code == 401
    assert old.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert _login(client, account.email, NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    ("password", "message"),
    [("1234567", "密碼至少需要 8 個字元"), ("x" * 129, "密碼最多 128 個字元")],
)
def test_invalid_new_password_is_422_and_keeps_the_token(
    client: TestClient, session: Session, password: str, message: str
) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)

    response = _reset(client, token, password)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "new_password"]
    assert error["msg"] == message
    session.expire_all()
    [record] = _reset_tokens(session, account.id)
    assert record.used_at is None
    assert _check(client, token).status_code == 204
    assert _login(client, account.email, OLD_PASSWORD).status_code == 200


@pytest.mark.parametrize("password", ["        ", "x" * 128])
def test_new_password_boundaries_are_accepted(
    client: TestClient, session: Session, password: str
) -> None:
    account = _make_account(session)
    token = _issue(client, session, account)

    assert _reset(client, token, password).status_code == 204
    assert _login(client, account.email, password).status_code == 200


def test_link_invalidated_after_opening_is_rejected_on_submit(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    superseded = _issue(client, session, account)
    assert _check(client, superseded).status_code == 204
    # 開啟 S9 之後又申請了一次：舊連結被作廢
    _issue(client, session, account)
    assert _reset(client, superseded).json() == RESET_LINK_INVALID

    expiring = _latest_token(session, account.id)
    assert _check(client, expiring).status_code == 204
    frozen_clock.advance(timedelta(hours=1))
    assert _reset(client, expiring).json() == RESET_LINK_INVALID
    assert _login(client, account.email, OLD_PASSWORD).status_code == 200


# ---------------------------------------------------------------- 登出其他裝置


def test_tokens_issued_before_reset_are_rejected_and_new_ones_work(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    login = _login(client, account.email, OLD_PASSWORD)
    old_token = login.json()["access_token"]
    me = f"{API}/accounts/me"
    assert client.get(me, headers={"Authorization": f"Bearer {old_token}"}).is_success

    assert _reset(client, _issue(client, session, account)).status_code == 204

    rejected = client.get(me, headers={"Authorization": f"Bearer {old_token}"})
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
    # 重設後同一秒內重新登入拿到的新 token 也可以用
    new_token = _login(client, account.email, NEW_PASSWORD).json()["access_token"]
    accepted = client.get(me, headers={"Authorization": f"Bearer {new_token}"})
    assert accepted.status_code == 200
    assert accepted.json()["id"] == str(account.id)


def test_token_without_ver_claim_works_until_the_first_reset(
    client: TestClient, session: Session
) -> None:
    # Story 1.5 以前簽發的 token 沒有 ver：帳號版本是 0 時照常可用，重設一次後失效
    account = _make_account(session)
    legacy_token = jwt.encode(
        {"sub": str(account.id), "exp": clock.now() + timedelta(days=1)},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    me = f"{API}/accounts/me"
    headers = {"Authorization": f"Bearer {legacy_token}"}
    assert client.get(me, headers=headers).status_code == 200

    assert _reset(client, _issue(client, session, account)).status_code == 204

    rejected = client.get(me, headers=headers)
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_each_reset_bumps_the_credentials_version(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    assert account.credentials_version == 0

    for expected in (1, 2):
        assert _reset(client, _issue(client, session, account)).status_code == 204
        session.expire_all()
        assert account.credentials_version == expected


# ---------------------------------------------------------------- Email 驗證與操作紀錄


def test_reset_marks_unverified_account_as_verified(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session, verified=False)

    assert _reset(client, _issue(client, session, account)).status_code == 204

    session.expire_all()
    assert account.email_verified is True
    [verified] = _audit_rows(session, account.id, "account.email_verified")
    assert verified.actor_id == account.id
    assert verified.tournament_id is None
    assert verified.before == {"email_verified": False}
    assert verified.after == {"email_verified": True}


def test_reset_of_verified_account_writes_no_email_verified_record(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)

    assert _reset(client, _issue(client, session, account)).status_code == 204

    assert _audit_rows(session, account.id, "account.email_verified") == []


def test_reset_writes_audit_record_without_passwords_or_hashes(
    client: TestClient, session: Session
) -> None:
    account = _make_account(session)
    old_hash = account.hashed_password

    assert _reset(client, _issue(client, session, account)).status_code == 204

    session.expire_all()
    [row] = _audit_rows(session, account.id, "account.password_reset")
    assert row.actor_id == account.id
    assert row.tournament_id is None
    assert row.entity_type == "account"
    recorded = repr((row.before, row.after))
    for secret in (OLD_PASSWORD, NEW_PASSWORD, old_hash, account.hashed_password):
        assert secret not in recorded
    assert "password" not in recorded
    assert row.before == {"credentials_version": 0}
    assert row.after == {"credentials_version": 1}


def test_failed_reset_writes_nothing(client: TestClient, session: Session) -> None:
    account = _make_account(session)

    assert _reset(client, "not-a-real-token").status_code == 400
    assert _reset(client, _issue(client, session, account), "short").status_code == 422

    assert _audit_rows(session, account.id, "account.password_reset") == []
    session.expire_all()
    assert account.credentials_version == 0
