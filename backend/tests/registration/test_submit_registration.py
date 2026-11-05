"""Story 3.3：送出報名與鎖定名單（I/O 矩陣、檢查順序、快照、截止邊界、併發）。

參賽資料直接寫進 team_member（填資料的 API 由 `test_player_profile_api.py` 測試），
學校直接設定在帳號上。平行送出用多條連線、多執行緒，寫法比照 `test_team_concurrency.py`。
"""

import threading
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import Session, col

from app.core import authz, clock
from app.core.db import engine
from app.core.errors import BusinessError
from app.modules.identity import service as identity_service
from app.modules.identity.models import Account, School
from app.modules.registration import player_profile, repository, service
from app.modules.registration.models import (
    MemberRole,
    Registration,
    RegistrationStatus,
    Team,
    TeamMember,
)
from app.modules.registration.player_profile import RosterEntry
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.helpers import make_account, make_game, make_tournament
from tests.registration import test_team_concurrency, test_teams
from tests.registration.test_teams import (
    API,
    LockSpy,
    _audit,
    _auth,
    _create,
    _create_ok,
    _error_code,
    _join,
    _make_account,
    _set_status,
    _tournament,
)

# 共用 3.1 的 fixture：包住真實的 lock_tournament
lock_spy = test_teams.lock_spy

SCREENSHOT_KEY = f"{'a' * 32}.png"


# ---------------------------------------------------------------- 測試資料


def _school(session: Session, name: str | None = None) -> School:
    school = School(name=name or f"測試大學-{uuid.uuid4().hex[:8]}")
    session.add(school)
    session.flush()
    return school


def _set_school(session: Session, account: Account, school: School | None) -> None:
    account.school_id = None if school is None else school.id
    session.add(account)
    session.flush()


def _fill(
    session: Session,
    team_id: Any,
    account: Account,
    *,
    rank_tier: str = "鑽石",
    rank_score: int = 30,
) -> None:
    """直接寫入完整的參賽資料。"""
    member = repository.get_team_member(session, uuid.UUID(str(team_id)), account.id)
    assert member is not None
    member.game_account_id = f"ID-{account.display_name}"
    member.rank_tier = rank_tier
    member.rank_score = rank_score
    member.rank_screenshot_key = SCREENSHOT_KEY
    member.rank_screenshot_name = "rank.png"
    session.add(member)
    session.flush()


def _team(
    client: TestClient,
    session: Session,
    *,
    names: list[str],
    school: School | None = None,
    fill: bool = True,
    **tournament_overrides: Any,
) -> tuple[dict[str, Any], list[Account]]:
    """建立隊伍：`names[0]` 是隊長，其餘依序加入；預設全員同校且填完資料。"""
    school = school or _school(session)
    tournament = _tournament(session, **tournament_overrides)
    accounts = [_make_account(session, display_name=name) for name in names]
    team = _create_ok(client, accounts[0], tournament.id)
    for account in accounts[1:]:
        response = _join(client, account, team["invite_token"])
        assert response.status_code == 200, response.text
    for account in accounts:
        _set_school(session, account, school)
        if fill:
            _fill(session, team["id"], account)
    return team, accounts


FIVE = ["阿哲", "小芸", "阿凱", "小安", "阿宏"]


def _submit(client: TestClient, account: Account, team_id: Any) -> Any:
    return client.post(f"{API}/teams/{team_id}/submission", headers=_auth(account))


def _detail(client: TestClient, account: Account, team_id: Any) -> dict[str, Any]:
    response = client.get(f"{API}/teams/{team_id}", headers=_auth(account))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _registration(session: Session, team_id: Any) -> Registration:
    session.expire_all()
    registration = repository.get_registration_by_team(session, uuid.UUID(str(team_id)))
    assert registration is not None
    return registration


def _unmet(response: Any) -> str:
    assert response.status_code == 409, response.text
    assert _error_code(response) == "REGISTRATION_REQUIREMENTS_UNMET"
    return str(response.json()["detail"]["message"])


def _blockers(detail: dict[str, Any]) -> list[tuple[str, str]]:
    return [(b["code"], b["message"]) for b in detail["submit_blockers"]]


