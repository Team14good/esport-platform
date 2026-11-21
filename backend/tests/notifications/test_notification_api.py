"""Story 1.6：通知中心 API（列表、未讀數、標為已讀；只能看與標記自己的通知）。"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock, events
from app.core.events import Event
from app.modules.identity.models import Account
from app.modules.notifications import repository
from app.modules.notifications.models import Notification
from tests.conftest import FrozenClock
from tests.helpers import API, bearer, make_account, token_for


class LampLit(Event):
    """測試專用事件：只用來當通知的來源事件。"""

    lamp_id: uuid.UUID


def _notify(
    session: Session, account: Account, *, title: str = "通知", minutes_ago: int = 0
) -> Notification:
    event = events.publish(session, LampLit(lamp_id=uuid.uuid4()))
    repository.add_notification_if_absent(
        session,
        event_id=event.id,
        account_id=account.id,
        type=event.type,
        title=title,
        body="說明",
        link=f"/lamps/{event.payload['lamp_id']}",
        now=clock.now() - timedelta(minutes=minutes_ago),
    )
    notification = repository.get_by_event_and_account(
        session, event_id=event.id, account_id=account.id
    )
    assert notification is not None
    return notification


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


@pytest.mark.usefixtures("frozen_clock")
def test_list_is_newest_first_and_paginated_by_20(
    client: TestClient, session: Session
) -> None:
    me = make_account(session)
    other = make_account(session)
    for i in range(25):
        _notify(session, me, title=f"第 {i} 則", minutes_ago=i)
    _notify(session, other, title="別人的")
    headers = _headers(client, me)

    first = client.get(f"{API}/notifications", headers=headers)
    second = client.get(f"{API}/notifications?page=2", headers=headers)

    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["title"] for item in body["items"]] == [
        f"第 {i} 則" for i in range(20)
    ]
    item = body["items"][0]
    assert set(item) == {"id", "type", "title", "body", "link", "created_at", "read_at"}
    assert item["read_at"] is None
    assert [item["title"] for item in second.json()["items"]] == [
        f"第 {i} 則" for i in range(20, 25)
    ]


@pytest.mark.usefixtures("frozen_clock")
def test_same_time_is_ordered_by_id_desc(client: TestClient, session: Session) -> None:
    me = make_account(session)
    created = [_notify(session, me) for _ in range(3)]

    response = client.get(f"{API}/notifications", headers=_headers(client, me))

    expected = sorted((str(n.id) for n in created), reverse=True)
    assert [item["id"] for item in response.json()["items"]] == expected


def test_page_beyond_total_is_empty(client: TestClient, session: Session) -> None:
    me = make_account(session)
    _notify(session, me)

    response = client.get(f"{API}/notifications?page=3", headers=_headers(client, me))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 1


@pytest.mark.parametrize("page", ["0", "-1", "abc"])
def test_invalid_page_is_422(client: TestClient, session: Session, page: str) -> None:
    me = make_account(session)

    response = client.get(
        f"{API}/notifications?page={page}", headers=_headers(client, me)
    )

    assert response.status_code == 422


def test_unread_count_counts_only_my_unread(
    client: TestClient, session: Session
) -> None:
    me = make_account(session)
    other = make_account(session)
    read = _notify(session, me)
    _notify(session, me)
    _notify(session, me)
    _notify(session, other)
    read.read_at = clock.now()
    session.add(read)
    session.flush()

    response = client.get(
        f"{API}/notifications/unread-count", headers=_headers(client, me)
    )

    assert response.status_code == 200
    assert response.json() == {"count": 2}


def test_unverified_account_can_read_notifications(
    client: TestClient, session: Session
) -> None:
    me = make_account(session, verified=False)
    _notify(session, me)

    response = client.get(
        f"{API}/notifications/unread-count", headers=_headers(client, me)
    )

    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_mark_read_sets_read_at_once(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    me = make_account(session)
    notification = _notify(session, me)
    headers = _headers(client, me)
    first_read_at = frozen_clock.now()

    response = client.post(
        f"{API}/notifications/{notification.id}/read", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(notification.id)
    assert body["read_at"] is not None
    count = client.get(f"{API}/notifications/unread-count", headers=headers)
    assert count.json() == {"count": 0}

    # 已讀過的保持原本的 read_at
    frozen_clock.advance(timedelta(hours=1))
    again = client.post(f"{API}/notifications/{notification.id}/read", headers=headers)
    assert again.status_code == 200
    assert again.json()["read_at"] == body["read_at"]
    session.refresh(notification)
    assert notification.read_at == first_read_at


def test_marking_someone_elses_notification_is_404_and_unchanged(
    client: TestClient, session: Session
) -> None:
    owner = make_account(session)
    intruder = make_account(session)
    notification = _notify(session, owner)

    response = client.post(
        f"{API}/notifications/{notification.id}/read",
        headers=_headers(client, intruder),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {"code": "NOTIFICATION_NOT_FOUND", "message": "找不到這則通知。"}
    }
    session.refresh(notification)
    assert notification.read_at is None


def test_marking_unknown_notification_is_404(
    client: TestClient, session: Session
) -> None:
    me = make_account(session)

    response = client.post(
        f"{API}/notifications/{uuid.uuid4()}/read", headers=_headers(client, me)
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_someone_elses_notifications_are_not_listed(
    client: TestClient, session: Session
) -> None:
    owner = make_account(session)
    intruder = make_account(session)
    _notify(session, owner)

    response = client.get(f"{API}/notifications", headers=_headers(client, intruder))

    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/notifications"),
        ("GET", "/notifications/unread-count"),
        ("POST", f"/notifications/{uuid.uuid4()}/read"),
    ],
)
def test_signed_out_is_401(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, f"{API}{path}")

    assert response.status_code == 401
