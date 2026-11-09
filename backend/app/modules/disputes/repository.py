"""disputes 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid
from datetime import datetime

from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.modules.disputes.models import (
    Appeal,
    AppealDecision,
    AppealStatus,
    Report,
    ReportStatus,
)


def get_appeal(session: Session, appeal_id: uuid.UUID) -> Appeal | None:
    return session.get(Appeal, appeal_id)


def find_open_team_appeal(
    session: Session, match_id: uuid.UUID, team_id: uuid.UUID
) -> Appeal | None:
    """某隊對某場次未結案的申訴（每隊每場最多一筆；已結案的不算）。"""
    statement = select(Appeal).where(
        Appeal.match_id == match_id,
        Appeal.team_id == team_id,
        Appeal.status == AppealStatus.OPEN,
    )
    return session.exec(statement).first()


def add_appeal(session: Session, appeal: Appeal) -> bool:
    """新增申訴；撞未結案申訴的部分唯一索引回 False（外層交易不受影響）。"""
    try:
        with session.begin_nested():
            session.add(appeal)
    except IntegrityError:
        return False
    return True


def list_match_appeals(session: Session, match_id: uuid.UUID) -> list[Appeal]:
    """某場次的全部申訴，依提出時間。"""
    statement = (
        select(Appeal)
        .where(Appeal.match_id == match_id)
        .order_by(col(Appeal.filed_at), col(Appeal.id))
    )
    return list(session.exec(statement))


def list_open_match_appeals(session: Session, match_id: uuid.UUID) -> list[Appeal]:
    """某場次未結案的申訴，依提出時間。"""
    return [
        appeal
        for appeal in list_match_appeals(session, match_id)
        if appeal.status == AppealStatus.OPEN
    ]


def list_tournament_appeals(
    session: Session, tournament_id: uuid.UUID, *, open_only: bool = False
) -> list[Appeal]:
    """某賽事的申訴，依提出時間。"""
    statement = select(Appeal).where(Appeal.tournament_id == tournament_id)
    if open_only:
        statement = statement.where(Appeal.status == AppealStatus.OPEN)
    statement = statement.order_by(col(Appeal.filed_at), col(Appeal.id))
    return list(session.exec(statement))


def close_appeals(
    session: Session,
    appeals: list[Appeal],
    *,
    decision: AppealDecision,
    reason: str,
    handled_by: uuid.UUID,
    handled_at: datetime,
) -> None:
    """以相同決定與理由結案；不改 `filed_by`。"""
    for appeal in appeals:
        appeal.status = AppealStatus.CLOSED
        appeal.decision = decision
        appeal.reason = reason
        appeal.handled_by = handled_by
        appeal.handled_at = handled_at
        session.add(appeal)
    session.flush()


def add_report(session: Session, report: Report) -> Report:
    session.add(report)
    session.flush()
    return report


def get_report(session: Session, report_id: uuid.UUID) -> Report | None:
    return session.get(Report, report_id)


def list_open_reported_team_ids(
    session: Session, reporter_team_id: uuid.UUID
) -> set[uuid.UUID]:
    """檢舉人隊伍目前處理中（`open`）的檢舉對象。"""
    statement = (
        select(Report.reported_team_id)
        .where(Report.reporter_team_id == reporter_team_id)
        .where(Report.status == ReportStatus.OPEN)
    )
    return set(session.exec(statement))


def list_tournament_reports(session: Session, tournament_id: uuid.UUID) -> list[Report]:
    """某賽事的檢舉：處理中在前，各組依提出時間由舊到新、再依 id。"""
    statement = (
        select(Report)
        .where(Report.tournament_id == tournament_id)
        .order_by(
            case((col(Report.status) == ReportStatus.OPEN, 0), else_=1),
            col(Report.filed_at),
            col(Report.id),
        )
    )
    return list(session.exec(statement))
