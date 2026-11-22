"""Story 4.5／6.5：退賽與取消資格遞補的呼叫順序，用真的 registration 與真的 `draw`。

`fake_registration` 替身不管學校，驗不出「先讓出名額、再遞補」的順序。這裡用真的報名資料
（比照 tests/disputes/test_resolve_report.py）：X 校已有 2 隊參賽，退賽的就是其中一隊；
候補有 X 校（分數較高）與 Y 校。順序正確時 X 校讓出名額後剩 1 隊，X 校候補遞補；
若先遞補、後退賽，X 校仍是 2 隊，X 校候補被略過、改由 Y 校遞補，測試就會失敗。
"""

import random
import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.competition import service
from app.modules.competition.models import Match
from app.modules.identity.models import Account, School
from app.modules.registration import repository as registration_repository
from app.modules.registration.models import RegistrationStatus as R
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.disputes.test_reports import _team
from tests.registration.test_first_come_submission import _first_come, _preset
from tests.registration.test_submit_registration import _school
from tests.registration.test_teams import _make_account, _set_status, _tournament

pytestmark = pytest.mark.usefixtures("frozen_clock")


@dataclass
class World:
    tournament: TournamentRead
    organizer: Account
    retiree: uuid.UUID
    retiree_captain: Account
    x_waitlisted: uuid.UUID
    y_waitlisted: uuid.UUID


def _status(session: Session, team_id: uuid.UUID) -> R:
    registration = registration_repository.get_registration_by_team(session, team_id)
    assert registration is not None
    session.refresh(registration)
    return R(registration.status)


def _world(client: TestClient, session: Session) -> World:
    """4 隊抽籤：X 校 2 隊（含退出者）、另兩校各 1 隊；候補 X 校（90 分）與 Y 校（70 分）。"""
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    x, z1, z2, y = (_school(session) for _ in range(4))
    schools: list[School] = [x, x, z1, z2]
    teams: list[tuple[uuid.UUID, Account]] = []
    for k, school in enumerate(schools, start=1):
        team, captain = _team(client, session, tournament.id, f"隊伍{k}")
        team_id = uuid.UUID(team["id"])
        _preset(
            session,
            tournament,
            school,
            R.ACCEPTED,
            submitted_at=_first_come(tournament, k),
            team_id=team_id,
        )
        teams.append((team_id, captain))
    _set_status(session, tournament.id, TournamentStatus.CLOSED)
    service.draw(
        session,
        tournament_id=tournament.id,
        actor_id=organizer.id,
        rng=random.Random(7),
    )
    x_wait = _preset(
        session,
        tournament,
        x,
        R.WAITLISTED,
        submitted_at=_first_come(tournament, 10),
        score="90",
    )
    y_wait = _preset(
        session,
        tournament,
        y,
        R.WAITLISTED,
        submitted_at=_first_come(tournament, 11),
        score="70",
    )
    retiree, retiree_captain = teams[0]
    return World(
        tournament, organizer, retiree, retiree_captain, x_wait.team_id, y_wait.team_id
    )


def _holder(session: Session, w: World, team_id: uuid.UUID) -> Match | None:
    session.expire_all()
    bracket = service.get_bracket(session, tournament_id=w.tournament.id)
    assert bracket is not None
    for match in bracket.matches:
        if team_id in (match.team_a_id, match.team_b_id):
            return session.get(Match, match.id)
    return None


def test_retire_hands_the_slot_to_the_waitlisted_schoolmate(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)

    result = service.retire_team(
        session, team_id=w.retiree, account_id=w.retiree_captain.id
    )

    assert result.replacement_team_id == w.x_waitlisted
    assert _status(session, w.retiree) == R.RETIRED
    assert _status(session, w.x_waitlisted) == R.DRAWN
    assert _status(session, w.y_waitlisted) == R.WAITLISTED
    assert _holder(session, w, w.x_waitlisted) is not None
    assert _holder(session, w, w.retiree) is None


def test_disqualify_hands_the_slot_to_the_waitlisted_schoolmate(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)

    result = service.disqualify(
        session,
        tournament_id=w.tournament.id,
        team_id=w.retiree,
        actor_id=w.organizer.id,
    )

    assert result.replacement_team_id == w.x_waitlisted
    assert _status(session, w.retiree) == R.DISQUALIFIED
    assert _status(session, w.x_waitlisted) == R.DRAWN
    assert _status(session, w.y_waitlisted) == R.WAITLISTED
    assert _holder(session, w, w.x_waitlisted) is not None


# ---------------------------------------------------------------- 已取消的賽事（2.6）


def test_cancelled_tournament_rejects_retirement(
    client: TestClient, session: Session
) -> None:
    """用 2.6 真的 `cancel_tournament` 取消已抽籤的賽事後，退賽回 409、資料不變。"""
    w = _world(client, session)
    tournaments_service.cancel_tournament(
        session, tournament_id=w.tournament.id, actor_id=w.organizer.id
    )

    status = service.get_retirement_status(
        session, team_id=w.retiree, account_id=w.retiree_captain.id
    )
    with pytest.raises(BusinessError) as exc:
        service.retire_team(session, team_id=w.retiree, account_id=w.retiree_captain.id)

    assert status.retirable is False
    assert exc.value.status_code == 409
    assert exc.value.code == "TEAM_NOT_RETIRABLE"
    assert _status(session, w.retiree) == R.DRAWN
    assert _status(session, w.x_waitlisted) == R.WAITLISTED
    assert _holder(session, w, w.retiree) is not None


def test_cancelled_tournament_rejects_disqualify_without_backfill(
    client: TestClient, session: Session
) -> None:
    """已取消的賽事取消資格交給 6.5 原本的檢查，回 409 `TOURNAMENT_CANCELLED`，不遞補。"""
    w = _world(client, session)
    tournaments_service.cancel_tournament(
        session, tournament_id=w.tournament.id, actor_id=w.organizer.id
    )

    with pytest.raises(BusinessError) as exc:
        service.disqualify(
            session,
            tournament_id=w.tournament.id,
            team_id=w.retiree,
            actor_id=w.organizer.id,
        )

    assert exc.value.status_code == 409
    assert exc.value.code == "TOURNAMENT_CANCELLED"
    assert _status(session, w.retiree) == R.DRAWN
    assert _status(session, w.x_waitlisted) == R.WAITLISTED
