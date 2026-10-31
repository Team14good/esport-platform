"""competition 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Literal

from sqlmodel import Session, col, or_, select

from app.modules.competition.models import Bracket, Match, MatchOutcome, MatchStatus


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


def list_matches(session: Session, bracket_id: uuid.UUID) -> list[Match]:
    """依輪次、季軍賽排在決賽之後、由上到下排序。"""
    statement = (
        select(Match)
        .where(Match.bracket_id == bracket_id)
        .order_by(col(Match.round_no), col(Match.is_third_place), col(Match.slot_no))
    )
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
