"""Story 7.1 示範資料的 tournaments 步驟：兩款遊戲、示範賽事、冪等與略過行為。"""

import logging
import uuid
from datetime import timedelta

import pytest
from sqlmodel import Session, col, func, select

from app.core import clock
from app.core.audit import AuditLog
from app.core.config import settings
from app.demo_data import STEPS, accounts, competition, load, tournaments
from app.demo_data.context import DemoContext
from app.modules.identity import service as identity_service
from app.modules.tournaments import service
from app.modules.tournaments.models import (
    GameIn,
    GameRead,
    RankTierIn,
    ScoreType,
    TournamentStatus,
)
from tests.helpers import make_account

pytestmark = pytest.mark.usefixtures("frozen_clock")


@pytest.fixture
def admin_id(session: Session) -> uuid.UUID:
    identity_service.ensure_first_admin(
        session, email=settings.FIRST_ADMIN_EMAIL, password="admin-password"
    )
    account_id = identity_service.find_account_id_by_email(
        session, settings.FIRST_ADMIN_EMAIL
    )
    assert account_id is not None
    return account_id


def _context(organizer_id: uuid.UUID | None) -> DemoContext:
    context = DemoContext(password="demo-password", email_domain="demo.example.com")
    if organizer_id is not None:
        context.accounts["organizer"] = organizer_id
    return context


def _games_by_name(session: Session) -> dict[str, GameRead]:
    return {game.name: game for game in service.list_games(session)}


def _audit_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(AuditLog)).one()


def test_tournaments_step_runs_between_accounts_and_competition() -> None:
    assert STEPS.index(accounts.seed) < STEPS.index(tournaments.seed)
    assert STEPS.index(tournaments.seed) < STEPS.index(competition.seed)


def test_fresh_database_creates_games_and_demo_tournament(
    session: Session, admin_id: uuid.UUID
) -> None:
    organizer = make_account(session, organizer=True)
    context = _context(organizer.id)

    tournaments.seed(session, context)

    games = _games_by_name(session)
    league = games["英雄聯盟"]
    assert (league.score_type, league.starters, league.substitutes) == (
        ScoreType.WIN_LOSS,
        5,
        1,
    )
    assert (league.default_bo, league.game_minutes) == (3, 35)
    assert [(t.name, t.score) for t in league.rank_tiers][:3] == [
        ("菁英", 200),
        ("宗師", 170),
        ("大師", 145),
    ]
    assert len(league.rank_tiers) == 11
    valorant = games["特戰英豪"]
    assert (valorant.score_type, valorant.starters, valorant.substitutes) == (
        ScoreType.ROUNDS,
        5,
        1,
    )
    assert (valorant.default_bo, valorant.game_minutes) == (3, 40)
    assert valorant.rank_tiers[0].name == "輻能戰魂"
    assert valorant.rank_tiers[-1].name == "無排位"
    assert len(valorant.rank_tiers) == 10

    assert context.tournament_to_draw is not None
    tournament = service.get_tournament(
        session, tournament_id=context.tournament_to_draw
    )
    now = clock.now()
    assert tournament.name == "FLOW 校園盃 特戰英豪"
    assert tournament.organizer_id == organizer.id
    assert tournament.game_id == valorant.id
    assert tournament.status == TournamentStatus.OPEN
    assert tournament.capacity == 32
    assert tournament.registration_start == now - timedelta(hours=1)
    assert tournament.priority_end == now + timedelta(hours=23)
    assert tournament.registration_end == now + timedelta(days=3)
    assert tournament.start_at == now + timedelta(days=7)
    assert tournament.round_interval_minutes == 180
    assert (tournament.forfeit_minutes, tournament.appeal_minutes) == (15, 30)
    assert tournament.livestream_url is None

    # 只看這次建立的遊戲與賽事：測試資料庫可能留有其他併發測試提交的資料
    actors = session.exec(
        select(AuditLog.action, AuditLog.actor_id).where(
            col(AuditLog.action).in_(["game.created", "tournament.created"]),
            col(AuditLog.entity_id).in_([league.id, valorant.id, tournament.id]),
        )
    ).all()
    assert sorted(actors) == sorted(
        [
            ("game.created", admin_id),
            ("game.created", admin_id),
            ("tournament.created", organizer.id),
        ]
    )