# ---------------------------------------------------------------- 送出成功


def test_submit_moves_to_pending_and_freezes_snapshots(
    client: TestClient,
    session: Session,
    lock_spy: LockSpy,
    frozen_clock: FrozenClock,
) -> None:
    school = _school(session)
    team, accounts = _team(client, session, names=FIVE, school=school)
    captain = accounts[0]
    before = _detail(client, captain, team["id"])
    assert before["submit_blockers"] == []
    assert before["submitted_at"] is None
    frozen_clock.advance(timedelta(minutes=5))
    lock_spy.locked.clear()

    response = _submit(client, captain, team["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["registration_status"] == "pending"
    assert body["invite_status"] == "locked"
    assert body["submit_blockers"] == []
    assert body["profile_editable"] is False
    assert datetime.fromisoformat(body["submitted_at"]) == frozen_clock.now()
    tournament_id = uuid.UUID(team["tournament_id"])
    assert lock_spy.locked == [tournament_id]

    registration = _registration(session, team["id"])
    assert registration.status == RegistrationStatus.PENDING
    assert registration.school_id == school.id
    assert registration.avg_rank_score == Decimal("30.00")
    assert registration.submitted_at == frozen_clock.now()

    read = service.get_registration(session, team_id=uuid.UUID(team["id"]))
    assert (read.school_id, read.avg_rank_score, read.submitted_at) == (
        school.id,
        Decimal("30.00"),
        frozen_clock.now(),
    )

    [submitted] = _audit(session, "registration.submitted", tournament_id)
    assert submitted.actor_id == captain.id
    assert submitted.entity_type == "registration"
    assert submitted.entity_id == registration.id
    assert submitted.after is not None
    assert submitted.after["school_id"] == str(school.id)
    assert submitted.after["avg_rank_score"] == "30.00"
    assert datetime.fromisoformat(submitted.after["submitted_at"]) == (
        frozen_clock.now()
    )
    [changed] = _audit(session, "registration.status_changed", tournament_id)
    assert (changed.before, changed.after) == (
        {"status": "forming"},
        {"status": "pending"},
    )


def test_submitted_team_shows_priority_and_deadline_times(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE, priority_hours=48)
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))

    body = _submit(client, accounts[0], team["id"]).json()

    assert datetime.fromisoformat(body["priority_end"]) == tournament.priority_end
    assert (
        datetime.fromisoformat(body["registration_end"]) == tournament.registration_end
    )


