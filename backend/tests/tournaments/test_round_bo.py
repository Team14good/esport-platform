"""Story 2.3：分輪設定 BO 數（I/O 矩陣每一列）。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.modules.tournaments import service
from app.modules.tournaments.models import RoundBo
from tests.helpers import (
    API,
    make_game,
    make_tournament,
    organizer_headers,
    tournament_body,
)

TOURNAMENTS_URL = f"{API}/organizer/tournaments"

SEMI_BO3_FINAL_BO5 = [
    {"rounds_from_final": 1, "bo": 3},
    {"rounds_from_final": 0, "bo": 5},
]


def _settings(*pairs: tuple[int, int]) -> list[RoundBo]:
    return [RoundBo(rounds_from_final=d, bo=bo) for d, bo in pairs]


def _bo_per_round(
    round_bo: list[RoundBo], *, default_bo: int, rounds: int
) -> tuple[list[int], int]:
    """（每一輪正規場次的 BO，季軍賽的 BO）。"""
    regular = [
        service.resolve_round_bo(
            round_bo,
            default_bo=default_bo,
            round_no=n,
            rounds=rounds,
            is_third_place=False,
        )
        for n in range(1, rounds + 1)
    ]
    third = service.resolve_round_bo(
        round_bo,
        default_bo=default_bo,
        round_no=rounds,
        rounds=rounds,
        is_third_place=True,
    )
    return regular, third


# ---------------------------------------------------------------- 換算（純函式）


@pytest.mark.parametrize(
    ("capacity", "rounds"), [(2, 1), (3, 2), (4, 2), (6, 3), (8, 3), (9, 4), (16, 4)]
)
def test_total_rounds_is_ceil_log2(capacity: int, rounds: int) -> None:
    assert service.total_rounds(capacity) == rounds


def test_semifinal_and_final_settings_for_16_teams() -> None:
    settings = _settings((1, 3), (0, 5))

    assert _bo_per_round(settings, default_bo=1, rounds=4) == ([1, 1, 3, 5], 3)


def test_fewer_teams_still_maps_by_distance_from_final() -> None:
    # 名額 16 但實際 6 隊：只有 3 輪，決賽與 4 強仍套用各自的設定
    settings = _settings((1, 3), (0, 5))

    assert _bo_per_round(settings, default_bo=1, rounds=3) == ([1, 3, 5], 3)


def test_no_settings_uses_snapshot_bo_everywhere() -> None:
    assert _bo_per_round([], default_bo=3, rounds=4) == ([3, 3, 3, 3], 3)


def test_only_final_set_third_place_uses_default() -> None:
    settings = _settings((0, 5))

    assert _bo_per_round(settings, default_bo=1, rounds=3) == ([1, 1, 5], 1)


@pytest.mark.parametrize(("round_no", "rounds"), [(0, 3), (4, 3), (1, 0)])
def test_round_out_of_range_is_value_error(round_no: int, rounds: int) -> None:
    with pytest.raises(ValueError):
        service.rounds_from_final(
            round_no=round_no, rounds=rounds, is_third_place=False
        )


# ---------------------------------------------------------------- 建立賽事


@pytest.fixture
def organizer(client: TestClient, session: Session) -> dict[str, str]:
    return organizer_headers(client, session)


def _create(client: TestClient, headers: dict[str, str], body: dict[str, Any]) -> Any:
    return client.post(TOURNAMENTS_URL, json=body, headers=headers)


@pytest.mark.usefixtures("frozen_clock")
def test_create_stores_round_bo_and_records_it(
    client: TestClient, session: Session, organizer: dict[str, str]
) -> None:
    game = make_game(session, default_bo=1)
    body = tournament_body(game.id, bo=1, round_bo=SEMI_BO3_FINAL_BO5)

    response = _create(client, organizer, body)

    assert response.status_code == 201, response.text
    created = response.json()
    # 依距決賽的輪數排序
    assert created["round_bo"] == [
        {"rounds_from_final": 0, "bo": 5},
        {"rounds_from_final": 1, "bo": 3},
    ]
    [row] = audit.list_for_tournament(session, created["id"])
    assert row.action == "tournament.created"
    assert row.after is not None
    assert row.after["round_bo"] == created["round_bo"]

    detail = client.get(f"{TOURNAMENTS_URL}/{created['id']}", headers=organizer)
    assert detail.json()["round_bo"] == created["round_bo"]
    listed = client.get(TOURNAMENTS_URL, headers=organizer).json()
    assert [t["round_bo"] for t in listed] == [created["round_bo"]]

    tournament_id = created["id"]
    assert [
        service.bo_for_round(
            session,
            tournament_id=tournament_id,
            round_no=n,
            rounds=4,
            is_third_place=False,
        )
        for n in (1, 2, 3, 4)
    ] == [1, 1, 3, 5]
    assert (
        service.bo_for_round(
            session,
            tournament_id=tournament_id,
            round_no=4,
            rounds=4,
            is_third_place=True,
        )
        == 3
    )
    locked = service.lock_tournament(session, tournament_id=tournament_id)
    assert [item.model_dump() for item in locked.round_bo] == created["round_bo"]


@pytest.mark.usefixtures("frozen_clock")
def test_create_without_round_bo_has_empty_list(session: Session) -> None:
    tournament = make_tournament(session, bo=5, round_interval_minutes=300)

    assert tournament.round_bo == []
    assert (
        service.bo_for_round(
            session,
            tournament_id=tournament.id,
            round_no=1,
            rounds=4,
            is_third_place=False,
        )
        == 5
    )


@pytest.mark.usefixtures("frozen_clock")
def test_largest_distance_allowed_by_capacity_is_accepted(
    client: TestClient, session: Session, organizer: dict[str, str]
) -> None:
    game = make_game(session)
    body = tournament_body(
        game.id, capacity=8, round_bo=[{"rounds_from_final": 2, "bo": 1}]
    )

    response = _create(client, organizer, body)

    assert response.status_code == 201, response.text


@pytest.mark.usefixtures("frozen_clock")
@pytest.mark.parametrize(
    ("capacity", "round_bo"),
    [
        # 不合法的 BO
        (16, [{"rounds_from_final": 0, "bo": 2}]),
        # 超出輪數：名額 8 只有 3 輪（距決賽 0～2）
        (8, [{"rounds_from_final": 3, "bo": 3}]),
        # 重複輪次
        (16, [{"rounds_from_final": 0, "bo": 3}, {"rounds_from_final": 0, "bo": 5}]),
        # 負的輪次
        (16, [{"rounds_from_final": -1, "bo": 3}]),
    ],
)
def test_invalid_round_bo_is_422_on_round_bo(
    client: TestClient,
    session: Session,
    organizer: dict[str, str],
    capacity: int,
    round_bo: list[dict[str, int]],
) -> None:
    game = make_game(session)
    body = tournament_body(game.id, capacity=capacity, round_bo=round_bo)

    response = _create(client, organizer, body)

    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "round_bo"]
    assert error["msg"]
    # 不建立賽事
    assert client.get(TOURNAMENTS_URL, headers=organizer).json() == []
