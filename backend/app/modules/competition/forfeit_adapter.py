"""逾時判棄權工作的轉接層（Story 5.2 收尾）。

把 `forfeit_job.ForfeitPorts` 的六個方法對應到 competition 與 tournaments 的
service，對應方式照 `forfeit_job` 檔頭的說明。這裡只轉換型別，不加任何規則；
判斷都在 `forfeit.judge_forfeit`，鎖的順序與寫入都在 `forfeit_job.forfeit_next_due`。
"""

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlmodel import Session

from app.modules.competition import service
from app.modules.competition.forfeit_job import (
    ForfeitMatchRecord,
    ForfeitPorts,
    TournamentForfeitInfo,
)
from app.modules.competition.models import Match, MatchStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentStatus


class ServiceForfeitPorts:
    """`ForfeitPorts` 的正式實作。"""

    def list_forfeit_due(self, session: Session, *, now: datetime) -> Sequence[UUID]:
        return service.list_forfeit_due(session, now=now)

    def get_tournament_id(self, session: Session, *, match_id: UUID) -> UUID:
        return service.get_match(session, match_id=match_id).tournament_id

    def lock_tournament(
        self, session: Session, *, tournament_id: UUID
    ) -> TournamentForfeitInfo:
        tournament = tournaments_service.lock_tournament(
            session, tournament_id=tournament_id
        )
        return TournamentForfeitInfo(
            cancelled=tournament.status == TournamentStatus.CANCELLED,
            appeal_minutes=tournament.appeal_minutes,
        )

    def lock_match(self, session: Session, *, match_id: UUID) -> Match:
        return service.lock_match(session, match_id=match_id)

    def list_checked_in_team_ids(
        self, session: Session, *, match_id: UUID
    ) -> Collection[UUID]:
        return [
            row.team_id for row in service.list_check_ins(session, match_id=match_id)
        ]

    def transition_to_appeal_window(
        self, session: Session, *, match: ForfeitMatchRecord
    ) -> None:
        # 工作傳回來的一定是 `lock_match` 給的 Match 資料列
        if not isinstance(match, Match):
            raise TypeError(f"expected Match row, got {type(match).__name__}")
        service.transition_match(session, match=match, to=MatchStatus.APPEAL_WINDOW)


SERVICE_FORFEIT_PORTS: ForfeitPorts = ServiceForfeitPorts()
