"""Story 7.1 示範資料：示範帳號的建立、冪等與略過行為。"""

import logging
from collections.abc import Callable

import pytest
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.demo_data import load
from app.demo_data.accounts import DEMO_SCHOOL_NAME
from app.initial_data import init
from app.modules.identity import service
from app.modules.identity.models import Account, School

DEMO_PASSWORD = "demo-password"
DEMO_DOMAIN = "demo.example.com"
DEMO_EMAILS = [
    f"{role}@{DEMO_DOMAIN}" for role in ("organizer", "referee", "captain", "player")
]


@pytest.fixture
def demo_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_PASSWORD", DEMO_PASSWORD)
    monkeypatch.setattr(settings, "DEMO_EMAIL_DOMAIN", DEMO_DOMAIN)


def _demo_accounts(session: Session) -> dict[str, Account]:
    accounts = session.exec(select(Account).where(col(Account.email).in_(DEMO_EMAILS)))
    return {account.email: account for account in accounts}


def _account_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(Account)).one()


@pytest.mark.usefixtures("demo_settings")
def test_fresh_database_creates_four_verified_demo_accounts(session: Session) -> None:
    assert load(session) is True

    accounts = _demo_accounts(session)
    assert sorted(accounts) == sorted(DEMO_EMAILS)
    school = session.exec(select(School).where(School.name == DEMO_SCHOOL_NAME)).one()
    for email, account in accounts.items():
        assert account.email_verified is True
        assert account.school_id == school.id
        assert account.is_platform_admin is False
        assert account.is_organizer is email.startswith("organizer@")
        assert verify_password(DEMO_PASSWORD, account.hashed_password)[0] is True


@pytest.mark.usefixtures("demo_settings")
def test_init_twice_keeps_demo_account_count(
    session_factory: Callable[[], Session], caplog: pytest.LogCaptureFixture
) -> None:
    init(session_factory)
    with session_factory() as check:
        count_after_first = _account_count(check)
        assert len(_demo_accounts(check)) == 4

    with caplog.at_level(logging.INFO):
        init(session_factory)

    with session_factory() as check:
        assert _account_count(check) == count_after_first
    skipped = [r for r in caplog.records if "already exists, skipped" in r.message]
    assert len(skipped) == 1 + len(DEMO_EMAILS)  # 第一個管理員＋四個示範帳號


@pytest.mark.usefixtures("demo_settings")
def test_existing_demo_account_is_skipped_without_overwriting(
    session: Session,
) -> None:
    load(session)
    [organizer] = [a for a in _demo_accounts(session).values() if a.is_organizer]
    organizer.display_name = "改過的名稱"
    session.add(organizer)
    session.flush()
    snapshot = organizer.model_dump()

    load(session)

    session.expire_all()
    assert _demo_accounts(session)[organizer.email].model_dump() == snapshot


def test_without_demo_password_only_first_admin_is_created(
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "DEMO_PASSWORD", None)
    monkeypatch.setattr(settings, "DEMO_EMAIL_DOMAIN", DEMO_DOMAIN)

    with caplog.at_level(logging.INFO):
        init(session_factory)

    with session_factory() as check:
        assert _demo_accounts(check) == {}
        admin = check.exec(
            select(Account).where(Account.email == settings.FIRST_ADMIN_EMAIL)
        ).one()
        assert admin.is_platform_admin is True
    assert any("DEMO_PASSWORD is not set" in r.message for r in caplog.records)


@pytest.mark.usefixtures("demo_settings")
def test_email_registered_by_real_person_is_not_promoted(session: Session) -> None:
    real_email = f"organizer@{DEMO_DOMAIN}"
    real = Account(
        email=real_email,
        hashed_password=get_password_hash("real-password"),
        display_name="真人",
        email_verified=False,
    )
    session.add(real)
    session.flush()
    snapshot = real.model_dump()

    load(session)

    session.expire_all()
    accounts = _demo_accounts(session)
    assert accounts[real_email].model_dump() == snapshot
    assert accounts[real_email].is_organizer is False
    assert len(accounts) == 4


def test_ensure_demo_account_raises_when_school_not_found(session: Session) -> None:
    with pytest.raises(LookupError):
        service.ensure_demo_account(
            session,
            email=f"nobody@{DEMO_DOMAIN}",
            password=DEMO_PASSWORD,
            display_name="示範",
            school_name="不存在的學校",
        )

    assert _demo_accounts(session) == {}
    assert service.find_account_id_by_email(session, f"nobody@{DEMO_DOMAIN}") is None
