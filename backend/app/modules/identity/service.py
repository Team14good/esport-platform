"""identity 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from pydantic import BaseModel
from sqlmodel import Session

from app.core import audit, clock, events
from app.core.errors import BusinessError, FieldError
from app.core.security import get_password_hash
from app.modules.identity import repository
from app.modules.identity.models import (
    Account,
    AccountToken,
    PublicSchool,
    RegisteredAccount,
    TokenPurpose,
    VerificationEmailRequested,
    normalize_email,
)

FIRST_ADMIN_DISPLAY_NAME = "平台管理員"
VERIFY_EMAIL_TOKEN_TTL = timedelta(hours=24)


class AccountContact(BaseModel):
    """給其他模組（notifications 寄信）使用的帳號聯絡資料。"""

    id: uuid.UUID
    email: str
    display_name: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_first_admin(session: Session, *, email: str, password: str) -> bool:
    """建立第一個平台管理員；同 Email 已存在就略過、不覆寫任何欄位。

    回傳是否新建了帳號。交易由呼叫端（`app.initial_data`）提交。
    """
    email = normalize_email(email)
    if repository.get_account_by_email(session, email) is not None:
        return False
    repository.add_account(
        session,
        Account(
            email=email,
            hashed_password=get_password_hash(password),
            email_verified=True,
            display_name=FIRST_ADMIN_DISPLAY_NAME,
            is_platform_admin=True,
        ),
    )
    return True


def list_schools(session: Session) -> list[PublicSchool]:
    """公開的學校清單，依名稱排序。"""
    return [
        PublicSchool.model_validate(school, from_attributes=True)
        for school in repository.list_schools(session)
    ]


def get_account_contact(
    session: Session, account_id: uuid.UUID
) -> AccountContact | None:
    account = repository.get_account(session, account_id)
    if account is None:
        return None
    return AccountContact.model_validate(account, from_attributes=True)


def _email_already_registered() -> BusinessError:
    return BusinessError(
        "EMAIL_ALREADY_REGISTERED", "這個 Email 已經註冊過。", status_code=409
    )


def _issue_verification_token(
    session: Session, account: Account, *, redirect: str | None
) -> None:
    """作廢舊的驗證 token、產生新的，並發出 VerificationEmailRequested。"""
    repository.delete_unused_tokens(session, account.id, TokenPurpose.VERIFY_EMAIL)
    token = secrets.token_urlsafe(32)
    repository.add_token(
        session,
        AccountToken(
            account_id=account.id,
            purpose=TokenPurpose.VERIFY_EMAIL,
            token_hash=hash_token(token),
            expires_at=clock.now() + VERIFY_EMAIL_TOKEN_TTL,
            created_at=clock.now(),
        ),
    )
    events.publish(
        session,
        VerificationEmailRequested(
            account_id=account.id, token=token, redirect=redirect
        ),
    )


def register(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    school_id: uuid.UUID | None,
    redirect: str | None = None,
) -> RegisteredAccount:
    """以 Email 註冊：帳號、驗證 token 與事件在同一個交易寫入；不自動登入。"""
    email = normalize_email(email)
    if school_id is not None and repository.get_school(session, school_id) is None:
        raise FieldError(
            "SCHOOL_NOT_FOUND", "找不到這間學校", loc=("body", "school_id")
        )
    if repository.get_account_by_email(session, email) is not None:
        raise _email_already_registered()

    account = Account(
        email=email,
        hashed_password=get_password_hash(password),
        email_verified=False,
        display_name=display_name.strip(),
        school_id=school_id,
        created_at=clock.now(),
    )
    try:
        repository.add_account(session, account)
    except repository.DuplicateEmailError:
        # 兩個請求同時註冊同一個 Email：後到的撞到唯一索引
        raise _email_already_registered()

    audit.record(
        session,
        actor_id=account.id,
        tournament_id=None,
        action="account.registered",
        entity_type="account",
        entity_id=account.id,
        before=None,
        after={
            "email": account.email,
            "display_name": account.display_name,
            "school_id": account.school_id,
        },
    )
    _issue_verification_token(session, account, redirect=redirect)
    return RegisteredAccount.model_validate(account, from_attributes=True)


def verify_email(session: Session, *, token: str) -> None:
    """以驗證連結的 token 完成 Email 驗證；token 用過、過期或已作廢都會被拒絕。"""
    record = repository.get_token_by_hash(
        session, hash_token(token), TokenPurpose.VERIFY_EMAIL, for_update=True
    )
    now = clock.now()
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise BusinessError(
            "VERIFICATION_LINK_INVALID", "此驗證連結已失效。", status_code=400
        )
    account = repository.get_account(session, record.account_id)
    assert account is not None  # 外鍵保證帳號存在

    record.used_at = now
    session.add(record)
    if not account.email_verified:
        account.email_verified = True
        session.add(account)
        audit.record(
            session,
            actor_id=account.id,
            tournament_id=None,
            action="account.email_verified",
            entity_type="account",
            entity_id=account.id,
            before={"email_verified": False},
            after={"email_verified": True},
        )
    session.flush()


def is_verification_token_active(session: Session, token: str) -> bool:
    """驗證 token 是否仍可使用：存在（沒被重寄作廢）、沒用過、沒過期，且帳號尚未驗證。

    notifications 寄驗證信前呼叫，避免寄出連結已失效的信。
    """
    record = repository.get_token_by_hash(
        session, hash_token(token), TokenPurpose.VERIFY_EMAIL
    )
    if record is None or record.used_at is not None:
        return False
    if record.expires_at <= clock.now():
        return False
    account = repository.get_account(session, record.account_id)
    return account is not None and not account.email_verified


def resend_verification(
    session: Session, *, email: str, redirect: str | None = None
) -> None:
    """重寄驗證信。不論 Email 是否存在、是否已驗證，呼叫端的回應都相同；
    只有存在且未驗證的帳號會產生新 token 與事件。"""
    account = repository.get_account_by_email(
        session, normalize_email(email), for_update=True
    )
    if account is None or account.email_verified:
        return
    _issue_verification_token(session, account, redirect=redirect)
