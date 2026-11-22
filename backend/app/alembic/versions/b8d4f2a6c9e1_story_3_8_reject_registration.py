"""Story 3.8: reject registration

registration 加主辦方退回的原因與時間（沒有被退回過為 null）。

Revision ID: b8d4f2a6c9e1
Revises: a7c3e9f1b5d8
Create Date: 2026-11-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8d4f2a6c9e1"
down_revision = "a7c3e9f1b5d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "registration",
        sa.Column("reject_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "registration",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("registration", "rejected_at")
    op.drop_column("registration", "reject_reason")
