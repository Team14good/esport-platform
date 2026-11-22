"""Story 3.8：主辦方退回報名、退回後重送與代表隊已退出時的候補順位（I/O 矩陣）。

前置狀態直接寫入報名列（沿用 3.5 的 `_preset`、3.7 的 `_team`），被測的退回與重送經 API。
`frozen_clock` 固定在 2026-10-18 11:00 UTC（下稱 T）；賽事報名從 T−1 小時開始、優先期
1 小時，所以優先期在 T 結束。主辦方清單與截圖下載在 test_organizer_registrations.py；
真實的並行退回在 test_settlement_concurrency.py。
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import audit
from app.modules.identity.models import Account
from app.modules.registration import repository, service
from app.modules.registration.models import (
    Registration,
    RegistrationStatus,
)
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
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
    _fill,
    _registration,
    _school,
    _submit,
)
from tests.registration.test_teams import (
    API,
    _auth,
    _error_code,
    _make_account,
    _set_status,
)
from tests.registration.test_withdraw_registration import (
    _accepted_count,
    _backfilled_ids,
    _card,
    _events,
    _race_world,
    _status,
    _team,
    _withdraw_ok,
)

S = RegistrationStatus
REASON = "段位截圖與申報段位不符"


# ---------------------------------------------------------------- 測試資料


def _organizer(session: Session, tournament: TournamentRead) -> Account:
    account = session.get(Account, tournament.organizer_id)
    assert account is not None
    return account


def _reject(
    client: TestClient,
    account: Account,
    tournament_id: Any,
    registration_id: Any,
    reason: Any = REASON,
) -> Any:
    return client.post(
        f"{API}/organizer/tournaments/{tournament_id}/registrations/"
        f"{registration_id}/rejection",
        json={"reason": reason},
        headers=_auth(account),
    )


def _reject_ok(
    client: TestClient,
    session: Session,
    tournament: TournamentRead,
    registration: Registration,
    reason: str = REASON,
) -> dict[str, Any]:
    response = _reject(
        client, _organizer(session, tournament), tournament.id, registration.id, reason
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _rejected_events(
    session: Session, tournament: TournamentRead
) -> list[dict[str, Any]]:
    return _events(session, tournament, "RegistrationRejected")


def _set_mode(session: Session, tournament_id: uuid.UUID, mode: TournamentMode) -> None:
    row = session.get(Tournament, tournament_id)
    assert row is not None
    row.mode = mode
    session.add(row)
    session.flush()


# ---------------------------------------------------------------- 退回本身


def test_reject_in_priority_window_records_reason_and_skips_settlement(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """優先期內退回（沒有結算紀錄）：轉 `rejected`、記原因；不遞補；之後結算不算這隊。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school = _school(session)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        school,
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
    organizer = _organizer(session, tournament)

    body = _reject_ok(client, session, tournament, registration, f"  {REASON}  ")

    assert body["registration_id"] == str(registration.id)
    assert body["status"] == "rejected"
    assert body["reject_reason"] == REASON
    assert body["rejectable"] is False
    session.expire_all()
    found = session.get(Registration, registration.id)
    assert found is not None
    assert (found.status, found.reject_reason) == (S.REJECTED, REASON)
    assert found.rejected_at == frozen_clock.now()
    assert _changes(session, tournament, registration.id) == [
        ("rejected", organizer.id)
    ]
    [log] = _logs(session, tournament, "registration.rejected")
    assert (log.actor_id, log.entity_id) == (organizer.id, registration.id)
    assert (log.before, log.after) == ({"status": "pending"}, {"reason": REASON})
    assert _rejected_events(session, tournament) == [
        {
            "registration_id": str(registration.id),
            "team_id": team["id"],
            "tournament_id": str(tournament.id),
            "reason": REASON,
            "can_resubmit": True,
        }
    ]
    assert _events(session, tournament, "RegistrationAllocated") == []
    assert _events(session, tournament, "RegistrationBackfilled") == []
    assert repository.get_settlement(session, tournament.id) is None
    # 優先期結算只算 pending：被退回且未重送的隊伍不參加
    frozen_clock.advance(timedelta(minutes=1))
    assert service.settle_priority_window(session, tournament_id=tournament.id)
    assert _status(session, other) == S.ACCEPTED
    assert _status(session, registration) == S.REJECTED
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert school.id not in settlement.priority_school_ids
    # 隊員看到的 S17、S12
    detail = _detail(client, captain, team["id"])
    assert (detail["registration_status"], detail["reject_reason"]) == (
        "rejected",
        REASON,
    )
    assert _card(client, captain, team["id"])["reject_reason"] == REASON


