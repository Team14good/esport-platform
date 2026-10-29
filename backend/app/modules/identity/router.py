"""identity 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。

未登入可以呼叫的寫入端點只有 `PUBLIC_WRITE_ROUTES` 列出的這些；其他寫入端點一律
套用 `CurrentAccount`（或更嚴格的依賴），未登入回 401（tests 會逐一檢查）。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.db import SessionDep
from app.modules.identity import service
from app.modules.identity.deps import CurrentAccount, PlatformAdmin, VerifiedAccount
from app.modules.identity.models import (
    AccessToken,
    AccessTokenCreate,
    AccountCreate,
    AccountRead,
    AdminOrganizerApplication,
    ApplicationStatus,
    EmailVerificationCreate,
    Identity,
    OrganizerApplicationCreate,
    OrganizerApplicationPage,
    OrganizerApplicationRead,
    OrganizerApplicationRejection,
    PasswordResetCheck,
    PasswordResetCreate,
    PasswordResetEmailCreate,
    ProfileUpdate,
    PublicSchool,
    RegisteredAccount,
    VerificationEmailCreate,
)

# (方法, 路徑)：未登入也能呼叫的寫入端點
PUBLIC_WRITE_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/accounts"),
        ("POST", "/email-verifications"),
        ("POST", "/verification-emails"),
        ("POST", "/access-tokens"),
        ("POST", "/password-reset-emails"),
        ("POST", "/password-reset-checks"),
        ("POST", "/password-resets"),
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


@router.post("/password-reset-emails", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset_email(
    session: SessionDep, body: PasswordResetEmailCreate
) -> None:
    """申請重設密碼信；不論 Email 是否已註冊，回應都相同。"""
    service.request_password_reset(session, email=body.email)
    session.commit()


@router.post("/password-reset-checks", status_code=status.HTTP_204_NO_CONTENT)
def check_password_reset_link(session: SessionDep, body: PasswordResetCheck) -> None:
    """檢查重設連結是否仍有效（不會用掉 token）；失效回 400 `RESET_LINK_INVALID`。

    用 POST 是為了不讓 token 出現在存取紀錄的網址裡。
    """
    service.check_reset_token(session, token=body.token)


@router.post("/password-resets", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(session: SessionDep, body: PasswordResetCreate) -> None:
    """以重設連結的 token 設定新密碼；之前簽發的 access token 一律失效，不會自動登入。"""
    service.reset_password(session, token=body.token, new_password=body.new_password)
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


@router.post("/organizer-applications", status_code=status.HTTP_201_CREATED)
def submit_organizer_application(
    session: SessionDep, account: VerifiedAccount, body: OrganizerApplicationCreate
) -> OrganizerApplicationRead:
    """送出主辦方申請（需已驗證 Email）；同一帳號同時只能有一筆待審核。"""
    application = service.submit_organizer_application(
        session,
        account_id=account.id,
        club_name=body.club_name,
        school_id=body.school_id,
    )
    session.commit()
    return application


@router.get("/accounts/me/organizer-application")
def read_current_organizer_application(
    session: SessionDep, account: CurrentAccount
) -> OrganizerApplicationRead | None:
    """目前帳號最新的一筆主辦方申請；從沒申請過時回傳 null。未驗證 Email 也能讀。"""
    return service.get_my_organizer_application(session, account.id)


# ---------------------------------------------------------------- 平台管理：審核主辦方申請


@router.get("/admin/organizer-applications")
def list_organizer_applications(
    session: SessionDep,
    _admin: PlatformAdmin,
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> OrganizerApplicationPage:
    """主辦方申請清單（平台管理員）：依送出時間由舊到新、每頁 20 筆；`status` 省略表示全部。"""
    return service.list_organizer_applications(session, status=status_filter, page=page)


@router.post("/admin/organizer-applications/{application_id}/approval")
def approve_organizer_application(
    session: SessionDep, admin: PlatformAdmin, application_id: uuid.UUID
) -> AdminOrganizerApplication:
    """核准主辦方申請：申請人立即成為主辦方。已審核過回 409 `APPLICATION_NOT_PENDING`。"""
    application = service.approve_organizer_application(
        session, admin_id=admin.id, application_id=application_id
    )
    session.commit()
    return application


@router.post("/admin/organizer-applications/{application_id}/rejection")
def reject_organizer_application(
    session: SessionDep,
    admin: PlatformAdmin,
    application_id: uuid.UUID,
    body: OrganizerApplicationRejection,
) -> AdminOrganizerApplication:
    """退回主辦方申請（必填原因）；申請人可以修改後重送。已審核過回 409。"""
    application = service.reject_organizer_application(
        session, admin_id=admin.id, application_id=application_id, reason=body.reason
    )
    session.commit()
    return application
