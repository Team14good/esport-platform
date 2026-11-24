"""Story 6.3：等待申訴結果的下一場暫停報到與棄權計時（確認 5.1、5.2、5.5 的既有行為），
以及公開單場的 `awaiting_appeal`。

沿用 test_check_in 的 8 隊賽事：第 1 輪 2026-10-26 11:00、第 2 輪 14:00、棄權時限 15 分鐘。
M1 申訴中、M2～M4 已確認時，M5 只有 M2 的勝隊、在等 M1 的申訴結果；同輪的 M6 兩隊已確定。
季軍賽在等準決賽申訴的情境另見 test_appeal_resolution.py（更正後敗隊進季軍賽）。
"""

# ruff: noqa: F811  (從 test_check_in 匯入 fixture，參數同名是 pytest 的用法)

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.competition import service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.identity.models import Account
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, FrozenClockLike
from tests.competition.test_check_in import (  # noqa: F401  setup 是 fixture
    Setup,
    setup,
)
from tests.competition.test_confirm_advance import (
    _confirm,
    _eight_to_semis,
    _rows,
)
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

ROUND_1 = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)
ROUND_2 = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)
FORFEIT = timedelta(minutes=15)


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _check_in_url(setup: Setup, match_id: uuid.UUID) -> str:
    return f"{API}/tournaments/{setup.tournament_id}/matches/{match_id}/check-in"


def _public(client: TestClient, setup: Setup, match_id: uuid.UUID) -> dict[str, object]:
    response = client.get(f"{API}/tournaments/{setup.tournament_id}/matches/{match_id}")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _m1_appealed(
    session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> dict[str, Match]:
    """M1 申訴中（原判 A 方勝），M2～M4 由 A 方勝並確認。"""
    frozen_clock.set(ROUND_1 + timedelta(hours=1))
    rows = _rows(session, setup.tournament_id)
    m1 = rows["M1"]
    m1.status = MatchStatus.APPEALED
    m1.outcome = MatchOutcome.PLAYED
    m1.winner_id = m1.team_a_id
    m1.appeal_deadline = ROUND_1 + timedelta(hours=1, minutes=30)
    session.add(m1)
    session.flush()
    for code in ("M2", "M3", "M4"):
        _confirm(session, rows[code], MatchOutcome.PLAYED, rows[code].team_a_id)
    session.commit()
    return _rows(session, setup.tournament_id)


def test_match_awaiting_appeal_is_paused_while_same_round_runs(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    rows = _m1_appealed(session, setup, frozen_clock)
    m5, m6 = rows["M5"], rows["M6"]
    assert m5.team_a_id is None and m5.team_b_id is not None
    assert m6.team_a_id is not None and m6.team_b_id is not None
    assert m5.forfeit_deadline is None
    assert m6.forfeit_deadline == ROUND_2 + FORFEIT

    # 到了第 2 輪的報到開放時間：M5 不開放報到，M6 照常
    frozen_clock.set(ROUND_2 - timedelta(minutes=30))
    response = client.post(
        _check_in_url(setup, m5.id),
        headers=_headers(client, setup.captains[m5.team_b_id]),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MATCH_TEAMS_PENDING"
    response = client.post(
        _check_in_url(setup, m6.id),
        headers=_headers(client, setup.captains[m6.team_a_id]),
    )
    assert response.status_code == 201, response.text

    paused = _public(client, setup, m5.id)
    assert paused["awaiting_appeal"] is True
    assert paused["forfeit_deadline"] is None
    other = _public(client, setup, m6.id)
    assert other["awaiting_appeal"] is False

    # 過了 M6 的棄權期限：只有 M6 要判棄權，M5 不判
    frozen_clock.set(ROUND_2 + FORFEIT + timedelta(minutes=5))
    due = service.list_forfeit_due(session, now=frozen_clock.now())
    assert m6.id in due
    assert m5.id not in due


def test_resolved_after_scheduled_time_restarts_forfeit_clock_from_now(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    rows = _m1_appealed(session, setup, frozen_clock)
    m5_id = rows["M5"].id
    resolved_at = ROUND_2 + timedelta(minutes=40)
    frozen_clock.set(resolved_at)

    tournaments_service.lock_tournament(session, tournament_id=setup.tournament_id)
    service.uphold_result(
        session, match_id=rows["M1"].id, actor_id=make_account(session).id
    )
    session.commit()

    m5 = _rows(session, setup.tournament_id)["M5"]
    assert m5.team_a_id is not None and m5.team_b_id is not None
    assert m5.forfeit_deadline == resolved_at + FORFEIT
    detail = _public(client, setup, m5_id)
    assert detail["awaiting_appeal"] is False
    assert detail["forfeit_deadline"] is not None
    assert datetime.fromisoformat(str(detail["forfeit_deadline"])) == (
        resolved_at + FORFEIT
    )
    # 已過報到開放時間：立即可以報到
    response = client.post(
        _check_in_url(setup, m5_id),
        headers=_headers(client, setup.captains[m5.team_a_id]),
    )
    assert response.status_code == 201, response.text


def test_final_and_third_place_both_await_semifinal_appeal(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, rows = _eight_to_semis(session, fake_registration)
    _confirm(session, rows["M6"], MatchOutcome.PLAYED, rows["M6"].team_a_id)
    m5 = _rows(session, tournament_id)["M5"]
    m5.status = MatchStatus.APPEALED
    m5.outcome = MatchOutcome.PLAYED
    m5.winner_id = m5.team_a_id
    session.add(m5)
    session.flush()

    def awaiting(code: str) -> bool:
        return service.get_public_match(
            session, tournament_id=tournament_id, match_id=rows[code].id
        ).awaiting_appeal

    assert awaiting("M7") is True
    assert awaiting("M8") is True
    assert awaiting("M5") is False


def test_cancelled_tournament_is_not_awaiting_appeal(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    rows = _m1_appealed(session, setup, frozen_clock)
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.CANCELLED
    session.add(row)
    session.commit()

    assert _public(client, setup, rows["M5"].id)["awaiting_appeal"] is False


@pytest.mark.parametrize(
    "feeder_status",
    [MatchStatus.SCHEDULED, MatchStatus.LIVE, MatchStatus.APPEAL_WINDOW],
)
def test_empty_side_whose_feeder_is_not_appealed_is_not_awaiting(
    session: Session,
    fake_registration: FakeRegistration,
    feeder_status: MatchStatus,
) -> None:
    """M7、M8 的一方空著，但來源 M5 還沒進入申訴中：不是在等申訴結果。"""
    tournament_id, rows = _eight_to_semis(session, fake_registration)
    _confirm(session, rows["M6"], MatchOutcome.PLAYED, rows["M6"].team_a_id)
    m5 = _rows(session, tournament_id)["M5"]
    m5.status = feeder_status
    session.add(m5)
    session.flush()

    for code in ("M7", "M8"):
        detail = service.get_public_match(
            session, tournament_id=tournament_id, match_id=rows[code].id
        )
        assert detail.status == MatchStatus.SCHEDULED
        assert (detail.team_a is None) != (detail.team_b is None)
        assert detail.awaiting_appeal is False