def test_reject_after_priority_end_settles_first(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """優先期已過、worker 還沒結算：先結算（被退回的隊伍算在內），再退回並依先搶期遞補。

    P 校代表隊 A（90）結算時正取後被退回 → 同校 P2（80）遞補；P 校仍是優先期學校。
    """
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q = _school(session), _school(session)
    team_a, _, registration_a = _team(
        client,
        session,
        tournament,
        school_p,
        S.PENDING,
        submitted_at=_in_window(tournament, 1),
        score="90",
    )
    q1 = _preset(
        session,
        tournament,
        school_q,
        S.PENDING,
        submitted_at=_in_window(tournament, 2),
    )
    p2 = _preset(
        session,
        tournament,
        school_p,
        S.PENDING,
        submitted_at=_in_window(tournament, 3),
        score="80",
    )
    frozen_clock.advance(SUBMIT_AFTER)
    organizer = _organizer(session, tournament)

    body = _reject_ok(client, session, tournament, registration_a)

    assert body["status"] == "rejected"
    settlement = repository.get_settlement(session, tournament.id)
    assert settlement is not None
    assert set(settlement.priority_school_ids) == {school_p.id, school_q.id}
    assert _changes(session, tournament, registration_a.id) == [
        ("accepted", None),
        ("rejected", organizer.id),
    ]
    assert _status(session, q1) == S.ACCEPTED
    assert _status(session, p2) == S.ACCEPTED
    assert _backfilled_ids(session, tournament) == {str(p2.id)}
    # 結算照常發其他隊伍的分配事件；被退回的 A 只收到退回通知（不發正取事件）
    allocated = [
        e["registration_id"]
        for e in _events(session, tournament, "RegistrationAllocated")
    ]
    assert str(registration_a.id) not in allocated
    assert set(allocated) == {str(q1.id), str(p2.id)}
    assert [e["registration_id"] for e in _rejected_events(session, tournament)] == [
        str(registration_a.id)
    ]
    session.expire_all()
    found = session.get(Registration, p2.id)
    assert found is not None and found.is_representative is True


@pytest.mark.parametrize(
    ("registration_status", "tournament_status"),
    [
        (S.FORMING, TournamentStatus.OPEN),
        (S.REJECTED, TournamentStatus.OPEN),
        (S.WITHDRAWN, TournamentStatus.OPEN),
        (S.DRAWN, TournamentStatus.PUBLISHED),
        (S.ACCEPTED, TournamentStatus.PUBLISHED),
        (S.ACCEPTED, TournamentStatus.CANCELLED),
    ],
    ids=["forming", "rejected", "withdrawn", "drawn", "published", "cancelled"],
)
def test_not_rejectable_is_rejected_without_changes(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    registration_status: S,
    tournament_status: TournamentStatus,
) -> None:
    tournament = _tournament(session, frozen_clock)
    school = _school(session)
    team, _ = _api_team(client, session, tournament, school)
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
    registration = _registration(session, team["id"])

    response = _reject(
        client, _organizer(session, tournament), tournament.id, registration.id
    )

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_NOT_REJECTABLE"
    registration = _registration(session, team["id"])
    assert registration.status == registration_status
    assert registration.reject_reason is None
    assert _changes(session, tournament, registration.id) == []
    assert _logs(session, tournament, "registration.rejected") == []
    assert _rejected_events(session, tournament) == []


@pytest.mark.parametrize("reason", ["", "   ", "字" * 201, None, 3])
def test_reason_is_required_and_limited(
    client: TestClient, session: Session, frozen_clock: FrozenClock, reason: Any
) -> None:
    tournament = _tournament(session, frozen_clock)
    _, _, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )

    response = _reject(
        client, _organizer(session, tournament), tournament.id, registration.id, reason
    )

    assert response.status_code == 422
    assert _status(session, registration) == S.PENDING


