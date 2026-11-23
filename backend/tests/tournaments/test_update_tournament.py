"""Story 2.5：抽籤前修改賽事（I/O 矩陣每一列，另含延長報名後重新截止與自動抽籤）。

`frozen_clock` 固定在 2026-10-18 11:00 UTC。預設賽事：遊戲先發 5、替補 2、BO3、每局
40 分鐘，名額 16、每輪間隔 180 分鐘（下限 15＋3×40＋30＝165）。
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.modules.competition import service as competition_service
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments import service
from app.modules.tournaments.models import (
    Tournament,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.helpers import (
    API,
    bearer,
    make_account,
    make_game,
    make_tournament,
    member_headers,
    organizer_headers,
    token_for,
)

S = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")


def _url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}"


def _iso(at: datetime) -> str:
    return at.isoformat()


def _owned(
    client: TestClient,
    session: Session,
    status: S = S.OPEN,
    **overrides: Any,
) -> tuple[TournamentRead, Account, dict[str, str]]:
    """主辦方本人的賽事。`upcoming` 時報名 1 天後才開始；其他狀態直接設欄位（略過轉換）。"""
    organizer = make_account(session, organizer=True)
    if status == S.UPCOMING:
        now = datetime.fromisoformat("2026-10-18T11:00:00+00:00")
        overrides.setdefault("registration_start", _iso(now + timedelta(days=1)))
    tournament = make_tournament(session, organizer=organizer, **overrides)
    if tournament.status != status:
        row = session.get(Tournament, tournament.id)
        assert row is not None
        row.status = status
        session.add(row)
        session.flush()
    tournament = _read(session, tournament.id)
    assert tournament.status == status
    return tournament, organizer, bearer(token_for(client, organizer))


def _read(session: Session, tournament_id: uuid.UUID) -> TournamentRead:
    session.expire_all()
    return service.get_tournament(session, tournament_id=tournament_id)


def _logs(session: Session, tournament_id: uuid.UUID, action: str) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament_id)
        if log.action == action
    ]


def _assert_field_error(response: Any, field: str, code: str | None = None) -> None:
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", field]
    if code is not None:
        assert error["type"] == code


def _business_code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


# ---------------------------------------------------------------- 尚未開放


def test_upcoming_changes_game_capacity_and_times(
    client: TestClient, session: Session
) -> None:
    tournament, organizer, headers = _owned(client, session, S.UPCOMING)
    other_game = make_game(
        session,
        starters=1,
        substitutes=0,
        default_bo=1,
        game_minutes=20,
        score_type="rounds",
        rank_tiers=[{"name": "傳說", "score": 99}],
    )
    new_start = tournament.start_at + timedelta(days=1)
    new_end = tournament.registration_end + timedelta(hours=3)

    response = client.patch(
        _url(tournament.id),
        json={
            "game_id": str(other_game.id),
            "capacity": 8,
            "registration_end": _iso(new_end),
            "start_at": _iso(new_start),
            "priority_hours": 2,
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    updated = _read(session, tournament.id)
    assert updated.status == S.UPCOMING
    assert updated.capacity == 8
    assert updated.start_at == new_start
    assert updated.registration_end == new_end
    assert updated.priority_end == updated.registration_start + timedelta(hours=2)
    # 快照換成新遊戲；未另填的人數與 BO 帶新遊戲的值
    assert updated.game_id == other_game.id
    assert updated.game_name == other_game.name
    assert (updated.starters, updated.substitutes, updated.bo) == (1, 0, 1)
    assert updated.game_minutes == 20
    assert updated.score_type == "rounds"
    assert [t.name for t in updated.rank_tiers] == ["傳說"]

    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.actor_id == organizer.id
    assert log.before is not None and log.after is not None
    assert set(log.after) == set(log.before)
    assert set(log.after) == {
        "capacity",
        "registration_end",
        "priority_end",
        "start_at",
        "game_id",
        "game_name",
        "starters",
        "substitutes",
        "bo",
        "game_minutes",
        "score_type",
        "rank_tiers",
    }
    assert log.before["capacity"] == 16
    assert log.after["capacity"] == 8
    assert response.json()["capacity"] == 8


def test_upcoming_game_change_keeps_explicit_starters(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.UPCOMING)
    other_game = make_game(session, starters=3, default_bo=1, game_minutes=20)

    response = client.patch(
        _url(tournament.id),
        json={"game_id": str(other_game.id), "starters": 4, "bo": 3},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    updated = _read(session, tournament.id)
    assert (updated.starters, updated.substitutes, updated.bo) == (4, 2, 3)


def test_upcoming_round_interval_below_minimum_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.UPCOMING)

    response = client.patch(
        _url(tournament.id), json={"round_interval_minutes": 164}, headers=headers
    )

    _assert_field_error(response, "round_interval_minutes", "ROUND_INTERVAL_TOO_SHORT")
    assert "165" in response.json()["detail"][0]["msg"]
    assert _read(session, tournament.id) == tournament
    assert _logs(session, tournament.id, "tournament.updated") == []


def test_upcoming_lowering_capacity_checks_round_bo_range(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(
        client, session, S.UPCOMING, round_bo=[{"rounds_from_final": 3, "bo": 5}]
    )

    response = client.patch(_url(tournament.id), json={"capacity": 4}, headers=headers)

    _assert_field_error(response, "round_bo", "ROUND_BO_OUT_OF_RANGE")


def test_upcoming_registration_start_moved_to_now_opens(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, organizer, headers = _owned(client, session, S.UPCOMING)

    response = client.patch(
        _url(tournament.id),
        json={"registration_start": _iso(frozen_clock.now())},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"
    assert _read(session, tournament.id).status == S.OPEN
    [changed] = _logs(session, tournament.id, "tournament.status_changed")
    assert changed.actor_id == organizer.id
    assert changed.after == {"status": "open"}


def test_upcoming_changes_starters_substitutes_and_bo_without_game(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.UPCOMING)

    # BO5：15＋5×40＋30＝245
    response = client.patch(
        _url(tournament.id),
        json={
            "starters": 4,
            "substitutes": 3,
            "bo": 5,
            "round_interval_minutes": 245,
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    updated = _read(session, tournament.id)
    assert (updated.starters, updated.substitutes, updated.bo) == (4, 3, 5)
    assert updated.round_interval_minutes == 245
    # 遊戲與其他快照值不變
    assert updated.game_id == tournament.game_id
    assert updated.game_name == tournament.game_name
    assert updated.game_minutes == tournament.game_minutes
    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.before == {
        "starters": 5,
        "substitutes": 2,
        "bo": 3,
        "round_interval_minutes": 180,
    }
    assert log.after == {
        "starters": 4,
        "substitutes": 3,
        "bo": 5,
        "round_interval_minutes": 245,
    }


def test_upcoming_raising_bo_needs_longer_interval(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.UPCOMING)

    response = client.patch(_url(tournament.id), json={"bo": 5}, headers=headers)

    # 15＋5×40＋30＝245 > 180
    _assert_field_error(response, "round_interval_minutes", "ROUND_INTERVAL_TOO_SHORT")
    assert "245" in response.json()["detail"][0]["msg"]
    assert _read(session, tournament.id) == tournament
    assert _logs(session, tournament.id, "tournament.updated") == []


def test_upcoming_unknown_game_is_404(client: TestClient, session: Session) -> None:
    tournament, _, headers = _owned(client, session, S.UPCOMING)

    response = client.patch(
        _url(tournament.id), json={"game_id": str(uuid.uuid4())}, headers=headers
    )

    assert response.status_code == 404
    assert _business_code(response) == "GAME_NOT_FOUND"


# ---------------------------------------------------------------- 開放報名、報名截止


@pytest.mark.parametrize("status", [S.OPEN, S.CLOSED])
def test_open_relaxing_settings(
    client: TestClient, session: Session, frozen_clock: FrozenClock, status: S
) -> None:
    tournament, organizer, headers = _owned(client, session, status)
    if status == S.CLOSED:
        # 報名截止已過、新截止仍早於現在：不轉回開放報名
        frozen_clock.set(tournament.registration_end + timedelta(hours=1))
        # 時鐘往後推，登入權杖要重新取得
        headers = bearer(token_for(client, organizer))
        new_end = tournament.registration_end + timedelta(minutes=30)
    else:
        new_end = tournament.registration_end + timedelta(hours=12)

    response = client.patch(
        _url(tournament.id),
        json={
            "registration_end": _iso(new_end),
            "forfeit_minutes": 20,
            "appeal_minutes": 40,
            "round_interval_minutes": 200,
            "round_bo": [{"rounds_from_final": 0, "bo": 5}],
            "livestream_url": "https://twitch.tv/flow",
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    updated = _read(session, tournament.id)
    assert updated.status == status
    assert updated.registration_end == new_end
    assert (
        updated.forfeit_minutes,
        updated.appeal_minutes,
        updated.round_interval_minutes,
    ) == (20, 40, 200)
    assert [(r.rounds_from_final, r.bo) for r in updated.round_bo] == [(0, 5)]
    assert updated.livestream_url == "https://twitch.tv/flow"
    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.actor_id == organizer.id
    assert log.before is not None
    assert (
        datetime.fromisoformat(log.before.pop("registration_end"))
        == tournament.registration_end
    )
    assert log.before == {
        "forfeit_minutes": 15,
        "appeal_minutes": 30,
        "round_interval_minutes": 180,
        "livestream_url": None,
        "round_bo": [],
    }
    assert log.after is not None
    assert log.after["round_bo"] == [{"rounds_from_final": 0, "bo": 5}]
    assert log.after["forfeit_minutes"] == 20


@pytest.mark.parametrize("status", [S.OPEN, S.CLOSED])
@pytest.mark.parametrize(
    ("field", "make_value", "code"),
    [
        ("name", lambda t, g: "新名稱", "TOURNAMENT_FIELD_LOCKED"),
        ("game_id", lambda t, g: str(g.id), "TOURNAMENT_FIELD_LOCKED"),
        ("capacity", lambda t, g: 8, "TOURNAMENT_FIELD_LOCKED"),
        ("capacity", lambda t, g: 32, "TOURNAMENT_FIELD_LOCKED"),
        (
            "registration_start",
            lambda t, g: _iso(t.registration_start - timedelta(hours=1)),
            "TOURNAMENT_FIELD_LOCKED",
        ),
        ("priority_hours", lambda t, g: 2, "TOURNAMENT_FIELD_LOCKED"),
        (
            "start_at",
            lambda t, g: _iso(t.start_at + timedelta(days=1)),
            "TOURNAMENT_FIELD_LOCKED",
        ),
        ("starters", lambda t, g: 4, "TOURNAMENT_FIELD_LOCKED"),
        ("substitutes", lambda t, g: 3, "TOURNAMENT_FIELD_LOCKED"),
        ("bo", lambda t, g: 5, "TOURNAMENT_FIELD_LOCKED"),
        (
            "registration_end",
            lambda t, g: _iso(t.registration_end - timedelta(hours=1)),
            "TOURNAMENT_SETTING_TIGHTENED",
        ),
        ("forfeit_minutes", lambda t, g: 15, "TOURNAMENT_SETTING_TIGHTENED"),
        ("appeal_minutes", lambda t, g: 30, "TOURNAMENT_SETTING_TIGHTENED"),
        ("round_interval_minutes", lambda t, g: 170, "TOURNAMENT_SETTING_TIGHTENED"),
    ],
)
def test_open_tightening_or_locked_field_is_rejected(
    client: TestClient,
    session: Session,
    status: S,
    field: str,
    make_value: Any,
    code: str,
) -> None:
    # 棄權時限、申訴期先放寬到 20、40，縮短回下限才算收緊
    tournament, _, headers = _owned(
        client,
        session,
        status,
        forfeit_minutes=20,
        appeal_minutes=40,
        round_interval_minutes=200,
    )
    other_game = make_game(session)

    response = client.patch(
        _url(tournament.id),
        json={field: make_value(tournament, other_game)},
        headers=headers,
    )

    _assert_field_error(response, field, code)
    assert _read(session, tournament.id) == tournament
    assert _logs(session, tournament.id, "tournament.updated") == []


def test_open_registration_end_after_start_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id),
        json={"registration_end": _iso(tournament.start_at + timedelta(minutes=1))},
        headers=headers,
    )

    _assert_field_error(response, "registration_end", "REGISTRATION_END_AFTER_START")


def test_open_registration_end_must_be_before_start(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id),
        json={"registration_end": _iso(tournament.start_at)},
        headers=headers,
    )

    _assert_field_error(response, "registration_end", "REGISTRATION_END_AFTER_START")
    assert response.json()["detail"][0]["msg"] == "報名截止必須早於開賽時間"
    assert _read(session, tournament.id) == tournament

    one_minute_before = tournament.start_at - timedelta(minutes=1)
    response = client.patch(
        _url(tournament.id),
        json={"registration_end": _iso(one_minute_before)},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert _read(session, tournament.id).registration_end == one_minute_before


def test_open_longer_forfeit_needs_longer_interval(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id), json={"forfeit_minutes": 20}, headers=headers
    )

    # 20＋3×40＋30＝170 ≤ 180，仍合法
    assert response.status_code == 200, response.text

    response = client.patch(
        _url(tournament.id), json={"appeal_minutes": 50}, headers=headers
    )

    # 20＋120＋50＝190 > 180
    _assert_field_error(response, "round_interval_minutes", "ROUND_INTERVAL_TOO_SHORT")
    assert _read(session, tournament.id).appeal_minutes == 30


def test_open_round_bo_out_of_range_for_capacity(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.OPEN, capacity=4)

    response = client.patch(
        _url(tournament.id),
        json={"round_bo": [{"rounds_from_final": 2, "bo": 3}]},
        headers=headers,
    )

    _assert_field_error(response, "round_bo", "ROUND_BO_OUT_OF_RANGE")


def test_closed_extended_past_now_reopens(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, organizer, headers = _owned(client, session, S.CLOSED)
    frozen_clock.set(tournament.registration_end + timedelta(hours=1))
    headers = bearer(token_for(client, organizer))
    new_end = frozen_clock.now() + timedelta(hours=6)

    response = client.patch(
        _url(tournament.id), json={"registration_end": _iso(new_end)}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"
    updated = _read(session, tournament.id)
    assert updated.status == S.OPEN
    assert updated.registration_end == new_end
    [updated_log] = _logs(session, tournament.id, "tournament.updated")
    assert set(updated_log.after) == {"registration_end"}
    [changed] = _logs(session, tournament.id, "tournament.status_changed")
    assert changed.actor_id == organizer.id
    assert (changed.before, changed.after) == ({"status": "closed"}, {"status": "open"})


def test_extended_registration_is_closed_again_and_auto_draw_retried(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """正取不足而自動抽籤略過的賽事延長報名後，新截止時重新截止並重新嘗試自動抽籤。"""
    now = frozen_clock.now()
    tournament, _, headers = _owned(
        client,
        session,
        S.OPEN,
        registration_end=_iso(now + timedelta(hours=2)),
        priority_hours=1,
    )
    frozen_clock.advance(timedelta(hours=3))
    assert registration_service.close_registration(session, tournament_id=tournament.id)
    assert _read(session, tournament.id).status == S.CLOSED
    outcome = competition_service.auto_draw(session, tournament_id=tournament.id)
    assert outcome == "not_enough_teams"
    # 同一個報名截止不會再試
    assert (
        competition_service.auto_draw(session, tournament_id=tournament.id) == "not_due"
    )

    new_end = frozen_clock.now() + timedelta(hours=4)
    response = client.patch(
        _url(tournament.id), json={"registration_end": _iso(new_end)}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert _read(session, tournament.id).status == S.OPEN

    # 新截止之前不會截止
    assert not registration_service.close_registration(
        session, tournament_id=tournament.id
    )
    frozen_clock.set(new_end)
    assert registration_service.close_registration(session, tournament_id=tournament.id)
    assert _read(session, tournament.id).status == S.CLOSED
    assert (
        competition_service.auto_draw(session, tournament_id=tournament.id)
        == "not_enough_teams"
    )
    assert len(_logs(session, tournament.id, "bracket.auto_draw_skipped")) == 2


# ---------------------------------------------------------------- 抽籤後


@pytest.mark.parametrize("status", [S.PUBLISHED, S.ONGOING])
def test_after_draw_livestream_only(
    client: TestClient, session: Session, status: S
) -> None:
    tournament, _, headers = _owned(client, session, status)

    response = client.patch(
        _url(tournament.id),
        json={"livestream_url": "http://youtube.com/live/flow"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert _read(session, tournament.id).livestream_url == (
        "http://youtube.com/live/flow"
    )
    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.before == {"livestream_url": None}
    assert log.after == {"livestream_url": "http://youtube.com/live/flow"}


@pytest.mark.parametrize("status", [S.PUBLISHED, S.ONGOING])
@pytest.mark.parametrize(
    "body",
    [
        {"round_bo": [{"rounds_from_final": 0, "bo": 5}]},
        {"livestream_url": "https://a.tv", "forfeit_minutes": 20},
    ],
)
def test_after_draw_other_fields_are_locked(
    client: TestClient, session: Session, status: S, body: dict[str, Any]
) -> None:
    tournament, _, headers = _owned(client, session, status)

    response = client.patch(_url(tournament.id), json=body, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "TOURNAMENT_SETTINGS_LOCKED",
        "message": "抽籤後只能修改場次時間。",
    }
    assert _read(session, tournament.id) == tournament


@pytest.mark.parametrize("status", [S.FINISHED, S.CANCELLED])
@pytest.mark.parametrize(
    "body", [{"livestream_url": "https://a.tv"}, {"name": "新名稱"}, {}]
)
def test_finished_or_cancelled_is_not_editable(
    client: TestClient, session: Session, status: S, body: dict[str, Any]
) -> None:
    tournament, _, headers = _owned(client, session, status)

    response = client.patch(_url(tournament.id), json=body, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "TOURNAMENT_NOT_EDITABLE",
        "message": "已結束或已取消的賽事不能修改。",
    }
    assert _read(session, tournament.id) == tournament


# ---------------------------------------------------------------- 共通


def test_invalid_livestream_url_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id), json={"livestream_url": "ftp://a.tv/x"}, headers=headers
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"][:2] == ["body", "livestream_url"]
    assert _read(session, tournament.id) == tournament


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_livestream_url_removes_it(
    client: TestClient, session: Session, blank: str | None
) -> None:
    tournament, _, headers = _owned(
        client, session, S.PUBLISHED, livestream_url="https://a.tv"
    )

    response = client.patch(
        _url(tournament.id), json={"livestream_url": blank}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert _read(session, tournament.id).livestream_url is None


def test_other_organizer_is_forbidden(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id),
        json={"livestream_url": "https://a.tv"},
        headers=organizer_headers(client, session),
    )

    assert response.status_code == 403
    assert _business_code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert _read(session, tournament.id) == tournament


@pytest.mark.parametrize(
    "new_round_bo",
    [
        [{"rounds_from_final": 0, "bo": 5}],
        [{"rounds_from_final": 1, "bo": 3}],
        [],
    ],
)
def test_open_replaces_round_bo(
    client: TestClient, session: Session, new_round_bo: list[dict[str, int]]
) -> None:
    tournament, _, headers = _owned(
        client, session, S.OPEN, round_bo=[{"rounds_from_final": 0, "bo": 3}]
    )

    response = client.patch(
        _url(tournament.id), json={"round_bo": new_round_bo}, headers=headers
    )

    assert response.status_code == 200, response.text
    updated = _read(session, tournament.id)
    # 舊的設定整份被取代（不會留下原本的決賽 BO3）
    assert [item.model_dump() for item in updated.round_bo] == new_round_bo
    assert response.json()["round_bo"] == new_round_bo
    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.before == {"round_bo": [{"rounds_from_final": 0, "bo": 3}]}
    assert log.after == {"round_bo": new_round_bo}


def test_unauthenticated_is_401(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id), json={"livestream_url": "https://a.tv"}
    )

    assert response.status_code == 401
    assert _read(session, tournament.id) == tournament


def test_non_organizer_is_forbidden(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session, S.OPEN)

    response = client.patch(
        _url(tournament.id),
        json={"livestream_url": "https://a.tv"},
        headers=member_headers(client, session),
    )

    assert response.status_code == 403
    assert _business_code(response) == "ORGANIZER_REQUIRED"
    assert _read(session, tournament.id) == tournament


def test_unknown_tournament_is_404(client: TestClient, session: Session) -> None:
    response = client.patch(
        _url(uuid.uuid4()), json={}, headers=organizer_headers(client, session)
    )

    assert response.status_code == 404
    assert _business_code(response) == "TOURNAMENT_NOT_FOUND"


@pytest.mark.parametrize("status", [S.UPCOMING, S.OPEN, S.PUBLISHED])
def test_same_values_return_200_without_audit(
    client: TestClient, session: Session, status: S
) -> None:
    tournament, _, headers = _owned(client, session, status)
    before_logs = len(audit.list_for_tournament(session, tournament.id))

    response = client.patch(
        _url(tournament.id),
        json={
            "name": tournament.name,
            "capacity": tournament.capacity,
            "registration_end": _iso(tournament.registration_end),
            "start_at": _iso(tournament.start_at),
            "bo": tournament.bo,
            "round_bo": [],
            "livestream_url": None,
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(tournament.id)
    assert len(audit.list_for_tournament(session, tournament.id)) == before_logs
