"""啟動時的初始資料：建立第一個平台管理員（已存在則略過）。

由 `scripts/prestart.sh` 在遷移之後執行；角色等同 router，負責開啟並提交交易。
"""

import logging
from collections.abc import Callable

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.modules.identity import service as identity_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _default_session_factory() -> Session:
    return Session(engine)


def init(session_factory: Callable[[], Session] = _default_session_factory) -> None:
    with session_factory() as session:
        created = identity_service.ensure_first_admin(
            session,
            email=settings.FIRST_ADMIN_EMAIL,
            password=settings.FIRST_ADMIN_PASSWORD,
        )
        session.commit()
    if created:
        logger.info("First platform admin created: %s", settings.FIRST_ADMIN_EMAIL)
    else:
        logger.info("First platform admin already exists, skipped")


def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