def test_reason_of_200_characters_is_accepted(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _, _, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )

    body = _reject_ok(client, session, tournament, registration, "字" * 200)

    assert body["reject_reason"] == "字" * 200


def test_registration_of_another_tournament_is_404_without_changes(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """主辦方以自己的賽事路徑帶他賽事的報名 id：404，不改資料。"""
    mine = _tournament(session, frozen_clock)
    other = _tournament(session, frozen_clock)
    _, _, registration = _team(
        client,
        session,
        other,
        _school(session),
        S.ACCEPTED,
        submitted_at=_in_window(other, 10),
    )

    response = _reject(client, _organizer(session, mine), mine.id, registration.id)

    assert response.status_code == 404
    assert _error_code(response) == "REGISTRATION_NOT_FOUND"
    assert _status(session, registration) == S.ACCEPTED
    missing = _reject(client, _organizer(session, mine), mine.id, uuid.uuid4())
    assert missing.status_code == 404
    assert (
        _reject(
            client, _organizer(session, mine), uuid.uuid4(), registration.id
        ).status_code
        == 404
    )


def test_non_organizer_cannot_reject(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    other_organizer = _organizer(session, _tournament(session, frozen_clock))

    for account in (captain, _make_account(session), other_organizer):
        response = _reject(client, account, tournament.id, registration.id)
        assert response.status_code == 403
    assert _error_code(
        _reject(client, other_organizer, tournament.id, registration.id)
    ) == ("TOURNAMENT_OWNER_REQUIRED")
    assert _status(session, registration) == S.PENDING


# ---------------------------------------------------------------- 先搶期的遞補


def test_first_come_reject_accepted_backfills_waitlist(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """名額 2 已滿；非代表隊的正取 A 被退回；候補 B（符合規則）遞補。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    _, _, registration_a = _team(
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
    team_b, captain_b, waiting_b = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    frozen_clock.advance(SUBMIT_AFTER)
    organizer = _organizer(session, tournament)

    _reject_ok(client, session, tournament, registration_a)

    assert _status(session, registration_a) == S.REJECTED
    assert _status(session, waiting_b) == S.ACCEPTED
    session.expire_all()
    assert waiting_b.backfilled_at == frozen_clock.now()
    assert _backfilled_ids(session, tournament) == {str(waiting_b.id)}
    assert _events(session, tournament, "RegistrationAllocated") == []
    # 遞補緊接在主辦方退回之後（同一交易）
    assert [
        (log.entity_id, log.actor_id, log.action)
        for log in audit.list_for_tournament(session, tournament.id)[-3:]
    ] == [
        (registration_a.id, organizer.id, "registration.status_changed"),
        (registration_a.id, organizer.id, "registration.rejected"),
        (waiting_b.id, None, "registration.status_changed"),
    ]
    detail = _detail(client, captain_b, team_b["id"])
    assert (detail["registration_status"], detail["backfilled"]) == ("accepted", True)


def test_first_come_reject_representative_backfills_same_school(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """P 校代表隊被退回；同校候補 P2（80）、P3（90）→ P3 遞補並記為代表隊。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_w = (_school(session) for _ in range(3))
    _settled(session, tournament, [school_p, school_q])
    _, _, rep = _team(
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

    _reject_ok(client, session, tournament, rep)

    assert _status(session, p3) == S.ACCEPTED
    assert _status(session, p2) == S.WAITLISTED
    assert _status(session, w) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(p3.id)}
    session.expire_all()
    found = session.get(Registration, p3.id)
    assert found is not None and found.is_representative is True


def test_rejected_representative_resubmits_and_is_backfilled_by_same_school(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """P 校代表隊被退回、當時沒有同校候補，空位由他校 W 遞補；P 修正後重送 → 候補第 1 位
    （已退出代表隊的第 1 群，排在更早送出的 X 之前）；之後名額釋出時由 P 同校遞補。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_w, school_x = (_school(session) for _ in range(4))
    _settled(session, tournament, [school_p, school_q])
    team_p, captain_p, rep = _team(
        client,
        session,
        tournament,
        school_p,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 10),
        representative=True,
    )
    team_q, captain_q, _ = _team(
        client,
        session,
        tournament,
        school_q,
        S.ACCEPTED,
        submitted_at=_in_window(tournament, 11),
    )
    w = _preset(
        session,
        tournament,
        school_w,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
    )
    x = _preset(
        session,
        tournament,
        school_x,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 2),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _reject_ok(client, session, tournament, rep)
    assert _status(session, w) == S.ACCEPTED
    detail = _detail(client, captain_p, team_p["id"])
    assert detail["profile_editable"] is True
    assert detail["submit_blockers"] == []

    body = _submit_ok(client, captain_p, team_p)

    assert body["registration_status"] == "waitlisted"
    assert (body["waitlist_position"], body["representative_backfill"]) == (1, True)
    assert body["reject_reason"] is None
    session.expire_all()
    found = session.get(Registration, rep.id)
    assert found is not None
    assert found.is_representative is True
    assert found.reject_reason == REASON  # 仍留在資料庫
    assert _status(session, x) == S.WAITLISTED

    _withdraw_ok(client, captain_q, team_q["id"])

    assert _status(session, rep) == S.ACCEPTED
    assert _status(session, x) == S.WAITLISTED
    assert str(rep.id) in _backfilled_ids(session, tournament)


def test_reject_waitlisted_does_not_backfill_and_updates_positions(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
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
    _, _, waiting_b = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 2),
    )
    team_c, captain_c, waiting_c = _team(
        client,
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 3),
    )
    frozen_clock.advance(SUBMIT_AFTER)
    assert _detail(client, captain_c, team_c["id"])["waitlist_position"] == 2

    _reject_ok(client, session, tournament, waiting_b)

    assert _status(session, accepted) == S.ACCEPTED
    assert _status(session, waiting_c) == S.WAITLISTED
    assert _events(session, tournament, "RegistrationBackfilled") == []
    assert _detail(client, captain_c, team_c["id"])["waitlist_position"] == 1


def test_disqualified_representative_positions_match_actual_backfill(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """6.5 取消代表隊（不遞補）後：P3 候補第 1 位（同校遞補）、X 第 2 位、P2 沒有順位；
    下一次送出時 P3 先遞補（順位與實際遞補一致）。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    school_p, school_q, school_x = (_school(session) for _ in range(3))
    _settled(session, tournament, [school_p, school_q])
    team_rep, _, rep = _team(
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
    team_p2, captain_p2, p2 = _team(
        client,
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 12),
        score="80",
    )
    team_p3, captain_p3, p3 = _team(
        client,
        session,
        tournament,
        school_p,
        S.WAITLISTED,
        submitted_at=_in_window(tournament, 13),
        score="90",
    )
    team_x, captain_x, x = _team(
        client,
        session,
        tournament,
        school_x,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
    )
    service.disqualify_registration(
        session, team_id=uuid.UUID(team_rep["id"]), actor_id=tournament.organizer_id
    )
    assert _status(session, rep) == S.DISQUALIFIED
    frozen_clock.advance(SUBMIT_AFTER)

    detail_p3 = _detail(client, captain_p3, team_p3["id"])
    assert (
        detail_p3["waitlist_position"],
        detail_p3["representative_backfill"],
        detail_p3["waitlist_reason"],
    ) == (1, True, None)
    detail_x = _detail(client, captain_x, team_x["id"])
    assert (detail_x["waitlist_position"], detail_x["representative_backfill"]) == (
        2,
        False,
    )
    detail_p2 = _detail(client, captain_p2, team_p2["id"])
    assert (detail_p2["waitlist_position"], detail_p2["waitlist_reason"]) == (
        None,
        "SCHOOL_NOT_ELIGIBLE",
    )
    card_p3 = _card(client, captain_p3, team_p3["id"])
    assert (card_p3["waitlist_position"], card_p3["representative_backfill"]) == (
        1,
        True,
    )

    team_n, captain_n = _api_team(client, session, tournament, _school(session))
    body = _submit_ok(client, captain_n, team_n)

    assert body["registration_status"] == "waitlisted"
    assert _status(session, p3) == S.ACCEPTED
    assert _status(session, p2) == S.WAITLISTED
    assert _status(session, x) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(p3.id)}


# ---------------------------------------------------------------- 截止後與自訂模式


def test_after_deadline_reject_follows_school_limit_and_blocks_resubmit(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """`closed`、名額 3 已滿（Z 校 2 隊、W1）；候補 E（Z，70）、H（V，40，最早送出）；
    W1 被退回 → 依截止後規則 E 會使 Z 校超過 2 隊而略過，H 遞補。不可重送。"""
    tournament = _tournament(session, frozen_clock, capacity=3)
    z, w, v = (_school(session) for _ in range(3))
    _settled(session, tournament, [])
    for minute in (2, 3):
        _preset(
            session,
            tournament,
            z,
            S.ACCEPTED,
            submitted_at=_first_come(tournament, minute),
        )
    team_w1, captain_w1, w1 = _team(
        client,
        session,
        tournament,
        w,
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 4),
    )
    e = _preset(
        session,
        tournament,
        z,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 5),
        score="70",
    )
    h = _preset(
        session,
        tournament,
        v,
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 1),
        score="40",
    )
    _set_status(session, tournament.id, TournamentStatus.CLOSED)
    frozen_clock.set(tournament.registration_end + timedelta(minutes=1))

    body = _reject_ok(client, session, tournament, w1)

    assert body["status"] == "rejected"
    assert _status(session, h) == S.ACCEPTED
    assert _status(session, e) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(h.id)}
    [event] = _rejected_events(session, tournament)
    assert event["can_resubmit"] is False
    detail = _detail(client, captain_w1, team_w1["id"])
    assert detail["profile_editable"] is False
    assert [b["code"] for b in detail["submit_blockers"]][0] == "REGISTRATION_CLOSED"
    response = _submit(client, captain_w1, team_w1["id"])
    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert _status(session, w1) == S.REJECTED


