"""Story 3.7：抽籤前撤回報名與遞補（I/O 矩陣；提高名額在 test_raise_capacity.py）。

前置狀態直接寫入報名列（沿用 3.5 的 `_preset`），被測的撤回經 API。`frozen_clock`
固定在 2026-10-18 11:00 UTC（下稱 T）；賽事報名從 T−1 小時開始、優先期 1 小時，所以
優先期在 T 結束，報名截止在 T−1 小時＋7 天。撤回前以 `frozen_clock.advance` 推進到
先搶期或截止後。真實的並行撤回與送出在 test_settlement_concurrency.py。
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import audit
from app.core.events import OutboxEvent
from app.modules.identity.models import Account, School
from app.modules.registration import repository, service
from app.modules.registration.models import (
    MemberRole,
    Registration,
    RegistrationStatus,
    TeamMember,
)
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.registration.test_first_come_submission import (
    SUBMIT_AFTER,
    _api_team,
    _changes,
    _first_come,
    _in_window,
    _logs,
    _preset,
    _settled,
    _submit_ok,
    _tournament,
)
from tests.registration.test_submit_registration import (
    _detail,
    _registration,
    _school,
    _submit,
)
from tests.registration.test_teams import (
    API,
    _auth,
    _error_code,
    _join,
    _make_account,
    _set_status,
)

S = RegistrationStatus


# ---------------------------------------------------------------- 測試資料


def _withdraw(client: TestClient, account: Account, team_id: Any) -> Any:
    return client.post(f"{API}/teams/{team_id}/withdrawal", headers=_auth(account))


def _withdraw_ok(client: TestClient, account: Account, team_id: Any) -> dict[str, Any]:
    response = _withdraw(client, account, team_id)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _team(
    client: TestClient,
    session: Session,
    tournament: TournamentRead,
    school: School,
    status: S,
    *,
    submitted_at: Any,
    score: str = "30",
    representative: bool = False,
) -> tuple[dict[str, Any], Account, Registration]:
    """經 API 建立的一人隊伍，報名直接改成 `status`（有送出快照）。"""
    team, captain = _api_team(client, session, tournament, school)
    registration = _preset(
        session,
        tournament,
        school,
        status,
        submitted_at=submitted_at,
        team_id=team["id"],
        score=score,
    )
    if representative:
        registration.is_representative = True
        session.add(registration)
        session.flush()
    return team, captain, registration


def _events(
    session: Session, tournament: TournamentRead, event_type: str
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.type == event_type)
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
    )
    return [
        row.payload
        for row in rows
        if row.payload["tournament_id"] == str(tournament.id)
    ]


def _backfilled_ids(session: Session, tournament: TournamentRead) -> set[str]:
    return {
        e["registration_id"]
        for e in _events(session, tournament, "RegistrationBackfilled")
    }


def _status(session: Session, registration: Registration) -> S:
    session.expire_all()
    found = session.get(Registration, registration.id)
    assert found is not None
    return found.status


def _card(client: TestClient, account: Account, team_id: Any) -> dict[str, Any]:
    response = client.get(f"{API}/accounts/me/teams", headers=_auth(account))
    assert response.status_code == 200, response.text
    return next(c for c in response.json() if c["team_id"] == str(team_id))


# ---------------------------------------------------------------- 撤回本身


def test_withdraw_in_priority_window_leaves_others_unchanged(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """優先期內撤回（沒有結算紀錄）：只轉 `withdrawn`，不遞補。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    other = _preset(
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 20),
    )

    body = _withdraw_ok(client, captain, team["id"])

    assert body["registration_status"] == "withdrawn"
    assert body["withdrawable"] is False
    assert body["backfilled"] is False
    assert _status(session, registration) == S.WITHDRAWN
    assert _status(session, other) == S.PENDING
    assert _changes(session, tournament, registration.id) == [("withdrawn", captain.id)]
    assert _events(session, tournament, "RegistrationBackfilled") == []
    assert repository.get_settlement(session, tournament.id) is None
    # 優先期結算不會把撤回的報名算進去
    frozen_clock.advance(timedelta(minutes=1))
    assert service.settle_priority_window(session, tournament_id=tournament.id)
    assert _status(session, other) == S.ACCEPTED
    assert _status(session, registration) == S.WITHDRAWN


