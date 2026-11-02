"""示範資料（Story 7.1）：啟動時由 `app.initial_data` 載入，可重複執行。

規則：

- 只透過各模組 `service.py` 的公開函式建立資料，不直接寫資料表；本套件與
  `initial_data` 一樣扮演 router 角色，由 `initial_data` 開交易並 commit。
- 每一筆資料先檢查是否已存在，再次啟動不重複建立、不覆寫既有欄位。
- 登入資訊來自 `.env` 的 `DEMO_PASSWORD`、`DEMO_EMAIL_DOMAIN`；沒有設定
  `DEMO_PASSWORD` 時整段略過。時間一律 `app.core.clock.now()`。

新增自己模組的示範資料：

1. 在本資料夾新增步驟檔（例如 `tournaments.py`），提供
   `def seed(session: Session, context: DemoContext) -> None`（`DemoContext` 在 `context.py`）。
   需要的帳號 id 從 `context.accounts`（角色 → 帳號 id）取得；要留給後面步驟用的
   值（例如賽事 id），在 `context.py` 的 `DemoContext` 新增欄位後寫回 `context`。
2. 把 `seed` 依呼叫方向的反序加進下面的 `STEPS`：
   identity → tournaments → registration → competition。
3. 在 `backend/tests/<模組>/` 補上「呼叫兩次不重複建立」的測試。
"""

import logging

from sqlmodel import Session

from app.core.config import settings
from app.demo_data import accounts
from app.demo_data.context import DemoContext, Step

logger = logging.getLogger(__name__)

# 依呼叫方向的反序執行：identity → tournaments → registration → competition
STEPS: list[Step] = [
    accounts.seed,
]


def load(session: Session) -> bool:
    """依序執行各模組的示範資料步驟；不 commit。回傳是否有執行（有設定密碼）。"""
    if not settings.DEMO_PASSWORD:
        logger.info(
            "DEMO_PASSWORD is not set, demo data skipped "
            "(add DEMO_PASSWORD to .env, see .env.example)"
        )
        return False
    context = DemoContext(
        password=settings.DEMO_PASSWORD,
        email_domain=settings.DEMO_EMAIL_DOMAIN,
    )
    for step in STEPS:
        step(session, context)
    return True
