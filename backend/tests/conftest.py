"""測試共用 fixture。

所有測試都連 compose 裡的 PostgreSQL 18（AD-16，禁止 SQLite），但一律使用同一
伺服器上獨立的 `<POSTGRES_DB>_test` 資料庫：每次測試開始時刪除重建，再跑
`alembic upgrade head`。開發用資料庫完全不會被寫入。

每個測試包在一個外層交易裡，結束時整個回滾；測試中的 session（包含 API 請求
與 worker 用的 session）都以 savepoint 模式加入這個交易，所以 router 的
`session.commit()` 只會釋放 savepoint，不會真的落地。
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]

_dev_url = make_url(str(settings.DATABASE_URL))
TEST_DATABASE = f"{_dev_url.database}_test"
_test_url = _dev_url.set(database=TEST_DATABASE)

# 必須在匯入 app.core.db（建立 engine）之前，把連線改到測試資料庫
settings.DATABASE_URL = PostgresDsn(_test_url.render_as_string(hide_password=False))

from app.core import clock  # noqa: E402
from app.core.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.notifications.email import EmailMessage  # noqa: E402

assert engine.url.database == TEST_DATABASE, (
    "app.core.db was imported before tests/conftest.py switched to the test database"
)


def _recreate_test_database() -> None:
    # 每次測試都從空資料庫跑完整遷移，修改過的遷移檔不會留下舊 schema
    admin_engine = create_engine(
        _dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin_engine.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)')
            )
            connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    engine.dispose()
    _recreate_test_database()
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "alembic"))
    command.upgrade(alembic_cfg, "head")


def _savepoint_session(connection: Connection) -> Session:
    return Session(bind=connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def db_connection() -> Iterator[Connection]:
    """包住整個測試的外層交易；測試結束時回滾。"""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def session(db_connection: Connection) -> Iterator[Session]:
    with _savepoint_session(db_connection) as db_session:
        yield db_session


@pytest.fixture
def session_factory(db_connection: Connection) -> Callable[[], Session]:
    """給 worker 等自行開 session 的程式使用；每次都是新的 savepoint session。"""
    return lambda: _savepoint_session(db_connection)


@pytest.fixture
def client(db_connection: Connection) -> Iterator[TestClient]:
    def _override_get_session() -> Iterator[Session]:
        with _savepoint_session(db_connection) as db_session:
            yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


class FrozenClock:
    """凍結的 `core.clock`：`set()` 設定時間點，`advance()` 往後推進。"""

    def set(self, at: datetime) -> None:
        clock.freeze(at)

    def advance(self, delta: timedelta) -> None:
        clock.advance(delta)

    def now(self) -> datetime:
        return clock.now()


@pytest.fixture
def frozen_clock() -> Iterator[FrozenClock]:
    """把時鐘凍結在 2026-10-18 11:00 UTC；測試結束後恢復真實時間。"""
    frozen = FrozenClock()
    frozen.set(datetime(2026, 10, 18, 11, 0, tzinfo=UTC))
    try:
        yield frozen
    finally:
        clock.reset()


class FakeEmailSender:
    """替換 SMTP 的假寄信器：記錄寄出的信；`fail_with` 設定時每次都拋出該例外。"""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_with: Exception | None = None
        self.calls = 0

    def send(self, message: EmailMessage) -> None:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(message)


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()
