"""示範資料最後一步（competition）：替 tournaments 步驟建立的示範賽事抽籤。

賽事由 `context.tournament_to_draw` 指定（tournaments 步驟寫入），正取隊伍由
registration 步驟建立。抽籤走 competition 的 `service.draw`，用固定的亂數種子，
全新資料庫每次產生同一張對戰表，演練腳本與截圖才對得上。

以下情況只記錄 log 並略過，不讓整段示範資料回滾：

- 沒有指定賽事（上游步驟還沒做或沒建立）。
- 已抽過籤（再次啟動）。
- 抽籤被業務規則拒絕，例如開賽時間已過、賽事狀態不能抽籤、registration 的
  抽籤函式還沒合併（503）。抽籤在 savepoint 裡執行，失敗時只撤銷抽籤本身。
"""

import logging
import random

from sqlmodel import Session

from app.core.errors import BusinessError
from app.demo_data.context import DemoContext
from app.modules.competition import service as competition_service

logger = logging.getLogger(__name__)

DEMO_DRAW_SEED = 14


def seed(session: Session, context: DemoContext) -> None:
    tournament_id = context.tournament_to_draw
    if tournament_id is None:
        logger.info("No demo tournament to draw, competition demo data skipped")
        return
    if competition_service.get_bracket(session, tournament_id=tournament_id):
        logger.info("Demo tournament already drawn, skipped: %s", tournament_id)
        return
    try:
        with session.begin_nested():
            competition_service.draw(
                session,
                tournament_id=tournament_id,
                actor_id=context.accounts["organizer"],
                rng=random.Random(DEMO_DRAW_SEED),
            )
    except BusinessError as exc:
        logger.warning(
            "Demo tournament %s not drawn (%s: %s), skipped",
            tournament_id,
            exc.code,
            exc.message,
        )
        return
    logger.info("Demo tournament drawn: %s", tournament_id)
