"""Story 3.10: tournament invite_token

自訂賽事的賽事報名連結：tournament 加 invite_token（明文、UNIQUE，校園賽為 null），
並以 CHECK 約束保證「自訂賽事⇔有 token」。既有的校園賽 token 維持 null。本遷移之前沒有
建立自訂賽事的入口，但以 SQL 手動改成自訂的賽事列（例如第 1 部分檢視畫面時）會擋下約束，
所以加約束前先替這些賽事補上 token（與 service 相同的產生方式）。

Revision ID: b2f6c8d4e1a9
Revises: a7d3e9b2c6f4
Create Date: 2026-11-24 12:00:00.000000

"""

import secrets

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "b2f6c8d4e1a9"
down_revision = "a7d3e9b2c6f4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tournament",
        sa.Column(
            "invite_token", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True
        ),
    )
    op.create_unique_constraint(
        "tournament_invite_token_key", "tournament", ["invite_token"]
    )
    connection = op.get_bind()
    custom_ids = connection.execute(
        sa.text("SELECT id FROM tournament WHERE mode = 'custom'")
    ).scalars()
    for tournament_id in list(custom_ids):
        connection.execute(
            sa.text("UPDATE tournament SET invite_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(32), "id": tournament_id},
        )
    op.create_check_constraint(
        "ck_tournament_custom_has_invite_token",
        "tournament",
        "(mode = 'custom') = (invite_token IS NOT NULL)",
    )


def downgrade():
    op.drop_constraint(
        "ck_tournament_custom_has_invite_token", "tournament", type_="check"
    )
    op.drop_constraint("tournament_invite_token_key", "tournament", type_="unique")
    op.drop_column("tournament", "invite_token")
