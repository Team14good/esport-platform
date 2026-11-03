"""registration 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.core import storage
from app.core.db import SessionDep
from app.modules.identity.deps import CurrentAccount, VerifiedAccount
from app.modules.registration import service
from app.modules.registration.models import (
    MyTeamCard,
    TeamCreate,
    TeamDetail,
    TeamInvitePreview,
)

router = APIRouter(tags=["registration"])


@router.post("/tournaments/{tournament_id}/teams", status_code=status.HTTP_201_CREATED)
def create_team(
    session: SessionDep,
    account: VerifiedAccount,
    tournament_id: uuid.UUID,
    body: TeamCreate,
) -> TeamDetail:
    """S16 建立隊伍：建立者成為隊長，報名狀態為「組隊中」，並產生邀請連結。"""
    team = service.create_team(
        session, tournament_id=tournament_id, account_id=account.id, name=body.name
    )
    session.commit()
    return team


@router.get("/teams/{team_id}")
def read_team(
    session: SessionDep, account: CurrentAccount, team_id: uuid.UUID
) -> TeamDetail:
    """S17 隊伍頁；只有隊員能看，其他帳號回 403 `TEAM_MEMBER_REQUIRED`。"""
    return service.get_team_detail(session, team_id=team_id, account_id=account.id)


@router.get("/team-invites/{token}")
def preview_team_invite(session: SessionDep, token: str) -> TeamInvitePreview:
    """S19 邀請連結的公開預覽（不需登入）：賽事、遊戲、隊名與是否已滿。"""
    return service.preview_invite(session, token=token)


@router.post("/team-invites/{token}/members")
def join_team(session: SessionDep, account: VerifiedAccount, token: str) -> TeamDetail:
    """S19 以邀請連結加入隊伍，成為選手。"""
    team = service.join_team(session, token=token, account_id=account.id)
    session.commit()
    return team


@router.put("/teams/{team_id}/members/me/profile")
def update_my_player_profile(
    session: SessionDep,
    account: VerifiedAccount,
    team_id: uuid.UUID,
    # 欄位格式由 service 在鎖住賽事後驗證，這裡不加限制；未附或空字串都交給 service
    game_account_id: Annotated[str, Form()] = "",
    rank_tier: Annotated[str, Form()] = "",
    rank_screenshot: Annotated[UploadFile | None, File()] = None,
) -> TeamDetail:
    """S18 存自己的參賽資料（multipart）：遊戲 ID、段位、段位截圖（JPG／PNG，5 MB 內）。

    已有截圖時可不附檔，保留原圖；換新截圖時，交易提交後才刪除舊檔。
    """
    screenshot = rank_screenshot
    # 瀏覽器送出空的檔案欄位時，檔名為空且 0 byte：視為未附檔
    if screenshot is not None and not screenshot.filename and not screenshot.size:
        screenshot = None
    result = service.update_player_profile(
        session,
        team_id=team_id,
        account_id=account.id,
        game_account_id=game_account_id,
        rank_tier=rank_tier,
        screenshot=screenshot.file if screenshot is not None else None,
        content_type=screenshot.content_type if screenshot is not None else None,
        file_name=screenshot.filename if screenshot is not None else None,
    )
    try:
        session.commit()
    except BaseException:
        if result.new_key is not None:
            storage.delete_file(result.new_key)
        raise
    if result.old_key is not None:
        storage.delete_file(result.old_key)
    return result.detail


@router.get("/accounts/me/teams")
def list_my_teams(session: SessionDep, account: CurrentAccount) -> list[MyTeamCard]:
    """S12 我的隊伍：目前帳號加入的每支隊伍與報名狀態。"""
    return service.list_my_teams(session, account_id=account.id)
