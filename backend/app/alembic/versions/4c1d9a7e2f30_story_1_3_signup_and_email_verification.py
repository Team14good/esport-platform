"""Story 1.3: signup and email verification

建立 school（含教育部大專校院名錄初始資料）、account.school_id、account_token、
outbox_event、email_delivery，並把 account 的 Email 唯一改成 lower(email) 唯一。

學校初始資料：政府資料開放平臺「大專校院名錄」（教育部，https://data.gov.tw/dataset/6091，
CSV：https://stats.moe.gov.tw/files/opendata/u1_new.csv），2026-10-24 下載，取最新的
115 學年度、只取校名，共 139 所。

Revision ID: 4c1d9a7e2f30
Revises: b786ec269db0
Create Date: 2026-10-24 12:30:00.000000

"""
import uuid
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "4c1d9a7e2f30"
down_revision = "b786ec269db0"
branch_labels = None
depends_on = None


SCHOOL_NAMES = (
    "國立政治大學",
    "國立清華大學",
    "國立臺灣大學",
    "國立臺灣師範大學",
    "國立成功大學",
    "國立中興大學",
    "國立陽明交通大學",
    "國立中央大學",
    "國立中山大學",
    "國立臺灣海洋大學",
    "國立中正大學",
    "國立高雄師範大學",
    "國立彰化師範大學",
    "國立臺北大學",
    "國立嘉義大學",
    "國立高雄大學",
    "國立東華大學",
    "國立暨南國際大學",
    "國立臺灣科技大學",
    "國立雲林科技大學",
    "國立屏東科技大學",
    "國立臺北科技大學",
    "國立臺北藝術大學",
    "國立臺灣藝術大學",
    "國立臺東大學",
    "國立宜蘭大學",
    "國立聯合大學",
    "國立虎尾科技大學",
    "國立臺南藝術大學",
    "國立臺南大學",
    "國立臺北教育大學",
    "國立臺中教育大學",
    "國立澎湖科技大學",
    "國立勤益科技大學",
    "國立體育大學",
    "國立臺北護理健康大學",
    "國立高雄餐旅大學",
    "國立金門大學",
    "國立臺灣體育運動大學",
    "國立臺中科技大學",
    "國立臺北商業大學",
    "國立屏東大學",
    "國立高雄科技大學",
    "國立臺灣戲曲學院",
    "國立臺南護理專科學校",
    "國立臺東專科學校",
    "東海大學",
    "輔仁大學",
    "東吳大學",
    "中原大學",
    "淡江大學",
    "中國文化大學",
    "逢甲大學",
    "靜宜大學",
    "長庚大學",
    "元智大學",
    "中華大學",
    "大葉大學",
    "華梵大學",
    "義守大學",
    "世新大學",
    "銘傳大學",
    "實踐大學",
    "朝陽科技大學",
    "高雄醫學大學",
    "南華大學",
    "真理大學",
    "大同大學",
    "南臺科技大學",
    "崑山科技大學",
    "嘉南藥理大學",
    "樹德科技大學",
    "慈濟大學",
    "臺北醫學大學",
    "中山醫學大學",
    "龍華科技大學",
    "輔英科技大學",
    "明新科技大學",
    "長榮大學",
    "弘光科技大學",
    "中國醫藥大學",
    "健行科技大學",
    "正修科技大學",
    "萬能科技大學",
    "玄奘大學",
    "建國科技大學",
    "明志科技大學",
    "台鋼科技大學",
    "大仁科技大學",
    "聖約翰科技大學",
    "嶺東科技大學",
    "中國科技大學",
    "中臺科技大學",
    "亞洲大學",
    "開南大學",
    "佛光大學",
    "台南應用科技大學",
    "中信科技大學",
    "元培醫事科技大學",
    "景文科技大學",
    "中華醫事科技大學",
    "東南科技大學",
    "德明財經科技大學",
    "南開科技大學",
    "中華科技大學",
    "僑光科技大學",
    "育達科技大學",
    "美和科技大學",
    "吳鳳科技大學",
    "修平科技大學",
    "長庚科技大學",
    "臺北城市科技大學",
    "敏實科技大學",
    "醒吾科技大學",
    "文藻外語大學",
    "華夏科技大學",
    "致理科技大學",
    "康寧大學",
    "宏國德霖科技大學",
    "崇右影藝科技大學",
    "台北海洋科技大學",
    "亞東科技大學",
    "馬偕醫學大學",
    "中信金融管理學院",
    "南亞技術學院",
    "黎明技術學院",
    "德育護理健康學院",
    "法鼓文理學院",
    "馬偕醫護管理專科學校",
    "仁德醫護管理專科學校",
    "樹人醫護管理專科學校",
    "慈惠醫護管理專科學校",
    "耕莘健康管理專科學校",
    "敏惠醫護管理專科學校",
    "育英醫護管理專科學校",
    "聖母醫護管理專科學校",
    "新生醫護管理專科學校",
    "崇仁醫護管理專科學校",
    "臺北市立大學",
)


def upgrade():
    school = op.create_table(
        "school",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_school_name"), "school", ["name"], unique=True)
    loaded_at = datetime.now(UTC)
    op.bulk_insert(
        school,
        [{"id": uuid.uuid4(), "name": name, "created_at": loaded_at} for name in SCHOOL_NAMES],
    )

    op.add_column("account", sa.Column("school_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "account_school_id_fkey", "account", "school", ["school_id"], ["id"]
    )
    # Email 一律以去除前後空白、轉小寫後的值儲存；唯一性改以 lower(email) 判斷
    op.execute("UPDATE account SET email = lower(btrim(email))")
    op.drop_index(op.f("ix_account_email"), table_name="account")
    op.create_index(
        "ix_account_lower_email", "account", [sa.text("lower(email)")], unique=True
    )

    op.create_table(
        "account_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column(
            "token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_token_account_id"), "account_token", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_account_token_token_hash"), "account_token", ["token_hash"], unique=True
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_event_processed_at_created_at",
        "outbox_event",
        ["processed_at", "created_at"],
        unique=False,
    )

    op.create_table(
        "email_delivery",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["outbox_event.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "account_id", name="uq_email_delivery_event_id_account_id"
        ),
    )
    op.create_index(
        "ix_email_delivery_status_next_attempt_at",
        "email_delivery",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_email_delivery_status_next_attempt_at", table_name="email_delivery")
    op.drop_table("email_delivery")
    op.drop_index("ix_outbox_event_processed_at_created_at", table_name="outbox_event")
    op.drop_table("outbox_event")
    op.drop_index(op.f("ix_account_token_token_hash"), table_name="account_token")
    op.drop_index(op.f("ix_account_token_account_id"), table_name="account_token")
    op.drop_table("account_token")
    op.drop_index("ix_account_lower_email", table_name="account")
    op.create_index(op.f("ix_account_email"), "account", ["email"], unique=True)
    op.drop_constraint("account_school_id_fkey", "account", type_="foreignkey")
    op.drop_column("account", "school_id")
    op.drop_index(op.f("ix_school_name"), table_name="school")
    op.drop_table("school")
