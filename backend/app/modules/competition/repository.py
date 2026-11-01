"""competition 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, or_, select

from app.modules.competition.models import (
    Bracket,
    CheckIn,
    Match,
    MatchGame,
    MatchOutcome,
    MatchStatus,
)


def add_bracket(session: Session, bracket: Bracket, matches: Sequence[Match]) -> None:
    """新增對戰表與全部場次並 flush。

    場次之間有自我參照外鍵（`next_match_id`、`loser_next_match_id`），呼叫端
    要依「被指向的場次先寫入」的順序傳入。
    """
    session.add(bracket)
    session.flush()
    for match in matches:
        session.add(match)
        session.flush()


def get_bracket_by_tournament(
    session: Session, tournament_id: uuid.UUID
) -> Bracket | None:
    statement = select(Bracket).where(Bracket.tournament_id == tournament_id)
    return session.exec(statement).first()


def get_bracket(session: Session, bracket_id: uuid.UUID) -> Bracket | None:
    return session.get(Bracket, bracket_id)


def list_matches(
    session: Session, bracket_id: uuid.UUID, *, fresh: bool = False
) -> list[Match]:
    """依輪次、季軍賽排在決賽之後、由上到下排序。

    `fresh` 為 True 時以資料庫最新值覆蓋 identity map（不加鎖；已鎖賽事後讀相鄰場次用）。
    """
    statement = (
        select(Match)
        .where(Match.bracket_id == bracket_id)
        .order_by(col(Match.round_no), col(Match.is_third_place), col(Match.slot_no))
    )
    if fresh:
        statement = statement.execution_options(populate_existing=True)
    return list(session.exec(statement))


def list_team_matches(
    session: Session, tournament_id: uuid.UUID, team_id: uuid.UUID
) -> list[Match]:
    statement = (
        select(Match)
        .where(
            Match.tournament_id == tournament_id,
            or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
        )
        .order_by(col(Match.round_no), col(Match.is_third_place), col(Match.slot_no))
    )
    return list(session.exec(statement))


def get_match(
    session: Session, match_id: uuid.UUID, *, for_update: bool = False
) -> Match | None:
    # for_update 時重新查詢並加鎖（SELECT … FOR UPDATE），以資料庫最新值覆蓋 identity map
    return session.get(
        Match,
        match_id,
        with_for_update=True if for_update else None,
        populate_existing=for_update,
    )


def set_match_status(
    session: Session, match: Match, status: MatchStatus, at: datetime
) -> None:
    match.status = status
    match.updated_at = at
    session.add(match)
    session.flush()


def set_forfeit_deadline(
    session: Session, match: Match, deadline: datetime, at: datetime
) -> None:
    match.forfeit_deadline = deadline
    match.updated_at = at
    session.add(match)
    session.flush()


def set_scheduled_at(
    session: Session, match: Match, scheduled_at: datetime, at: datetime
) -> None:
    match.scheduled_at = scheduled_at
    match.updated_at = at
    session.add(match)
    session.flush()


def lock_bracket_matches(session: Session, bracket_id: uuid.UUID) -> list[Match]:
    """依 id 遞增 `SELECT … FOR UPDATE` 鎖住對戰表的全部場次（AD-6），回傳最新值。"""
    statement = (
        select(Match)
        .where(Match.bracket_id == bracket_id)
        .order_by(col(Match.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(session.exec(statement))


def find_expired_appeal_id(
    session: Session,
    now: datetime,
    *,
    exclude_tournaments: Collection[uuid.UUID] = (),
) -> uuid.UUID | None:
    """一場申訴期、`appeal_deadline <= now`、已有 outcome 的場次 id（期限早的先）；沒有回 None。

    沒有 outcome 的場次無法確認，排除掉，以免一直被選中而擋住後面的場次。
    """
    statement = select(Match.id).where(
        Match.status == MatchStatus.APPEAL_WINDOW,
        col(Match.appeal_deadline) <= now,
        col(Match.outcome).is_not(None),
    )
    if exclude_tournaments:
        statement = statement.where(
            col(Match.tournament_id).not_in(list(exclude_tournaments))
        )
    statement = statement.order_by(col(Match.appeal_deadline), col(Match.id)).limit(1)
    return session.exec(statement).first()


def set_match_result(
    session: Session,
    match: Match,
    *,
    outcome: MatchOutcome,
    winner_id: uuid.UUID | None,
    confirmed_at: datetime,
) -> None:
    match.outcome = outcome
    match.winner_id = winner_id
    match.confirmed_at = confirmed_at
    match.updated_at = confirmed_at
    session.add(match)
    session.flush()


def set_match_team(
    session: Session,
    match: Match,
    side: Literal["a", "b"],
    team_id: uuid.UUID,
    at: datetime,
) -> None:
    if side == "a":
        match.team_a_id = team_id
    else:
        match.team_b_id = team_id
    match.updated_at = at
    session.add(match)
    session.flush()


def clear_match_result(session: Session, match: Match, at: datetime) -> None:
    """清除結果、勝隊與棄權期限（季軍賽取消時用）。"""
    match.outcome = None
    match.winner_id = None
    match.forfeit_deadline = None
    match.updated_at = at
    session.add(match)
    session.flush()


def add_check_in(session: Session, check_in: CheckIn) -> bool:
    """新增報到紀錄；撞 `(match_id, team_id)` 唯一鍵回 False（外層交易不受影響）。"""
    try:
        with session.begin_nested():
            session.add(check_in)
    except IntegrityError:
        return False
    return True


def list_check_ins(session: Session, match_id: uuid.UUID) -> list[CheckIn]:
    """依報到時間排序（同時間依 id）。"""
    statement = (
        select(CheckIn)
        .where(CheckIn.match_id == match_id)
        .order_by(col(CheckIn.at), col(CheckIn.id))
    )
    return list(session.exec(statement))


def find_forfeit_due(session: Session, now: datetime) -> list[uuid.UUID]:
    """待開打、`forfeit_deadline <= now`、且不是兩隊都已報到的場次 id，依期限排序。"""
    checked_in = (
        select(func.count())
        .select_from(CheckIn)
        .where(CheckIn.match_id == Match.id)
        .scalar_subquery()
    )
    statement = (
        select(Match.id)
        .where(
            Match.status == MatchStatus.SCHEDULED,
            col(Match.forfeit_deadline) <= now,
            checked_in < 2,
        )
        .order_by(col(Match.forfeit_deadline), col(Match.id))
    )
    return list(session.exec(statement))


def find_unstarted_bracket_id(
    session: Session, first_match_by: datetime
) -> uuid.UUID | None:
    """尚未處理開始、且最早場次預定時間 <= `first_match_by` 的對戰表 id（最早的先）。

    `first_match_by` ＝ 現在 ＋ 報到提前量，由呼叫端算；這裡只是粗篩，
    service 鎖住後會用 `checkin.tournament_starts_at` 重新判斷。
    """
    statement = (
        select(Bracket.id)
        .join(Match, col(Match.bracket_id) == col(Bracket.id))
        .where(col(Bracket.start_handled_at).is_(None))
        .group_by(col(Bracket.id))
        .having(func.min(Match.scheduled_at) <= first_match_by)
        .order_by(func.min(Match.scheduled_at), col(Bracket.id))
        .limit(1)
    )
    return session.exec(statement).first()


def mark_start_handled(session: Session, bracket: Bracket, at: datetime) -> None:
    bracket.start_handled_at = at
    session.add(bracket)
    session.flush()


# ---------------------------------------------------------------- 逐局比分（5.3、5.4）


def list_games(session: Session, match_id: uuid.UUID) -> list[MatchGame]:
    """依局號排序。"""
    statement = (
        select(MatchGame)
        .where(MatchGame.match_id == match_id)
        .order_by(col(MatchGame.game_no))
    )
    return list(session.exec(statement))


def add_game(session: Session, game: MatchGame) -> None:
    session.add(game)
    session.flush()


def update_game(
    session: Session,
    game: MatchGame,
    *,
    winner_side: str,
    score_a: int | None,
    score_b: int | None,
    recorded_by: uuid.UUID,
    recorded_at: datetime,
) -> None:
    game.winner_side = winner_side
    game.score_a = score_a
    game.score_b = score_b
    game.recorded_by = recorded_by
    game.recorded_at = recorded_at
    session.add(game)
    session.flush()


def delete_game(session: Session, game: MatchGame) -> None:
    session.delete(game)
    session.flush()


def set_match_wins(
    session: Session, match: Match, wins_a: int, wins_b: int, at: datetime
) -> None:
    match.wins_a = wins_a
    match.wins_b = wins_b
    match.updated_at = at
    session.add(match)
    session.flush()


def set_match_submission(
    session: Session,
    match: Match,
    *,
    winner_id: uuid.UUID,
    submitted_by: uuid.UUID,
    submitted_at: datetime,
    appeal_deadline: datetime,
) -> None:
    """寫入送出的系列結果（`outcome = played`）；不寫 `confirmed_at`。"""
    match.outcome = MatchOutcome.PLAYED
    match.winner_id = winner_id
    match.submitted_by = submitted_by
    match.submitted_at = submitted_at
    match.appeal_deadline = appeal_deadline
    match.updated_at = submitted_at
    session.add(match)
    session.flush()


def clear_for_replay(session: Session, match: Match, at: datetime) -> None:
    """刪除該場所有報到紀錄與逐局比分，並把結果相關欄位歸零（6.2 重新比賽）。

    不改狀態、`scheduled_at` 與結構欄位。
    """
    for check_in in list_check_ins(session, match.id):
        session.delete(check_in)
    for game in list_games(session, match.id):
        session.delete(game)
    match.outcome = None
    match.winner_id = None
    match.submitted_by = None
    match.submitted_at = None
    match.appeal_deadline = None
    match.confirmed_at = None
    match.forfeit_deadline = None
    match.wins_a = 0
    match.wins_b = 0
    match.updated_at = at
    session.add(match)
    session.flush()
