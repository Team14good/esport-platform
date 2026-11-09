"""disputes 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.db import SessionDep
from app.modules.disputes import service
from app.modules.disputes.models import ReportableTeam, ReportRead
from app.modules.identity.deps import Organizer, VerifiedAccount

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
