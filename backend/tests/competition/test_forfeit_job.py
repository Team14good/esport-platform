"""Story 5.2 第二階段：逾時判棄權 worker 工作的測試。

D、B 的函式尚未合併，所以用記憶體中的假 `ForfeitPorts`（記錄呼叫順序）；
session 是真的，操作紀錄與事件照常寫進測試資料庫。
"""

import dataclasses
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlmodel import Session, col, select

from app.core import audit
from app.core.events import OutboxEvent
from app.modules.competition.forfeit_job import (
    ForfeitMatchRecord,
    MatchForfeited,
    TournamentForfeitInfo,
    forfeit_next_due,
    make_forfeit_job,
)
from app.modules.competition.models import MatchOutcome, MatchStatus
from app.worker import run_once
from tests.conftest import FrozenClock

DEADLINE = datetime(2026, 11, 1, 13, 15, tzinfo=UTC)
NOW = datetime(2026, 11, 1, 13, 16, tzinfo=UTC)


@dataclass
class FakeMatch:
    """場次的記憶體版本；多帶 5.4 才會寫的欄位，用來確認判棄權不會動到。"""

    id: UUID
    tournament_id: UUID
    team_a_id: UUID | None
    team_b_id: UUID | None
    forfeit_deadline: datetime | None
    status: MatchStatus = MatchStatus.SCHEDULED
    outcome: MatchOutcome | None = None
    winner_id: UUID | None = None
    appeal_deadline: datetime | None = None
    submitted_by: UUID | None = None
    submitted_at: datetime | None = None
    wins_a: int = 0
    wins_b: int = 0


@dataclass
class FakePorts:
    """假的 D、B 函式。

    `lock_match` 回傳複本，`transition_to_appeal_window` 成功時才存回，所以轉換失敗
    （交易回滾）時記憶體中的場次不變。`list_forfeit_due` 只看期限、不看狀態與報到，
    模擬清單取得後到鎖住前狀態改變（已判過、另一隊剛報到），用來測鎖住後的重新判斷。
    """

    tournaments: dict[UUID, TournamentForfeitInfo] = field(default_factory=dict)
    matches: dict[UUID, FakeMatch] = field(default_factory=dict)
    check_ins: dict[UUID, set[UUID]] = field(default_factory=dict)
    calls: list[tuple[str, UUID | datetime]] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    fail_transition_once: set[UUID] = field(default_factory=set)

    def add_tournament(
        self, *, cancelled: bool = False, appeal_minutes: int = 60
    ) -> UUID:
        tournament_id = uuid.uuid4()
        self.tournaments[tournament_id] = TournamentForfeitInfo(
            cancelled=cancelled, appeal_minutes=appeal_minutes
        )
        return tournament_id

    def add_match(
        self,
        tournament_id: UUID,
        *,
        checked_in: str = "",
        deadline: datetime | None = DEADLINE,
    ) -> FakeMatch:
        match = FakeMatch(
            id=uuid.uuid4(),
            tournament_id=tournament_id,
            team_a_id=uuid.uuid4(),
            team_b_id=uuid.uuid4(),
            forfeit_deadline=deadline,
        )
        self.matches[match.id] = match
        self.check_ins[match.id] = {
            team
            for side, team in (("a", match.team_a_id), ("b", match.team_b_id))
            if side in checked_in and team is not None
        }
        return match

    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    # ---------------------------------------------------------- ForfeitPorts

    def list_forfeit_due(self, session: Session, *, now: datetime) -> Sequence[UUID]:
        self.calls.append(("list_forfeit_due", now))
        self.sessions.append(session)
        return [
            m.id
            for m in self.matches.values()
            if m.forfeit_deadline is not None and m.forfeit_deadline <= now
        ]

    def get_tournament_id(self, _session: Session, *, match_id: UUID) -> UUID:
        self.calls.append(("get_tournament_id", match_id))
        return self.matches[match_id].tournament_id

    def lock_tournament(
        self, _session: Session, *, tournament_id: UUID
    ) -> TournamentForfeitInfo:
        self.calls.append(("lock_tournament", tournament_id))
        return self.tournaments[tournament_id]

    def lock_match(self, _session: Session, *, match_id: UUID) -> FakeMatch:
        self.calls.append(("lock_match", match_id))
        return dataclasses.replace(self.matches[match_id])

    def list_checked_in_team_ids(
        self, _session: Session, *, match_id: UUID
    ) -> set[UUID]:
        self.calls.append(("list_checked_in_team_ids", match_id))
        return set(self.check_ins[match_id])

    def transition_to_appeal_window(
        self, _session: Session, *, match: ForfeitMatchRecord
    ) -> None:
        self.calls.append(("transition_to_appeal_window", match.id))
        if match.id in self.fail_transition_once:
            self.fail_transition_once.discard(match.id)
            raise RuntimeError("transition failed")
        assert isinstance(match, FakeMatch)
        assert match.status == MatchStatus.SCHEDULED
        match.status = MatchStatus.APPEAL_WINDOW
        self.matches[match.id] = match


