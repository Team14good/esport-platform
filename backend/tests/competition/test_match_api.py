"""Story 5.8 後端：公開單場 API（`GET /tournaments/{id}/matches/{id}`）。"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.competition import service
from app.modules.competition.models import Match, MatchStatus
from app.modules.tournaments.models import TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    draw_with,
    tournament_in,
)
from tests.helpers import API

S = MatchStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

# A 的 PublicMatchDetail（frontend/src/features/competition/match-types.ts，commit 24a8fce）
DETAIL_KEYS = {
    # PublicMatch
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
    # PublicMatchDetail 新增
    "tournament",
    "game_name",
    "best_of",
    "score_type",
    "round_name",
    "games",
    "same_round",
    "appeal_deadline",
    "updated_at",
    # 5.1：兩隊的報到時間
    "check_in_a_at",
    "check_in_b_at",
}


def _url(tournament_id: uuid.UUID, match_id: uuid.UUID) -> str:
    return f"{API}/tournaments/{tournament_id}/matches/{match_id}"


def _drawn(
    session: Session,
    fake: FakeRegistration,
    team_count: int = 8,
    **overrides: object,
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    tournament, bracket = draw_with(session, fake, team_count, **overrides)
    return tournament.id, {m.code: m.id for m in bracket.matches}


def _get(
    client: TestClient, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> dict[str, Any]:
    response = client.get(_url(tournament_id, match_id))
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_first_round_match_without_token(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    snapshot = {
        "game_name": "特戰英豪",
        "starters": 5,
        "substitutes": 2,
        "bo": 3,
        "game_minutes": 40,
        "score_type": "rounds",
        "rank_tiers": [{"name": "鑽石", "score": 30}],
    }
    tournament_id, ids = _drawn(session, fake_registration, game_snapshot=snapshot)
    session.commit()

    response = client.get(_url(tournament_id, ids["M1"]))

    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == DETAIL_KEYS
    assert data["code"] == "M1"
    assert data["round_name"] == "8 強"
    assert data["best_of"] == 3
    assert data["score_type"] == "rounds"
    assert data["game_name"] == "特戰英豪"
    assert data["tournament"] == {"id": str(tournament_id), "name": "期中盃"}
    assert data["games"] == []
    assert [m["code"] for m in data["same_round"]] == ["M2", "M3", "M4"]
    assert data["appeal_deadline"] is None
    assert data["status"] == "scheduled"
    assert data["team_a"]["name"].startswith("隊伍")
    assert data["team_b"]["name"].startswith("隊伍")
    assert "@" not in response.text


def test_every_match_equals_public_bracket_entry(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, ids = _drawn(session, fake_registration)
    session.commit()
    bracket = client.get(f"{API}/tournaments/{tournament_id}/bracket").json()
    by_code = {m["code"]: m for m in bracket["matches"]}
    expected_same_round = {
        "M1": ["M2", "M3", "M4"],
        "M2": ["M1", "M3", "M4"],
        "M3": ["M1", "M2", "M4"],
        "M4": ["M1", "M2", "M3"],
        "M5": ["M6"],
        "M6": ["M5"],
        "M7": ["M8"],
        "M8": ["M7"],
    }

    for code, match_id in ids.items():
        data = _get(client, tournament_id, match_id)
        assert {k: data[k] for k in by_code[code]} == by_code[code]
        assert [m["code"] for m in data["same_round"]] == expected_same_round[code]
        for other in data["same_round"]:
            assert other == by_code[other["code"]]


@pytest.mark.parametrize("team_count", [3, 5, 6])
def test_bye_bracket_matches_equal_public_bracket_entry(
    client: TestClient,
    session: Session,
    fake_registration: FakeRegistration,
    team_count: int,
) -> None:
    """有輪空的對戰表：只組同輪場次時，隊名、來源、輪空欄位仍與整棵樹相同。"""
    tournament_id, ids = _drawn(session, fake_registration, team_count)
    session.commit()
    bracket = client.get(f"{API}/tournaments/{tournament_id}/bracket").json()
    by_code = {m["code"]: m for m in bracket["matches"]}

    for code, match_id in ids.items():
        data = _get(client, tournament_id, match_id)
        assert {k: data[k] for k in by_code[code]} == by_code[code]
        expected = sorted(
            c
            for c, m in by_code.items()
            if m["round_no"] == by_code[code]["round_no"] and c != code
        )
        assert sorted(m["code"] for m in data["same_round"]) == expected
        for other in data["same_round"]:
            assert other == by_code[other["code"]]


def test_pending_match_shows_sources(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, ids = _drawn(session, fake_registration)
    session.commit()

    data = _get(client, tournament_id, ids["M5"])

    assert (data["team_a"], data["team_b"]) == (None, None)
    assert (data["source_a"], data["source_b"]) == ("M1 勝者", "M2 勝者")
    assert data["round_name"] == "4 強"


def test_third_place_and_final_list_each_other(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, ids = _drawn(session, fake_registration)
    session.commit()

    third = _get(client, tournament_id, ids["M8"])
    final = _get(client, tournament_id, ids["M7"])

    assert third["is_third_place"] is True
    assert third["round_name"] == "季軍賽"
    assert [m["code"] for m in third["same_round"]] == ["M7"]
    assert final["is_third_place"] is False
    assert final["round_name"] == "決賽"
    assert [m["code"] for m in final["same_round"]] == ["M8"]


def test_two_team_tournament_has_empty_same_round(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, ids = _drawn(session, fake_registration, 2)
    session.commit()

    data = _get(client, tournament_id, ids["M1"])

    assert set(data) == DETAIL_KEYS
    assert data["round_name"] == "決賽"
    assert data["same_round"] == []


def test_appeal_deadline_only_in_appeal_states(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    tournament_id, ids = _drawn(session, fake_registration)
    deadline = datetime(2026, 10, 26, 12, 30, tzinfo=UTC)
    row = session.get(Match, ids["M1"])
    assert row is not None
    row.appeal_deadline = deadline
    # 已確認、已取消時欄位可能仍留著舊值，公開 API 一律不顯示
    expected: dict[MatchStatus, str | None] = {
        S.SCHEDULED: None,
        S.LIVE: None,
        S.APPEAL_WINDOW: "2026-10-26T12:30:00Z",
        S.APPEALED: "2026-10-26T12:30:00Z",
        S.CONFIRMED: None,
        S.VOIDED: None,
    }
    for status, want in expected.items():
        row.status = status
        session.add(row)
        session.commit()

        data = _get(client, tournament_id, ids["M1"])

        assert data["appeal_deadline"] == want, status


def test_updated_at_follows_same_round_changes(
    client: TestClient,
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    tournament_id, ids = _drawn(session, fake_registration)
    session.commit()
    before = _get(client, tournament_id, ids["M1"])
    assert before["updated_at"] == "2026-10-18T11:00:00Z"
    frozen_clock.advance(timedelta(minutes=5))

    match = service.lock_match(session, match_id=ids["M2"])
    service.transition_match(session, match=match, to=S.LIVE)
    session.commit()

    assert _get(client, tournament_id, ids["M1"])["updated_at"] == (
        "2026-10-18T11:05:00Z"
    )
    assert _get(client, tournament_id, ids["M2"])["updated_at"] == (
        "2026-10-18T11:05:00Z"
    )
    # 別輪的場次不受影響
    assert _get(client, tournament_id, ids["M5"])["updated_at"] == (
        "2026-10-18T11:00:00Z"
    )


def test_match_of_another_tournament_is_404(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    first_id, first_ids = _drawn(session, fake_registration)
    second_id, second_ids = _drawn(session, fake_registration)
    session.commit()

    for tournament_id, match_id in (
        (second_id, first_ids["M1"]),
        (first_id, second_ids["M1"]),
    ):
        response = client.get(_url(tournament_id, match_id))
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "MATCH_NOT_FOUND"


def test_unknown_ids_and_undrawn_tournament_are_404(
    client: TestClient, session: Session, fake_registration: FakeRegistration
) -> None:
    undrawn = tournament_in(session, TournamentStatus.CLOSED)
    drawn_id, ids = _drawn(session, fake_registration)
    session.commit()

    for tournament_id, match_id in (
        (undrawn.id, uuid.uuid4()),
        (uuid.uuid4(), uuid.uuid4()),
        (drawn_id, uuid.uuid4()),
        (undrawn.id, ids["M1"]),
        (uuid.uuid4(), ids["M1"]),
    ):
        response = client.get(_url(tournament_id, match_id))
        assert response.status_code == 404
        assert response.json() == {
            "detail": {"code": "MATCH_NOT_FOUND", "message": "找不到這個場次。"}
        }
