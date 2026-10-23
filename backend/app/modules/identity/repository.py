"""identity 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

from sqlmodel import Session, select

from app.modules.identity.models import Account


def get_account_by_email(session: Session, email: str) -> Account | None:
    return session.exec(select(Account).where(Account.email == email)).first()


def add_account(session: Session, account: Account) -> Account:
    session.add(account)
    session.flush()
    return account
