"""tournaments 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import psycopg
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.modules.tournaments.models import (
    GameTitle,
    RankTier,
    RefereeInvitation,
    Tournament,
    TournamentReferee,
    TournamentStatus,
)

GAME_NAME_INDEX = "ix_game_title_lower_name"


class DuplicateGameNameError(Exception):
    """寫入遊戲時撞到名稱唯一索引（同時新增或改成同名的競態）。"""


def _flush_game(session: Session, write: Callable[[], None]) -> None:
    """在 savepoint 裡寫入並 flush；名稱重複時拋 DuplicateGameNameError，外層交易不受影響。"""
    try:
        with session.begin_nested():
            write()
            session.flush()
    except IntegrityError as exc:
        if (
            isinstance(exc.orig, psycopg.Error)
            and exc.orig.diag.constraint_name == GAME_NAME_INDEX
        ):
            raise DuplicateGameNameError from exc
        raise


def get_game(
    session: Session,
    game_id: uuid.UUID,
    *,
    for_update: bool = False,
    for_share: bool = False,
) -> GameTitle | None:
    # for_update（FOR UPDATE）或 for_share（FOR SHARE）時重新查詢並加鎖，
    # 並以資料庫的最新值覆蓋 identity map 裡已載入的同一筆
    lock: bool | dict[str, bool] | None = None
    if for_update:
        lock = True
    elif for_share:
        lock = {"read": True}
    return session.get(
        GameTitle,
        game_id,
        with_for_update=lock,
        populate_existing=lock is not None,
    )


def get_game_by_name(session: Session, name: str) -> GameTitle | None:
    """以去除前後空白、不分大小寫的名稱查詢（與 lower(btrim(name)) 唯一索引同一規則）。"""
    statement = select(GameTitle).where(
        func.lower(func.btrim(GameTitle.name)) == func.lower(func.btrim(name))
    )
    return session.exec(statement).first()


def list_games(session: Session) -> list[GameTitle]:
    # 以 "C" 定序（逐碼位比較）排序，結果不受資料庫 locale 影響
    return list(
        session.exec(select(GameTitle).order_by(col(GameTitle.name).collate("C")))
    )


def list_rank_tiers(session: Session, game_ids: list[uuid.UUID]) -> list[RankTier]:
    """依積分由高到低、同分依名稱排列。"""
    if not game_ids:
        return []
    statement = (
        select(RankTier)
        .where(col(RankTier.game_id).in_(game_ids))
        .order_by(col(RankTier.score).desc(), col(RankTier.name).collate("C"))
    )
    return list(session.exec(statement))


def add_game(session: Session, game: GameTitle, tiers: list[RankTier]) -> GameTitle:
    """新增遊戲與段位；名稱已存在時拋 DuplicateGameNameError。"""

    def _write() -> None:
        session.add(game)
        session.flush()
        session.add_all(tiers)

    _flush_game(session, _write)
    return game


def update_game(
    session: Session, game: GameTitle, changes: dict[str, Any]
) -> GameTitle:
    """修改遊戲欄位；改成已存在的名稱時拋 DuplicateGameNameError。

    欄位在 savepoint 裡才設定：`begin_nested()` 會先 flush 既有的變更，若事先改好，
    唯一索引的錯誤會發生在 savepoint 之外。
    """

    def _write() -> None:
        for field, value in changes.items():
            setattr(game, field, value)
        session.add(game)

    _flush_game(session, _write)
    return game


def replace_rank_tiers(
    session: Session, game_id: uuid.UUID, tiers: list[RankTier]
) -> None:
    """整份替換某遊戲的段位表：先刪除舊的（flush），再新增新的。"""
    for tier in list_rank_tiers(session, [game_id]):
        session.delete(tier)
    session.flush()
    session.add_all(tiers)
    session.flush()


# ---------------------------------------------------------------- 賽事


def add_tournament(session: Session, tournament: Tournament) -> Tournament:
    session.add(tournament)
    session.flush()
    return tournament


def get_tournament(
    session: Session, tournament_id: uuid.UUID, *, for_update: bool = False
) -> Tournament | None:
    # for_update 時 SELECT … FOR UPDATE，並以資料庫的最新值覆蓋 identity map 裡的同一筆
    return session.get(
        Tournament,
        tournament_id,
        with_for_update=for_update or None,
        populate_existing=for_update,
    )


def list_tournaments_by_organizer(
    session: Session, organizer_id: uuid.UUID
) -> list[Tournament]:
    """某主辦方的賽事，新建立的在前。"""
    statement = (
        select(Tournament)
        .where(Tournament.organizer_id == organizer_id)
        .order_by(col(Tournament.created_at).desc(), col(Tournament.id))
    )
    return list(session.exec(statement))


def list_tournaments(session: Session) -> list[Tournament]:
    """所有賽事，依開賽時間排序（呈現順序由前端依狀態分組決定）。"""
    statement = select(Tournament).order_by(
        col(Tournament.start_at), col(Tournament.id)
    )
    return list(session.exec(statement))


def find_due_upcoming_id(session: Session, now: datetime) -> uuid.UUID | None:
    """一筆尚未開放、報名開始已到的賽事 id（最早到期的優先）；不加鎖。"""
    statement = (
        select(Tournament.id)
        .where(Tournament.status == TournamentStatus.UPCOMING)
        .where(col(Tournament.registration_start) <= now)
        .order_by(col(Tournament.registration_start), col(Tournament.id))
        .limit(1)
    )
    return session.exec(statement).first()


def set_tournament_status(
    session: Session, tournament: Tournament, status: TournamentStatus, at: datetime
) -> Tournament:
    tournament.status = status
    tournament.updated_at = at
    session.add(tournament)
    session.flush()
    return tournament


# ---------------------------------------------------------------- 裁判


def expire_active_invitations(
    session: Session, tournament_id: uuid.UUID, now: datetime
) -> None:
    """把同賽事尚未過期的邀請 `expires_at` 設為 `now`（不刪除）。

    UPDATE 會鎖住這些列，與接受邀請時的 FOR SHARE 互斥。
    """
    session.connection().execute(
        update(RefereeInvitation)
        .where(col(RefereeInvitation.tournament_id) == tournament_id)
        .where(col(RefereeInvitation.expires_at) > now)
        .values(expires_at=now)
    )


def add_invitation(
    session: Session, invitation: RefereeInvitation
) -> RefereeInvitation:
    session.add(invitation)
    session.flush()
    return invitation


def get_latest_invitation(
    session: Session, tournament_id: uuid.UUID
) -> RefereeInvitation | None:
    """同賽事最新的一筆邀請。

    最新的邀請 `expires_at` 一定最大（舊的不是較早到期，就是被設為產生新邀請的當下），
    以它排序；同一時間點產生時（凍結時鐘）也不會選到已作廢的那筆。
    """
    statement = (
        select(RefereeInvitation)
        .where(RefereeInvitation.tournament_id == tournament_id)
        .order_by(
            col(RefereeInvitation.expires_at).desc(),
            col(RefereeInvitation.created_at).desc(),
        )
        .limit(1)
        # 同一交易內剛以 UPDATE 作廢過時，不要用 identity map 裡的舊值
        .execution_options(populate_existing=True)
    )
    return session.exec(statement).first()


def get_invitation_by_token(
    session: Session, token: str, *, for_share: bool = False
) -> RefereeInvitation | None:
    # for_share 時 SELECT … FOR SHARE，並以資料庫的最新值覆蓋 identity map 裡的同一筆
    statement = select(RefereeInvitation).where(RefereeInvitation.token == token)
    if for_share:
        statement = statement.with_for_update(read=True).execution_options(
            populate_existing=True
        )
    return session.exec(statement).first()


def add_referee(session: Session, referee: TournamentReferee) -> bool:
    """新增裁判；已存在（同賽事同帳號）時不做任何事。回傳是否真的新增。"""
    statement = (
        insert(TournamentReferee)
        .values(
            tournament_id=referee.tournament_id,
            account_id=referee.account_id,
            invitation_id=referee.invitation_id,
            accepted_at=referee.accepted_at,
        )
        .on_conflict_do_nothing(index_elements=["tournament_id", "account_id"])
        # 有衝突時不回傳任何列；以 RETURNING 判斷，不依賴 rowcount
        .returning(col(TournamentReferee.account_id))
    )
    return session.connection().execute(statement).first() is not None


def get_referee(
    session: Session, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> TournamentReferee | None:
    return session.get(
        TournamentReferee, (tournament_id, account_id), populate_existing=True
    )


def has_any_referee_row(session: Session, account_id: uuid.UUID) -> bool:
    """帳號在任一賽事有裁判列（走 account_id 索引）。"""
    statement = (
        select(col(TournamentReferee.account_id))
        .where(TournamentReferee.account_id == account_id)
        .limit(1)
    )
    return session.exec(statement).first() is not None


def list_referees(
    session: Session, tournament_id: uuid.UUID
) -> list[TournamentReferee]:
    """某賽事的裁判，依接受邀請的時間排序。"""
    statement = (
        select(TournamentReferee)
        .where(TournamentReferee.tournament_id == tournament_id)
        .order_by(col(TournamentReferee.accepted_at), col(TournamentReferee.account_id))
    )
    return list(session.exec(statement))
