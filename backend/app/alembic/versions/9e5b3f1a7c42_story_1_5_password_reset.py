"""Story 1.5: forgot and reset password

account 加上 credentials_version（憑證版本，預設 0）：access token 帶 `ver` claim，
與帳號目前的值不同就視為失效；重設密碼時＋1，讓之前簽發的 token 全部失效。
重設 token 沿用 Story 1.3 的 account_token（purpose = reset_password），不需新表。

Revision ID: 9e5b3f1a7c42
Revises: 4c1d9a7e2f30
Create Date: 2026-10-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9e5b3f1a7c42"
down_revision = "4c1d9a7e2f30"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "account",
        sa.Column(
            "credentials_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("account", "credentials_version")
