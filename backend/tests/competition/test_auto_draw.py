"""Story 4.2：報名截止的賽事由系統自動抽籤（`auto_draw`、`auto_draw_due`）。

registration 以 `fake_registration` 替身取代；真的 registration 接起來的「截止補位 →
抽籤」在 tests/worker/test_auto_draw.py。手動與自動同時抽籤的併發在
test_auto_draw_concurrency.py。

`auto_draw_due` 會從整個測試資料庫找「報名截止」的賽事，其中可能有其他併發測試留下、
已提交的賽事；斷言一律只看本測試建立的賽事。
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlmodel import Session, col, func, select

from app.core import audit
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, service
from app.modules.competition.models import AutoDrawSkip, Bracket
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentRead, TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    count_matches,
    draw_with,
    tournament_in,
)
from tests.helpers import make_account

S = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")


def _status(session: Session, tournament: TournamentRead) -> TournamentStatus:
    session.expire_all()
    return tournaments_service.get_tournament(
        session, tournament_id=tournament.id
    ).status


def _events(
    session: Session, tournament: TournamentRead, event_type: str
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(OutboxEvent)
        .where(OutboxEvent.type == event_type)
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
    )
    return [r.payload for r in rows if r.payload["tournament_id"] == str(tournament.id)]


def _logs(session: Session, tournament: TournamentRead, action: str) -> list[Any]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == action
    ]


def _skips(session: Session, tournament: TournamentRead) -> int:
    statement = select(func.count()).where(AutoDrawSkip.tournament_id == tournament.id)
    return session.exec(statement).one()


def _has_bracket(session: Session, tournament: TournamentRead) -> bool:
    statement = select(Bracket).where(Bracket.tournament_id == tournament.id)
    return session.exec(statement).first() is not None


def _snapshot(session: Session, tournament: TournamentRead) -> tuple[Any, ...]:
    return (
        _status(session, tournament),
        _has_bracket(session, tournament),
        _skips(session, tournament),
        len(audit.list_for_tournament(session, tournament.id)),
        len(_events(session, tournament, "AutoDrawSkipped")),
        len(_events(session, tournament, "BracketDrawn")),
    )


# ---------------------------------------------------------------- 抽籤


@pytest.mark.parametrize("team_count", [2, 3, 13])
def test_closed_tournament_is_drawn_by_system(
    session: Session, fake_registration: FakeRegistration, team_count: int
) -> None:
    tournament = tournament_in(session, S.CLOSED)
    teams = fake_registration.set_team_count(team_count)

    assert service.auto_draw(session, tournament_id=tournament.id) == "drawn"

    assert _status(session, tournament) == S.PUBLISHED
    bracket = service.get_bracket(session, tournament_id=tournament.id)
    assert bracket is not None
    placed = {
        team
        for m in bracket.matches
        for team in (m.team_a_id, m.team_b_id)
        if team is not None
    }
    assert placed == set(teams)
    assert count_matches(session, tournament.id) == len(bracket.matches)
    # 與手動抽籤同一套：標為已參賽、操作紀錄、事件；操作者全部是系統
    assert len(fake_registration.drawn) == 1
    drawn_tournament, drawn_teams, drawn_actor = fake_registration.drawn[0]
    assert drawn_tournament == tournament.id
    assert sorted(drawn_teams) == sorted(teams)
    assert drawn_actor is None
    assert "finalize_for_draw" not in fake_registration.calls
    drawn_logs = _logs(session, tournament, "bracket.drawn")
    assert len(drawn_logs) == 1
    assert drawn_logs[0].actor_id is None
    assert drawn_logs[0].after["team_count"] == team_count
    published = _logs(session, tournament, "tournament.status_changed")
    assert [(log.actor_id, log.after) for log in published] == [
        (None, {"status": "published"})
    ]
    assert _events(session, tournament, "BracketDrawn") == [
        {"tournament_id": str(tournament.id), "bracket_id": str(bracket.id)}
    ]
    assert _events(session, tournament, "AutoDrawSkipped") == []
    assert _skips(session, tournament) == 0


def test_auto_draw_twice_draws_once(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament = tournament_in(session, S.CLOSED)
    fake_registration.set_team_count(4)
    assert service.auto_draw(session, tournament_id=tournament.id) == "drawn"
    before = _snapshot(session, tournament)

    assert service.auto_draw(session, tournament_id=tournament.id) == "not_due"

    assert _snapshot(session, tournament) == before
    assert len(fake_registration.drawn) == 1


def test_manual_draw_after_auto_draw_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    organizer = make_account(session, organizer=True)
    tournament = tournament_in(session, S.CLOSED, organizer=organizer)
    fake_registration.set_team_count(4)
    service.auto_draw(session, tournament_id=tournament.id)

    with pytest.raises(BusinessError) as exc:
        service.draw(session, tournament_id=tournament.id, actor_id=organizer.id)
    assert exc.value.code == "BRACKET_ALREADY_DRAWN"


def test_auto_draw_after_manual_draw_does_nothing(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament, _ = draw_with(session, fake_registration, 4)
    before = _snapshot(session, tournament)

    assert service.auto_draw(session, tournament_id=tournament.id) == "not_due"

    assert _snapshot(session, tournament) == before


# ---------------------------------------------------------------- 正取不足


@pytest.mark.parametrize("team_count", [0, 1])
def test_not_enough_teams_stays_closed_and_notifies_once(
    session: Session, fake_registration: FakeRegistration, team_count: int
) -> None:
    tournament = tournament_in(session, S.CLOSED)
    fake_registration.set_team_count(team_count)

    assert service.auto_draw(session, tournament_id=tournament.id) == "not_enough_teams"

    assert _status(session, tournament) == S.CLOSED
    assert not _has_bracket(session, tournament)
    assert fake_registration.drawn == []
    assert _events(session, tournament, "AutoDrawSkipped") == [
        {"tournament_id": str(tournament.id), "accepted_teams": team_count}
    ]
    assert _events(session, tournament, "BracketDrawn") == []
    logs = _logs(session, tournament, "bracket.auto_draw_skipped")
    assert [(log.actor_id, log.after) for log in logs] == [
        (None, {"reason": "not_enough_teams", "accepted_teams": team_count})
    ]
    assert _skips(session, tournament) == 1

    # 之後每一輪都不再處理，事件只發一次
    before = _snapshot(session, tournament)
    for _ in range(3):
        assert service.auto_draw(session, tournament_id=tournament.id) == "not_due"
    assert _snapshot(session, tournament) == before


def test_manual_draw_still_reports_not_enough_teams_after_skip(
    session: Session, fake_registration: FakeRegistration
) -> None:
    organizer = make_account(session, organizer=True)
    tournament = tournament_in(session, S.CLOSED, organizer=organizer)
    fake_registration.set_team_count(1)
    service.auto_draw(session, tournament_id=tournament.id)

    with pytest.raises(BusinessError) as exc:
        service.draw(session, tournament_id=tournament.id, actor_id=organizer.id)
    assert exc.value.code == "NOT_ENOUGH_TEAMS"


def test_new_registration_end_is_tried_again(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 期末的延長報名（2.5）會改報名截止時間；再次截止時要重新嘗試（本 Story 不做 2.5，
    # 這裡直接改欄位模擬）
    tournament = tournament_in(session, S.CLOSED)
    fake_registration.set_team_count(1)
    assert service.auto_draw(session, tournament_id=tournament.id) == "not_enough_teams"

    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.registration_end = row.registration_end + timedelta(days=1)
    session.add(row)
    session.flush()
    fake_registration.set_team_count(2)

    assert service.auto_draw(session, tournament_id=tournament.id) == "drawn"
    assert _status(session, tournament) == S.PUBLISHED


# ---------------------------------------------------------------- 不是候選


@pytest.mark.parametrize("status", [s for s in TournamentStatus if s != S.CLOSED])
def test_other_statuses_are_not_drawn(
    session: Session, fake_registration: FakeRegistration, status: TournamentStatus
) -> None:
    tournament = tournament_in(session, status)
    fake_registration.set_team_count(4)
    before = _snapshot(session, tournament)

    assert service.auto_draw(session, tournament_id=tournament.id) == "not_due"
    assert tournament.id not in tournaments_service.list_closed_tournament_ids(session)

    assert _snapshot(session, tournament) == before
    assert fake_registration.calls == []


def test_start_passed_is_not_drawn_and_not_notified(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    tournament = tournament_in(session, S.CLOSED)
    fake_registration.set_team_count(4)
    frozen_clock.set(tournament.start_at)
    before = _snapshot(session, tournament)

    assert tournament.id not in tournaments_service.list_closed_tournament_ids(session)
    assert service.auto_draw(session, tournament_id=tournament.id) == "not_due"

    assert _snapshot(session, tournament) == before


# ---------------------------------------------------------------- worker 入口


def _drain(session: Session) -> int:
    """呼叫 `auto_draw_due` 直到沒有候選（最多 50 次），回傳處理的筆數。"""
    for handled in range(50):
        if not service.auto_draw_due(session):
            return handled
    raise AssertionError("auto_draw_due never returned False")


def test_due_draws_closed_and_then_has_nothing_left(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drawn = tournament_in(session, S.CLOSED)
    short = tournament_in(session, S.CLOSED)
    still_open = tournament_in(session, S.OPEN)
    fake_registration.set_team_count(3)
    # 正取不足的那場：替身依賽事回傳不同隊數
    original = fake_registration.list_accepted_teams

    def _accepted(_session: Session, *, tournament_id: uuid.UUID) -> list[uuid.UUID]:
        teams = original(_session, tournament_id=tournament_id)
        return teams[:1] if tournament_id == short.id else teams

    monkeypatch.setattr(registration_port, "list_accepted_teams", _accepted)

    assert _drain(session) >= 2
    assert _status(session, drawn) == S.PUBLISHED
    assert _status(session, short) == S.CLOSED
    assert _status(session, still_open) == S.OPEN
    assert len(_events(session, short, "AutoDrawSkipped")) == 1

    # 已處理完：再跑不會處理任何一場，也不會再發事件
    assert service.auto_draw_due(session) is False
    assert len(_events(session, short, "AutoDrawSkipped")) == 1


def test_due_skips_a_failing_tournament_and_draws_the_next(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = tournament_in(session, S.CLOSED)
    ok = tournament_in(session, S.CLOSED)
    # 讓 failing 排在前面（報名截止較早）
    row = session.get(Tournament, failing.id)
    assert row is not None
    row.registration_end = row.registration_end - timedelta(hours=1)
    session.add(row)
    session.flush()
    fake_registration.set_team_count(3)
    original = fake_registration.mark_drawn

    def _mark_drawn(_session: Session, **kwargs: Any) -> None:
        if kwargs["tournament_id"] == failing.id:
            raise RuntimeError("boom")
        original(_session, **kwargs)

    monkeypatch.setattr(registration_port, "mark_drawn", _mark_drawn)

    _drain(session)

    # failing 在 savepoint 裡回滾：沒有對戰表、場次、事件，仍為報名截止
    assert _status(session, failing) == S.CLOSED
    assert not _has_bracket(session, failing)
    assert count_matches(session, failing.id) == 0
    assert _events(session, failing, "BracketDrawn") == []
    assert _skips(session, failing) == 0
    # 後面的賽事照常抽籤
    assert _status(session, ok) == S.PUBLISHED
    assert len(_events(session, ok, "BracketDrawn")) == 1
