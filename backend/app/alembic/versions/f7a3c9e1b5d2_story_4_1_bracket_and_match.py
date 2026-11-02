"""Story 4.1: bracket and match

建立 bracket（每場賽事一份對戰表）與 match（場次；勝隊與準決賽敗隊的去向
以自我參照外鍵 next_match_id、loser_next_match_id 表示）。

Revision ID: f7a3c9e1b5d2
Revises: e4b8c1d2a6f7
Create Date: 2026-10-31 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "f7a3c9e1b5d2"
down_revision = "e4b8c1d2a6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bracket",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("team_count", sa.Integer(), nullable=False),
        sa.Column("drawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id"),
    )
    op.create_table(
        "match",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bracket_id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("slot_no", sa.Integer(), nullable=False),
        sa.Column("is_third_place", sa.Boolean(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("team_a_id", sa.Uuid(), nullable=True),
        sa.Column("team_b_id", sa.Uuid(), nullable=True),
        sa.Column("bye_a", sa.Boolean(), nullable=False),
        sa.Column("bye_b", sa.Boolean(), nullable=False),
        sa.Column("referee_account_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("winner_id", sa.Uuid(), nullable=True),
        sa.Column("wins_a", sa.Integer(), nullable=False),
        sa.Column("wins_b", sa.Integer(), nullable=False),
        sa.Column("forfeit_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("appeal_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_match_id", sa.Uuid(), nullable=True),
        sa.Column("loser_next_match_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bracket_id"], ["bracket.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.ForeignKeyConstraint(["referee_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["next_match_id"], ["match.id"]),
        sa.ForeignKeyConstraint(["loser_next_match_id"], ["match.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bracket_id",
            "round_no",
            "slot_no",
            "is_third_place",
            name="uq_match_bracket_round_slot",
        ),
    )
    op.create_index(op.f("ix_match_bracket_id"), "match", ["bracket_id"], unique=False)
    op.create_index(
        op.f("ix_match_tournament_id"), "match", ["tournament_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_match_tournament_id"), table_name="match")
    op.drop_index(op.f("ix_match_bracket_id"), table_name="match")
    op.drop_table("match")
    op.drop_table("bracket")
