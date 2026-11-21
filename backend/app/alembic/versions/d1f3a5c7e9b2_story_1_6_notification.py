"""Story 1.6: notification

新增站內通知（每個事件對每個收件人一則；未讀為 read_at IS NULL）。

Revision ID: d1f3a5c7e9b2
Revises: c4f8a2e6d1b7
Create Date: 2026-11-21 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "d1f3a5c7e9b2"
down_revision = "c4f8a2e6d1b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False
        ),
        sa.Column(
            "body", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False
        ),
        sa.Column(
            "link", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_event.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "account_id", name="uq_notification_event_id_account_id"
        ),
    )
    op.create_index(
        "ix_notification_account_id_created_at",
        "notification",
        ["account_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_notification_account_id_created_at", table_name="notification")
    op.drop_table("notification")
