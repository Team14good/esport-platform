"""competition 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlmodel import Session, col, or_, select

from app.modules.competition.models import Bracket, Match, MatchStatus


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