@pytest.fixture
def ports() -> FakePorts:
    return FakePorts()


@pytest.fixture(autouse=True)
def _clock_at_now(frozen_clock: FrozenClock) -> None:
    frozen_clock.set(NOW)


def _forfeit_events(session: Session) -> list[OutboxEvent]:
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.type == "MatchForfeited")
        .order_by(col(OutboxEvent.created_at))
    )
    return list(session.exec(statement))


def _events_for(session: Session, match_id: UUID) -> list[dict[str, Any]]:
    return [
        e.payload
        for e in _forfeit_events(session)
        if e.payload["match_id"] == str(match_id)
    ]


def _audits_for(
    session: Session, tournament_id: UUID, match_id: UUID
) -> list[audit.AuditLogRead]:
    return [
        row
        for row in audit.list_for_tournament(session, tournament_id)
        if row.entity_id == match_id
    ]


# ------------------------------------------------------------------ I/O 矩陣


def test_one_team_checked_in_forfeits_the_other(
    session: Session, ports: FakePorts
) -> None:
    tournament_id = ports.add_tournament(appeal_minutes=60)
    match = ports.add_match(tournament_id, checked_in="a")

    assert forfeit_next_due(session, ports=ports) is True

    stored = ports.matches[match.id]
    expected_deadline = datetime(2026, 11, 1, 14, 16, tzinfo=UTC)
    assert stored.status == MatchStatus.APPEAL_WINDOW
    assert stored.outcome == MatchOutcome.FORFEIT
    assert stored.winner_id == match.team_a_id
    assert stored.appeal_deadline == expected_deadline
    # 沒有送出者、沒有比過局
    assert stored.submitted_by is None
    assert stored.submitted_at is None
    assert (stored.wins_a, stored.wins_b) == (0, 0)

    [row] = audit.list_for_tournament(session, tournament_id)
    assert row.actor_id is None
    assert row.tournament_id == tournament_id
    assert row.action == "match.forfeited"
    assert row.entity_type == "match"
    assert row.entity_id == match.id
    assert row.before == {
        "status": "scheduled",
        "outcome": None,
        "winner_id": None,
        "appeal_deadline": None,
    }
    assert row.after == {
        "status": "appeal_window",
        "outcome": "forfeit",
        "winner_id": str(match.team_a_id),
        "appeal_deadline": "2026-11-01T14:16:00Z",
    }

    [event] = _forfeit_events(session)
    assert event.payload == {
        "match_id": str(match.id),
        "tournament_id": str(tournament_id),
        "outcome": "forfeit",
        "winner_id": str(match.team_a_id),
        "forfeited_team_ids": [str(match.team_b_id)],
        "appeal_deadline": "2026-11-01T14:16:00Z",
    }
    assert MatchForfeited.model_validate(event.payload).appeal_deadline == (
        expected_deadline
    )


def test_no_team_checked_in_is_double_forfeit(
    session: Session, ports: FakePorts
) -> None:
    tournament_id = ports.add_tournament(appeal_minutes=30)
    match = ports.add_match(tournament_id)

    assert forfeit_next_due(session, ports=ports) is True

    stored = ports.matches[match.id]
    assert stored.status == MatchStatus.APPEAL_WINDOW
    assert stored.outcome == MatchOutcome.DOUBLE_FORFEIT
    assert stored.winner_id is None
    assert stored.appeal_deadline == NOW + timedelta(minutes=30)
    assert stored.submitted_by is None
    assert stored.submitted_at is None
    assert (stored.wins_a, stored.wins_b) == (0, 0)

    [row] = _audits_for(session, tournament_id, match.id)
    assert row.after is not None
    assert row.after["outcome"] == "double_forfeit"
    assert row.after["winner_id"] is None

    [payload] = _events_for(session, match.id)
    assert payload["outcome"] == "double_forfeit"
    assert payload["winner_id"] is None
    assert payload["forfeited_team_ids"] == [str(match.team_a_id), str(match.team_b_id)]


