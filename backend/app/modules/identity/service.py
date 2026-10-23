"""identity 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

from sqlmodel import Session

from app.core.security import get_password_hash
from app.modules.identity import repository
from app.modules.identity.models import Account

FIRST_ADMIN_DISPLAY_NAME = "平台管理員"


def ensure_first_admin(session: Session, *, email: str, password: str) -> bool:
    """建立第一個平台管理員；同 Email 已存在就略過、不覆寫任何欄位。

    回傳是否新建了帳號。交易由呼叫端（`app.initial_data`）提交。
    """
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
