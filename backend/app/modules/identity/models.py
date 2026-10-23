"""identity 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from app.core import clock


class TokenPurpose(StrEnum):
    """一次性帳號 token 的用途（AccountToken 由 Story 1.3 建立）。"""

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class ApplicationStatus(StrEnum):
    """主辦方申請狀態：待審核、核准、退回（OrganizerApplication 由 Story 1.7 建立）。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Account(SQLModel, table=True):
    """帳號。平台管理員與主辦方都是帳號上的旗標；`school_id` 由 Story 1.3 加入。"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(max_length=255)
    email_verified: bool = False
    display_name: str = Field(max_length=255)
    is_platform_admin: bool = False
    is_organizer: bool = False
    created_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
