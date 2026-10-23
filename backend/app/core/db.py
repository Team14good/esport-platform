"""資料庫連線與 session 依賴（AD-5）。

`get_session` 只 yield、不自動 commit：一個請求就是一個交易，由 router 在
使用案例成功後明確呼叫 `session.commit()`；沒有 commit 的寫入會在 session
關閉時回滾。service 與 repository 一律不得 commit 或 rollback。
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
