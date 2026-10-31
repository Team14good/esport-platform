"""Story 5.5: match confirmed_at

場次加上 confirmed_at（轉為已確認時寫入；申訴期滿自動確認與輪空確認都會寫），
以及 worker 找申訴期滿場次用的 (status, appeal_deadline) 索引。

Revision ID: a3d5e7f9b1c4
Revises: f7a3c9e1b5d2
Create Date: 2026-10-31 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3d5e7f9b1c4"
down_revision = "f7a3c9e1b5d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "match",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_match_status_appeal_deadline",
        "match",
        ["status", "appeal_deadline"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_match_status_appeal_deadline", table_name="match")
    op.drop_column("match", "confirmed_at")
