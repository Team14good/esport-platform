"""Story 3.11: disbanded team member

新增 disbanded_team_member：隊長解散隊伍時刪除所有 team_member 列（原隊員才能加入同賽事
的其他隊伍），另存解散當下的原隊員帳號與角色，供 S12 撤回卡片、S17 唯讀頁與 S29 使用。

Revision ID: c3e7a9d1f5b2
Revises: b8d4f2a6c9e1
Create Date: 2026-11-23 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3e7a9d1f5b2"
down_revision = "b8d4f2a6c9e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "disbanded_team_member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["team.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "account_id",
            name="uq_disbanded_team_member_team_id_account_id",
        ),
    )
    op.create_index(
        op.f("ix_disbanded_team_member_account_id"),
        "disbanded_team_member",
        ["account_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_disbanded_team_member_account_id"),
        table_name="disbanded_team_member",
    )
    op.drop_table("disbanded_team_member")
