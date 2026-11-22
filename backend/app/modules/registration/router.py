"""registration 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core import storage
from app.core.db import SessionDep
from app.modules.identity.deps import CurrentAccount, Organizer, VerifiedAccount
from app.modules.registration import service
from app.modules.registration.models import (
    CapacityUpdate,
    MyTeamCard,
    OrganizerRegistration,
    OrganizerRegistrationPage,
    PublicAcceptedTeams,
    RegistrationRejection,
    RegistrationStatus,
    TeamCreate,
    TeamDetail,
    TeamInvitePreview,
)
from app.modules.tournaments.models import MAX_PAGE, TournamentRead

router = APIRouter(tags=["registration"])

_CHUNK_BYTES = 64 * 1024
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}


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


@router.get("/tournaments/{tournament_id}/accepted-teams")
def list_accepted_teams(
    session: SessionDep, tournament_id: uuid.UUID
) -> PublicAcceptedTeams:
    """S2「正取隊伍」的公開名單（不需登入）：只有隊伍 id 與隊名。

    校園賽優先期結束前不公布，回 `announce_at`（優先期結束時間）與空的 `teams`。
    """
    return service.list_public_accepted_teams(session, tournament_id=tournament_id)


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


@router.post("/teams/{team_id}/submission")
def submit_registration(
    session: SessionDep, account: VerifiedAccount, team_id: uuid.UUID
) -> TeamDetail:
    """S17 隊長送出報名：名單鎖定並凍結學校、平均段位積分與送出時間。

    優先期內或自訂模式送出時報名轉為「已送出・待分配」；校園賽在先搶期送出時
    當下分配，回應直接帶正取或候補結果與候補順位。

    不符合送出條件時回 409 `REGISTRATION_REQUIREMENTS_UNMET`，`message` 列出全部原因。
    """
    team = service.submit_registration(session, team_id=team_id, account_id=account.id)
    session.commit()
    return team


@router.post("/teams/{team_id}/withdrawal")
def withdraw_registration(
    session: SessionDep, account: VerifiedAccount, team_id: uuid.UUID
) -> TeamDetail:
    """S17 隊長在抽籤前退賽：報名撤回，正取釋出的名額依當下階段由候補遞補。

    報名不是已送出・待分配／正取／候補，或賽事不是開放報名／報名截止時回 409
    `REGISTRATION_NOT_WITHDRAWABLE`。
    """
    team = service.withdraw_registration(
        session, team_id=team_id, account_id=account.id
    )
    session.commit()
    return team


@router.post("/tournaments/{tournament_id}/capacity")
def raise_capacity(
    session: SessionDep,
    account: VerifiedAccount,
    tournament_id: uuid.UUID,
    body: CapacityUpdate,
) -> TournamentRead:
    """主辦方提高名額（抽籤前），候補依當下階段遞補。

    只有該賽事的主辦方可以呼叫（403 `TOURNAMENT_OWNER_REQUIRED`）；新名額不大於目前
    名額時回 422 `CAPACITY_NOT_INCREASED`；抽籤後回 409 `CAPACITY_NOT_EDITABLE`。
    """
    tournament = service.raise_capacity(
        session,
        tournament_id=tournament_id,
        capacity=body.capacity,
        actor_id=account.id,
    )
    session.commit()
    return tournament


@router.get("/accounts/me/teams")
def list_my_teams(session: SessionDep, account: CurrentAccount) -> list[MyTeamCard]:
    """S12 我的隊伍：目前帳號加入的每支隊伍與報名狀態。"""
    return service.list_my_teams(session, account_id=account.id)


# ---------------------------------------------------------------- 主辦方檢視與退回（Story 3.8）


@router.get("/organizer/tournaments/{tournament_id}/registrations")
def list_organizer_registrations(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    status_filter: Annotated[RegistrationStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
) -> OrganizerRegistrationPage:
    """S29 報名清單：送出過的報名，依分配結果分組排序、每頁 20 筆；`status` 省略表示全部。

    不存在 404 `TOURNAMENT_NOT_FOUND`；別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`。
    """
    return service.list_organizer_registrations(
        session,
        tournament_id=tournament_id,
        actor_id=organizer.id,
        status=status_filter,
        page=page,
    )


def _stream(file: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := file.read(_CHUNK_BYTES):
            yield chunk
    finally:
        file.close()


@router.get(
    "/organizer/tournaments/{tournament_id}/registrations/{registration_id}"
    "/members/{account_id}/rank-screenshot",
    response_class=StreamingResponse,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def download_rank_screenshot(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    registration_id: uuid.UUID,
    account_id: uuid.UUID,
) -> StreamingResponse:
    """下載隊員的段位截圖：只有該賽事主辦方（隊長、隊員、上傳者本人都是 403）。

    報名不屬於這個賽事 404 `REGISTRATION_NOT_FOUND`；不是這支隊伍的隊員 404
    `TEAM_MEMBER_NOT_FOUND`；沒有截圖 404 `FILE_NOT_FOUND`。
    """
    file, media_type = service.open_rank_screenshot(
        session,
        tournament_id=tournament_id,
        registration_id=registration_id,
        account_id=account_id,
        actor_id=organizer.id,
    )
    filename = f"rank-{registration_id}-{account_id}.{_EXTENSIONS[media_type]}"
    return StreamingResponse(
        _stream(file),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 段位截圖只給主辦方：不讓瀏覽器猜測內容型態，也不留在任何快取
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/organizer/tournaments/{tournament_id}/registrations/{registration_id}/rejection"
)
def reject_registration(
    session: SessionDep,
    organizer: Organizer,
    tournament_id: uuid.UUID,
    registration_id: uuid.UUID,
    body: RegistrationRejection,
) -> OrganizerRegistration:
    """主辦方退回報名（必填原因）：名單解鎖，正取釋出的名額依當下階段由候補遞補。

    報名不是已送出・待分配／正取／候補，或賽事不是開放報名／報名截止時回 409
    `REGISTRATION_NOT_REJECTABLE`。
    """
    registration = service.reject_registration(
        session,
        tournament_id=tournament_id,
        registration_id=registration_id,
        actor_id=organizer.id,
        reason=body.reason,
    )
    session.commit()
    return registration
