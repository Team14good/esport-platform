"""Story 3.9：S2「正取隊伍」的公開名單（`GET /tournaments/{id}/accepted-teams`）。

列入 `accepted`、`drawn`、`retired`，依 `(隊名, id)` 排序；校園賽優先期結束前不公布，
自訂模式直接公布；不需登入，回應只有隊伍 id 與隊名。
"""

import secrets
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock
from app.core.errors import BusinessError
from app.modules.registration import repository, service
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.registration.test_teams import (
    API,
    _auth,
    _create_ok,
    _make_account,
    _tournament,
)

# 所有案例都凍結時鐘，期限比較不受執行時間影響
pytestmark = pytest.mark.usefixtures("frozen_clock")


def _url(tournament_id: uuid.UUID) -> str:
    return f"{API}/tournaments/{tournament_id}/accepted-teams"


def _patch_tournament(
    session: Session, tournament_id: uuid.UUID, **fields: Any
) -> None:
    """直接改賽事列（測試用：狀態、模式、優先期結束時間）。"""
    row = session.get(Tournament, tournament_id)
    assert row is not None
    for key, value in fields.items():
        setattr(row, key, value)
    session.add(row)
    session.flush()


def _team(
    client: TestClient,
    session: Session,
    tournament: TournamentRead,
    name: str,
    status: RegistrationStatus,
) -> uuid.UUID:
    """在賽事建一隊並直接把報名改為 `status`，回傳隊伍 id。"""
    team = _create_ok(client, _make_account(session), tournament.id, name)
    registration = repository.get_registration_by_team(session, uuid.UUID(team["id"]))
    assert registration is not None
    registration.status = status
    session.add(registration)
    session.flush()
    return uuid.UUID(team["id"])


def _after_priority(session: Session, tournament: TournamentRead) -> None:
    _patch_tournament(
        session, tournament.id, priority_end=clock.now() - timedelta(minutes=1)
    )


def test_lists_accepted_teams_sorted_by_name_after_priority_window(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    b = _team(client, session, tournament, "B 隊", RegistrationStatus.ACCEPTED)
    a = _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    _team(client, session, tournament, "C 隊", RegistrationStatus.WAITLISTED)
    _team(client, session, tournament, "D 隊", RegistrationStatus.PENDING)
    _team(client, session, tournament, "E 隊", RegistrationStatus.FORMING)
    _after_priority(session, tournament)

    response = client.get(_url(tournament.id))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "announce_at": None,
        "teams": [
            {"id": str(a), "name": "A 隊"},
            {"id": str(b), "name": "B 隊"},
        ],
    }


def test_service_sorts_by_name_then_id(client: TestClient, session: Session) -> None:
    # 直接驗 service 的排序鍵 `(隊名, id)`（同一賽事隊名唯一，id 只是次要鍵）
    tournament = _tournament(session)
    ids = [
        _team(client, session, tournament, name, RegistrationStatus.ACCEPTED)
        for name in ("乙", "甲", "丙")
    ]
    _after_priority(session, tournament)

    result = service.list_public_accepted_teams(session, tournament_id=tournament.id)

    expected = sorted(zip(["乙", "甲", "丙"], ids, strict=True))
    assert [(team.name, team.id) for team in result.teams] == expected


def test_after_draw_lists_drawn_and_retired_only(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    drawn = _team(client, session, tournament, "已參賽", RegistrationStatus.DRAWN)
    retired = _team(client, session, tournament, "退賽", RegistrationStatus.RETIRED)
    for name, status in (
        ("取消資格", RegistrationStatus.DISQUALIFIED),
        ("退回", RegistrationStatus.REJECTED),
        ("撤回", RegistrationStatus.WITHDRAWN),
    ):
        _team(client, session, tournament, name, status)
    _after_priority(session, tournament)
    _patch_tournament(session, tournament.id, status=TournamentStatus.PUBLISHED)

    body = client.get(_url(tournament.id)).json()

    assert body["announce_at"] is None
    assert {team["id"] for team in body["teams"]} == {str(drawn), str(retired)}


@pytest.mark.parametrize("status", [TournamentStatus.OPEN, TournamentStatus.UPCOMING])
def test_campus_priority_window_hides_teams(
    client: TestClient,
    session: Session,
    status: TournamentStatus,
) -> None:
    tournament = _tournament(session)
    # 異常資料：優先期內就有正取，仍不公布
    _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    priority_end = clock.now() + timedelta(hours=2)
    _patch_tournament(session, tournament.id, priority_end=priority_end, status=status)

    response = client.get(_url(tournament.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["teams"] == []
    assert body["announce_at"] is not None
    result = service.list_public_accepted_teams(session, tournament_id=tournament.id)
    assert result.announce_at == priority_end
    assert result.teams == []


def test_announces_at_the_exact_priority_end(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session)
    a = _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    _patch_tournament(session, tournament.id, priority_end=clock.now())

    body = client.get(_url(tournament.id)).json()

    assert body == {"announce_at": None, "teams": [{"id": str(a), "name": "A 隊"}]}

    # 前一刻仍不公布
    frozen_clock.set(clock.now() - timedelta(microseconds=1))
    assert client.get(_url(tournament.id)).json()["teams"] == []


def test_custom_mode_announces_immediately(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    a = _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    _patch_tournament(
        session,
        tournament.id,
        mode=TournamentMode.CUSTOM,
        invite_token=secrets.token_urlsafe(32),
        priority_end=clock.now() + timedelta(hours=2),
    )

    body = client.get(_url(tournament.id)).json()

    assert body == {"announce_at": None, "teams": [{"id": str(a), "name": "A 隊"}]}


def test_cancelled_tournament_still_lists_teams(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    a = _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    _after_priority(session, tournament)
    _patch_tournament(session, tournament.id, status=TournamentStatus.CANCELLED)

    body = client.get(_url(tournament.id)).json()

    assert body["teams"] == [{"id": str(a), "name": "A 隊"}]


def test_does_not_require_login_and_ignores_token(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    _after_priority(session, tournament)

    anonymous = client.get(_url(tournament.id))
    logged_in = client.get(_url(tournament.id), headers=_auth(_make_account(session)))

    assert anonymous.status_code == 200, anonymous.text
    assert logged_in.status_code == 200, logged_in.text
    assert anonymous.json() == logged_in.json()


def test_unknown_tournament_is_404(client: TestClient, session: Session) -> None:
    response = client.get(_url(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TOURNAMENT_NOT_FOUND"
    with pytest.raises(BusinessError) as excinfo:
        service.list_public_accepted_teams(session, tournament_id=uuid.uuid4())
    assert excinfo.value.code == "TOURNAMENT_NOT_FOUND"


def test_response_has_no_personal_data(client: TestClient, session: Session) -> None:
    tournament = _tournament(session)
    team_id = _team(client, session, tournament, "A 隊", RegistrationStatus.ACCEPTED)
    for member in repository.list_members(session, team_id):
        member.game_account_id = "SecretGamer#1234"
        member.rank_tier = "鑽石"
        member.rank_score = 80
        member.rank_screenshot_key = "secret-screenshot.png"
        session.add(member)
    session.flush()
    _after_priority(session, tournament)

    response = client.get(_url(tournament.id))

    body = response.json()
    assert set(body) == {"announce_at", "teams"}
    assert [set(team) for team in body["teams"]] == [{"id", "name"}]
    for secret in ("SecretGamer", "鑽石", "secret-screenshot", "@example.com"):
        assert secret not in response.text
