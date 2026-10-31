"""Story 5.1: check_in

新增報到紀錄（(match_id, team_id) 唯一），以及 bracket.start_handled_at
（worker 標記賽事開始已處理）。

Revision ID: b5c7e9a1d3f2
Revises: a3d5e7f9b1c4
Create Date: 2026-11-01 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b5c7e9a1d3f2"
down_revision = "a3d5e7f9b1c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "check_in",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "team_id", name="uq_check_in_match_team"),
    )
    op.add_column(
        "bracket",
        sa.Column("start_handled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("bracket", "start_handled_at")
    op.drop_table("check_in")
