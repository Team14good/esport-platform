"""Story 4.1 第二階段：抽籤與公開對戰樹 API。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.competition import service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.tournaments.models import TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    draw_with,
    tournament_in,
)
from tests.helpers import API, bearer, make_account, member_headers, token_for

S = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

PUBLIC_MATCH_KEYS = {
    "id",
    "code",
    "round_no",
    "slot_no",
    "is_third_place",
    "team_a",
    "team_b",
    "source_a",
    "source_b",
    "bye_a",
    "bye_b",
    "scheduled_at",
    "status",
    "outcome",
    "winner_id",
    "wins_a",
    "wins_b",
}


def _owner_and_tournament(
    client: TestClient, session: Session, status: TournamentStatus = S.CLOSED
) -> tuple[dict[str, str], uuid.UUID]:
    organizer = make_account(session, organizer=True)
    tournament = tournament_in(session, status, organizer=organizer)
    return bearer(token_for(client, organizer)), tournament.id


def test_owner_draws_and_public_bracket_is_visible(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    headers, tournament_id = _owner_and_tournament(client, session)
    fake_registration.set_team_count(8)

    response = client.post(f"{API}/tournaments/{tournament_id}/draw", headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["size"], body["rounds"], body["delayed_rounds"]) == (8, 3, [])
    assert len(body["matches"]) == 8
    assert body["tournament_id"] == str(tournament_id)

    public = client.get(f"{API}/tournaments/{tournament_id}/bracket")

    assert public.status_code == 200, public.text
    data = public.json()
    assert set(data) == {
        "tournament_id",
        "rounds",
        "round_names",
        "matches",
        "podium",
        "updated_at",
    }
    assert data["podium"] is None
    assert data["round_names"] == ["8 強", "4 強", "決賽"]
    assert datetime.fromisoformat(data["updated_at"]) == datetime(
        2026, 10, 18, 11, 0, tzinfo=UTC
    )
    matches = {m["code"]: m for m in data["matches"]}
    assert [m["code"] for m in data["matches"]] == [
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
        "M6",
        "M7",
        "M8",
    ]
    for match in data["matches"]:
        assert set(match) == PUBLIC_MATCH_KEYS
    for team in (matches["M1"]["team_a"], matches["M1"]["team_b"]):
        assert set(team) == {"id", "name"}
        assert team["name"].startswith("隊伍")
    assert (matches["M1"]["source_a"], matches["M1"]["source_b"]) == (None, None)
    assert (matches["M5"]["team_a"], matches["M5"]["team_b"]) == (None, None)
    assert (matches["M5"]["source_a"], matches["M5"]["source_b"]) == (
        "M1 勝者",
        "M2 勝者",
    )
    assert (matches["M7"]["source_a"], matches["M7"]["source_b"]) == (
        "M5 勝者",
        "M6 勝者",
    )
    assert matches["M8"]["is_third_place"] is True
    assert (matches["M8"]["source_a"], matches["M8"]["source_b"]) == (
        "M5 敗者",
        "M6 敗者",
    )
    assert datetime.fromisoformat(matches["M8"]["scheduled_at"]) == datetime(
        2026, 10, 26, 17, 0, tzinfo=UTC
    )
    assert "@" not in public.text


def test_public_bracket_marks_bye_sides_and_unknown_names(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    headers, tournament_id = _owner_and_tournament(client, session, S.OPEN)
    fake_registration.set_team_count(10)
    assert (
        client.post(
            f"{API}/tournaments/{tournament_id}/draw", headers=headers
        ).status_code
        == 201
    )
    fake_registration.names = {}

    data = client.get(f"{API}/tournaments/{tournament_id}/bracket").json()

    matches = {m["code"]: m for m in data["matches"]}
    assert data["round_names"] == ["16 強", "8 強", "4 強", "決賽"]
    assert [
        (matches[c]["bye_a"], matches[c]["bye_b"]) for c in ("M3", "M4", "M5", "M6")
    ] == [(True, True), (True, False), (True, True), (True, False)]
    # 兩方都是輪空隊伍：都已入座，沒有待定列
    assert (matches["M3"]["source_a"], matches["M3"]["source_b"]) == (None, None)
    assert matches["M3"]["team_a"] is not None
    assert matches["M3"]["team_b"] is not None
    # 輪空一方已入座，另一方待定
    assert matches["M4"]["team_a"]["name"] == "未知隊伍"
    assert matches["M4"]["team_b"] is None
    assert matches["M4"]["source_a"] is None
    assert matches["M4"]["source_b"] == "M1 勝者"


def test_public_bracket_nine_teams_three_double_byes(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 9 隊（P=16、7 支輪空）：第一輪只有 M1（位置 8），第二輪 M2～M4 兩方都是輪空
    tournament, _bracket = draw_with(session, fake_registration, 9)

    public = service.get_public_bracket(session, tournament_id=tournament.id)

    assert public is not None
    matches = {m.code: m for m in public.matches}
    assert len(matches) == 9
    assert {
        code: (m.bye_a, m.bye_b, m.source_a, m.source_b)
        for code, m in matches.items()
        if m.round_no <= 2
    } == {
        "M1": (False, False, None, None),
        "M2": (True, True, None, None),
        "M3": (True, True, None, None),
        "M4": (True, True, None, None),
        "M5": (True, False, None, "M1 勝者"),
    }
    assert (matches["M6"].source_a, matches["M6"].source_b) == ("M2 勝者", "M3 勝者")


def test_walkover_empty_side_has_no_source(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 直接在資料庫造出狀態：M5 已以 walkover 確認，a 方有隊伍、b 方確定不會有隊伍；
    # 對照組 M6 仍待定，兩方都顯示待定列
    tournament, bracket = draw_with(session, fake_registration, 8)
    by_code = {m.code: m for m in bracket.matches}
    winner = by_code["M1"].team_a_id
    row = session.get(Match, by_code["M5"].id)
    assert row is not None
    row.team_a_id = winner
    row.status = MatchStatus.CONFIRMED
    row.outcome = MatchOutcome.WALKOVER
    row.winner_id = winner
    session.add(row)
    session.flush()

    public = service.get_public_bracket(session, tournament_id=tournament.id)

    assert public is not None
    matches = {m.code: m for m in public.matches}
    assert (matches["M5"].source_a, matches["M5"].source_b) == (None, None)
    assert matches["M5"].team_b is None
    assert (matches["M6"].source_a, matches["M6"].source_b) == ("M3 勝者", "M4 勝者")


def test_voided_third_place_has_no_source(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 季軍賽 M8 已取消、兩方都沒有隊伍：不再顯示「M5 敗者」「M6 敗者」
    tournament, bracket = draw_with(session, fake_registration, 8)
    third = next(m for m in bracket.matches if m.code == "M8")
    row = session.get(Match, third.id)
    assert row is not None
    row.status = MatchStatus.VOIDED
    session.add(row)
    session.flush()

    public = service.get_public_bracket(session, tournament_id=tournament.id)

    assert public is not None
    matches = {m.code: m for m in public.matches}
    assert matches["M8"].is_third_place is True
    assert (matches["M8"].source_a, matches["M8"].source_b) == (None, None)
    assert (matches["M7"].source_a, matches["M7"].source_b) == ("M5 勝者", "M6 勝者")


def test_public_bracket_updated_at_follows_match_changes(
    client: TestClient,
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 8)
    frozen_clock.advance(timedelta(minutes=5))
    m1 = next(m for m in bracket.matches if m.code == "M1")

    match = service.lock_match(session, match_id=m1.id)
    service.transition_match(session, match=match, to=MatchStatus.LIVE)
    session.commit()

    data = client.get(f"{API}/tournaments/{tournament.id}/bracket").json()

    assert datetime.fromisoformat(data["updated_at"]) == datetime(
        2026, 10, 18, 11, 5, tzinfo=UTC
    )


def test_public_bracket_before_draw_is_404(
    client: TestClient, session: Session
) -> None:
    tournament = tournament_in(session, S.CLOSED)

    for tournament_id in (tournament.id, uuid.uuid4()):
        response = client.get(f"{API}/tournaments/{tournament_id}/bracket")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "BRACKET_NOT_FOUND"


def test_draw_without_token_is_401(client: TestClient) -> None:
    response = client.post(f"{API}/tournaments/{uuid.uuid4()}/draw")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_member_cannot_draw(client: TestClient, session: Session) -> None:
    tournament = tournament_in(session, S.CLOSED)

    response = client.post(
        f"{API}/tournaments/{tournament.id}/draw",
        headers=member_headers(client, session),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ORGANIZER_REQUIRED"


def test_other_organizer_cannot_draw(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    _headers, tournament_id = _owner_and_tournament(client, session)
    other = bearer(token_for(client, make_account(session, organizer=True)))
    fake_registration.set_team_count(8)

    response = client.post(f"{API}/tournaments/{tournament_id}/draw", headers=other)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TOURNAMENT_OWNER_REQUIRED"


def test_draw_missing_tournament_is_404(client: TestClient, session: Session) -> None:
    headers = bearer(token_for(client, make_account(session, organizer=True)))

    response = client.post(f"{API}/tournaments/{uuid.uuid4()}/draw", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TOURNAMENT_NOT_FOUND"


def test_draw_twice_is_409(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    headers, tournament_id = _owner_and_tournament(client, session)
    fake_registration.set_team_count(4)
    url = f"{API}/tournaments/{tournament_id}/draw"
    assert client.post(url, headers=headers).status_code == 201

    response = client.post(url, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BRACKET_ALREADY_DRAWN"


@pytest.mark.usefixtures("registration_without_draw_functions")
def test_registration_unavailable_is_503(client: TestClient, session: Session) -> None:
    headers, tournament_id = _owner_and_tournament(client, session)

    response = client.post(f"{API}/tournaments/{tournament_id}/draw", headers=headers)

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "REGISTRATION_UNAVAILABLE",
            "message": "報名功能尚未提供抽籤所需的資料，暫時無法抽籤。",
        }
    }
    assert client.get(f"{API}/tournaments/{tournament_id}/bracket").status_code == 404
