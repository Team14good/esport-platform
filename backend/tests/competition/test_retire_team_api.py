"""Story 4.5：`GET`／`POST /teams/{team_id}/retirement` 的 HTTP 層（登入、commit、回應格式）。

registration 以 `fake_registration` 替身；隊長帳號由 `fake.set_captain` 控制。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.modules.competition import registration_port
from app.modules.identity.models import Account
from tests.competition.conftest import FakeRegistration, draw_with
from tests.competition.test_confirm_advance import _rows, _team
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")


class World:
    def __init__(self, session: Session, fake: FakeRegistration, waitlist: int) -> None:
        self.fake = fake
        self.tournament, _bracket = draw_with(session, fake, 8)
        self.accounts: dict[uuid.UUID, Account] = {}
        for team_id in fake.teams:
            account = make_account(session)
            fake.set_captain(team_id, account.id)
            self.accounts[team_id] = account
        fake.add_waitlist(waitlist)
        self.unverified = make_account(session, verified=False)
        fake.players.setdefault(_team(fake, 7), set()).add(self.unverified.id)

    def url(self, k: int) -> str:
        return f"{API}/teams/{_team(self.fake, k)}/retirement"

    def headers(self, client: TestClient, k: int) -> dict[str, str]:
        return bearer(token_for(client, self.accounts[_team(self.fake, k)]))


@pytest.fixture
def world(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> World:
    monkeypatch.setattr(registration_port, "is_captain", fake_registration.is_captain)
    monkeypatch.setattr(registration_port, "is_member", fake_registration.is_member)
    result = World(session, fake_registration, waitlist=1)
    session.commit()
    return result


def test_get_requires_login(client: TestClient, world: World) -> None:
    assert client.get(world.url(7)).status_code == 401
    assert client.post(world.url(7)).status_code == 401


def test_get_status_for_captain(client: TestClient, world: World) -> None:
    response = client.get(world.url(7), headers=world.headers(client, 7))

    assert response.status_code == 200
    assert response.json() == {"retirable": True, "reason": None}


def test_get_status_for_another_team_is_403(client: TestClient, world: World) -> None:
    response = client.get(world.url(7), headers=world.headers(client, 8))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TEAM_MEMBER_REQUIRED"


def test_post_retires_the_team_and_commits(
    client: TestClient, session: Session, world: World
) -> None:
    fake = world.fake
    waiting = fake.waitlist[0]

    response = client.post(world.url(7), headers=world.headers(client, 7))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replacement_team_id"] == str(waiting)
    rows = _rows(session, world.tournament.id)
    assert str(body["match_id"]) == str(rows["M1"].id)
    assert waiting in (rows["M1"].team_a_id, rows["M1"].team_b_id)
    # 退賽後不能再退
    again = client.post(world.url(7), headers=world.headers(client, 7))
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "TEAM_NOT_RETIRABLE"


def test_post_by_another_captain_is_403_and_changes_nothing(
    client: TestClient, session: Session, world: World
) -> None:
    before = _rows(session, world.tournament.id)["M1"].team_a_id

    response = client.post(world.url(7), headers=world.headers(client, 8))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TEAM_MEMBER_REQUIRED"
    assert _rows(session, world.tournament.id)["M1"].team_a_id == before
    assert world.fake.retired == []


def test_post_unknown_team_is_404(client: TestClient, world: World) -> None:
    response = client.post(
        f"{API}/teams/{uuid.uuid4()}/retirement", headers=world.headers(client, 7)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TEAM_NOT_FOUND"


def test_unverified_account_cannot_use_the_endpoints(
    client: TestClient, world: World
) -> None:
    headers = bearer(token_for(client, world.unverified))

    assert client.get(world.url(7), headers=headers).status_code == 403
    assert client.post(world.url(7), headers=headers).status_code == 403
    assert world.fake.retired == []
