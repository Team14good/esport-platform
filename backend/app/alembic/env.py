import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic 的設定物件，可以讀到目前使用的 .ini 檔裡的值
config = context.config

# 依 .ini 檔設定 Python 的 logging
assert config.config_file_name is not None
# 不停用既有 logger（測試時由 conftest 呼叫遷移，避免把 app 的 logger 關掉）
fileConfig(config.config_file_name, disable_existing_loggers=False)

# autogenerate 比對用的 MetaData：由下方匯入的所有 models 註冊

from sqlmodel import SQLModel  # noqa

from app.core.config import settings  # noqa

# 匯入 core（操作紀錄、事件）與六個模組的 models（app.modules 會載入全部模組），讓所有資料表都註冊到 SQLModel.metadata
import app.core.audit  # noqa
import app.core.events  # noqa
import app.modules  # noqa

target_metadata = SQLModel.metadata


def get_url():
    return str(settings.DATABASE_URL)


def run_migrations_offline():
    """以「離線」模式執行遷移。

    只用 URL 設定 context，不建立 Engine，因此不需要可用的 DBAPI；
    這裡呼叫 context.execute() 會把 SQL 字串輸出到腳本，而不是送進資料庫。
    """
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """以「連線」模式執行遷移：建立 Engine，並把連線交給 context。"""
    configuration = config.get_section(config.config_ini_section)
    assert configuration is not None
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
