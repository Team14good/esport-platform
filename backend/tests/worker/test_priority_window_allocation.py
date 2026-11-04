"""Story 3.4（第二階段）：worker 在優先期結束時結算校園賽的正取與候補。

分配規則本身在 tests/registration/test_allocation.py；這裡確認 worker、鎖、`mark_status`、
結算紀錄、操作紀錄與事件接得起來，以及 I/O 矩陣每一列。報名直接寫成「已送出・待分配」
並帶送出時的快照（送出流程由 test_submit_registration.py 測試）。

`frozen_clock` 固定在 2026-10-18 11:00 UTC；賽事報名從 1 小時前開始、優先期 2 小時，
所以優先期在 1 小時後結束。
"""

import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import audit
from app.core.events import OutboxEvent
from app.modules.identity.models import School
from app.modules.registration import allocation, repository, service
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
    WaitlistPhase,
    WaitlistReasonCode,
)
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from app.worker import run_once
from app.worker.jobs import JOBS, allocate_priority_windows, dispatch_outbox
from tests.conftest import FrozenClock
from tests.helpers import make_tournament
from tests.registration.test_teams import (
    API,
    _auth,
    _create_ok,
    _make_account,
    _set_status,
)

PRIORITY_HOURS = 2


# ---------------------------------------------------------------- 測試資料


def _tournament(
    session: Session, frozen_clock: FrozenClock, **overrides: Any
) -> TournamentRead:
    overrides.setdefault(
        "registration_start", (frozen_clock.now() - timedelta(hours=1)).isoformat()
    )
    overrides.setdefault("priority_hours", PRIORITY_HOURS)
    return make_tournament(session, **overrides)


def _school(session: Session) -> School:
    school = School(name=f"測試大學-{uuid.uuid4().hex[:8]}")
    session.add(school)
    session.flush()
    return school


def _submitted(
    session: Session,
    tournament: TournamentRead,
    school: School,
    *,
    score: str = "20",
    submitted_at: datetime,
    registration: Registration | None = None,
) -> Registration:
    """一筆已送出的報名（待分配，帶三個快照）；`registration` 給定時改寫那一筆。"""
    if registration is None:
        team = Team(
            tournament_id=tournament.id,
            name=f"隊伍-{uuid.uuid4().hex[:8]}",
            invite_token=secrets.token_urlsafe(24),
        )
        session.add(team)
        session.flush()
        registration = Registration(
            team_id=team.id,
            tournament_id=tournament.id,
            status=RegistrationStatus.PENDING,
        )
    registration.status = RegistrationStatus.PENDING
    registration.school_id = school.id
    registration.avg_rank_score = Decimal(score)
    registration.submitted_at = submitted_at
    session.add(registration)
    session.flush()
    return registration


def _in_window(tournament: TournamentRead, minutes: int = 30) -> datetime:
    """優先期內的送出時間（報名開始後若干分鐘）。"""
    return tournament.registration_start + timedelta(minutes=minutes)


def _statuses(session: Session, tournament: TournamentRead) -> dict[uuid.UUID, str]:
    session.expire_all()
    return {
        r.id: r.status for r in repository.list_registrations(session, tournament.id)
    }


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


def _actions(session: Session, tournament: TournamentRead) -> list[str]:
    return [log.action for log in audit.list_for_tournament(session, tournament.id)]


def _run(session_factory: Callable[[], Session]) -> None:
    run_once([allocate_priority_windows], session_factory=session_factory)


def _end_priority(frozen_clock: FrozenClock, tournament: TournamentRead) -> None:
    frozen_clock.set(tournament.priority_end)


# ---------------------------------------------------------------- 註冊與時機


def test_job_is_registered_before_outbox_dispatch() -> None:
    assert allocate_priority_windows in JOBS
    assert JOBS.index(allocate_priority_windows) < JOBS.index(dispatch_outbox)


def test_job_returns_false_when_nothing_is_due(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )

    assert allocate_priority_windows(session) is False


