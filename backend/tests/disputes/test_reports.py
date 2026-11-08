"""Story 6.4：提出檢舉（I/O 矩陣後端各列）、S20 選單、主辦方列表與附件下載。

賽事與隊伍用真實資料（3.1 的 API 建隊，再直接改報名狀態）；附件存到 `tmp_path`。
平行送出相同檢舉見 `test_report_concurrency.py`。
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import events
from app.core.config import settings
from app.core.events import OutboxEvent
from app.core.storage import MAX_IMAGE_BYTES
from app.modules.disputes.models import Report, ReportStatus
from app.modules.identity.models import Account
from app.modules.registration import repository as registration_repository
from app.modules.registration.models import RegistrationStatus, Team
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.conftest import FrozenClock
from tests.registration import test_teams
from tests.registration.test_teams import (
    API,
    LockSpy,
    _audit,
    _auth,
    _create_ok,
    _error_code,
    _make_account,
    _set_status,
    _tournament,
)

# 共用 3.1 的 fixture：包住真實的 lock_tournament
lock_spy = test_teams.lock_spy

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
JPEG = b"\xff\xd8\xff\xe0" + b"pixels"
GIF = b"GIF89a" + b"pixels"
DESCRIPTION = "隊員小明不是本校學生，學生證照片不符。"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


def _files(directory: Path) -> list[str]:
    return sorted(os.listdir(directory)) if directory.exists() else []


# ---------------------------------------------------------------- 測試資料


class World:
    """一場賽事、主辦方，以及 A（檢舉人）、B（對象）兩隊與各自的隊長。"""

    def __init__(
        self,
        tournament: TournamentRead,
        organizer: Account,
        a: dict[str, Any],
        a_captain: Account,
        b: dict[str, Any],
        b_captain: Account,
    ) -> None:
        self.tournament = tournament
        self.organizer = organizer
        self.a, self.a_captain = a, a_captain
        self.b, self.b_captain = b, b_captain

    @property
    def tid(self) -> uuid.UUID:
        return self.tournament.id


def _set_registration(
    session: Session, team_id: Any, status: RegistrationStatus
) -> None:
    registration = registration_repository.get_registration_by_team(
        session, uuid.UUID(str(team_id))
    )
    assert registration is not None
    registration.status = status
    session.add(registration)
    session.flush()


def _registration_status(session: Session, team_id: Any) -> RegistrationStatus:
    session.expire_all()
    registration = registration_repository.get_registration_by_team(
        session, uuid.UUID(str(team_id))
    )
    assert registration is not None
    return registration.status


def _team(
    client: TestClient,
    session: Session,
    tournament_id: uuid.UUID,
    name: str,
    status: RegistrationStatus | None = RegistrationStatus.ACCEPTED,
) -> tuple[dict[str, Any], Account]:
    captain = _make_account(session)
    team = _create_ok(client, captain, tournament_id, name)
    if status is not None:
        _set_registration(session, team["id"], status)
    return team, captain


def _world(client: TestClient, session: Session) -> World:
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    a, a_captain = _team(client, session, tournament.id, "夜貓隊")
    b, b_captain = _team(client, session, tournament.id, "晨鳥隊")
    return World(tournament, organizer, a, a_captain, b, b_captain)


def _post(
    client: TestClient,
    account: Account,
    tournament_id: Any,
    reported_team_id: Any,
    *,
    description: str | None = DESCRIPTION,
    attachment: tuple[str, bytes, str] | None = None,
) -> Any:
    data: dict[str, str] = {"reported_team_id": str(reported_team_id)}
    if description is not None:
        data["description"] = description
    files = {"attachment": attachment} if attachment is not None else None
    return client.post(
        f"{API}/tournaments/{tournament_id}/reports",
        data=data,
        files=files,
        headers=_auth(account),
    )


def _post_ok(client: TestClient, w: World, **kwargs: Any) -> dict[str, Any]:
    response = _post(client, w.a_captain, w.tid, w.b["id"], **kwargs)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _reportable(client: TestClient, account: Account, tournament_id: Any) -> Any:
    return client.get(
        f"{API}/tournaments/{tournament_id}/reportable-teams", headers=_auth(account)
    )


def _reports(session: Session, tournament_id: uuid.UUID) -> list[Report]:
    session.expire_all()
    return list(
        session.exec(select(Report).where(Report.tournament_id == tournament_id))
    )


def _filed_events(session: Session, tournament_id: uuid.UUID) -> list[OutboxEvent]:
    rows = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "ReportFiled")
    ).all()
    return [row for row in rows if row.payload["tournament_id"] == str(tournament_id)]


def _list(client: TestClient, account: Account, tournament_id: Any) -> Any:
    return client.get(
        f"{API}/organizer/tournaments/{tournament_id}/reports", headers=_auth(account)
    )


def _download(client: TestClient, account: Account, report_id: Any) -> Any:
    return client.get(
        f"{API}/organizer/reports/{report_id}/attachment", headers=_auth(account)
    )


def _close_report(session: Session, report_id: Any, status: ReportStatus) -> None:
    report = session.get(Report, uuid.UUID(str(report_id)))
    assert report is not None
    report.status = status
    session.add(report)
    session.flush()


# ---------------------------------------------------------------- 送出成功


def test_file_report_with_attachment(
    client: TestClient, session: Session, upload_dir: Path, lock_spy: LockSpy
) -> None:
    w = _world(client, session)
    lock_spy.locked.clear()

    body = _post_ok(
        client,
        w,
        description=f"  {DESCRIPTION}  ",
        attachment=("proof.png", PNG, "image/png"),
    )

    assert body["status"] == "open"
    assert body["has_attachment"] is True
    assert body["description"] == DESCRIPTION
    assert body["tournament_id"] == str(w.tid)
    assert (body["reporter_team_id"], body["reporter_team_name"]) == (
        w.a["id"],
        "夜貓隊",
    )
    assert (body["reported_team_id"], body["reported_team_name"]) == (
        w.b["id"],
        "晨鳥隊",
    )
    assert body["filed_by"] == str(w.a_captain.id)
    assert (body["reason"], body["handled_by"], body["handled_at"]) == (
        None,
        None,
        None,
    )
    assert "attachment_key" not in body
    assert lock_spy.locked == [w.tid]

    [report] = _reports(session, w.tid)
    assert report.attachment_key is not None
    assert _files(upload_dir) == [report.attachment_key]

    [log] = _audit(session, "report.filed", w.tid)
    assert log.actor_id == w.a_captain.id
    assert (log.entity_type, log.entity_id) == ("report", report.id)
    assert log.before is None
    assert log.after == {
        "reporter_team_id": w.a["id"],
        "reported_team_id": w.b["id"],
        "description": DESCRIPTION,
        "has_attachment": True,
    }
    assert report.attachment_key not in str(log.after)

    [event] = _filed_events(session, w.tid)
    assert event.payload == {
        "report_id": str(report.id),
        "tournament_id": str(w.tid),
        "reported_team_id": w.b["id"],
    }
    # 被檢舉的隊伍在查證前不受影響
    assert _registration_status(session, w.b["id"]) == RegistrationStatus.ACCEPTED


def test_file_report_without_attachment(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    w = _world(client, session)

    body = _post_ok(client, w)

    assert body["has_attachment"] is False
    [report] = _reports(session, w.tid)
    assert report.attachment_key is None
    assert _files(upload_dir) == []
    [log] = _audit(session, "report.filed", w.tid)
    assert log.after is not None and log.after["has_attachment"] is False


def test_empty_file_field_counts_as_no_attachment(
    client: TestClient, session: Session, upload_dir: Path
) -> None:
    w = _world(client, session)

    body = _post_ok(client, w, attachment=("", b"", "application/octet-stream"))

    assert body["has_attachment"] is False
    assert _files(upload_dir) == []


def test_jpeg_attachment_is_accepted(client: TestClient, session: Session) -> None:
    w = _world(client, session)

    body = _post_ok(client, w, attachment=("proof.jpg", JPEG, "image/jpeg"))

    assert body["has_attachment"] is True


@pytest.mark.parametrize(
    "reporter_status",
    [
        RegistrationStatus.PENDING,
        RegistrationStatus.ACCEPTED,
        RegistrationStatus.WAITLISTED,
        RegistrationStatus.DRAWN,
    ],
)
@pytest.mark.parametrize(
    "reported_status",
    [
        RegistrationStatus.PENDING,
        RegistrationStatus.WAITLISTED,
        RegistrationStatus.DRAWN,
    ],
)
def test_all_reportable_statuses_can_file(
    client: TestClient,
    session: Session,
    reporter_status: RegistrationStatus,
    reported_status: RegistrationStatus,
) -> None:
    w = _world(client, session)
    _set_registration(session, w.a["id"], reporter_status)
    _set_registration(session, w.b["id"], reported_status)

    _post_ok(client, w)

    assert _registration_status(session, w.b["id"]) == reported_status


@pytest.mark.parametrize(
    "tournament_status",
    [TournamentStatus.CLOSED, TournamentStatus.PUBLISHED, TournamentStatus.ONGOING],
)
def test_can_file_in_any_unfinished_tournament_status(
    client: TestClient, session: Session, tournament_status: TournamentStatus
) -> None:
    w = _world(client, session)
    _set_status(session, w.tid, tournament_status)

    _post_ok(client, w)


# ---------------------------------------------------------------- 拒絕


@pytest.mark.parametrize(
    ("tournament_status", "message"),
    [
        (TournamentStatus.FINISHED, "賽事已結束，不能提出檢舉。"),
        (TournamentStatus.CANCELLED, "賽事已取消，不能提出檢舉。"),
    ],
)
def test_finished_or_cancelled_tournament_is_rejected(
    client: TestClient,
    session: Session,
    tournament_status: TournamentStatus,
    message: str,
) -> None:
    w = _world(client, session)
    _set_status(session, w.tid, tournament_status)

    response = _post(client, w.a_captain, w.tid, w.b["id"])
    listing = _reportable(client, w.a_captain, w.tid)

    for result in (response, listing):
        assert result.status_code == 409
        assert result.json()["detail"] == {
            "code": "REPORT_NOT_ALLOWED",
            "message": message,
        }
    assert _reports(session, w.tid) == []


def test_unknown_tournament_is_404(client: TestClient, session: Session) -> None:
    w = _world(client, session)

    response = _post(client, w.a_captain, uuid.uuid4(), w.b["id"])

    assert response.status_code == 404
    assert _error_code(response) == "TOURNAMENT_NOT_FOUND"


def test_reporting_own_team_is_422(client: TestClient, session: Session) -> None:
    w = _world(client, session)

    response = _post(client, w.a_captain, w.tid, w.a["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "REPORT_SELF",
        "message": "不能檢舉自己的隊伍。",
    }


@pytest.mark.parametrize(
    "reported_status",
    [
        RegistrationStatus.FORMING,
        RegistrationStatus.REJECTED,
        RegistrationStatus.WITHDRAWN,
        RegistrationStatus.RETIRED,
        RegistrationStatus.DISQUALIFIED,
    ],
)
def test_reported_team_status_must_be_reportable(
    client: TestClient, session: Session, reported_status: RegistrationStatus
) -> None:
    w = _world(client, session)
    _set_registration(session, w.b["id"], reported_status)

    response = _post(client, w.a_captain, w.tid, w.b["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "REPORT_NOT_ALLOWED",
        "message": "這支隊伍的報名尚未送出或已不在賽事中，不能檢舉。",
    }


@pytest.mark.parametrize(
    "reporter_status",
    [
        RegistrationStatus.FORMING,
        RegistrationStatus.WITHDRAWN,
        RegistrationStatus.REJECTED,
        RegistrationStatus.RETIRED,
        RegistrationStatus.DISQUALIFIED,
    ],
)
def test_reporter_team_status_must_be_reportable(
    client: TestClient, session: Session, reporter_status: RegistrationStatus
) -> None:
    w = _world(client, session)
    _set_registration(session, w.a["id"], reporter_status)

    response = _post(client, w.a_captain, w.tid, w.b["id"])
    listing = _reportable(client, w.a_captain, w.tid)

    for result in (response, listing):
        assert result.status_code == 409
        assert result.json()["detail"] == {
            "code": "REPORT_NOT_ALLOWED",
            "message": "本隊的報名尚未送出或已不在賽事中，不能提出檢舉。",
        }


def test_reported_team_must_exist_in_this_tournament(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    other = _tournament(session)
    other_team, _ = _team(client, session, other.id, "別場隊")

    for reported_id in (uuid.uuid4(), other_team["id"]):
        response = _post(client, w.a_captain, w.tid, reported_id)
        assert response.status_code == 404
        assert _error_code(response) == "TEAM_NOT_FOUND"


def test_non_captains_are_403(client: TestClient, session: Session) -> None:
    w = _world(client, session)
    # 名單鎖定前加入 A 隊，再改回正取
    _set_registration(session, w.a["id"], RegistrationStatus.FORMING)
    player = _make_account(session)
    response = client.post(
        f"{API}/team-invites/{w.a['invite_token']}/members", headers=_auth(player)
    )
    assert response.status_code == 200, response.text
    _set_registration(session, w.a["id"], RegistrationStatus.ACCEPTED)
    outsider = _make_account(session)
    other = _tournament(session)
    _, other_captain = _team(client, session, other.id, "別場隊")

    for account in (player, outsider, other_captain):
        for result in (
            _post(client, account, w.tid, w.b["id"]),
            _reportable(client, account, w.tid),
        ):
            assert result.status_code == 403
            assert result.json()["detail"] == {
                "code": "CAPTAIN_REQUIRED",
                "message": "只有隊長可以提出檢舉。",
            }


def test_requires_login_and_verified_email(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    unverified = _make_account(session, verified=False)

    anonymous = client.post(
        f"{API}/tournaments/{w.tid}/reports",
        data={"reported_team_id": w.b["id"], "description": DESCRIPTION},
    )
    assert anonymous.status_code == 401
    assert client.get(f"{API}/tournaments/{w.tid}/reportable-teams").status_code == 401

    for result in (
        _post(client, unverified, w.tid, w.b["id"]),
        _reportable(client, unverified, w.tid),
    ):
        assert result.status_code == 403
        assert _error_code(result) == "EMAIL_NOT_VERIFIED"


# ---------------------------------------------------------------- 重複檢舉


def test_duplicate_open_report_is_rejected_until_closed(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    first = _post_ok(client, w)

    response = _post(client, w.a_captain, w.tid, w.b["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "REPORT_ALREADY_FILED",
        "message": "已檢舉這支隊伍，主辦方處理中。",
    }

    _close_report(session, first["id"], ReportStatus.DISMISSED)
    second = _post_ok(client, w)
    _close_report(session, second["id"], ReportStatus.SUBSTANTIATED)
    _post_ok(client, w)
    assert len(_reports(session, w.tid)) == 3


def test_another_team_can_report_the_same_team(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    _, c_captain = _team(client, session, w.tid, "午後隊")
    _post_ok(client, w)

    response = _post(client, c_captain, w.tid, w.b["id"])

    assert response.status_code == 201, response.text


def test_duplicate_check_runs_before_description_validation(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    _post_ok(client, w)

    response = _post(client, w.a_captain, w.tid, w.b["id"], description="  ")

    assert response.status_code == 409
    assert _error_code(response) == "REPORT_ALREADY_FILED"


# ---------------------------------------------------------------- 說明與附件


@pytest.mark.parametrize("description", [None, "", "   ", "字" * 1001])
def test_invalid_description_is_422_and_keeps_no_file(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    description: str | None,
) -> None:
    w = _world(client, session)

    response = _post(
        client,
        w.a_captain,
        w.tid,
        w.b["id"],
        description=description,
        attachment=("proof.png", PNG, "image/png"),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "type": "REPORT_DESCRIPTION_INVALID",
            "loc": ["body", "description"],
            "msg": "說明須為 1～1000 字。",
        }
    ]
    assert _files(upload_dir) == []
    assert _reports(session, w.tid) == []


def test_description_counts_code_points(client: TestClient, session: Session) -> None:
    w = _world(client, session)

    body = _post_ok(client, w, description="😀" * 1000)

    assert body["description"] == "😀" * 1000


@pytest.mark.parametrize(
    ("attachment", "status_code", "code"),
    [
        (("anim.gif", GIF, "image/gif"), 415, "UNSUPPORTED_FILE_TYPE"),
        (("fake.png", GIF, "image/png"), 415, "UNSUPPORTED_FILE_TYPE"),
        (
            ("huge.png", PNG + b"0" * MAX_IMAGE_BYTES, "image/png"),
            413,
            "FILE_TOO_LARGE",
        ),
    ],
)
def test_invalid_attachment_creates_no_report(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    attachment: tuple[str, bytes, str],
    status_code: int,
    code: str,
) -> None:
    w = _world(client, session)

    response = _post(client, w.a_captain, w.tid, w.b["id"], attachment=attachment)

    assert response.status_code == status_code
    assert _error_code(response) == code
    assert _files(upload_dir) == []
    assert _reports(session, w.tid) == []


def test_service_failure_after_saving_leaves_no_file(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = _world(client, session)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("publish failed")

    monkeypatch.setattr(events, "publish", boom)
    with pytest.raises(RuntimeError):
        _post(
            client,
            w.a_captain,
            w.tid,
            w.b["id"],
            attachment=("p.png", PNG, "image/png"),
        )

    assert _files(upload_dir) == []


def test_commit_failure_deletes_the_new_file(
    client: TestClient,
    session: Session,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = _world(client, session)

    def boom(_self: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        _post(
            client,
            w.a_captain,
            w.tid,
            w.b["id"],
            attachment=("p.png", PNG, "image/png"),
        )

    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 先鎖再檢查


def test_locks_the_tournament_before_checking(
    client: TestClient, session: Session, lock_spy: LockSpy
) -> None:
    """鎖住後讀到的狀態才算數：鎖定回傳「已結束」時拒絕，即使先前讀到的是開放報名。"""
    w = _world(client, session)
    lock_spy.override = lambda t: t.model_copy(
        update={"status": TournamentStatus.FINISHED}
    )
    lock_spy.locked.clear()

    response = _post(client, w.a_captain, w.tid, w.b["id"])

    assert response.status_code == 409
    assert _error_code(response) == "REPORT_NOT_ALLOWED"
    assert lock_spy.locked == [w.tid]


# ---------------------------------------------------------------- S20 選單


def test_reportable_teams_lists_other_submitted_teams(
    client: TestClient, session: Session
) -> None:
    """排除自己與組隊中的隊伍；隊名順序刻意與 id 順序相反，確認依隊名排序。"""
    w = _world(client, session)
    forming, _ = _team(client, session, w.tid, "組隊隊", RegistrationStatus.FORMING)
    others = [
        _team(client, session, w.tid, f"暫名{i}", status)[0]
        for i, status in enumerate(
            [RegistrationStatus.WAITLISTED, RegistrationStatus.PENDING]
        )
    ]
    ids = sorted([w.b["id"], *(t["id"] for t in others)], reverse=True)
    names = ["A 隊", "B 隊", "C 隊"]
    # id 由大到小依序命名為 A、B、C 隊：依隊名排序時 id 由大到小
    for team_id, name in zip(ids, names, strict=True):
        team = session.get(Team, uuid.UUID(team_id))
        assert team is not None
        team.name = name
        session.add(team)
    session.flush()
    assert sorted(names) == names

    response = _reportable(client, w.a_captain, w.tid)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [t["name"] for t in body] == names
    assert [t["id"] for t in body] == ids
    assert all(t["has_open_report"] is False for t in body)
    assert forming["id"] not in {t["id"] for t in body}

    _post_ok(client, w)
    flags = {
        t["id"]: t["has_open_report"]
        for t in _reportable(client, w.a_captain, w.tid).json()
    }
    assert flags == {team_id: team_id == w.b["id"] for team_id in ids}


def test_reportable_teams_ignores_other_teams_reports(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    _, c_captain = _team(client, session, w.tid, "午後隊")
    assert _post(client, c_captain, w.tid, w.b["id"]).status_code == 201

    body = _reportable(client, w.a_captain, w.tid).json()

    assert {t["id"]: t["has_open_report"] for t in body}[w.b["id"]] is False


def test_reportable_teams_empty_when_alone(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    _set_registration(session, w.b["id"], RegistrationStatus.WITHDRAWN)

    response = _reportable(client, w.a_captain, w.tid)

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------- 主辦方列表


def test_organizer_lists_reports_open_first_then_oldest(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    w = _world(client, session)
    _, c_captain = _team(client, session, w.tid, "午後隊")
    first = _post_ok(client, w)
    frozen_clock.advance(timedelta(minutes=1))
    second = _post(client, c_captain, w.tid, w.b["id"]).json()
    frozen_clock.advance(timedelta(minutes=1))
    third = _post(client, w.b_captain, w.tid, w.a["id"]).json()
    frozen_clock.advance(timedelta(minutes=1))
    _close_report(session, first["id"], ReportStatus.DISMISSED)
    fourth = _post_ok(client, w, attachment=("p.png", PNG, "image/png"))

    response = _list(client, w.organizer, w.tid)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["id"] for r in body] == [
        second["id"],
        third["id"],
        fourth["id"],
        first["id"],
    ]
    assert [r["status"] for r in body] == ["open", "open", "open", "dismissed"]
    assert body[1]["reporter_team_name"] == "晨鳥隊"
    assert body[1]["reported_team_name"] == "夜貓隊"
    assert body[2]["has_attachment"] is True
    assert all("attachment_key" not in r for r in body)


@pytest.mark.usefixtures("frozen_clock")
def test_organizer_list_same_time_orders_by_id(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    _, c_captain = _team(client, session, w.tid, "午後隊")
    first = _post_ok(client, w)
    second = _post(client, c_captain, w.tid, w.b["id"]).json()

    body = _list(client, w.organizer, w.tid).json()

    assert [r["id"] for r in body] == sorted([first["id"], second["id"]])


def test_organizer_list_permissions(client: TestClient, session: Session) -> None:
    w = _world(client, session)
    other_organizer = _make_account(session)
    other_organizer.is_organizer = True
    session.add(other_organizer)
    session.flush()

    response = _list(client, other_organizer, w.tid)
    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"

    response = _list(client, w.a_captain, w.tid)
    assert response.status_code == 403
    assert _error_code(response) == "ORGANIZER_REQUIRED"

    response = _list(client, w.organizer, uuid.uuid4())
    assert response.status_code == 404
    assert _error_code(response) == "TOURNAMENT_NOT_FOUND"


# ---------------------------------------------------------------- 附件下載


@pytest.mark.parametrize(
    ("attachment", "media_type", "extension"),
    [
        (("proof.png", PNG, "image/png"), "image/png", "png"),
        (("proof.jpeg", JPEG, "image/jpeg"), "image/jpeg", "jpg"),
    ],
)
def test_organizer_downloads_attachment(
    client: TestClient,
    session: Session,
    attachment: tuple[str, bytes, str],
    media_type: str,
    extension: str,
) -> None:
    w = _world(client, session)
    report = _post_ok(client, w, attachment=attachment)

    response = _download(client, w.organizer, report["id"])

    assert response.status_code == 200
    assert response.content == attachment[1]
    assert response.headers["content-type"] == media_type
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="report-{report["id"]}.{extension}"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_download_permissions_and_missing(client: TestClient, session: Session) -> None:
    w = _world(client, session)
    with_file = _post_ok(client, w, attachment=("p.png", PNG, "image/png"))
    _, c_captain = _team(client, session, w.tid, "午後隊")
    without_file = _post(client, c_captain, w.tid, w.b["id"]).json()
    other_organizer = _make_account(session)
    other_organizer.is_organizer = True
    session.add(other_organizer)
    session.flush()

    cases = [
        (other_organizer, with_file["id"], 403, "TOURNAMENT_OWNER_REQUIRED"),
        (w.a_captain, with_file["id"], 403, "ORGANIZER_REQUIRED"),
        (w.organizer, uuid.uuid4(), 404, "REPORT_NOT_FOUND"),
        (w.organizer, without_file["id"], 404, "FILE_NOT_FOUND"),
    ]
    for account, report_id, status_code, code in cases:
        response = _download(client, account, report_id)
        assert response.status_code == status_code, (account, report_id)
        assert _error_code(response) == code
    # 先查檢舉是否存在，再檢查是不是該賽事主辦方
    response = _download(client, other_organizer, uuid.uuid4())
    assert _error_code(response) == "REPORT_NOT_FOUND"


def test_list_reports_has_no_open_reports_from_other_tournaments(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    other = _world(client, session)
    _post_ok(client, other)

    body = _list(client, w.organizer, w.tid).json()

    assert body == []
    assert (
        len(
            list(
                session.exec(
                    select(Report).where(col(Report.tournament_id) == other.tid)
                )
            )
        )
        == 1
    )
