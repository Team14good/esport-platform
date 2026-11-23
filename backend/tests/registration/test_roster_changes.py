"""Story 3.11：隊員異動與解散隊伍（I/O 矩陣；併發在 test_team_concurrency.py）。

被測的四個操作都經 API；前置的報名狀態直接寫入報名列。截圖存到 `tmp_path`，檢查
交易提交後才刪檔。先鎖再檢查以包裝真實的 `lock_tournament` 驗證。
"""

import os
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import clock
from app.core.config import settings
from app.modules.identity.models import Account
from app.modules.registration import repository
from app.modules.registration.models import (
    DisbandedTeamMember,
    Registration,
    RegistrationStatus,
    TeamMember,
)
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.registration import test_teams
from tests.registration.test_submit_registration import (
    _fill,
    _school,
    _set_school,
    _submit,
)
from tests.registration.test_teams import (
    API,
    LockSpy,
    _audit,
    _auth,
    _create_ok,
    _error_code,
    _join,
    _make_account,
    _set_status,
    _tournament,
)
from tests.registration.test_withdraw_registration import _events

# 共用 3.1 的 fixture：包住真實的 lock_tournament
lock_spy = test_teams.lock_spy

pytestmark = pytest.mark.usefixtures("frozen_clock")

S = RegistrationStatus
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


# ---------------------------------------------------------------- 測試資料


def _files(directory: Path) -> list[str]:
    return sorted(os.listdir(directory)) if directory.exists() else []


def _upload(client: TestClient, account: Account, team_id: Any) -> None:
    """經 API 存參賽資料與段位截圖（真的寫檔）。"""
    response = client.put(
        f"{API}/teams/{team_id}/members/me/profile",
        data={"game_account_id": "Night#TW1", "rank_tier": "鑽石"},
        files={"rank_screenshot": ("rank.png", PNG, "image/png")},
        headers=_auth(account),
    )
    assert response.status_code == 200, response.text


def _world(
    client: TestClient,
    session: Session,
    names: tuple[str, ...] = ("小芸", "阿凱"),
    **overrides: Any,
) -> tuple[TournamentRead, dict[str, Any], Account, list[Account]]:
    """開放報名中的賽事、一支組隊中的隊伍：隊長「阿哲」與 `names` 依序加入的隊員。"""
    tournament = _tournament(session, **overrides)
    captain = _make_account(session, display_name="阿哲")
    team = _create_ok(client, captain, tournament.id)
    players = []
    for k, name in enumerate(names, start=1):
        player = _make_account(session, display_name=name)
        assert _join(client, player, team["invite_token"]).status_code == 200
        # 時鐘凍結時加入時間相同；錯開才有固定的名單順序
        member = repository.get_team_member(session, uuid.UUID(team["id"]), player.id)
        assert member is not None
        member.created_at = member.created_at + timedelta(seconds=k)
        session.add(member)
        session.flush()
        players.append(player)
    return tournament, team, captain, players


def _remove(client: TestClient, actor: Account, team_id: Any, target_id: Any) -> Any:
    return client.post(
        f"{API}/teams/{team_id}/members/{target_id}/removal", headers=_auth(actor)
    )


def _transfer(client: TestClient, actor: Account, team_id: Any, target_id: Any) -> Any:
    return client.post(
        f"{API}/teams/{team_id}/captain-transfer",
        json={"account_id": str(target_id)},
        headers=_auth(actor),
    )


def _leave(client: TestClient, actor: Account, team_id: Any) -> Any:
    return client.post(f"{API}/teams/{team_id}/departure", headers=_auth(actor))


def _disband(client: TestClient, actor: Account, team_id: Any) -> Any:
    return client.post(f"{API}/teams/{team_id}/disbandment", headers=_auth(actor))


def _detail(client: TestClient, account: Account, team_id: Any) -> Any:
    return client.get(f"{API}/teams/{team_id}", headers=_auth(account))


def _registration(session: Session, team_id: Any) -> Registration:
    session.expire_all()
    registration = repository.get_registration_by_team(session, uuid.UUID(str(team_id)))
    assert registration is not None
    return registration


