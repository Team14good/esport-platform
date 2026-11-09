"""Story 6.2 審查後續: appeal open unique

重新比賽後，原申訴隊可以對重賽後的結果再申訴：(match_id, team_id) 唯一鍵改成
「同一隊對同一場只能有一筆未結案申訴」（status = 'open' 的部分唯一索引）。
另加 match_id 的一般索引（原唯一鍵兼作依場次查詢的索引）。

Revision ID: f2b6d8a1c3e5
Revises: a9d4f2c6e8b1
Create Date: 2026-11-09 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2b6d8a1c3e5"
down_revision = "a9d4f2c6e8b1"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_appeal_match_team", "appeal", type_="unique")
    op.create_index(
        "uq_appeal_open_match_team",
        "appeal",
        ["match_id", "team_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        op.f("ix_appeal_match_id"), "appeal", ["match_id"], unique=False
    )


def downgrade():
    # 重新比賽後再申訴會留下同隊同場多筆申訴，舊的唯一鍵建不回去：不刪資料，先停下來
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT match_id, team_id, count(*) FROM appeal "
                "GROUP BY match_id, team_id HAVING count(*) > 1"
            )
        )
        .all()
    )
    if duplicates:
        raise RuntimeError(
            "無法降版：有同一隊對同一場的多筆申訴（重新比賽後再申訴），"
            "舊的 uq_appeal_match_team 唯一鍵建不回去。請先人工處理這些申訴再降版："
            f"{[(str(m), str(t), n) for m, t, n in duplicates]}"
        )
    op.drop_index(op.f("ix_appeal_match_id"), table_name="appeal")
    op.drop_index("uq_appeal_open_match_team", table_name="appeal")
    op.create_unique_constraint(
        "uq_appeal_match_team", "appeal", ["match_id", "team_id"]
    )
