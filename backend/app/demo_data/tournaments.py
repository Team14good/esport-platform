"""示範資料第二步（tournaments）：兩款遊戲與一場《特戰英豪》示範賽事。

- 遊戲：《英雄聯盟》（`win_loss`）、《特戰英豪》（`rounds`），含段位對照表；
  操作者為第一個平台管理員（`settings.FIRST_ADMIN_EMAIL`）。同名遊戲已存在時
  沿用、不修改設定。
- 賽事：32 隊校園賽「FLOW 校園盃 特戰英豪」，主辦方為 `context.accounts["organizer"]`，
  建立後維持「開放報名」，由 competition 步驟抽籤（`draw` 接受 `open`）。不放直播連結。
  同一主辦方已有同名賽事時沿用、不修改。不論新建或沿用，都把賽事 id 寫進
  `context.tournament_to_draw`。

時間以 `app.core.clock.now()` 為基準：報名開始為 1 小時前、報名截止為 3 天後、
開賽為 7 天後。
"""

import logging
import uuid
from datetime import timedelta

from sqlmodel import Session

from app.core import clock
from app.core.config import settings
from app.core.errors import BusinessError
from app.demo_data.context import DemoContext
from app.modules.identity import service as identity_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    GameIn,
    RankTierIn,
    ScoreType,
    TournamentCreate,
)

logger = logging.getLogger(__name__)


def _tiers(*pairs: tuple[str, int]) -> list[RankTierIn]:
    return [RankTierIn(name=name, score=score) for name, score in pairs]


VALORANT_NAME = "特戰英豪"
LEAGUE_NAME = "英雄聯盟"

DEMO_GAMES = (
    GameIn(
        name=LEAGUE_NAME,
        starters=5,
        substitutes=1,
        default_bo=3,
        game_minutes=35,
        score_type=ScoreType.WIN_LOSS,
        rank_tiers=_tiers(
            ("無排位", 0),
            ("鐵牌", 5),
            ("銅牌", 15),
            ("銀牌", 30),
            ("金牌", 50),
            ("白金", 70),
            ("翡翠", 90),
            ("鑽石", 115),
            ("大師", 145),
            ("宗師", 170),
            ("菁英", 200),
        ),
    ),
    GameIn(
        name=VALORANT_NAME,
        starters=5,
        substitutes=1,
        default_bo=3,
        game_minutes=40,
        score_type=ScoreType.ROUNDS,
        rank_tiers=_tiers(
            ("無排位", 0),
            ("鐵牌", 5),
            ("銅牌", 15),
            ("銀牌", 30),
            ("金牌", 50),
            ("白金", 75),
            ("鑽石", 105),
            ("超凡入聖", 140),
            ("神話", 170),
            ("輻能戰魂", 200),
        ),
    ),
)

DEMO_TOURNAMENT_NAME = "FLOW 校園盃 特戰英豪"
DEMO_TOURNAMENT_CAPACITY = 32
DEMO_ROUND_INTERVAL_MINUTES = 180


def _name_key(name: str) -> str:
    # 與 tournaments 的遊戲名稱唯一規則一致：去除前後空白、不分大小寫
    return name.strip().lower()


def _ensure_games(session: Session, actor_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """建立示範遊戲（同名已存在就沿用）；回傳示範遊戲名稱 → 遊戲 id。"""
    existing = {
        _name_key(game.name): game.id
        for game in tournaments_service.list_games(session)
    }
    game_ids: dict[str, uuid.UUID] = {}
    for data in DEMO_GAMES:
        game_id = existing.get(_name_key(data.name))
        if game_id is None:
            game_id = tournaments_service.create_game(
                session, actor_id=actor_id, data=data
            ).id
            logger.info("Demo game created: %s", data.name)
        else:
            logger.info("Demo game already exists, reused: %s", data.name)
        game_ids[data.name] = game_id
    return game_ids


def _ensure_tournament(
    session: Session, *, organizer_id: uuid.UUID, game_id: uuid.UUID
) -> uuid.UUID | None:
    """建立示範賽事（同一主辦方已有同名賽事就沿用）；建立被拒絕時回傳 None。"""
    for tournament in tournaments_service.list_organizer_tournaments(
        session, organizer_id=organizer_id
    ):
        if _name_key(tournament.name) == _name_key(DEMO_TOURNAMENT_NAME):
            logger.info(
                "Demo tournament already exists, reused: %s", DEMO_TOURNAMENT_NAME
            )
            return tournament.id

    now = clock.now()
    data = TournamentCreate(
        name=DEMO_TOURNAMENT_NAME,
        game_id=game_id,
        capacity=DEMO_TOURNAMENT_CAPACITY,
        registration_start=now - timedelta(hours=1),
        registration_end=now + timedelta(days=3),
        priority_hours=24,
        start_at=now + timedelta(days=7),
        round_interval_minutes=DEMO_ROUND_INTERVAL_MINUTES,
    )
    try:
        # 沿用的同名遊戲設定可能讓每輪間隔不合規則而被拒絕：記錄後略過賽事。
        # 目前的檢查都在寫入前；savepoint 防範之後 create_tournament 先寫入再失敗
        # 時，連帶撤銷前面步驟的資料
        with session.begin_nested():
            created = tournaments_service.create_tournament(
                session, organizer_id=organizer_id, data=data
            )
    except BusinessError as exc:
        logger.warning(
            "Demo tournament not created (%s: %s), skipped", exc.code, exc.message
        )
        return None
    logger.info("Demo tournament created: %s", DEMO_TOURNAMENT_NAME)
    return created.id


def seed(session: Session, context: DemoContext) -> None:
    admin_id = identity_service.find_account_id_by_email(
        session, settings.FIRST_ADMIN_EMAIL
    )
    if admin_id is None:
        logger.warning(
            "First platform admin not found, tournaments demo data skipped: %s",
            settings.FIRST_ADMIN_EMAIL,
        )
        return
    game_ids = _ensure_games(session, admin_id)

    organizer_id = context.accounts.get("organizer")
    if organizer_id is None:
        logger.info("No demo organizer, demo tournament skipped")
        return
    context.tournament_to_draw = _ensure_tournament(
        session, organizer_id=organizer_id, game_id=game_ids[VALORANT_NAME]
    )