def test_reject_after_registration_end_before_close_cannot_resubmit(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """報名截止時間已到、worker 還沒把賽事轉 `closed`（仍為 `open`）時退回：
    通知為不可重送（`can_resubmit=False`），重送得到 409 `REGISTRATION_CLOSED`。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    frozen_clock.set(tournament.registration_end)

    body = _reject_ok(client, session, tournament, registration)

    assert body["status"] == "rejected"
    [event] = _rejected_events(session, tournament)
    assert event["can_resubmit"] is False
    response = _submit(client, captain, team["id"])
    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert _status(session, registration) == S.REJECTED


def test_custom_mode_reject_does_not_backfill(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=2)
    _set_mode(session, tournament.id, TournamentMode.CUSTOM)
    _, _, accepted = _team(
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
        submitted_at=_first_come(tournament, 1),
    )
    waiting = _preset(
        session,
        tournament,
        _school(session),
        S.WAITLISTED,
        submitted_at=_first_come(tournament, 2),
    )
    frozen_clock.advance(SUBMIT_AFTER)

    _reject_ok(client, session, tournament, accepted)

    assert _status(session, accepted) == S.REJECTED
    assert _status(session, waiting) == S.WAITLISTED
    assert repository.get_settlement(session, tournament.id) is None
    assert _events(session, tournament, "RegistrationBackfilled") == []


# ---------------------------------------------------------------- 退回後的名單與重送


def test_rejected_roster_is_unlocked(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """退回後：S17、S12 顯示退回與原因；可改參賽資料、可邀請（未滿時）、可加入。"""
    tournament = _tournament(session, frozen_clock, substitutes=1)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    locked = _detail(client, captain, team["id"])
    assert (locked["invite_status"], locked["profile_editable"]) == ("locked", False)

    _reject_ok(client, session, tournament, registration)

    detail = _detail(client, captain, team["id"])
    assert detail["registration_status"] == "rejected"
    assert detail["reject_reason"] == REASON
    assert detail["invite_status"] == "active"
    assert detail["profile_editable"] is True
    assert detail["submit_blockers"] == []
    assert detail["withdrawable"] is False
    card = _card(client, captain, team["id"])
    assert (card["registration_status"], card["reject_reason"]) == ("rejected", REASON)
    preview = client.get(f"{API}/team-invites/{team['invite_token']}")
    assert preview.json()["invite_status"] == "active"
    player = _make_account(session, display_name="新隊員")
    joined = client.post(
        f"{API}/team-invites/{team['invite_token']}/members", headers=_auth(player)
    )
    assert joined.status_code == 200, joined.text
    profile = client.put(
        f"{API}/teams/{team['id']}/members/me/profile",
        data={"game_account_id": "NEW-ID", "rank_tier": "鑽石"},
        headers=_auth(captain),
    )
    assert profile.status_code == 200, profile.text


def test_resubmit_in_priority_window_rewrites_snapshot(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """退回後重送（優先期內）：`rejected → forming → pending`，三個快照重寫、遞補時間清掉。"""
    tournament = _tournament(session, frozen_clock)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
        score="99",
    )
    _reject_ok(client, session, tournament, registration)
    session.expire_all()
    registration = _registration(session, team["id"])
    registration.backfilled_at = frozen_clock.now()
    session.add(registration)
    session.flush()
    # 時鐘停在優先期最後一刻（T），重送仍在優先期內
    _fill(session, team["id"], captain, rank_score=40)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "pending"
    assert body["reject_reason"] is None
    assert body["submitted_at"] is not None
    session.expire_all()
    found = _registration(session, team["id"])
    assert found.avg_rank_score == Decimal("40.00")
    assert found.submitted_at == frozen_clock.now()
    assert found.backfilled_at is None
    assert found.reject_reason == REASON
    assert _changes(session, tournament, found.id) == [
        ("rejected", tournament.organizer_id),
        ("forming", captain.id),
        ("pending", captain.id),
    ]
    assert _card(client, captain, team["id"])["reject_reason"] is None


def test_resubmit_in_first_come_is_allocated_on_the_spot(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """退回後重送（先搶期）：依先搶期當下判定；非優先期學校、有空位 → 正取。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _settled(session, tournament, [])
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.ACCEPTED,
        submitted_at=_first_come(tournament, 1),
    )
    frozen_clock.advance(SUBMIT_AFTER)
    _reject_ok(client, session, tournament, registration)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "accepted"
    assert body["backfilled"] is False
    allocated = _events(session, tournament, "RegistrationAllocated")
    assert [(e["registration_id"], e["status"]) for e in allocated] == [
        (str(registration.id), "accepted")
    ]


# ---------------------------------------------------------------- 退回與送出（依序）


def test_reject_then_submit(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """先退回：A 的名額沒有候補可遞補而保留，B 送出時依當下規則正取，不超收。"""
    tournament, team_a, _, team_b, captain_b = _race_world(
        client, session, frozen_clock
    )

    _reject_ok(client, session, tournament, _registration(session, team_a["id"]))
    body = _submit_ok(client, captain_b, team_b)

    assert body["registration_status"] == "accepted"
    assert _accepted_count(session, tournament) == 2


def test_submit_then_reject(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """先送出：B 依已滿的名額成為候補；A 被退回後 B 遞補，不超收。"""
    tournament, team_a, _, team_b, captain_b = _race_world(
        client, session, frozen_clock
    )

    body = _submit_ok(client, captain_b, team_b)
    assert body["registration_status"] == "waitlisted"
    _reject_ok(client, session, tournament, _registration(session, team_a["id"]))

    detail = _detail(client, captain_b, team_b["id"])
    assert (detail["registration_status"], detail["backfilled"]) == ("accepted", True)
    assert _accepted_count(session, tournament) == 2