def _set_registration(session: Session, team_id: Any, status: S) -> Registration:
    """直接改報名狀態，並補上送出時的快照（候補順位、S29 需要）。"""
    registration = _registration(session, team_id)
    registration.status = status
    registration.school_id = _school(session).id
    registration.avg_rank_score = Decimal("30.00")
    registration.submitted_at = clock.now()
    session.add(registration)
    session.flush()
    return registration


def _member_ids(session: Session, team_id: Any) -> list[uuid.UUID]:
    session.expire_all()
    return [
        m.account_id for m in repository.list_members(session, uuid.UUID(str(team_id)))
    ]


def _roles(session: Session, team_id: Any) -> dict[uuid.UUID, str]:
    session.expire_all()
    return {
        m.account_id: m.role
        for m in repository.list_members(session, uuid.UUID(str(team_id)))
    }


def _status_changes(session: Session, tournament: TournamentRead) -> list[Any]:
    return [
        (log.before["status"], log.after["status"])
        for log in sorted(
            _audit(session, "registration.status_changed", tournament.id),
            key=lambda log: log.seq or 0,
        )
    ]


# ---------------------------------------------------------------- 移除隊員


def test_remove_member_deletes_profile_and_screenshot(
    client: TestClient, session: Session, upload_dir: Path, lock_spy: LockSpy
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    _upload(client, b, team["id"])
    _upload(client, c, team["id"])
    [b_key] = [
        m.rank_screenshot_key
        for m in repository.list_members(session, uuid.UUID(team["id"]))
        if m.account_id == b.id
    ]
    assert b_key is not None
    lock_spy.locked.clear()

    response = _remove(client, captain, team["id"], b.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["display_name"] for m in body["members"]] == ["阿哲", "阿凱"]
    assert body["my_role"] == "captain"
    assert body["roster_editable"] is True
    assert body["disbanded"] is False
    assert lock_spy.locked == [tournament.id]
    assert _member_ids(session, team["id"]) == [captain.id, c.id]
    assert b_key not in _files(upload_dir)
    assert len(_files(upload_dir)) == 1  # 阿凱的截圖還在
    [event] = _events(session, tournament, "TeamMemberRemoved")
    assert event == {
        "team_id": team["id"],
        "tournament_id": str(tournament.id),
        "account_id": str(b.id),
    }
    [log] = _audit(session, "team.member_removed", tournament.id)
    assert log.actor_id == captain.id
    assert (log.entity_type, log.entity_id) == ("team", uuid.UUID(team["id"]))
    assert (log.before, log.after) == (
        {"account_id": str(b.id), "role": "player"},
        None,
    )


def test_screenshot_is_kept_when_commit_fails(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """截圖檔在交易提交後才刪：提交失敗時檔案還在。"""
    _, team, captain, [b, c] = _world(client, session)
    _upload(client, b, team["id"])
    _upload(client, c, team["id"])
    files = _files(upload_dir)

    def boom(_self: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        _remove(client, captain, team["id"], b.id)
    with pytest.raises(RuntimeError):
        _leave(client, c, team["id"])
    with pytest.raises(RuntimeError):
        _disband(client, captain, team["id"])

    assert _files(upload_dir) == files


def test_full_team_invite_reactivates_and_removed_member_can_rejoin(
    client: TestClient, session: Session
) -> None:
    """隊伍已滿時移除一人，邀請連結恢復有效；被移除者用原連結加入，參賽資料為空。"""
    _, team, captain, [b] = _world(
        client, session, names=("小芸",), starters=1, substitutes=1
    )
    _upload(client, b, team["id"])
    preview_url = f"{API}/team-invites/{team['invite_token']}"
    assert client.get(preview_url).json()["invite_status"] == "full"

    removed = _remove(client, captain, team["id"], b.id).json()

    assert removed["invite_status"] == "active"
    assert removed["invite_token"] == team["invite_token"]
    assert client.get(preview_url).json()["invite_status"] == "active"
    rejoined = _join(client, b, team["invite_token"])
    assert rejoined.status_code == 200, rejoined.text
    [row] = [m for m in rejoined.json()["members"] if m["account_id"] == str(b.id)]
    assert (row["game_account_id"], row["rank_tier"], row["has_rank_screenshot"]) == (
        None,
        None,
        False,
    )


def test_removed_member_cannot_rejoin_after_deadline(
    client: TestClient, session: Session
) -> None:
    """報名截止後仍可移除，但邀請狀態為 closed，被移除者無法再加入。"""
    tournament, team, captain, [b] = _world(client, session, names=("小芸",))
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    assert _remove(client, captain, team["id"], b.id).status_code == 200

    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()
    assert preview["invite_status"] == "closed"
    response = _join(client, b, team["invite_token"])
    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"


def test_captain_cannot_remove_self(client: TestClient, session: Session) -> None:
    tournament, team, captain, _ = _world(client, session)

    response = _remove(client, captain, team["id"], captain.id)

    assert response.status_code == 409
    assert _error_code(response) == "CAPTAIN_CANNOT_REMOVE_SELF"
    assert response.json()["detail"]["message"] == "隊長不能移除自己。"
    assert len(_member_ids(session, team["id"])) == 3
    assert _audit(session, "team.member_removed", tournament.id) == []


def test_remove_account_not_in_team_is_404(
    client: TestClient, session: Session
) -> None:
    tournament, team, captain, _ = _world(client, session)
    _, other_team, _, [other] = _world(client, session, names=("別隊",))

    for target in (other.id, uuid.uuid4()):
        response = _remove(client, captain, team["id"], target)
        assert response.status_code == 404
        assert _error_code(response) == "TEAM_MEMBER_NOT_FOUND"
    assert other.id in _member_ids(session, other_team["id"])
    assert _events(session, tournament, "TeamMemberRemoved") == []


# ---------------------------------------------------------------- 轉讓隊長


def test_transfer_captain_swaps_roles(client: TestClient, session: Session) -> None:
    """A 轉給 B：A 變選手、送出得 403；B 成為隊長，可以送出。"""
    tournament, team, a, [b] = _world(
        client, session, names=("小芸",), starters=1, substitutes=1
    )
    school = _school(session)
    for account in (a, b):
        _set_school(session, account, school)
        _fill(session, team["id"], account)

    response = _transfer(client, a, team["id"], b.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["my_role"] == "player"
    assert {m["account_id"]: m["role"] for m in body["members"]} == {
        str(a.id): "player",
        str(b.id): "captain",
    }
    assert _roles(session, team["id"]) == {a.id: "player", b.id: "captain"}
    [event] = _events(session, tournament, "CaptainTransferred")
    assert event == {
        "team_id": team["id"],
        "tournament_id": str(tournament.id),
        "from_account_id": str(a.id),
        "to_account_id": str(b.id),
    }
    [log] = _audit(session, "team.captain_transferred", tournament.id)
    assert log.actor_id == a.id
    assert (log.before, log.after) == (
        {"captain_id": str(a.id)},
        {"captain_id": str(b.id)},
    )
    denied = _submit(client, a, team["id"])
    assert denied.status_code == 403
    assert _error_code(denied) == "TEAM_CAPTAIN_REQUIRED"
    # 原隊長立即失去管理權限
    removal = _remove(client, a, team["id"], b.id)
    assert _error_code(removal) == "TEAM_CAPTAIN_REQUIRED"
    submitted = _submit(client, b, team["id"])
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["registration_status"] == "pending"


def test_transfer_to_self_or_outsider_is_rejected(
    client: TestClient, session: Session
) -> None:
    tournament, team, captain, _ = _world(client, session)
    _, _, _, [other] = _world(client, session, names=("別隊",))

    to_self = _transfer(client, captain, team["id"], captain.id)
    assert to_self.status_code == 409
    assert _error_code(to_self) == "ALREADY_CAPTAIN"
    assert to_self.json()["detail"]["message"] == "你已經是隊長。"
    for target in (other.id, uuid.uuid4()):
        response = _transfer(client, captain, team["id"], target)
        assert response.status_code == 404
        assert _error_code(response) == "TEAM_MEMBER_NOT_FOUND"
    assert _roles(session, team["id"])[captain.id] == "captain"
    assert _events(session, tournament, "CaptainTransferred") == []


@pytest.mark.parametrize("body", [{}, {"account_id": "不是 uuid"}])
def test_transfer_body_is_validated(
    client: TestClient, session: Session, body: dict[str, Any]
) -> None:
    _, team, captain, _ = _world(client, session)

    response = client.post(
        f"{API}/teams/{team['id']}/captain-transfer", json=body, headers=_auth(captain)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------- 退出隊伍


def test_member_leaves_and_can_join_another_team(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    _upload(client, b, team["id"])

    response = _leave(client, b, team["id"])

    assert response.status_code == 204, response.text
    assert _member_ids(session, team["id"]) == [captain.id, c.id]
    assert _files(upload_dir) == []
    [log] = _audit(session, "team.member_left", tournament.id)
    assert log.actor_id == b.id
    assert (log.before, log.after) == (
        {"account_id": str(b.id), "role": "player"},
        None,
    )
    # 退出不通知
    for event_type in ("TeamMemberRemoved", "CaptainTransferred", "TeamDisbanded"):
        assert _events(session, tournament, event_type) == []
    # 不再是隊員，看不到原隊伍；可以在同賽事建立別的隊伍
    hidden = _detail(client, b, team["id"])
    assert hidden.status_code == 403
    assert _error_code(hidden) == "TEAM_MEMBER_REQUIRED"
    _create_ok(client, b, tournament.id, "新隊")


def test_captain_cannot_leave(client: TestClient, session: Session) -> None:
    tournament, team, captain, _ = _world(client, session)

    response = _leave(client, captain, team["id"])

    assert response.status_code == 409
    assert _error_code(response) == "CAPTAIN_MUST_TRANSFER"
    assert response.json()["detail"]["message"] == "先轉讓隊長才能退出。"
    assert captain.id in _member_ids(session, team["id"])
    assert _audit(session, "team.member_left", tournament.id) == []


def test_removed_member_cannot_see_the_team(
    client: TestClient, session: Session
) -> None:
    _, team, captain, [b, _c] = _world(client, session)
    _remove(client, captain, team["id"], b.id)

    response = _detail(client, b, team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_MEMBER_REQUIRED"
    cards = client.get(f"{API}/accounts/me/teams", headers=_auth(b)).json()
    assert cards == []


# ---------------------------------------------------------------- 解散隊伍


def test_disband_keeps_a_read_only_page_for_former_members(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    _upload(client, captain, team["id"])
    _upload(client, b, team["id"])

    response = _disband(client, captain, team["id"])

    assert response.status_code == 204, response.text
    assert _member_ids(session, team["id"]) == []
    assert _files(upload_dir) == []
    registration = _registration(session, team["id"])
    assert registration.status == S.WITHDRAWN
    assert _status_changes(session, tournament) == [("forming", "withdrawn")]
    former = session.exec(
        select(DisbandedTeamMember).where(
            DisbandedTeamMember.team_id == uuid.UUID(team["id"])
        )
    ).all()
    assert {(m.account_id, m.role) for m in former} == {
        (captain.id, "captain"),
        (b.id, "player"),
        (c.id, "player"),
    }
    [event] = _events(session, tournament, "TeamDisbanded")
    assert event == {"team_id": team["id"], "tournament_id": str(tournament.id)}
    [log] = _audit(session, "team.disbanded", tournament.id)
    assert log.actor_id == captain.id
    assert log.after is None
    assert sorted(log.before["member_ids"]) == sorted(
        str(i) for i in (captain.id, b.id, c.id)
    )

    # S17 唯讀頁：原隊員（含隊長）都看得到，只有名稱與角色，不能做任何操作
    for account, role in ((captain, "captain"), (b, "player")):
        detail = _detail(client, account, team["id"])
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["disbanded"] is True
        assert body["registration_status"] == "withdrawn"
        assert body["my_role"] == role
        assert body["invite_token"] is None
        assert body["invite_status"] == "disbanded"
        assert (body["roster_editable"], body["withdrawable"]) == (False, False)
        assert (body["profile_editable"], body["submit_blockers"]) == (False, [])
        assert [(m["display_name"], m["role"]) for m in body["members"]] == [
            ("阿哲", "captain"),
            ("小芸", "player"),
            ("阿凱", "player"),
        ]
        assert all(
            m["game_account_id"] is None
            and not m["has_rank_screenshot"]
            and m["missing_fields"] == []
            for m in body["members"]
        )
    # S12 撤回卡片
    [card] = client.get(f"{API}/accounts/me/teams", headers=_auth(b)).json()
    assert (card["team_id"], card["registration_status"], card["withdrawable"]) == (
        team["id"],
        "withdrawn",
        False,
    )
    # S19 預覽：隊伍已解散；原連結無法加入
    preview = client.get(f"{API}/team-invites/{team['invite_token']}").json()
    assert preview["invite_status"] == "disbanded"
    joined = _join(client, _make_account(session), team["invite_token"])
    assert joined.status_code == 409
    assert _error_code(joined) == "ROSTER_LOCKED"
    # 原隊員可以加入同賽事的其他隊伍；隊名仍被佔用
    other = _create_ok(client, _make_account(session), tournament.id, "新隊")
    assert _join(client, b, other["invite_token"]).status_code == 200
    taken = client.post(
        f"{API}/tournaments/{tournament.id}/teams",
        json={"name": team["name"]},
        headers=_auth(c),
    )
    assert _error_code(taken) == "TEAM_NAME_TAKEN"


def test_disbanding_again_is_rejected(client: TestClient, session: Session) -> None:
    tournament, team, captain, _ = _world(client, session)
    assert _disband(client, captain, team["id"]).status_code == 204

    response = _disband(client, captain, team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_MEMBER_REQUIRED"
    assert len(_events(session, tournament, "TeamDisbanded")) == 1


def test_my_teams_merges_disbanded_teams_by_join_time(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    account = _make_account(session)
    first = _tournament(session)
    second = _tournament(session, name="清大盃")
    third = _tournament(session, name="交大盃")
    _create_ok(client, account, first.id, "A 隊")
    frozen_clock.advance(timedelta(minutes=1))
    team_b = _create_ok(client, account, second.id, "B 隊")
    frozen_clock.advance(timedelta(minutes=1))
    _create_ok(client, account, third.id, "C 隊")
    assert _disband(client, account, team_b["id"]).status_code == 204

    cards = client.get(f"{API}/accounts/me/teams", headers=_auth(account)).json()

    assert [(c["team_name"], c["registration_status"]) for c in cards] == [
        ("C 隊", "forming"),
        ("B 隊", "withdrawn"),
        ("A 隊", "forming"),
    ]


# ---------------------------------------------------------------- 被退回的隊伍


def test_rejected_team_can_change_roster_and_disband_through_forming(
    client: TestClient, session: Session
) -> None:
    tournament, team, captain, [b, c, d] = _world(
        client, session, names=("小芸", "阿凱", "小安")
    )
    _upload(client, b, team["id"])
    registration = _set_registration(session, team["id"], S.REJECTED)
    registration.reject_reason = "段位截圖不符"
    session.add(registration)
    session.flush()
    assert _detail(client, captain, team["id"]).json()["roster_editable"] is True

    assert _remove(client, captain, team["id"], d.id).status_code == 200
    assert _leave(client, c, team["id"]).status_code == 204
    assert _transfer(client, captain, team["id"], b.id).status_code == 200
    assert _disband(client, b, team["id"]).status_code == 204

    found = _registration(session, team["id"])
    assert found.status == S.WITHDRAWN
    assert _status_changes(session, tournament) == [
        ("rejected", "forming"),
        ("forming", "withdrawn"),
    ]
    # S29：撤回組列出原隊員（只有名稱與角色）、沒有截圖
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    page = client.get(
        f"{API}/organizer/tournaments/{tournament.id}/registrations",
        headers=_auth(organizer),
    ).json()
    [item] = page["items"]
    assert item["status"] == "withdrawn"
    assert item["disbanded"] is True
    assert [(m["display_name"], m["role"]) for m in item["members"]] == [
        ("小芸", "captain"),
        ("阿哲", "player"),
    ]
    assert not any(m["has_rank_screenshot"] for m in item["members"])
    assert all(m["rank_screenshot_version"] is None for m in item["members"])


def test_rejected_team_after_deadline_can_still_change_roster(
    client: TestClient, session: Session
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    _set_registration(session, team["id"], S.REJECTED)
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    assert _detail(client, captain, team["id"]).json()["roster_editable"] is True
    assert _remove(client, captain, team["id"], b.id).status_code == 200
    assert _transfer(client, captain, team["id"], c.id).status_code == 200
    assert _leave(client, captain, team["id"]).status_code == 204
    assert _disband(client, c, team["id"]).status_code == 204


def test_forming_team_after_deadline_can_change_roster(
    client: TestClient, session: Session
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    assert _remove(client, captain, team["id"], b.id).status_code == 200
    assert _transfer(client, captain, team["id"], c.id).status_code == 200
    assert _leave(client, captain, team["id"]).status_code == 204
    assert _disband(client, c, team["id"]).status_code == 204


# ---------------------------------------------------------------- 拒絕的情況


def _all_operations(
    client: TestClient,
    team: dict[str, Any],
    captain: Account,
    player: Account,
) -> list[Any]:
    return [
        _remove(client, captain, team["id"], player.id),
        _transfer(client, captain, team["id"], player.id),
        _leave(client, player, team["id"]),
        _disband(client, captain, team["id"]),
    ]


@pytest.mark.parametrize(
    "status",
    [
        TournamentStatus.PUBLISHED,
        TournamentStatus.ONGOING,
        TournamentStatus.FINISHED,
        TournamentStatus.CANCELLED,
    ],
)
def test_tournament_after_draw_or_cancelled_locks_the_roster(
    client: TestClient, session: Session, status: TournamentStatus
) -> None:
    tournament, team, captain, [b] = _world(client, session, names=("小芸",))
    _set_status(session, tournament.id, status)

    for response in _all_operations(client, team, captain, b):
        assert response.status_code == 409
        assert _error_code(response) == "ROSTER_LOCKED"
        assert response.json()["detail"]["message"] == "名單已鎖定，無法異動隊員。"
    assert _detail(client, captain, team["id"]).json()["roster_editable"] is False
    assert _member_ids(session, team["id"]) == [captain.id, b.id]
    assert _registration(session, team["id"]).status == S.FORMING


@pytest.mark.parametrize(
    "status", [S.PENDING, S.ACCEPTED, S.WAITLISTED, S.WITHDRAWN, S.DRAWN]
)
def test_locked_roster_rejects_every_operation(
    client: TestClient, session: Session, status: S
) -> None:
    tournament, team, captain, [b] = _world(client, session, names=("小芸",))
    _set_registration(session, team["id"], status)

    for response in _all_operations(client, team, captain, b):
        assert response.status_code == 409
        assert _error_code(response) == "ROSTER_LOCKED"
    assert _detail(client, captain, team["id"]).json()["roster_editable"] is False
    assert _roles(session, team["id"]) == {captain.id: "captain", b.id: "player"}
    assert _registration(session, team["id"]).status == status
    assert _events(session, tournament, "TeamDisbanded") == []


def test_non_captain_cannot_remove_transfer_or_disband(
    client: TestClient, session: Session
) -> None:
    _, team, captain, [b, c] = _world(client, session)

    for response in (
        _remove(client, b, team["id"], c.id),
        _transfer(client, b, team["id"], c.id),
        _disband(client, b, team["id"]),
    ):
        assert response.status_code == 403
        assert _error_code(response) == "TEAM_CAPTAIN_REQUIRED"
        assert (
            response.json()["detail"]["message"] == "只有隊長可以管理隊員或解散隊伍。"
        )
    assert _member_ids(session, team["id"]) == [captain.id, b.id, c.id]


def test_non_member_cannot_use_any_operation(
    client: TestClient, session: Session
) -> None:
    _, team, captain, [b] = _world(client, session, names=("小芸",))
    outsider = _make_account(session)

    for response in (
        _remove(client, outsider, team["id"], b.id),
        _transfer(client, outsider, team["id"], b.id),
        _leave(client, outsider, team["id"]),
        _disband(client, outsider, team["id"]),
    ):
        assert response.status_code == 403
        assert _error_code(response) == "TEAM_MEMBER_REQUIRED"
        assert response.json()["detail"]["message"] == "你不是這支隊伍的隊員。"
    assert _member_ids(session, team["id"]) == [captain.id, b.id]


def test_unknown_team_is_404_without_locking(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    account = _make_account(session)
    team_id = uuid.uuid4()

    for response in (
        _remove(client, account, team_id, uuid.uuid4()),
        _transfer(client, account, team_id, uuid.uuid4()),
        _leave(client, account, team_id),
        _disband(client, account, team_id),
    ):
        assert response.status_code == 404
        assert _error_code(response) == "TEAM_NOT_FOUND"
    assert lock_spy.locked == []


def test_requires_verified_account(client: TestClient, session: Session) -> None:
    _, team, _, [b] = _world(client, session, names=("小芸",))
    unverified = _make_account(session, verified=False)

    assert client.post(f"{API}/teams/{team['id']}/departure").status_code == 401
    assert _leave(client, unverified, team["id"]).status_code == 403
    assert b.id in _member_ids(session, team["id"])


def test_check_order_status_then_member_then_captain_then_roster(
    client: TestClient, session: Session
) -> None:
    """賽事狀態先於隊員；隊員先於隊長；隊長先於名單狀態。"""
    tournament, team, captain, [b] = _world(client, session, names=("小芸",))
    outsider = _make_account(session)

    _set_registration(session, team["id"], S.PENDING)
    # 名單已鎖定時：非隊員仍是 403、非隊長仍是 403（名單檢查在最後）
    assert _error_code(_disband(client, outsider, team["id"])) == "TEAM_MEMBER_REQUIRED"
    assert _error_code(_disband(client, b, team["id"])) == "TEAM_CAPTAIN_REQUIRED"
    # 隊長退出：名單鎖定先於 CAPTAIN_MUST_TRANSFER
    assert _error_code(_leave(client, captain, team["id"])) == "ROSTER_LOCKED"
    # 移除自己：名單鎖定先於對象檢查
    assert _error_code(_remove(client, captain, team["id"], captain.id)) == (
        "ROSTER_LOCKED"
    )
    # 賽事已抽籤：非隊員也得 409（賽事狀態先於隊員）
    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)
    assert _error_code(_disband(client, outsider, team["id"])) == "ROSTER_LOCKED"


def test_operations_lock_the_tournament_before_checking(
    client: TestClient,
    session: Session,
    lock_spy: LockSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament, team, captain, [b, c] = _world(client, session)
    original = repository.list_members

    def wrapped(*args: Any) -> list[TeamMember]:
        lock_spy.events.append("list_members")
        return original(*args)

    monkeypatch.setattr(repository, "list_members", wrapped)

    for call in (
        lambda: _remove(client, captain, team["id"], b.id),
        lambda: _transfer(client, captain, team["id"], c.id),
        lambda: _leave(client, captain, team["id"]),
        lambda: _disband(client, c, team["id"]),
    ):
        lock_spy.events.clear()
        response = call()
        assert response.status_code in (200, 204), response.text
        assert lock_spy.events[:2] == ["lock", "list_members"]
    assert lock_spy.locked.count(tournament.id) >= 4