def test_skips_first_match_and_judges_the_second(
    session: Session, ports: FakePorts
) -> None:
    tournament_id = ports.add_tournament()
    both_checked = ports.add_match(tournament_id, checked_in="ab")
    only_b = ports.add_match(tournament_id, checked_in="b")
    untouched = dataclasses.replace(both_checked)

    assert forfeit_next_due(session, ports=ports) is True

    assert ports.matches[both_checked.id] == untouched
    stored = ports.matches[only_b.id]
    assert stored.outcome == MatchOutcome.FORFEIT
    assert stored.winner_id == only_b.team_b_id
    assert _audits_for(session, tournament_id, both_checked.id) == []
    assert _events_for(session, both_checked.id) == []
    assert len(_audits_for(session, tournament_id, only_b.id)) == 1
    [payload] = _events_for(session, only_b.id)
    assert payload["forfeited_team_ids"] == [str(only_b.team_a_id)]


def test_invalid_match_is_logged_and_skipped(
    session: Session, ports: FakePorts, caplog: pytest.LogCaptureFixture
) -> None:
    # 報到名單有外隊：judge_forfeit 拋 ValueError，這一場重試也不會成功
    tournament_id = ports.add_tournament()
    invalid = ports.add_match(tournament_id, checked_in="a")
    ports.check_ins[invalid.id].add(uuid.uuid4())
    only_a = ports.add_match(tournament_id, checked_in="a")
    untouched = dataclasses.replace(invalid)

    assert forfeit_next_due(session, ports=ports) is True

    assert ports.matches[invalid.id] == untouched
    assert _audits_for(session, tournament_id, invalid.id) == []
    assert _events_for(session, invalid.id) == []
    assert ports.matches[only_a.id].outcome == MatchOutcome.FORFEIT
    assert str(invalid.id) in caplog.text


def test_all_skipped_writes_nothing_and_returns_false(
    session: Session, ports: FakePorts
) -> None:
    cancelled = ports.add_tournament(cancelled=True)
    first = ports.add_match(cancelled)
    second = ports.add_match(cancelled, checked_in="a")
    before = {m.id: dataclasses.replace(m) for m in (first, second)}

    assert forfeit_next_due(session, ports=ports) is False

    assert ports.matches == before
    assert audit.list_for_tournament(session, cancelled) == []
    assert _forfeit_events(session) == []
    assert "transition_to_appeal_window" not in ports.call_names()


def test_no_due_matches_returns_false(session: Session, ports: FakePorts) -> None:
    tournament_id = ports.add_tournament()
    # 期限還沒到、兩隊未確定（沒有期限）的場次都不在到期清單裡
    ports.add_match(tournament_id, deadline=NOW + timedelta(minutes=1))
    ports.add_match(tournament_id, deadline=None)

    assert forfeit_next_due(session, ports=ports) is False

    assert ports.call_names() == ["list_forfeit_due"]
    assert _forfeit_events(session) == []


def test_running_again_skips_already_forfeited_match(
    session: Session, ports: FakePorts, frozen_clock: FrozenClock
) -> None:
    tournament_id = ports.add_tournament()
    match = ports.add_match(tournament_id, checked_in="a")
    assert forfeit_next_due(session, ports=ports) is True
    judged = dataclasses.replace(ports.matches[match.id])

    frozen_clock.advance(timedelta(minutes=1))
    # 清單仍列出這一場，但鎖住後狀態已是申訴期，所以略過
    assert forfeit_next_due(session, ports=ports) is False

    assert ports.matches[match.id] == judged
    assert len(_audits_for(session, tournament_id, match.id)) == 1
    assert len(_events_for(session, match.id)) == 1


def test_locks_tournament_before_match_and_rechecks_after_locking(
    session: Session, ports: FakePorts
) -> None:
    tournament_id = ports.add_tournament()
    skipped = ports.add_match(tournament_id, checked_in="ab")
    judged = ports.add_match(tournament_id)

    assert forfeit_next_due(session, ports=ports) is True

    assert ports.calls == [
        ("list_forfeit_due", NOW),
        ("get_tournament_id", skipped.id),
        ("lock_tournament", tournament_id),
        ("lock_match", skipped.id),
        ("list_checked_in_team_ids", skipped.id),
        ("get_tournament_id", judged.id),
        ("lock_tournament", tournament_id),
        ("lock_match", judged.id),
        ("list_checked_in_team_ids", judged.id),
        ("transition_to_appeal_window", judged.id),
    ]