@pytest.mark.usefixtures("admin_id")
def test_second_run_creates_nothing_and_keeps_tournament_to_draw(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    organizer = make_account(session, organizer=True)
    first = _context(organizer.id)
    tournaments.seed(session, first)
    games_after_first = len(service.list_games(session))
    audit_after_first = _audit_count(session)

    second = _context(organizer.id)
    with caplog.at_level(logging.INFO):
        tournaments.seed(session, second)

    assert len(service.list_games(session)) == games_after_first
    assert _audit_count(session) == audit_after_first
    assert second.tournament_to_draw == first.tournament_to_draw
    assert (
        len(service.list_organizer_tournaments(session, organizer_id=organizer.id)) == 1
    )
    assert caplog.text.count("Demo game already exists, reused") == 2
    assert "Demo tournament already exists, reused" in caplog.text


def test_existing_game_with_same_name_is_reused_unchanged(
    session: Session, admin_id: uuid.UUID
) -> None:
    existing = service.create_game(
        session,
        actor_id=admin_id,
        data=GameIn(
            name=" 特戰英豪 ",
            starters=6,
            substitutes=2,
            default_bo=1,
            game_minutes=30,
            score_type=ScoreType.WIN_LOSS,
            rank_tiers=[RankTierIn(name="自訂段位", score=1)],
        ),
    )
    organizer = make_account(session, organizer=True)
    context = _context(organizer.id)

    tournaments.seed(session, context)

    assert service.get_game(session, game_id=existing.id) == existing
    assert [g.id for g in service.list_games(session) if g.name == "特戰英豪"] == [
        existing.id
    ]
    assert context.tournament_to_draw is not None
    tournament = service.get_tournament(
        session, tournament_id=context.tournament_to_draw
    )
    assert tournament.game_id == existing.id


def test_existing_game_rejecting_schedule_skips_tournament(
    session: Session, admin_id: uuid.UUID, caplog: pytest.LogCaptureFixture
) -> None:
    # 每局 60 分鐘 × BO3：每輪間隔下限 225 > 180，建立賽事被拒絕
    service.create_game(
        session,
        actor_id=admin_id,
        data=GameIn(
            name="特戰英豪",
            starters=5,
            substitutes=1,
            default_bo=3,
            game_minutes=60,
            score_type=ScoreType.ROUNDS,
            rank_tiers=[RankTierIn(name="無排位", score=0)],
        ),
    )
    organizer = make_account(session, organizer=True)
    earlier = make_account(session)  # 前面步驟寫入的資料
    context = _context(organizer.id)

    with caplog.at_level(logging.WARNING):
        tournaments.seed(session, context)

    assert context.tournament_to_draw is None
    assert "ROUND_INTERVAL_TOO_SHORT" in caplog.text
    assert service.list_organizer_tournaments(session, organizer_id=organizer.id) == []
    # 前面步驟的資料、既有的同名遊戲與另一款示範遊戲都保留
    session.refresh(earlier)
    games = _games_by_name(session)
    assert games["特戰英豪"].game_minutes == 60
    assert "英雄聯盟" in games


@pytest.mark.usefixtures("admin_id")
def test_without_organizer_only_games_are_created(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    context = _context(None)

    with caplog.at_level(logging.INFO):
        tournaments.seed(session, context)

    assert {"英雄聯盟", "特戰英豪"} <= set(_games_by_name(session))
    assert context.tournament_to_draw is None
    assert "No demo organizer, demo tournament skipped" in caplog.text


def test_without_first_admin_step_is_skipped(
    session: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 指向一定不存在的 Email，不依賴測試資料庫裡有沒有第一個管理員
    monkeypatch.setattr(
        settings, "FIRST_ADMIN_EMAIL", f"missing-{uuid.uuid4().hex}@example.com"
    )
    organizer = make_account(session, organizer=True)
    context = _context(organizer.id)

    with caplog.at_level(logging.WARNING):
        tournaments.seed(session, context)

    # 只檢查示範遊戲：測試資料庫可能留有其他併發測試提交的遊戲
    assert not {"英雄聯盟", "特戰英豪"} & set(_games_by_name(session))
    assert context.tournament_to_draw is None
    assert "First platform admin not found" in caplog.text


@pytest.mark.usefixtures("admin_id")
def test_load_passes_demo_tournament_to_competition_step(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "demo-password")
    monkeypatch.setattr(settings, "DEMO_EMAIL_DOMAIN", "demo.example.com")

    with caplog.at_level(logging.INFO):
        assert load(session) is True

    assert "Demo tournament created" in caplog.text
    assert "No demo tournament to draw" not in caplog.text
    # competition 步驟確實拿到這場賽事（抽籤成功或因 registration 未就緒略過都會帶 id）
    [demo] = [
        t
        for t in service.list_public_tournaments(session)
        if t.name == tournaments.DEMO_TOURNAMENT_NAME
    ]
    competition_logs = [
        r.getMessage() for r in caplog.records if r.name == "app.demo_data.competition"
    ]
    assert any(str(demo.id) in message for message in competition_logs)
