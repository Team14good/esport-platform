"""Story 6.4: report

disputes 新增 report（檢舉）：檢舉人隊伍、被檢舉隊伍、說明與選擇性附件鍵值；
處理欄位（reason、handled_by、handled_at）一併建立，6.5 只寫入、不再改表。
重複檢舉以鎖住賽事列序列化，不用部分唯一索引。

Revision ID: e9a4c2f7b6d1
Revises: b5c8e2f4a1d7
Create Date: 2026-11-08 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "e9a4c2f7b6d1"
down_revision = "b5c8e2f4a1d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_team_id", sa.Uuid(), nullable=False),
        sa.Column("filed_by", sa.Uuid(), nullable=False),
        sa.Column("reported_team_id", sa.Uuid(), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False
        ),
        sa.Column(
            "attachment_key", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "reason", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True
        ),
        sa.Column("handled_by", sa.Uuid(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["filed_by"], ["account.id"]),
        sa.ForeignKeyConstraint(["handled_by"], ["account.id"]),
        sa.ForeignKeyConstraint(["reported_team_id"], ["team.id"]),
        sa.ForeignKeyConstraint(["reporter_team_id"], ["team.id"]),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournament.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_report_tournament_id"), "report", ["tournament_id"], unique=False
    )
    op.create_index(
        "ix_report_reporter_team_id_reported_team_id",
        "report",
        ["reporter_team_id", "reported_team_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_report_reporter_team_id_reported_team_id", table_name="report")
    op.drop_index(op.f("ix_report_tournament_id"), table_name="report")
    op.drop_table("report")
