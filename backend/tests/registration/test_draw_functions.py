"""Story 3.6（第二階段之一）：給 competition 抽籤用的四個 registration 函式。

`finalize_for_draw`（優先期結算 → 補做先搶期 → 截止補位）、`list_accepted_teams`、
`mark_drawn`、`get_team_names`，以及經 competition `draw` 的完整抽籤（不用
`fake_registration`）與抽籤後 S17／S12 的候補顯示。

報名直接寫成「已送出・待分配」並帶送出時的快照（沿用 worker 測試的 helper）；
`frozen_clock` 固定在 2026-10-18 11:00 UTC，賽事報名從 1 小時前開始、優先期 2 小時、
7 天後報名截止、8 天後開賽。
"""

import random
import secrets
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.core.config import settings
from app.core.errors import BusinessError
from app.demo_data import load, tournaments
from app.modules.competition import service as competition_service
from app.modules.identity import service as identity_service
from app.modules.identity.models import Account
from app.modules.registration import repository, service
from app.modules.registration.models import (
    MemberRole,
    Registration,
    RegistrationStatus,
    Team,
    TeamMember,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.helpers import make_account
from tests.registration.test_teams import _auth, _set_status
from tests.worker.test_priority_window_allocation import (
    _events,
    _in_window,
    _my_card,
    _own_team,
    _run,
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


# ---------------------------------------------------------------- 共用


def _finalize(session: Session, tournament: TournamentRead) -> None:
    service.finalize_for_draw(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )


def _after_priority(tournament: TournamentRead, minutes: int) -> Any:
    return tournament.priority_end + timedelta(minutes=minutes)


def _logs(session: Session, tournament: TournamentRead, action: str) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == action
    ]


def _changes(session: Session, tournament: TournamentRead) -> list[tuple[Any, str]]:
    """狀態變更紀錄依寫入順序（操作紀錄的 seq）：(報名 id, 新狀態)。"""
    return [
        (log.entity_id, log.after["status"])
        for log in _logs(session, tournament, "registration.status_changed")
    ]


def _snapshot(session: Session, tournament: TournamentRead) -> tuple[Any, ...]:
    return (
        _statuses(session, tournament),
        len(audit.list_for_tournament(session, tournament.id)),
        len(_events(session, tournament)),
    )


# ---------------------------------------------------------------- finalize_for_draw：I/O 矩陣


def test_early_draw_settles_priority_window_immediately(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 優先期還沒結束：立即以當下已送出的報名結算（提前抽籤＝提前結束報名）
    tournament = _tournament(session, frozen_clock, capacity=2)
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
    assert frozen_clock.now() < tournament.priority_end

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {rx.id: A, ry.id: A, rz.id: W}
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert sorted(settlement.priority_school_ids) == sorted([x.id, y.id, z.id])
    # settled_at 為當下時間，早於優先期結束
    assert settlement.settled_at == frozen_clock.now()
    assert settlement.settled_at < tournament.priority_end

    # 操作者為主辦方：逐筆狀態變更、結算摘要
    changed = _logs(session, tournament, "registration.status_changed")
    assert len(changed) == 3
    assert {log.actor_id for log in changed} == {tournament.organizer_id}
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.actor_id == tournament.organizer_id
    assert {
        (e["registration_id"], e["status"]) for e in _events(session, tournament)
    } == {
        (str(rx.id), "accepted"),
        (str(ry.id), "accepted"),
        (str(rz.id), "waitlisted"),
    }


def _same_school_teams(
    session: Session, tournament: TournamentRead
) -> tuple[Registration, Registration, Registration, Registration]:
    a, b = _school(session), _school(session)
    a30 = _submitted(
        session, tournament, a, score="30", submitted_at=_in_window(tournament, 1)
    )
    a25 = _submitted(
        session, tournament, a, score="25", submitted_at=_in_window(tournament, 2)
    )
    a20 = _submitted(
        session, tournament, a, score="20", submitted_at=_in_window(tournament, 3)
    )
    b28 = _submitted(
        session, tournament, b, score="28", submitted_at=_in_window(tournament, 4)
    )
    return a30, a25, a20, b28


def test_same_school_teams_settle_then_fill_up_to_two_per_school(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)
    a30, a25, a20, b28 = _same_school_teams(session, tournament)
    frozen_clock.set(_after_priority(tournament, 1))

    _finalize(session, tournament)

    # 結算：A30、B28 正取；補位補 A25，A20 會使 A 校超過 2 隊而略過；保留 1 空位
    assert _statuses(session, tournament) == {
        a30.id: A,
        b28.id: A,
        a25.id: A,
        a20.id: W,
    }
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.after["accepted"] == [str(a30.id), str(b28.id)]
    # a25 改了兩次（候補 → 正取），共 5 筆狀態變更、5 則事件
    assert len(_logs(session, tournament, "registration.status_changed")) == 5
    assert _changes(session, tournament)[-1] == (a25.id, "accepted")
    assert len(_events(session, tournament)) == 5


def test_already_settled_by_worker_only_fills(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)
    a30, a25, a20, b28 = _same_school_teams(session, tournament)
    session.commit()
    frozen_clock.set(_after_priority(tournament, 1))
    _run(session_factory)
    [worker_summary] = _logs(
        session, tournament, "registration.priority_window_settled"
    )
    assert worker_summary.actor_id is None

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {
        a30.id: A,
        b28.id: A,
        a25.id: A,
        a20.id: W,
    }
    # 不重複結算：摘要仍只有 1 筆（worker 寫的）；補位的操作者為主辦方
    assert len(_logs(session, tournament, "registration.priority_window_settled")) == 1
    changed = _logs(session, tournament, "registration.status_changed")
    assert len(changed) == 5
    assert changed[-1].entity_id == a25.id
    assert changed[-1].actor_id == tournament.organizer_id


def test_late_submissions_are_decided_first_come_in_order(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=3)
    p, q, r = _school(session), _school(session), _school(session)
    p30 = _submitted(
        session, tournament, p, score="30", submitted_at=_in_window(tournament)
    )
    q20 = _submitted(
        session, tournament, q, score="20", submitted_at=_after_priority(tournament, 1)
    )
    q25 = _submitted(
        session, tournament, q, score="25", submitted_at=_after_priority(tournament, 2)
    )
    r22 = _submitted(
        session, tournament, r, score="22", submitted_at=_after_priority(tournament, 3)
    )
    p28 = _submitted(
        session, tournament, p, score="28", submitted_at=_after_priority(tournament, 4)
    )
    frozen_clock.set(_after_priority(tournament, 10))

    _finalize(session, tournament)

    statuses = _statuses(session, tournament)
    assert statuses == {p30.id: A, q20.id: A, q25.id: W, r22.id: A, p28.id: W}
    assert P not in statuses.values()
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert settlement.priority_school_ids == [p.id]
    # 每筆一次分配：結算 1 筆、先搶期 4 筆；補位無空位
    assert len(_events(session, tournament)) == 5
    assert _changes(session, tournament) == [
        (p30.id, "accepted"),
        (q20.id, "accepted"),
        (q25.id, "waitlisted"),
        (r22.id, "accepted"),
        (p28.id, "waitlisted"),
    ]


def test_late_submission_with_same_submit_time_is_ordered_by_id(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 名額 2：優先期內 1 隊正取；之後兩校同時送出，id 小的正取，另一隊候補
    # （截止補位已無空位）
    tournament = _tournament(session, frozen_clock, capacity=2)
    early = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    at = _after_priority(tournament, 1)
    first, second = sorted(
        (
            _submitted(session, tournament, _school(session), submitted_at=at)
            for _ in range(2)
        ),
        key=lambda r: r.id,
    )
    frozen_clock.set(_after_priority(tournament, 10))

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {early.id: A, first.id: A, second.id: W}


def test_late_submission_of_priority_school_is_filled_at_deadline(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)
    p = _school(session)
    p30 = _submitted(
        session, tournament, p, score="30", submitted_at=_in_window(tournament)
    )
    p28 = _submitted(
        session, tournament, p, score="28", submitted_at=_after_priority(tournament, 1)
    )
    frozen_clock.set(_after_priority(tournament, 10))

    _finalize(session, tournament)

    # 先搶期判為候補，截止補位再補為正取；保留 2 空位
    assert _statuses(session, tournament) == {p30.id: A, p28.id: A}
    assert _changes(session, tournament) == [
        (p30.id, "accepted"),
        (p28.id, "waitlisted"),
        (p28.id, "accepted"),
    ]
    assert len(_events(session, tournament)) == 3


def test_first_come_backfills_vacancy_before_new_submission(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 名額 2：X、Y 已結算正取，Z 候補且有順位；X 被取消資格空出 1 位。
    # 之後 W 校送出：先由 Z 遞補，W 再判定時名額已滿而候補
    tournament = _tournament(session, frozen_clock, capacity=2)
    rx = _submitted(
        session,
        tournament,
        _school(session),
        score="30",
        submitted_at=_in_window(tournament),
    )
    _submitted(
        session,
        tournament,
        _school(session),
        score="28",
        submitted_at=_in_window(tournament),
    )
    frozen_clock.set(_after_priority(tournament, 1))
    assert service.settle_priority_window(session, tournament_id=tournament.id)
    # 結算後才送出的 Z 校候補（先搶期學校，有順位）
    rz = _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=_after_priority(tournament, 2),
    )
    service.mark_status(session, registration=rz, to=W, actor_id=None)
    service.mark_status(
        session, registration=rx, to=RegistrationStatus.DISQUALIFIED, actor_id=None
    )
    rw = _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=_after_priority(tournament, 3),
    )
    frozen_clock.set(_after_priority(tournament, 10))

    _finalize(session, tournament)

    statuses = _statuses(session, tournament)
    assert statuses[rz.id] == A
    assert statuses[rw.id] == W


def test_full_capacity_changes_nothing(
    session: Session,
    session_factory: Callable[[], Session],
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
    for score in ("30", "28", "26"):
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
    session.commit()
    frozen_clock.set(_after_priority(tournament, 1))
    _run(session_factory)
    before = _snapshot(session, tournament)

    _finalize(session, tournament)

    assert _snapshot(session, tournament) == before


def test_second_call_changes_nothing(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=3)
    p, q = _school(session), _school(session)
    _submitted(session, tournament, p, score="30", submitted_at=_in_window(tournament))
    _submitted(session, tournament, p, score="29", submitted_at=_in_window(tournament))
    _submitted(
        session, tournament, q, score="20", submitted_at=_after_priority(tournament, 1)
    )
    frozen_clock.set(_after_priority(tournament, 10))
    _finalize(session, tournament)
    first = _snapshot(session, tournament)

    frozen_clock.advance(timedelta(minutes=5))
    _finalize(session, tournament)

    assert _snapshot(session, tournament) == first


def test_tournament_without_submissions_does_not_raise(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    forming = Team(
        tournament_id=tournament.id,
        name="組隊中",
        invite_token=secrets.token_urlsafe(24),
    )
    session.add(forming)
    session.flush()
    registration = Registration(
        team_id=forming.id,
        tournament_id=tournament.id,
        status=RegistrationStatus.FORMING,
    )
    session.add(registration)
    session.flush()

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {
        registration.id: RegistrationStatus.FORMING
    }
    assert service.list_accepted_teams(session, tournament_id=tournament.id) == []
    assert _events(session, tournament) == []
    with pytest.raises(BusinessError) as caught:
        competition_service.draw(
            session, tournament_id=tournament.id, actor_id=tournament.organizer_id
        )
    assert caught.value.code == "NOT_ENOUGH_TEAMS"


@pytest.mark.parametrize(
    "status", [s for s in TournamentStatus if s != TournamentStatus.OPEN]
)
def test_tournament_not_open_is_left_unchanged(
    session: Session, frozen_clock: FrozenClock, status: TournamentStatus
) -> None:
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    _set_status(session, tournament.id, status)

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {registration.id: P}
    assert repository.get_settlement(session, tournament.id) is None


def test_custom_mode_tournament_is_left_unchanged(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.mode = TournamentMode.CUSTOM
    session.add(row)
    session.flush()
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )

    _finalize(session, tournament)

    assert _statuses(session, tournament) == {registration.id: P}
    assert repository.get_settlement(session, tournament.id) is None


# ---------------------------------------------------------------- list_accepted_teams


def test_list_accepted_teams_returns_only_accepted_with_members_sorted_by_id(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
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
    captain = make_account(session)
    player = make_account(session)
    for account, role in ((captain, MemberRole.CAPTAIN), (player, MemberRole.PLAYER)):
        session.add(
            TeamMember(
                team_id=regs[0].team_id,
                tournament_id=tournament.id,
                account_id=account.id,
                role=role,
            )
        )
        session.flush()
        # 加入時間不同，成員依加入順序排列
        frozen_clock.advance(timedelta(seconds=1))
    _finalize(session, tournament)

    teams = service.list_accepted_teams(session, tournament_id=tournament.id)

    assert [t.id for t in teams] == sorted([regs[0].team_id, regs[1].team_id])
    by_id = {t.id: t for t in teams}
    assert [(m.account_id, m.role) for m in by_id[regs[0].team_id].members] == [
        (captain.id, MemberRole.CAPTAIN),
        (player.id, MemberRole.PLAYER),
    ]
    assert by_id[regs[1].team_id].members == []
    assert all(t.tournament_id == tournament.id for t in teams)


# ---------------------------------------------------------------- mark_drawn


def _two_accepted(
    session: Session, frozen_clock: FrozenClock
) -> tuple[TournamentRead, Registration, Registration, Registration]:
    tournament = _tournament(session, frozen_clock, capacity=2)
    first, second, waiting = (
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
        for score in ("30", "28", "26")
    )
    _finalize(session, tournament)
    return tournament, first, second, waiting


def _mark_drawn(
    session: Session, tournament: TournamentRead, team_ids: list[uuid.UUID]
) -> None:
    service.mark_drawn(
        session,
        tournament_id=tournament.id,
        team_ids=team_ids,
        actor_id=tournament.organizer_id,
    )


def test_mark_drawn_changes_only_given_teams_without_events(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, first, second, waiting = _two_accepted(session, frozen_clock)
    events_before = len(_events(session, tournament))

    _mark_drawn(session, tournament, [first.team_id, first.team_id])

    assert _statuses(session, tournament) == {first.id: D, second.id: A, waiting.id: W}
    assert len(_events(session, tournament)) == events_before
    last = _logs(session, tournament, "registration.status_changed")[-1]
    assert (last.entity_id, last.actor_id, last.after) == (
        first.id,
        tournament.organizer_id,
        {"status": "drawn"},
    )
    # 已是 drawn 再呼叫：拒絕
    with pytest.raises(BusinessError) as caught:
        _mark_drawn(session, tournament, [first.team_id])
    assert caught.value.code == "REGISTRATION_NOT_ACCEPTED"


def test_mark_drawn_with_empty_list_does_nothing(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, *_ = _two_accepted(session, frozen_clock)
    before = _snapshot(session, tournament)

    _mark_drawn(session, tournament, [])

    assert _snapshot(session, tournament) == before


@pytest.mark.parametrize(
    "intruder", ["missing", "other_tournament", "forming", "waitlisted"]
)
def test_mark_drawn_rejects_whole_batch(
    session: Session, frozen_clock: FrozenClock, intruder: str
) -> None:
    tournament, first, second, waiting = _two_accepted(session, frozen_clock)
    if intruder == "missing":
        extra = uuid.uuid4()
    elif intruder == "other_tournament":
        other = _tournament(session, frozen_clock, capacity=2)
        reg = _submitted(
            session, other, _school(session), submitted_at=_in_window(other)
        )
        _finalize(session, other)
        assert _statuses(session, other) == {reg.id: A}
        extra = reg.team_id
    elif intruder == "forming":
        team = Team(
            tournament_id=tournament.id,
            name="組隊中",
            invite_token=secrets.token_urlsafe(24),
        )
        session.add(team)
        session.flush()
        session.add(
            Registration(
                team_id=team.id,
                tournament_id=tournament.id,
                status=RegistrationStatus.FORMING,
            )
        )
        session.flush()
        extra = team.id
    else:
        extra = waiting.team_id
    before = _snapshot(session, tournament)

    with pytest.raises(BusinessError) as caught:
        _mark_drawn(session, tournament, [first.team_id, second.team_id, extra])

    assert caught.value.code == "REGISTRATION_NOT_ACCEPTED"
    assert caught.value.status_code == 409
    assert caught.value.message == "有隊伍不是這個賽事的正取，無法標為已參賽。"
    assert _snapshot(session, tournament) == before


# ---------------------------------------------------------------- get_team_names


def test_get_team_names_ignores_missing_ids_and_status(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament, first, second, waiting = _two_accepted(session, frozen_clock)
    _mark_drawn(session, tournament, [first.team_id])
    names = service.get_team_names(
        session, team_ids=[first.team_id, waiting.team_id, uuid.uuid4(), first.team_id]
    )

    first_team = session.get(Team, first.team_id)
    waiting_team = session.get(Team, waiting.team_id)
    assert first_team is not None
    assert waiting_team is not None
    assert set(names) == {first.team_id, waiting.team_id}
    assert names[first.team_id] == first_team.name
    assert names[waiting.team_id] == waiting_team.name
    assert service.get_team_names(session, team_ids=[]) == {}


# ---------------------------------------------------------------- 經 competition 抽籤


def _draw(session: Session, tournament: TournamentRead) -> Any:
    return competition_service.draw(
        session,
        tournament_id=tournament.id,
        actor_id=tournament.organizer_id,
        rng=random.Random(7),
    )


def test_full_draw_while_open_then_waitlist_shows_after_deadline_position(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
    x = _submitted(
        session,
        tournament,
        _school(session),
        score="30",
        submitted_at=_in_window(tournament),
    )
    y = _submitted(
        session,
        tournament,
        _school(session),
        score="28",
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
    session.commit()

    bracket = _draw(session, tournament)

    placed = {
        team
        for match in bracket.matches
        for team in (match.team_a_id, match.team_b_id)
        if team is not None
    }
    assert placed == {x.team_id, y.team_id}
    assert _statuses(session, tournament) == {x.id: D, y.id: D, own.id: W}
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == TournamentStatus.PUBLISHED
    )
    assert service.list_accepted_teams(session, tournament_id=tournament.id) == []
    # 分配與 drawn 的操作紀錄操作者為主辦方
    changed = _logs(session, tournament, "registration.status_changed")
    assert len(changed) == 5
    assert {log.actor_id for log in changed} == {tournament.organizer_id}
    [summary] = _logs(session, tournament, "registration.priority_window_settled")
    assert summary.actor_id == tournament.organizer_id
    # 事件只有分配（3 則），mark_drawn 不發
    assert len(_events(session, tournament)) == 3

    # 還沒到報名截止時間，但賽事已不是開放報名：候補依截止後規則顯示順位
    assert frozen_clock.now() < tournament.registration_end
    expected = (1, None, False, "after_deadline")
    page = _team_page(client, captain, own.team_id)
    assert page["registration_status"] == "waitlisted"
    assert _waitlist(page) == expected
    card = _my_card(client, captain, own.team_id)
    assert card["registration_status"] == "waitlisted"
    assert _waitlist(card) == expected


def test_after_draw_school_with_two_drawn_teams_shows_limit_reason(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
) -> None:
    # A 校 3 隊、名額 2：結算 A30 正取，補位補 A25，A20 候補；抽籤後 A 校 2 隊 drawn
    tournament = _tournament(session, frozen_clock, capacity=2)
    a = _school(session)
    a30 = _submitted(
        session, tournament, a, score="30", submitted_at=_in_window(tournament, 1)
    )
    a25 = _submitted(
        session, tournament, a, score="25", submitted_at=_in_window(tournament, 2)
    )
    captain, own = _own_team(client, session, tournament)
    _submitted(
        session,
        tournament,
        a,
        score="20",
        submitted_at=_in_window(tournament, 3),
        registration=own,
    )
    session.commit()

    _draw(session, tournament)

    assert _statuses(session, tournament) == {a30.id: D, a25.id: D, own.id: W}
    expected = (None, "SCHOOL_LIMIT_REACHED", False, "after_deadline")
    assert _waitlist(_team_page(client, captain, own.team_id)) == expected
    assert _waitlist(_my_card(client, captain, own.team_id)) == expected


def test_draw_via_api_no_longer_returns_503(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=4)
    for score in ("30", "28"):
        _submitted(
            session,
            tournament,
            _school(session),
            score=score,
            submitted_at=_in_window(tournament),
        )
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    session.commit()

    response = client.post(
        f"{settings.API_V1_STR}/tournaments/{tournament.id}/draw",
        headers=_auth(organizer),
    )

    assert response.status_code == 201, response.text
    assert set(_statuses(session, tournament).values()) == {D}


def test_failed_early_draw_via_api_rolls_back_finalize(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 優先期還沒結束、只有 1 隊：finalize_for_draw 在請求的交易內結算（寫入結算紀錄、
    # 狀態、操作紀錄與事件），之後正取不足 2 隊抽籤失敗，router 不 commit，全部回滾
    tournament = _tournament(session, frozen_clock)
    registration = _submitted(
        session, tournament, _school(session), submitted_at=_in_window(tournament)
    )
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    session.commit()
    assert frozen_clock.now() < tournament.priority_end
    logs_before = len(audit.list_for_tournament(session, tournament.id))

    real_finalize = service.finalize_for_draw
    seen: dict[str, Any] = {}

    def _finalize_and_observe(db: Session, **kwargs: Any) -> None:
        real_finalize(db, **kwargs)
        # 在請求的同一個 session 內確認確實寫入過
        seen["settled"] = repository.get_settlement(db, tournament.id) is not None
        row = repository.get_registration_by_team(db, registration.team_id)
        seen["status"] = None if row is None else row.status
        seen["changed"] = len(_logs(db, tournament, "registration.status_changed"))
        seen["events"] = len(_events(db, tournament))

    monkeypatch.setattr(service, "finalize_for_draw", _finalize_and_observe)

    response = client.post(
        f"{settings.API_V1_STR}/tournaments/{tournament.id}/draw",
        headers=_auth(organizer),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "NOT_ENOUGH_TEAMS"
    assert seen == {"settled": True, "status": A, "changed": 1, "events": 1}
    # 全部回滾
    session.expire_all()
    assert repository.get_settlement(session, tournament.id) is None
    assert _statuses(session, tournament) == {registration.id: P}
    assert len(audit.list_for_tournament(session, tournament.id)) == logs_before
    assert _events(session, tournament) == []
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == TournamentStatus.OPEN
    )


# ---------------------------------------------------------------- 示範資料


@pytest.fixture
def first_admin(session: Session) -> None:
    identity_service.ensure_first_admin(
        session, email=settings.FIRST_ADMIN_EMAIL, password="admin-password"
    )


@pytest.mark.usefixtures("frozen_clock", "first_admin")
def test_demo_load_leaves_no_settlement_on_demo_tournament(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "demo-password")
    monkeypatch.setattr(settings, "DEMO_EMAIL_DOMAIN", "demo.example.com")

    assert load(session) is True

    [demo] = [
        t
        for t in tournaments_service.list_public_tournaments(session)
        if t.name == tournaments.DEMO_TOURNAMENT_NAME
    ]
    assert repository.get_settlement(session, demo.id) is None
    assert competition_service.get_bracket(session, tournament_id=demo.id) is None
