"""Story 3.4: priority window settlement

registration 新增優先期結算紀錄：一場賽事一筆（tournament_id 為主鍵），存在就代表
已結算；保存參加優先期結算的報名的學校（可為空陣列），候補順位用來判斷「優先期有
報名的學校」。

Revision ID: b5c8e2f4a1d7
Revises: d7e2a5c9b4f1
Create Date: 2026-11-04 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b5c8e2f4a1d7"
down_revision = "d7e2a5c9b4f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "priority_window_settlement",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority_school_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("tournament_id"),
    )


def downgrade():
    op.drop_table("priority_window_settlement")
