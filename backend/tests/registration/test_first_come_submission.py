"""Story 3.5：先搶期送出時當下分配（I/O 矩陣，併發兩列在 test_first_come_concurrency.py）。

前置狀態（優先期學校、正取、候補、殘留的 `pending`）一律直接寫入報名列，只有被測的
那一筆經 API 送出。分配規則本身在 test_allocation.py；這裡確認送出、結算、
`_first_come_locked`、操作紀錄與事件接得起來。

`frozen_clock` 固定在 2026-10-18 11:00 UTC（下稱 T）；賽事報名從 T−1 小時開始、優先期
1 小時，所以優先期在 T 結束。送出前以 `frozen_clock.advance` 推進到先搶期，
前置報名的送出時間依序排在 T 之前或之後，讓送出順序固定。
"""

import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import audit
from app.core.audit import AuditLogRead
from app.core.events import OutboxEvent
from app.modules.identity.models import Account, School
from app.modules.registration import repository
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
)
from app.modules.tournaments.models import Tournament, TournamentMode, TournamentRead
from tests.conftest import FrozenClock
from tests.helpers import make_tournament
from tests.registration.test_submit_registration import (
    _detail,
    _fill,
    _registration,
    _school,
    _set_school,
    _submit,
)
from tests.registration.test_teams import _create_ok, _error_code, _make_account

# 送出時間：先搶期內、T 之後 10 分鐘（前置的先搶期報名排在這之前）
SUBMIT_AFTER = timedelta(minutes=10)


# ---------------------------------------------------------------- 測試資料


def _tournament(
    session: Session, frozen_clock: FrozenClock, **overrides: Any
) -> TournamentRead:
    """優先期在 T 結束的校園賽；每隊 1 人就能送出。"""
    overrides.setdefault(
        "registration_start", (frozen_clock.now() - timedelta(hours=1)).isoformat()
    )
    overrides.setdefault("priority_hours", 1)
    overrides.setdefault("starters", 1)
    overrides.setdefault("substitutes", 0)
    tournament = make_tournament(session, **overrides)
    assert tournament.priority_end == frozen_clock.now()
    return tournament


def _api_team(
    client: TestClient, session: Session, tournament: TournamentRead, school: School
) -> tuple[dict[str, Any], Account]:
    """經 API 建立、填完資料、尚未送出的隊伍（隊長一人）。"""
    captain = _make_account(session, display_name=f"隊長{uuid.uuid4().hex[:4]}")
    team = _create_ok(client, captain, tournament.id, name=f"隊-{uuid.uuid4().hex[:8]}")
    _set_school(session, captain, school)
    _fill(session, team["id"], captain)
    return team, captain


def _preset(
    session: Session,
    tournament: TournamentRead,
    school: School,
    status: RegistrationStatus,
    *,
    submitted_at: datetime,
    team_id: Any = None,
    score: str = "30",
) -> Registration:
    """直接寫入一筆已送出的報名；`team_id` 給定時改寫該隊的報名。"""
    if team_id is None:
        team = Team(
            tournament_id=tournament.id,
            name=f"隊伍-{uuid.uuid4().hex[:8]}",
            invite_token=secrets.token_urlsafe(24),
        )
        session.add(team)
        session.flush()
        registration = Registration(
            team_id=team.id, tournament_id=tournament.id, status=status
        )
    else:
        found = repository.get_registration_by_team(session, uuid.UUID(str(team_id)))
        assert found is not None
        registration = found
    registration.status = status
    registration.school_id = school.id
    registration.avg_rank_score = Decimal(score)
    registration.submitted_at = submitted_at
    session.add(registration)
    session.flush()
    return registration


def _settled(
    session: Session, tournament: TournamentRead, schools: list[School]
) -> None:
    """直接寫入結算紀錄（優先期有報名的學校）。"""
    repository.add_settlement(
        session,
        PriorityWindowSettlement(
            tournament_id=tournament.id,
            settled_at=tournament.priority_end,
            priority_school_ids=sorted(s.id for s in schools),
        ),
    )


def _in_window(tournament: TournamentRead, minutes: int) -> datetime:
    return tournament.registration_start + timedelta(minutes=minutes)


def _first_come(tournament: TournamentRead, minutes: int) -> datetime:
    """先搶期內、早於被測送出的時間。"""
    return tournament.priority_end + timedelta(minutes=minutes)


def _submit_ok(
    client: TestClient, captain: Account, team: dict[str, Any]
) -> dict[str, Any]:
    response = _submit(client, captain, team["id"])
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _events(session: Session, tournament: TournamentRead) -> list[dict[str, Any]]:
    rows = session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.type == "RegistrationAllocated")
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
    )
    return [
        row.payload
        for row in rows
        if row.payload["tournament_id"] == str(tournament.id)
    ]


