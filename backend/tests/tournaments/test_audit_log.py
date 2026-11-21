"""Story 2.8：主辦方查閱操作紀錄的 API（排序、分頁、操作者名稱與權限）。"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit, clock
from app.modules.identity.models import Account
from app.modules.tournaments import service
from app.modules.tournaments.models import TournamentRead
from tests.conftest import FrozenClock
from tests.helpers import (
    API,
    admin_headers,
    bearer,
    make_account,
    make_tournament,
    member_headers,
    organizer_headers,
    token_for,
)


def _url(tournament_id: uuid.UUID, page: int | None = None) -> str:
    url = f"{API}/organizer/tournaments/{tournament_id}/audit-log"
    return url if page is None else f"{url}?page={page}"


def _error_code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


@pytest.fixture
def organizer(session: Session) -> Account:
    account = make_account(session, organizer=True)
    account.display_name = "主辦小明"
    session.add(account)
    session.flush()
    return account


@pytest.fixture
def tournament(session: Session, organizer: Account) -> TournamentRead:
    created = make_tournament(session, organizer=organizer)
    # 讓 API 請求（另一個 savepoint session）看得到 tournament.created
    session.flush()
    return created


def _record(
    session: Session,
    tournament_id: uuid.UUID | None,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament_id,
        action=action,
        entity_type="test",
        entity_id=uuid.uuid4(),
        before=None,
        after={"action": action},
    )
    session.flush()


def _get(client: TestClient, account: Account, url: str) -> Any:
    response = client.get(url, headers=bearer(token_for(client, account)))
    assert response.status_code == 200, response.text
    return response.json()


def test_pages_newest_first_with_same_time_in_reverse_write_order(
    client: TestClient,
    session: Session,
    organizer: Account,
    frozen_clock: FrozenClock,
) -> None:
    """I/O：25 筆紀錄，第 1 頁 20 筆（最新在前），第 2 頁 5 筆；同一時間依寫入順序倒序。"""
    tournament = make_tournament(session, organizer=organizer)  # tournament.created
    # 23 筆各差 1 分鐘，最後 1 筆與前一筆同一時間
    for index in range(23):
        frozen_clock.advance(timedelta(minutes=1))
        _record(session, tournament.id, f"test.{index:02d}")
    _record(session, tournament.id, "test.same_time")

    first = _get(client, organizer, _url(tournament.id))
    second = _get(client, organizer, _url(tournament.id, 2))

    assert (first["total"], first["page"], first["page_size"]) == (25, 1, 20)
    assert (second["total"], second["page"], second["page_size"]) == (25, 2, 20)
    actions = [item["action"] for item in first["items"] + second["items"]]
    assert actions == [
        "test.same_time",
        *[f"test.{index:02d}" for index in reversed(range(23))],
        "tournament.created",
    ]
    assert len(first["items"]) == 20
    assert len(second["items"]) == 5


def test_page_beyond_last_returns_empty_items_with_total(
    client: TestClient, organizer: Account, tournament: TournamentRead
) -> None:
    body = _get(client, organizer, _url(tournament.id, 99))

    assert body == {"items": [], "total": 1, "page": 99, "page_size": 20}


@pytest.mark.parametrize("page", [0, 100_001])
def test_page_out_of_range_is_422(
    client: TestClient, organizer: Account, tournament: TournamentRead, page: int
) -> None:
    response = client.get(
        _url(tournament.id, page), headers=bearer(token_for(client, organizer))
    )

    assert response.status_code == 422


def test_system_and_account_actors(
    client: TestClient,
    session: Session,
    organizer: Account,
    frozen_clock: FrozenClock,
) -> None:
    """AC：worker 轉開放報名（操作者 system）排在建立賽事（主辦方）之前。"""
    tournament = make_tournament(
        session,
        organizer=organizer,
        registration_start=(clock.now() + timedelta(hours=1)).isoformat(),
    )
    frozen_clock.advance(timedelta(hours=2))
    while service.open_due_registration(session):
        pass
    session.flush()

    items = _get(client, organizer, _url(tournament.id))["items"]

    assert [item["action"] for item in items] == [
        "tournament.status_changed",
        "tournament.created",
    ]
    system, created = items
    assert system["actor_id"] is None
    assert system["actor_display_name"] is None
    assert system["before"] == {"status": "upcoming"}
    assert system["after"] == {"status": "open"}
    assert created["actor_id"] == str(organizer.id)
    assert created["actor_display_name"] == "主辦小明"
    assert created["before"] is None
    assert created["after"]["name"] == "期中盃"
    assert created["entity_type"] == "tournament"
    assert created["entity_id"] == str(tournament.id)


def test_excludes_other_tournaments_and_account_records(
    client: TestClient,
    session: Session,
    organizer: Account,
    tournament: TournamentRead,
) -> None:
    other = make_tournament(session, organizer=organizer)
    _record(session, other.id, "test.other_tournament")
    _record(session, None, "account.profile_updated", actor_id=organizer.id)

    body = _get(client, organizer, _url(tournament.id))

    assert body["total"] == 1
    assert [item["action"] for item in body["items"]] == ["tournament.created"]


def test_other_organizers_tournament_is_403(
    client: TestClient, session: Session, tournament: TournamentRead
) -> None:
    response = client.get(
        _url(tournament.id), headers=organizer_headers(client, session)
    )

    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"


def test_non_organizer_is_403(
    client: TestClient, session: Session, tournament: TournamentRead
) -> None:
    for headers in (member_headers(client, session), admin_headers(client, session)):
        response = client.get(_url(tournament.id), headers=headers)

        assert response.status_code == 403
        assert _error_code(response) == "ORGANIZER_REQUIRED"


def test_without_token_is_401(client: TestClient, tournament: TournamentRead) -> None:
    response = client.get(_url(tournament.id))

    assert response.status_code == 401
    assert _error_code(response) == "AUTHENTICATION_REQUIRED"


def test_missing_tournament_is_404(client: TestClient, organizer: Account) -> None:
    response = client.get(
        _url(uuid.uuid4()), headers=bearer(token_for(client, organizer))
    )

    assert response.status_code == 404
    assert _error_code(response) == "TOURNAMENT_NOT_FOUND"
