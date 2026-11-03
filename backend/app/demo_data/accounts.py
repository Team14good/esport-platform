"""示範資料第一步（identity）：主辦方、裁判、隊長、選手四個已驗證 Email 的帳號。

帳號為 `<角色>@<DEMO_EMAIL_DOMAIN>`，密碼共用 `DEMO_PASSWORD`，都屬示範學校。
同 Email 已存在（包含被真人註冊）時略過、不覆寫；不論新建或略過，都把帳號 id
寫進 `context.accounts`，給後面的步驟使用。
"""

import logging
from typing import NamedTuple

from sqlmodel import Session

from app.demo_data.context import DemoContext
from app.modules.identity import service as identity_service

logger = logging.getLogger(__name__)

DEMO_SCHOOL_NAME = "國立中央大學"


class DemoAccount(NamedTuple):
    role: str
    display_name: str
    is_organizer: bool = False


DEMO_ACCOUNTS = (
    DemoAccount("organizer", "示範主辦方", is_organizer=True),
    DemoAccount("referee", "示範裁判"),
    DemoAccount("captain", "示範隊長"),
    DemoAccount("player", "示範選手"),
)


def demo_email(role: str, domain: str) -> str:
    return f"{role}@{domain}"


def seed(session: Session, context: DemoContext) -> None:
    for demo in DEMO_ACCOUNTS:
        email = demo_email(demo.role, context.email_domain)
        created = identity_service.ensure_demo_account(
            session,
            email=email,
            password=context.password,
            display_name=demo.display_name,
            school_name=DEMO_SCHOOL_NAME,
            is_organizer=demo.is_organizer,
        )
        if created:
            logger.info("Demo account created: %s", email)
        else:
            logger.info("Demo account already exists, skipped: %s", email)
        account_id = identity_service.find_account_id_by_email(session, email)
        assert account_id is not None  # 剛建立或已存在
        context.accounts[demo.role] = account_id
