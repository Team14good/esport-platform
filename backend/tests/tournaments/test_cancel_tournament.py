"""Story 2.6：主辦方取消賽事（I/O 矩陣前 7 列）。

worker 略過已取消賽事的部分在 tests/worker/test_cancelled_tournament_skipped.py。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import audit
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.identity.models import Account
from app.modules.tournaments import service
from app.modules.tournaments.models import Tournament, TournamentStatus
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

S = TournamentStatus
CANCELLABLE = [S.UPCOMING, S.OPEN, S.CLOSED, S.PUBLISHED, S.ONGOING]

pytestmark = pytest.mark.usefixtures("frozen_clock")


def _cancel_url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}/cancel"


def _owned_tournament(
    client: TestClient, session: Session, status: S
) -> tuple[uuid.UUID, Account, dict[str, str]]:
    """主辦方本人的賽事，狀態直接設成指定值（測試用，略過轉換規則）。"""
    organizer = make_account(session, organizer=True)
    tournament_id = make_tournament(session, organizer=organizer).id
    row = session.get(Tournament, tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.flush()
    return tournament_id, organizer, bearer(token_for(client, organizer))


def _cancelled_events(session: Session, tournament_id: uuid.UUID) -> list[OutboxEvent]:
    rows = session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.type == "TournamentCancelled")
        .order_by(col(OutboxEvent.created_at))
    ).all()
    return [
        row for row in rows if row.payload.get("tournament_id") == str(tournament_id)
    ]


def _status(session: Session, tournament_id: uuid.UUID) -> S:
    return service.get_tournament(session, tournament_id=tournament_id).status


@pytest.mark.parametrize("status", CANCELLABLE)
def test_owner_cancels_tournament(
    client: TestClient, session: Session, status: S
) -> None:
    tournament_id, organizer, headers = _owned_tournament(client, session, status)

    response = client.post(_cancel_url(tournament_id), headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(tournament_id)
    assert body["status"] == "cancelled"
    assert _status(session, tournament_id) == S.CANCELLED
    row = audit.list_for_tournament(session, tournament_id)[-1]
    assert row.action == "tournament.status_changed"
    assert row.actor_id == organizer.id
    assert row.before == {"status": status.value}
    assert row.after == {"status": "cancelled"}
    [event] = _cancelled_events(session, tournament_id)
    # 事件只帶實體 id
    assert event.payload == {"tournament_id": str(tournament_id)}
    assert event.processed_at is None


@pytest.mark.parametrize("status", [S.FINISHED, S.CANCELLED])
def test_finished_or_cancelled_is_409_and_changes_nothing(
    client: TestClient, session: Session, status: S
) -> None:
    tournament_id, _, headers = _owned_tournament(client, session, status)
    logs_before = audit.list_for_tournament(session, tournament_id)

    response = client.post(_cancel_url(tournament_id), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "TOURNAMENT_NOT_CANCELLABLE",
        "message": "已結束或已取消的賽事不能取消。",
    }
    assert _status(session, tournament_id) == status
    assert audit.list_for_tournament(session, tournament_id) == logs_before
    assert _cancelled_events(session, tournament_id) == []


def test_cancelling_twice_publishes_one_event(
    client: TestClient, session: Session
) -> None:
    tournament_id, _, headers = _owned_tournament(client, session, S.OPEN)

    first = client.post(_cancel_url(tournament_id), headers=headers)
    second = client.post(_cancel_url(tournament_id), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "TOURNAMENT_NOT_CANCELLABLE"
    assert len(_cancelled_events(session, tournament_id)) == 1


def test_another_organizer_is_403(client: TestClient, session: Session) -> None:
    tournament = make_tournament(session)

    response = client.post(
        _cancel_url(tournament.id), headers=organizer_headers(client, session)
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "TOURNAMENT_OWNER_REQUIRED"
    assert _status(session, tournament.id) == S.OPEN
    assert _cancelled_events(session, tournament.id) == []


def test_non_organizer_is_403(client: TestClient, session: Session) -> None:
    tournament = make_tournament(session)

    for headers in (member_headers(client, session), admin_headers(client, session)):
        response = client.post(_cancel_url(tournament.id), headers=headers)

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "ORGANIZER_REQUIRED"
    assert _status(session, tournament.id) == S.OPEN


def test_without_token_is_401(client: TestClient, session: Session) -> None:
    tournament = make_tournament(session)

    response = client.post(_cancel_url(tournament.id))

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
    assert _status(session, tournament.id) == S.OPEN


def test_missing_tournament_is_404(client: TestClient, session: Session) -> None:
    response = client.post(
        _cancel_url(uuid.uuid4()), headers=organizer_headers(client, session)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TOURNAMENT_NOT_FOUND"


def test_service_missing_tournament_is_404(session: Session) -> None:
    with pytest.raises(BusinessError) as excinfo:
        service.cancel_tournament(
            session, tournament_id=uuid.uuid4(), actor_id=uuid.uuid4()
        )

    assert excinfo.value.code == "TOURNAMENT_NOT_FOUND"
    assert excinfo.value.status_code == 404


def test_registration_after_cancel_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament_id, _, headers = _owned_tournament(client, session, S.OPEN)
    assert client.post(_cancel_url(tournament_id), headers=headers).status_code == 200

    response = client.post(
        f"{API}/tournaments/{tournament_id}/teams",
        json={"name": "取消後的隊伍"},
        headers=member_headers(client, session),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REGISTRATION_CLOSED"


def test_scores_after_cancel_are_rejected(client: TestClient, session: Session) -> None:
    tournament_id, _, headers = _owned_tournament(client, session, S.ONGOING)
    assert client.post(_cancel_url(tournament_id), headers=headers).status_code == 200

    with pytest.raises(BusinessError) as excinfo:
        service.ensure_accepting_scores(
            service.get_tournament(session, tournament_id=tournament_id)
        )

    assert excinfo.value.code == "TOURNAMENT_NOT_ACCEPTING_SCORES"
    assert excinfo.value.status_code == 409
