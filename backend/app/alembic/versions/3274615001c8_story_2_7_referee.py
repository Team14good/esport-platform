"""Story 2.7: referee invitation and tournament referee

建立 referee_invitation（裁判邀請；token 明文、UNIQUE；tournament_id 有索引）與
tournament_referee（已接受邀請的裁判；主鍵 (tournament_id, account_id)）。

Revision ID: 3274615001c8
Revises: a3d5e7f9b1c4
Create Date: 2026-11-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "3274615001c8"
down_revision = "a3d5e7f9b1c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "referee_invitation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("token", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["account.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(
        op.f("ix_referee_invitation_tournament_id"),
        "referee_invitation",
        ["tournament_id"],
        unique=False,
    )

    op.create_table(
        "tournament_referee",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["invitation_id"], ["referee_invitation.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("tournament_id", "account_id"),
    )
    op.create_index(
        op.f("ix_tournament_referee_account_id"),
        "tournament_referee",
        ["account_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_tournament_referee_account_id"), table_name="tournament_referee"
    )
    op.drop_table("tournament_referee")
    op.drop_index(
        op.f("ix_referee_invitation_tournament_id"), table_name="referee_invitation"
    )
    op.drop_table("referee_invitation")
