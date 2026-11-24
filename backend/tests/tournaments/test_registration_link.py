"""Story 3.10 第 2 部分：賽事模式選項與賽事報名連結（tournaments 層）。

建立自訂賽事、S27 讀取與重設連結、權限、S28 切換模式、公開 API 與操作紀錄不含 token。
建隊時的檢查在 tests/registration/test_custom_team_invite.py。

`frozen_clock` 固定在 2026-10-18 11:00 UTC（下稱 T）。
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core import audit
from app.modules.identity.models import Account
from app.modules.tournaments import service
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.helpers import (
    API,
    bearer,
    make_account,
    make_game,
    make_tournament,
    token_for,
    tournament_body,
)

S = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")
T = datetime.fromisoformat("2026-10-18T11:00:00+00:00")


def _link_url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}/registration-link"


def _status_url(tournament_id: uuid.UUID) -> str:
    return f"{API}/tournaments/{tournament_id}/registration-link-status"


def _owned(
    client: TestClient,
    session: Session,
    *,
    mode: TournamentMode = TournamentMode.CUSTOM,
    **overrides: Any,
) -> tuple[TournamentRead, Account, dict[str, str]]:
    """主辦方本人的賽事（預設自訂、開放報名中）與主辦方的登入標頭。"""
    organizer = make_account(session, organizer=True)
    tournament = make_tournament(
        session, organizer=organizer, mode=mode.value, **overrides
    )
    return tournament, organizer, bearer(token_for(client, organizer))


def _row(session: Session, tournament_id: uuid.UUID) -> Tournament:
    session.expire_all()
    row = session.get(Tournament, tournament_id)
    assert row is not None
    return row


def _token(session: Session, tournament_id: uuid.UUID) -> str | None:
    return _row(session, tournament_id).invite_token


def _logs(session: Session, tournament_id: uuid.UUID, action: str) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament_id)
        if log.action == action
    ]


def _assert_no_token_in_audit(session: Session, tournament_id: uuid.UUID) -> None:
    """操作紀錄的 before／after 都不含 token 值，也沒有 `invite_token` 欄位。"""
    for log in audit.list_for_tournament(session, tournament_id):
        dumped = json.dumps([log.before, log.after], ensure_ascii=False)
        assert "invite_token" not in dumped
        token = _token(session, tournament_id)
        if token is not None:
            assert token not in dumped


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def _other_organizer(client: TestClient, session: Session) -> dict[str, str]:
    return bearer(token_for(client, make_account(session, organizer=True)))


# ---------------------------------------------------------------- 建立賽事


def test_create_custom_tournament_has_token_and_no_priority_window(
    client: TestClient, session: Session
) -> None:
    organizer = make_account(session, organizer=True)
    game = make_game(session)

    response = client.post(
        f"{API}/organizer/tournaments",
        json=tournament_body(game.id, mode="custom", priority_hours=48),
        headers=bearer(token_for(client, organizer)),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "custom"
    assert "invite_token" not in body
    # 優先期一律 0：傳入的 48 小時被忽略，優先期結束＝報名開始
    assert body["priority_end"] == body["registration_start"]
    tournament_id = uuid.UUID(body["id"])
    token = _token(session, tournament_id)
    assert token is not None and len(token) >= 40
    [created] = _logs(session, tournament_id, "tournament.created")
    assert created.after["mode"] == "custom"
    _assert_no_token_in_audit(session, tournament_id)


def test_create_campus_tournament_has_no_token(
    client: TestClient, session: Session
) -> None:
    tournament, _, _ = _owned(client, session, mode=TournamentMode.CAMPUS)

    assert tournament.mode == TournamentMode.CAMPUS
    assert _token(session, tournament.id) is None
    assert tournament.priority_end == tournament.registration_start + timedelta(
        hours=24
    )


def test_database_rejects_custom_without_token(session: Session) -> None:
    tournament = make_tournament(session)
    row = _row(session, tournament.id)
    row.mode = TournamentMode.CUSTOM
    session.add(row)

    with pytest.raises(IntegrityError, match="ck_tournament_custom_has_invite_token"):
        session.flush()


# ---------------------------------------------------------------- S27 讀取


def test_owner_reads_registration_link(client: TestClient, session: Session) -> None:
    tournament, _, headers = _owned(client, session)

    response = client.get(_link_url(tournament.id), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tournament_id": str(tournament.id),
        "invite_token": _token(session, tournament.id),
    }


def test_read_link_permissions(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session)
    campus, _, campus_headers = _owned(client, session, mode=TournamentMode.CAMPUS)

    other = client.get(
        _link_url(tournament.id), headers=_other_organizer(client, session)
    )
    missing = client.get(_link_url(uuid.uuid4()), headers=campus_headers)
    not_custom = client.get(_link_url(campus.id), headers=campus_headers)
    anonymous = client.get(_link_url(tournament.id))

    assert other.status_code == 403
    assert _code(other) == "TOURNAMENT_OWNER_REQUIRED"
    assert missing.status_code == 404
    assert _code(missing) == "TOURNAMENT_NOT_FOUND"
    assert not_custom.status_code == 409
    assert _code(not_custom) == "TOURNAMENT_NOT_CUSTOM"
    assert anonymous.status_code == 401


# ---------------------------------------------------------------- 重設


def test_reset_replaces_token_and_records_audit(
    client: TestClient, session: Session
) -> None:
    tournament, organizer, headers = _owned(client, session)
    old = _token(session, tournament.id)

    response = client.post(_link_url(tournament.id), headers=headers)

    assert response.status_code == 200, response.text
    new = response.json()["invite_token"]
    assert new != old
    assert _token(session, tournament.id) == new
    [log] = _logs(session, tournament.id, "tournament.invite_link_reset")
    assert log.actor_id == organizer.id
    assert log.entity_id == tournament.id
    assert (log.before, log.after) == (None, None)
    _assert_no_token_in_audit(session, tournament.id)
    # 舊連結立即失效、新連結有效
    assert client.get(_status_url(tournament.id), params={"invite": old}).json() == {
        "valid": False
    }
    assert client.get(_status_url(tournament.id), params={"invite": new}).json() == {
        "valid": True
    }


@pytest.mark.parametrize("status", [S.CANCELLED, S.FINISHED])
def test_reset_rejected_when_cancelled_or_finished(
    client: TestClient, session: Session, status: TournamentStatus
) -> None:
    tournament, _, headers = _owned(client, session)
    old = _token(session, tournament.id)
    row = _row(session, tournament.id)
    row.status = status
    session.add(row)
    session.flush()

    response = client.post(_link_url(tournament.id), headers=headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "TOURNAMENT_NOT_EDITABLE",
        "message": "已結束或已取消的賽事不能修改。",
    }
    assert _token(session, tournament.id) == old
    assert _logs(session, tournament.id, "tournament.invite_link_reset") == []


def test_reset_permissions(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session)
    campus, _, campus_headers = _owned(client, session, mode=TournamentMode.CAMPUS)
    old = _token(session, tournament.id)

    other = client.post(
        _link_url(tournament.id), headers=_other_organizer(client, session)
    )
    missing = client.post(_link_url(uuid.uuid4()), headers=campus_headers)
    not_custom = client.post(_link_url(campus.id), headers=campus_headers)
    anonymous = client.post(_link_url(tournament.id))

    assert other.status_code == 403
    assert _code(other) == "TOURNAMENT_OWNER_REQUIRED"
    assert missing.status_code == 404
    assert not_custom.status_code == 409
    assert _code(not_custom) == "TOURNAMENT_NOT_CUSTOM"
    assert anonymous.status_code == 401
    assert _token(session, tournament.id) == old
    assert _token(session, campus.id) is None
    assert _logs(session, tournament.id, "tournament.invite_link_reset") == []


# ---------------------------------------------------------------- 公開 API


def test_link_status_cases(client: TestClient, session: Session) -> None:
    tournament, _, _ = _owned(client, session)
    campus, _, _ = _owned(client, session, mode=TournamentMode.CAMPUS)
    token = _token(session, tournament.id)

    valid = client.get(_status_url(tournament.id), params={"invite": token})
    wrong = client.get(_status_url(tournament.id), params={"invite": "x" * 200})
    absent = client.get(_status_url(tournament.id))
    campus_any = client.get(_status_url(campus.id), params={"invite": token})
    missing = client.get(_status_url(uuid.uuid4()), params={"invite": token})

    assert valid.status_code == 200
    assert valid.json() == {"valid": True}
    assert wrong.json() == {"valid": False}
    assert absent.json() == {"valid": False}
    assert campus_any.json() == {"valid": False}
    assert missing.status_code == 404
    assert _code(missing) == "TOURNAMENT_NOT_FOUND"


def test_public_tournament_api_has_mode_without_token(
    client: TestClient, session: Session
) -> None:
    tournament, _, _ = _owned(client, session)
    token = _token(session, tournament.id)
    assert token is not None

    listed = client.get(f"{API}/tournaments")
    single = client.get(f"{API}/tournaments/{tournament.id}")

    assert single.status_code == 200
    assert single.json()["mode"] == "custom"
    [item] = [t for t in listed.json() if t["id"] == str(tournament.id)]
    assert item["mode"] == "custom"
    for response in (listed, single):
        assert token not in response.text
        assert "invite_token" not in response.text


def test_organizer_tournament_read_has_no_token(
    client: TestClient, session: Session
) -> None:
    tournament, _, headers = _owned(client, session)
    token = _token(session, tournament.id)
    assert token is not None

    single = client.get(f"{API}/organizer/tournaments/{tournament.id}", headers=headers)
    listed = client.get(f"{API}/organizer/tournaments", headers=headers)

    for response in (single, listed):
        assert response.status_code == 200
        assert token not in response.text


def test_invite_token_matches_treats_none_as_mismatch(session: Session) -> None:
    custom = make_tournament(session, mode="custom")
    campus = make_tournament(session)
    token = _token(session, custom.id)

    assert service.invite_token_matches(session, tournament_id=custom.id, token=token)
    assert not service.invite_token_matches(
        session, tournament_id=custom.id, token=None
    )
    assert not service.invite_token_matches(
        session, tournament_id=custom.id, token=f"{token}x"
    )
    # 校園賽的 token 是 null：帶 None 也不能算相符
    assert not service.invite_token_matches(
        session, tournament_id=campus.id, token=None
    )
    assert not service.invite_token_matches(
        session, tournament_id=campus.id, token=token
    )


# ---------------------------------------------------------------- S28 切換模式


def _upcoming(
    client: TestClient, session: Session, mode: TournamentMode
) -> tuple[TournamentRead, dict[str, str]]:
    tournament, _, headers = _owned(
        client,
        session,
        mode=mode,
        registration_start=(T + timedelta(days=1)).isoformat(),
    )
    assert tournament.status == S.UPCOMING
    return tournament, headers


def test_switch_campus_to_custom_generates_token(
    client: TestClient, session: Session
) -> None:
    tournament, headers = _upcoming(client, session, TournamentMode.CAMPUS)

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"mode": "custom", "priority_hours": 12},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "custom"
    assert body["priority_end"] == body["registration_start"]
    assert _token(session, tournament.id) is not None
    [log] = _logs(session, tournament.id, "tournament.updated")
    assert log.before["mode"] == "campus"
    assert log.after["mode"] == "custom"
    _assert_no_token_in_audit(session, tournament.id)


def test_switch_custom_to_campus_clears_token(
    client: TestClient, session: Session
) -> None:
    tournament, headers = _upcoming(client, session, TournamentMode.CUSTOM)
    assert tournament.priority_end == tournament.registration_start

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"mode": "campus", "priority_hours": 24},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "campus"
    assert datetime.fromisoformat(body["priority_end"]) == datetime.fromisoformat(
        body["registration_start"]
    ) + timedelta(hours=24)
    assert _token(session, tournament.id) is None
    _assert_no_token_in_audit(session, tournament.id)


@pytest.mark.parametrize("status", [S.UPCOMING, S.OPEN])
def test_custom_ignores_priority_hours_on_update(
    client: TestClient, session: Session, status: TournamentStatus
) -> None:
    if status == S.UPCOMING:
        tournament, headers = _upcoming(client, session, TournamentMode.CUSTOM)
    else:
        tournament, _, headers = _owned(client, session)
        assert tournament.status == S.OPEN
    token = _token(session, tournament.id)

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"priority_hours": 6},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["priority_end"] == response.json()["registration_start"]
    # 沒有實際變動：不寫紀錄、token 不變
    assert _logs(session, tournament.id, "tournament.updated") == []
    assert _token(session, tournament.id) == token


def test_switch_custom_to_campus_without_priority_uses_default(
    client: TestClient, session: Session
) -> None:
    tournament, headers = _upcoming(client, session, TournamentMode.CUSTOM)

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"mode": "campus"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert datetime.fromisoformat(body["priority_end"]) == datetime.fromisoformat(
        body["registration_start"]
    ) + timedelta(hours=24)
    assert _token(session, tournament.id) is None


def test_other_edit_of_upcoming_custom_keeps_token(
    client: TestClient, session: Session
) -> None:
    tournament, headers = _upcoming(client, session, TournamentMode.CUSTOM)
    token = _token(session, tournament.id)

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"name": "改名的自訂賽"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "改名的自訂賽"
    assert response.json()["mode"] == "custom"
    assert response.json()["priority_end"] == response.json()["registration_start"]
    assert _token(session, tournament.id) == token


@pytest.mark.parametrize("mode", [TournamentMode.CAMPUS, TournamentMode.CUSTOM])
def test_mode_locked_after_open(
    client: TestClient, session: Session, mode: TournamentMode
) -> None:
    tournament, _, headers = _owned(client, session, mode=mode)
    assert tournament.status == S.OPEN
    other = "campus" if mode == TournamentMode.CUSTOM else "custom"

    response = client.patch(
        f"{API}/organizer/tournaments/{tournament.id}",
        json={"mode": other},
        headers=headers,
    )

    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "mode"]
    assert error["type"] == "TOURNAMENT_FIELD_LOCKED"
    assert error["msg"] == "開放報名後不能修改賽事模式"
    assert _row(session, tournament.id).mode == mode
