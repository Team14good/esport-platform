"""6.2／6.5 前置：`check_replay_time`、`get_replay_window`、`unassign_referee_if_member`。

沿用 test_reschedule 的 8 隊對戰表（frozen_clock 為 2026-10-18 11:00 UTC）：第一輪 M1～M4
在 10-26 11:00、準決賽 M5、M6 在 14:00、決賽 M7 與季軍賽 M8 在 17:00；最小間隔 165 分鐘。
申訴中的場次直接寫入狀態與棄權結果模擬；registration 的 `is_member` 以 `members` 集合替身，
以待定（None）的隊伍呼叫時直接失敗。
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update
from sqlmodel import Session, col, func, select

from app.core import audit, clock
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, service
from app.modules.competition.models import CheckIn, Match, MatchOutcome, MatchStatus
from app.modules.identity.models import Account
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration
from tests.competition.test_reschedule import (
    FLOOR,
    GAP,
    MINUTE,
    NOW,
    R1,
    R2,
    R3,
    Setup,
)
from tests.helpers import make_account

pytestmark = pytest.mark.usefixtures("frozen_clock")


class HookSetup(Setup):
    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        super().__init__(session, fake)
        self.members: set[tuple[uuid.UUID, uuid.UUID]] = set()
        self.member_calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def appeal(self, code: str) -> None:
        """申訴中、棄權結果（可以重賽的場次）。"""
        self.update(code, status=MatchStatus.APPEALED, outcome=MatchOutcome.FORFEIT)

    def team(self, code: str, side: str) -> uuid.UUID:
        row = self.row(code)
        team = row.team_a_id if side == "a" else row.team_b_id
        assert team is not None
        return team

    def tournament_status(self, status: TournamentStatus) -> None:
        row = self.session.get(Tournament, self.tournament_id)
        assert row is not None
        row.status = status
        self.session.add(row)
        self.session.commit()


@pytest.fixture
def setup(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> HookSetup:
    result = HookSetup(session, fake_registration)

    def is_member(
        _session: Session, *, team_id: uuid.UUID | None, account_id: uuid.UUID
    ) -> bool:
        assert team_id is not None, "不能以待定的隊伍查隊員"
        result.member_calls.append((team_id, account_id))
        return (team_id, account_id) in result.members

    monkeypatch.setattr(registration_port, "is_member", is_member)
    session.commit()
    return result


def _check(session: Session, setup: HookSetup, code: str, at: datetime) -> None:
    """照 B 的 `replay_match` 呼叫：先鎖賽事、再鎖場次。"""
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=setup.tournament_id
    )
    match = service.lock_match(session, match_id=setup.matches[code].id)
    service.check_replay_time(
        session, tournament=tournament, match=match, scheduled_at=at
    )


def _check_error(
    session: Session, setup: HookSetup, code: str, at: datetime
) -> BusinessError:
    with pytest.raises(BusinessError) as error:
        _check(session, setup, code, at)
    assert error.value.status_code == 409
    return error.value


def _outcome(
    session: Session, setup: HookSetup, code: str, at: datetime
) -> tuple[str, str] | None:
    try:
        _check(session, setup, code, at)
    except BusinessError as error:
        return error.code, error.message
    return None


def _reschedule_error(
    session: Session, setup: HookSetup, code: str, at: datetime
) -> BusinessError:
    with pytest.raises(BusinessError) as error:
        service.reschedule_match(
            session,
            tournament_id=setup.tournament_id,
            match_id=setup.matches[code].id,
            actor_id=setup.organizer.id,
            scheduled_at=at,
        )
    return error.value


def _writes(session: Session, setup: HookSetup) -> tuple[object, ...]:
    """場次欄位、該賽事的操作紀錄數、outbox 事件總數。

    先 flush 再丟掉記憶體中的物件，所以函式在拋錯前改過的欄位（即使還沒 commit）也會被看到。
    """
    session.flush()
    session.expire_all()
    audits = len(audit.list_for_tournament(session, setup.tournament_id))
    events = session.exec(select(func.count()).select_from(OutboxEvent)).one()
    rows = {}
    for code in setup.matches:
        row = setup.row(code)
        rows[code] = (
            row.status,
            row.outcome,
            row.scheduled_at,
            row.forfeit_deadline,
            row.referee_account_id,
            row.team_a_id,
            row.team_b_id,
            row.updated_at,
        )
    return rows, audits, events


# ---------------------------------------------------------------- check_replay_time


def test_valid_time_returns_none_and_writes_nothing(
    session: Session, setup: HookSetup
) -> None:
    setup.appeal("M1")
    before = _writes(session, setup)

    for at in (FLOOR, R1, R2 - GAP):
        _check(session, setup, "M1", at)

    assert _writes(session, setup) == before


@pytest.mark.parametrize(
    ("code", "at", "expected"),
    [
        ("M1", FLOOR - MINUTE, "RESCHEDULE_BEFORE_NOW"),
        ("M1", R2 - GAP + MINUTE, "RESCHEDULE_AFTER_NEXT_MATCH"),
        ("M5", R1 + GAP - MINUTE, "RESCHEDULE_BEFORE_FEEDER"),
        ("M5", R3 - GAP + MINUTE, "RESCHEDULE_AFTER_NEXT_MATCH"),
        ("M7", R2 + GAP - MINUTE, "RESCHEDULE_BEFORE_FEEDER"),
    ],
)
def test_same_error_as_reschedule_match(
    session: Session, setup: HookSetup, code: str, at: datetime, expected: str
) -> None:
    setup.appeal(code)
    before = _writes(session, setup)

    replay = _check_error(session, setup, code, at)
    # 不 rollback：拋錯前若寫過任何東西，flush 後就會出現差異
    assert _writes(session, setup) == before

    # 等價情境：同一場、同一時間，改回待開打後走 4.3 改期
    setup.update(code, status=MatchStatus.SCHEDULED, outcome=None)
    reschedule = _reschedule_error(session, setup, code, at)

    assert replay.code == expected
    assert (replay.code, replay.message, replay.status_code) == (
        reschedule.code,
        reschedule.message,
        reschedule.status_code,
    )


def test_range_message_verbatim(session: Session, setup: HookSetup) -> None:
    setup.appeal("M1")

    early = _check_error(session, setup, "M1", FLOOR - MINUTE)
    late = _check_error(session, setup, "M1", R2 - GAP + MINUTE)

    # 最早：現在 10/18 11:00 UTC＋30 分鐘；最晚：M5 14:00 UTC − 165 分鐘（台北時間）
    expected = "新時間不在允許範圍內，可選 10/18（日）19:30～10/26（一）19:15。"
    assert early.message == expected
    assert late.message == expected


def test_semifinal_uses_earlier_of_final_and_third_place(
    session: Session, setup: HookSetup
) -> None:
    # 季軍賽 M8 早於決賽 M7：準決賽的最晚以 M8 為準，不能只看勝隊去的 next_match_id
    third = R2 + GAP
    setup.update("M8", scheduled_at=third)
    setup.appeal("M5")
    latest = third - GAP

    info = service.get_replay_window(session, match_id=setup.matches["M5"].id)
    assert info.latest == latest
    _check(session, setup, "M5", latest)
    assert _check_error(session, setup, "M5", latest + MINUTE).code == (
        "RESCHEDULE_AFTER_NEXT_MATCH"
    )


def test_no_valid_time_when_appeal_drags(session: Session, setup: HookSetup) -> None:
    # 申訴拖久：決賽與季軍賽已排在現在附近，準決賽重賽沒有可選時間
    setup.update("M7", scheduled_at=NOW + timedelta(hours=1))
    setup.update("M8", scheduled_at=NOW + timedelta(hours=1))
    setup.appeal("M5")
    before = _writes(session, setup)

    replay = _check_error(session, setup, "M5", R2)

    assert _writes(session, setup) == before
    assert replay.code == "RESCHEDULE_NO_VALID_TIME"
    assert replay.message == "這場目前沒有可選的時間（最早 10/26（一）21:45）。"
    info = service.get_replay_window(session, match_id=setup.matches["M5"].id)
    assert info.can_reschedule is False
    assert info.reason == "no_valid_time"
    assert info.earliest == R1 + GAP
    assert info.latest == NOW + timedelta(hours=1) - GAP

    setup.update("M5", status=MatchStatus.SCHEDULED, outcome=None)
    reschedule = _reschedule_error(session, setup, "M5", R2)
    assert (reschedule.code, reschedule.message) == (replay.code, replay.message)


def test_ignores_status_and_check_ins(session: Session, setup: HookSetup) -> None:
    """不看場次狀態與報到：轉回待開打、有報到資料時結果與申訴中相同。"""
    times = (FLOOR - MINUTE, FLOOR, R2 - GAP, R2 - GAP + MINUTE)
    setup.appeal("M1")
    appealed = [_outcome(session, setup, "M1", at) for at in times]
    assert appealed[1] is None and appealed[2] is None
    assert appealed[0] is not None and appealed[3] is not None

    match = service.lock_match(session, match_id=setup.matches["M1"].id)
    service.transition_match(session, match=match, to=MatchStatus.SCHEDULED)
    session.commit()
    assert [_outcome(session, setup, "M1", at) for at in times] == appealed

    for side in ("a", "b"):
        session.add(
            CheckIn(
                match_id=setup.matches["M1"].id,
                team_id=setup.team("M1", side),
                account_id=setup.organizer.id,
                at=clock.now(),
            )
        )
    session.commit()
    assert [_outcome(session, setup, "M1", at) for at in times] == appealed


def test_reads_latest_neighbour_times(session: Session, setup: HookSetup) -> None:
    """下一場的時間被別的交易改過：不沿用 identity map 裡的舊值。"""
    setup.appeal("M1")
    stale = setup.row("M5")  # 載入舊的 14:00
    assert stale.scheduled_at == R2
    later = R2 + timedelta(hours=1)
    # 不經 ORM、不同步 identity map，模擬其他交易已寫入
    session.execute(
        update(Match)
        .where(col(Match.id) == setup.matches["M5"].id)
        .values(scheduled_at=later)
        .execution_options(synchronize_session=False)
    )
    assert stale.scheduled_at == R2

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)
    assert info.latest == later - GAP

    session.execute(
        update(Match)
        .where(col(Match.id) == setup.matches["M5"].id)
        .values(scheduled_at=R2 + timedelta(hours=2))
        .execution_options(synchronize_session=False)
    )
    _check(session, setup, "M1", R2 + timedelta(hours=2) - GAP)


def test_tournament_mismatch_and_naive_time_are_value_errors(
    session: Session, setup: HookSetup
) -> None:
    setup.appeal("M1")
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=setup.tournament_id
    )
    match = service.lock_match(session, match_id=setup.matches["M1"].id)
    other = tournament.model_copy(update={"id": uuid.uuid4()})

    with pytest.raises(ValueError, match="所屬的賽事"):
        service.check_replay_time(
            session, tournament=other, match=match, scheduled_at=R1
        )
    with pytest.raises(ValueError, match="時區"):
        service.check_replay_time(
            session,
            tournament=tournament,
            match=match,
            scheduled_at=R1.replace(tzinfo=None),
        )


# ---------------------------------------------------------------- get_replay_window


def test_window_for_appealed_match_matches_check(
    session: Session, setup: HookSetup
) -> None:
    setup.appeal("M1")
    before = _writes(session, setup)

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert info.can_reschedule is True
    assert info.reason is None
    assert (info.earliest, info.latest) == (FLOOR, R2 - GAP)
    assert info.latest is not None
    _check(session, setup, "M1", info.earliest)
    _check(session, setup, "M1", info.latest)
    assert _check_error(session, setup, "M1", info.latest + MINUTE).code == (
        "RESCHEDULE_AFTER_NEXT_MATCH"
    )
    assert _writes(session, setup) == before


def test_window_ongoing_tournament(session: Session, setup: HookSetup) -> None:
    setup.tournament_status(TournamentStatus.ONGOING)
    setup.appeal("M1")

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert (info.can_reschedule, info.reason) == (True, None)


@pytest.mark.parametrize("code", ["M7", "M8"])
def test_final_and_third_place_have_no_upper_bound(
    session: Session, setup: HookSetup, code: str
) -> None:
    setup.appeal(code)

    info = service.get_replay_window(session, match_id=setup.matches[code].id)

    assert info.can_reschedule is True
    assert info.latest is None
    assert info.earliest == R2 + GAP
    _check(session, setup, code, R3 + timedelta(days=60))


@pytest.mark.parametrize(
    "status",
    [
        MatchStatus.SCHEDULED,
        MatchStatus.LIVE,
        MatchStatus.APPEAL_WINDOW,
        MatchStatus.CONFIRMED,
        MatchStatus.VOIDED,
    ],
)
def test_window_not_appealed(
    session: Session, setup: HookSetup, status: MatchStatus
) -> None:
    # 結果是棄權，只有狀態不對
    setup.update("M1", status=status, outcome=MatchOutcome.FORFEIT)
    before = _writes(session, setup)

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert info.can_reschedule is False
    assert info.reason == "match_not_reschedulable"
    assert (info.earliest, info.latest) == (None, None)
    assert _writes(session, setup) == before


@pytest.mark.parametrize(
    "outcome", [None, MatchOutcome.PLAYED, MatchOutcome.DOUBLE_FORFEIT]
)
def test_window_appealed_but_not_forfeit(
    session: Session, setup: HookSetup, outcome: MatchOutcome | None
) -> None:
    setup.update("M1", status=MatchStatus.APPEALED, outcome=outcome)

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert info.can_reschedule is False
    assert info.reason == "match_not_reschedulable"
    assert (info.earliest, info.latest) == (None, None)


@pytest.mark.parametrize(
    "status",
    [TournamentStatus.CANCELLED, TournamentStatus.FINISHED, TournamentStatus.CLOSED],
)
def test_window_tournament_not_reschedulable(
    session: Session, setup: HookSetup, status: TournamentStatus
) -> None:
    setup.appeal("M1")
    setup.tournament_status(status)
    before = _writes(session, setup)

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert info.can_reschedule is False
    assert info.reason == "tournament_not_reschedulable"
    assert (info.earliest, info.latest) == (None, None)
    assert _writes(session, setup) == before


def test_tournament_reason_comes_before_match_reason(
    session: Session, setup: HookSetup
) -> None:
    setup.update("M1", status=MatchStatus.SCHEDULED)
    setup.tournament_status(TournamentStatus.CANCELLED)

    info = service.get_replay_window(session, match_id=setup.matches["M1"].id)

    assert info.reason == "tournament_not_reschedulable"


@pytest.mark.usefixtures("setup")
def test_window_unknown_match_is_404(session: Session) -> None:
    with pytest.raises(BusinessError) as error:
        service.get_replay_window(session, match_id=uuid.uuid4())

    assert (error.value.code, error.value.status_code) == ("MATCH_NOT_FOUND", 404)


# ---------------------------------------------------------------- unassign_referee_if_member


def _referee_on(session: Session, setup: HookSetup, code: str) -> Account:
    referee = make_account(session)
    setup.update(code, referee_account_id=referee.id)
    return referee


def _unassign(session: Session, setup: HookSetup, code: str) -> None:
    tournaments_service.lock_tournament(session, tournament_id=setup.tournament_id)
    match = service.lock_match(session, match_id=setup.matches[code].id)
    service.unassign_referee_if_member(session, match=match)
    session.commit()


def _unassigned_logs(session: Session) -> list[audit.AuditLog]:
    return list(
        session.exec(
            select(audit.AuditLog).where(
                audit.AuditLog.action == "match.referee_unassigned"
            )
        )
    )


def _unassigned_events(session: Session) -> list[dict[str, object]]:
    rows = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "RefereeUnassigned")
    ).all()
    return [row.payload for row in rows]


def _assert_unassigned_once(
    session: Session, setup: HookSetup, code: str, referee: Account
) -> None:
    assert setup.row(code).referee_account_id is None
    (log,) = _unassigned_logs(session)
    assert log.actor_id is None
    assert log.entity_id == setup.matches[code].id
    assert log.before == {"referee_account_id": str(referee.id)}
    assert log.after == {"referee_account_id": None}
    assert _unassigned_events(session) == [
        {
            "match_id": str(setup.matches[code].id),
            "referee_account_id": str(referee.id),
        }
    ]


@pytest.mark.parametrize("sides", [("a",), ("b",), ("a", "b")])
def test_member_referee_is_unassigned(
    session: Session, setup: HookSetup, sides: tuple[str, ...]
) -> None:
    referee = _referee_on(session, setup, "M1")
    for side in sides:
        setup.members.add((setup.team("M1", side), referee.id))

    _unassign(session, setup, "M1")

    _assert_unassigned_once(session, setup, "M1", referee)


@pytest.mark.parametrize("filled", ["a", "b"])
def test_one_side_pending_member_referee_is_unassigned(
    session: Session, setup: HookSetup, filled: str
) -> None:
    """取消資格最常見的情況：頂替後一方已定、另一方仍待定，裁判是已定那隊的隊員。"""
    team = setup.team("M1", "a")
    setup.update("M5", **{f"team_{filled}_id": team})
    referee = _referee_on(session, setup, "M5")
    setup.members.add((team, referee.id))

    _unassign(session, setup, "M5")

    _assert_unassigned_once(session, setup, "M5", referee)


def test_non_member_referee_kept(session: Session, setup: HookSetup) -> None:
    referee = _referee_on(session, setup, "M1")
    # 是別場隊伍的隊員，不影響這場
    setup.members.add((setup.team("M2", "a"), referee.id))
    before = _writes(session, setup)

    _unassign(session, setup, "M1")

    assert setup.row("M1").referee_account_id == referee.id
    assert _writes(session, setup) == before
    assert len(setup.member_calls) == 2


def test_no_referee_does_nothing(session: Session, setup: HookSetup) -> None:
    someone = make_account(session)
    setup.members.add((setup.team("M1", "a"), someone.id))
    setup.members.add((setup.team("M1", "b"), someone.id))
    session.commit()
    before = _writes(session, setup)

    _unassign(session, setup, "M1")

    assert _writes(session, setup) == before
    assert setup.member_calls == []


def test_pending_teams_do_nothing(session: Session, setup: HookSetup) -> None:
    referee = _referee_on(session, setup, "M5")
    # 裁判是 M1、M2 隊伍的隊員，但 M5 兩方都還待定（替身遇到 None 會失敗）
    setup.members.add((setup.team("M1", "a"), referee.id))
    setup.members.add((setup.team("M2", "a"), referee.id))
    before = _writes(session, setup)

    _unassign(session, setup, "M5")

    assert setup.row("M5").referee_account_id == referee.id
    assert _writes(session, setup) == before
    assert setup.member_calls == []
