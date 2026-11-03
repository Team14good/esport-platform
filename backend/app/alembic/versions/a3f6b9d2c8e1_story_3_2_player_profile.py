"""Story 3.2: player profile

team_member 加參賽資料欄位：遊戲 ID、段位與其積分、段位截圖的檔案鍵值與清理過的
原始檔名（皆可為 null，尚未填寫）。截圖檔案存在 uploads volume，資料庫只存鍵值。

Revision ID: a3f6b9d2c8e1
Revises: c5d2e8a4f913
Create Date: 2026-11-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "a3f6b9d2c8e1"
down_revision = "c5d2e8a4f913"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "team_member",
        sa.Column(
            "game_account_id",
            sqlmodel.sql.sqltypes.AutoString(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "team_member",
        sa.Column(
            "rank_tier", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True
        ),
    )
    op.add_column("team_member", sa.Column("rank_score", sa.Integer(), nullable=True))
    op.add_column(
        "team_member",
        sa.Column(
            "rank_screenshot_key",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "team_member",
        sa.Column(
            "rank_screenshot_name",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("team_member", "rank_screenshot_name")
    op.drop_column("team_member", "rank_screenshot_key")
    op.drop_column("team_member", "rank_score")
    op.drop_column("team_member", "rank_tier")
    op.drop_column("team_member", "game_account_id")
