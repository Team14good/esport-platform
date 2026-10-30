"""identity 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid

from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.modules.identity.models import (
    PENDING_APPLICATION_INDEX,
    Account,
    AccountToken,
    ApplicationStatus,
    OrganizerApplication,
    School,
    TokenPurpose,
)


class DuplicateEmailError(Exception):
    """新增帳號時撞到 lower(email) 唯一索引（同時註冊的競態）。"""


class DuplicatePendingApplicationError(Exception):
    """新增主辦方申請時撞到「每帳號一筆待審核」的部分唯一索引（同時送出的競態）。"""


def get_account(
    session: Session, account_id: uuid.UUID, *, for_update: bool = False
) -> Account | None:
    # for_update 時重新查詢並加鎖，並以資料庫的最新值覆蓋 identity map 裡已載入的同一筆
    return session.get(
        Account,
        account_id,
        with_for_update=for_update or None,
        populate_existing=for_update,
    )


def get_account_by_email(
    session: Session, email: str, *, for_update: bool = False
) -> Account | None:
    """以正規化後的 Email 查詢（走 lower(email) 唯一索引）。"""
    statement = select(Account).where(func.lower(Account.email) == email)
    if for_update:
        statement = statement.with_for_update()
    return session.exec(statement).first()


def add_account(session: Session, account: Account) -> Account:
    """新增帳號；Email 已存在時拋 DuplicateEmailError，外層交易不受影響。"""
    try:
        with session.begin_nested():
            session.add(account)
    except IntegrityError as exc:
        if "ix_account_lower_email" in str(exc.orig):
            raise DuplicateEmailError from exc
        raise
    return account


def get_school(session: Session, school_id: uuid.UUID) -> School | None:
    return session.get(School, school_id)


def list_schools(session: Session) -> list[School]:
    # 以 "C" 定序（逐碼位比較）排序，結果不受資料庫 locale 影響
    return list(session.exec(select(School).order_by(col(School.name).collate("C"))))


def add_token(session: Session, token: AccountToken) -> AccountToken:
    session.add(token)
    session.flush()
    return token


def get_token_by_hash(
    session: Session,
    token_hash: str,
    purpose: TokenPurpose,
    *,
    for_update: bool = False,
) -> AccountToken | None:
    statement = (
        select(AccountToken)
        .where(AccountToken.token_hash == token_hash)
        .where(AccountToken.purpose == purpose)
    )
    if for_update:
        # 加鎖後以資料庫的最新值覆蓋 identity map 裡已載入的同一筆
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()


def delete_unused_tokens(
    session: Session, account_id: uuid.UUID, purpose: TokenPurpose
) -> None:
    """作廢同帳號、同用途尚未使用的 token（重新產生時呼叫）。"""
    session.connection().execute(
        delete(AccountToken)
        .where(col(AccountToken.account_id) == account_id)
        .where(col(AccountToken.purpose) == purpose)
        .where(col(AccountToken.used_at).is_(None))
    )


def get_pending_application(
    session: Session, account_id: uuid.UUID
) -> OrganizerApplication | None:
    return session.exec(
        select(OrganizerApplication)
        .where(OrganizerApplication.account_id == account_id)
        .where(OrganizerApplication.status == ApplicationStatus.PENDING)
    ).first()


def get_latest_application(
    session: Session, account_id: uuid.UUID
) -> OrganizerApplication | None:
    """帳號最新（created_at 最晚）的一筆主辦方申請。"""
    return session.exec(
        select(OrganizerApplication)
        .where(OrganizerApplication.account_id == account_id)
        .order_by(
            col(OrganizerApplication.created_at).desc(),
            col(OrganizerApplication.id).desc(),
        )
        .limit(1)
    ).first()


def add_organizer_application(
    session: Session, application: OrganizerApplication
) -> OrganizerApplication:
    """新增主辦方申請；已有待審核申請時拋 DuplicatePendingApplicationError，外層交易不受影響。"""
    try:
        with session.begin_nested():
            session.add(application)
    except IntegrityError as exc:
        if PENDING_APPLICATION_INDEX in str(exc.orig):
            raise DuplicatePendingApplicationError from exc
        raise
    return application