def test_withdrawable_only_for_captain_before_draw(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    team, captain, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
    )
    player = _make_account(session)
    # 名單已鎖定不能經 API 加入：直接寫入隊員
    session.add(
        TeamMember(
            team_id=uuid.UUID(team["id"]),
            tournament_id=tournament.id,
            account_id=player.id,
            role=MemberRole.PLAYER,
        )
    )
    session.flush()

    assert _detail(client, captain, team["id"])["withdrawable"] is True
    assert _card(client, captain, team["id"])["withdrawable"] is True
    assert _detail(client, player, team["id"])["withdrawable"] is False
    assert _card(client, player, team["id"])["withdrawable"] is False

    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)
    assert _detail(client, captain, team["id"])["withdrawable"] is False

    response = _withdraw(client, player, team["id"])
    assert response.status_code == 403
    assert _error_code(response) == "TEAM_CAPTAIN_REQUIRED"


def test_non_captain_cannot_withdraw(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, starters=2)
    school = _school(session)
    team, captain = _api_team(client, session, tournament, school)
    player = _make_account(session)
    assert _join(client, player, team["invite_token"]).status_code == 200
    _preset(
        session,
        tournament,
        school,
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
        team_id=team["id"],
    )

    response = _withdraw(client, player, team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_CAPTAIN_REQUIRED"
    assert _registration(session, team["id"]).status == S.PENDING
    outsider = _withdraw(client, _make_account(session), team["id"])
    assert outsider.status_code == 403
    assert _error_code(outsider) == "TEAM_MEMBER_REQUIRED"
    assert _withdraw(client, captain, uuid.uuid4()).status_code == 404


@pytest.mark.parametrize(
    ("registration_status", "tournament_status"),
    [
        (S.FORMING, TournamentStatus.OPEN),
        (S.WITHDRAWN, TournamentStatus.OPEN),
        (S.DRAWN, TournamentStatus.PUBLISHED),
        (S.ACCEPTED, TournamentStatus.PUBLISHED),
        (S.ACCEPTED, TournamentStatus.CANCELLED),
    ],
    ids=["forming", "withdrawn", "drawn", "published", "cancelled"],
)
def test_not_withdrawable_is_rejected_without_changes(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    registration_status: S,
    tournament_status: TournamentStatus,
) -> None:
    tournament = _tournament(session, frozen_clock)
    school = _school(session)
    team, captain = _api_team(client, session, tournament, school)
    if registration_status != S.FORMING:
        _preset(
            session,
            tournament,
            school,
            registration_status,
            submitted_at=_in_window(tournament, 10),
            team_id=team["id"],
        )
    _set_status(session, tournament.id, tournament_status)

    response = _withdraw(client, captain, team["id"])

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_NOT_WITHDRAWABLE"
    registration = _registration(session, team["id"])
    assert registration.status == registration_status
    assert _changes(session, tournament, registration.id) == []


# ---------------------------------------------------------------- 先搶期的遞補


def test_first_come_withdraw_backfills_earliest_eligible_waitlist(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """名額 2 已滿；A（X）撤回；候補 B（Y，最早送出）、C（Y）→ B 遞補，C 仍候補。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_x, school_y, school_q = (_school(session) for _ in range(3))
    _settled(session, tournament, [])
    team_a, captain_a, registration_a = _team(
        client,
        session,
        tournament,
        school_x,
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    _preset(
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 2),
    )
    team_b, captain_b, waiting_b = _team(
        client,
        session,
        tournament,
        school_y,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    waiting_c = _preset(
        session,
        tournament,
        school_y,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 4),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _withdraw_ok(client, captain_a, team_a["id"])

    assert _status(session, waiting_b) == S.ACCEPTED
    assert _status(session, waiting_c) == S.WAITLISTED
    session.expire_all()
    assert waiting_b.backfilled_at == frozen_clock.now()
    assert _changes(session, tournament, waiting_b.id) == [("accepted", None)]
    # 遞補的操作者是系統，可追溯：同一交易內緊接在隊長撤回那筆之後（依時間、序號排列）
    assert [
        (log.entity_id, log.actor_id, log.after)
        for log in audit.list_for_tournament(session, tournament.id)[-2:]
    ] == [
        (registration_a.id, captain_a.id, {"status": "withdrawn"}),
        (waiting_b.id, None, {"status": "accepted"}),
    ]
    assert _events(session, tournament, "RegistrationBackfilled") == [
        {
            "registration_id": str(waiting_b.id),
            "team_id": team_b["id"],
            "tournament_id": str(tournament.id),
        }
    ]
    # 遞補只發 RegistrationBackfilled
    assert _events(session, tournament, "RegistrationAllocated") == []
    detail = _detail(client, captain_b, team_b["id"])
    assert (detail["registration_status"], detail["backfilled"]) == ("accepted", True)
    card = _card(client, captain_b, team_b["id"])
    assert (card["registration_status"], card["backfilled"]) == ("accepted", True)

    # 抽籤後為已參賽，不再顯示「已遞補為正取」
    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)
    service.mark_drawn(
        session,
        tournament_id=tournament.id,
        team_ids=[uuid.UUID(team_b["id"])],
        actor_id=tournament.organizer_id,
    )
    detail = _detail(client, captain_b, team_b["id"])
    assert (detail["registration_status"], detail["backfilled"]) == ("drawn", False)
    assert _card(client, captain_b, team_b["id"])["backfilled"] is False


def test_withdrawing_waitlisted_updates_other_positions(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """名額已滿時撤回候補：不遞補；其餘候補的順位在下次載入時往前。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    accepted = _preset(
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    _preset(
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    team_b, captain_b, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 2),
    )
    team_d, captain_d, waiting_d = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    frozen_clock.advance(SUBMIT_AFTER)
    assert _detail(client, captain_d, team_d["id"])["waitlist_position"] == 2

    body = _withdraw_ok(client, captain_b, team_b["id"])

    assert body["registration_status"] == "withdrawn"
    assert body["waitlist_position"] is None
    assert _status(session, accepted) == S.ACCEPTED
    assert _status(session, waiting_d) == S.WAITLISTED
    assert _events(session, tournament, "RegistrationBackfilled") == []
    assert _detail(client, captain_d, team_d["id"])["waitlist_position"] == 1
    assert _card(client, captain_d, team_d["id"])["waitlist_position"] == 1


def test_withdrawing_waitlisted_fills_a_vacancy_left_earlier(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """之前取消資格留下的空位：撤回候補時也跑遞補，順便補上。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    _preset(
        session,
        tournament,
        _school(session),
        S.DISQUALIFIED,
        submitted_at=_first_come(tournament, 1),
    )
    _preset(
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 2),
    )
    team_b, captain_b, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    waiting_c = _preset(
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 4),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _withdraw_ok(client, captain_b, team_b["id"])

    assert _status(session, waiting_c) == S.ACCEPTED
    assert _backfilled_ids(session, tournament) == {str(waiting_c.id)}


def test_representative_withdraw_is_backfilled_by_same_school_next_best(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """P 校代表隊撤回；同校候補 P2（80）、P3（90）→ P3 遞補，別校更早的候補不搶。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_w = (_school(session) for _ in range(3))
    _settled(session, tournament, [school_p, school_q])
    team_p, captain_p, _ = _team(
        client,
        session,
        tournament,
        school_p,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
        score="95",
        representative=True,
    )
    _preset(
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 11),
    )
    p2 = _preset(
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 12),
        score="80",
    )
    p3 = _preset(
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 13),
        score="90",
    )
    w = _preset(
        session,
        tournament,
        school_w,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _withdraw_ok(client, captain_p, team_p["id"])

    assert _status(session, p3) == S.ACCEPTED
    assert _status(session, p2) == S.WAITLISTED
    assert _status(session, w) == S.WAITLISTED
    session.expire_all()
    assert p3.is_representative is True
    assert p3.backfilled_at == frozen_clock.now()
    assert _backfilled_ids(session, tournament) == {str(p3.id)}


def test_representative_withdraw_without_schoolmates_uses_first_come_rule(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """代表隊撤回、同校沒有候補：走一般先搶期規則（優先期學校 Q 的候補沒有資格）。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_w = (_school(session) for _ in range(3))
    _settled(session, tournament, [school_p, school_q])
    team_p, captain_p, _ = _team(
        client,
        session,
        tournament,
        school_p,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
        representative=True,
    )
    _preset(
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 11),
    )
    q2 = _preset(
        session,
        tournament,
        school_q,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 12),
    )
    w = _preset(
        session,
        tournament,
        school_w,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _withdraw_ok(client, captain_p, team_p["id"])

    assert _status(session, w) == S.ACCEPTED
    assert _status(session, q2) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(w.id)}


def test_representative_withdraw_without_eligible_waitlist_keeps_vacancy(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q = _school(session), _school(session)
    _settled(session, tournament, [school_p, school_q])
    team_p, captain_p, _ = _team(
        client,
        session,
        tournament,
        school_p,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
        representative=True,
    )
    _preset(
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 11),
    )
    q2 = _preset(
        session,
        tournament,
        school_q,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 12),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _withdraw_ok(client, captain_p, team_p["id"])

    assert _status(session, q2) == S.WAITLISTED
    assert _events(session, tournament, "RegistrationBackfilled") == []


def test_disqualified_representative_is_backfilled_before_next_submission(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """6.5 取消代表隊資格（不遞補）；之後先搶期有人送出：先由 P 校候補第一名遞補，
    再判定新送出的報名（名額已滿 → 候補）。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q = _school(session), _school(session)
    _settled(session, tournament, [school_p, school_q])
    team_p, _, rep = _team(
        client,
        session,
        tournament,
        school_p,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
        representative=True,
    )
    _preset(
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 11),
    )
    p2 = _preset(
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 12),
        score="80",
    )
    p3 = _preset(
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 13),
        score="70",
    )
    service.disqualify_registration(
        session, team_id=uuid.UUID(team_p["id"]), actor_id=tournament.organizer_id
    )
    assert _status(session, rep) == S.DISQUALIFIED
    assert _status(session, p2) == S.WAITLISTED  # 取消資格本身不遞補
    team_n, captain_n = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)

    body = _submit_ok(client, captain_n, team_n)

    assert body["registration_status"] == "waitlisted"
    assert _status(session, p2) == S.ACCEPTED
    assert _status(session, p3) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(p2.id)}
    new = _registration(session, team_n["id"])
    assert [
        e["registration_id"]
        for e in _events(session, tournament, "RegistrationAllocated")
    ] == [str(new.id)]


