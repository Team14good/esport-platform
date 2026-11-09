"""Story 6.2：competition 端的申訴處理（`uphold_result`、`correct_result`、`replay_match`）。

沿用 test_score_entry 的已抽籤 8 隊賽事（賽程已公布、BO3）；M1 直接寫成申訴中。
frozen_clock 凍結在 2026-10-18 11:00 UTC，第一輪 2026-10-26 11:00 開打。
"""

# ruff: noqa: F811  (從 test_score_entry 匯入 fixture，參數同名是 pytest 的用法)

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, col, select

from app.core import audit, clock
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import service
from app.modules.competition.models import (
    CheckIn,
    GameScoreIn,
    Match,
    MatchGame,
    MatchOutcome,
    MatchStatus,
)
from app.modules.tournaments.models import ScoreType
from tests.competition.test_score_entry import (  # noqa: F401
    Factory,
    Setup,
    make_setup,
    setup,
)
from tests.helpers import make_account

pytestmark = pytest.mark.usefixtures("frozen_clock")

REPLAY_AT = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def _row(session: Session, setup: Setup, code: str = "M1") -> Match:
    session.expire_all()
    match = session.get(Match, setup.match_id(code))
    assert match is not None
    return match


def _appealed(
    session: Session,
    setup: Setup,
    *,
    outcome: MatchOutcome = MatchOutcome.PLAYED,
    winner: str | None = "a",
    sides: str = "aa",
    scores: list[tuple[int, int]] | None = None,
    code: str = "M1",
) -> None:
    """把場次寫成申訴中；played 時依 `sides`（或 `scores`）寫入各局。"""
    match = _row(session, setup, code)
    now = clock.now()
    if outcome == MatchOutcome.PLAYED:
        rows = scores or [(1, 0) if s == "a" else (0, 1) for s in sides]
        for no, (a, b) in enumerate(rows, start=1):
            session.add(
                MatchGame(
                    match_id=match.id,
                    game_no=no,
                    winner_side="a" if a > b else "b",
                    score_a=a if scores else None,
                    score_b=b if scores else None,
                    recorded_by=setup.organizer.id,
                    recorded_at=now,
                )
            )
        match.wins_a = sum(1 for a, b in rows if a > b)
        match.wins_b = len(rows) - match.wins_a
        match.submitted_by = setup.organizer.id
        match.submitted_at = now
    match.status = MatchStatus.APPEALED
    match.outcome = outcome
    match.winner_id = setup.team(winner, code) if winner else None
    match.appeal_deadline = now + timedelta(minutes=30)
    session.add(match)
    session.commit()


def _games(session: Session, setup: Setup, code: str = "M1") -> list[tuple[str, ...]]:
    session.expire_all()
    rows = session.exec(
        select(MatchGame)
        .where(MatchGame.match_id == setup.match_id(code))
        .order_by(col(MatchGame.game_no))
    )
    return [(g.winner_side, str(g.score_a), str(g.score_b)) for g in rows]


def _next_teams(session: Session, setup: Setup, code: str = "M1") -> set[object]:
    nxt = _row(session, setup, setup.next_code(code))
    return {nxt.team_a_id, nxt.team_b_id} - {None}


def _actions(session: Session, setup: Setup) -> list[str]:
    return [r.action for r in audit.list_for_tournament(session, setup.tournament_id)]


def _outbox(session: Session, event_type: str) -> list[dict[str, object]]:
    statement = select(OutboxEvent).where(OutboxEvent.type == event_type)
    return [event.payload for event in session.exec(statement)]


def _wl(*sides: str) -> list[GameScoreIn]:
    return [GameScoreIn(winner_side="a" if s == "a" else "b") for s in sides]


def _error(excinfo: pytest.ExceptionInfo[BusinessError]) -> tuple[str, int]:
    return excinfo.value.code, excinfo.value.status_code


# ---------------------------------------------------------------- 維持原結果


def test_uphold_confirms_and_advances_existing_winner(
    session: Session, setup: Setup
) -> None:
    _appealed(session, setup)

    read = service.uphold_result(
        session, match_id=setup.match_id(), actor_id=setup.organizer.id
    )
    session.commit()

    assert read.status == MatchStatus.CONFIRMED
    assert read.outcome == MatchOutcome.PLAYED
    assert read.winner_id == setup.team("a")
    assert setup.team("a") in _next_teams(session, setup)
    assert _row(session, setup).confirmed_at is not None
    assert "match.confirmed" in _actions(session, setup)


