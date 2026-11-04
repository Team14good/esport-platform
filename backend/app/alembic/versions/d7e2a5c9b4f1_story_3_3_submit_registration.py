"""Story 3.3: submit registration

registration 加送出時的快照：學校、全隊（含替補）平均段位積分、送出時間（組隊中皆為
null）。平均段位積分用 numeric(12,2)：段位積分上限是 PostgreSQL integer 上限，
numeric(6,2) 會溢位。

Revision ID: d7e2a5c9b4f1
Revises: b5c7e9a1d3f2
Create Date: 2026-11-03 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d7e2a5c9b4f1"
down_revision = "b5c7e9a1d3f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("registration", sa.Column("school_id", sa.Uuid(), nullable=True))
    op.add_column(
        "registration",
        sa.Column("avg_rank_score", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "registration",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "registration_school_id_fkey",
        "registration",
        "school",
        ["school_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "registration_school_id_fkey", "registration", type_="foreignkey"
    )
    op.drop_column("registration", "submitted_at")
    op.drop_column("registration", "avg_rank_score")
    op.drop_column("registration", "school_id")
