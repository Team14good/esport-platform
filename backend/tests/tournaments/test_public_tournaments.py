"""Story 2.4：不需登入的公開賽事 API（I/O 矩陣的公開列表、公開單場、不洩漏資料）。"""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock
from app.modules.identity.models import School
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.helpers import API, make_account, make_tournament

LIST_URL = f"{API}/tournaments"

# PublicTournament 的欄位白名單（AD-19：不含主辦方帳號、Email、學校）
PUBLIC_FIELDS = {
    "id",
    "name",
    "status",
    "game_name",
    "capacity",
    "registration_start",
    "priority_end",
    "registration_end",
    "start_at",
    "round_interval_minutes",
    "livestream_url",
}


def _tournament_in(session: Session, status: TournamentStatus) -> uuid.UUID:
    """建立賽事後直接把狀態設成指定值（測試用，略過轉換規則）。"""
    tournament_id = make_tournament(
        session, name=f"賽事-{status.value}", livestream_url="https://twitch.tv/flow"
    ).id
    row = session.get(Tournament, tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.flush()
    return tournament_id


@pytest.mark.usefixtures("frozen_clock")
def test_anonymous_can_list_every_status_with_public_fields_only(
    client: TestClient, session: Session
) -> None:
    ids = {status: _tournament_in(session, status) for status in TournamentStatus}

    response = client.get(LIST_URL)

    assert response.status_code == 200, response.text
    by_id = {item["id"]: item for item in response.json()}
    for status, tournament_id in ids.items():
        item = by_id[str(tournament_id)]
        assert set(item) == PUBLIC_FIELDS
        assert item["status"] == status.value
        assert item["name"] == f"賽事-{status.value}"
        assert item["livestream_url"] == "https://twitch.tv/flow"


@pytest.mark.usefixtures("frozen_clock")
def test_list_is_ordered_by_start_time(client: TestClient, session: Session) -> None:
    now = clock.now()
    later = make_tournament(
        session,
        registration_end=(now + timedelta(days=9)).isoformat(),
        start_at=(now + timedelta(days=10)).isoformat(),
    )
    sooner = make_tournament(session)

    response = client.get(LIST_URL)

    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()]
    assert ids.index(str(sooner.id)) < ids.index(str(later.id))


@pytest.mark.usefixtures("frozen_clock")
def test_anonymous_can_read_one_tournament(
    client: TestClient, session: Session
) -> None:
    created = make_tournament(session)

    response = client.get(f"{LIST_URL}/{created.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == PUBLIC_FIELDS
    assert body["id"] == str(created.id)
    assert body["name"] == created.name
    assert body["status"] == created.status.value
    assert body["game_name"] == created.game_name
    assert body["capacity"] == created.capacity
    assert body["round_interval_minutes"] == created.round_interval_minutes
    for field in ("registration_start", "priority_end", "registration_end", "start_at"):
        assert datetime.fromisoformat(body[field]) == getattr(created, field), field
    assert body["livestream_url"] is None


def test_missing_tournament_is_404(client: TestClient) -> None:
    response = client.get(f"{LIST_URL}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TOURNAMENT_NOT_FOUND"


def test_malformed_tournament_id_is_422(client: TestClient) -> None:
    response = client.get(f"{LIST_URL}/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.usefixtures("frozen_clock")
def test_public_responses_do_not_leak_organizer_email_or_school(
    client: TestClient, session: Session
) -> None:
    school = School(name=f"測試大學-{uuid.uuid4().hex[:8]}")
    session.add(school)
    session.flush()
    organizer = make_account(session, organizer=True, school_id=school.id)
    created = make_tournament(session, organizer=organizer)

    for url in (LIST_URL, f"{LIST_URL}/{created.id}"):
        response = client.get(url)
        assert response.status_code == 200, response.text
        text = response.text
        assert str(organizer.id) not in text
        assert organizer.email not in text
        assert str(school.id) not in text
        assert school.name not in text
        assert "organizer" not in text
