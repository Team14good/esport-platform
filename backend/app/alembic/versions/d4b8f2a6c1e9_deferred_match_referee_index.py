"""deferred: match.referee_account_id 索引

裁判查自己的場次（GET /me/referee/matches）不再掃整張場次表。

Revision ID: d4b8f2a6c1e9
Revises: a7d3e9b2c6f4
Create Date: 2026-11-25 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d4b8f2a6c1e9"
down_revision = "a7d3e9b2c6f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        op.f("ix_match_referee_account_id"),
        "match",
        ["referee_account_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_match_referee_account_id"), table_name="match")
