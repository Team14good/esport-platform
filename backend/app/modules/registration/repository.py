"""registration 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from collections.abc import Collection

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.modules.registration.models import (
    PriorityWindowSettlement,
    Registration,
    RegistrationStatus,
    Team,
    TeamMember,
)

MEMBER_UNIQUE_CONSTRAINT = "uq_team_member_tournament_id_account_id"
TEAM_NAME_UNIQUE_INDEX = "ix_team_tournament_id_lower_name"


class DuplicateMemberError(Exception):
    """新增隊員時撞到（tournament_id, account_id）唯一鍵：已在同賽事的某支隊伍。"""


class DuplicateTeamNameError(Exception):
    """新增隊伍時撞到（tournament_id, lower(name)）唯一索引：同賽事已有同名隊伍。"""


def _translate(exc: IntegrityError) -> Exception | None:
    """把撞到唯一鍵的 IntegrityError 轉成具名的例外；其他違反約束的情況回傳 None。"""
    message = str(exc.orig)
    if MEMBER_UNIQUE_CONSTRAINT in message:
        return DuplicateMemberError()
    if TEAM_NAME_UNIQUE_INDEX in message:
        return DuplicateTeamNameError()
    return None


def get_team(session: Session, team_id: uuid.UUID) -> Team | None:
    return session.get(Team, team_id)


def get_team_by_invite_token(session: Session, token: str) -> Team | None:
    return session.exec(select(Team).where(Team.invite_token == token)).first()


def get_team_by_name(
    session: Session, tournament_id: uuid.UUID, name: str
) -> Team | None:
    """同賽事內不分大小寫比對隊名（走 lower(name) 唯一索引）。"""
    statement = (
        select(Team)
        .where(Team.tournament_id == tournament_id)
        .where(func.lower(Team.name) == func.lower(name))
    )
    return session.exec(statement).first()


def get_membership(
    session: Session, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> TeamMember | None:
    """帳號在某賽事的隊員資料（最多一筆）。"""
    statement = (
        select(TeamMember)
        .where(TeamMember.tournament_id == tournament_id)
        .where(TeamMember.account_id == account_id)
    )
    return session.exec(statement).first()


def get_team_member(
    session: Session, team_id: uuid.UUID, account_id: uuid.UUID
) -> TeamMember | None:
    statement = (
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .where(TeamMember.account_id == account_id)
    )
    return session.exec(statement).first()


def list_members(session: Session, team_id: uuid.UUID) -> list[TeamMember]:
    """依加入時間排列（同時間依 id），隊長是第一個加入的人。"""
    statement = (
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .order_by(col(TeamMember.created_at), col(TeamMember.id))
    )
    return list(session.exec(statement))


def count_members(session: Session, team_id: uuid.UUID) -> int:
    statement = select(func.count()).where(TeamMember.team_id == team_id)
    return session.exec(statement).one()


def list_memberships_of_account(
    session: Session, account_id: uuid.UUID
) -> list[TeamMember]:
    """帳號加入的所有隊伍（新加入的在前）。"""
    statement = (
        select(TeamMember)
        .where(TeamMember.account_id == account_id)
        .order_by(col(TeamMember.created_at).desc(), col(TeamMember.id))
    )
    return list(session.exec(statement))


def get_registration_by_team(
    session: Session, team_id: uuid.UUID
) -> Registration | None:
    return session.exec(
        select(Registration).where(Registration.team_id == team_id)
    ).first()


def add_team(session: Session, team: Team) -> Team:
    """新增隊伍；同賽事已有同名隊伍時拋 DuplicateTeamNameError，外層交易不受影響。"""
    try:
        with session.begin_nested():
            session.add(team)
    except IntegrityError as exc:
        translated = _translate(exc)
        if translated is None:
            raise
        raise translated from exc
    return team


def add_member(session: Session, member: TeamMember) -> TeamMember:
    """新增隊員；已在同賽事時拋 DuplicateMemberError，外層交易不受影響。"""
    try:
        with session.begin_nested():
            session.add(member)
    except IntegrityError as exc:
        translated = _translate(exc)
        if translated is None:
            raise
        raise translated from exc
    return member


def add_registration(session: Session, registration: Registration) -> Registration:
    session.add(registration)
    session.flush()
    return registration


def list_registrations(
    session: Session, tournament_id: uuid.UUID
) -> list[Registration]:
    """某賽事的所有報名（依 id 排列，結果與資料庫的回傳順序無關）。"""
    statement = (
        select(Registration)
        .where(Registration.tournament_id == tournament_id)
        .order_by(col(Registration.id))
    )
    return list(session.exec(statement))


def list_unsettled_pending_tournament_ids(session: Session) -> list[uuid.UUID]:
    """有「已送出・待分配」報名、但還沒有優先期結算紀錄的賽事 id（依 id 排列）。"""
    settled = select(PriorityWindowSettlement.tournament_id).where(
        PriorityWindowSettlement.tournament_id == Registration.tournament_id
    )
    statement = (
        select(Registration.tournament_id)
        .where(Registration.status == RegistrationStatus.PENDING)
        .where(~settled.exists())
        .distinct()
        .order_by(col(Registration.tournament_id))
    )
    return list(session.exec(statement))


def get_settlement(
    session: Session, tournament_id: uuid.UUID
) -> PriorityWindowSettlement | None:
    return session.get(PriorityWindowSettlement, tournament_id)


def add_settlement(
    session: Session, settlement: PriorityWindowSettlement
) -> PriorityWindowSettlement:
    session.add(settlement)
    session.flush()
    return settlement


def list_teams_by_ids(session: Session, team_ids: Collection[uuid.UUID]) -> list[Team]:
    """依 id 一次查出多支隊伍（依 id 排列）；不存在的 id 不出現。"""
    if not team_ids:
        return []
    statement = select(Team).where(col(Team.id).in_(team_ids)).order_by(col(Team.id))
    return list(session.exec(statement))


def list_registrations_by_team_ids(
    session: Session, team_ids: Collection[uuid.UUID]
) -> list[Registration]:
    """依隊伍 id 一次查出多筆報名（依隊伍 id 排列）；不存在的隊伍不出現。"""
    if not team_ids:
        return []
    statement = (
        select(Registration)
        .where(col(Registration.team_id).in_(team_ids))
        .order_by(col(Registration.team_id))
    )
    return list(session.exec(statement))


def list_teams_with_members_by_status(
    session: Session, tournament_id: uuid.UUID, status: RegistrationStatus
) -> list[tuple[Team, list[TeamMember]]]:
    """某賽事報名為 `status` 的隊伍（依隊伍 id 排列）與其隊員（依加入時間、再依 id）。

    隊伍一次查出、隊員一次查出，不逐隊查詢。
    """
    teams = list(
        session.exec(
            select(Team)
            .join(Registration, col(Registration.team_id) == col(Team.id))
            .where(Registration.tournament_id == tournament_id)
            .where(Registration.status == status)
            .order_by(col(Team.id))
        )
    )
    if not teams:
        return []
    members: dict[uuid.UUID, list[TeamMember]] = {team.id: [] for team in teams}
    for member in session.exec(
        select(TeamMember)
        .where(col(TeamMember.team_id).in_(members))
        .order_by(col(TeamMember.created_at), col(TeamMember.id))
    ):
        members[member.team_id].append(member)
    return [(team, members[team.id]) for team in teams]
