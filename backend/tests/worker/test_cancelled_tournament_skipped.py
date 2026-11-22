"""Story 2.6：賽事取消後，worker 的判棄權、申訴期滿確認、賽事開始都略過、狀態不變。

這三個工作本身的檢查已存在（spec Decisions：不改既有 worker），這裡經真正的
`cancel_tournament` 取消賽事後跑一次 `run_once`，確認行為。

8 隊抽籤後第一輪 M1～M4 排在 2026-10-26 11:00 UTC，棄權期限 11:15，
報到在開賽前 30 分鐘開放（tests/competition/conftest.py 的預設）。
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.audit import AuditLog
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from app.worker import run_once
from app.worker.jobs import (
    confirm_expired_appeals,
    judge_forfeits,
    start_due_tournaments,
)
from tests.competition.conftest import (  # noqa: F401  fake_registration 是 fixture
    FakeRegistration,
    draw_with,
    fake_registration,
)
from tests.conftest import FrozenClock

pytestmark = pytest.mark.usefixtures("fake_registration")

FIRST_ROUND_AT = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)


def _cancel(session: Session, tournament: TournamentRead) -> None:
    tournaments_service.cancel_tournament(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )
    session.commit()


def _status_audit_count(session: Session, tournament_id: uuid.UUID) -> int:
    return len(
        session.exec(
            select(AuditLog).where(
                AuditLog.tournament_id == tournament_id,
                AuditLog.action == "tournament.status_changed",
            )
        ).all()
    )


def _status(session: Session, tournament_id: uuid.UUID) -> TournamentStatus:
    return tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    ).status


def test_judge_forfeits_skips_cancelled_tournament(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,  # noqa: F811
    frozen_clock: FrozenClock,
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 8)
    _cancel(session, tournament)
    audits_before = _status_audit_count(session, tournament.id)
    frozen_clock.set(FIRST_ROUND_AT + timedelta(minutes=15))  # 棄權期限已到、無人報到

    run_once([judge_forfeits], session_factory=session_factory)
    session.expire_all()

    for summary in bracket.matches:
        match = session.get(Match, summary.id)
        assert match is not None
        assert match.status == MatchStatus.SCHEDULED
    forfeits = session.exec(
        select(AuditLog).where(AuditLog.action == "match.forfeited")
    ).all()
    assert forfeits == []
    assert _status_audit_count(session, tournament.id) == audits_before
    assert _status(session, tournament.id) == TournamentStatus.CANCELLED


def test_confirm_expired_appeals_skips_cancelled_tournament(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,  # noqa: F811
    frozen_clock: FrozenClock,
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 2)
    appeal_deadline = FIRST_ROUND_AT + timedelta(minutes=30)
    final = session.get(Match, bracket.matches[0].id)
    assert final is not None
    final.status = MatchStatus.APPEAL_WINDOW
    final.outcome = MatchOutcome.PLAYED
    final.winner_id = fake_registration.teams[1]
    final.appeal_deadline = appeal_deadline
    session.add(final)
    _cancel(session, tournament)
    audits_before = _status_audit_count(session, tournament.id)

    frozen_clock.set(appeal_deadline)  # 申訴期滿
    run_once([confirm_expired_appeals], session_factory=session_factory)
    session.expire_all()

    final = session.get(Match, bracket.matches[0].id)
    assert final is not None
    assert final.status == MatchStatus.APPEAL_WINDOW
    assert final.confirmed_at is None
    assert _status_audit_count(session, tournament.id) == audits_before
    assert _status(session, tournament.id) == TournamentStatus.CANCELLED


def test_start_due_tournaments_skips_cancelled_tournament(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,  # noqa: F811
    frozen_clock: FrozenClock,
) -> None:
    tournament, _ = draw_with(session, fake_registration, 8)
    _cancel(session, tournament)
    audits_before = _status_audit_count(session, tournament.id)
    frozen_clock.set(FIRST_ROUND_AT - timedelta(minutes=30))  # 報到開放＝賽事開始

    run_once([start_due_tournaments], session_factory=session_factory)
    session.expire_all()

    assert _status(session, tournament.id) == TournamentStatus.CANCELLED
    assert _status_audit_count(session, tournament.id) == audits_before
