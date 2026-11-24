"""Story 6.3：申訴逾期提醒（`remind_due_appeal`）與 S32 的處理期限。

沿用 test_score_entry 的已抽籤 8 隊賽事與 test_resolve_appeals 的輔助函式：申訴直接
寫入資料表，場次直接寫成申訴中。準決賽申訴時，決賽與季軍賽都在等它的結果。
"""

# ruff: noqa: F811  (從 test_score_entry 匯入 fixture，參數同名是 pytest 的用法)

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core import clock
from app.core.events import OutboxEvent
from app.modules.competition.models import Match, MatchStatus
from app.modules.disputes import service
from app.modules.disputes.models import Appeal, AppealStatus
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    Tournament,
    TournamentRead,
    TournamentStatus,
)
from tests.competition.conftest import (  # noqa: F401
    FakeRegistration,
    fake_registration,
)
from tests.competition.test_score_entry import (  # noqa: F401
    Factory,
    Setup,
    make_setup,
    setup,
)
from tests.conftest import FrozenClock
from tests.disputes.test_resolve_appeals import (
    _appealed,
    _seat,
    _set_time,
    _third_place_code,
)
from tests.helpers import make_account

# 決賽 14:00；季軍賽排在決賽之後，處理期限取兩者較早的決賽
FINAL_AT = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _team_names(
    fake_registration: FakeRegistration, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S32 的隊名由 registration `get_team_names` 查：改用假的 registration 的隊名。"""
    monkeypatch.setattr(
        registration_service, "get_team_names", fake_registration.get_team_names
    )


def _reminded_events(session: Session) -> list[OutboxEvent]:
    return list(
        session.exec(select(OutboxEvent).where(OutboxEvent.type == "AppealReminded"))
    )


def _fresh(session: Session, appeal: Appeal) -> Appeal:
    session.expire_all()
    row = session.get(Appeal, appeal.id)
    assert row is not None
    return row


def _semi_appeal(
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
    *,
    filed_at: datetime = FINAL_AT - timedelta(hours=3),
    teams: str = "a",
) -> list[Appeal]:
    """準決賽申訴中：決賽 14:00、季軍賽 15:00（處理期限為 14:00，提醒時間 13:00）。"""
    semi = setup.next_code("M1")
    _seat(session, setup, semi)
    frozen_clock.set(filed_at)
    appeals = _appealed(session, setup, code=semi, teams=teams)
    _set_time(session, setup, setup.next_code(semi), FINAL_AT)
    _set_time(session, setup, _third_place_code(setup), FINAL_AT + timedelta(hours=1))
    return appeals


def _final_code(setup: Setup) -> str:
    return setup.next_code(setup.next_code("M1"))


def _set_tournament_status(
    session: Session, setup: Setup, status: TournamentStatus
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.commit()


# ---------------------------------------------------------------- 提醒時間


def test_semifinal_appeal_is_reminded_once_an_hour_before_next_match(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    frozen_clock.set(FINAL_AT - timedelta(hours=1))

    assert service.remind_due_appeal(session) is True
    session.commit()

    events = _reminded_events(session)
    assert [e.payload for e in events] == [
        {
            "appeal_id": str(appeal.id),
            "match_id": str(appeal.match_id),
            "tournament_id": str(setup.tournament_id),
        }
    ]
    assert _fresh(session, appeal).reminded_at == clock.now()

    # 再輪詢一次：同一筆申訴不再提醒
    frozen_clock.advance(timedelta(minutes=5))
    assert service.remind_due_appeal(session) is False
    assert len(_reminded_events(session)) == 1


def test_not_reminded_before_remind_time(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    frozen_clock.set(FINAL_AT - timedelta(hours=1, minutes=1))

    assert service.remind_due_appeal(session) is False

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at is None


def test_appeal_filed_after_remind_time_is_reminded_immediately(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    _semi_appeal(
        session, setup, frozen_clock, filed_at=FINAL_AT - timedelta(minutes=30)
    )

    assert service.remind_due_appeal(session) is True
    assert len(_reminded_events(session)) == 1


def test_final_appeal_is_reminded_one_hour_after_filing(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    final = _final_code(setup)
    _seat(session, setup, final)
    filed_at = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    frozen_clock.set(filed_at)
    (appeal,) = _appealed(session, setup, code=final, teams="a")

    frozen_clock.set(filed_at + timedelta(minutes=59))
    assert service.remind_due_appeal(session) is False

    frozen_clock.set(filed_at + timedelta(hours=1))
    assert service.remind_due_appeal(session) is True
    session.commit()
    assert _fresh(session, appeal).reminded_at == filed_at + timedelta(hours=1)
    assert len(_reminded_events(session)) == 1


def test_third_place_appeal_is_reminded_one_hour_after_filing(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    third = _third_place_code(setup)
    _seat(session, setup, third)
    filed_at = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    frozen_clock.set(filed_at)
    _appealed(session, setup, code=third, teams="b")

    frozen_clock.set(filed_at + timedelta(minutes=59))
    assert service.remind_due_appeal(session) is False

    frozen_clock.set(filed_at + timedelta(hours=1))
    assert service.remind_due_appeal(session) is True
    assert len(_reminded_events(session)) == 1


# ---------------------------------------------------------------- 不提醒


def test_already_reminded_appeal_is_skipped(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    earlier = FINAL_AT - timedelta(hours=2)
    row = _fresh(session, appeal)
    row.reminded_at = earlier
    session.add(row)
    session.commit()
    frozen_clock.set(FINAL_AT - timedelta(minutes=30))

    assert service.remind_due_appeal(session) is False

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at == earlier


def test_closed_appeal_is_not_reminded(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    row = _fresh(session, appeal)
    row.status = AppealStatus.CLOSED
    session.add(row)
    session.commit()
    frozen_clock.set(FINAL_AT - timedelta(minutes=30))

    assert service.remind_due_appeal(session) is False

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at is None


@pytest.mark.parametrize(
    "status", [TournamentStatus.CANCELLED, TournamentStatus.FINISHED]
)
def test_ended_tournament_is_skipped(
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
    status: TournamentStatus,
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    _set_tournament_status(session, setup, status)
    frozen_clock.set(FINAL_AT - timedelta(minutes=30))

    assert service.remind_due_appeal(session) is False

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at is None


def test_two_appeals_on_one_match_are_each_reminded_once(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    appeals = _semi_appeal(session, setup, frozen_clock, teams="ab")
    frozen_clock.set(FINAL_AT - timedelta(hours=1))

    assert service.remind_due_appeal(session) is True
    session.commit()
    assert service.remind_due_appeal(session) is True
    session.commit()
    assert service.remind_due_appeal(session) is False

    events = _reminded_events(session)
    assert sorted(e.payload["appeal_id"] for e in events) == sorted(
        str(a.id) for a in appeals
    )
    assert all(_fresh(session, a).reminded_at == clock.now() for a in appeals)


# ---------------------------------------------------------------- S32 處理期限


def test_appeal_groups_carry_handling_deadline(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    """未結案的場次帶處理期限（與 S27 相同）；已結案的場次為 None。"""
    _semi_appeal(session, setup, frozen_clock)
    final = _final_code(setup)
    _seat(session, setup, final)
    (final_appeal,) = _appealed(session, setup, code=final, teams="b")
    row = _fresh(session, final_appeal)
    row.status = AppealStatus.CLOSED
    session.add(row)
    session.commit()

    groups = service.list_tournament_appeals(
        session, tournament_id=setup.tournament_id, actor_id=setup.organizer.id
    )

    deadlines = {g.match_code: g.deadline for g in groups}
    assert deadlines == {setup.next_code("M1"): FINAL_AT, final: None}


def test_final_group_deadline_uses_earliest_open_appeal(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    """決賽兩筆未結案申訴（10:00、10:01 提出）：處理期限為 11:00。"""
    final = _final_code(setup)
    _seat(session, setup, final)
    filed_at = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    frozen_clock.set(filed_at)
    _appealed(session, setup, code=final, teams="ab")

    (group,) = service.list_tournament_appeals(
        session, tournament_id=setup.tournament_id, actor_id=setup.organizer.id
    )

    assert group.deadline == filed_at + timedelta(hours=1)


def test_final_group_deadline_ignores_closed_earlier_appeal(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    """較早的申訴已結案、較新的未結案：處理期限依較新那一筆的提出時間。"""
    final = _final_code(setup)
    _seat(session, setup, final)
    frozen_clock.set(datetime(2026, 10, 26, 10, 0, tzinfo=UTC))
    (old,) = _appealed(session, setup, code=final, teams="a")
    row = _fresh(session, old)
    row.status = AppealStatus.CLOSED
    session.add(row)
    newer_at = datetime(2026, 10, 26, 10, 30, tzinfo=UTC)
    session.add(
        Appeal(
            tournament_id=setup.tournament_id,
            match_id=row.match_id,
            team_id=setup.team("b", final),
            filed_by=make_account(session).id,
            filed_at=newer_at,
            description="b 隊的申訴",
            status=AppealStatus.OPEN,
        )
    )
    session.commit()

    (group,) = service.list_tournament_appeals(
        session, tournament_id=setup.tournament_id, actor_id=setup.organizer.id
    )

    assert group.deadline == newer_at + timedelta(hours=1)


# ---------------------------------------------------------------- 已取消的下一場


def _set_match(session: Session, setup: Setup, code: str, **fields: object) -> None:
    row = session.get(Match, setup.match_id(code))
    assert row is not None
    for key, value in fields.items():
        setattr(row, key, value)
    session.add(row)
    session.commit()


def test_voided_third_place_is_not_a_next_match(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    """季軍賽已取消（例如雙方棄權）且排得比決賽早：處理期限與提醒時間只看決賽。"""
    _semi_appeal(session, setup, frozen_clock)
    _set_match(
        session,
        setup,
        _third_place_code(setup),
        status=MatchStatus.VOIDED,
        scheduled_at=FINAL_AT - timedelta(hours=1),
    )

    # 若把已取消的季軍賽算進去，提醒時間會是 FINAL_AT − 2 小時
    frozen_clock.set(FINAL_AT - timedelta(hours=2))
    assert service.remind_due_appeal(session) is False
    (group,) = service.list_tournament_appeals(
        session, tournament_id=setup.tournament_id, actor_id=setup.organizer.id
    )
    assert group.deadline == FINAL_AT

    frozen_clock.set(FINAL_AT - timedelta(hours=1))
    assert service.remind_due_appeal(session) is True
    assert len(_reminded_events(session)) == 1


def test_all_next_matches_voided_uses_one_hour_after_filing(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    filed_at = FINAL_AT - timedelta(hours=3)
    _semi_appeal(session, setup, frozen_clock, filed_at=filed_at)
    for code in (_final_code(setup), _third_place_code(setup)):
        _set_match(session, setup, code, status=MatchStatus.VOIDED)

    (group,) = service.list_tournament_appeals(
        session, tournament_id=setup.tournament_id, actor_id=setup.organizer.id
    )
    assert group.deadline == filed_at + timedelta(hours=1)

    frozen_clock.set(filed_at + timedelta(minutes=59))
    assert service.remind_due_appeal(session) is False
    frozen_clock.set(filed_at + timedelta(hours=1))
    assert service.remind_due_appeal(session) is True


# ---------------------------------------------------------------- 鎖內重新檢查與交易


def _change_before_lock(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: Callable[[], Session],
    mutate: Callable[[Session], None],
) -> None:
    """在不鎖定的預先檢查之後、鎖住賽事之前，由另一個 session 改資料並提交（模擬併發）。"""
    original = tournaments_service.lock_tournament

    def lock(session: Session, *, tournament_id: uuid.UUID) -> TournamentRead:
        with session_factory() as other:
            mutate(other)
            other.commit()
        return original(session, tournament_id=tournament_id)

    monkeypatch.setattr(tournaments_service, "lock_tournament", lock)


def test_reschedule_seen_only_after_lock_prevents_reminder(
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """預先檢查看到舊的決賽時間（已到提醒時間），鎖住前決賽改到更晚：不提醒。"""
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    frozen_clock.set(FINAL_AT - timedelta(hours=1))
    later = FINAL_AT + timedelta(hours=2)
    # identity map 是弱參照：預先檢查讀過的場次可能剛好被回收，讓測試碰巧通過。
    # 在主 session 持有決賽、季軍賽的強參照（值為改期前），確保鎖內重新檢查真的重讀資料庫
    held: list[Match | None] = []

    def reschedule(other: Session) -> None:
        held.extend(
            session.get(Match, setup.match_id(code))
            for code in (_final_code(setup), _third_place_code(setup))
        )
        for code in (_final_code(setup), _third_place_code(setup)):
            row = other.get(Match, setup.match_id(code))
            assert row is not None
            row.scheduled_at = later
            other.add(row)

    _change_before_lock(monkeypatch, session_factory, reschedule)

    assert service.remind_due_appeal(session) is True
    session.commit()

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at is None


@pytest.mark.parametrize("change", ["closed", "reminded", "cancelled", "finished"])
def test_state_seen_only_after_lock_prevents_reminder(
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClock,
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    frozen_clock.set(FINAL_AT - timedelta(hours=1))
    earlier = FINAL_AT - timedelta(hours=2)

    def mutate(other: Session) -> None:
        if change in ("closed", "reminded"):
            row = other.get(Appeal, appeal.id)
            assert row is not None
            if change == "closed":
                row.status = AppealStatus.CLOSED
            else:
                row.reminded_at = earlier
            other.add(row)
        else:
            tournament = other.get(Tournament, setup.tournament_id)
            assert tournament is not None
            tournament.status = (
                TournamentStatus.CANCELLED
                if change == "cancelled"
                else TournamentStatus.FINISHED
            )
            other.add(tournament)

    _change_before_lock(monkeypatch, session_factory, mutate)

    assert service.remind_due_appeal(session) is True
    session.commit()

    assert _reminded_events(session) == []
    expected = earlier if change == "reminded" else None
    assert _fresh(session, appeal).reminded_at == expected


def test_does_not_commit(
    session: Session, setup: Setup, frozen_clock: FrozenClock
) -> None:
    (appeal,) = _semi_appeal(session, setup, frozen_clock)
    frozen_clock.set(FINAL_AT - timedelta(hours=1))

    assert service.remind_due_appeal(session) is True
    session.rollback()

    assert _reminded_events(session) == []
    assert _fresh(session, appeal).reminded_at is None
