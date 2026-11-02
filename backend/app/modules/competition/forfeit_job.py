"""逾時判棄權的 worker 工作（Story 5.2 第二階段）。

每次呼叫最多判一場：依序走過到期場次，先鎖賽事、再鎖場次（AD-6），用鎖住後的
資料重新呼叫 `judge_forfeit`；有結果就寫入結果、轉為申訴期、寫操作紀錄並發出
`MatchForfeited`，回傳 True。全部略過時回傳 False。交易由 `app.worker.run_once`
負責，這裡不 commit 也不 rollback（AD-5）。

用到的 D（competition）與 B（tournaments）函式尚未合併，所以透過 `ForfeitPorts`
注入，不直接 import。`get_match`、`lock_match`、`transition_match`、`lock_tournament`
在 D 的 4.1 第二階段（PR #19）；`list_forfeit_due`、`list_check_ins` 在 5.1 第二階段。
合併後要寫的轉接層，各方法對應如下（D 已於 2026-11-02 確認簽名相同）：

- `list_forfeit_due` → competition `service.list_forfeit_due(session, now=now)`
- `get_tournament_id` → competition `service.get_match(session, match_id=...)` 的
  `tournament_id`
- `lock_tournament` → tournaments `service.lock_tournament(session, tournament_id=...)`，
  把 `status` 是否為已取消與 `appeal_minutes` 轉成 `TournamentForfeitInfo`
- `lock_match` → competition `service.lock_match(session, match_id=...)`，直接回傳 Match
  資料列（屬於這個 session，工作寫入的欄位隨交易 commit）
- `list_checked_in_team_ids` → competition `service.list_check_ins(session, match_id=...)`
  每筆的 `team_id`
- `transition_to_appeal_window` → competition
  `service.transition_match(session, match=match, to=MatchStatus.APPEAL_WINDOW)`；
  D 的轉換表已允許「待開打 → 申訴期」（`test_match_transitions.py` 固定）

轉接層寫好後，把 `make_forfeit_job(轉接層)` 加進 `app/worker/jobs.py` 的 `JOBS`。
"""

import logging
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlmodel import Session

from app.core import audit, clock, events
from app.core.events import Event
from app.modules.competition.forfeit import (
    ForfeitVerdict,
    appeal_deadline,
    judge_forfeit,
)
from app.modules.competition.models import MatchOutcome, MatchStatus

logger = logging.getLogger(__name__)

# 與 `app.worker.Job` 相同的形狀；模組不 import worker（worker 是呼叫模組的一方）
type ForfeitJob = Callable[[Session], bool]

AUDIT_ACTION = "match.forfeited"
AUDIT_ENTITY_TYPE = "match"


class MatchForfeited(Event):
    """場次逾時判棄權（期中只發事件，不另寫通知）。

    `forfeited_team_ids` 的順序與 `judge_forfeit` 相同：一方棄權只有未報到的一隊，
    雙方棄權依序為 a、b 兩隊。
    """

    match_id: UUID
    tournament_id: UUID
    outcome: MatchOutcome
    winner_id: UUID | None
    forfeited_team_ids: tuple[UUID, ...]
    appeal_deadline: datetime


@dataclass(frozen=True)
class TournamentForfeitInfo:
    """判棄權需要的賽事資料（鎖住賽事後取得）。"""

    cancelled: bool
    appeal_minutes: int


class ForfeitMatchRecord(Protocol):
    """工作讀寫的場次屬性，名稱照 `MatchRead`。

    唯讀的屬性用 property 宣告；`outcome`、`winner_id`、`appeal_deadline` 由工作寫入。
    `status` 只透過 `ForfeitPorts.transition_to_appeal_window` 改變。
    """

    outcome: MatchOutcome | None
    winner_id: UUID | None
    appeal_deadline: datetime | None

    @property
    def id(self) -> UUID:
        """場次 id。"""

    @property
    def tournament_id(self) -> UUID:
        """所屬賽事 id。"""

    @property
    def status(self) -> MatchStatus:
        """場次狀態。"""

    @property
    def team_a_id(self) -> UUID | None:
        """A 隊；未確定時為 None。"""

    @property
    def team_b_id(self) -> UUID | None:
        """B 隊；未確定時為 None。"""

    @property
    def forfeit_deadline(self) -> datetime | None:
        """棄權期限；兩隊都確定才有值。"""


