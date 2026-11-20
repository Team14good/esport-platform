"""Story 5.7: result_screenshot

新增結算截圖（每個場次最多一列，更換時覆寫；只存檔案鍵值）。

Revision ID: c4f8a2e6d1b7
Revises: f2b6d8a1c3e5
Create Date: 2026-11-20 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "c4f8a2e6d1b7"
down_revision = "f2b6d8a1c3e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "result_screenshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column(
            "file_key", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id"),
    )


def downgrade():
    op.drop_table("result_screenshot")
