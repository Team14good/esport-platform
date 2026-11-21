"""Story 3.7: withdraw registration

registration 加遞補時間（名額釋出後由候補遞補為正取的時間，其他方式成為正取為 null）
與優先期代表隊標記（既有報名一律為 false）。

Revision ID: a7c3e9f1b5d8
Revises: d1f3a5c7e9b2
Create Date: 2026-11-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7c3e9f1b5d8"
down_revision = "d1f3a5c7e9b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "registration",
        sa.Column("backfilled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "registration",
        sa.Column(
            "is_representative",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("registration", "is_representative")
    op.drop_column("registration", "backfilled_at")