def test_uphold_double_forfeit_keeps_no_winner(session: Session, setup: Setup) -> None:
    _appealed(session, setup, outcome=MatchOutcome.DOUBLE_FORFEIT, winner=None)

    read = service.uphold_result(
        session, match_id=setup.match_id(), actor_id=setup.organizer.id
    )

    assert read.status == MatchStatus.CONFIRMED
    assert read.outcome == MatchOutcome.DOUBLE_FORFEIT
    assert read.winner_id is None


@pytest.mark.parametrize(
    "status", [MatchStatus.APPEAL_WINDOW, MatchStatus.CONFIRMED, MatchStatus.LIVE]
)
def test_uphold_rejects_match_not_appealed(
    session: Session, setup: Setup, status: MatchStatus
) -> None:
    _appealed(session, setup)
    match = _row(session, setup)
    match.status = status
    session.add(match)
    session.commit()

    with pytest.raises(BusinessError) as excinfo:
        service.uphold_result(
            session, match_id=setup.match_id(), actor_id=setup.organizer.id
        )

    assert _error(excinfo) == ("MATCH_INVALID_TRANSITION", 409)
    assert _row(session, setup).status == status


# ---------------------------------------------------------------- 更正結果


def test_correct_replaces_games_and_advances_new_winner(
    session: Session, setup: Setup
) -> None:
    _appealed(session, setup, sides="aa")

    result = service.correct_result(
        session,
        match_id=setup.match_id(),
        games=_wl("a", "b", "b"),
        actor_id=setup.organizer.id,
    )
    session.commit()

    assert [g.winner_side for g in result.before_games] == ["a", "a"]
    assert [g.winner_side for g in result.after_games] == ["a", "b", "b"]
    assert result.winner_id == setup.team("b")
    match = _row(session, setup)
    assert match.status == MatchStatus.CONFIRMED
    assert match.outcome == MatchOutcome.PLAYED
    assert match.winner_id == setup.team("b")
    assert (match.wins_a, match.wins_b) == (1, 2)
    assert [g[0] for g in _games(session, setup)] == ["a", "b", "b"]
    teams = _next_teams(session, setup)
    assert setup.team("b") in teams
    assert setup.team("a") not in teams
    payloads = _outbox(session, "MatchResultConfirmed")
    assert {"match_id": str(match.id), "winner_id": str(setup.team("b"))} in payloads


def test_correct_rounds_score_type(session: Session, make_setup: Factory) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)
    _appealed(session, setup, scores=[(13, 5), (13, 7)])

    result = service.correct_result(
        session,
        match_id=setup.match_id(),
        games=[
            GameScoreIn(score_a=13, score_b=5),
            GameScoreIn(score_a=11, score_b=13),
            GameScoreIn(score_a=13, score_b=9),
        ],
        actor_id=setup.organizer.id,
    )

    assert result.winner_id == setup.team("a")
    assert _games(session, setup) == [
        ("a", "13", "5"),
        ("b", "11", "13"),
        ("a", "13", "9"),
    ]


@pytest.mark.parametrize(
    ("games", "code"),
    [
        (_wl("a"), "SERIES_NOT_DECIDED"),
        ([], "SERIES_NOT_DECIDED"),
        (_wl("b", "b", "a"), "REDUNDANT_GAMES"),
        ([GameScoreIn(score_a=3, score_b=1)], "SCORE_INVALID"),
    ],
)
def test_correct_rejections_change_nothing(
    session: Session, setup: Setup, games: list[GameScoreIn], code: str
) -> None:
    _appealed(session, setup, sides="aa")
    before = _games(session, setup)
    actions = _actions(session, setup)

    with pytest.raises(BusinessError) as excinfo:
        service.correct_result(
            session,
            match_id=setup.match_id(),
            games=games,
            actor_id=setup.organizer.id,
        )
    session.rollback()

    assert _error(excinfo) == (code, 409)
    match = _row(session, setup)
    assert match.status == MatchStatus.APPEALED
    assert match.winner_id == setup.team("a")
    assert _games(session, setup) == before
    assert _actions(session, setup) == actions


def test_correct_rounds_tie_is_rejected(session: Session, make_setup: Factory) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)
    _appealed(session, setup, scores=[(13, 5), (13, 7)])

    with pytest.raises(BusinessError) as excinfo:
        service.correct_result(
            session,
            match_id=setup.match_id(),
            games=[GameScoreIn(score_a=13, score_b=13)],
            actor_id=setup.organizer.id,
        )

    assert _error(excinfo) == ("SCORE_TIE", 409)