def test_settlement_marks_accepted_representatives(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """優先期結算把正取的代表隊記為代表隊；超過名額而候補的代表隊與非代表隊不記。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_r = (_school(session) for _ in range(3))
    rep_r = _preset(
        session,
        tournament,
        school_r,
        S.PENDING,
        submitted_at=_in_window(tournament, 4),
        score="95",
    )
    rep_p = _preset(
        session,
        tournament,
        school_p,
        S.PENDING,
        submitted_at=_in_window(tournament, 1),
        score="90",
    )
    p2 = _preset(
        session,
        tournament,
        school_p,
        S.PENDING,
        submitted_at=_in_window(tournament, 2),
        score="80",
    )
    rep_q = _preset(
        session,
        tournament,
        school_q,
        S.PENDING,
        submitted_at=_in_window(tournament, 3),
        score="70",
    )
    frozen_clock.advance(timedelta(minutes=1))

    assert service.settle_priority_window(session, tournament_id=tournament.id)

    session.expire_all()
    assert (rep_r.status, rep_r.is_representative) == (S.ACCEPTED, True)
    assert (rep_p.status, rep_p.is_representative) == (S.ACCEPTED, True)
    assert (p2.status, p2.is_representative) == (S.WAITLISTED, False)
    assert (rep_q.status, rep_q.is_representative) == (S.WAITLISTED, False)


# ---------------------------------------------------------------- 截止後的遞補


@pytest.mark.parametrize("closed", [True, False], ids=["closed", "open-past-deadline"])
def test_after_deadline_withdraw_follows_epics_example(
    client: TestClient, session: Session, frozen_clock: FrozenClock, closed: bool
) -> None:
    """名額 5 已滿：Z 校 2 隊、W1、X、Y 正取；候補 E（Z）、F（W）、G（W）、H（V）；W1 撤回
    → F 遞補；E 沒有順位（SCHOOL_LIMIT_REACHED）；G 候補第 1 位、H 第 2 位。

    H 送出最早：若誤用先搶期規則會由 H 遞補。`open-past-deadline` 是 worker 還沒把賽事
    轉為 `closed`、但已過報名截止時間的情境（依 `_current_phase` 判斷為截止後）。
    """
    tournament = _tournament(session, frozen_clock, capacity=5)
    z, w, v, x, y = (_school(session) for _ in range(5))
    _settled(session, tournament, [])
    for school, minute in ((z, 2), (z, 3), (x, 4), (y, 5)):
        _preset(
            session,
            tournament,
            school,
            S.ACCEPTED,
            submitted_at=_first_come(tournament, minute),
        )
    team_w1, captain_w1, _ = _team(
        client,
        session,
        tournament,
        w,
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 6),
    )
    team_e, captain_e, _ = _team(
        client,
        session,
        tournament,
        z,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 7),
        score="70",
    )
    f = _preset(
        session,
        tournament,
        w,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 8),
        score="60",
    )
    team_g, captain_g, _ = _team(
        client,
        session,
        tournament,
        w,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 9),
        score="50",
    )
    team_h, captain_h, h = _team(
        client,
        session,
        tournament,
        v,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
        score="40",
    )
    if closed:
        _set_status(session, tournament.id, TournamentStatus.CLOSED)
    frozen_clock.set(tournament.registration_end + timedelta(minutes=1))

    _withdraw_ok(client, captain_w1, team_w1["id"])

    assert _status(session, f) == S.ACCEPTED
    assert _status(session, h) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(f.id)}
    detail_e = _detail(client, captain_e, team_e["id"])
    assert (detail_e["waitlist_position"], detail_e["waitlist_reason"]) == (
        None,
        "SCHOOL_LIMIT_REACHED",
    )
    assert detail_e["waitlist_phase"] == "after_deadline"
    assert _detail(client, captain_g, team_g["id"])["waitlist_position"] == 1
    assert _detail(client, captain_h, team_h["id"])["waitlist_position"] == 2


# ---------------------------------------------------------------- 撤回與送出（依序）


def _race_world(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> tuple[TournamentRead, dict[str, Any], Account, dict[str, Any], Account]:
    """名額 2 已滿（A 與另一隊正取）；B 填完資料、尚未送出。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    team_a, captain_a, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    _preset(
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 2),
    )
    team_b, captain_b = _api_team(client, session, tournament, _school(session))
    frozen_clock.advance(SUBMIT_AFTER)
    return tournament, team_a, captain_a, team_b, captain_b


