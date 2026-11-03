"""Story 3.2 第二段：隊員存參賽資料的 API 與 S17 的完成度、平均段位積分。

賽事用真實資料（`make_game` 段位預設 鑽石=30、黃金=10）；圖片存到 `tmp_path`。
"""

import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.storage import MAX_IMAGE_BYTES
from app.modules.identity.models import Account
from app.modules.registration import repository, service
from app.modules.registration.models import RegistrationStatus, TeamMember
from app.modules.tournaments.models import TournamentStatus
from tests.helpers import make_game
from tests.registration import test_teams
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

# 共用 3.1 的 fixture：包住真實的 lock_tournament
lock_spy = test_teams.lock_spy

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
JPEG = b"\xff\xd8\xff\xe0" + b"pixels"
GIF = b"GIF89a" + b"pixels"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


def _files(directory: Path) -> list[str]:
    return sorted(os.listdir(directory)) if directory.exists() else []


def _url(team_id: str | uuid.UUID) -> str:
    return f"{API}/teams/{team_id}/members/me/profile"


def _put(
    client: TestClient,
    account: Account,
    team_id: str | uuid.UUID,
    *,
    game_account_id: str | None = "Night#TW1",
    rank_tier: str | None = "鑽石",
    screenshot: tuple[str, bytes, str] | None = ("my rank.png", PNG, "image/png"),
) -> Any:
    data: dict[str, str] = {}
    if game_account_id is not None:
        data["game_account_id"] = game_account_id
    if rank_tier is not None:
        data["rank_tier"] = rank_tier
    files = {"rank_screenshot": screenshot} if screenshot is not None else None
    return client.put(_url(team_id), data=data, files=files, headers=_auth(account))