@pytest.mark.parametrize("outcome", [MatchOutcome.FORFEIT, MatchOutcome.DOUBLE_FORFEIT])
def test_correct_only_for_played(
    session: Session, setup: Setup, outcome: MatchOutcome
) -> None:
    _appealed(session, setup, outcome=outcome, winner="a")

    with pytest.raises(BusinessError) as excinfo:
        service.correct_result(
            session,
            match_id=setup.match_id(),
            games=_wl("b", "b"),
            actor_id=setup.organizer.id,
        )

    assert _error(excinfo) == ("CORRECTION_ONLY_FOR_PLAYED", 409)


# ---------------------------------------------------------------- 重新比賽


@pytest.mark.parametrize(
    ("outcome", "winner"),
    [(MatchOutcome.FORFEIT, "a"), (MatchOutcome.DOUBLE_FORFEIT, None)],
)
def test_replay_resets_match_and_restarts_forfeit_clock(
    session: Session, make_setup: Factory, outcome: MatchOutcome, winner: str | None
) -> None:
    setup = make_setup(check_in=("a",))
    referee = make_account(session)
    _appealed(session, setup, outcome=outcome, winner=winner)
    match = _row(session, setup)
    match.referee_account_id = referee.id
    session.add(match)
    session.commit()

    cleared = service.replay_match(
        session,
        match_id=setup.match_id(),
        scheduled_at=REPLAY_AT,
        actor_id=setup.organizer.id,
    )
    session.commit()

    assert cleared.outcome == outcome
    assert [c.team_id for c in cleared.check_ins] == [setup.team("a")]
    match = _row(session, setup)
    assert match.status == MatchStatus.SCHEDULED
    assert match.outcome is None
    assert match.winner_id is None
    assert match.appeal_deadline is None
    assert match.scheduled_at == REPLAY_AT
    # 棄權時限 15 分鐘，從新的預定時間起算
    assert match.forfeit_deadline == REPLAY_AT + timedelta(minutes=15)
    assert match.referee_account_id == referee.id
    checks = session.exec(select(CheckIn).where(CheckIn.match_id == match.id)).all()
    assert checks == []
    records = [
        r
        for r in audit.list_for_tournament(session, setup.tournament_id)
        if r.action == "match.replay_scheduled"
    ]
    assert len(records) == 1
    assert records[0].actor_id == setup.organizer.id
    assert records[0].before is not None and records[0].after is not None
    assert records[0].before["outcome"] == outcome.value
    assert records[0].after["status"] == MatchStatus.SCHEDULED.value
    assert [
        p
        for p in _outbox(session, "MatchRescheduled")
        if p["match_id"] == str(match.id)
    ]


def test_replay_only_for_forfeit(session: Session, setup: Setup) -> None:
    _appealed(session, setup)

    with pytest.raises(BusinessError) as excinfo:
        service.replay_match(
            session,
            match_id=setup.match_id(),
            scheduled_at=REPLAY_AT,
            actor_id=setup.organizer.id,
        )

    assert _error(excinfo) == ("REPLAY_ONLY_FOR_FORFEIT", 409)
    assert _row(session, setup).status == MatchStatus.APPEALED


def test_replay_time_out_of_range_changes_nothing(
    session: Session, make_setup: Factory
) -> None:
    setup = make_setup(check_in=("a",))
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT, winner="a")

    with pytest.raises(BusinessError) as excinfo:
        service.replay_match(
            session,
            match_id=setup.match_id(),
            scheduled_at=clock.now() - timedelta(hours=1),
            actor_id=setup.organizer.id,
        )
    session.rollback()

    assert _error(excinfo) == ("RESCHEDULE_BEFORE_NOW", 409)
    match = _row(session, setup)
    assert match.status == MatchStatus.APPEALED
    assert match.outcome == MatchOutcome.FORFEIT
    assert session.exec(select(CheckIn).where(CheckIn.match_id == match.id)).all()


def test_replay_window_accepts_double_forfeit(session: Session, setup: Setup) -> None:
    _appealed(session, setup, outcome=MatchOutcome.DOUBLE_FORFEIT, winner=None)

    info = service.get_replay_window(session, match_id=setup.match_id())

    assert info.can_reschedule is True
    assert info.earliest is not None
