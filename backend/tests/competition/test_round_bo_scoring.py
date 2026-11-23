"""Story 2.3：分輪 BO 套用到抽籤排程、登錄比分的勝局門檻與公開單場。

賽事一律是預設 BO1、4 強 BO3、決賽 BO5（每局 40 分鐘、棄權 15、申訴 30），
最小間隔：BO1 85 分鐘、BO3 165 分鐘、BO5 245 分鐘。
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock
from app.modules.competition import service
from app.modules.competition.models import CheckIn, Match, MatchRead
from app.modules.identity.models import Account
from tests.competition.conftest import FakeRegistration, draw_with_round_bo
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

START = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)


def _draw(
    session: Session, fake: FakeRegistration, team_count: int
) -> tuple[Account, list[MatchRead]]:
    tournament, bracket = draw_with_round_bo(session, fake, team_count)
    session.commit()
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    return organizer, bracket.matches


def _check_in_both(session: Session, match: Match | MatchRead) -> None:
    for team_id in (match.team_a_id, match.team_b_id):
        assert team_id is not None
        session.add(
            CheckIn(
                match_id=match.id,
                team_id=team_id,
                account_id=make_account(session).id,
                at=clock.now(),
            )
        )
    session.commit()


def test_draw_delays_round_after_bo3_semifinal(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 每輪間隔 85 分鐘＝BO1 的最小間隔：8 強（BO1）後不順延，
    # 4 強（BO3）後順延到 165 分鐘
    tournament, bracket = draw_with_round_bo(
        session, fake_registration, 8, round_interval_minutes=85
    )

    starts = {
        ("third" if m.is_third_place else m.round_no): m.scheduled_at
        for m in bracket.matches
    }
    second = START + timedelta(minutes=85)
    final = second + timedelta(minutes=165)
    assert starts == {1: START, 2: second, 3: final, "third": final}
    assert bracket.delayed_rounds == [3]
    read = service.get_bracket(session, tournament_id=tournament.id)
    assert read is not None
    assert read.delayed_rounds == [3]


def test_semifinal_needs_two_wins_when_semifinal_is_bo3(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    organizer, matches = _draw(session, fake_registration, 4)
    # 4 隊共 2 輪：第 1 輪就是四強
    semi = next(m for m in matches if m.round_no == 1)
    _check_in_both(session, semi)
    headers = bearer(token_for(client, organizer))
    base = f"{API}/tournaments/{semi.tournament_id}/matches/{semi.id}"

    state = client.get(f"{base}/score-entry", headers=headers).json()
    assert state["series"]["wins_needed"] == 2

    first = client.put(f"{base}/games/1", json={"winner_side": "a"}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["series"]["can_submit"] is False
    early = client.post(f"{base}/submit", headers=headers)
    assert early.json()["detail"]["code"] == "SERIES_NOT_DECIDED"

    second = client.put(f"{base}/games/2", json={"winner_side": "a"}, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["series"]["can_submit"] is True
    submitted = client.post(f"{base}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text


def test_third_place_uses_semifinal_bo_not_final_bo(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    organizer, matches = _draw(session, fake_registration, 4)
    semis = [m for m in matches if m.round_no == 1]
    third = next(m for m in matches if m.is_third_place)
    # 直接把兩場 4 強的敗隊放進季軍賽（略過送出結果與晉級）
    row = session.get(Match, third.id)
    assert row is not None
    row.team_a_id = semis[0].team_b_id
    row.team_b_id = semis[1].team_b_id
    session.add(row)
    session.commit()
    _check_in_both(session, row)
    headers = bearer(token_for(client, organizer))

    state = client.get(
        f"{API}/tournaments/{third.tournament_id}/matches/{third.id}/score-entry",
        headers=headers,
    ).json()

    # 季軍賽沿用 4 強的 BO3（先 2 勝），不是決賽 BO5 的先 3 勝
    assert state["series"]["wins_needed"] == 2


def test_public_match_detail_shows_round_bo(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    _organizer, matches = _draw(session, fake_registration, 8)
    best_of = {}
    for match in matches:
        response = client.get(
            f"{API}/tournaments/{match.tournament_id}/matches/{match.id}"
        )
        assert response.status_code == 200, response.text
        key = "third" if match.is_third_place else match.round_no
        best_of[key] = response.json()["best_of"]

    # 8 隊 3 輪：8 強用預設 BO1、4 強 BO3、決賽 BO5、季軍賽沿用 4 強
    assert best_of == {1: 1, 2: 3, 3: 5, "third": 3}