def test_priority_window_not_over_is_left_unchanged(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    session.commit()

    frozen_clock.set(tournament.priority_end - timedelta(seconds=1))
    _run(session_factory)

    assert _statuses(session, tournament) == {registration.id: "pending"}
    assert repository.get_settlement(session, tournament.id) is None
    assert _events(session, tournament) == []


# ---------------------------------------------------------------- I/O 矩陣


def test_forty_schools_for_thirty_two_places_and_rerun_changes_nothing(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=32)
    schools = [_school(session) for _ in range(40)]
    # 積分 40、39、…、1：前 32 校正取
    registrations = [
        _submitted(
            session,
            tournament,
            school,
            score=str(40 - i),
            submitted_at=_in_window(tournament, minutes=i + 1),
        )
        for i, school in enumerate(schools)
    ]
    expected = allocation.allocate_priority_window(
        [service._candidate(r) for r in registrations], capacity=32
    )
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    statuses = _statuses(session, tournament)
    accepted = [i for i, s in statuses.items() if s == "accepted"]
    waitlisted = [i for i, s in statuses.items() if s == "waitlisted"]
    assert sorted(accepted) == sorted(expected.accepted)
    assert sorted(waitlisted) == sorted(expected.waitlisted)
    assert sorted(accepted) == sorted(r.id for r in registrations[:32])
    assert len(waitlisted) == 8

    # 結算紀錄：優先期有報名的學校＝40 校
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.settled_at == tournament.priority_end
    assert sorted(settlement.priority_school_ids) == sorted(s.id for s in schools)

    # 每筆一則事件、一筆 mark_status 紀錄（系統），外加一筆結算摘要
    events = _events(session, tournament)
    assert len(events) == 40
    assert {(e["registration_id"], e["status"]) for e in events} == {
        (str(i), s) for i, s in statuses.items()
    }
    logs = audit.list_for_tournament(session, tournament.id)
    changed = [log for log in logs if log.action == "registration.status_changed"]
    assert len(changed) == 40
    assert all(log.actor_id is None for log in changed)
    summary = [
        log for log in logs if log.action == "registration.priority_window_settled"
    ]
    assert len(summary) == 1
    assert summary[0].actor_id is None
    assert summary[0].entity_id == tournament.id
    assert summary[0].after == {
        "capacity": 32,
        "accepted": [str(i) for i in expected.accepted],
        "waitlisted": [str(i) for i in expected.waitlisted],
        "priority_school_ids": [str(i) for i in settlement.priority_school_ids],
    }

    # 8 隊候補沒有順位，原因 SCHOOL_NOT_ELIGIBLE（先搶期，優先期有報名的學校）
    for registration_id in waitlisted:
        registration = session.get(Registration, registration_id)
        assert registration is not None
        fields = service._waitlist_fields(session, registration, tournament)
        assert fields.waitlist_position is None
        assert fields.waitlist_reason == "SCHOOL_NOT_ELIGIBLE"
        assert fields.representative_backfill is False
        assert fields.waitlist_phase == "first_come"

    # 再跑一次（時間也往後推）：狀態、操作紀錄、事件都不變
    log_count = len(logs)
    frozen_clock.advance(timedelta(minutes=5))
    _run(session_factory)
    assert _statuses(session, tournament) == statuses
    assert len(audit.list_for_tournament(session, tournament.id)) == log_count
    assert len(_events(session, tournament)) == 40


def test_three_teams_of_one_school_get_one_place(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=16)
    school = _school(session)
    best, second, third = (
        _submitted(
            session,
            tournament,
            school,
            score=score,
            submitted_at=_in_window(tournament, minutes=minute),
        )
        for score, minute in (("30", 20), ("25", 10), ("25", 15))
    )
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    assert _statuses(session, tournament) == {
        best.id: "accepted",
        second.id: "waitlisted",
        third.id: "waitlisted",
    }
    for registration in (second, third):
        fields = service._waitlist_fields(session, registration, tournament)
        assert fields.waitlist_position is None
        assert fields.waitlist_reason == "SCHOOL_NOT_ELIGIBLE"
        assert fields.representative_backfill is True


def test_pending_submitted_after_priority_window_is_not_settled(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 優先期內只有 A 校；B 校在優先期後送出（3.5 尚未接上），維持 pending
    tournament = _tournament(session, frozen_clock)
    school_a, school_b = _school(session), _school(session)
    early = _submitted(
        session, tournament, school_a, submitted_at=_in_window(tournament)
    )
    on_the_edge = _submitted(
        session, tournament, school_a, score="10", submitted_at=tournament.priority_end
    )
    late = _submitted(
        session,
        tournament,
        school_b,
        score="99",
        submitted_at=tournament.priority_end + timedelta(seconds=1),
    )
    session.commit()

    frozen_clock.set(tournament.priority_end + timedelta(minutes=1))
    _run(session_factory)

    assert _statuses(session, tournament) == {
        early.id: "accepted",
        on_the_edge.id: "waitlisted",
        late.id: "pending",
    }
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == [school_a.id]
    assert {e["registration_id"] for e in _events(session, tournament)} == {
        str(early.id),
        str(on_the_edge.id),
    }


def test_only_late_submissions_write_an_empty_settlement(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 優先期內沒有任何報名：寫空的結算紀錄、不發事件，之後 worker 不再處理這場
    tournament = _tournament(session, frozen_clock)
    late = _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=tournament.priority_end + timedelta(minutes=1),
    )
    session.commit()

    frozen_clock.set(tournament.priority_end + timedelta(minutes=2))
    _run(session_factory)

    assert _statuses(session, tournament) == {late.id: "pending"}
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == []
    assert _events(session, tournament) == []
    assert (
        _actions(session, tournament).count("registration.priority_window_settled") == 1
    )
    assert allocate_priority_windows(session) is False


def test_worker_skips_tournament_without_any_submission(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 完全沒有送出報名：worker 不處理、不寫結算紀錄（Decisions：選 (甲)）
    tournament = _tournament(session, frozen_clock)
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    assert repository.get_settlement(session, tournament.id) is None
    assert "registration.priority_window_settled" not in _actions(session, tournament)
    assert allocate_priority_windows(session) is False


def test_settle_tournament_without_registrations_writes_empty_settlement(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _end_priority(frozen_clock, tournament)

    assert service.settle_priority_window(session, tournament_id=tournament.id) is True
    # 已結算：再呼叫不做任何事
    assert service.settle_priority_window(session, tournament_id=tournament.id) is False

    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == []
    assert (
        _actions(session, tournament).count("registration.priority_window_settled") == 1
    )
    assert _events(session, tournament) == []


@pytest.mark.parametrize(
    "status", [s for s in TournamentStatus if s != TournamentStatus.OPEN]
)
def test_tournament_not_open_is_left_unchanged(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
    status: TournamentStatus,
) -> None:
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set_status(session, tournament.id, status)
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    assert _statuses(session, tournament) == {registration.id: "pending"}
    assert repository.get_settlement(session, tournament.id) is None


def test_settle_rechecks_inside_the_lock(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 優先期未到時直接呼叫：鎖內重新檢查，不結算
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )

    assert service.settle_priority_window(session, tournament_id=tournament.id) is False
    assert registration.status == RegistrationStatus.PENDING
    assert session.get(PriorityWindowSettlement, tournament.id) is None


def test_worker_settles_every_due_tournament_in_one_round(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 候選依賽事 id 排列：讓 id 最小的那場優先期還沒結束，確認 worker 不會在第一個
    # 未到期的候選停下
    tournaments = sorted(
        (_tournament(session, frozen_clock) for _ in range(3)), key=lambda t: t.id
    )
    not_due, due = tournaments[0], tournaments[1:]
    row = session.get(Tournament, not_due.id)
    assert row is not None
    row.priority_end = not_due.priority_end + timedelta(hours=5)
    session.add(row)
    session.flush()
    for tournament in tournaments:
        _submitted(
            session, tournament, _school(session), submitted_at=_in_window(tournament)
        )
    session.commit()

    _end_priority(frozen_clock, due[0])
    _run(session_factory)

    for tournament in due:
        assert list(_statuses(session, tournament).values()) == ["accepted"]
    assert list(_statuses(session, not_due).values()) == ["pending"]
    assert repository.get_settlement(session, not_due.id) is None


def test_custom_mode_tournament_is_left_unchanged(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 建立賽事一律是校園賽（期中），所以直接改賽事列的模式
    tournament = _tournament(session, frozen_clock)
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.mode = TournamentMode.CUSTOM
    session.add(row)
    session.flush()
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    assert _statuses(session, tournament) == {registration.id: "pending"}
    assert repository.get_settlement(session, tournament.id) is None


# ---------------------------------------------------------------- S17、S12


def _team_page(client: TestClient, account: Any, team_id: Any) -> dict[str, Any]:
    response = client.get(f"{API}/teams/{team_id}", headers=_auth(account))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _my_card(client: TestClient, account: Any, team_id: Any) -> dict[str, Any]:
    response = client.get(f"{API}/accounts/me/teams", headers=_auth(account))
    assert response.status_code == 200, response.text
    cards = [c for c in response.json() if c["team_id"] == str(team_id)]
    assert len(cards) == 1
    card: dict[str, Any] = cards[0]
    return card


WAITLIST_KEYS = (
    "waitlist_position",
    "waitlist_reason",
    "representative_backfill",
    "waitlist_phase",
)


def _waitlist(body: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(body[key] for key in WAITLIST_KEYS)


def _own_team(
    client: TestClient, session: Session, tournament: TournamentRead
) -> tuple[Any, Registration]:
    """經 API 建一支隊伍（只有隊長），回傳隊長帳號與其報名。"""
    captain = _make_account(session)
    team = _create_ok(
        client, captain, tournament.id, name=f"夜貓-{uuid.uuid4().hex[:6]}"
    )
    registration = repository.get_registration_by_team(session, uuid.UUID(team["id"]))
    assert registration is not None
    return captain, registration


def test_team_page_and_my_teams_show_representative_school_waitlist(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock)
    school = _school(session)
    captain, own = _own_team(client, session, tournament)
    _submitted(
        session,
        tournament,
        school,
        score="10",
        submitted_at=_in_window(tournament),
        registration=own,
    )
    _submitted(
        session, tournament, school, score="30", submitted_at=_in_window(tournament)
    )
    session.commit()

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    expected = (None, "SCHOOL_NOT_ELIGIBLE", True, "first_come")
    page = _team_page(client, captain, own.team_id)
    assert page["registration_status"] == "waitlisted"
    assert _waitlist(page) == expected
    card = _my_card(client, captain, own.team_id)
    assert card["registration_status"] == "waitlisted"
    assert _waitlist(card) == expected

    # 報名截止後改用截止後的規則：本校只有 1 隊正取，排第 1 位
    frozen_clock.set(tournament.registration_end)
    assert _waitlist(_team_page(client, captain, own.team_id)) == (
        1,
        None,
        False,
        "after_deadline",
    )
    assert _waitlist(_my_card(client, captain, own.team_id)) == (
        1,
        None,
        False,
        "after_deadline",
    )


def test_team_page_shows_waitlist_position_in_first_come_phase(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 優先期沒有報名的學校（直接寫成候補，模擬 3.5 的先搶期送出）有順位
    tournament = _tournament(session, frozen_clock, capacity=2)
    _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    session.commit()
    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    captain, own = _own_team(client, session, tournament)
    _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=tournament.priority_end + timedelta(minutes=1),
        registration=own,
    )
    service.mark_status(
        session, registration=own, to=RegistrationStatus.WAITLISTED, actor_id=None
    )
    session.commit()

    assert _waitlist(_team_page(client, captain, own.team_id)) == (
        1,
        None,
        False,
        "first_come",
    )


def test_accepted_and_pending_have_no_waitlist_fields(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock)
    captain, own = _own_team(client, session, tournament)
    _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=_in_window(tournament),
        registration=own,
    )
    session.commit()

    empty = (None, None, None, None)
    assert _waitlist(_team_page(client, captain, own.team_id)) == empty

    _end_priority(frozen_clock, tournament)
    _run(session_factory)

    page = _team_page(client, captain, own.team_id)
    assert page["registration_status"] == "accepted"
    assert _waitlist(page) == empty
    assert _waitlist(_my_card(client, captain, own.team_id)) == empty


# ---------------------------------------------------------------- 型別對應


def test_literal_types_match_allocation_enums() -> None:
    assert set(get_args(WaitlistReasonCode)) == {
        r.value for r in allocation.WaitlistReason
    }
    assert set(get_args(WaitlistPhase)) == {p.value for p in allocation.AllocationPhase}
