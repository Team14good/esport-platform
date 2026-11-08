"""disputes 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.core import storage
from app.core.db import SessionDep
from app.modules.disputes import service
from app.modules.disputes.models import AppealRead, AppealState
from app.modules.identity.deps import CurrentAccount, Organizer, VerifiedAccount

router = APIRouter(tags=["disputes"])

_CHUNK_BYTES = 64 * 1024


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


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(_CHUNK_BYTES):
        yield chunk


@router.get(
    "/organizer/appeals/{appeal_id}/attachment",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"image/jpeg": {}, "image/png": {}},
            "description": "申訴附件",
        }
    },
)
def download_appeal_attachment(
    session: SessionDep, organizer: Organizer, appeal_id: uuid.UUID
) -> StreamingResponse:
    """下載申訴附件；只有該賽事主辦方（AD-15）。"""
    stream, media_type = service.open_appeal_attachment(
        session, appeal_id=appeal_id, actor_id=organizer.id
    )
    return StreamingResponse(
        _chunks(stream),
        media_type=media_type,
        # 使用者上傳的檔案：不讓瀏覽器猜測內容型別
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stream.close),
    )
