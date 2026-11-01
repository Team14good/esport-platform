"""Story 5.3: match_game

新增逐局比分（(match_id, game_no) 唯一），以及 match.submitted_by、
match.submitted_at（5.4 送出系列結果）。

Revision ID: d8e2f4a6b1c3
Revises: b5c7e9a1d3f2
Create Date: 2026-11-01 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8e2f4a6b1c3"
down_revision = "b5c7e9a1d3f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "match_game",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("game_no", sa.Integer(), nullable=False),
        sa.Column("winner_side", sa.String(length=1), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=True),
        sa.Column("score_b", sa.Integer(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "game_no", name="uq_match_game_match_game_no"),
    )
    op.add_column("match", sa.Column("submitted_by", sa.Uuid(), nullable=True))
    op.add_column(
        "match",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "match_submitted_by_fkey", "match", "account", ["submitted_by"], ["id"]
    )


def downgrade():
    op.drop_constraint("match_submitted_by_fkey", "match", type_="foreignkey")
    op.drop_column("match", "submitted_at")
    op.drop_column("match", "submitted_by")
    op.drop_table("match_game")
