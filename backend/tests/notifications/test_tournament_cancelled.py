"""Story 3.9 第 2 部分：取消賽事時通知已送出報名隊伍的隊長與選手（FR-10）。

賽事以 2.6 的真實取消流程（API 或 `cancel_tournament`）取消，事件取自 outbox，
再交給 `dispatch_event`，檢查站內通知與 EmailDelivery。
"""

import random
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import events
from app.core.events import OutboxEvent
from app.modules.competition import service as competition_service
from app.modules.notifications import service
from app.modules.notifications.models import EmailDelivery, Notification
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentCancelled, TournamentStatus
from tests.disputes.test_reports import _set_registration
from tests.helpers import API, bearer, token_for
from tests.notifications.test_rules import Team, World, _world
from tests.registration.test_teams import _create_ok, _make_account, _set_status

pytestmark = pytest.mark.usefixtures("frozen_clock")

S = RegistrationStatus


def _cancelled_event(session: Session, tournament_id: uuid.UUID) -> OutboxEvent:
    [event] = [
        e
        for e in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "TournamentCancelled")
        )
        if e.payload["tournament_id"] == str(tournament_id)
    ]
    return event


def _dispatch(
    session: Session, event: OutboxEvent
) -> tuple[dict[uuid.UUID, Notification], set[uuid.UUID]]:
    service.dispatch_event(session, event)
    notifications = {
        n.account_id: n
        for n in session.exec(
            select(Notification).where(Notification.event_id == event.id)
        )
    }
    deliveries = {
        d.account_id
        for d in session.exec(
            select(EmailDelivery).where(EmailDelivery.event_id == event.id)
        )
    }
    return notifications, deliveries


def _cancel(session: Session, w: World) -> OutboxEvent:
    tournaments_service.cancel_tournament(
        session, tournament_id=w.tid, actor_id=w.organizer.id
    )
    return _cancelled_event(session, w.tid)


def _members(teams: list[Team]) -> set[uuid.UUID]:
    return {account for team in teams for account in team.members}


def test_cancel_via_api_notifies_members_of_submitted_teams_in_app_and_by_email(
    client: TestClient, session: Session
) -> None:
    """待分配、正取、候補三種已送出的隊伍，隊長與選手都收到站內通知與 Email。"""
    w = _world(client, session, count=3)
    pending, accepted, waitlisted = w.teams
    _set_registration(session, str(pending.id), S.PENDING)
    _set_registration(session, str(waitlisted.id), S.WAITLISTED)

    response = client.post(
        f"{API}/organizer/tournaments/{w.tid}/cancel",
        headers=bearer(token_for(client, w.organizer)),
    )
    assert response.status_code == 200, response.text
    notifications, deliveries = _dispatch(session, _cancelled_event(session, w.tid))

    expected = _members([pending, accepted, waitlisted])
    assert set(notifications) == expected
    assert deliveries == expected
    assert {(n.type, n.title, n.body, n.link) for n in notifications.values()} == {
        (
            "TournamentCancelled",
            "賽事已取消",
            f"「{w.tournament.name}」已由主辦方取消，你的隊伍不會再進行比賽。",
            f"/tournaments/{w.tid}",
        )
    }


@pytest.mark.parametrize(
    "status", [S.FORMING, S.REJECTED, S.WITHDRAWN, S.RETIRED, S.DISQUALIFIED]
)
def test_teams_not_submitted_or_already_out_are_not_notified(
    client: TestClient, session: Session, status: RegistrationStatus
) -> None:
    w = _world(client, session, count=2)
    notified, skipped = w.teams
    _set_registration(session, str(skipped.id), status)

    notifications, deliveries = _dispatch(session, _cancel(session, w))

    assert set(notifications) == notified.members
    assert deliveries == notified.members


def test_cancel_after_draw_notifies_every_drawn_team(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, count=4)
    _set_status(session, w.tid, TournamentStatus.CLOSED)
    competition_service.draw(
        session, tournament_id=w.tid, actor_id=w.organizer.id, rng=random.Random(7)
    )

    notifications, _ = _dispatch(session, _cancel(session, w))

    assert set(notifications) == _members(w.teams)


def test_captain_of_forming_team_alone_gets_nothing(
    client: TestClient, session: Session
) -> None:
    """只有組隊中的隊伍：沒有收件人，不建立通知也不寄信。"""
    w = _world(client, session, count=0)
    captain = _make_account(session)
    _create_ok(client, captain, w.tid, "還在組隊")

    notifications, deliveries = _dispatch(session, _cancel(session, w))

    assert notifications == {}
    assert deliveries == set()


def test_unknown_tournament_is_skipped(session: Session) -> None:
    event = events.publish(session, TournamentCancelled(tournament_id=uuid.uuid4()))

    notifications, deliveries = _dispatch(session, event)

    assert notifications == {}
    assert deliveries == set()
