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
    # tournaments 步驟建立、要由 competition 步驟抽籤的示範賽事（主辦方須為
    # `accounts["organizer"]`）；沒有就是 None，competition 步驟略過
    tournament_to_draw: uuid.UUID | None = None


Step = Callable[[Session, DemoContext], None]
