"""disputes 擁有的資料表的查詢與加鎖；不做業務判斷、不碰其他模組的資料表。"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.disputes.models import Appeal


def get_appeal(session: Session, appeal_id: uuid.UUID) -> Appeal | None:
    return session.get(Appeal, appeal_id)


def find_team_appeal(
    session: Session, match_id: uuid.UUID, team_id: uuid.UUID
) -> Appeal | None:
    """某隊對某場次的申訴（每隊每場最多一筆）。"""
    statement = select(Appeal).where(
        Appeal.match_id == match_id, Appeal.team_id == team_id
    )
    return session.exec(statement).first()


def add_appeal(session: Session, appeal: Appeal) -> bool:
    """新增申訴；撞 `(match_id, team_id)` 唯一鍵回 False（外層交易不受影響）。"""
    try:
        with session.begin_nested():
            session.add(appeal)
    except IntegrityError:
        return False
    return True
