"""Story 6.2 前置：重新比賽時清除報到紀錄與逐局比分（`clear_for_replay`）。

沿用 test_score_entry 的已抽籤賽事（M1 兩隊預設都已報到、BO3）；
場次狀態與結果欄位直接寫入，模擬申訴中的場次。
"""

# ruff: noqa: F811  (從 test_score_entry 匯入 fixture，參數同名是 pytest 的用法)

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, func, select

from app.core import audit, clock
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import repository, service
from app.modules.competition.models import (
    CheckIn,
    Match,
    MatchGame,
    MatchOutcome,
    MatchStatus,
)
from app.modules.tournaments import service as tournaments_service
from tests.competition.test_score_entry import (  # noqa: F401
    Factory,
    Setup,
    _put,
    make_setup,
    setup,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")


def _row(session: Session, setup: Setup, code: str = "M1") -> Match:
    session.expire_all()
    match = session.get(Match, setup.match_id(code))
    assert match is not None
    return match


def _appeal(
    session: Session,
    setup: Setup,
    *,
    outcome: MatchOutcome,
    winner: str | None,
    code: str = "M1",
) -> None:
    """把場次寫成申訴中，結果欄位填滿。"""
    match = _row(session, setup, code)
    now = clock.now()
    # confirmed_at 等欄位平常申訴中不會有值，這裡全填滿只為證明它們會被清除
    match.status = MatchStatus.APPEALED
    match.outcome = outcome
    match.winner_id = setup.team(winner, code) if winner else None
    match.submitted_by = setup.organizer.id
    match.submitted_at = now
    match.appeal_deadline = now + timedelta(minutes=30)
    match.confirmed_at = now
    match.forfeit_deadline = now
    session.add(match)
    session.commit()


def _counts(session: Session, setup: Setup, code: str = "M1") -> tuple[int, int]:
    match_id = setup.match_id(code)
    checks = session.exec(
        select(func.count()).select_from(CheckIn).where(CheckIn.match_id == match_id)
    ).one()
    games = session.exec(
        select(func.count())
        .select_from(MatchGame)
        .where(MatchGame.match_id == match_id)
    ).one()
    return checks, games


def _assert_zeroed(match: Match) -> None:
    assert match.outcome is None
    assert match.winner_id is None
    assert match.submitted_by is None
    assert match.submitted_at is None
    assert match.appeal_deadline is None
    assert match.confirmed_at is None
    assert match.forfeit_deadline is None
    assert (match.wins_a, match.wins_b) == (0, 0)


def _add_games(session: Session, setup: Setup, code: str = "M1") -> None:
    for no, side in enumerate("ab", start=1):
        session.add(
            MatchGame(
                match_id=setup.match_id(code),
                game_no=no,
                winner_side=side,
                recorded_by=setup.organizer.id,
                recorded_at=clock.now(),
            )
        )
    match = _row(session, setup, code)
    match.wins_a, match.wins_b = 1, 1
    session.add(match)
    session.commit()


def test_forfeit_with_one_check_in(session: Session, make_setup: Factory) -> None:
    setup = make_setup(check_in=("a",))
    _appeal(session, setup, outcome=MatchOutcome.FORFEIT, winner="a")

    cleared = service.clear_for_replay(session, match=_row(session, setup))

    assert [c.team_id for c in cleared.check_ins] == [setup.team("a")]
    assert cleared.outcome == MatchOutcome.FORFEIT
    assert cleared.winner_id == setup.team("a")
    assert cleared.games == []
    assert _counts(session, setup) == (0, 0)
    _assert_zeroed(_row(session, setup))


def test_double_forfeit_without_check_in(session: Session, make_setup: Factory) -> None:
    setup = make_setup(check_in=())
    _appeal(session, setup, outcome=MatchOutcome.DOUBLE_FORFEIT, winner=None)

    cleared = service.clear_for_replay(session, match=_row(session, setup))

    assert cleared.check_ins == []
    assert cleared.outcome == MatchOutcome.DOUBLE_FORFEIT
    assert cleared.winner_id is None
    _assert_zeroed(_row(session, setup))


def test_played_with_games(session: Session, setup: Setup) -> None:
    _add_games(session, setup)
    _appeal(session, setup, outcome=MatchOutcome.PLAYED, winner="a")

    cleared = service.clear_for_replay(session, match=_row(session, setup))

    assert [(g.game_no, g.winner_side) for g in cleared.games] == [(1, "a"), (2, "b")]
    assert (cleared.wins_a, cleared.wins_b) == (1, 1)
    assert len(cleared.check_ins) == 2
    assert _counts(session, setup) == (0, 0)
    _assert_zeroed(_row(session, setup))


@pytest.mark.parametrize(
    "status",
    [
        MatchStatus.SCHEDULED,
        MatchStatus.LIVE,
        MatchStatus.APPEAL_WINDOW,
        MatchStatus.CONFIRMED,
        MatchStatus.VOIDED,
    ],
)
def test_wrong_status_changes_nothing(
    session: Session, setup: Setup, status: MatchStatus
) -> None:
    _add_games(session, setup)
    match = _row(session, setup)
    match.status = status
    match.outcome = MatchOutcome.PLAYED
    match.winner_id = setup.team("a")
    match.forfeit_deadline = clock.now()
    session.add(match)
    session.commit()

    with pytest.raises(BusinessError) as error:
        service.clear_for_replay(session, match=_row(session, setup))

    assert error.value.code == "MATCH_INVALID_TRANSITION"
    assert error.value.status_code == 409
    assert _counts(session, setup) == (2, 2)
    row = _row(session, setup)
    assert row.status == status
    assert row.outcome == MatchOutcome.PLAYED
    assert row.winner_id == setup.team("a")
    assert row.forfeit_deadline == clock.now()
    assert (row.wins_a, row.wins_b) == (1, 1)


def test_other_matches_untouched(session: Session, setup: Setup) -> None:
    _add_games(session, setup, "M2")
    session.add(
        CheckIn(
            match_id=setup.match_id("M2"),
            team_id=setup.team("a", "M2"),
            account_id=setup.organizer.id,
            at=clock.now(),
        )
    )
    session.commit()
    _appeal(session, setup, outcome=MatchOutcome.FORFEIT, winner="a")

    service.clear_for_replay(session, match=_row(session, setup))

    other = _row(session, setup, "M2")
    assert _counts(session, setup, "M2") == (1, 2)
    assert (other.wins_a, other.wins_b) == (1, 1)


def test_no_audit_or_event_and_structure_kept(session: Session, setup: Setup) -> None:
    _appeal(session, setup, outcome=MatchOutcome.FORFEIT, winner="a")
    before = _row(session, setup)
    kept = (
        before.scheduled_at,
        before.team_a_id,
        before.team_b_id,
        before.referee_account_id,
        before.next_match_id,
        before.loser_next_match_id,
    )
    audits = len(audit.list_for_tournament(session, setup.tournament_id))
    events = session.exec(select(func.count()).select_from(OutboxEvent)).one()

    service.clear_for_replay(session, match=before)

    after = _row(session, setup)
    assert after.status == MatchStatus.APPEALED
    assert kept == (
        after.scheduled_at,
        after.team_a_id,
        after.team_b_id,
        after.referee_account_id,
        after.next_match_id,
        after.loser_next_match_id,
    )
    assert len(audit.list_for_tournament(session, setup.tournament_id)) == audits
    assert session.exec(select(func.count()).select_from(OutboxEvent)).one() == events


def test_contract_replay_sequence(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _add_games(session, setup)
    _appeal(session, setup, outcome=MatchOutcome.PLAYED, winner="a")

    # B 的 replay_match 約定流程
    match = _row(session, setup)
    service.clear_for_replay(session, match=match)
    service.transition_match(session, match=match, to=MatchStatus.SCHEDULED)
    new_time = clock.now() + timedelta(hours=2)
    match.scheduled_at = new_time
    session.add(match)
    service.start_forfeit_clock(session, match=match)
    session.commit()

    row = _row(session, setup)
    assert row.status == MatchStatus.SCHEDULED
    minutes = tournaments_service.get_tournament(
        session, tournament_id=setup.tournament_id
    ).forfeit_minutes
    deadline = max(new_time, clock.now()) + timedelta(minutes=minutes)
    assert row.forfeit_deadline == deadline
    # 沒有任何報到、期限到了：判棄權候選會選到它
    assert row.id in service.list_forfeit_due(session, now=deadline)
    assert row.id not in service.list_forfeit_due(
        session, now=deadline - timedelta(seconds=1)
    )
    # 兩隊都能重新報到（不會撞唯一鍵）
    for side in ("a", "b"):
        assert repository.add_check_in(
            session,
            CheckIn(
                match_id=setup.match_id(),
                team_id=setup.team(side),
                account_id=setup.organizer.id,
                at=clock.now(),
            ),
        )
    session.commit()

    response = _put(client, setup, 1, {"winner_side": "b"})

    assert response.status_code == 200, response.text
    assert response.json()["games"] == [
        {"game_no": 1, "winner_side": "b", "score_a": None, "score_b": None}
    ]
    [record] = [
        r
        for r in audit.list_for_tournament(session, setup.tournament_id)
        if r.action == "match.game_recorded"
    ]
    assert record.before == {"status": "scheduled"}  # 新增，不是覆寫
    rows = list(
        session.exec(
            select(MatchGame).where(col(MatchGame.match_id) == setup.match_id())
        )
    )
    assert len(rows) == 1
    assert _row(session, setup).status == MatchStatus.LIVE
