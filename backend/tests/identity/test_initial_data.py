from collections.abc import Callable

from sqlmodel import Session, select

from app.core.config import settings
from app.initial_data import init
from app.modules.identity.models import Account


def test_init_twice_commits_a_single_first_admin(
    session_factory: Callable[[], Session],
) -> None:
    init(session_factory)
    init(session_factory)

    with session_factory() as check:
        admins = list(
            check.exec(
                select(Account).where(Account.email == settings.FIRST_ADMIN_EMAIL)
            )
        )
    assert len(admins) == 1
    assert admins[0].is_platform_admin is True