class ForfeitPorts(Protocol):
    """工作用到的 D、B 函式；合併後由轉接層對應到真的 service（見檔頭）。"""

    def list_forfeit_due(self, session: Session, *, now: datetime) -> Sequence[UUID]:
        """待開打、`forfeit_deadline <= now`、且已報到隊數少於 2 的場次 id，依處理順序排列。

        清單不加鎖，取得後到鎖住前狀態仍可能改變（例如另一隊剛完成報到），所以工作
        鎖住後仍會重新判斷。
        """

    def get_tournament_id(self, session: Session, *, match_id: UUID) -> UUID:
        """場次所屬的賽事 id（不加鎖，只用來決定先鎖哪個賽事）。"""

    def lock_tournament(
        self, session: Session, *, tournament_id: UUID
    ) -> TournamentForfeitInfo:
        """`SELECT … FOR UPDATE` 賽事列，回傳鎖住後的賽事資料。"""

    def lock_match(self, session: Session, *, match_id: UUID) -> ForfeitMatchRecord:
        """`SELECT … FOR UPDATE` 場次列；寫入回傳物件的欄位會隨交易 commit。"""

    def list_checked_in_team_ids(
        self, session: Session, *, match_id: UUID
    ) -> Collection[UUID]:
        """這場已報到的隊伍 id。"""

    def transition_to_appeal_window(
        self, session: Session, *, match: ForfeitMatchRecord
    ) -> None:
        """把場次轉為申訴期（不經過進行中）。"""


def _snapshot(match: ForfeitMatchRecord) -> dict[str, Any]:
    return {
        "status": match.status,
        "outcome": match.outcome,
        "winner_id": match.winner_id,
        "appeal_deadline": match.appeal_deadline,
    }


def _apply_verdict(
    session: Session,
    *,
    ports: ForfeitPorts,
    tournament_id: UUID,
    tournament: TournamentForfeitInfo,
    match: ForfeitMatchRecord,
    verdict: ForfeitVerdict[UUID],
    now: datetime,
) -> None:
    """寫入判棄權結果、轉為申訴期、寫操作紀錄並發出事件。

    `submitted_by`、`submitted_at` 維持空值，`wins_a`、`wins_b` 不變（沒有比過局）。
    """
    before = _snapshot(match)
    deadline = appeal_deadline(decided_at=now, appeal_minutes=tournament.appeal_minutes)
    match.outcome = verdict.outcome
    match.winner_id = verdict.winner
    match.appeal_deadline = deadline
    ports.transition_to_appeal_window(session, match=match)
    audit.record(
        session,
        actor_id=None,
        tournament_id=tournament_id,
        action=AUDIT_ACTION,
        entity_type=AUDIT_ENTITY_TYPE,
        entity_id=match.id,
        before=before,
        after=_snapshot(match),
    )
    events.publish(
        session,
        MatchForfeited(
            match_id=match.id,
            tournament_id=tournament_id,
            outcome=verdict.outcome,
            winner_id=verdict.winner,
            forfeited_team_ids=verdict.forfeited,
            appeal_deadline=deadline,
        ),
    )


def forfeit_next_due(session: Session, *, ports: ForfeitPorts) -> bool:
    """判一場到期的棄權；判了回傳 True，全部略過回傳 False。不 commit。

    略過的場次（兩隊都已報到、賽事已取消、狀態已不是待開打等）不寫任何東西，
    但它們的鎖會留到這個交易結束。資料不合法、`judge_forfeit` 拋 ValueError 的場次
    記錄日誌後同樣略過。
    """
    now = clock.now()
    for match_id in ports.list_forfeit_due(session, now=now):
        tournament_id = ports.get_tournament_id(session, match_id=match_id)
        # 先鎖賽事再鎖場次（AD-6，與 5.5 相同）；之後的判斷都以鎖住後的值為準
        tournament = ports.lock_tournament(session, tournament_id=tournament_id)
        match = ports.lock_match(session, match_id=match_id)
        try:
            verdict = judge_forfeit(
                now=now,
                tournament_cancelled=tournament.cancelled,
                status=match.status,
                team_a=match.team_a_id,
                team_b=match.team_b_id,
                forfeit_deadline=match.forfeit_deadline,
                checked_in=ports.list_checked_in_team_ids(session, match_id=match_id),
            )
        except ValueError:
            # 資料不合法（例如報到名單有外隊）：重試也不會成功。記錄後略過這一場，
            # 不讓它每輪排在最前面、擋住後面到期的場次
            logger.exception("Match %s has invalid data for forfeit; skipped", match_id)
            continue
        if verdict is None:
            continue
        _apply_verdict(
            session,
            ports=ports,
            tournament_id=tournament_id,
            tournament=tournament,
            match=match,
            verdict=verdict,
            now=now,
        )
        return True
    return False


def make_forfeit_job(ports: ForfeitPorts) -> ForfeitJob:
    """回傳 worker 工作；函式名稱 `judge_forfeits` 會出現在 worker 的日誌。"""

    def judge_forfeits(session: Session) -> bool:
        """判一場逾時未報到的棄權。"""
        return forfeit_next_due(session, ports=ports)

    return judge_forfeits
