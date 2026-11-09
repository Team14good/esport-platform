"""Story 7.1 示範資料：示範帳號的建立、冪等與略過行為。"""

import logging
from collections.abc import Callable
from typing import Any

import pytest
from sqlmodel import Session, col, func, select

from app import demo_data
from app.core.config import settings
from app.core.errors import BusinessError
from app.core.security import get_password_hash, verify_password
from app.demo_data import load
from app.demo_data import registration as registration_step
from app.demo_data.accounts import DEMO_SCHOOL_NAME
from app.initial_data import init
from app.modules.competition.models import Bracket, Match
from app.modules.identity import service
from app.modules.identity.models import Account, School
from app.modules.registration import service as registration_service
from app.modules.registration.models import Registration, Team, TeamMember

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


@pytest.mark.usefixtures("demo_settings")
def test_renamed_demo_school_skips_demo_data_without_blocking_startup(
    session_factory: Callable[[], Session], caplog: pytest.LogCaptureFixture
) -> None:
    # 平台管理員在 S36 改了示範學校的名稱，之後才補上 DEMO_PASSWORD 再重啟
    with session_factory() as admin_session:
        school = admin_session.exec(
            select(School).where(School.name == DEMO_SCHOOL_NAME)
        ).one()
        school.name = f"{DEMO_SCHOOL_NAME}（改名）"
        admin_session.add(school)
        admin_session.commit()

    with caplog.at_level(logging.ERROR):
        init(session_factory)  # 不拋錯：backend 照常啟動

    with session_factory() as check:
        assert _demo_accounts(check) == {}
        admin = check.exec(
            select(Account).where(Account.email == settings.FIRST_ADMIN_EMAIL)
        ).one()
        assert admin.is_platform_admin is True
    [error] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "Demo data failed to load" in error.message
    assert error.exc_info is not None
    assert error.exc_info[0] is LookupError


@pytest.mark.usefixtures("demo_settings")
def test_failing_later_step_rolls_back_all_demo_data(
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 後面的步驟失敗時，前面步驟建立的示範帳號也不寫入（整段同一個交易）
    def broken_step(_session: Session, _context: object) -> None:
        raise RuntimeError("broken demo step")

    monkeypatch.setattr(demo_data, "STEPS", [*demo_data.STEPS, broken_step])

    init(session_factory)

    with session_factory() as check:
        assert _demo_accounts(check) == {}
        assert (
            check.exec(
                select(Account).where(Account.email == settings.FIRST_ADMIN_EMAIL)
            ).first()
            is not None
        )


def _count(session: Session, model: type) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


@pytest.fixture
def first_admin(session: Session) -> None:
    """tournaments 步驟要有第一個平台管理員才會建立示範賽事。"""
    service.ensure_first_admin(
        session, email=settings.FIRST_ADMIN_EMAIL, password="admin-password"
    )


@pytest.mark.usefixtures("demo_settings", "first_admin")
def test_demo_tournament_is_drawn_with_32_teams(session: Session) -> None:
    assert load(session) is True

    # 抽籤後正取隊伍轉為 drawn
    drawn = session.exec(
        select(func.count())
        .select_from(Registration)
        .where(Registration.status == "drawn")
    ).one()
    assert drawn == registration_step.DEMO_TEAM_COUNT
    assert _count(session, Bracket) == 1
    first_round = session.exec(select(Match).where(Match.round_no == 1)).all()
    assert len(first_round) == registration_step.DEMO_TEAM_COUNT // 2
    assert all(m.team_a_id and m.team_b_id for m in first_round)


@pytest.mark.usefixtures("demo_settings", "first_admin")
def test_demo_captain_and_player_share_first_team(session: Session) -> None:
    load(session)

    accounts = _demo_accounts(session)
    captain = accounts[f"captain@{DEMO_DOMAIN}"]
    player = accounts[f"player@{DEMO_DOMAIN}"]
    [captain_card] = registration_service.list_my_teams(session, account_id=captain.id)
    [player_card] = registration_service.list_my_teams(session, account_id=player.id)
    assert captain_card.team_id == player_card.team_id
    assert captain_card.team_name == f"{DEMO_SCHOOL_NAME}電競隊"
    members = session.exec(
        select(func.count())
        .select_from(TeamMember)
        .where(TeamMember.team_id == captain_card.team_id)
    ).one()
    assert members == registration_step.DEMO_TEAM_SIZE


@pytest.mark.usefixtures("demo_settings", "first_admin")
def test_load_twice_does_not_duplicate_demo_teams(session: Session) -> None:
    load(session)
    accounts = _account_count(session)

    assert load(session) is True

    assert _account_count(session) == accounts
    assert _count(session, Team) == registration_step.DEMO_TEAM_COUNT
    assert _count(session, Bracket) == 1


@pytest.mark.usefixtures("demo_settings", "first_admin")
def test_rejected_demo_team_is_skipped_with_its_accounts(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    real_submit = registration_service.submit_registration
    calls = {"count": 0}

    def fail_second_team(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 2:
            raise BusinessError("REGISTRATION_CLOSED", "報名已截止", status_code=409)
        return real_submit(*args, **kwargs)

    monkeypatch.setattr(registration_service, "submit_registration", fail_second_team)

    with caplog.at_level(logging.WARNING):
        assert load(session) is True

    assert "Demo team 2" in caplog.text
    assert _count(session, Team) == registration_step.DEMO_TEAM_COUNT - 1
    assert service.find_account_id_by_email(session, f"team02-m1@{DEMO_DOMAIN}") is None