def _allocated(
    session: Session, tournament: TournamentRead, *ordered: tuple[uuid.UUID, str]
) -> None:
    """系統分配的順序（操作紀錄依寫入順序）與事件（凍結時鐘下沒有先後，只比集合）。"""
    system_changes = [
        (log.entity_id, log.after["status"])
        for log in _logs(session, tournament, "registration.status_changed")
        if log.actor_id is None and log.after is not None
    ]
    assert system_changes == list(ordered)
    assert sorted(
        (e["registration_id"], e["status"]) for e in _events(session, tournament)
    ) == sorted((str(i), s) for i, s in ordered)


def _logs(
    session: Session, tournament: TournamentRead, action: str
) -> list[AuditLogRead]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == action
    ]


def _changes(
    session: Session, tournament: TournamentRead, registration_id: uuid.UUID
) -> list[tuple[str, uuid.UUID | None]]:
    """某筆報名的狀態變更（新狀態, 操作者），依寫入順序。"""
    return [
        (log.after["status"], log.actor_id)
        for log in _logs(session, tournament, "registration.status_changed")
        if log.entity_id == registration_id and log.after is not None
    ]


def _statuses(session: Session, tournament: TournamentRead) -> list[str]:
    session.expire_all()
    return [r.status for r in repository.list_registrations(session, tournament.id)]


# ---------------------------------------------------------------- I/O 矩陣


