"""Story 5.7：勝隊隊長上傳／更換結算截圖、公開下載、能否上傳的狀態查詢。

沿用 5.3 的 `Setup`（8 隊、M1 兩隊已報到、主辦方記分、BO3、申訴 30 分鐘）。
預設由主辦方登錄「aa」並送出，所以 a 隊是勝隊、場次在申訴期。
"""

import io
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import audit, clock
from app.core.config import settings
from app.core.storage import MAX_IMAGE_BYTES
from app.modules.competition import registration_port, result_screenshot, service
from app.modules.competition.models import (
    GameScoreIn,
    Match,
    MatchOutcome,
    MatchStatus,
    ResultScreenshot,
)
from app.modules.identity.models import Account
from app.worker import jobs, run_once
from tests.competition.conftest import FrozenClockLike
from tests.competition.test_score_entry import (  # noqa: F401  (fixture)
    Factory,
    Setup,
    make_setup,
)
from tests.helpers import bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

PNG = b"\x89PNG\r\n\x1a\n" + b"settlement"
JPG = b"\xff\xd8\xff" + b"replaced"
APPEAL = timedelta(minutes=30)


class Scene:
    """`Setup` 加上每隊一位隊長（替身 `is_captain`）與一位無關的帳號。"""

    def __init__(self, session: Session, setup: Setup) -> None:
        self.setup = setup
        self.captains: dict[uuid.UUID, Account] = {
            team_id: make_account(session) for team_id in setup.fake.teams
        }
        self.outsider = make_account(session)
        self.referee = make_account(session)

    def captain(self, side: str) -> Account:
        return self.captains[self.setup.team(side)]

    @property
    def url(self) -> str:
        return f"{self.setup.base()}/result-screenshot"

    @property
    def state_url(self) -> str:
        return f"{self.setup.base()}/result-screenshot-state"


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


