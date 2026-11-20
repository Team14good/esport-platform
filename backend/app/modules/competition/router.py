"""competition 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.db import SessionDep
from app.core.errors import BusinessError
from app.modules.competition import service
from app.modules.competition.models import (
    BracketRead,
    CheckInRead,
    CheckInStatus,
    DrawStatus,
    GameScoreIn,
    ManagedMatch,
    MatchRead,
    NextMatch,
    PublicBracket,
    PublicMatchDetail,
    RefereeAssignIn,
    RefereeTournamentMatches,
    RescheduleIn,
    ResultScreenshotState,
    ScoreEntryState,
)
from app.modules.identity.deps import CurrentAccount, Organizer, VerifiedAccount

router = APIRouter(tags=["competition"])


@router.post("/tournaments/{tournament_id}/draw", status_code=status.HTTP_201_CREATED)
def draw(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> BracketRead:
    """抽籤並公布賽程；只限該賽事主辦方，只能抽一次。"""
    bracket = service.draw(session, tournament_id=tournament_id, actor_id=organizer.id)
    session.commit()
    return bracket


@router.get("/organizer/tournaments/{tournament_id}/draw-status")
def read_draw_status(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> DrawStatus:
    """S27 抽籤按鈕：現在能不能抽籤；與抽籤同一套檢查與分配規則預估，不寫入（不 commit）。"""
    return service.get_draw_status(
        session, tournament_id=tournament_id, actor_id=organizer.id
    )


@router.get("/tournaments/{tournament_id}/bracket")
def read_public_bracket(session: SessionDep, tournament_id: uuid.UUID) -> PublicBracket:
    """公開對戰樹（不需登入）；尚未抽籤回 404 `BRACKET_NOT_FOUND`。"""
    bracket = service.get_public_bracket(session, tournament_id=tournament_id)
    if bracket is None:
        raise BusinessError(
            "BRACKET_NOT_FOUND", "這場賽事還沒有對戰表。", status_code=404
        )
    return bracket


@router.get("/tournaments/{tournament_id}/matches/{match_id}")
def read_public_match(
    session: SessionDep, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> PublicMatchDetail:
    """公開單場（不需登入）；賽事或場次不存在、未抽籤、場次不屬於該賽事都回 404 `MATCH_NOT_FOUND`。"""
    return service.get_public_match(
        session, tournament_id=tournament_id, match_id=match_id
    )


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/check-in",
    status_code=status.HTTP_201_CREATED,
)
def check_in(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> CheckInRead:
    """隊長為本隊報到（隊伍由登入者是哪一隊的隊長推得，請求不帶隊伍）。"""
    result = service.check_in(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )
    session.commit()
    return result


@router.get("/tournaments/{tournament_id}/matches/{match_id}/check-in")
def read_check_in_status(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> CheckInStatus:
    """登入者的報到狀態：所屬一方與不能報到的原因（None 代表可報到）。"""
    return service.get_check_in_status(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )


@router.get("/tournaments/{tournament_id}/matches/{match_id}/score-entry")
def read_score_entry(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> ScoreEntryState:
    """登入者的比分登錄狀態（S4 Score entry panel）；不是記分者時 `is_scorer` 為 false、其他欄位空。"""
    return service.get_score_entry(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )


@router.put("/tournaments/{tournament_id}/matches/{match_id}/games/{game_no}")
def record_game(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    game_no: int,
    body: GameScoreIn,
) -> ScoreEntryState:
    """登錄一局（局號＝目前局數＋1 為新增，不大於目前局數為覆寫）；只限記分者。"""
    result = service.record_game(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        account_id=account.id,
        game_no=game_no,
        data=body,
    )
    session.commit()
    return result


@router.delete("/tournaments/{tournament_id}/matches/{match_id}/games/{game_no}")
def delete_game(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    game_no: int,
) -> ScoreEntryState:
    """刪除最後一局；只限記分者。"""
    result = service.delete_game(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        account_id=account.id,
        game_no=game_no,
    )
    session.commit()
    return result


@router.post("/tournaments/{tournament_id}/matches/{match_id}/submit")
def submit_result(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> ScoreEntryState:
    """送出系列結果，場次進入申訴期；之後只能經申訴更正。只限記分者。"""
    result = service.submit_result(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )
    session.commit()
    return result


def _stream(file: BinaryIO) -> Iterator[bytes]:
    """分塊送出檔案內容，送完（或中斷）後關閉。"""
    try:
        while chunk := file.read(64 * 1024):
            yield chunk
    finally:
        file.close()


@router.put("/tournaments/{tournament_id}/matches/{match_id}/result-screenshot")
def upload_result_screenshot(
    session: SessionDep,
    account: VerifiedAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    screenshot: Annotated[UploadFile, File()],
) -> ResultScreenshotState:
    """S22 勝隊隊長上傳或更換結算截圖（multipart；JPG／PNG，5 MB 內）。

    系列結果送出後才能上傳；不影響結果確認與晉級。更換時，交易提交後才刪除舊檔。
    """
    result = service.upload_result_screenshot(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        account_id=account.id,
        screenshot=screenshot.file,
        content_type=screenshot.content_type,
    )
    try:
        session.commit()
    except BaseException:
        storage.delete_file(result.new_key)
        raise
    if result.old_key is not None:
        storage.delete_file(result.old_key)
    return result.state


@router.get(
    "/tournaments/{tournament_id}/matches/{match_id}/result-screenshot",
    response_class=StreamingResponse,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def download_result_screenshot(
    session: SessionDep, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> StreamingResponse:
    """結算截圖（公開，不需登入；AD-15）；沒有可公開的截圖回 404 `RESULT_SCREENSHOT_NOT_FOUND`。"""
    file, media_type = service.open_result_screenshot(
        session, tournament_id=tournament_id, match_id=match_id
    )
    return StreamingResponse(
        _stream(file),
        media_type=media_type,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            # 同一個網址的圖會被更換：每次都向伺服器確認
            "Cache-Control": "no-cache",
        },
    )


@router.get("/tournaments/{tournament_id}/matches/{match_id}/result-screenshot-state")
def read_result_screenshot_state(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> ResultScreenshotState:
    """S4：登入者能不能上傳這場的結算截圖（勝隊隊長且系列結果已送出）。"""
    return service.get_result_screenshot_state(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )


@router.get("/me/referee/matches")
def list_my_referee_matches(
    session: SessionDep, account: CurrentAccount
) -> list[RefereeTournamentMatches]:
    """S13：指派給登入者、未取消的場次，依賽事分組；沒有指派回空清單（不要求有裁判身分）。"""
    return service.list_my_referee_matches(session, account_id=account.id)


@router.get("/me/next-matches")
def list_my_next_matches(
    session: SessionDep, account: CurrentAccount
) -> list[NextMatch]:
    """S12：登入者所屬、已參賽的每支隊伍的下一場（各最多一場）；沒有回空清單。只讀，不 commit。"""
    return service.list_my_next_matches(session, account_id=account.id)


@router.get("/tournaments/{tournament_id}/manage/matches")
def list_managed_matches(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> list[ManagedMatch]:
    """S30 場次列表：每場附上能不能改時間與可選範圍；只限該賽事主辦方，尚未抽籤回 404 `BRACKET_NOT_FOUND`。"""
    return service.list_managed_matches(
        session, tournament_id=tournament_id, actor_id=organizer.id
    )


@router.patch("/tournaments/{tournament_id}/matches/{match_id}/schedule")
def reschedule_match(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    body: RescheduleIn,
) -> MatchRead:
    """修改待開打場次的預定時間；只限該賽事主辦方。"""
    result = service.reschedule_match(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        actor_id=organizer.id,
        scheduled_at=body.scheduled_at,
    )
    session.commit()
    return result


@router.put("/tournaments/{tournament_id}/matches/{match_id}/referee")
def assign_referee(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    body: RefereeAssignIn,
) -> MatchRead:
    """指派或改派場次的裁判；只限該賽事主辦方。"""
    result = service.assign_referee(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        actor_id=organizer.id,
        referee_account_id=body.account_id,
    )
    session.commit()
    return result


@router.delete("/tournaments/{tournament_id}/matches/{match_id}/referee")
def unassign_referee(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> MatchRead:
    """收回場次的裁判，之後由主辦方代登；只限該賽事主辦方。"""
    result = service.unassign_referee(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        actor_id=organizer.id,
    )
    session.commit()
    return result
