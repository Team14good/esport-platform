"""competition 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid

from fastapi import APIRouter, status

from app.core.db import SessionDep
from app.core.errors import BusinessError
from app.modules.competition import service
from app.modules.competition.models import (
    BracketRead,
    CheckInRead,
    CheckInStatus,
    PublicBracket,
    PublicMatchDetail,
)
from app.modules.identity.deps import CurrentAccount, Organizer

router = APIRouter(tags=["competition"])


@router.post("/tournaments/{tournament_id}/draw", status_code=status.HTTP_201_CREATED)
def draw(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> BracketRead:
    """抽籤並公布賽程；只限該賽事主辦方，只能抽一次。"""
    bracket = service.draw(session, tournament_id=tournament_id, actor_id=organizer.id)
    session.commit()
    return bracket


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
