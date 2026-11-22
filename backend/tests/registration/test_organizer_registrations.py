"""Story 3.8：S29 主辦方報名清單與段位截圖下載。

清單的分組排序、篩選、分頁、候補順位與隊員資料；截圖下載的權限、歸屬與標頭。
退回本身在 test_reject_registration.py。
"""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.modules.identity.models import Account
from app.modules.registration import repository
from app.modules.registration.models import MemberRole, RegistrationStatus, TeamMember
from app.modules.tournaments.models import TournamentRead
from tests.conftest import FrozenClock
from tests.registration.test_first_come_submission import (
    SUBMIT_AFTER,
    _first_come,
    _in_window,
    _preset,
    _settled,
    _tournament,
)
from tests.registration.test_submit_registration import _school
from tests.registration.test_teams import API, _auth, _error_code, _make_account
from tests.registration.test_withdraw_registration import _team

S = RegistrationStatus
PNG = b"\x89PNG\r\n\x1a\n" + b"rank-pixels"
JPEG = b"\xff\xd8\xff\xe0" + b"rank-pixels"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


# ---------------------------------------------------------------- 測試資料


def _organizer(session: Session, tournament: TournamentRead) -> Account:
    account = session.get(Account, tournament.organizer_id)
    assert account is not None
    return account


def _list(
    client: TestClient, account: Account, tournament_id: Any, **params: Any
) -> Any:
    return client.get(
        f"{API}/organizer/tournaments/{tournament_id}/registrations",
        params=params,
        headers=_auth(account),
    )


