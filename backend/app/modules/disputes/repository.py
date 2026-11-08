"""disputes 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid

from sqlalchemy import case
from sqlmodel import Session, col, select

from app.modules.disputes.models import Report, ReportStatus


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
