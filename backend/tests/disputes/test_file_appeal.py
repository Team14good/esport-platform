"""Story 6.1：提出申訴、申訴狀態查詢與附件下載（I/O 矩陣每一列）。

2 隊抽籤後只有決賽一場；測試把它改成申訴期（frozen_clock 下現在為
2026-10-18 11:00 UTC，申訴截止 11:30）。隊長身分以替身 `registration.is_captain` 判斷。
"""

import io
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core import audit
from app.core.config import settings
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.core.storage import MAX_IMAGE_BYTES
from app.modules.competition import service as competition_service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.disputes import repository, service
from app.modules.disputes.models import Appeal
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import (  # noqa: F401  fake_registration 是 fixture
    FakeRegistration,
    draw_with,
    fake_registration,
)
from tests.conftest import FrozenClock
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock", "fake_registration")

DEADLINE = datetime(2026, 10, 18, 11, 30, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
JPEG = b"\xff\xd8\xff\xe0" + b"pixels"
GIF = b"GIF89a" + b"pixels"


class Setup:
    """已抽籤的 2 隊賽事：決賽在申訴期，每隊一位隊長。"""

    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        tournament, bracket = draw_with(session, fake, 2)
        self.tournament_id = tournament.id
        organizer = session.get(Account, tournament.organizer_id)
        assert organizer is not None
        self.organizer = organizer
        self.match_id = bracket.matches[0].id
        match = session.get(Match, self.match_id)
        assert match is not None and match.team_a_id and match.team_b_id
        self.team_a, self.team_b = match.team_a_id, match.team_b_id
        match.status = MatchStatus.APPEAL_WINDOW
        match.outcome = MatchOutcome.PLAYED
        match.winner_id = self.team_a
        match.wins_a, match.wins_b = 2, 0
        match.appeal_deadline = DEADLINE
        session.add(match)
        self.captain_a = make_account(session)
        self.captain_b = make_account(session)
        self.player = make_account(session)
        self.captains = {self.team_a: self.captain_a, self.team_b: self.captain_b}

    def match(self, session: Session) -> Match:
        session.expire_all()
        match = session.get(Match, self.match_id)
        assert match is not None
        return match

    def set_match(self, session: Session, **values: object) -> None:
        match = self.match(session)
        for key, value in values.items():
            setattr(match, key, value)
        session.add(match)
        session.commit()

    def url(self, suffix: str = "appeals", match_id: uuid.UUID | None = None) -> str:
        return (
            f"{API}/tournaments/{self.tournament_id}"
            f"/matches/{match_id or self.match_id}/{suffix}"
        )


@pytest.fixture
def setup(
    session: Session,
    fake_registration: FakeRegistration,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Setup:
    result = Setup(session, fake_registration)

    def is_captain(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        captain = result.captains.get(team_id)
        return captain is not None and captain.id == account_id

    monkeypatch.setattr(registration_service, "is_captain", is_captain)
    session.commit()
    return result


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


def _files(directory: Path) -> list[str]:
    return sorted(os.listdir(directory)) if directory.exists() else []


def _auth(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _file(
    client: TestClient,
    setup: Setup,
    account: Account,
    *,
    description: str = "第二局對方使用了禁用角色。",
    attachment: tuple[str, bytes, str] | None = None,
    match_id: uuid.UUID | None = None,
) -> Any:
    files = {"attachment": attachment} if attachment is not None else None
    return client.post(
        setup.url(match_id=match_id),
        data={"description": description},
        files=files,
        headers=_auth(client, account),
    )


def _state(client: TestClient, setup: Setup, account: Account) -> Any:
    response = client.get(setup.url("appeal-state"), headers=_auth(client, account))
    assert response.status_code == 200, response.text
    return response.json()


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def _counts(session: Session, setup: Setup) -> tuple[int, int, int]:
    """這場的（申訴筆數、`appeal.filed` 紀錄數、`AppealFiled` 事件數）。

    只算這場：併發測試真正提交的操作紀錄刪不掉，會留在測試資料庫。
    """
    appeals = session.exec(
        select(func.count())
        .select_from(Appeal)
        .where(Appeal.match_id == setup.match_id)
    ).one()
    logs = session.exec(
        select(func.count())
        .select_from(audit.AuditLog)
        .where(audit.AuditLog.action == "appeal.filed")
        .where(audit.AuditLog.tournament_id == setup.tournament_id)
    ).one()
    events = [
        row
        for row in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "AppealFiled")
        ).all()
        if row.payload["match_id"] == str(setup.match_id)
    ]
    return appeals, logs, len(events)


# ---------------------------------------------------------------- 成功


def test_first_team_files_and_match_becomes_appealed(
    client: TestClient, session: Session, setup: Setup, upload_dir: Path
) -> None:
    response = _file(
        client, setup, setup.captain_a, attachment=("proof.png", PNG, "image/png")
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["match_id"] == str(setup.match_id)
    assert body["tournament_id"] == str(setup.tournament_id)
    assert body["team_id"] == str(setup.team_a)
    assert body["filed_by"] == str(setup.captain_a.id)
    assert body["description"] == "第二局對方使用了禁用角色。"
    assert body["has_attachment"] is True
    assert body["status"] == "open"
    assert body["decision"] is None
    assert "attachment_key" not in body

    match = setup.match(session)
    assert match.status == MatchStatus.APPEALED
    assert match.appeal_deadline == DEADLINE
    assert _counts(session, setup) == (1, 1, 1)

    appeal = session.get(Appeal, uuid.UUID(body["id"]))
    assert appeal is not None and appeal.attachment_key is not None
    assert (upload_dir / appeal.attachment_key).read_bytes() == PNG

    log = session.exec(
        select(audit.AuditLog)
        .where(audit.AuditLog.action == "appeal.filed")
        .where(audit.AuditLog.tournament_id == setup.tournament_id)
    ).one()
    assert log.actor_id == setup.captain_a.id
    assert log.tournament_id == setup.tournament_id
    assert log.entity_type == "appeal"
    assert log.entity_id == appeal.id
    assert log.before == {"match_status": "appeal_window"}
    assert log.after is not None
    assert log.after["match_status"] == "appealed"
    assert log.after["has_attachment"] is True

    [event] = [
        row
        for row in session.exec(
            select(OutboxEvent).where(OutboxEvent.type == "AppealFiled")
        ).all()
        if row.payload["match_id"] == str(setup.match_id)
    ]
    assert event.payload == {
        "appeal_id": str(appeal.id),
        "match_id": str(setup.match_id),
        "team_id": str(setup.team_a),
    }


def test_second_team_files_while_appealed(
    client: TestClient, session: Session, setup: Setup
) -> None:
    assert _file(client, setup, setup.captain_a).status_code == 201

    response = _file(client, setup, setup.captain_b, description="比分登錄錯誤")

    assert response.status_code == 201, response.text
    assert response.json()["team_id"] == str(setup.team_b)
    assert response.json()["has_attachment"] is False
    assert setup.match(session).status == MatchStatus.APPEALED
    assert _counts(session, setup) == (2, 2, 2)
    log = session.exec(
        select(audit.AuditLog)
        .where(audit.AuditLog.action == "appeal.filed")
        .where(audit.AuditLog.actor_id == setup.captain_b.id)
    ).one()
    assert log.before == {"match_status": "appealed"}


def test_jpeg_attachment_and_description_is_trimmed(
    client: TestClient, setup: Setup
) -> None:
    response = _file(
        client,
        setup,
        setup.captain_b,
        description="  多行說明\n第二行  ",
        attachment=("p.jpg", JPEG, "image/jpeg"),
    )

    assert response.status_code == 201, response.text
    assert response.json()["description"] == "多行說明\n第二行"


def test_empty_file_field_counts_as_no_attachment(
    client: TestClient, setup: Setup, upload_dir: Path
) -> None:
    response = _file(
        client, setup, setup.captain_a, attachment=("", b"", "application/octet-stream")
    )

    assert response.status_code == 201, response.text
    assert response.json()["has_attachment"] is False
    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 拒絕：不留任何痕跡


def test_duplicate_appeal_is_rejected(
    client: TestClient, session: Session, setup: Setup, upload_dir: Path
) -> None:
    assert _file(client, setup, setup.captain_a).status_code == 201

    response = _file(
        client, setup, setup.captain_a, attachment=("p.png", PNG, "image/png")
    )

    assert response.status_code == 409
    assert _code(response) == "APPEAL_ALREADY_FILED"
    assert _counts(session, setup) == (1, 1, 1)
    assert _files(upload_dir) == []


@pytest.mark.parametrize(
    "now",
    [DEADLINE, DEADLINE + timedelta(seconds=1)],
    ids=["at-deadline", "after-deadline"],
)
def test_deadline_passed(
    client: TestClient,
    session: Session,
    setup: Setup,
    upload_dir: Path,
    frozen_clock: FrozenClock,
    now: datetime,
) -> None:
    frozen_clock.set(now)

    response = _file(
        client, setup, setup.captain_a, attachment=("p.png", PNG, "image/png")
    )

    assert response.status_code == 409
    assert _code(response) == "APPEAL_DEADLINE_PASSED"
    assert setup.match(session).status == MatchStatus.APPEAL_WINDOW
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


def test_just_before_deadline_is_accepted(
    client: TestClient, setup: Setup, frozen_clock: FrozenClock
) -> None:
    frozen_clock.set(DEADLINE - timedelta(seconds=1))

    assert _file(client, setup, setup.captain_a).status_code == 201


@pytest.mark.parametrize(
    "status",
    [MatchStatus.SCHEDULED, MatchStatus.LIVE, MatchStatus.CONFIRMED],
)
def test_wrong_match_status(
    client: TestClient,
    session: Session,
    setup: Setup,
    upload_dir: Path,
    status: MatchStatus,
) -> None:
    setup.set_match(session, status=status)

    response = _file(
        client, setup, setup.captain_a, attachment=("p.png", PNG, "image/png")
    )

    assert response.status_code == 409
    assert _code(response) == "APPEAL_NOT_ALLOWED"
    assert setup.match(session).status == status
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


@pytest.mark.parametrize(
    "tournament_status", [TournamentStatus.FINISHED, TournamentStatus.CANCELLED]
)
def test_ended_tournament_rejects_appeal(
    client: TestClient,
    session: Session,
    setup: Setup,
    upload_dir: Path,
    tournament_status: TournamentStatus,
) -> None:
    """賽事已結束或已取消時，申訴期的場次也不能申訴（與 6.4 檢舉一致）。"""
    tournament = session.get(Tournament, setup.tournament_id)
    assert tournament is not None
    tournament.status = tournament_status
    session.add(tournament)
    session.commit()

    state = _state(client, setup, setup.captain_a)
    response = _file(
        client, setup, setup.captain_a, attachment=("p.png", PNG, "image/png")
    )

    assert state["can_file"] is False
    assert state["reason"] == "not_appealable"
    assert response.status_code == 409
    assert _code(response) == "APPEAL_NOT_ALLOWED"
    assert setup.match(session).status == MatchStatus.APPEAL_WINDOW
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


def test_not_captain_is_forbidden(
    client: TestClient, session: Session, setup: Setup, upload_dir: Path
) -> None:
    for account in (setup.player, setup.organizer):
        response = _file(client, setup, account, attachment=("p.png", PNG, "image/png"))
        assert response.status_code == 403
        assert _code(response) == "CAPTAIN_REQUIRED"
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


def test_unauthenticated_is_401(client: TestClient, setup: Setup) -> None:
    response = client.post(setup.url(), data={"description": "x"})

    assert response.status_code == 401


def test_unverified_account_is_403(
    client: TestClient, session: Session, setup: Setup
) -> None:
    unverified = make_account(session, verified=False)
    session.commit()

    response = _file(client, setup, unverified)

    assert response.status_code == 403
    assert _code(response) == "EMAIL_NOT_VERIFIED"


def test_match_from_another_tournament_is_not_found(
    client: TestClient,
    session: Session,
    setup: Setup,
    fake_registration: FakeRegistration,  # noqa: F811
) -> None:
    _other, bracket = draw_with(session, fake_registration, 2)
    session.commit()

    response = _file(client, setup, setup.captain_a, match_id=bracket.matches[0].id)
    missing = _file(client, setup, setup.captain_a, match_id=uuid.uuid4())

    assert response.status_code == 404
    assert _code(response) == "MATCH_NOT_FOUND"
    assert missing.status_code == 404
    assert _code(missing) == "MATCH_NOT_FOUND"


@pytest.mark.parametrize(
    ("description", "code"),
    [
        ("", "APPEAL_DESCRIPTION_REQUIRED"),
        ("   \n ", "APPEAL_DESCRIPTION_REQUIRED"),
        ("字" * 1001, "APPEAL_DESCRIPTION_TOO_LONG"),
    ],
)
def test_description_field_errors(
    client: TestClient,
    session: Session,
    setup: Setup,
    upload_dir: Path,
    description: str,
    code: str,
) -> None:
    response = _file(
        client,
        setup,
        setup.captain_a,
        description=description,
        attachment=("p.png", PNG, "image/png"),
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == code
    assert error["loc"] == ["body", "description"]
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


@pytest.mark.parametrize(
    ("description", "stored"),
    [
        ("ab", "ab"),
        ("比分‮有誤", "比分有誤"),
        ("⁦隔離⁩", "隔離"),
        ("第一點	第二點", "第一點	第二點"),
        # 組合 emoji（U+200D）保留
        ("證據 👨‍👩‍👧", "證據 👨‍👩‍👧"),
    ],
    ids=["bell", "bidi-override", "bidi-isolate", "tab", "zwj-emoji"],
)
def test_description_control_characters(
    client: TestClient, setup: Setup, description: str, stored: str
) -> None:
    response = _file(client, setup, setup.captain_a, description=description)

    assert response.status_code == 201, response.text
    assert response.json()["description"] == stored


def test_description_of_only_control_characters_is_required(
    client: TestClient, setup: Setup
) -> None:
    response = _file(client, setup, setup.captain_a, description="‮⁦")

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == "APPEAL_DESCRIPTION_REQUIRED"


def test_commit_failure_deletes_the_attachment(
    client: TestClient,
    setup: Setup,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client, setup.captain_a)

    def boom(_self: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        client.post(
            setup.url(),
            data={"description": "比分有誤"},
            files={"attachment": ("p.png", PNG, "image/png")},
            headers=headers,
        )

    assert _files(upload_dir) == []


def test_description_of_1000_characters_is_accepted(
    client: TestClient, setup: Setup
) -> None:
    response = _file(client, setup, setup.captain_a, description="字" * 1000)

    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    ("attachment", "status_code", "code"),
    [
        (("a.gif", GIF, "image/gif"), 415, "UNSUPPORTED_FILE_TYPE"),
        (("a.jpg", PNG, "image/jpeg"), 415, "UNSUPPORTED_FILE_TYPE"),
        (
            ("a.png", PNG + b"\0" * (MAX_IMAGE_BYTES + 1 - len(PNG)), "image/png"),
            413,
            "FILE_TOO_LARGE",
        ),
    ],
    ids=["gif", "mismatched-magic", "too-large"],
)
def test_bad_attachment_creates_nothing(
    client: TestClient,
    session: Session,
    setup: Setup,
    upload_dir: Path,
    attachment: tuple[str, bytes, str],
    status_code: int,
    code: str,
) -> None:
    response = _file(client, setup, setup.captain_a, attachment=attachment)

    assert response.status_code == status_code
    assert _code(response) == code
    assert setup.match(session).status == MatchStatus.APPEAL_WINDOW
    assert _counts(session, setup) == (0, 0, 0)
    assert _files(upload_dir) == []


def test_unique_key_is_the_last_line_of_defence(
    session: Session,
    setup: Setup,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """鎖之外的併發重複送出：前面的檢查沒擋到時，唯一鍵擋下並刪掉剛存的附件。"""
    service.file_appeal(
        session,
        tournament_id=setup.tournament_id,
        match_id=setup.match_id,
        account_id=setup.captain_a.id,
        description="第一次",
        attachment=None,
        content_type=None,
    )
    monkeypatch.setattr(repository, "find_team_appeal", lambda *_args: None)

    with pytest.raises(BusinessError) as caught:
        service.file_appeal(
            session,
            tournament_id=setup.tournament_id,
            match_id=setup.match_id,
            account_id=setup.captain_a.id,
            description="第二次",
            attachment=io.BytesIO(PNG),
            content_type="image/png",
        )

    assert caught.value.code == "APPEAL_ALREADY_FILED"
    assert _counts(session, setup) == (1, 1, 1)
    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 申訴狀態（S4 入口）


def test_state_for_captain_before_filing(client: TestClient, setup: Setup) -> None:
    assert _state(client, setup, setup.captain_a) == {
        "can_file": True,
        "already_filed": False,
        "deadline": "2026-10-18T11:30:00Z",
        "reason": None,
    }


def test_state_does_not_reveal_the_other_team(client: TestClient, setup: Setup) -> None:
    assert _file(client, setup, setup.captain_a).status_code == 201

    own = _state(client, setup, setup.captain_a)
    other = _state(client, setup, setup.captain_b)

    assert own["can_file"] is False
    assert own["already_filed"] is True
    assert own["reason"] == "already_filed"
    assert other == {
        "can_file": True,
        "already_filed": False,
        "deadline": "2026-10-18T11:30:00Z",
        "reason": None,
    }


def test_state_for_non_captains(client: TestClient, setup: Setup) -> None:
    for account in (setup.player, setup.organizer):
        state = _state(client, setup, account)
        assert state["can_file"] is False
        assert state["already_filed"] is False
        assert state["reason"] == "not_captain"


def test_state_after_deadline_still_reports_filed(
    client: TestClient, setup: Setup, frozen_clock: FrozenClock
) -> None:
    assert _file(client, setup, setup.captain_a).status_code == 201
    frozen_clock.set(DEADLINE)

    own = _state(client, setup, setup.captain_a)
    other = _state(client, setup, setup.captain_b)

    assert own["reason"] == "deadline_passed"
    assert own["already_filed"] is True
    assert other["reason"] == "deadline_passed"
    assert other["already_filed"] is False
    assert other["can_file"] is False


def test_state_for_wrong_status_has_no_deadline(
    client: TestClient, session: Session, setup: Setup
) -> None:
    setup.set_match(session, status=MatchStatus.CONFIRMED)

    state = _state(client, setup, setup.captain_a)

    assert state == {
        "can_file": False,
        "already_filed": False,
        "deadline": None,
        "reason": "not_appealable",
    }


def test_state_requires_login_and_matching_tournament(
    client: TestClient, setup: Setup
) -> None:
    assert client.get(setup.url("appeal-state")).status_code == 401
    response = client.get(
        setup.url("appeal-state", match_id=uuid.uuid4()),
        headers=_auth(client, setup.captain_a),
    )
    assert response.status_code == 404
    assert _code(response) == "MATCH_NOT_FOUND"


# ---------------------------------------------------------------- 公開 API 不含申訴內容


def test_public_match_has_no_appeal_content(client: TestClient, setup: Setup) -> None:
    description = "公開頁不能出現的申訴內容-7f3a"
    assert (
        _file(client, setup, setup.captain_a, description=description).status_code
        == 201
    )

    public = client.get(
        f"{API}/tournaments/{setup.tournament_id}/matches/{setup.match_id}"
    )
    bracket = client.get(f"{API}/tournaments/{setup.tournament_id}/bracket")

    assert public.status_code == 200
    assert public.json()["status"] == "appealed"
    for response in (public, bracket):
        assert description not in response.text
        assert "attachment" not in response.text
        assert str(setup.captain_a.id) not in response.text


# ---------------------------------------------------------------- 附件下載


def _appeal_with_attachment(
    client: TestClient, setup: Setup, attachment: tuple[str, bytes, str]
) -> str:
    response = _file(client, setup, setup.captain_a, attachment=attachment)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.mark.parametrize(
    ("attachment", "media_type"),
    [
        (("p.png", PNG, "image/png"), "image/png"),
        (("p.jpg", JPEG, "image/jpeg"), "image/jpeg"),
    ],
)
def test_organizer_downloads_attachment(
    client: TestClient,
    setup: Setup,
    attachment: tuple[str, bytes, str],
    media_type: str,
) -> None:
    appeal_id = _appeal_with_attachment(client, setup, attachment)

    response = client.get(
        f"{API}/organizer/appeals/{appeal_id}/attachment",
        headers=_auth(client, setup.organizer),
    )

    assert response.status_code == 200
    assert response.content == attachment[1]
    assert response.headers["content-type"] == media_type
    assert response.headers["x-content-type-options"] == "nosniff"


def test_missing_stored_file_is_not_found(
    client: TestClient, session: Session, setup: Setup, upload_dir: Path
) -> None:
    appeal_id = _appeal_with_attachment(client, setup, ("p.png", PNG, "image/png"))
    appeal = session.get(Appeal, uuid.UUID(appeal_id))
    assert appeal is not None and appeal.attachment_key is not None
    (upload_dir / appeal.attachment_key).unlink()

    response = client.get(
        f"{API}/organizer/appeals/{appeal_id}/attachment",
        headers=_auth(client, setup.organizer),
    )

    assert response.status_code == 404
    assert _code(response) == "FILE_NOT_FOUND"


def test_others_cannot_download_attachment(
    client: TestClient, session: Session, setup: Setup
) -> None:
    appeal_id = _appeal_with_attachment(client, setup, ("p.png", PNG, "image/png"))
    other_organizer = make_account(session, organizer=True)
    session.commit()
    url = f"{API}/organizer/appeals/{appeal_id}/attachment"

    other = client.get(url, headers=_auth(client, other_organizer))
    captain = client.get(url, headers=_auth(client, setup.captain_a))
    anonymous = client.get(url)

    assert other.status_code == 403
    assert _code(other) == "TOURNAMENT_OWNER_REQUIRED"
    assert captain.status_code == 403
    assert _code(captain) == "ORGANIZER_REQUIRED"
    assert anonymous.status_code == 401


def test_download_without_attachment_or_unknown_appeal(
    client: TestClient, setup: Setup
) -> None:
    response = _file(client, setup, setup.captain_a)
    appeal_id = response.json()["id"]
    headers = _auth(client, setup.organizer)

    no_file = client.get(
        f"{API}/organizer/appeals/{appeal_id}/attachment", headers=headers
    )
    unknown = client.get(
        f"{API}/organizer/appeals/{uuid.uuid4()}/attachment", headers=headers
    )

    assert no_file.status_code == 404
    assert _code(no_file) == "FILE_NOT_FOUND"
    assert unknown.status_code == 404
    assert _code(unknown) == "APPEAL_NOT_FOUND"


# ---------------------------------------------------------------- 與 worker 期滿確認互斥（依序）


def test_worker_after_appeal_leaves_match_appealed(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
) -> None:
    assert _file(client, setup, setup.captain_a).status_code == 201
    frozen_clock.set(DEADLINE)

    competition_service.auto_confirm_expired(session)

    assert setup.match(session).status == MatchStatus.APPEALED


def test_appeal_after_worker_confirmed_is_rejected(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
) -> None:
    frozen_clock.set(DEADLINE)
    assert competition_service.auto_confirm_expired(session) is True
    session.commit()
    assert setup.match(session).status == MatchStatus.CONFIRMED
    status = tournaments_service.get_tournament(
        session, tournament_id=setup.tournament_id
    ).status

    response = _file(client, setup, setup.captain_a)

    assert response.status_code == 409
    assert _code(response) == "APPEAL_NOT_ALLOWED"
    assert _counts(session, setup) == (0, 0, 0)
    assert status == "finished"
