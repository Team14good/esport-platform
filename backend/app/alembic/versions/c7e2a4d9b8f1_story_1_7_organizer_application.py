"""Story 1.7: apply to be organizer

建立 organizer_application（主辦方申請）。同一帳號可以有多筆（被退回後重送），
但待審核（status = 'pending'）同時只能有一筆：以 account_id 的部分唯一索引保底。

Revision ID: c7e2a4d9b8f1
Revises: 9e5b3f1a7c42
Create Date: 2026-10-29 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "c7e2a4d9b8f1"
down_revision = "9e5b3f1a7c42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizer_application",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "club_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["school_id"], ["school.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organizer_application_account_id"),
        "organizer_application",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_organizer_application_pending_account_id",
        "organizer_application",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index(
        "ix_organizer_application_pending_account_id",
        table_name="organizer_application",
    )
    op.drop_index(
        op.f("ix_organizer_application_account_id"),
        table_name="organizer_application",
    )
    op.drop_table("organizer_application")
