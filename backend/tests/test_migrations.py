"""遷移檔與 SQLModel 模型一致：autogenerate 不應再產生任何差異。"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlmodel import SQLModel

import app.core.audit  # noqa: F401
import app.modules  # noqa: F401


def test_migrations_match_models(db_connection: Connection) -> None:
    context = MigrationContext.configure(db_connection, opts={"compare_type": True})

    diff = compare_metadata(context, SQLModel.metadata)

    assert diff == []
