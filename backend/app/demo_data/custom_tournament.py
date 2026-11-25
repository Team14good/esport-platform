"""示範資料第三步（tournaments，Story 3.10）：一場開放報名中、自訂模式的《英雄聯盟》校內賽。

- 賽事：名額 8 的自訂賽事「FLOW 校內賽 英雄聯盟」，主辦方為 `context.accounts["organizer"]`，
  遊戲用 tournaments 步驟建立（或沿用）的《英雄聯盟》。不建隊伍：評審從 S27 取得賽事
  報名連結後自行建隊。不寫進 `context.tournament_to_draw`（之後的報名、抽籤步驟只處理
  校園賽）。
- 同一主辦方已有同名賽事時沿用、不修改。

時間以 `app.core.clock.now()` 為基準（比照校園賽示範賽事）：報名開始為 1 小時前、
報名截止為 3 天後、開賽為 7 天後。自訂賽事沒有優先期。
"""

import logging
import uuid
from datetime import timedelta

from sqlmodel import Session

from app.core import clock
from app.core.errors import BusinessError
from app.demo_data.context import DemoContext
from app.demo_data.tournaments import DEMO_ROUND_INTERVAL_MINUTES, LEAGUE_NAME
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentCreate, TournamentMode

logger = logging.getLogger(__name__)

DEMO_CUSTOM_TOURNAMENT_NAME = "FLOW 校內賽 英雄聯盟"
DEMO_CUSTOM_TOURNAMENT_CAPACITY = 8


def _name_key(name: str) -> str:
    # 與 tournaments 步驟相同：去除前後空白、不分大小寫
    return name.strip().lower()


def _league_game_id(session: Session) -> uuid.UUID | None:
    for game in tournaments_service.list_games(session):
        if _name_key(game.name) == _name_key(LEAGUE_NAME):
            return game.id
    return None


def _existing_id(session: Session, organizer_id: uuid.UUID) -> uuid.UUID | None:
    for tournament in tournaments_service.list_organizer_tournaments(
        session, organizer_id=organizer_id
    ):
        if _name_key(tournament.name) == _name_key(DEMO_CUSTOM_TOURNAMENT_NAME):
            return tournament.id
    return None


def ensure_custom_tournament(
    session: Session, *, organizer_id: uuid.UUID, game_id: uuid.UUID
) -> uuid.UUID | None:
    """建立示範自訂賽事（同一主辦方已有同名賽事就沿用）；建立被拒絕時回傳 None。"""
    existing = _existing_id(session, organizer_id)
    if existing is not None:
        logger.info(
            "Demo custom tournament already exists, reused: %s",
            DEMO_CUSTOM_TOURNAMENT_NAME,
        )
        return existing

    now = clock.now()
    data = TournamentCreate(
        name=DEMO_CUSTOM_TOURNAMENT_NAME,
        game_id=game_id,
        mode=TournamentMode.CUSTOM,
        capacity=DEMO_CUSTOM_TOURNAMENT_CAPACITY,
        registration_start=now - timedelta(hours=1),
        registration_end=now + timedelta(days=3),
        priority_hours=0,
        start_at=now + timedelta(days=7),
        round_interval_minutes=DEMO_ROUND_INTERVAL_MINUTES,
    )
    try:
        # 沿用的同名遊戲設定可能讓每輪間隔不合規則而被拒絕：記錄後略過（比照校園賽）
        with session.begin_nested():
            created = tournaments_service.create_tournament(
                session, organizer_id=organizer_id, data=data
            )
    except BusinessError as exc:
        logger.warning(
            "Demo custom tournament not created (%s: %s), skipped",
            exc.code,
            exc.message,
        )
        return None
    logger.info("Demo custom tournament created: %s", DEMO_CUSTOM_TOURNAMENT_NAME)
    return created.id


def seed(session: Session, context: DemoContext) -> None:
    organizer_id = context.accounts.get("organizer")
    if organizer_id is None:
        logger.info("No demo organizer, demo custom tournament skipped")
        return
    game_id = _league_game_id(session)
    if game_id is None:
        logger.info(
            "Demo game %s not found, demo custom tournament skipped", LEAGUE_NAME
        )
        return
    ensure_custom_tournament(session, organizer_id=organizer_id, game_id=game_id)
