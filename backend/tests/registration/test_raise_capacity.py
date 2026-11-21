"""Story 3.7：主辦方提高名額（FR-9）與遞補（I/O 矩陣的提高名額各列）。

時間設定同 test_withdraw_registration.py（優先期在 T 結束）。前置報名直接寫入。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.modules.identity.models import Account
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.registration.test_first_come_submission import (
    SUBMIT_AFTER,
    _first_come,
    _in_window,
    _preset,
    _settled,
    _tournament,
)
from tests.registration.test_submit_registration import _school
from tests.registration.test_teams import (
    API,
    _auth,
    _error_code,
    _make_account,
    _set_status,
)
from tests.registration.test_withdraw_registration import (
    _backfilled_ids,
    _events,
    _status,
)

S = RegistrationStatus


def _organizer(session: Session, tournament: TournamentRead) -> Account:
    account = session.get(Account, tournament.organizer_id)
    assert account is not None
    return account


def _raise(
    client: TestClient, account: Account, tournament: TournamentRead, capacity: Any
) -> Any:
    return client.post(
        f"{API}/tournaments/{tournament.id}/capacity",
        json={"capacity": capacity},
        headers=_auth(account),
    )


def _capacity(session: Session, tournament: TournamentRead) -> int:
    session.expire_all()
    return tournaments_service.get_tournament(
        session, tournament_id=tournament.id
    ).capacity


def _capacity_logs(session: Session, tournament: TournamentRead) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "tournament.capacity_changed"
    ]


def test_raise_capacity_in_first_come_backfills_in_order(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """名額 4 已滿，改為 6；3 隊符合先搶期規則的候補 → 依順位遞補前 2 隊。"""
    tournament = _tournament(session, frozen_clock, capacity=4)
    _settled(session, tournament, [])
    for minute in range(1, 5):
        _preset(
            session,
            tournament,
            _school(session),
            S.ACCEPTED,
            submitted_at=_first_come(tournament, minute),
        )
    waiting = [
        _preset(
            session,
            tournament,
            _school(session),
            S.WAITLISTED,
            submitted_at=_first_come(tournament, minute),
        )
        for minute in (7, 5, 6)
    ]
    frozen_clock.advance(SUBMIT_AFTER)
    organizer = _organizer(session, tournament)

    response = _raise(client, organizer, tournament, 6)

    assert response.status_code == 200, response.text
    assert response.json()["capacity"] == 6
    assert _capacity(session, tournament) == 6
    assert [_status(session, r) for r in waiting] == [
        S.WAITLISTED,
        S.ACCEPTED,
        S.ACCEPTED,
    ]
    assert _backfilled_ids(session, tournament) == {
        str(waiting[1].id),
        str(waiting[2].id),
    }
    [log] = _capacity_logs(session, tournament)
    assert log.actor_id == organizer.id
    assert (log.before, log.after) == ({"capacity": 4}, {"capacity": 6})
    # 遞補的操作者是系統，可追溯：同一交易內緊接在主辦方改名額那筆之後
    assert [
        (entry.action, entry.actor_id, entry.after)
        for entry in audit.list_for_tournament(session, tournament.id)[-3:]
    ] == [
        ("tournament.capacity_changed", organizer.id, {"capacity": 6}),
        ("registration.status_changed", None, {"status": "accepted"}),
        ("registration.status_changed", None, {"status": "accepted"}),
    ]


def test_raise_capacity_in_priority_window_only_changes_capacity(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """沒有結算紀錄（優先期內）：只改名額。"""
    tournament = _tournament(session, frozen_clock, capacity=4)
    pending = [
        _preset(
            session,
            tournament,
            _school(session),
            S.PENDING,
            submitted_at=_in_window(tournament, minute),
        )
        for minute in (1, 2)
    ]

    response = _raise(client, _organizer(session, tournament), tournament, 6)

    assert response.status_code == 200, response.text
    assert _capacity(session, tournament) == 6
    assert [_status(session, r) for r in pending] == [S.PENDING, S.PENDING]
    assert _events(session, tournament, "RegistrationBackfilled") == []


def test_raise_capacity_after_deadline_uses_after_deadline_order(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """報名截止後提高名額：依截止後順位（積分）遞補，同校上限 2 隊。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_z = _school(session)
    _settled(session, tournament, [])
    for minute in (1, 2):
        _preset(
            session,
            tournament,
            school_z,
            S.ACCEPTED,
            submitted_at=_first_come(tournament, minute),
        )
    over_limit = _preset(
        session,
        tournament,
        school_z,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
        score="90",
    )
    low = _preset(
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 4),
        score="10",
    )
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    response = _raise(client, _organizer(session, tournament), tournament, 4)

    assert response.status_code == 200, response.text
    assert _status(session, low) == S.ACCEPTED
    assert _status(session, over_limit) == S.WAITLISTED


def test_raise_capacity_before_registration_opens(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """尚未開放（`upcoming`）也能提高名額；沒有結算紀錄，不遞補。"""
    tournament = _tournament(session, frozen_clock, capacity=4)
    _set_status(session, tournament.id, TournamentStatus.UPCOMING)

    response = _raise(client, _organizer(session, tournament), tournament, 6)

    assert response.status_code == 200, response.text
    assert _capacity(session, tournament) == 6
    assert len(_capacity_logs(session, tournament)) == 1
    assert _events(session, tournament, "RegistrationBackfilled") == []


@pytest.mark.parametrize("capacity", [4, 3])
def test_capacity_not_increased_is_422(
    client: TestClient, session: Session, frozen_clock: FrozenClock, capacity: int
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)

    response = _raise(client, _organizer(session, tournament), tournament, capacity)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == "CAPACITY_NOT_INCREASED"
    assert error["loc"] == ["body", "capacity"]
    assert _capacity(session, tournament) == 4
    assert _capacity_logs(session, tournament) == []


def test_capacity_below_minimum_is_field_error(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)

    response = _raise(client, _organizer(session, tournament), tournament, 1)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "capacity"]


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.PUBLISHED,
        TournamentStatus.ONGOING,
        TournamentStatus.FINISHED,
        TournamentStatus.CANCELLED,
    ],
)
def test_capacity_not_editable_after_draw(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    status: TournamentStatus,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)
    _set_status(session, tournament.id, status)

    response = _raise(client, _organizer(session, tournament), tournament, 6)

    assert response.status_code == 409
    assert _error_code(response) == "CAPACITY_NOT_EDITABLE"
    assert _capacity(session, tournament) == 4


def test_only_the_organizer_can_raise_capacity(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)

    response = _raise(client, _make_account(session), tournament, 6)

    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert _capacity(session, tournament) == 4
    missing = client.post(
        f"{API}/tournaments/{uuid.uuid4()}/capacity",
        json={"capacity": 6},
        headers=_auth(_organizer(session, tournament)),
    )
    assert missing.status_code == 404
    unauthenticated = client.post(
        f"{API}/tournaments/{tournament.id}/capacity", json={"capacity": 6}
    )
    assert unauthenticated.status_code == 401