def test_new_school_with_capacity_is_accepted(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _settled(session, tournament, [])
    team, captain = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "accepted"
    assert body["waitlist_position"] is None
    assert body["waitlist_reason"] is None
    assert body["waitlist_phase"] is None
    registration = _registration(session, team["id"])
    assert registration.status == RegistrationStatus.ACCEPTED
    assert registration.submitted_at == frozen_clock.now()
    assert _changes(session, tournament, registration.id) == [
        ("pending", captain.id),
        ("accepted", None),
    ]
    assert _events(session, tournament) == [
        {
            "registration_id": str(registration.id),
            "team_id": team["id"],
            "tournament_id": str(tournament.id),
            "status": "accepted",
        }
    ]
    # 已結算：不再寫結算摘要
    assert _logs(session, tournament, "registration.priority_window_settled") == []


def test_priority_school_is_waitlisted_without_position(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    school_a = _school(session)
    _settled(session, tournament, [school_a])
    team, captain = _api_team(client, session, tournament, school_a)
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "waitlisted"
    assert body["waitlist_position"] is None
    assert body["waitlist_reason"] == "SCHOOL_NOT_ELIGIBLE"
    assert body["waitlist_phase"] == "first_come"
    registration = _registration(session, team["id"])
    assert _changes(session, tournament, registration.id) == [
        ("pending", captain.id),
        ("waitlisted", None),
    ]
    assert [e["status"] for e in _events(session, tournament)] == ["waitlisted"]


def test_second_team_of_school_with_first_come_acceptance_is_waitlisted(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    school_x = _school(session)
    _settled(session, tournament, [])
    _preset(
        session,
        tournament,
        school_x,
        RegistrationStatus.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    team, captain = _api_team(client, session, tournament, school_x)
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "waitlisted"
    assert body["waitlist_position"] is None
    assert body["waitlist_reason"] == "SCHOOL_NOT_ELIGIBLE"
    assert body["representative_backfill"] is False
    assert body["waitlist_phase"] == "first_come"
    assert len(_events(session, tournament)) == 1


def test_full_capacity_waitlist_positions_follow_epics_example(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """epics 3.5 範例：候補已有 A（優先期學校）、B（X 校）；C（X 校）、D（Y 校）依序送出。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_x, school_y = (_school(session) for _ in range(4))
    _settled(session, tournament, [school_p])
    _preset(
        session,
        tournament,
        school_p,
        RegistrationStatus.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
    )
    _preset(
        session,
        tournament,
        school_p,
        RegistrationStatus.WAITLISTED,
        submitted_at=_in_window(tournament, 20),
    )
    _preset(
        session,
        tournament,
        school_q,
        RegistrationStatus.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    team_b, captain_b = _api_team(client, session, tournament, school_x)
    _preset(
        session,
        tournament,
        school_x,
        RegistrationStatus.WAITLISTED,
        submitted_at=_first_come(tournament, 2),
        team_id=team_b["id"],
    )
    team_c, captain_c = _api_team(client, session, tournament, school_x)
    team_d, captain_d = _api_team(client, session, tournament, school_y)

    frozen_clock.advance(SUBMIT_AFTER)
    body_c = _submit_ok(client, captain_c, team_c)
    frozen_clock.advance(timedelta(minutes=1))
    body_d = _submit_ok(client, captain_d, team_d)

    assert (body_c["registration_status"], body_c["waitlist_position"]) == (
        "waitlisted",
        None,
    )
    assert body_c["waitlist_reason"] == "LATER_THAN_SCHOOLMATE"
    assert (body_d["registration_status"], body_d["waitlist_position"]) == (
        "waitlisted",
        2,
    )
    detail_b = _detail(client, captain_b, team_b["id"])
    assert (detail_b["registration_status"], detail_b["waitlist_position"]) == (
        "waitlisted",
        1,
    )
    assert [e["status"] for e in _events(session, tournament)] == [
        "waitlisted",
        "waitlisted",
    ]


def test_vacancy_is_backfilled_before_judging_the_submission(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_x, school_y, school_w = (_school(session) for _ in range(3))
    _settled(session, tournament, [])
    _preset(
        session,
        tournament,
        school_x,
        RegistrationStatus.DISQUALIFIED,
        submitted_at=_first_come(tournament, 1),
    )
    _preset(
        session,
        tournament,
        school_y,
        RegistrationStatus.ACCEPTED,
        submitted_at=_first_come(tournament, 2),
    )
    waiting_b = _preset(
        session,
        tournament,
        school_w,
        RegistrationStatus.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    team, captain = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "waitlisted"
    assert body["waitlist_position"] == 1
    assert body["waitlist_phase"] == "first_come"
    registration = _registration(session, team["id"])
    _allocated(
        session,
        tournament,
        (waiting_b.id, "accepted"),
        (registration.id, "waitlisted"),
    )


def test_unsettled_priority_window_is_settled_first(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    school_p = _school(session)
    in_window = _preset(
        session,
        tournament,
        school_p,
        RegistrationStatus.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    team, captain = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "accepted"
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == [school_p.id]
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.actor_id is None
    assert summary.after is not None
    assert summary.after["accepted"] == [str(in_window.id)]
    registration = _registration(session, team["id"])
    _allocated(
        session,
        tournament,
        (in_window.id, "accepted"),
        (registration.id, "accepted"),
    )
    # 結算摘要寫在本筆判定之前
    actions = [
        log.action
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action != "registration.submitted"
    ]
    assert actions[-2:] == [
        "registration.priority_window_settled",
        "registration.status_changed",
    ]


def test_first_submission_without_any_priority_registration(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    team, captain = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "accepted"
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == []
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.actor_id is None
    assert summary.after == {
        "capacity": tournament.capacity,
        "accepted": [],
        "waitlisted": [],
        "priority_school_ids": [],
    }
    assert len(_events(session, tournament)) == 1


def test_leftover_first_come_pending_is_judged_first(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """3.5 上線前送出、仍為 `pending` 的 P1 依送出順序先判定，同校的 P2 才候補。"""
    tournament = _tournament(session, frozen_clock)
    school_x = _school(session)
    _settled(session, tournament, [])
    leftover = _preset(
        session,
        tournament,
        school_x,
        RegistrationStatus.PENDING,
        submitted_at=_first_come(tournament, 1),
    )
    team, captain = _api_team(client, session, tournament, school_x)
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "waitlisted"
    assert body["waitlist_reason"] == "SCHOOL_NOT_ELIGIBLE"
    registration = _registration(session, team["id"])
    _allocated(
        session,
        tournament,
        (leftover.id, "accepted"),
        (registration.id, "waitlisted"),
    )
    assert "pending" not in _statuses(session, tournament)


def test_submission_at_priority_end_stays_pending(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """`now == priority_end` 屬優先期（與結算的 `submitted_at <= priority_end` 一致）。"""
    tournament = _tournament(session, frozen_clock)
    team, captain = _api_team(client, session, tournament, _school(session))

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "pending"
    assert _events(session, tournament) == []
    assert repository.get_settlement(session, tournament.id) is None


def test_custom_mode_submission_stays_pending(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    # 建立賽事一律是校園賽（期中），所以直接改賽事列的模式
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.mode = TournamentMode.CUSTOM
    session.add(row)
    session.flush()
    team, captain = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "pending"
    assert _events(session, tournament) == []
    assert repository.get_settlement(session, tournament.id) is None


def test_rejected_submission_does_not_settle_or_allocate(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _preset(
        session,
        tournament,
        _school(session),
        RegistrationStatus.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    team, captain = _api_team(client, session, tournament, _school(session))
    member = repository.get_team_member(session, uuid.UUID(team["id"]), captain.id)
    assert member is not None
    member.rank_score = None
    member.rank_tier = None
    session.add(member)
    session.flush()
    frozen_clock.advance(SUBMIT_AFTER)

    unmet = _submit(client, captain, team["id"])
    frozen_clock.set(tournament.registration_end)
    closed = _submit(client, captain, team["id"])

    assert unmet.status_code == 409
    assert _error_code(unmet) == "REGISTRATION_REQUIREMENTS_UNMET"
    assert closed.status_code == 409
    assert _error_code(closed) == "REGISTRATION_CLOSED"
    assert repository.get_settlement(session, tournament.id) is None
    assert _events(session, tournament) == []
    assert sorted(_statuses(session, tournament)) == ["forming", "pending"]
