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
    GameScoreIn,
    PublicBracket,
    PublicMatchDetail,
    ScoreEntryState,
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