def _accepted_count(session: Session, tournament: TournamentRead) -> int:
    session.expire_all()
    return sum(
        1
        for r in repository.list_registrations(session, tournament.id)
        if r.status == S.ACCEPTED
    )


def test_withdraw_then_submit(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """先撤回：A 的名額沒有候補可遞補而保留，B 送出時依當下規則正取。"""
    tournament, team_a, captain_a, team_b, captain_b = _race_world(
        client, session, frozen_clock
    )

    _withdraw_ok(client, captain_a, team_a["id"])
    body = _submit_ok(client, captain_b, team_b)

    assert body["registration_status"] == "accepted"
    assert body["backfilled"] is False
    assert _accepted_count(session, tournament) == 2


def test_submit_then_withdraw(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """先送出：B 依已滿的名額成為候補；A 撤回後 B 遞補。"""
    tournament, team_a, captain_a, team_b, captain_b = _race_world(
        client, session, frozen_clock
    )

    body = _submit_ok(client, captain_b, team_b)
    assert (body["registration_status"], body["waitlist_position"]) == (
        "waitlisted",
        1,
    )
    _withdraw_ok(client, captain_a, team_a["id"])

    detail = _detail(client, captain_b, team_b["id"])
    assert (detail["registration_status"], detail["backfilled"]) == ("accepted", True)
    assert _accepted_count(session, tournament) == 2
    assert _submit(client, captain_b, team_b["id"]).status_code == 409
    assert len(_logs(session, tournament, "registration.submitted")) == 1
