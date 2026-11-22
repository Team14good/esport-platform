"""Story 2.3: round_setting

新增分輪 BO：以「距決賽的輪數」（決賽＝0、4 強＝1…）儲存；主鍵 (tournament_id, rounds_from_final)。

Revision ID: a7d3e9b2c6f4
Revises: b8d4f2a6c9e1
Create Date: 2026-11-21 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7d3e9b2c6f4"
down_revision = "b8d4f2a6c9e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "round_setting",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("rounds_from_final", sa.Integer(), nullable=False),
        sa.Column("bo", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("tournament_id", "rounds_from_final"),
    )


def downgrade():
    op.drop_table("round_setting")
