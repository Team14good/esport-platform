"""示範資料各步驟共用的 context 與步驟型別。"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlmodel import Session


@dataclass
class DemoContext:
    """各步驟共用的資料：前面步驟寫入，後面步驟讀取。"""

    password: str
    email_domain: str
    # 角色（organizer、referee、captain、player）→ 帳號 id
    accounts: dict[str, uuid.UUID] = field(default_factory=dict)


Step = Callable[[Session, DemoContext], None]