def _put_ok(client: TestClient, account: Account, team_id: Any, **kwargs: Any) -> Any:
    response = _put(client, account, team_id, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def _row(body: dict[str, Any], account: Account) -> dict[str, Any]:
    [row] = [m for m in body["members"] if m["account_id"] == str(account.id)]
    return row


def _member(session: Session, team_id: Any, account: Account) -> TeamMember:
    session.expire_all()
    member = repository.get_team_member(session, uuid.UUID(str(team_id)), account.id)
    assert member is not None
    return member


def _field_error(response: Any) -> tuple[str, list[str]]:
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    return error["type"], error["loc"]


def _team(
    client: TestClient, session: Session, **tournament_overrides: Any
) -> tuple[dict[str, Any], Account]:
    captain = _make_account(session, display_name="阿哲")
    tournament = _tournament(session, **tournament_overrides)
    return _create_ok(client, captain, tournament.id), captain


def _set_registration(
    session: Session, team_id: Any, status: RegistrationStatus
) -> None:
    registration = repository.get_registration_by_team(session, uuid.UUID(str(team_id)))
    assert registration is not None
    registration.status = status
    session.add(registration)
    session.flush()


# ---------------------------------------------------------------- 存資料


def test_first_fill_saves_profile_and_screenshot(
    client: TestClient, session: Session, upload_dir: Path, lock_spy: LockSpy
) -> None:
    team, captain = _team(client, session)
    lock_spy.locked.clear()

    body = _put_ok(client, captain, team["id"], game_account_id="  Night#TW1  ")

    row = _row(body, captain)
    assert row["game_account_id"] == "Night#TW1"
    assert (row["rank_tier"], row["rank_score"]) == ("鑽石", 30)
    assert row["has_rank_screenshot"] is True
    assert row["rank_screenshot_name"] == "my rank.png"
    assert row["missing_fields"] == []
    assert lock_spy.locked == [uuid.UUID(team["tournament_id"])]

    member = _member(session, team["id"], captain)
    assert member.rank_screenshot_key is not None
    assert _files(upload_dir) == [member.rank_screenshot_key]
    assert (upload_dir / member.rank_screenshot_key).read_bytes() == PNG
    assert member.rank_screenshot_key not in str(body)
    assert "rank_screenshot_key" not in str(body)


def test_update_without_screenshot_keeps_the_file(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    _put_ok(client, captain, team["id"])
    key = _member(session, team["id"], captain).rank_screenshot_key

    omitted = _put_ok(
        client, captain, team["id"], game_account_id="New#1", screenshot=None
    )
    # 瀏覽器送出空的檔案欄位：檔名為空且 0 byte
    empty = _put_ok(
        client,
        captain,
        team["id"],
        rank_tier="黃金",
        screenshot=("", b"", "application/octet-stream"),
    )

    assert _row(omitted, captain)["game_account_id"] == "New#1"
    row = _row(empty, captain)
    assert (row["rank_tier"], row["rank_score"]) == ("黃金", 10)
    assert row["rank_screenshot_name"] == "my rank.png"
    member = _member(session, team["id"], captain)
    assert member.rank_screenshot_key == key
    assert _files(upload_dir) == [key]


def test_replacing_screenshot_deletes_the_old_file_after_commit(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    _put_ok(client, captain, team["id"])
    old_key = _member(session, team["id"], captain).rank_screenshot_key

    body = _put_ok(
        client, captain, team["id"], screenshot=("C:\\fake\\新.jpg", JPEG, "image/jpeg")
    )

    new_key = _member(session, team["id"], captain).rank_screenshot_key
    assert new_key is not None and new_key != old_key
    assert new_key.endswith(".jpg")
    assert _files(upload_dir) == [new_key]
    assert _row(body, captain)["rank_screenshot_name"] == "新.jpg"


def test_first_fill_without_screenshot_is_rejected(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)

    response = _put(client, captain, team["id"], screenshot=None)
    empty = _put(
        client, captain, team["id"], screenshot=("", b"", "application/octet-stream")
    )

    assert _field_error(response) == (
        "RANK_SCREENSHOT_REQUIRED",
        ["body", "rank_screenshot"],
    )
    assert response.json()["detail"][0]["msg"] == "請上傳段位截圖"
    assert _field_error(empty)[0] == "RANK_SCREENSHOT_REQUIRED"
    assert _member(session, team["id"], captain).game_account_id is None
    assert _files(upload_dir) == []


@pytest.mark.parametrize(
    ("game_account_id", "code", "message"),
    [
        (None, "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("   ", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("x" * 51, "GAME_ACCOUNT_ID_TOO_LONG", "遊戲 ID 最多 50 個字"),
    ],
)
def test_invalid_game_account_id_is_rejected(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    game_account_id: str | None,
    code: str,
    message: str,
) -> None:
    team, captain = _team(client, session)

    response = _put(client, captain, team["id"], game_account_id=game_account_id)

    assert _field_error(response) == (code, ["body", "game_account_id"])
    assert response.json()["detail"][0]["msg"] == message
    assert _member(session, team["id"], captain).game_account_id is None
    assert _files(upload_dir) == []


def test_game_account_id_of_50_characters_after_trimming_is_accepted(
    client: TestClient, session: Session
) -> None:
    team, captain = _team(client, session)

    body = _put_ok(client, captain, team["id"], game_account_id=f" {'x' * 50} ")

    assert _row(body, captain)["game_account_id"] == "x" * 50


@pytest.mark.parametrize("rank_tier", [None, "", "大師", "鑽石 "])
def test_rank_tier_not_in_table_is_rejected_without_leaving_a_file(
    client: TestClient, session: Session, upload_dir: Path, rank_tier: str | None
) -> None:
    team, captain = _team(client, session)

    response = _put(client, captain, team["id"], rank_tier=rank_tier)

    assert _field_error(response) == ("RANK_TIER_NOT_ALLOWED", ["body", "rank_tier"])
    assert _member(session, team["id"], captain).rank_tier is None
    assert _files(upload_dir) == []


@pytest.mark.parametrize(
    ("screenshot", "status_code", "code"),
    [
        (("a.gif", GIF, "image/gif"), 415, "UNSUPPORTED_FILE_TYPE"),
        (("a.jpg", PNG, "image/jpeg"), 415, "UNSUPPORTED_FILE_TYPE"),
        (
            ("a.png", PNG + b"\0" * (MAX_IMAGE_BYTES + 1 - len(PNG)), "image/png"),
            413,
            "FILE_TOO_LARGE",
        ),
    ],
)
def test_invalid_image_is_rejected(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    screenshot: tuple[str, bytes, str],
    status_code: int,
    code: str,
) -> None:
    team, captain = _team(client, session)

    response = _put(client, captain, team["id"], screenshot=screenshot)

    assert response.status_code == status_code
    assert _error_code(response) == code
    member = _member(session, team["id"], captain)
    assert (member.game_account_id, member.rank_screenshot_key) == (None, None)
    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 權限與狀態


def test_unknown_team_is_404_without_locking(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    response = _put(client, _make_account(session), uuid.uuid4())

    assert response.status_code == 404
    assert _error_code(response) == "TEAM_NOT_FOUND"
    assert lock_spy.locked == []


def test_only_members_can_save_and_only_their_own_row(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    other_team, _ = _team(client, session)
    player = _make_account(session, display_name="小安")
    _join(client, player, team["invite_token"])

    stranger = _put(client, _make_account(session), team["id"])
    other_captain_row = _put(client, captain, other_team["id"])
    body = _put_ok(client, player, team["id"])

    for response in (stranger, other_captain_row):
        assert response.status_code == 403
        assert _error_code(response) == "TEAM_MEMBER_REQUIRED"
    assert _row(body, player)["missing_fields"] == []
    assert _row(body, captain)["missing_fields"] == [
        "game_account_id",
        "rank_tier",
        "rank_screenshot",
    ]
    assert len(_files(upload_dir)) == 1


def test_requires_login_and_verified_email(
    client: TestClient, session: Session
) -> None:
    team, _ = _team(client, session)

    anonymous = client.put(_url(team["id"]), data={"game_account_id": "x"})
    unverified = _put(client, _make_account(session, verified=False), team["id"])

    assert anonymous.status_code == 401
    assert unverified.status_code == 403


def test_locks_the_tournament_before_checking_membership(
    client: TestClient,
    session: Session,
    lock_spy: LockSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team, captain = _team(client, session)
    for name in ("get_team", "get_team_member"):
        original = getattr(repository, name)

        def wrapped(*args: Any, _name: str = name, _original: Any = original) -> Any:
            lock_spy.events.append(_name)
            return _original(*args)

        monkeypatch.setattr(repository, name, wrapped)
    lock_spy.events.clear()

    _put_ok(client, captain, team["id"])

    assert lock_spy.events[:3] == ["get_team", "lock", "get_team_member"]


def test_roster_locked_rejects_and_is_not_editable(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    _set_registration(session, team["id"], RegistrationStatus.PENDING)

    response = _put(client, captain, team["id"])
    # 欄位錯誤也一樣先回名單鎖定（欄位驗證在狀態檢查之後）
    blank = _put(client, captain, team["id"], game_account_id="")
    detail = client.get(f"{API}/teams/{team['id']}", headers=_auth(captain)).json()

    assert response.status_code == 409
    assert _error_code(response) == "ROSTER_LOCKED"
    assert response.json()["detail"]["message"] == "名單已鎖定，資料無法修改。"
    assert blank.status_code == 409
    assert detail["profile_editable"] is False
    assert _files(upload_dir) == []


def test_tournament_not_open_rejects_and_is_not_editable(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    response = _put(client, captain, team["id"], rank_tier="大師")
    detail = client.get(f"{API}/teams/{team['id']}", headers=_auth(captain)).json()

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert detail["profile_editable"] is False
    assert _files(upload_dir) == []


def test_non_member_on_closed_tournament_is_403_not_409(
    client: TestClient, session: Session
) -> None:
    team, _ = _team(client, session)
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    response = _put(client, _make_account(session), team["id"])

    assert response.status_code == 403
    assert _error_code(response) == "TEAM_MEMBER_REQUIRED"


def test_blank_game_id_on_closed_tournament_is_409_not_422(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    team, captain = _team(client, session)
    _set_status(session, uuid.UUID(team["tournament_id"]), TournamentStatus.CLOSED)

    response = _put(client, captain, team["id"], game_account_id="   ")

    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_CLOSED"
    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 操作紀錄與失敗清理


def test_records_audit_without_the_file_key(
    client: TestClient, session: Session
) -> None:
    team, captain = _team(client, session)
    tournament_id = uuid.UUID(team["tournament_id"])
    _put_ok(client, captain, team["id"])
    _put_ok(client, captain, team["id"], rank_tier="黃金", screenshot=None)

    first, second = sorted(
        _audit(session, "team_member.profile_updated", tournament_id),
        key=lambda log: log.seq or 0,
    )
    member = _member(session, team["id"], captain)
    assert (first.entity_type, first.entity_id) == ("team_member", member.id)
    assert first.actor_id == captain.id
    assert first.before == {
        "game_account_id": None,
        "rank_tier": None,
        "rank_score": None,
        "had_screenshot": False,
    }
    assert first.after == {
        "game_account_id": "Night#TW1",
        "rank_tier": "鑽石",
        "rank_score": 30,
        "screenshot_replaced": True,
    }
    assert second.before == {
        "game_account_id": "Night#TW1",
        "rank_tier": "鑽石",
        "rank_score": 30,
        "had_screenshot": True,
    }
    assert second.after is not None
    assert second.after["screenshot_replaced"] is False
    assert member.rank_screenshot_key is not None
    assert member.rank_screenshot_key not in str(first.after)


def test_service_failure_after_saving_leaves_no_new_file(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team, captain = _team(client, session)
    _put_ok(client, captain, team["id"])
    old_files = _files(upload_dir)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("build failed")

    monkeypatch.setattr(service, "_build_detail", boom)
    with pytest.raises(RuntimeError):
        _put(client, captain, team["id"])

    assert _files(upload_dir) == old_files


def test_commit_failure_deletes_the_new_file_and_keeps_the_old_one(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team, captain = _team(client, session)
    _put_ok(client, captain, team["id"])
    old_files = _files(upload_dir)

    def boom(_self: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        _put(client, captain, team["id"])

    assert _files(upload_dir) == old_files


# ---------------------------------------------------------------- S17 名單資料


def test_new_team_detail_has_rank_tiers_and_empty_profile(
    client: TestClient, session: Session
) -> None:
    team, _ = _team(client, session)

    assert team["rank_tiers"] == [
        {"name": "鑽石", "score": 30},
        {"name": "黃金", "score": 10},
    ]
    assert team["profile_editable"] is True
    assert (team["avg_rank_score"], team["rank_filled_count"]) == (None, 0)
    [row] = team["members"]
    assert row["missing_fields"] == ["game_account_id", "rank_tier", "rank_screenshot"]
    assert row["has_rank_screenshot"] is False
    assert row["rank_screenshot_name"] is None


def test_other_members_see_screenshot_status_but_not_file_name(
    client: TestClient, session: Session
) -> None:
    team, captain = _team(client, session)
    player = _make_account(session)
    _join(client, player, team["invite_token"])
    _put_ok(client, player, team["id"])

    as_captain = client.get(f"{API}/teams/{team['id']}", headers=_auth(captain))
    as_player = client.get(f"{API}/teams/{team['id']}", headers=_auth(player))

    captain_view = _row(as_captain.json(), player)
    assert captain_view["has_rank_screenshot"] is True
    assert captain_view["rank_screenshot_name"] is None
    assert captain_view["game_account_id"] == "Night#TW1"
    assert _row(as_player.json(), player)["rank_screenshot_name"] == "my rank.png"


def test_average_counts_filled_members_including_substitutes(
    client: TestClient, session: Session
) -> None:
    team, captain = _team(client, session, starters=1, substitutes=2)
    substitutes = [_make_account(session), _make_account(session)]
    for account in substitutes:
        _join(client, account, team["invite_token"])

    one = _put_ok(client, captain, team["id"])
    two = _put_ok(client, substitutes[0], team["id"])
    three = _put_ok(client, substitutes[1], team["id"], rank_tier="黃金")

    assert (one["avg_rank_score"], one["rank_filled_count"]) == (30.0, 1)
    assert (two["avg_rank_score"], two["rank_filled_count"]) == (30.0, 2)
    # (30 + 30 + 10) / 3 = 23.333… → 23.33
    assert (three["avg_rank_score"], three["rank_filled_count"]) == (23.33, 3)


def test_average_rounds_half_up(client: TestClient, session: Session) -> None:
    game = make_game(
        session, rank_tiers=[{"name": "高", "score": 1}, {"name": "低", "score": 0}]
    )
    team, captain = _team(client, session, game=game, starters=1, substitutes=7)
    accounts = [captain] + [_make_account(session) for _ in range(7)]
    for account in accounts[1:]:
        _join(client, account, team["invite_token"])

    body: dict[str, Any] = {}
    for index, account in enumerate(accounts):
        body = _put_ok(
            client, account, team["id"], rank_tier="高" if index == 0 else "低"
        )

    # 1 / 8 = 0.125 → 0.13（銀行家捨入會是 0.12）
    assert (body["avg_rank_score"], body["rank_filled_count"]) == (0.13, 8)


def test_browser_empty_file_field_counts_as_no_screenshot(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    """瀏覽器的空檔案欄位會帶 `filename=""`（httpx 不會），手動組 multipart 驗證。"""
    team, captain = _team(client, session)
    _put_ok(client, captain, team["id"])
    key = _member(session, team["id"], captain).rank_screenshot_key
    boundary = "----flowtest"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="game_account_id"'
        "\r\n\r\nEmpty#1\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="rank_tier"'
        "\r\n\r\n黃金\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="rank_screenshot"; '
        'filename=""\r\nContent-Type: application/octet-stream\r\n\r\n\r\n',
        f"--{boundary}--\r\n",
    ]

    response = client.put(
        _url(team["id"]),
        content="".join(parts).encode(),
        headers={
            **_auth(captain),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    assert response.status_code == 200, response.text
    assert _row(response.json(), captain)["game_account_id"] == "Empty#1"
    assert _member(session, team["id"], captain).rank_screenshot_key == key
    assert _files(upload_dir) == [key]
