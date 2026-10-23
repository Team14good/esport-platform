"""Story 1.1: account and audit_log

建立 account（首位平台管理員所需的最小欄位）與 audit_log（只增不改的操作紀錄）。

Revision ID: b786ec269db0
Revises:
Create Date: 2026-10-23 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b786ec269db0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column(
            "hashed_password", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "display_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("is_organizer", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_email"), "account", ["email"], unique=True)

    op.create_table(
        "audit_log",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("tournament_id", sa.Uuid(), nullable=True),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "entity_type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_tournament_id_at_seq",
        "audit_log",
        ["tournament_id", "at", "seq"],
        unique=False,
    )

    # 操作紀錄只增不改（AD-9）：任何 UPDATE、DELETE、TRUNCATE 都由資料庫拒絕。
    # 用 statement-level trigger，即使沒有符合的資料列也會拒絕。
    op.execute(
        """
        CREATE FUNCTION audit_log_reject_modification() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_reject_modification
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_modification();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER audit_log_reject_modification ON audit_log")
    op.execute("DROP FUNCTION audit_log_reject_modification()")
    op.drop_index("ix_audit_log_tournament_id_at_seq", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_account_email"), table_name="account")
    op.drop_table("account")
