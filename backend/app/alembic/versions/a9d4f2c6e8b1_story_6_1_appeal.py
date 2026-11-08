"""Story 6.1: appeal

disputes 新增申訴：(match_id, team_id) 唯一（每隊每場一次）；處理欄位由 6.2 寫入，
reminded_at 給 6.3（期中擱置）。

Revision ID: a9d4f2c6e8b1
Revises: b5c8e2f4a1d7
Create Date: 2026-11-08 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "a9d4f2c6e8b1"
down_revision = "b5c8e2f4a1d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "appeal",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("filed_by", sa.Uuid(), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "description",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=False,
        ),
        sa.Column(
            "attachment_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("handled_by", sa.Uuid(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["filed_by"], ["account.id"]),
        sa.ForeignKeyConstraint(["handled_by"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "team_id", name="uq_appeal_match_team"),
    )
    op.create_index(
        op.f("ix_appeal_tournament_id"), "appeal", ["tournament_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_appeal_tournament_id"), table_name="appeal")
    op.drop_table("appeal")
