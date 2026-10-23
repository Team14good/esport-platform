"""業務模組（AD-1）：每個模組各有 router、service、repository、models。

匯入本套件就會載入六個模組的 models，讓所有資料表都註冊到同一份
`SQLModel.metadata`；跨模組外鍵（例如 `audit_log.actor_id → account.id`）
因此在任何進入點（API、worker、prestart、alembic）都能解析。
"""

from app.modules.competition import models as competition_models
from app.modules.disputes import models as disputes_models
from app.modules.identity import models as identity_models
from app.modules.notifications import models as notifications_models
from app.modules.registration import models as registration_models
from app.modules.tournaments import models as tournaments_models

__all__ = [
    "competition_models",
    "disputes_models",
    "identity_models",
    "notifications_models",
    "registration_models",
    "tournaments_models",
]
