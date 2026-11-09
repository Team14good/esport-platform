"""Story 6.4：給 disputes 檢舉用的 registration 公開函式。

`find_team_of_account`（帳號在賽事所屬的隊伍，不限角色）與 `list_teams_by_status`
（某賽事指定報名狀態的隊伍摘要）。
"""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.registration import repository, service
from app.modules.registration.models import RegistrationStatus, TeamSummary
from tests.registration.test_teams import (
    API,
    _auth,
    _create_ok,
    _make_account,
    _tournament,
)


def _set_registration(
    session: Session, team_id: str, status: RegistrationStatus
) -> None:
    registration = repository.get_registration_by_team(session, uuid.UUID(team_id))
    assert registration is not None
    registration.status = status
    session.add(registration)
    session.flush()


def test_find_team_of_account_returns_team_for_captain_and_player(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    captain = _make_account(session)
    team = _create_ok(client, captain, tournament.id)
    player = _make_account(session)
    response = client.post(
        f"{API}/team-invites/{team['invite_token']}/members", headers=_auth(player)
    )
    assert response.status_code == 200, response.text

    for account, role in ((captain, "captain"), (player, "player")):
        found = service.find_team_of_account(
            session, tournament_id=tournament.id, account_id=account.id
        )
        assert found is not None
        assert str(found.id) == team["id"]
        assert found.tournament_id == tournament.id
        assert found.name == "夜貓隊"
        assert {(m.account_id, m.role) for m in found.members} == {
            (captain.id, "captain"),
            (player.id, "player"),
        }
        assert any(m.account_id == account.id and m.role == role for m in found.members)


def test_find_team_of_account_is_none_outside_the_tournament(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    other = _tournament(session)
    captain = _make_account(session)
    _create_ok(client, captain, other.id)

    assert (
        service.find_team_of_account(
            session, tournament_id=tournament.id, account_id=captain.id
        )
        is None
    )
    assert (
        service.find_team_of_account(
            session, tournament_id=tournament.id, account_id=_make_account(session).id
        )
        is None
    )


def test_list_teams_by_status_filters_by_tournament_and_status(
    client: TestClient, session: Session
) -> None:
    tournament = _tournament(session)
    other = _tournament(session)
    statuses = {
        "正取隊": RegistrationStatus.ACCEPTED,
        "候補隊": RegistrationStatus.WAITLISTED,
        "組隊隊": RegistrationStatus.FORMING,
        "撤回隊": RegistrationStatus.WITHDRAWN,
    }
    ids: dict[str, uuid.UUID] = {}
    for name, status in statuses.items():
        team = _create_ok(client, _make_account(session), tournament.id, name)
        _set_registration(session, team["id"], status)
        ids[name] = uuid.UUID(team["id"])
    elsewhere = _create_ok(client, _make_account(session), other.id, "別場隊")
    _set_registration(session, elsewhere["id"], RegistrationStatus.ACCEPTED)

    result = service.list_teams_by_status(
        session,
        tournament_id=tournament.id,
        statuses={RegistrationStatus.ACCEPTED, RegistrationStatus.WAITLISTED},
    )

    assert result == sorted(
        [
            TeamSummary(id=ids["正取隊"], name="正取隊"),
            TeamSummary(id=ids["候補隊"], name="候補隊"),
        ],
        key=lambda team: team.id,
    )
    assert (
        service.list_teams_by_status(session, tournament_id=tournament.id, statuses=[])
        == []
    )