def _list_ok(
    client: TestClient, session: Session, tournament: TournamentRead, **params: Any
) -> dict[str, Any]:
    response = _list(client, _organizer(session, tournament), tournament.id, **params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _screenshot(
    client: TestClient,
    account: Account,
    tournament_id: Any,
    registration_id: Any,
    account_id: Any,
) -> Any:
    return client.get(
        f"{API}/organizer/tournaments/{tournament_id}/registrations/"
        f"{registration_id}/members/{account_id}/rank-screenshot",
        headers=_auth(account),
    )


def _store(
    session: Session,
    upload_dir: Path,
    team_id: Any,
    account_id: uuid.UUID,
    *,
    content: bytes = PNG,
    extension: str = "png",
) -> str:
    """把截圖檔寫進上傳目錄並設為該隊員的截圖。"""
    key = f"{uuid.uuid4().hex}.{extension}"
    (upload_dir / key).write_bytes(content)
    member = repository.get_team_member(session, uuid.UUID(str(team_id)), account_id)
    assert member is not None
    member.rank_screenshot_key = key
    session.add(member)
    session.flush()
    return key


def _add_player(
    session: Session, team_id: Any, tournament: TournamentRead, name: str
) -> Account:
    """名單已鎖定不能經 API 加入：直接寫入隊員（沒有參賽資料）。"""
    player = _make_account(session, display_name=name)
    session.add(
        TeamMember(
            team_id=uuid.UUID(str(team_id)),
            tournament_id=tournament.id,
            account_id=player.id,
            role=MemberRole.PLAYER,
        )
    )
    session.flush()
    return player


# ---------------------------------------------------------------- 清單


def test_list_groups_by_allocation_with_waitlist_positions(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """正取 → 候補（依順位，沒有順位的最後）→ 待分配 → 已參賽 → 退賽 → 退回 → 撤回 →
    取消資格；組內依送出時間、再依 id；組隊中（未送出）不列出。"""
    tournament = _tournament(session, frozen_clock, capacity=10)
    school_p, school_x, school_y = (_school(session) for _ in range(3))
    _settled(session, tournament, [school_p])

    def add(status: S, minute: int, school: Any = None) -> Any:
        return _preset(
            session,
            tournament,
            school or _school(session),
            status,
            submitted_at=_first_come(tournament, minute),
        )

    disqualified = add(S.DISQUALIFIED, 1)
    withdrawn = add(S.WITHDRAWN, 2)
    rejected = add(S.REJECTED, 3)
    retired = add(S.RETIRED, 4)
    drawn = add(S.DRAWN, 5)
    pending = add(S.PENDING, 6)
    accepted_late = add(S.ACCEPTED, 8)
    accepted_early = add(S.ACCEPTED, 7)
    no_position = add(S.WAITLISTED, 9, school_p)  # 優先期學校：先搶期沒有順位
    second = add(S.WAITLISTED, 11, school_y)
    first = add(S.WAITLISTED, 10, school_x)
    rejected.reject_reason = "截圖不符"
    session.add(rejected)
    session.flush()
    # 組隊中、沒有送出時間的報名不列出
    _team(
        client,
        session,
        tournament,
        _school(session),
        S.FORMING,
        submitted_at=None,
    )
    frozen_clock.advance(SUBMIT_AFTER)

    body = _list_ok(client, session, tournament)

    order = [(item["status"], item["registration_id"]) for item in body["items"]]
    assert order == [
        ("accepted", str(accepted_early.id)),
        ("accepted", str(accepted_late.id)),
        ("waitlisted", str(first.id)),
        ("waitlisted", str(second.id)),
        ("waitlisted", str(no_position.id)),
        ("pending", str(pending.id)),
        ("drawn", str(drawn.id)),
        ("retired", str(retired.id)),
        ("rejected", str(rejected.id)),
        ("withdrawn", str(withdrawn.id)),
        ("disqualified", str(disqualified.id)),
    ]
    assert (body["total"], body["page"], body["page_size"]) == (11, 1, 20)
    items = {item["registration_id"]: item for item in body["items"]}
    assert items[str(first.id)]["waitlist_position"] == 1
    assert items[str(second.id)]["waitlist_position"] == 2
    assert items[str(no_position.id)]["waitlist_position"] is None
    assert items[str(no_position.id)]["waitlist_reason"] == "SCHOOL_NOT_ELIGIBLE"
    assert items[str(first.id)]["waitlist_phase"] == "first_come"
    assert items[str(accepted_early.id)]["waitlist_position"] is None
    assert items[str(rejected.id)]["reject_reason"] == "截圖不符"
    assert items[str(accepted_early.id)]["reject_reason"] is None
    rejectable = {i["registration_id"] for i in body["items"] if i["rejectable"]}
    assert rejectable == {
        str(r.id)
        for r in (accepted_early, accepted_late, first, second, no_position, pending)
    }


def test_list_filters_by_status_and_paginates(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock, capacity=30)
    for minute in range(21):
        _preset(
            session,
            tournament,
            _school(session),
            S.PENDING,
            submitted_at=_in_window(tournament, minute + 1),
        )
    _preset(
        session,
        tournament,
        _school(session),
        S.WITHDRAWN,
        submitted_at=_in_window(tournament, 30),
    )

    first_page = _list_ok(client, session, tournament)
    second_page = _list_ok(client, session, tournament, page=2)
    pending = _list_ok(client, session, tournament, status="pending", page=2)
    withdrawn = _list_ok(client, session, tournament, status="withdrawn")
    none = _list_ok(client, session, tournament, status="accepted")
    beyond = _list_ok(client, session, tournament, page=9)

    assert (len(first_page["items"]), first_page["total"]) == (20, 22)
    assert [i["status"] for i in second_page["items"]] == ["pending", "withdrawn"]
    assert (len(pending["items"]), pending["total"]) == (1, 21)
    assert [i["status"] for i in withdrawn["items"]] == ["withdrawn"]
    assert (none["items"], none["total"]) == ([], 0)
    assert (beyond["items"], beyond["total"]) == ([], 22)
    organizer = _organizer(session, tournament)
    assert _list(client, organizer, tournament.id, status="bogus").status_code == 422
    assert _list(client, organizer, tournament.id, page=0).status_code == 422


def test_list_empty_tournament(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    body = _list_ok(client, session, tournament)
    assert (body["items"], body["total"]) == ([], 0)


def test_list_members_captain_first_without_private_fields(
    client: TestClient, session: Session, frozen_clock: FrozenClock, upload_dir: Path
) -> None:
    """隊員：隊長在前再依加入順序；平均段位積分用快照；不回傳截圖檔名與鍵值；
    換截圖後 `rank_screenshot_version` 改變。"""
    tournament = _tournament(session, frozen_clock, substitutes=2)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
        score="42.5",
    )
    player = _add_player(session, team["id"], tournament, "後加入")

    body = _list_ok(client, session, tournament)

    [item] = body["items"]
    assert item["team_id"] == team["id"]
    assert item["team_name"] == team["name"]
    assert item["avg_rank_score"] == 42.5
    assert item["backfilled"] is False
    members = item["members"]
    assert [(m["account_id"], m["role"]) for m in members] == [
        (str(captain.id), "captain"),
        (str(player.id), "player"),
    ]
    assert members[0]["display_name"] == captain.display_name
    assert members[0]["game_account_id"] == f"ID-{captain.display_name}"
    assert members[0]["rank_tier"] == "鑽石"
    assert members[0]["has_rank_screenshot"] is True
    assert members[1]["has_rank_screenshot"] is False
    assert members[1]["rank_screenshot_version"] is None
    assert "rank_screenshot_name" not in members[0]
    assert "rank_screenshot_key" not in members[0]
    old_version = members[0]["rank_screenshot_version"]
    assert old_version
    member = repository.get_team_member(session, registration.team_id, captain.id)
    assert member is not None and member.rank_screenshot_key is not None
    assert member.rank_screenshot_key not in str(body)

    _store(session, upload_dir, team["id"], captain.id)

    new_version = _list_ok(client, session, tournament)["items"][0]["members"][0][
        "rank_screenshot_version"
    ]
    assert new_version and new_version != old_version


def test_list_permissions(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)
    _, captain, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    other_organizer = _organizer(session, _tournament(session, frozen_clock))

    assert _list(client, captain, tournament.id).status_code == 403
    assert _list(client, _make_account(session), tournament.id).status_code == 403
    response = _list(client, other_organizer, tournament.id)
    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert _list(client, other_organizer, uuid.uuid4()).status_code == 404
    assert (
        client.get(
            f"{API}/organizer/tournaments/{tournament.id}/registrations"
        ).status_code
        == 401
    )


# ---------------------------------------------------------------- 段位截圖


@pytest.mark.parametrize(
    ("content", "extension", "media_type"),
    [(PNG, "png", "image/png"), (JPEG, "jpg", "image/jpeg")],
)
def test_organizer_downloads_rank_screenshot(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    upload_dir: Path,
    content: bytes,
    extension: str,
    media_type: str,
) -> None:
    tournament = _tournament(session, frozen_clock)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    _store(
        session,
        upload_dir,
        team["id"],
        captain.id,
        content=content,
        extension=extension,
    )

    response = _screenshot(
        client,
        _organizer(session, tournament),
        tournament.id,
        registration.id,
        captain.id,
    )

    assert response.status_code == 200, response.text
    assert response.content == content
    assert response.headers["content-type"] == media_type
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="rank-{registration.id}-{captain.id}.{extension}"'
    )


def test_rank_screenshot_permissions_and_ownership(
    client: TestClient, session: Session, frozen_clock: FrozenClock, upload_dir: Path
) -> None:
    """隊長、隊員、上傳者本人一律 403；別賽事的報名、別隊的隊員 404；沒有截圖 404。"""
    tournament = _tournament(session, frozen_clock, substitutes=1)
    team, captain, registration = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 10),
    )
    _store(session, upload_dir, team["id"], captain.id)
    player = _add_player(session, team["id"], tournament, "沒上傳")
    _, other_captain, _ = _team(
        client,
        session,
        tournament,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(tournament, 11),
    )
    other = _tournament(session, frozen_clock)
    _, foreign_captain, foreign = _team(
        client,
        session,
        other,
        _school(session),
        S.PENDING,
        submitted_at=_in_window(other, 10),
    )
    organizer = _organizer(session, tournament)
    other_organizer = _organizer(session, other)

    for account in (captain, player):
        response = _screenshot(
            client, account, tournament.id, registration.id, captain.id
        )
        assert response.status_code == 403
    response = _screenshot(
        client, other_organizer, tournament.id, registration.id, captain.id
    )
    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"

    cross = _screenshot(
        client, organizer, tournament.id, foreign.id, foreign_captain.id
    )
    assert cross.status_code == 404
    assert _error_code(cross) == "REGISTRATION_NOT_FOUND"
    not_member = _screenshot(
        client, organizer, tournament.id, registration.id, other_captain.id
    )
    assert not_member.status_code == 404
    assert _error_code(not_member) == "TEAM_MEMBER_NOT_FOUND"
    missing = _screenshot(client, organizer, tournament.id, registration.id, player.id)
    assert missing.status_code == 404
    assert _error_code(missing) == "FILE_NOT_FOUND"
    assert (
        _screenshot(
            client, organizer, uuid.uuid4(), registration.id, captain.id
        ).status_code
        == 404
    )
