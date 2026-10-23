from sqlmodel import Session, func, select

from app.core.security import get_password_hash, verify_password
from app.modules.identity import service
from app.modules.identity.models import Account

ADMIN_EMAIL = "first-admin@example.com"
ADMIN_PASSWORD = "first-admin-password"


def _accounts(session: Session, email: str) -> list[Account]:
    return list(session.exec(select(Account).where(Account.email == email)))


def test_creates_first_admin_when_absent(session: Session) -> None:
    created = service.ensure_first_admin(
        session, email=ADMIN_EMAIL, password=ADMIN_PASSWORD
    )

    assert created is True
    [admin] = _accounts(session, ADMIN_EMAIL)
    assert admin.is_platform_admin is True
    assert admin.email_verified is True
    assert admin.is_organizer is False
    assert admin.display_name == "平台管理員"
    assert admin.hashed_password != ADMIN_PASSWORD
    assert verify_password(ADMIN_PASSWORD, admin.hashed_password)[0] is True
    assert admin.created_at.tzinfo is not None


def test_skips_existing_account_without_overwriting(session: Session) -> None:
    existing = Account(
        email=ADMIN_EMAIL,
        hashed_password=get_password_hash("changed-password"),
        display_name="改過的名稱",
        email_verified=False,
        is_platform_admin=True,
    )
    session.add(existing)
    session.flush()
    snapshot = existing.model_dump()

    created = service.ensure_first_admin(
        session, email=ADMIN_EMAIL, password=ADMIN_PASSWORD
    )

    assert created is False
    session.expire_all()
    [admin] = _accounts(session, ADMIN_EMAIL)
    assert admin.model_dump() == snapshot
    assert verify_password("changed-password", admin.hashed_password)[0] is True


def test_repeated_startup_keeps_a_single_platform_admin(session: Session) -> None:
    for _ in range(3):
        service.ensure_first_admin(session, email=ADMIN_EMAIL, password=ADMIN_PASSWORD)

    admin_count = session.exec(
        select(func.count()).select_from(Account).where(Account.is_platform_admin)
    ).one()
    assert admin_count == 1
