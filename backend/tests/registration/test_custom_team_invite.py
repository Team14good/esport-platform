"""Story 3.10 第 2 部分：自訂賽事建隊要帶賽事報名連結（I/O 矩陣建隊各列）。

自訂賽事經建立賽事的 `mode` 建立（不再直接改賽事列）。重設連結經主辦方 API；加入隊伍
（隊伍邀請連結）不檢查賽事報名連結。讀取與重設的權限在 tests/tournaments/test_registration_link.py。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.identity.models import Account
from app.modules.registration import repository
from app.modules.tournaments.models import (
    Tournament,
    TournamentRead,
    TournamentStatus,
)
from tests.helpers import API
from tests.registration.test_teams import (
    _auth,
    _create,
    _create_ok,
    _error_code,
    _join,
    _make_account,
    _set_status,
    _tournament,
)

NO_LINK = "這是邀請制賽事，請向主辦方索取報名連結。"
EXPIRED_LINK = "報名連結已失效，請向主辦方索取新的連結。"


def _custom(session: Session, **overrides: Any) -> TournamentRead:
    return _tournament(session, mode="custom", **overrides)


def _invite(session: Session, tournament_id: uuid.UUID) -> str:
    session.expire_all()
    row = session.get(Tournament, tournament_id)
    assert row is not None and row.invite_token is not None
    return row.invite_token


def _assert_invite_required(response: Any, message: str) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {
        "code": "TOURNAMENT_INVITE_REQUIRED",
        "message": message,
    }


def _reset(client: TestClient, session: Session, tournament: TournamentRead) -> str:
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    response = client.post(
        f"{API}/organizer/tournaments/{tournament.id}/registration-link",
        headers=_auth(organizer),
    )
    assert response.status_code == 200, response.text
    return str(response.json()["invite_token"])


def test_create_team_with_valid_link(client: TestClient, session: Session) -> None:
    tournament = _custom(session)
    captain = _make_account(session)

    team = _create_ok(
        client,
        captain,
        tournament.id,
        "邀請隊",
        invite_token=_invite(session, tournament.id),
    )

    assert team["name"] == "邀請隊"
    assert repository.get_membership(session, tournament.id, captain.id) is not None


def test_create_team_without_link_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament = _custom(session)
    captain = _make_account(session)

    response = _create(client, captain, tournament.id, "沒連結隊")

    _assert_invite_required(response, NO_LINK)
    assert repository.get_membership(session, tournament.id, captain.id) is None


def test_create_team_with_empty_link_counts_as_missing(
    client: TestClient, session: Session
) -> None:
    tournament = _custom(session)

    response = _create(client, _make_account(session), tournament.id, invite_token="")

    _assert_invite_required(response, NO_LINK)


def test_create_team_with_wrong_link_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament = _custom(session)

    response = _create(
        client, _make_account(session), tournament.id, invite_token="亂打的連結"
    )

    _assert_invite_required(response, EXPIRED_LINK)


def test_reset_link_rejects_old_token_and_keeps_existing_team(
    client: TestClient, session: Session
) -> None:
    tournament = _custom(session)
    old = _invite(session, tournament.id)
    first = _create_ok(
        client, _make_account(session), tournament.id, "先建隊", invite_token=old
    )

    new = _reset(client, session, tournament)
    stale = _create(
        client, _make_account(session), tournament.id, "舊連結隊", invite_token=old
    )
    fresh = _create(
        client, _make_account(session), tournament.id, "新連結隊", invite_token=new
    )

    # 對話框開著時連結被重設：建隊被拒並回失效的訊息
    _assert_invite_required(stale, EXPIRED_LINK)
    assert fresh.status_code == 201, fresh.text
    # 已建立的隊伍不受影響，隊友仍可經隊伍邀請連結加入
    assert repository.get_team(session, uuid.UUID(first["id"])) is not None
    joined = _join(client, _make_account(session), first["invite_token"])
    assert joined.status_code == 200, joined.text


def test_teammate_joins_custom_team_without_tournament_link(
    client: TestClient, session: Session
) -> None:
    tournament = _custom(session)
    team = _create_ok(
        client,
        _make_account(session),
        tournament.id,
        invite_token=_invite(session, tournament.id),
    )
    teammate = _make_account(session, display_name="隊友")

    response = _join(client, teammate, team["invite_token"])

    assert response.status_code == 200, response.text
    assert repository.get_membership(session, tournament.id, teammate.id) is not None


@pytest.mark.parametrize("invite_token", [None, "任意值"])
def test_campus_ignores_invite_token(
    client: TestClient, session: Session, invite_token: str | None
) -> None:
    tournament = _tournament(session)

    response = _create(
        client, _make_account(session), tournament.id, invite_token=invite_token
    )

    assert response.status_code == 201, response.text


def test_existing_checks_run_before_link_check(
    client: TestClient, session: Session
) -> None:
    """鎖賽事、報名期間、主辦方、已在賽事的檢查都在比對連結之前。"""
    tournament = _custom(session)
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    member = _make_account(session)
    _create_ok(
        client,
        member,
        tournament.id,
        "已有隊",
        invite_token=_invite(session, tournament.id),
    )

    as_organizer = _create(client, organizer, tournament.id, "主辦隊")
    already = _create(client, member, tournament.id, "第二隊")
    _set_status(session, tournament.id, TournamentStatus.CLOSED)
    closed = _create(client, _make_account(session), tournament.id, "截止隊")

    assert _error_code(as_organizer) == "ORGANIZER_CANNOT_JOIN"
    assert _error_code(already) == "ALREADY_IN_TOURNAMENT"
    assert _error_code(closed) == "REGISTRATION_CLOSED"