def test_snapshot_average_includes_substitutes(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(
        client, session, names=["阿哲", "小芸", "阿凱"], starters=2, substitutes=1
    )
    _fill(session, team["id"], accounts[2], rank_tier="黃金", rank_score=10)

    assert _submit(client, accounts[0], team["id"]).status_code == 200

    # (30 + 30 + 10) / 3 = 23.333… → 23.33
    assert _registration(session, team["id"]).avg_rank_score == Decimal("23.33")


def test_snapshot_average_rounds_half_up(client: TestClient, session: Session) -> None:
    names = [f"選手{i}" for i in range(8)]
    team, accounts = _team(client, session, names=names, starters=1, substitutes=7)
    _fill(session, team["id"], accounts[0], rank_score=1)
    for account in accounts[1:]:
        _fill(session, team["id"], account, rank_score=0)

    assert _submit(client, accounts[0], team["id"]).status_code == 200

    # 1 / 8 = 0.125 → 0.13（銀行家捨入會是 0.12）
    assert _registration(session, team["id"]).avg_rank_score == Decimal("0.13")


def test_snapshot_average_of_huge_scores_does_not_overflow(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(
        client, session, names=["阿哲", "小芸"], starters=2, substitutes=0
    )
    top = 2_147_483_647
    _fill(session, team["id"], accounts[0], rank_score=top)
    _fill(session, team["id"], accounts[1], rank_score=top - 1)

    assert _submit(client, accounts[0], team["id"]).status_code == 200

    assert _registration(session, team["id"]).avg_rank_score == Decimal("2147483646.50")


def test_snapshot_school_does_not_follow_later_account_changes(
    client: TestClient, session: Session
) -> None:
    school = _school(session)
    team, accounts = _team(client, session, names=FIVE, school=school)
    assert _submit(client, accounts[0], team["id"]).status_code == 200

    _set_school(session, accounts[1], _school(session))
    detail = _detail(client, accounts[0], team["id"])

    assert _registration(session, team["id"]).school_id == school.id
    assert detail["submit_blockers"] == []


# ---------------------------------------------------------------- 送出條件


def test_starters_not_met(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE[:4])

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "還差 1 人才達先發人數（5 人）"
    assert _blockers(_detail(client, accounts[0], team["id"])) == [
        ("STARTERS_NOT_MET", message)
    ]
    assert _registration(session, team["id"]).status == RegistrationStatus.FORMING


def test_profile_incomplete_lists_names_in_join_order(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE, fill=False)
    for account in (accounts[0], accounts[3], accounts[4]):
        _fill(session, team["id"], account)
    # 阿凱只填一部分也算未填完
    member = repository.get_team_member(session, uuid.UUID(team["id"]), accounts[2].id)
    assert member is not None
    member.game_account_id = "Kai#1"
    session.add(member)
    session.flush()

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "尚未填完參賽資料：小芸、阿凱"
    assert _blockers(_detail(client, accounts[0], team["id"])) == [
        ("PROFILE_INCOMPLETE", message)
    ]


def test_rank_tier_without_score_counts_as_incomplete(
    client: TestClient, session: Session
) -> None:
    """只有段位、沒有積分（示範資料、手動匯入）也擋在送出條件，不會在算平均時 500。"""
    team, accounts = _team(client, session, names=FIVE)
    member = repository.get_team_member(session, uuid.UUID(team["id"]), accounts[2].id)
    assert member is not None
    member.rank_score = None
    session.add(member)
    session.flush()

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "尚未填完參賽資料：阿凱"


def test_school_missing(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE)
    _set_school(session, accounts[2], None)

    message = _unmet(_submit(client, accounts[0], team["id"]))

    # 其餘同校：只列沒設學校的人
    assert message == "尚未設定學校：阿凱"
    assert _blockers(_detail(client, accounts[0], team["id"])) == [
        ("SCHOOL_MISSING", message)
    ]


def test_school_mismatch(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE)
    _set_school(session, accounts[4], _school(session))

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "隊員的學校不一致"
    assert _blockers(_detail(client, accounts[0], team["id"])) == [
        ("SCHOOL_MISMATCH", message)
    ]


def test_school_missing_and_mismatch_are_both_listed(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    _set_school(session, accounts[1], None)
    _set_school(session, accounts[4], _school(session))

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "尚未設定學校：小芸；隊員的學校不一致"


def test_every_unmet_requirement_is_listed_in_fixed_order(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE[:3], fill=False)
    _fill(session, team["id"], accounts[0])
    _set_school(session, accounts[2], None)
    _set_school(session, accounts[0], _school(session))

    response = _submit(client, accounts[0], team["id"])
    detail = _detail(client, accounts[0], team["id"])

    expected = [
        ("STARTERS_NOT_MET", "還差 2 人才達先發人數（5 人）"),
        ("PROFILE_INCOMPLETE", "尚未填完參賽資料：小芸、阿凱"),
        ("SCHOOL_MISSING", "尚未設定學校：阿凱"),
        ("SCHOOL_MISMATCH", "隊員的學校不一致"),
    ]
    assert _blockers(detail) == expected
    # 伺服器拒絕的文字與畫面上的停用原因出自同一份規則
    assert _unmet(response) == "；".join(message for _, message in expected)


def test_non_captain_member_sees_the_same_blockers(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE[:4])

    detail = _detail(client, accounts[1], team["id"])

    assert detail["my_role"] == "player"
    assert _blockers(detail) == [("STARTERS_NOT_MET", "還差 1 人才達先發人數（5 人）")]


# ---------------------------------------------------------------- 權限與狀態


def test_non_captain_cannot_submit(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE)

    response = _submit(client, accounts[1], team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_CAPTAIN_REQUIRED"
    assert response.json()["detail"]["message"] == "只有隊長可以送出報名"
    assert _registration(session, team["id"]).status == RegistrationStatus.FORMING


def test_non_member_cannot_submit(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    team, _ = _team(client, session, names=FIVE)
    lock_spy.locked.clear()

    response = _submit(client, _make_account(session), team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_MEMBER_REQUIRED"
    # 先鎖再檢查隊員
    assert lock_spy.locked == [uuid.UUID(team["tournament_id"])]


def test_unknown_team_is_404_without_locking(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    response = _submit(client, _make_account(session), uuid.uuid4())

    assert response.status_code == 404
    assert _error_code(response) == "TEAM_NOT_FOUND"
    assert lock_spy.locked == []


def test_submit_requires_login_and_verified_email(
    client: TestClient, session: Session
) -> None:
    team, _ = _team(client, session, names=FIVE)
    unverified = _make_account(session, verified=False)

    anonymous = client.post(f"{API}/teams/{team['id']}/submission")
    not_verified = _submit(client, unverified, team["id"])

    assert anonymous.status_code == 401
    assert not_verified.status_code == 403


def test_submitting_twice_is_rejected(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE)
    assert _submit(client, accounts[0], team["id"]).status_code == 200

    response = _submit(client, accounts[0], team["id"])

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_ALREADY_SUBMITTED"
    assert response.json()["detail"]["message"] == "這支隊伍已送出報名"
    tournament_id = uuid.UUID(team["tournament_id"])
    assert len(_audit(session, "registration.submitted", tournament_id)) == 1


def test_tournament_not_open_rejects_submission(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    response = _submit(client, accounts[0], team["id"])
    detail = _detail(client, accounts[0], team["id"])

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert _blockers(detail) == [("REGISTRATION_CLOSED", "已截止")]


def test_check_order_member_then_captain_then_period_then_status(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE[:2])
    assert _unmet(_submit(client, accounts[0], team["id"]))
    registration = _registration(session, team["id"])
    registration.status = RegistrationStatus.PENDING
    session.add(registration)
    session.flush()
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    # 非隊員、非隊長的錯誤優先於報名期間
    assert _error_code(_submit(client, _make_account(session), team["id"])) == (
        "TEAM_MEMBER_REQUIRED"
    )
    assert _error_code(_submit(client, accounts[1], team["id"])) == (
        "TEAM_CAPTAIN_REQUIRED"
    )
    # 報名期間優先於已送出
    assert _error_code(_submit(client, accounts[0], team["id"])) == (
        "REGISTRATION_CLOSED"
    )
    # 已送出優先於送出條件（人數仍不足）
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.OPEN)
    assert _error_code(_submit(client, accounts[0], team["id"])) == (
        "REGISTRATION_ALREADY_SUBMITTED"
    )


def test_submit_uses_the_value_returned_by_lock_tournament(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    # 鎖住後讀到的最新值：先發已改成 6 人
    lock_spy.override = lambda locked: locked.model_copy(update={"starters": 6})

    message = _unmet(_submit(client, accounts[0], team["id"]))

    assert message == "還差 1 人才達先發人數（6 人）"


# ---------------------------------------------------------------- 名單鎖定


def test_locked_roster_rejects_join_and_invalidates_invite(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    assert _submit(client, accounts[0], team["id"]).status_code == 200
    newcomer = _make_account(session)

    response = _join(client, newcomer, team["invite_token"])
    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()

    assert response.status_code == 409
    assert _error_code(response) == "ROSTER_LOCKED"
    assert response.json()["detail"]["message"] == "名單已鎖定，無法加入。"
    assert preview["invite_status"] == "locked"
    assert repository.count_members(session, uuid.UUID(team["id"])) == 5


def test_join_reads_registration_status_after_locking(
    client: TestClient,
    session: Session,
    lock_spy: LockSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """送出與加入同時發生時，加入一定看到送出後的狀態：鎖之後才讀報名。"""
    tournament = _tournament(session)
    team = _create_ok(client, _make_account(session), tournament.id)
    original = repository.get_registration_by_team

    def wrapped(*args: Any) -> Any:
        lock_spy.events.append("get_registration_by_team")
        return original(*args)

    monkeypatch.setattr(repository, "get_registration_by_team", wrapped)
    lock_spy.events.clear()

    assert _join(client, _make_account(session), team["invite_token"]).status_code == (
        200
    )

    assert lock_spy.events[0] == "lock"
    assert "get_registration_by_team" in lock_spy.events


def test_invite_is_closed_after_the_deadline(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    team, accounts = _team(client, session, names=FIVE[:2], starters=1, substitutes=1)
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    preview_url = f"{API}/team-invites/{team['invite_token']}"
    # 額滿（2／2 人）且未截止：full
    assert _detail(client, accounts[0], team["id"])["invite_status"] == "full"

    frozen_clock.set(tournament.registration_end)

    # 已截止優先於額滿
    assert _detail(client, accounts[0], team["id"])["invite_status"] == "closed"
    assert client.get(preview_url).json()["invite_status"] == "closed"


def test_invite_is_closed_when_tournament_not_open(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE[:1])
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    assert _detail(client, accounts[0], team["id"])["invite_status"] == "closed"
    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()
    assert preview["invite_status"] == "closed"


def test_locked_takes_precedence_over_closed(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    assert _submit(client, accounts[0], team["id"]).status_code == 200

    frozen_clock.set(tournament.registration_end)

    assert _detail(client, accounts[0], team["id"])["invite_status"] == "locked"


def test_locked_takes_precedence_over_full(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE[:2], starters=1, substitutes=1)
    assert _detail(client, accounts[0], team["id"])["invite_status"] == "full"

    assert _submit(client, accounts[0], team["id"]).status_code == 200
    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()
    response = _join(client, _make_account(session), team["invite_token"])

    assert preview["invite_status"] == "locked"
    assert _error_code(response) == "ROSTER_LOCKED"


def test_locked_roster_rejects_profile_changes(
    client: TestClient, session: Session
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    assert _submit(client, accounts[0], team["id"]).status_code == 200

    response = client.put(
        f"{API}/teams/{team['id']}/members/me/profile",
        data={"game_account_id": "New#1", "rank_tier": "黃金"},
        headers=_auth(accounts[1]),
    )

    assert response.status_code == 409
    assert _error_code(response) == "ROSTER_LOCKED"


# ---------------------------------------------------------------- 報名截止


def test_submit_one_second_before_deadline_succeeds(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    team, accounts = _team(client, session, names=FIVE)
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    frozen_clock.set(tournament.registration_end - timedelta(seconds=1))

    assert _detail(client, accounts[0], team["id"])["submit_blockers"] == []
    assert _submit(client, accounts[0], team["id"]).status_code == 200


def test_submit_at_deadline_is_closed(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    team, accounts = _team(client, session, names=FIVE[:4])
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    frozen_clock.set(tournament.registration_end)

    response = _submit(client, accounts[0], team["id"])
    detail = _detail(client, accounts[0], team["id"])

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert response.json()["detail"]["message"] == "這場賽事的報名已截止。"
    # 已截止排在最前面，其餘原因照常列出
    assert _blockers(detail) == [
        ("REGISTRATION_CLOSED", "已截止"),
        ("STARTERS_NOT_MET", "還差 1 人才達先發人數（5 人）"),
    ]
    assert detail["profile_editable"] is False


def test_submit_crossing_the_deadline_uses_one_time_for_check_and_snapshot(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """截止前一刻送出、中間的查詢跨過截止：檢查與 `submitted_at` 用同一個時間。

    直接呼叫 service（不經 API，避免登入驗證等其他程式先取時間）；`clock.now()`
    第一次回傳截止前 1 微秒、之後一律截止後 1 微秒。改回兩次取時間時，
    `submitted_at` 會晚於報名截止時間而失敗。
    """
    team, accounts = _team(client, session, names=FIVE)
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    before = tournament.registration_end - timedelta(microseconds=1)
    after = tournament.registration_end + timedelta(microseconds=1)
    calls: list[datetime] = []

    def _crossing_now() -> datetime:
        calls.append(before if not calls else after)
        return calls[-1]

    monkeypatch.setattr(clock, "now", _crossing_now)

    service.submit_registration(
        session, team_id=uuid.UUID(team["id"]), account_id=accounts[0].id
    )

    registration = _registration(session, team["id"])
    assert registration.status == RegistrationStatus.PENDING
    assert registration.submitted_at == before
    assert registration.submitted_at < tournament.registration_end
    [submitted] = _audit(session, "registration.submitted", tournament.id)
    assert submitted.after is not None
    assert datetime.fromisoformat(submitted.after["submitted_at"]) == before


def test_profile_editable_until_the_deadline(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    team, accounts = _team(client, session, names=FIVE[:1])
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))

    frozen_clock.set(tournament.registration_end - timedelta(seconds=1))
    editable = _detail(client, accounts[0], team["id"])["profile_editable"]
    frozen_clock.set(tournament.registration_end)
    closed = _detail(client, accounts[0], team["id"])["profile_editable"]

    assert (editable, closed) == (True, False)


def test_create_join_and_profile_are_closed_after_the_deadline(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session)
    captain = _make_account(session)
    team = _create_ok(client, captain, tournament.id)
    frozen_clock.set(tournament.registration_end)

    create = _create(client, _make_account(session), tournament.id, "晚到隊")
    join = _join(client, _make_account(session), team["invite_token"])
    profile = client.put(
        f"{API}/teams/{team['id']}/members/me/profile",
        data={"game_account_id": "Late#1", "rank_tier": "鑽石"},
        headers=_auth(captain),
    )

    for response in (create, join, profile):
        assert response.status_code == 409, response.text
        assert _error_code(response) == "REGISTRATION_CLOSED"


def test_join_after_submit_and_deadline_says_roster_locked(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """已送出又已截止：加入與預覽都以名單鎖定為準（locked > closed）。"""
    team, accounts = _team(client, session, names=FIVE)
    assert _submit(client, accounts[0], team["id"]).status_code == 200
    tournament = service._get_tournament(session, uuid.UUID(team["tournament_id"]))
    frozen_clock.set(tournament.registration_end)

    response = _join(client, _make_account(session), team["invite_token"])
    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()

    assert response.status_code == 409
    assert _error_code(response) == "ROSTER_LOCKED"
    assert preview["invite_status"] == "locked"


def test_join_one_second_before_deadline_succeeds(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session)
    team = _create_ok(client, _make_account(session), tournament.id)
    frozen_clock.set(tournament.registration_end - timedelta(seconds=1))

    assert _join(client, _make_account(session), team["invite_token"]).status_code == (
        200
    )


# ---------------------------------------------------------------- 送出條件（純函式）


def _entry(
    name: str, *, missing: bool = False, school: uuid.UUID | None = None
) -> RosterEntry:
    return RosterEntry(
        display_name=name,
        missing_fields=["rank_tier"] if missing else [],
        school_id=school,
    )


def test_submit_blockers_empty_when_all_requirements_met() -> None:
    school = uuid.uuid4()
    members = [_entry("甲", school=school), _entry("乙", school=school)]

    assert player_profile.submit_blockers(starters=2, members=members) == []


def test_submit_blockers_counts_shortage_and_ignores_extra_members() -> None:
    school = uuid.uuid4()

    short = player_profile.submit_blockers(
        starters=5, members=[_entry("甲", school=school)]
    )
    extra = player_profile.submit_blockers(
        starters=1, members=[_entry("甲", school=school), _entry("乙", school=school)]
    )

    assert [(b.code, b.message) for b in short] == [
        ("STARTERS_NOT_MET", "還差 4 人才達先發人數（5 人）")
    ]
    assert extra == []


def test_submit_blockers_only_compares_members_with_a_school() -> None:
    school = uuid.uuid4()
    members = [_entry("甲", school=school), _entry("乙"), _entry("丙", school=school)]

    blockers = player_profile.submit_blockers(starters=3, members=members)

    assert [(b.code, b.message) for b in blockers] == [
        ("SCHOOL_MISSING", "尚未設定學校：乙")
    ]


def test_submit_blockers_with_nobody_having_a_school() -> None:
    blockers = player_profile.submit_blockers(
        starters=2, members=[_entry("甲", missing=True), _entry("乙")]
    )

    assert [b.code for b in blockers] == ["PROFILE_INCOMPLETE", "SCHOOL_MISSING"]
    assert blockers[1].message == "尚未設定學校：甲、乙"


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([], None),
        ([30, 30, 10], Decimal("23.33")),
        ([1, 0, 0, 0, 0, 0, 0, 0], Decimal("0.13")),
    ],
)
def test_average_rank_score_decimal(
    scores: list[int], expected: Decimal | None
) -> None:
    assert player_profile.average_rank_score_decimal(scores) == expected


# ---------------------------------------------------------------- core.authz 與 identity


def test_ensure_captain_compares_loaded_members() -> None:
    captain, player = uuid.uuid4(), uuid.uuid4()
    team = SimpleNamespace(
        members=[
            SimpleNamespace(account_id=captain, role=MemberRole.CAPTAIN),
            SimpleNamespace(account_id=player, role=MemberRole.PLAYER),
        ]
    )

    authz.ensure_captain(team, captain)
    for other in (player, uuid.uuid4()):
        with pytest.raises(BusinessError) as excinfo:
            authz.ensure_captain(team, other)
        assert excinfo.value.code == "TEAM_CAPTAIN_REQUIRED"
        assert excinfo.value.status_code == 403
        assert excinfo.value.message == "只有隊長可以使用這個功能。"
    with pytest.raises(BusinessError) as custom:
        authz.ensure_captain(team, player, message="只有隊長可以送出報名")
    assert custom.value.message == "只有隊長可以送出報名"


def test_ensure_captain_accepts_team_read(client: TestClient, session: Session) -> None:
    team, accounts = _team(client, session, names=FIVE[:2])
    read = service.get_team(session, team_id=uuid.UUID(team["id"]))

    authz.ensure_captain(read, accounts[0].id)
    with pytest.raises(BusinessError):
        authz.ensure_captain(read, accounts[1].id)


def test_get_account_school_ids(session: Session) -> None:
    school = _school(session)
    with_school = make_account(session, school_id=school.id)
    without_school = make_account(session)
    unknown = uuid.uuid4()

    result = identity_service.get_account_school_ids(
        session, [with_school.id, without_school.id, unknown]
    )

    assert result == {with_school.id: school.id, without_school.id: None}
    assert identity_service.get_account_school_ids(session, []) == {}


# ---------------------------------------------------------------- 併發


SUBMITTERS = 4


def test_parallel_submissions_succeed_only_once() -> None:
    """隊長的多個送出請求同時到達：只有一個成功，其餘 409 `REGISTRATION_ALREADY_SUBMITTED`。"""
    with Session(engine) as setup:
        game = make_game(setup)
        test_team_concurrency._demote_game_creator(setup, game.id)
        tournament: TournamentRead = make_tournament(
            setup, game=game, starters=2, substitutes=0
        )
        school = _school(setup)
        captain = make_account(setup, school_id=school.id)
        player = make_account(setup, school_id=school.id)
        team = service.create_team(
            setup, tournament_id=tournament.id, account_id=captain.id, name="併發送出隊"
        )
        service.join_team(setup, token=team.invite_token, account_id=player.id)
        for account in (captain, player):
            _fill(setup, team.id, account)
        # commit 之後 ORM 物件會過期，先記下 id
        team_id, captain_id, school_id = team.id, captain.id, school.id
        setup.commit()

    start = threading.Barrier(SUBMITTERS)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def _submit_in_thread() -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                service.submit_registration(db, team_id=team_id, account_id=captain_id)
                db.commit()
                result = "ok"
            except BusinessError as exc:
                result = exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                result = repr(exc)
        with outcomes_lock:
            outcomes.append(result)

    threads: list[threading.Thread] = []
    try:
        threads = [
            threading.Thread(target=_submit_in_thread) for _ in range(SUBMITTERS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        assert sorted(outcomes) == ["REGISTRATION_ALREADY_SUBMITTED"] * (
            SUBMITTERS - 1
        ) + ["ok"], outcomes
        with Session(engine) as check:
            registration = repository.get_registration_by_team(check, team_id)
            assert registration is not None
            assert registration.status == RegistrationStatus.PENDING
            assert registration.school_id == school_id
            assert len(_audit(check, "registration.submitted", tournament.id)) == 1
    finally:
        for thread in threads:
            thread.join(timeout=10)
        with Session(engine) as cleanup:
            cleanup.execute(
                delete(TeamMember).where(col(TeamMember.team_id) == team_id)
            )
            cleanup.execute(
                delete(Registration).where(col(Registration.team_id) == team_id)
            )
            cleanup.execute(delete(Team).where(col(Team.id) == team_id))
            cleanup.commit()


JOINERS_DURING_SUBMIT = 3


def test_joins_racing_a_submission_never_change_the_submitted_roster() -> None:
    """隊長送出時有人同時以邀請連結加入：送出後的名單人數等於送出當下的人數。"""
    with Session(engine) as setup:
        game = make_game(setup)
        test_team_concurrency._demote_game_creator(setup, game.id)
        tournament: TournamentRead = make_tournament(
            setup, game=game, starters=2, substitutes=5
        )
        school = _school(setup)
        captain = make_account(setup, school_id=school.id)
        player = make_account(setup, school_id=school.id)
        team = service.create_team(
            setup, tournament_id=tournament.id, account_id=captain.id, name="搶加入隊"
        )
        service.join_team(setup, token=team.invite_token, account_id=player.id)
        for account in (captain, player):
            _fill(setup, team.id, account)
        joiner_ids = [
            make_account(setup, school_id=school.id).id
            for _ in range(JOINERS_DURING_SUBMIT)
        ]
        team_id, token, captain_id = team.id, team.invite_token, captain.id
        setup.commit()

    start = threading.Barrier(JOINERS_DURING_SUBMIT + 1)
    outcomes: dict[str, str] = {}
    outcomes_lock = threading.Lock()

    def _run(name: str, action: Any) -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                detail = action(db)
                db.commit()
                result = f"ok:{len(detail.members)}"
            except BusinessError as exc:
                result = exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                result = repr(exc)
        with outcomes_lock:
            outcomes[name] = result

    def _submit_action(db: Session) -> Any:
        return service.submit_registration(db, team_id=team_id, account_id=captain_id)

    def _join_action(account_id: uuid.UUID) -> Any:
        return lambda db: service.join_team(db, token=token, account_id=account_id)

    threads: list[threading.Thread] = []
    try:
        threads = [threading.Thread(target=_run, args=("submit", _submit_action))]
        threads += [
            threading.Thread(target=_run, args=(str(i), _join_action(i)))
            for i in joiner_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        submit_result = outcomes["submit"]
        join_results = [outcomes[str(i)] for i in joiner_ids]
        joined = sum(r.startswith("ok:") for r in join_results)
        with Session(engine) as check:
            registration = repository.get_registration_by_team(check, team_id)
            assert registration is not None
            member_count = repository.count_members(check, team_id)
        # 加入的人沒有參賽資料：有人先加入，送出就因資料未填完而被拒；
        # 送出先成功，之後的加入一律被名單鎖定擋下。兩種順序都不會讓已送出的名單變動。
        if submit_result.startswith("ok:"):
            assert join_results == ["ROSTER_LOCKED"] * JOINERS_DURING_SUBMIT, outcomes
            assert registration.status == RegistrationStatus.PENDING
            assert member_count == int(submit_result.removeprefix("ok:")) == 2
        else:
            assert submit_result == "REGISTRATION_REQUIREMENTS_UNMET", outcomes
            assert "ROSTER_LOCKED" not in join_results, outcomes
            assert registration.status == RegistrationStatus.FORMING
            assert member_count == 2 + joined
    finally:
        for thread in threads:
            thread.join(timeout=10)
        with Session(engine) as cleanup:
            cleanup.execute(
                delete(TeamMember).where(col(TeamMember.team_id) == team_id)
            )
            cleanup.execute(
                delete(Registration).where(col(Registration.team_id) == team_id)
            )
            cleanup.execute(delete(Team).where(col(Team.id) == team_id))
            cleanup.commit()