@pytest.fixture
def scene(
    session: Session,
    make_setup: Factory,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    upload_dir: Path,
) -> Scene:
    result = Scene(session, make_setup())

    def is_captain(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        captain = result.captains.get(team_id)
        return captain is not None and captain.id == account_id

    monkeypatch.setattr(registration_port, "is_captain", is_captain)
    session.commit()
    return result


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def _submit(client: TestClient, scene: Scene, sides: str = "aa") -> None:
    """主辦方登錄各局並送出系列結果；場次進入申訴期。"""
    headers = _headers(client, scene.setup.organizer)
    for no, side in enumerate(sides, start=1):
        response = client.put(
            scene.setup.game_url(no), json={"winner_side": side}, headers=headers
        )
        assert response.status_code == 200, response.text
    response = client.post(f"{scene.setup.base()}/submit", headers=headers)
    assert response.status_code == 200, response.text


def _upload(
    client: TestClient,
    scene: Scene,
    account: Account,
    file: tuple[str, bytes, str] = ("result.png", PNG, "image/png"),
) -> Any:
    return client.put(
        scene.url, files={"screenshot": file}, headers=_headers(client, account)
    )


def _match(session: Session, scene: Scene, code: str = "M1") -> Match:
    session.expire_all()
    match = session.get(Match, scene.setup.match_id(code))
    assert match is not None
    return match


def _rows(session: Session) -> list[ResultScreenshot]:
    session.expire_all()
    return list(session.exec(select(ResultScreenshot)))


def _files(upload_dir: Path) -> list[str]:
    return sorted(p.name for p in upload_dir.iterdir())


def _audit_actions(session: Session, scene: Scene) -> list[str]:
    rows = session.exec(
        select(audit.AuditLog).where(
            audit.AuditLog.entity_id == scene.setup.match_id(),
            audit.AuditLog.action == "match.result_screenshot_uploaded",
        )
    )
    return [row.action for row in rows]


# ---------------------------------------------------------------- 上傳與公開下載


def test_winning_captain_uploads_and_anyone_can_download(
    client: TestClient, session: Session, scene: Scene, upload_dir: Path
) -> None:
    _submit(client, scene)
    before = _match(session, scene)
    status, deadline = before.status, before.appeal_deadline

    response = _upload(client, scene, scene.captain("a"))

    assert response.status_code == 200, response.text
    assert response.json() == {"can_upload": True, "reason": None}
    [row] = _rows(session)
    assert row.match_id == scene.setup.match_id()
    assert row.team_id == scene.setup.team("a")
    assert row.uploaded_by == scene.captain("a").id
    assert _files(upload_dir) == [row.file_key]
    assert (upload_dir / row.file_key).read_bytes() == PNG

    # 公開單場（未登入）：有上傳時間，不含檔案鍵值（AD-19）
    public = client.get(scene.setup.base())
    assert public.status_code == 200
    body = public.json()
    assert body["result_screenshot_enabled"] is True
    assert body["result_screenshot_at"] is not None
    assert row.file_key not in public.text

    # 公開下載（未登入）
    image = client.get(scene.url)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.headers["content-disposition"] == "inline"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.content == PNG

    # 不影響場次狀態與期限；寫一筆操作紀錄
    after = _match(session, scene)
    assert (after.status, after.appeal_deadline) == (status, deadline)
    assert after.confirmed_at is None
    assert _audit_actions(session, scene) == ["match.result_screenshot_uploaded"]


def test_upload_touches_match_so_polling_clients_refetch(
    client: TestClient, scene: Scene, frozen_clock: FrozenClockLike
) -> None:
    _submit(client, scene)
    before = client.get(scene.setup.base()).json()["updated_at"]
    frozen_clock.advance(timedelta(minutes=1))

    assert _upload(client, scene, scene.captain("a")).status_code == 200

    assert client.get(scene.setup.base()).json()["updated_at"] > before


def test_replace_keeps_one_row_and_deletes_the_old_file(
    client: TestClient, session: Session, scene: Scene, upload_dir: Path
) -> None:
    _submit(client, scene)
    assert _upload(client, scene, scene.captain("a")).status_code == 200
    [first] = _rows(session)
    old_key = first.file_key

    response = _upload(
        client, scene, scene.captain("a"), ("new.jpg", JPG, "image/jpeg")
    )

    assert response.status_code == 200, response.text
    [row] = _rows(session)
    assert row.file_key != old_key
    assert _files(upload_dir) == [row.file_key]
    image = client.get(scene.url)
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content == JPG
    assert len(_audit_actions(session, scene)) == 2


# ---------------------------------------------------------------- 拒絕


@pytest.mark.parametrize("who", ["loser_captain", "organizer", "referee", "outsider"])
def test_only_the_winning_captain_can_upload(
    client: TestClient, session: Session, scene: Scene, upload_dir: Path, who: str
) -> None:
    _submit(client, scene)
    account = {
        "loser_captain": scene.captain("b"),
        "organizer": scene.setup.organizer,
        "referee": scene.referee,
        "outsider": scene.outsider,
    }[who]

    response = _upload(client, scene, account)

    assert response.status_code == 403
    assert _code(response) == "WINNING_CAPTAIN_REQUIRED"
    assert _rows(session) == []
    assert _files(upload_dir) == []
    assert _audit_actions(session, scene) == []
    assert client.get(scene.url).status_code == 404


def test_upload_requires_login(client: TestClient, scene: Scene) -> None:
    _submit(client, scene)

    response = client.put(
        scene.url, files={"screenshot": ("result.png", PNG, "image/png")}
    )

    assert response.status_code == 401


def test_upload_before_result_is_submitted_is_rejected(
    client: TestClient, session: Session, scene: Scene, upload_dir: Path
) -> None:
    # 只登錄一局、尚未送出：場次進行中
    headers = _headers(client, scene.setup.organizer)
    client.put(scene.setup.game_url(1), json={"winner_side": "a"}, headers=headers)

    response = _upload(client, scene, scene.captain("a"))

    assert response.status_code == 409
    assert _code(response) == "RESULT_NOT_SUBMITTED"
    assert _rows(session) == []
    assert _files(upload_dir) == []
    public = client.get(scene.setup.base()).json()
    assert public["result_screenshot_enabled"] is False
    assert public["result_screenshot_at"] is None


@pytest.mark.parametrize(
    "outcome",
    [MatchOutcome.FORFEIT, MatchOutcome.WALKOVER, MatchOutcome.DISQUALIFIED],
)
def test_matches_without_a_submitted_series_cannot_take_a_screenshot(
    client: TestClient,
    session: Session,
    scene: Scene,
    upload_dir: Path,
    outcome: MatchOutcome,
) -> None:
    # 判棄權、輪空、取消資格判負：有勝隊，但沒有送出系列結果
    match = _match(session, scene)
    match.status = MatchStatus.CONFIRMED
    match.outcome = outcome
    match.winner_id = scene.setup.team("a")
    session.add(match)
    session.commit()

    response = _upload(client, scene, scene.captain("a"))

    assert response.status_code == 409
    assert _code(response) == "RESULT_NOT_SUBMITTED"
    assert _files(upload_dir) == []
    assert client.get(scene.setup.base()).json()["result_screenshot_enabled"] is False


@pytest.mark.parametrize(
    ("file", "status_code", "code"),
    [
        (("a.gif", b"GIF89a....", "image/gif"), 415, "UNSUPPORTED_FILE_TYPE"),
        (("a.png", b"just text", "image/png"), 415, "UNSUPPORTED_FILE_TYPE"),
        (("a.jpg", PNG, "image/jpeg"), 415, "UNSUPPORTED_FILE_TYPE"),
        (
            ("a.png", PNG + b"\0" * (MAX_IMAGE_BYTES + 1 - len(PNG)), "image/png"),
            413,
            "FILE_TOO_LARGE",
        ),
    ],
)
def test_invalid_images_are_rejected_and_leave_nothing(
    client: TestClient,
    session: Session,
    scene: Scene,
    upload_dir: Path,
    file: tuple[str, bytes, str],
    status_code: int,
    code: str,
) -> None:
    _submit(client, scene)

    response = _upload(client, scene, scene.captain("a"), file)

    assert response.status_code == status_code
    assert _code(response) == code
    assert _rows(session) == []
    assert _files(upload_dir) == []


def test_image_of_exactly_5_mb_is_accepted(client: TestClient, scene: Scene) -> None:
    _submit(client, scene)
    exact = PNG + b"\0" * (MAX_IMAGE_BYTES - len(PNG))

    response = _upload(client, scene, scene.captain("a"), ("a.png", exact, "image/png"))

    assert response.status_code == 200, response.text


def test_missing_file_is_a_field_error(client: TestClient, scene: Scene) -> None:
    _submit(client, scene)

    response = client.put(scene.url, headers=_headers(client, scene.captain("a")))

    assert response.status_code == 422


def test_match_of_another_tournament_is_not_found(
    client: TestClient, scene: Scene
) -> None:
    _submit(client, scene)
    other = f"{scene.setup.base(tournament_id=uuid.uuid4())}/result-screenshot"
    headers = _headers(client, scene.captain("a"))

    upload = client.put(
        other, files={"screenshot": ("a.png", PNG, "image/png")}, headers=headers
    )

    assert upload.status_code == 404
    assert _code(upload) == "MATCH_NOT_FOUND"
    assert _code(client.get(other)) == "MATCH_NOT_FOUND"
    assert _code(client.get(f"{other}-state", headers=headers)) == "MATCH_NOT_FOUND"


def test_download_without_a_screenshot_is_not_found(
    client: TestClient, scene: Scene
) -> None:
    _submit(client, scene)

    response = client.get(scene.url)

    assert response.status_code == 404
    assert _code(response) == "RESULT_SCREENSHOT_NOT_FOUND"


def test_failure_after_saving_the_image_deletes_it(
    session: Session,
    client: TestClient,
    scene: Scene,
    upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _submit(client, scene)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(audit, "record", boom)
    with pytest.raises(RuntimeError):
        service.upload_result_screenshot(
            session,
            tournament_id=scene.setup.tournament_id,
            match_id=scene.setup.match_id(),
            account_id=scene.captain("a").id,
            screenshot=io.BytesIO(PNG),
            content_type="image/png",
        )
    session.rollback()

    assert _files(upload_dir) == []


# ---------------------------------------------------------------- 不影響確認與晉級


def test_no_screenshot_does_not_block_confirmation_and_advancement(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    scene: Scene,
    frozen_clock: FrozenClockLike,
) -> None:
    _submit(client, scene)
    frozen_clock.set(clock.now() + APPEAL)

    run_once([jobs.confirm_expired_appeals], session_factory=session_factory)

    match = _match(session, scene)
    assert match.status == MatchStatus.CONFIRMED
    assert _rows(session) == []
    next_match = _match(session, scene, scene.setup.next_code())
    assert scene.setup.team("a") in (next_match.team_a_id, next_match.team_b_id)
    # 區塊照樣顯示（未上傳）
    public = client.get(scene.setup.base()).json()
    assert public["result_screenshot_enabled"] is True
    assert public["result_screenshot_at"] is None


def test_upload_and_replace_still_work_after_confirmation(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    scene: Scene,
    frozen_clock: FrozenClockLike,
) -> None:
    # 決定 1：沒有上傳期限
    _submit(client, scene)
    frozen_clock.set(clock.now() + APPEAL)
    run_once([jobs.confirm_expired_appeals], session_factory=session_factory)
    confirmed = _match(session, scene)
    assert confirmed.status == MatchStatus.CONFIRMED
    confirmed_at = confirmed.confirmed_at

    assert _upload(client, scene, scene.captain("a")).status_code == 200
    assert (
        _upload(client, scene, scene.captain("a"), ("b.jpg", JPG, "image/jpeg"))
    ).status_code == 200

    after = _match(session, scene)
    assert (after.status, after.confirmed_at) == (MatchStatus.CONFIRMED, confirmed_at)
    assert client.get(scene.url).content == JPG


# ---------------------------------------------------------------- 申訴更正換勝隊


def test_correction_that_flips_the_winner_hides_the_old_screenshot(
    client: TestClient,
    session: Session,
    scene: Scene,
    upload_dir: Path,
    frozen_clock: FrozenClockLike,
) -> None:
    _submit(client, scene)
    assert _upload(client, scene, scene.captain("a")).status_code == 200
    [old] = _rows(session)
    old_key = old.file_key

    frozen_clock.advance(timedelta(minutes=5))
    service.mark_appealed(session, match_id=scene.setup.match_id())
    service.correct_result(
        session,
        match_id=scene.setup.match_id(),
        games=[GameScoreIn(winner_side="b"), GameScoreIn(winner_side="b")],
        actor_id=scene.setup.organizer.id,
    )
    session.commit()
    assert _match(session, scene).winner_id == scene.setup.team("b")

    # 原勝隊的圖不再公開，區塊回到未上傳
    public = client.get(scene.setup.base()).json()
    assert public["result_screenshot_enabled"] is True
    assert public["result_screenshot_at"] is None
    assert _code(client.get(scene.url)) == "RESULT_SCREENSHOT_NOT_FOUND"

    # 原勝隊隊長不能再上傳；新勝隊隊長可以，舊檔在提交後刪除
    rejected = _upload(client, scene, scene.captain("a"))
    assert _code(rejected) == "WINNING_CAPTAIN_REQUIRED"
    frozen_clock.advance(timedelta(minutes=1))
    accepted = _upload(client, scene, scene.captain("b"), ("b.jpg", JPG, "image/jpeg"))
    assert accepted.status_code == 200, accepted.text

    [row] = _rows(session)
    assert row.team_id == scene.setup.team("b")
    assert _files(upload_dir) == [row.file_key]
    assert row.file_key != old_key
    assert client.get(scene.url).content == JPG
    assert client.get(scene.setup.base()).json()["result_screenshot_at"] is not None


def test_screenshot_older_than_the_current_submission_is_not_visible(
    client: TestClient, session: Session, scene: Scene
) -> None:
    # 重新比賽後殘留的舊列：上傳時間早於這次送出結果的時間
    _submit(client, scene)
    match = _match(session, scene)
    assert match.submitted_at is not None
    row = ResultScreenshot(
        match_id=match.id,
        team_id=scene.setup.team("a"),
        file_key="0" * 32 + ".png",
        uploaded_by=scene.captain("a").id,
        created_at=match.submitted_at - timedelta(seconds=1),
    )

    assert result_screenshot.visible_at(match, row) is None
    row.created_at = match.submitted_at
    assert result_screenshot.visible_at(match, row) == match.submitted_at
    assert result_screenshot.visible_at(match, None) is None


# ---------------------------------------------------------------- 能否上傳


def test_upload_state_matches_the_upload_checks(
    client: TestClient, scene: Scene
) -> None:
    def state(account: Account) -> dict[str, object]:
        response = client.get(scene.state_url, headers=_headers(client, account))
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        return body

    not_submitted = {"can_upload": False, "reason": "result_not_submitted"}
    assert state(scene.captain("a")) == not_submitted

    _submit(client, scene)

    assert state(scene.captain("a")) == {"can_upload": True, "reason": None}
    not_winner = {"can_upload": False, "reason": "not_winning_captain"}
    assert state(scene.captain("b")) == not_winner
    assert state(scene.setup.organizer) == not_winner
    assert state(scene.outsider) == not_winner
    assert client.get(scene.state_url).status_code == 401


def test_commit_failure_on_replace_keeps_the_old_file_and_row(
    client: TestClient,
    session: Session,
    scene: Scene,
    upload_dir: Path,
) -> None:
    # router：提交失敗刪新檔；舊檔只在提交成功後才刪
    _submit(client, scene)
    assert _upload(client, scene, scene.captain("a")).status_code == 200
    [before] = _rows(session)
    old_key = before.file_key
    headers = _headers(client, scene.captain("a"))

    def failing_commit(_self: Session) -> None:
        raise RuntimeError("commit failed")

    # 另開一個 MonkeyPatch：只還原 commit，不動 fixture 換掉的上傳資料夾與 is_captain
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Session, "commit", failing_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            client.put(
                scene.url,
                files={"screenshot": ("new.jpg", JPG, "image/jpeg")},
                headers=headers,
            )

    assert _files(upload_dir) == [old_key]
    [after] = _rows(session)
    assert after.file_key == old_key
    assert client.get(scene.url).content == PNG


def test_disqualified_after_submission_hides_the_screenshot_and_blocks_upload(
    client: TestClient, session: Session, scene: Scene
) -> None:
    # 已送出（submitted_at 有值）後被取消資格判負：outcome 不再是 played
    _submit(client, scene)
    assert _upload(client, scene, scene.captain("a")).status_code == 200
    match = _match(session, scene)
    assert match.submitted_at is not None
    match.status = MatchStatus.CONFIRMED
    match.outcome = MatchOutcome.DISQUALIFIED
    match.winner_id = scene.setup.team("b")
    session.add(match)
    session.commit()

    public = client.get(scene.setup.base()).json()
    assert public["result_screenshot_enabled"] is False
    assert public["result_screenshot_at"] is None
    assert _code(client.get(scene.url)) == "RESULT_SCREENSHOT_NOT_FOUND"
    for side in ("a", "b"):
        rejected = _upload(client, scene, scene.captain(side))
        assert rejected.status_code == 409
        assert _code(rejected) == "RESULT_NOT_SUBMITTED"