def test_uses_locked_values_not_the_listing(session: Session, ports: FakePorts) -> None:
    """清單列出之後才被取消的賽事、才報到的隊伍，都以鎖住後的值為準。"""
    tournament_id = ports.add_tournament()
    cancelled_later = ports.add_match(tournament_id)
    other_tournament = ports.add_tournament()
    checked_in_later = ports.add_match(other_tournament)
    original_lock = ports.lock_tournament

    def lock_and_cancel(session: Session, *, tournament_id: UUID) -> Any:
        info = original_lock(session, tournament_id=tournament_id)
        if tournament_id == cancelled_later.tournament_id:
            return dataclasses.replace(info, cancelled=True)
        # 另一場在鎖住前兩隊都完成報到
        ports.check_ins[checked_in_later.id] = {
            t for t in (checked_in_later.team_a_id, checked_in_later.team_b_id) if t
        }
        return info

    ports.lock_tournament = lock_and_cancel

    assert forfeit_next_due(session, ports=ports) is False
    assert _forfeit_events(session) == []


def test_now_is_read_once_per_call(
    session: Session,
    ports: FakePorts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """時鐘每讀一次就前進一小時：若工作讀了兩次，申訴期截止時間會跟著偏移。"""
    from app.core import clock

    ticks = iter(NOW + timedelta(hours=n) for n in range(100))
    monkeypatch.setattr(clock, "now", lambda: next(ticks))
    tournament_id = ports.add_tournament(appeal_minutes=60)
    match = ports.add_match(tournament_id, checked_in="b")

    assert forfeit_next_due(session, ports=ports) is True

    assert ports.calls[0] == ("list_forfeit_due", NOW)
    assert ports.matches[match.id].appeal_deadline == NOW + timedelta(minutes=60)
    [payload] = _events_for(session, match.id)
    assert payload["appeal_deadline"] == "2026-11-01T14:16:00Z"


# ------------------------------------------------------------------ worker


def test_job_is_named_for_worker_logs(ports: FakePorts) -> None:
    job = make_forfeit_job(ports)

    assert job.__name__ == "judge_forfeits"


def test_run_once_judges_each_due_match_in_its_own_transaction(
    session_factory: Callable[[], Session],
    session: Session,
    ports: FakePorts,
) -> None:
    tournament_id = ports.add_tournament()
    matches = [
        ports.add_match(tournament_id, checked_in="a"),
        ports.add_match(tournament_id, checked_in="b"),
        ports.add_match(tournament_id),
    ]

    run_once([make_forfeit_job(ports)], session_factory=session_factory)

    assert all(ports.matches[m.id].status == MatchStatus.APPEAL_WINDOW for m in matches)
    assert [ports.matches[m.id].outcome for m in matches] == [
        MatchOutcome.FORFEIT,
        MatchOutcome.FORFEIT,
        MatchOutcome.DOUBLE_FORFEIT,
    ]
    # 3 次判了一場、第 4 次全部略過回傳 False，run_once 就不再呼叫
    assert ports.call_names().count("list_forfeit_due") == 4
    assert len({id(s) for s in ports.sessions}) == 4
    for m in matches:
        assert len(_audits_for(session, tournament_id, m.id)) == 1
        assert len(_events_for(session, m.id)) == 1


def test_run_once_failure_rolls_back_only_that_match(
    session_factory: Callable[[], Session],
    session: Session,
    ports: FakePorts,
) -> None:
    tournament_id = ports.add_tournament()
    first, failing, third = (
        ports.add_match(tournament_id, checked_in="a"),
        ports.add_match(tournament_id, checked_in="a"),
        ports.add_match(tournament_id, checked_in="a"),
    )
    ports.fail_transition_once.add(failing.id)

    run_once([make_forfeit_job(ports)], session_factory=session_factory)

    # 第一場已 commit；失敗那場回滾，本輪停止這個工作
    assert ports.matches[first.id].status == MatchStatus.APPEAL_WINDOW
    assert len(_audits_for(session, tournament_id, first.id)) == 1
    assert len(_events_for(session, first.id)) == 1
    for m in (failing, third):
        assert ports.matches[m.id].status == MatchStatus.SCHEDULED
        assert ports.matches[m.id].outcome is None
        assert _audits_for(session, tournament_id, m.id) == []
        assert _events_for(session, m.id) == []

    run_once([make_forfeit_job(ports)], session_factory=session_factory)

    for m in (first, failing, third):
        assert ports.matches[m.id].status == MatchStatus.APPEAL_WINDOW
        assert len(_audits_for(session, tournament_id, m.id)) == 1
        assert len(_events_for(session, m.id)) == 1
