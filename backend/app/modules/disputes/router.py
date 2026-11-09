"""disputes 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.db import SessionDep
from app.modules.competition.models import RescheduleInfo
from app.modules.disputes import service
from app.modules.disputes.models import (
    AppealGroup,
    AppealRead,
    AppealResolveIn,
    AppealState,
    OpenDisputes,
    PublicAppealResult,
    ReportableTeam,
    ReportRead,
)
from app.modules.identity.deps import CurrentAccount, Organizer, VerifiedAccount

router = APIRouter(tags=["disputes"])

_CHUNK_BYTES = 64 * 1024
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}


@router.get("/tournaments/{tournament_id}/reportable-teams")
def list_reportable_teams(
    session: SessionDep, account: VerifiedAccount, tournament_id: uuid.UUID
) -> list[ReportableTeam]:
    """S20 檢舉對象選單：同賽事已送出報名、不是自己的隊伍（依隊名排序）。

    只有該賽事待分配、正取、候補、已參賽隊伍的隊長能取得；賽事已結束或已取消時
    回 409 `REPORT_NOT_ALLOWED`。
    """
    return service.list_reportable_teams(
        session, tournament_id=tournament_id, account_id=account.id
    )


@router.post(
    "/tournaments/{tournament_id}/reports", status_code=status.HTTP_201_CREATED
)
def file_report(
    session: SessionDep,
    account: VerifiedAccount,
    tournament_id: uuid.UUID,
    reported_team_id: Annotated[uuid.UUID, Form()],
    # 說明由 service 去頭尾空白後驗證；未附時為空字串，回 `REPORT_DESCRIPTION_INVALID`
    description: Annotated[str, Form()] = "",
    attachment: Annotated[UploadFile | None, File()] = None,
) -> ReportRead:
    """S20 提出檢舉（multipart）：對象、說明（1～1000 字）、選擇性截圖（JPG／PNG，5 MB 內）。"""
    upload = attachment
    # 瀏覽器送出空的檔案欄位時，檔名為空且 0 byte：視為未附檔
    if upload is not None and not upload.filename and not upload.size:
        upload = None
    result = service.file_report(
        session,
        tournament_id=tournament_id,
        account_id=account.id,
        reported_team_id=reported_team_id,
        description=description,
        attachment=upload.file if upload is not None else None,
        content_type=upload.content_type if upload is not None else None,
    )
    try:
        session.commit()
    except BaseException:
        if result.attachment_key is not None:
            storage.delete_file(result.attachment_key)
        raise
    return result.report


@router.get("/organizer/tournaments/{tournament_id}/reports")
def list_tournament_reports(
    session: SessionDep, account: Organizer, tournament_id: uuid.UUID
) -> list[ReportRead]:
    """S33 檢舉列表：只有該賽事主辦方；處理中在前，各組依提出時間由舊到新。"""
    return service.list_tournament_reports(
        session, tournament_id=tournament_id, actor_id=account.id
    )


def _stream(file: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := file.read(_CHUNK_BYTES):
            yield chunk
    finally:
        file.close()


@router.get(
    "/organizer/reports/{report_id}/attachment",
    response_class=StreamingResponse,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def download_report_attachment(
    session: SessionDep, account: Organizer, report_id: uuid.UUID
) -> StreamingResponse:
    """下載檢舉附件：只有該賽事主辦方。"""
    file, media_type = service.open_report_attachment(
        session, report_id=report_id, actor_id=account.id
    )
    filename = f"report-{report_id}.{_EXTENSIONS[media_type]}"
    return StreamingResponse(
        _stream(file),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 檢舉證據：不讓瀏覽器猜測內容型態，也不留在任何快取
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# ---------------------------------------------------------------- 申訴（6.1）


@router.get("/tournaments/{tournament_id}/matches/{match_id}/appeal-state")
def read_appeal_state(
    session: SessionDep,
    account: CurrentAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> AppealState:
    """S4 申訴入口：登入者本隊現在能不能提出申訴；不透露另一隊有沒有申訴。"""
    return service.get_appeal_state(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account.id
    )


@router.post(
    "/tournaments/{tournament_id}/matches/{match_id}/appeals",
    status_code=status.HTTP_201_CREATED,
)
def file_appeal(
    session: SessionDep,
    account: VerifiedAccount,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    # 字數與空白由 service 驗證（422 指向 description）
    description: Annotated[str, Form()] = "",
    attachment: Annotated[UploadFile | None, File()] = None,
) -> AppealRead:
    """S21 提出申訴（multipart）：說明 1～1000 字，附件最多一張（JPG／PNG，5 MB 內）。

    只有該場兩隊的隊長能在申訴期限內提出，每隊每場一次；第一筆申訴讓場次轉為申訴中。
    """
    upload = attachment
    # 瀏覽器送出空的檔案欄位時，檔名為空且 0 byte：視為未附檔
    if upload is not None and not upload.filename and not upload.size:
        upload = None
    result = service.file_appeal(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        account_id=account.id,
        description=description,
        attachment=upload.file if upload is not None else None,
        content_type=upload.content_type if upload is not None else None,
    )
    try:
        session.commit()
    except BaseException:
        if result.attachment_key is not None:
            storage.delete_file(result.attachment_key)
        raise
    return result.appeal


@router.get(
    "/organizer/appeals/{appeal_id}/attachment",
    response_class=StreamingResponse,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def download_appeal_attachment(
    session: SessionDep, organizer: Organizer, appeal_id: uuid.UUID
) -> StreamingResponse:
    """下載申訴附件：只有該賽事主辦方（AD-15）。"""
    file, media_type = service.open_appeal_attachment(
        session, appeal_id=appeal_id, actor_id=organizer.id
    )
    filename = f"appeal-{appeal_id}.{_EXTENSIONS[media_type]}"
    return StreamingResponse(
        _stream(file),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 申訴證據：不讓瀏覽器猜測內容型態，也不留在任何快取
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/organizer/tournaments/{tournament_id}/appeals")
def list_tournament_appeals(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> list[AppealGroup]:
    """S32：該賽事的申訴，依場次分組（未結案在前）；只有該賽事主辦方。"""
    return service.list_tournament_appeals(
        session, tournament_id=tournament_id, actor_id=organizer.id
    )


@router.post(
    "/organizer/tournaments/{tournament_id}/matches/{match_id}/appeal-resolution"
)
def resolve_appeals(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    body: AppealResolveIn,
) -> list[AppealRead]:
    """S32 處理同一場次的申訴：維持原結果、更正結果（整組各局）或重新比賽（只用於棄權）。"""
    result = service.resolve_appeals(
        session,
        tournament_id=tournament_id,
        match_id=match_id,
        actor_id=organizer.id,
        decision=body.decision,
        reason=body.reason,
        games=body.games,
        replay_at=body.replay_at,
    )
    session.commit()
    return result


@router.get("/organizer/tournaments/{tournament_id}/matches/{match_id}/replay-window")
def read_replay_window(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
) -> RescheduleInfo:
    """S32 重新比賽的時間範圍（與 4.3 改期同一個規則）；只有該賽事主辦方。"""
    return service.get_replay_window(
        session, tournament_id=tournament_id, match_id=match_id, actor_id=organizer.id
    )


@router.get("/organizer/tournaments/{tournament_id}/open-disputes")
def read_open_disputes(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> OpenDisputes:
    """S27 待處理清單：未結案的申訴，依處理期限由近到遠（檢舉由 6.5 接上，目前為 0）。"""
    return service.count_open_disputes(
        session, tournament_id=tournament_id, actor_id=organizer.id
    )


@router.get("/tournaments/{tournament_id}/matches/{match_id}/appeal-result")
def read_appeal_result(
    session: SessionDep, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> PublicAppealResult:
    """S4（公開，不需登入）：已確認場次的申訴處理結果；不含申訴內容（AD-19）。"""
    return service.get_public_appeal_result(
        session, tournament_id=tournament_id, match_id=match_id
    )
