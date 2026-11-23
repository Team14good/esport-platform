"""Story 3.10（epics 4.5 自訂模式的驗收條件）：自訂賽事抽籤後退賽、取消資格的遞補，
經 competition 的 `retire_team`、`disqualify` 與真的 registration、真的 `draw`。

本 Story 不改 competition（D 的模組），只新增這支測試：competition 經既有的 registration
公開函式（`has_backfill_candidate`、`backfill_drawn_from_waitlist`）取得結果。
建立賽事一律是校園賽（3.10 第 2 部分才有模式選項），所以直接把賽事列改成自訂模式。

4 隊抽籤，全部同一所學校（自訂沒有每校上限）；抽籤後加兩隊候補：早送出、積分低的同校隊
與晚送出、積分高的他校隊。最早送出的候補接手位置；改成依積分或受每校 2 隊上限時就會失敗。
"""

import random
import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core.events import OutboxEvent
from app.modules.competition import service
from app.modules.competition.models import Match
from app.modules.identity.models import Account
from app.modules.registration import repository as registration_repository
from app.modules.registration.models import RegistrationStatus as R
from app.modules.tournaments.models import (
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.disputes.test_reports import _team
from tests.registration.test_first_come_submission import _first_come, _preset
from tests.registration.test_reject_registration import _set_mode
from tests.registration.test_submit_registration import _school
from tests.registration.test_teams import _make_account, _set_status, _tournament

pytestmark = pytest.mark.usefixtures("frozen_clock")


@dataclass
class World:
    tournament: TournamentRead
    organizer: Account
    leaving: uuid.UUID
    leaving_captain: Account
    earliest: uuid.UUID | None
    later: uuid.UUID | None


def _status(session: Session, team_id: uuid.UUID) -> R:
    registration = registration_repository.get_registration_by_team(session, team_id)
    assert registration is not None
    session.refresh(registration)
    return R(registration.status)


def _world(client: TestClient, session: Session, *, waitlist: bool = True) -> World:
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    _set_mode(session, tournament.id, TournamentMode.CUSTOM)
    school = _school(session)
    teams: list[tuple[uuid.UUID, Account]] = []
    for k in range(1, 5):
        team, captain = _team(client, session, tournament.id, f"自訂隊{k}")
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
    earliest = later = None
    if waitlist:
        earliest = _preset(
            session,
            tournament,
            school,
            R.WAITLISTED,
            submitted_at=_first_come(tournament, 10),
            score="10",
        ).team_id
        later = _preset(
            session,
            tournament,
            _school(session),
            R.WAITLISTED,
            submitted_at=_first_come(tournament, 11),
            score="90",
        ).team_id
    leaving, leaving_captain = teams[0]
    return World(tournament, organizer, leaving, leaving_captain, earliest, later)


def _holder(session: Session, w: World, team_id: uuid.UUID) -> Match | None:
    session.expire_all()
    bracket = service.get_bracket(session, tournament_id=w.tournament.id)
    assert bracket is not None
    for match in bracket.matches:
        if team_id in (match.team_a_id, match.team_b_id):
            return session.get(Match, match.id)
    return None


def _backfilled_events(session: Session, w: World) -> list[OutboxEvent]:
    return [
        e
        for e in session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == "RegistrationBackfilled")
        )
        if e.payload["tournament_id"] == str(w.tournament.id)
    ]


def test_custom_retire_hands_the_slot_to_the_earliest_waitlisted(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    assert w.earliest is not None and w.later is not None

    result = service.retire_team(
        session, team_id=w.leaving, account_id=w.leaving_captain.id
    )

    assert result.replacement_team_id == w.earliest
    assert _status(session, w.leaving) == R.RETIRED
    assert _status(session, w.earliest) == R.DRAWN
    assert _status(session, w.later) == R.WAITLISTED
    assert _holder(session, w, w.earliest) is not None
    assert _holder(session, w, w.leaving) is None


def test_custom_disqualify_after_draw_hands_the_slot_without_accepting(
    client: TestClient, session: Session
) -> None:
    """取消資格本身不產生 `accepted`、不發 `RegistrationBackfilled`；最早送出的候補接手位置。"""
    w = _world(client, session)
    assert w.earliest is not None and w.later is not None

    result = service.disqualify(
        session,
        tournament_id=w.tournament.id,
        team_id=w.leaving,
        actor_id=w.organizer.id,
    )

    assert result.replacement_team_id == w.earliest
    assert _status(session, w.leaving) == R.DISQUALIFIED
    assert _status(session, w.earliest) == R.DRAWN
    assert _status(session, w.later) == R.WAITLISTED
    accepted = registration_repository.list_registrations(session, w.tournament.id)
    assert R.ACCEPTED not in {r.status for r in accepted}
    assert _backfilled_events(session, w) == []
    assert _holder(session, w, w.earliest) is not None


def test_custom_retire_without_waitlist_gives_a_bye(
    client: TestClient, session: Session
) -> None:
    """沒有候補時照 4.5 輪空：沒有接手的隊伍。"""
    w = _world(client, session, waitlist=False)

    result = service.retire_team(
        session, team_id=w.leaving, account_id=w.leaving_captain.id
    )

    assert result.replacement_team_id is None
    assert _status(session, w.leaving) == R.RETIRED
