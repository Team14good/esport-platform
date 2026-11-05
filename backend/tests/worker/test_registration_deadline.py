"""Story 3.6：報名截止 worker 工作（`close_registrations`）與截止補位。

分配規則本身在 tests/registration/test_allocation.py；這裡確認找候選、鎖、鎖內的結算
→ 補做先搶期 → 截止補位 → 轉「報名截止」接得起來，以及 I/O 矩陣每一列。報名直接寫成
已送出並帶快照（沿用優先期 worker 測試的 helper）。

`frozen_clock` 固定在 2026-10-18 11:00 UTC；賽事報名從 1 小時前開始、優先期 2 小時
（12:00 結束）、報名截止在 13:00。測試資料庫裡有併發測試真正提交、仍為開放報名的
賽事（tests/registration/test_settlement_concurrency.py，報名截止 2026-10-25 11:00）；
呼叫 `close_due_registration`／`run_once` 會從全部賽事找候選，所以報名截止時間與時鐘
都要早於它，不能用 `make_tournament` 預設的 7 天後截止。
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.modules.competition import service as competition_service
from app.modules.registration import repository, service
from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from app.worker import run_once
from app.worker.jobs import (
    JOBS,
    allocate_priority_windows,
    close_registrations,
    dispatch_outbox,
    open_registrations,
    start_due_tournaments,
)
from tests.conftest import FrozenClock
from tests.registration.test_teams import (
    API,
    _auth,
    _create,
    _create_ok,
    _error_code,
    _join,
    _make_account,
    _set_status,
)
from tests.worker.test_priority_window_allocation import (
    _events,
    _in_window,
    _my_card,
    _own_team,
    _school,
    _statuses,
    _submitted,
    _team_page,
    _tournament,
    _waitlist,
)

A = RegistrationStatus.ACCEPTED
W = RegistrationStatus.WAITLISTED
P = RegistrationStatus.PENDING
D = RegistrationStatus.DRAWN
F = RegistrationStatus.FORMING

DEADLINE_MESSAGE = "這場賽事的報名已截止。"


# ---------------------------------------------------------------- 共用


def _due_tournament(
    session: Session,
    frozen_clock: FrozenClock,
    *,
    end_hours: float = 2,
    **overrides: Any,
) -> TournamentRead:
    """報名 1 小時前開始、優先期 2 小時、`end_hours` 小時後截止（早於殘留賽事）。"""
    overrides.setdefault(
        "registration_end",
        (frozen_clock.now() + timedelta(hours=end_hours)).isoformat(),
    )
    return _tournament(session, frozen_clock, **overrides)


def _close(session: Session, tournament: TournamentRead) -> bool:
    return service.close_registration(session, tournament_id=tournament.id)


def _status(session: Session, tournament: TournamentRead) -> TournamentStatus:
    session.expire_all()
    return tournaments_service.get_tournament(
        session, tournament_id=tournament.id
    ).status


def _logs(session: Session, tournament: TournamentRead, action: str) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == action
    ]


def _snapshot(session: Session, tournament: TournamentRead) -> tuple[Any, ...]:
    return (
        _status(session, tournament),
        _statuses(session, tournament),
        len(audit.list_for_tournament(session, tournament.id)),
        len(_events(session, tournament)),
        repository.get_settlement(session, tournament.id) is not None,
    )


def _set(
    session: Session, registration: Registration, status: RegistrationStatus
) -> None:
    """直接改報名狀態（測試用：做出正常流程做不出的狀態）。"""
    registration.status = status
    session.add(registration)
    session.flush()


def _settled(session: Session, tournament: TournamentRead, *schools: Any) -> None:
    """寫一筆結算紀錄（「已結算」必須有紀錄，否則鎖內會再結算一次）。"""
    repository.add_settlement(
        session,
        PriorityWindowSettlement(
            tournament_id=tournament.id,
            settled_at=tournament.priority_end,
            priority_school_ids=sorted(s.id for s in schools),
        ),
    )


def _forming(session: Session, tournament: TournamentRead) -> Registration:
    team = Team(
        tournament_id=tournament.id,
        name=f"組隊中-{uuid.uuid4().hex[:8]}",
        invite_token=uuid.uuid4().hex,
    )
    session.add(team)
    session.flush()
    registration = Registration(team_id=team.id, tournament_id=tournament.id, status=F)
    session.add(registration)
    session.flush()
    return registration


def _round(session_factory: Callable[[], Session]) -> None:
    run_once(
        [open_registrations, allocate_priority_windows, close_registrations],
        session_factory=session_factory,
    )


# ---------------------------------------------------------------- 註冊與時機


def test_job_is_registered_after_priority_window_and_before_start_and_outbox() -> None:
    position = JOBS.index(close_registrations)
    assert JOBS.index(allocate_priority_windows) < position
    assert position < JOBS.index(start_due_tournaments)
    assert position < JOBS.index(dispatch_outbox)


def test_not_due_is_not_a_candidate_and_changes_nothing(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _due_tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    frozen_clock.set(tournament.registration_end - timedelta(microseconds=1))
    before = _snapshot(session, tournament)

    assert service.close_due_registration(session) is False
    assert close_registrations(session) is False
    assert _close(session, tournament) is False

    assert _snapshot(session, tournament) == before
    assert _statuses(session, tournament) == {registration.id: P}
    assert _status(session, tournament) == TournamentStatus.OPEN


@pytest.mark.parametrize(
    "status", [s for s in TournamentStatus if s != TournamentStatus.OPEN]
)
def test_tournament_not_open_is_not_a_candidate_and_changes_nothing(
    session: Session, frozen_clock: FrozenClock, status: TournamentStatus
) -> None:
    # 提前抽籤後為 published、或已取消等：不是候選，直接呼叫也不做任何事
    tournament = _due_tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set_status(session, tournament.id, status)
    frozen_clock.set(tournament.registration_end)
    before = _snapshot(session, tournament)

    assert service.close_due_registration(session) is False
    assert _close(session, tournament) is False

    assert _snapshot(session, tournament) == before
    assert _statuses(session, tournament) == {registration.id: P}
    assert _status(session, tournament) == status


# ---------------------------------------------------------------- I/O 矩陣：截止補位


def test_epics_example_fills_skipping_schools_at_limit_in_one_worker_round(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    # 名額 5、已結算；Z 校 2 隊、W 校 1 隊正取；候補依積分 E（Z）、F（W）、G（W）、
    # H（V，優先期超過名額的代表隊）。補 2 位：E 會使 Z 校超過 2 隊、G 會使 W 校超過
    # 2 隊而略過，補 F、H
    tournament = _due_tournament(session, frozen_clock, capacity=5)
    z, w, v = _school(session), _school(session), _school(session)
    t = _in_window(tournament)
    accepted = [
        _submitted(session, tournament, z, score="90", submitted_at=t),
        _submitted(session, tournament, z, score="85", submitted_at=t),
        _submitted(session, tournament, w, score="80", submitted_at=t),
    ]
    e = _submitted(session, tournament, z, score="70", submitted_at=t)
    f = _submitted(session, tournament, w, score="60", submitted_at=t)
    g = _submitted(session, tournament, w, score="50", submitted_at=t)
    h = _submitted(session, tournament, v, score="40", submitted_at=t)
    for registration in accepted:
        _set(session, registration, A)
    for registration in (e, f, g, h):
        _set(session, registration, W)
    _settled(session, tournament, z, w, v)
    session.commit()
    logs_before = len(audit.list_for_tournament(session, tournament.id))

    frozen_clock.set(tournament.registration_end)
    _round(session_factory)

    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _statuses(session, tournament) == {
        **{r.id: A for r in accepted},
        e.id: W,
        f.id: A,
        g.id: W,
        h.id: A,
    }
    # 補上的 F、H 各 1 則事件（凍結時鐘下建立時間相同，不比順序）
    events = _events(session, tournament)
    assert sorted((ev["registration_id"], ev["status"]) for ev in events) == sorted(
        [(str(f.id), "accepted"), (str(h.id), "accepted")]
    )
    # 操作紀錄：F、H 的狀態變更，最後才轉報名截止；操作者皆為系統
    new_logs = audit.list_for_tournament(session, tournament.id)[logs_before:]
    assert [(log.action, log.entity_id) for log in new_logs] == [
        ("registration.status_changed", f.id),
        ("registration.status_changed", h.id),
        ("tournament.status_changed", tournament.id),
    ]
    assert {log.actor_id for log in new_logs} == {None}
    assert (new_logs[-1].before, new_logs[-1].after) == (
        {"status": "open"},
        {"status": "closed"},
    )
    # E、G 仍候補，原因為學校已達上限
    tournament_now = tournaments_service.get_tournament(
        session, tournament_id=tournament.id
    )
    for registration in (e, g):
        fields = service._waitlist_fields(session, registration, tournament_now)
        assert fields.waitlist_position is None
        assert fields.waitlist_reason == "SCHOOL_LIMIT_REACHED"
        assert fields.waitlist_phase == "after_deadline"


def test_vacancies_remain_when_no_waitlist(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=4)
    x, y = _school(session), _school(session)
    rx = _submitted(session, tournament, x, submitted_at=_in_window(tournament))
    ry = _submitted(session, tournament, y, submitted_at=_in_window(tournament))
    _set(session, rx, A)
    _set(session, ry, A)
    _settled(session, tournament, x, y)
    frozen_clock.set(tournament.registration_end)

    assert _close(session, tournament) is True

    assert _statuses(session, tournament) == {rx.id: A, ry.id: A}
    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _events(session, tournament) == []
    assert _logs(session, tournament, "registration.status_changed") == []


def test_unsettled_priority_window_is_settled_first(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 直接呼叫（真正的 worker 一輪會先由 allocate_priority_windows 結算）
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    x, y, z = _school(session), _school(session), _school(session)
    rx = _submitted(
        session, tournament, x, score="30", submitted_at=_in_window(tournament)
    )
    ry = _submitted(
        session, tournament, y, score="28", submitted_at=_in_window(tournament)
    )
    rz = _submitted(
        session, tournament, z, score="26", submitted_at=_in_window(tournament)
    )
    frozen_clock.set(tournament.registration_end)
    logs_before = len(audit.list_for_tournament(session, tournament.id))

    assert _close(session, tournament) is True

    assert _statuses(session, tournament) == {rx.id: A, ry.id: A, rz.id: W}
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert sorted(settlement.priority_school_ids) == sorted([x.id, y.id, z.id])
    actions = [
        (log.action, log.actor_id)
        for log in audit.list_for_tournament(session, tournament.id)[logs_before:]
    ]
    assert actions == [
        ("registration.status_changed", None),
        ("registration.status_changed", None),
        ("registration.status_changed", None),
        ("registration.priority_window_settled", None),
        ("tournament.status_changed", None),
    ]
    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert len(_events(session, tournament)) == 3


def test_pending_submitted_after_settlement_is_decided_first_come_then_filled(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 名額 3；P30 優先期內；之後依序送出 Q20、Q25、R22、P28
    tournament = _due_tournament(session, frozen_clock, capacity=3)
    p, q, r = _school(session), _school(session), _school(session)
    p30 = _submitted(
        session, tournament, p, score="30", submitted_at=_in_window(tournament)
    )
    frozen_clock.set(tournament.priority_end)
    assert service.settle_priority_window(session, tournament_id=tournament.id)
    late = tournament.priority_end
    q20 = _submitted(
        session, tournament, q, score="20", submitted_at=late + timedelta(minutes=1)
    )
    q25 = _submitted(
        session, tournament, q, score="25", submitted_at=late + timedelta(minutes=2)
    )
    r22 = _submitted(
        session, tournament, r, score="22", submitted_at=late + timedelta(minutes=3)
    )
    p28 = _submitted(
        session, tournament, p, score="28", submitted_at=late + timedelta(minutes=4)
    )
    frozen_clock.set(tournament.registration_end)

    assert _close(session, tournament) is True

    assert _statuses(session, tournament) == {
        p30.id: A,
        q20.id: A,
        q25.id: W,
        r22.id: A,
        p28.id: W,
    }
    assert P not in _statuses(session, tournament).values()
    assert _status(session, tournament) == TournamentStatus.CLOSED
    changed = _logs(session, tournament, "registration.status_changed")
    assert {log.actor_id for log in changed} == {None}


def test_late_pending_with_vacancy_is_filled_at_deadline(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 名額 4；P30 優先期內；之後送出 P28：先搶期判為候補，截止補位再補為正取
    tournament = _due_tournament(session, frozen_clock, capacity=4)
    p = _school(session)
    p30 = _submitted(
        session, tournament, p, score="30", submitted_at=_in_window(tournament)
    )
    frozen_clock.set(tournament.priority_end)
    assert service.settle_priority_window(session, tournament_id=tournament.id)
    p28 = _submitted(
        session,
        tournament,
        p,
        score="28",
        submitted_at=tournament.priority_end + timedelta(minutes=1),
    )
    frozen_clock.set(tournament.registration_end)

    assert _close(session, tournament) is True

    assert _statuses(session, tournament) == {p30.id: A, p28.id: A}
    # P28 先搶期判為候補、截止補位再補為正取（兩則事件建立時間相同，不比順序）；
    # 狀態變更紀錄依寫入順序
    p28_events = [
        ev["status"]
        for ev in _events(session, tournament)
        if ev["registration_id"] == str(p28.id)
    ]
    assert sorted(p28_events) == ["accepted", "waitlisted"]
    assert [
        log.after["status"]
        for log in _logs(session, tournament, "registration.status_changed")
        if log.entity_id == p28.id
    ] == ["waitlisted", "accepted"]


@pytest.mark.parametrize("with_forming", [False, True], ids=["no-team", "forming"])
def test_tournament_without_submissions_closes_with_empty_settlement(
    session: Session, frozen_clock: FrozenClock, with_forming: bool
) -> None:
    tournament = _due_tournament(session, frozen_clock)
    forming = _forming(session, tournament) if with_forming else None
    frozen_clock.set(tournament.registration_end)

    assert service.close_due_registration(session) is True

    assert _status(session, tournament) == TournamentStatus.CLOSED
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == []
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.actor_id is None
    expected = {} if forming is None else {forming.id: F}
    assert _statuses(session, tournament) == expected
    assert _events(session, tournament) == []


def test_custom_mode_only_closes(session: Session, frozen_clock: FrozenClock) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.mode = TournamentMode.CUSTOM
    session.add(row)
    session.flush()
    accepted = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    waitlisted = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set(session, accepted, A)
    _set(session, waitlisted, W)
    frozen_clock.set(tournament.registration_end)

    assert _close(session, tournament) is True

    assert _status(session, tournament) == TournamentStatus.CLOSED
    assert _statuses(session, tournament) == {accepted.id: A, waitlisted.id: W}
    assert repository.get_settlement(session, tournament.id) is None
    assert _events(session, tournament) == []
    [changed] = _logs(session, tournament, "tournament.status_changed")
    assert changed.actor_id is None


def test_rerun_changes_nothing(session: Session, frozen_clock: FrozenClock) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    for score in ("30", "28", "26"):
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
    frozen_clock.set(tournament.registration_end)
    assert service.close_due_registration(session) is True
    first = _snapshot(session, tournament)

    frozen_clock.advance(timedelta(minutes=5))
    assert service.close_due_registration(session) is False
    assert _close(session, tournament) is False

    assert _snapshot(session, tournament) == first


def test_multiple_due_tournaments_are_closed_one_at_a_time_earliest_first(
    session: Session, frozen_clock: FrozenClock
) -> None:
    later = _due_tournament(session, frozen_clock, end_hours=3)
    earlier = _due_tournament(session, frozen_clock, end_hours=2)
    frozen_clock.set(later.registration_end + timedelta(minutes=1))

    assert service.close_due_registration(session) is True
    assert _status(session, earlier) == TournamentStatus.CLOSED
    assert _status(session, later) == TournamentStatus.OPEN

    assert service.close_due_registration(session) is True
    assert _status(session, later) == TournamentStatus.CLOSED

    assert service.close_due_registration(session) is False


def test_worker_downtime_opens_and_closes_in_one_round(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    now = frozen_clock.now()
    tournament = _tournament(
        session,
        frozen_clock,
        registration_start=(now + timedelta(hours=1)).isoformat(),
        registration_end=(now + timedelta(hours=4)).isoformat(),
    )
    assert _status(session, tournament) == TournamentStatus.UPCOMING
    session.commit()

    frozen_clock.set(tournament.registration_end + timedelta(hours=1))
    _round(session_factory)

    assert _status(session, tournament) == TournamentStatus.CLOSED
    changes = [
        (log.before, log.after, log.actor_id)
        for log in _logs(session, tournament, "tournament.status_changed")
    ]
    assert changes == [
        ({"status": "upcoming"}, {"status": "open"}, None),
        ({"status": "open"}, {"status": "closed"}, None),
    ]


# ---------------------------------------------------------------- 截止後


def test_create_join_profile_and_submit_after_closed_say_deadline_passed(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _due_tournament(session, frozen_clock)
    captain = _make_account(session)
    team = _create_ok(client, captain, tournament.id)
    frozen_clock.set(tournament.registration_end)
    assert _close(session, tournament) is True
    # 把時鐘撥回截止前：只剩「賽事已是報名截止」這個原因，確認不會變成「目前不開放報名」
    frozen_clock.set(tournament.registration_end - timedelta(seconds=1))

    responses = [
        _create(client, _make_account(session), tournament.id, "晚到隊"),
        _join(client, _make_account(session), team["invite_token"]),
        client.put(
            f"{API}/teams/{team['id']}/members/me/profile",
            data={"game_account_id": "Late#1", "rank_tier": "鑽石"},
            headers=_auth(captain),
        ),
        client.post(f"{API}/teams/{team['id']}/submission", headers=_auth(captain)),
    ]

    for response in responses:
        assert response.status_code == 409, response.text
        assert _error_code(response) == "REGISTRATION_CLOSED"
        assert response.json()["detail"]["message"] == DEADLINE_MESSAGE


def test_draw_after_closed_does_not_finalize_again(
    session: Session, frozen_clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    regs = [
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
        for score in ("30", "28", "26")
    ]
    frozen_clock.set(tournament.registration_end)
    assert _close(session, tournament) is True
    before = _statuses(session, tournament)
    assert before == {regs[0].id: A, regs[1].id: A, regs[2].id: W}

    calls: list[Any] = []
    monkeypatch.setattr(
        service, "finalize_for_draw", lambda *args, **kwargs: calls.append(kwargs)
    )
    competition_service.draw(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )

    assert calls == []
    assert _statuses(session, tournament) == {
        regs[0].id: D,
        regs[1].id: D,
        regs[2].id: W,
    }
    assert _status(session, tournament) == TournamentStatus.PUBLISHED


def test_waitlist_after_closed_shows_after_deadline_position(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _due_tournament(session, frozen_clock, capacity=2)
    for score in ("30", "28"):
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
    captain, own = _own_team(client, session, tournament)
    _submitted(
        session,
        tournament,
        _school(session),
        score="26",
        submitted_at=_in_window(tournament),
        registration=own,
    )
    frozen_clock.set(tournament.registration_end)
    assert _close(session, tournament) is True

    expected = (1, None, False, "after_deadline")
    page = _team_page(client, captain, own.team_id)
    assert page["registration_status"] == "waitlisted"
    assert _waitlist(page) == expected
    card = _my_card(client, captain, own.team_id)
    assert card["registration_status"] == "waitlisted"
    assert _waitlist(card) == expected
