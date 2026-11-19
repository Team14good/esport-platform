"""Story 4.2: auto draw skip

自動抽籤判定正取不足 2 隊、沒有抽籤時記一筆（賽事, 報名截止時間）唯一的紀錄，
worker 之後不再選這場賽事，主辦方只收到一次事件。

Revision ID: b3e7a1c9d5f2
Revises: f2b6d8a1c3e5
Create Date: 2026-11-19 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3e7a1c9d5f2"
down_revision = "f2b6d8a1c3e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auto_draw_skip",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("registration_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_teams", sa.Integer(), nullable=False),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tournament_id",
            "registration_end",
            name="uq_auto_draw_skip_tournament_registration_end",
        ),
    )


def downgrade():
    op.drop_table("auto_draw_skip")
