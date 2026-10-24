"""identity 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

from fastapi import APIRouter, status

from app.core.db import SessionDep
from app.modules.identity import service
from app.modules.identity.models import (
    AccountCreate,
    EmailVerificationCreate,
    PublicSchool,
    RegisteredAccount,
    VerificationEmailCreate,
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
