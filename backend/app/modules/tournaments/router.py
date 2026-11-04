"""tournaments 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core import authz
from app.core.db import SessionDep
from app.modules.identity.deps import Organizer, PlatformAdmin, VerifiedAccount
from app.modules.tournaments import service
from app.modules.tournaments.models import (
    REFEREE_INVITATION_TOKEN_MAX_LENGTH,
    GameIn,
    GameRead,
    PublicRefereeInvitation,
    PublicTournament,
    RefereeInvitationRead,
    RefereeRead,
    TournamentCreate,
    TournamentRead,
)

router = APIRouter(tags=["tournaments"])

# 裁判邀請 token（公開預覽也會用到）；超過欄位長度的不可能存在，直接 422
RefereeToken = Annotated[
    str, Path(min_length=1, max_length=REFEREE_INVITATION_TOKEN_MAX_LENGTH)
]


@router.get("/admin/games")
def list_games(session: SessionDep, _admin: PlatformAdmin) -> list[GameRead]:
    """所有遊戲設定（依名稱排序）；只限平台管理員。"""
    return service.list_games(session)


@router.post("/admin/games", status_code=status.HTTP_201_CREATED)
def create_game(session: SessionDep, admin: PlatformAdmin, body: GameIn) -> GameRead:
    """新增遊戲；名稱重複回 409 `GAME_NAME_TAKEN`。"""
    game = service.create_game(session, actor_id=admin.id, data=body)
    session.commit()
    return game


@router.get("/admin/games/{game_id}")
def read_game(
    session: SessionDep, _admin: PlatformAdmin, game_id: uuid.UUID
) -> GameRead:
    """一款遊戲的設定；不存在回 404 `GAME_NOT_FOUND`。"""
    return service.get_game(session, game_id=game_id)


@router.put("/admin/games/{game_id}")
def update_game(
    session: SessionDep, admin: PlatformAdmin, game_id: uuid.UUID, body: GameIn
) -> GameRead:
    """整份替換遊戲設定（含段位表）；不存在回 404，名稱重複回 409。"""
    game = service.update_game(session, actor_id=admin.id, game_id=game_id, data=body)
    session.commit()
    return game


# ---------------------------------------------------------------- 公開（不需登入）


@router.get("/tournaments")
def list_public_tournaments(session: SessionDep) -> list[PublicTournament]:
    """所有賽事的公開資料，依開賽時間排序；不需登入，只回 `PublicTournament`。"""
    return service.list_public_tournaments(session)


@router.get("/tournaments/{tournament_id}")
def read_public_tournament(
    session: SessionDep, tournament_id: uuid.UUID
) -> PublicTournament:
    """一場賽事的公開資料；不需登入，不存在回 404 `TOURNAMENT_NOT_FOUND`。"""
    return service.get_public_tournament(session, tournament_id=tournament_id)


# ---------------------------------------------------------------- 主辦方


@router.get("/games")
def list_games_for_organizer(
    session: SessionDep, _organizer: Organizer
) -> list[GameRead]:
    """主辦方建立賽事時可選的遊戲（依名稱排序）；只限主辦方。"""
    return service.list_games(session)


@router.post("/organizer/tournaments", status_code=status.HTTP_201_CREATED)
def create_tournament(
    session: SessionDep, organizer: Organizer, body: TournamentCreate
) -> TournamentRead:
    """建立賽事；遊戲不存在回 404 `GAME_NOT_FOUND`，欄位不合法回 422。"""
    tournament = service.create_tournament(
        session, organizer_id=organizer.id, data=body
    )
    session.commit()
    return tournament


@router.get("/organizer/tournaments")
def list_my_tournaments(
    session: SessionDep, organizer: Organizer
) -> list[TournamentRead]:
    """目前主辦方建立的賽事，新建立的在前。"""
    return service.list_organizer_tournaments(session, organizer_id=organizer.id)


@router.get("/organizer/tournaments/{tournament_id}")
def read_my_tournament(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> TournamentRead:
    """主辦方自己的賽事；不存在回 404，別人的賽事回 403 `TOURNAMENT_OWNER_REQUIRED`。"""
    tournament = service.get_tournament(session, tournament_id=tournament_id)
    authz.ensure_tournament_owner(tournament, organizer.id)
    return tournament


# ---------------------------------------------------------------- 裁判


@router.post(
    "/organizer/tournaments/{tournament_id}/referee-invitation",
    status_code=status.HTTP_201_CREATED,
)
def create_referee_invitation(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> RefereeInvitationRead:
    """產生新的裁判邀請（7 天有效），舊的未過期邀請立即作廢。

    不存在 404；別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`；已結束或已取消 409
    `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
    """
    invitation = service.invite_referee(
        session, tournament_id=tournament_id, actor_id=organizer.id
    )
    session.commit()
    return invitation


@router.get("/organizer/tournaments/{tournament_id}/referee-invitation")
def read_referee_invitation(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> RefereeInvitationRead | None:
    """目前（最新一筆）的裁判邀請，含是否過期；從未產生過回 `null`。"""
    tournament = service.get_tournament(session, tournament_id=tournament_id)
    authz.ensure_tournament_owner(tournament, organizer.id)
    return service.get_current_invitation(session, tournament_id=tournament_id)


@router.get("/organizer/tournaments/{tournament_id}/referees")
def list_tournament_referees(
    session: SessionDep, organizer: Organizer, tournament_id: uuid.UUID
) -> list[RefereeRead]:
    """已接受邀請的裁判，依接受時間排序。"""
    tournament = service.get_tournament(session, tournament_id=tournament_id)
    authz.ensure_tournament_owner(tournament, organizer.id)
    return service.list_referees(session, tournament_id=tournament_id)


@router.get("/referee-invites/{token}")
def preview_referee_invitation(
    session: SessionDep, token: RefereeToken
) -> PublicRefereeInvitation:
    """裁判邀請預覽；不需登入，只回賽事名稱、到期時間與是否過期。

    不存在 404 `REFEREE_INVITATION_NOT_FOUND`。
    """
    return service.preview_invitation(session, token=token)


@router.post("/referee-invites/{token}/accept")
def accept_referee_invitation(
    session: SessionDep, account: VerifiedAccount, token: RefereeToken
) -> RefereeRead:
    """接受裁判邀請（需已驗證 Email）；已是裁判時回原本的資料。

    過期或已作廢 409 `REFEREE_INVITATION_EXPIRED`；主辦方本人 409
    `ORGANIZER_CANNOT_BE_REFEREE`；已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
    """
    referee = service.accept_invitation(session, token=token, account_id=account.id)
    session.commit()
    return referee
