"""Story 5.2 收尾：逾時判棄權工作接上真正的 service，經 `run_once` 走完整流程。

判棄權規則與工作本身的各種情境在 tests/competition/test_forfeit.py、
test_forfeit_job.py（用替身 ports）；這裡只確認轉接層 `ServiceForfeitPorts`
對應正確、工作已註冊，並接得上 5.5 的申訴期滿自動確認與晉級。

8 隊抽籤後第一輪 M1～M4 排在 2026-10-26 11:00 UTC，棄權期限為 11:15，
申訴時限 30 分鐘（tests/competition/conftest.py 的預設）。
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, col, select

from app.core.audit import AuditLog
from app.core.events import OutboxEvent
from app.modules.competition import repository
from app.modules.competition.forfeit_adapter import SERVICE_FORFEIT_PORTS
from app.modules.competition.models import CheckIn, Match, MatchOutcome, MatchStatus
from app.modules.tournaments.models import Tournament, TournamentStatus
from app.worker import run_once
from app.worker.jobs import (
    JOBS,
    confirm_expired_appeals,
    dispatch_outbox,
    judge_forfeits,
)
from tests.competition.conftest import (  # noqa: F401  fake_registration 是 fixture
    FakeRegistration,
    draw_with,
    fake_registration,
)
from tests.conftest import FrozenClock
from tests.helpers import make_account

pytestmark = pytest.mark.usefixtures("fake_registration")

DEADLINE = datetime(2026, 10, 26, 11, 15, tzinfo=UTC)
ROUND_ONE = ("M1", "M2", "M3", "M4")


class Drawn:
    """已抽籤、已 commit 的 8 隊賽事。"""

    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        tournament, bracket = draw_with(session, fake, 8)
        self.tournament_id = tournament.id
        self.ids = {m.code: m.id for m in bracket.matches}
        session.commit()

    def match(self, session: Session, code: str) -> Match:
        row = session.get(Match, self.ids[code])
        assert row is not None
        return row

    def check_in(self, session: Session, code: str, *sides: str) -> None:
        match = self.match(session, code)
        for side in sides:
            team_id = match.team_a_id if side == "a" else match.team_b_id
            assert team_id is not None
            repository.add_check_in(
                session,
                CheckIn(
                    match_id=match.id,
                    team_id=team_id,
                    account_id=make_account(session).id,
                    at=DEADLINE - timedelta(minutes=20),
                ),
            )
        session.commit()


@pytest.fixture
def drawn(
    session: Session,
    fake_registration: FakeRegistration,  # noqa: F811
    frozen_clock: FrozenClock,
) -> Drawn:
    # 抽籤要在凍結時鐘下進行，開賽時間才會是 10/26 11:00
    return Drawn(session, fake_registration)


def _forfeit_audits(session: Session) -> list[AuditLog]:
    return list(
        session.exec(select(AuditLog).where(AuditLog.action == "match.forfeited")).all()
    )


def _forfeit_events(session: Session) -> list[OutboxEvent]:
    return list(
        session.exec(
            select(OutboxEvent)
            .where(OutboxEvent.type == "MatchForfeited")
            .order_by(col(OutboxEvent.created_at))
        ).all()
    )


def test_judge_forfeits_is_registered_before_confirm_expired_appeals() -> None:
    assert judge_forfeits in JOBS
    assert JOBS.index(judge_forfeits) < JOBS.index(confirm_expired_appeals)


def test_nothing_due_returns_false(session: Session, drawn: Drawn) -> None:
    # frozen_clock 在 10/18，第一輪的棄權期限還沒到
    assert judge_forfeits(session) is False


def test_one_round_judges_every_due_match(
    session: Session,
    session_factory: Callable[[], Session],
    drawn: Drawn,
    frozen_clock: FrozenClock,
) -> None:
    drawn.check_in(session, "M1", "a")  # 一方棄權：B 隊未報到
    drawn.check_in(session, "M2", "a", "b")  # 兩隊都到：不判
    # M3、M4 都沒人報到：雙方棄權
    frozen_clock.set(DEADLINE)

    run_once([judge_forfeits], session_factory=session_factory)
    session.expire_all()

    m1 = drawn.match(session, "M1")
    assert m1.status == MatchStatus.APPEAL_WINDOW
    assert m1.outcome == MatchOutcome.FORFEIT
    assert m1.winner_id == m1.team_a_id
    assert m1.appeal_deadline == DEADLINE + timedelta(minutes=30)
    assert drawn.match(session, "M2").status == MatchStatus.SCHEDULED
    for code in ("M3", "M4"):
        match = drawn.match(session, code)
        assert match.status == MatchStatus.APPEAL_WINDOW
        assert match.outcome == MatchOutcome.DOUBLE_FORFEIT
        assert match.winner_id is None

    judged = {drawn.ids[c] for c in ("M1", "M3", "M4")}
    assert {a.entity_id for a in _forfeit_audits(session)} == judged
    assert {
        uuid.UUID(e.payload["match_id"]) for e in _forfeit_events(session)
    } == judged
    # 再跑一次不會重複判
    assert judge_forfeits(session) is False


def test_cancelled_tournament_is_skipped(
    session: Session,
    session_factory: Callable[[], Session],
    drawn: Drawn,
    frozen_clock: FrozenClock,
) -> None:
    tournament = session.get(Tournament, drawn.tournament_id)
    assert tournament is not None
    tournament.status = TournamentStatus.CANCELLED
    session.add(tournament)
    session.commit()
    frozen_clock.set(DEADLINE)

    run_once([judge_forfeits], session_factory=session_factory)
    session.expire_all()

    for code in ROUND_ONE:
        assert drawn.match(session, code).status == MatchStatus.SCHEDULED
    assert _forfeit_audits(session) == []


def test_forfeit_then_appeal_expiry_confirms_and_advances(
    session: Session,
    session_factory: Callable[[], Session],
    drawn: Drawn,
    frozen_clock: FrozenClock,
) -> None:
    for code in ROUND_ONE:
        drawn.check_in(session, code, "a")  # 每場都是 A 隊勝
    frozen_clock.set(DEADLINE)
    run_once([judge_forfeits, dispatch_outbox], session_factory=session_factory)

    # 申訴期滿後同一個 worker 清單的下一個工作確認並推進晉級
    frozen_clock.advance(timedelta(minutes=30))
    run_once(
        [judge_forfeits, confirm_expired_appeals, dispatch_outbox],
        session_factory=session_factory,
    )
    session.expire_all()

    winners = []
    for code in ROUND_ONE:
        match = drawn.match(session, code)
        assert match.status == MatchStatus.CONFIRMED
        winners.append(match.winner_id)
    second_round = [
        drawn.match(session, code)
        for code in drawn.ids
        if drawn.match(session, code).round_no == 2
        and not drawn.match(session, code).is_third_place
    ]
    advanced = {t for m in second_round for t in (m.team_a_id, m.team_b_id)}
    assert advanced == set(winners)


def test_adapter_rejects_non_row_match(session: Session) -> None:
    class NotARow:
        pass

    with pytest.raises(TypeError):
        SERVICE_FORFEIT_PORTS.transition_to_appeal_window(
            session,
            match=NotARow(),  # type: ignore[arg-type]
        )
