"""結算截圖（Story 5.7、FR-28、AD-15）：勝隊隊長上傳／更換、公開下載、能否上傳。

由 `service.py` 的公開函式呼叫。截圖只是佐證：這裡不改場次狀態、期限與晉級，
確認與晉級流程也不讀這張表。不 commit（AD-5）。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import BinaryIO

from sqlmodel import Session

from app.core import audit, clock, storage
from app.core.errors import BusinessError
from app.modules.competition import registration_port, repository
from app.modules.competition.models import (
    Match,
    MatchOutcome,
    ResultScreenshot,
    ResultScreenshotReason,
    ResultScreenshotState,
)

_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png"}

# 原因代碼對應上傳 API 的錯誤碼、狀態碼與訊息
_REJECTIONS: dict[ResultScreenshotReason, tuple[str, int, str]] = {
    "result_not_submitted": (
        "RESULT_NOT_SUBMITTED",
        409,
        "系列結果送出後才能上傳結算截圖。",
    ),
    "not_winning_captain": (
        "WINNING_CAPTAIN_REQUIRED",
        403,
        "只有勝隊隊長可以上傳結算截圖。",
    ),
}


@dataclass(frozen=True)
class UploadedScreenshot:
    """`upload` 的結果。

    `new_key`：這次存下的檔案鍵值；交易提交失敗時由 router 刪除。
    `old_key`：被換掉的舊檔案鍵值（第一次上傳為 None）；交易提交後由 router 刪除。
    """

    state: ResultScreenshotState
    new_key: str
    old_key: str | None


def _not_found() -> BusinessError:
    return BusinessError(
        "RESULT_SCREENSHOT_NOT_FOUND", "這場比賽沒有結算截圖。", status_code=404
    )


def is_result_submitted(match: Match) -> bool:
    """系列結果已送出：正常完賽且有送出時間（判棄權、輪空、取消資格判負都不算）。"""
    return match.outcome == MatchOutcome.PLAYED and match.submitted_at is not None


def visible_at(match: Match, row: ResultScreenshot | None) -> datetime | None:
    """這張截圖現在可公開時回傳上傳時間，否則 None。

    上傳的隊伍要是目前的勝隊（申訴更正換勝隊後，原勝隊的圖不再公開），且上傳時間
    不早於這次送出結果的時間（重新比賽後殘留的舊列不算）。
    """
    if row is None or not is_result_submitted(match):
        return None
    assert match.submitted_at is not None
    if row.team_id != match.winner_id or row.created_at < match.submitted_at:
        return None
    return row.created_at


def _evaluate(
    session: Session, *, match: Match, account_id: uuid.UUID
) -> ResultScreenshotReason | None:
    """上傳與狀態查詢共用的檢查；可以上傳時為 None。

    未送出時沒有勝隊，所以先判斷已送出，再判斷勝隊隊長。
    """
    if not is_result_submitted(match) or match.winner_id is None:
        return "result_not_submitted"
    if not registration_port.is_captain(
        session, team_id=match.winner_id, account_id=account_id
    ):
        return "not_winning_captain"
    return None


def get_state(
    session: Session, *, match: Match, account_id: uuid.UUID
) -> ResultScreenshotState:
    reason = _evaluate(session, match=match, account_id=account_id)
    return ResultScreenshotState(can_upload=reason is None, reason=reason)


def upload(
    session: Session,
    *,
    match: Match,
    account_id: uuid.UUID,
    screenshot: BinaryIO,
    content_type: str | None,
) -> UploadedScreenshot:
    """勝隊隊長上傳或更換結算截圖；`match` 必須是呼叫端鎖住後的最新值。

    檢查全部通過才存圖片；圖片存下之後的步驟失敗時，在這裡刪掉新檔再往外拋。
    """
    reason = _evaluate(session, match=match, account_id=account_id)
    if reason is not None:
        code, status_code, message = _REJECTIONS[reason]
        raise BusinessError(code, message, status_code=status_code)
    assert match.winner_id is not None  # `_evaluate` 已確認有勝隊

    new_key = storage.save_image(screenshot, content_type=content_type)
    try:
        now = clock.now()
        old_key = repository.save_result_screenshot(
            session,
            match_id=match.id,
            team_id=match.winner_id,
            file_key=new_key,
            uploaded_by=account_id,
            at=now,
        )
        # 公開單場的 updated_at 取自場次；不更新的話輪詢的觀眾不會重抓
        repository.touch_match(session, match, now)
        audit.record(
            session,
            actor_id=account_id,
            tournament_id=match.tournament_id,
            action="match.result_screenshot_uploaded",
            entity_type="match",
            entity_id=match.id,
            before={"had_screenshot": old_key is not None},
            after={"team_id": match.winner_id, "at": now},
        )
    except BaseException:
        storage.delete_file(new_key)
        raise
    return UploadedScreenshot(
        state=ResultScreenshotState(can_upload=True, reason=None),
        new_key=new_key,
        old_key=old_key,
    )


def open_public(session: Session, *, match: Match) -> tuple[BinaryIO, str]:
    """公開的結算截圖（二進位串流、Content-Type）；呼叫端負責關閉串流。

    沒有可公開的截圖拋 404 `RESULT_SCREENSHOT_NOT_FOUND`；檔案不見拋 404 `FILE_NOT_FOUND`。
    """
    row = repository.get_result_screenshot(session, match.id)
    if row is None or visible_at(match, row) is None:
        raise _not_found()
    media_type = _MEDIA_TYPES.get(PurePath(row.file_key).suffix)
    if media_type is None:
        raise _not_found()
    return storage.open_file(row.file_key), media_type
