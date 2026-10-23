"""交易邊界（AD-5）：session 依賴不自動 commit，只有 router 明確 commit 才落地。"""

import uuid
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, delete
from sqlmodel import Session, select

from app.core.db import SessionDep, engine, get_session
from app.modules.identity.models import Account


def _new_account(email: str) -> Account:
    return Account(
        email=email, hashed_password="not-a-real-hash", display_name="測試帳號"
    )


def _unique_email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def test_uncommitted_write_does_not_persist_after_request() -> None:
    # 使用真正的 get_session（不覆寫），確認請求結束、session 關閉時會回滾
    email = _unique_email()
    app = FastAPI()

    @app.post("/write-without-commit")
    def write_without_commit(session: SessionDep) -> None:
        session.add(_new_account(email))
        session.flush()

    try:
        response = TestClient(app).post("/write-without-commit")

        assert response.status_code == 200
        with Session(engine) as check:
            found = check.exec(select(Account).where(Account.email == email)).first()
        assert found is None
    finally:
        # 萬一測試失敗、資料真的落地，也不要留在測試資料庫裡
        with Session(engine) as cleanup:
            cleanup.execute(delete(Account).where(Account.email == email))  # type: ignore[arg-type]
            cleanup.commit()


def test_router_commit_makes_write_visible(
    db_connection: Connection, session: Session
) -> None:
    email = _unique_email()
    app = FastAPI()

    @app.post("/write-and-commit")
    def write_and_commit(db_session: SessionDep) -> None:
        db_session.add(_new_account(email))
        db_session.commit()

    def _override() -> Iterator[Session]:
        with Session(bind=db_connection, join_transaction_mode="create_savepoint") as s:
            yield s

    app.dependency_overrides[get_session] = _override

    response = TestClient(app).post("/write-and-commit")

    assert response.status_code == 200
    found = session.exec(select(Account).where(Account.email == email)).first()
    assert found is not None
