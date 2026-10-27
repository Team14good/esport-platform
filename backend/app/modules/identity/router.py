"""identity 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。

未登入可以呼叫的寫入端點只有 `PUBLIC_WRITE_ROUTES` 列出的這些；其他寫入端點一律
套用 `CurrentAccount`（或更嚴格的依賴），未登入回 401（tests 會逐一檢查）。
"""

from fastapi import APIRouter, status

from app.core.db import SessionDep
from app.modules.identity import service
from app.modules.identity.deps import CurrentAccount
from app.modules.identity.models import (
    AccessToken,
    AccessTokenCreate,
    AccountCreate,
    AccountRead,
    EmailVerificationCreate,
    Identity,
    ProfileUpdate,
    PublicSchool,
    RegisteredAccount,
    VerificationEmailCreate,
)

# (方法, 路徑)：未登入也能呼叫的寫入端點（之後 Story 1.5 加入忘記／重設密碼）
PUBLIC_WRITE_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/accounts"),
        ("POST", "/email-verifications"),
        ("POST", "/verification-emails"),
        ("POST", "/access-tokens"),
    }
)

router = APIRouter(tags=["identity"])


@router.get("/schools")
def list_schools(session: SessionDep) -> list[PublicSchool]:
    """公開的學校清單（依名稱排序）。"""
    return service.list_schools(session)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def register(session: SessionDep, body: AccountCreate) -> RegisteredAccount:
    """以 Email 註冊；之後要收驗證信完成驗證。不會自動登入。"""
    account = service.register(
        session,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        school_id=body.school_id,
        redirect=body.redirect,
    )
    session.commit()
    return account


@router.post("/email-verifications", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(session: SessionDep, body: EmailVerificationCreate) -> None:
    """以驗證信連結中的 token 完成 Email 驗證。"""
    service.verify_email(session, token=body.token)
    session.commit()


@router.post("/verification-emails", status_code=status.HTTP_202_ACCEPTED)
def resend_verification_email(
    session: SessionDep, body: VerificationEmailCreate
) -> None:
    """重寄驗證信；不論 Email 是否已註冊或已驗證，回應都相同。"""
    service.resend_verification(session, email=body.email, redirect=body.redirect)
    session.commit()


@router.post("/access-tokens", status_code=status.HTTP_200_OK)
def login(session: SessionDep, body: AccessTokenCreate) -> AccessToken:
    """以 Email 與密碼登入，回傳 access token（之後以 `Authorization: Bearer` 帶上）。

    Email 不存在、密碼錯誤或格式不符都回 401 `INVALID_CREDENTIALS`，回應完全相同。
    """
    token = service.authenticate(session, email=body.email, password=body.password)
    # 只有雜湊需要更新時才有寫入
    session.commit()
    return token


@router.get("/accounts/me")
def read_current_account(account: CurrentAccount) -> AccountRead:
    """目前登入的帳號。"""
    return account


@router.patch("/accounts/me")
def update_current_account(
    session: SessionDep, account: CurrentAccount, body: ProfileUpdate
) -> AccountRead:
    """修改顯示名稱與學校（`school_id: null` 清除學校）；Email 與密碼不能在這裡改。"""
    updated = service.update_profile(session, account_id=account.id, changes=body)
    session.commit()
    return updated


@router.get("/accounts/me/identities")
def list_current_identities(
    session: SessionDep, account: CurrentAccount
) -> list[Identity]:
    """目前帳號擁有的身分（身分切換器用），只由後端依帳號資料產生。"""
    return service.list_identities(session, account)
