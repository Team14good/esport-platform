"""Story 4.1 S27：抽籤狀態 API（`get_draw_status`、`GET /organizer/tournaments/{id}/draw-status`）。

用真的 registration 函式（不用 `fake_registration`）：報名直接寫成「已送出・待分配」，
沿用 3.6 `test_draw_functions.py` 與 worker 測試的資料準備。預估在 savepoint 裡呼叫
`finalize_for_draw` 後回滾，所以每個開放報名中的情境都要確認報名狀態、結算紀錄、
操作紀錄、outbox 事件與賽事狀態都沒變，而且預估隊數等於接著真的抽籤的隊數。
"""

import random
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, select

from app.core import audit
from app.core.config import settings
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port
from app.modules.competition import repository as competition_repository
from app.modules.competition import service as competition_service
from app.modules.competition.models import BracketRead, DrawStatus
from app.modules.identity.models import Account
from app.modules.registration import repository as registration_repository
from app.modules.registration import service as registration_service
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.helpers import make_account
from tests.registration.test_teams import _auth, _set_status
from tests.worker.test_priority_window_allocation import (
    _in_window,
    _school,
    _statuses,
    _submitted,
    _tournament,
)

S = TournamentStatus
API = settings.API_V1_STR


# ---------------------------------------------------------------- 共用


def _status(session: Session, tournament: TournamentRead) -> DrawStatus:
    return competition_service.get_draw_status(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )


def _draw(session: Session, tournament: TournamentRead) -> BracketRead:
    return competition_service.draw(
        session,
        tournament_id=tournament.id,
        actor_id=tournament.organizer_id,
        rng=random.Random(7),
    )


def _drawn_team_count(bracket: BracketRead) -> int:
    return len(
        {
            team
            for match in bracket.matches
            for team in (match.team_a_id, match.team_b_id)
            if team is not None
        }
    )


def _outbox_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(OutboxEvent)).one()


def _snapshot(session: Session, tournament: TournamentRead) -> dict[str, Any]:
    """預估不得改變的一切：報名狀態、結算紀錄、操作紀錄數、outbox 事件數、賽事狀態。"""
    statuses = _statuses(session, tournament)  # 會 expire_all，之後的查詢都讀資料庫
    return {
        "statuses": statuses,
        "settlement": registration_repository.get_settlement(session, tournament.id),
        "audit": len(audit.list_for_tournament(session, tournament.id)),
        "outbox": _outbox_count(session),
        "tournament_status": tournaments_service.get_tournament(
            session, tournament_id=tournament.id
        ).status,
    }


def _open_with(
    session: Session,
    frozen_clock: FrozenClock,
    *,
    capacity: int,
    scores: tuple[str, ...],
    same_school: bool = False,
) -> TournamentRead:
    """開放報名中、優先期內，`scores` 各一隊已送出（都還是待分配）。"""
    tournament = _tournament(session, frozen_clock, capacity=capacity)
    school = _school(session)
    for minute, score in enumerate(scores, start=1):
        _submitted(
            session,
            tournament,
            school if same_school else _school(session),
            score=score,
            submitted_at=_in_window(tournament, minute),
        )
    assert frozen_clock.now() < tournament.priority_end
    return tournament


# ---------------------------------------------------------------- 驗收條件一：優先期內提前抽籤


def test_early_draw_preview_twice_leaves_no_trace_then_draw_succeeds(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    before = _snapshot(session, tournament)
    assert set(before["statuses"].values()) == {"pending"}
    assert before["settlement"] is None
    assert before["tournament_status"] == S.OPEN

    first = _status(session, tournament)
    second = _status(session, tournament)

    expected = DrawStatus(can_draw=True, reason=None, expected_teams=2)
    assert first == expected
    assert second == expected
    # 報名仍為待分配、沒有結算紀錄、操作紀錄與 outbox 事件數不變、賽事仍開放報名
    assert _snapshot(session, tournament) == before

    bracket = _draw(session, tournament)

    assert _drawn_team_count(bracket) == first.expected_teams
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == S.PUBLISHED
    )


@pytest.mark.parametrize(
    ("capacity", "scores", "same_school", "expected"),
    [
        # 名額 2、3 校各 1 隊：2 隊正取、1 隊候補
        (2, ("30", "28", "26"), False, 2),
        # 同校 3 隊、名額 4：結算 1 隊正取、截止補位再補 1 隊（同校上限 2 隊）
        (4, ("30", "25", "20"), True, 2),
        # 5 校、名額 8：全部正取
        (8, ("30", "28", "26", "24", "22"), False, 5),
    ],
)
def test_preview_count_equals_real_draw(
    session: Session,
    frozen_clock: FrozenClock,
    capacity: int,
    scores: tuple[str, ...],
    same_school: bool,
    expected: int,
) -> None:
    tournament = _open_with(
        session, frozen_clock, capacity=capacity, scores=scores, same_school=same_school
    )
    before = _snapshot(session, tournament)

    status = _status(session, tournament)

    assert status == DrawStatus(can_draw=True, reason=None, expected_teams=expected)
    assert _snapshot(session, tournament) == before
    assert _drawn_team_count(_draw(session, tournament)) == expected


def test_preview_after_priority_window_counts_first_come_and_fill(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 優先期已過（worker 尚未結算）且有優先期後送出的報名：結算＋先搶期＋補位都在預估裡
    tournament = _tournament(session, frozen_clock, capacity=3)
    for minutes in (30, 31):
        _submitted(
            session,
            tournament,
            _school(session),
            submitted_at=_in_window(tournament, minutes),
        )
    _submitted(
        session,
        tournament,
        _school(session),
        submitted_at=tournament.priority_end + timedelta(minutes=1),
    )
    frozen_clock.set(tournament.priority_end + timedelta(minutes=10))
    before = _snapshot(session, tournament)

    status = _status(session, tournament)

    assert status == DrawStatus(can_draw=True, reason=None, expected_teams=3)
    assert _snapshot(session, tournament) == before
    assert _drawn_team_count(_draw(session, tournament)) == 3


# ---------------------------------------------------------------- I/O 矩陣


def test_only_one_team_is_not_enough_and_leaves_no_trace(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30",))
    before = _snapshot(session, tournament)

    status = _status(session, tournament)

    assert status == DrawStatus(
        can_draw=False, reason="not_enough_teams", expected_teams=1
    )
    assert _snapshot(session, tournament) == before
    # 真的抽籤也一樣被擋
    with pytest.raises(BusinessError) as caught:
        _draw(session, tournament)
    assert caught.value.code == "NOT_ENOUGH_TEAMS"


def test_no_submissions_is_not_enough(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _tournament(session, frozen_clock)

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="not_enough_teams", expected_teams=0
    )


def test_closed_counts_accepted_without_finalizing(
    session: Session, frozen_clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tournament = _open_with(
        session, frozen_clock, capacity=2, scores=("30", "28", "26")
    )
    registration_service.finalize_for_draw(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )
    _set_status(session, tournament.id, S.CLOSED)
    before = _snapshot(session, tournament)
    finalized: list[uuid.UUID] = []
    monkeypatch.setattr(
        registration_port,
        "finalize_for_draw",
        lambda session, *, tournament_id, actor_id: finalized.append(tournament_id),
    )

    status = _status(session, tournament)

    assert status == DrawStatus(can_draw=True, reason=None, expected_teams=2)
    # 報名截止：與 draw 相同，不呼叫 finalize_for_draw
    assert finalized == []
    assert _snapshot(session, tournament) == before


def test_already_drawn(session: Session, frozen_clock: FrozenClock) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    _draw(session, tournament)
    # 已抽籤的檢查在狀態之前：即使把賽事改回報名截止也回 already_drawn
    _set_status(session, tournament.id, S.CLOSED)

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="already_drawn", expected_teams=None
    )


@pytest.mark.parametrize("status", [s for s in S if s not in (S.OPEN, S.CLOSED)])
def test_not_drawable_status(
    session: Session, frozen_clock: FrozenClock, status: TournamentStatus
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    _set_status(session, tournament.id, status)
    before = _snapshot(session, tournament)

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="not_drawable", expected_teams=None
    )
    assert _snapshot(session, tournament) == before


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(minutes=-1)])
def test_start_passed(
    session: Session, frozen_clock: FrozenClock, offset: timedelta
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    frozen_clock.set(tournament.start_at - offset)
    before = _snapshot(session, tournament)

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="start_passed", expected_teams=None
    )
    assert _snapshot(session, tournament) == before


def test_preview_locks_tournament_before_reading_or_finalizing(
    session: Session, frozen_clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    calls: list[str] = []
    original_lock = tournaments_service.lock_tournament
    original_finalize = registration_port.finalize_for_draw
    original_bracket = competition_repository.get_bracket_by_tournament

    def lock(session: Session, *, tournament_id: uuid.UUID) -> TournamentRead:
        calls.append("lock")
        return original_lock(session, tournament_id=tournament_id)

    def finalize(session: Session, **kwargs: Any) -> None:
        calls.append("finalize")
        original_finalize(session, **kwargs)

    def bracket(session: Session, tournament_id: uuid.UUID) -> Any:
        calls.append("bracket")
        return original_bracket(session, tournament_id)

    monkeypatch.setattr(tournaments_service, "lock_tournament", lock)
    monkeypatch.setattr(registration_port, "finalize_for_draw", finalize)
    monkeypatch.setattr(competition_repository, "get_bracket_by_tournament", bracket)

    _status(session, tournament)

    # 先鎖賽事，才查對戰表、才分配（AD-6）
    assert calls[:3] == ["lock", "bracket", "finalize"]


def test_other_organizer_is_rejected(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    other = make_account(session, organizer=True)
    before = _snapshot(session, tournament)

    with pytest.raises(BusinessError) as caught:
        competition_service.get_draw_status(
            session, tournament_id=tournament.id, actor_id=other.id
        )

    assert (caught.value.code, caught.value.status_code) == (
        "TOURNAMENT_OWNER_REQUIRED",
        403,
    )
    assert _snapshot(session, tournament) == before


def test_other_organizer_is_rejected_after_draw_too(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 已抽籤的賽事：其他主辦方仍是 403，不會因為 already_drawn 而洩漏狀態
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    _draw(session, tournament)
    other = make_account(session, organizer=True)

    with pytest.raises(BusinessError) as caught:
        competition_service.get_draw_status(
            session, tournament_id=tournament.id, actor_id=other.id
        )

    assert (caught.value.code, caught.value.status_code) == (
        "TOURNAMENT_OWNER_REQUIRED",
        403,
    )


def test_other_organizer_is_rejected_before_taking_the_lock(
    session: Session, frozen_clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    other = make_account(session, organizer=True)
    locked: list[uuid.UUID] = []
    monkeypatch.setattr(
        tournaments_service,
        "lock_tournament",
        lambda session, *, tournament_id: locked.append(tournament_id),
    )

    with pytest.raises(BusinessError) as caught:
        competition_service.get_draw_status(
            session, tournament_id=tournament.id, actor_id=other.id
        )

    assert caught.value.code == "TOURNAMENT_OWNER_REQUIRED"
    assert locked == []


def test_unknown_tournament_is_404(session: Session) -> None:
    organizer = make_account(session, organizer=True)

    with pytest.raises(BusinessError) as caught:
        competition_service.get_draw_status(
            session, tournament_id=uuid.uuid4(), actor_id=organizer.id
        )

    assert (caught.value.code, caught.value.status_code) == (
        "TOURNAMENT_NOT_FOUND",
        404,
    )


# ---------------------------------------------------------------- 原因順序、不足、錯誤與非校園賽


def test_wrong_status_wins_over_start_passed(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    _set_status(session, tournament.id, S.PUBLISHED)
    frozen_clock.set(tournament.start_at + timedelta(minutes=1))

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="not_drawable", expected_teams=None
    )


def test_already_drawn_wins_over_start_passed(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    _draw(session, tournament)
    frozen_clock.set(tournament.start_at + timedelta(minutes=1))

    assert _status(session, tournament) == DrawStatus(
        can_draw=False, reason="already_drawn", expected_teams=None
    )


def test_start_passed_wins_over_not_enough_teams(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30",))
    frozen_clock.set(tournament.start_at + timedelta(minutes=1))

    status = _status(session, tournament)

    assert status == DrawStatus(
        can_draw=False, reason="start_passed", expected_teams=None
    )
    assert status.expected_teams is None


def test_closed_with_one_accepted_team_is_not_enough(
    session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30",))
    registration_service.finalize_for_draw(
        session, tournament_id=tournament.id, actor_id=tournament.organizer_id
    )
    _set_status(session, tournament.id, S.CLOSED)

    status = _status(session, tournament)

    assert status == DrawStatus(
        can_draw=False, reason="not_enough_teams", expected_teams=1
    )
    assert status.expected_teams == 1


def test_business_error_inside_preview_propagates_and_rolls_back(
    session: Session, frozen_clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    before = _snapshot(session, tournament)
    original_finalize = registration_port.finalize_for_draw

    def write_then_fail(session: Session, **kwargs: Any) -> None:
        original_finalize(session, **kwargs)  # 在 savepoint 內真的寫入
        raise BusinessError("PREVIEW_BOOM", "預估失敗", status_code=409)

    monkeypatch.setattr(registration_port, "finalize_for_draw", write_then_fail)

    with pytest.raises(BusinessError) as caught:
        _status(session, tournament)

    # 錯誤原樣傳出（不被當成預估結果吞掉），savepoint 內的寫入全部回滾
    assert (caught.value.code, caught.value.status_code) == ("PREVIEW_BOOM", 409)
    assert _snapshot(session, tournament) == before


def test_non_campus_open_preview_equals_real_draw(
    session: Session, frozen_clock: FrozenClock
) -> None:
    # 非校園賽：finalize_for_draw 什麼都不做，正取是已經是 accepted 的報名
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.mode = TournamentMode.CUSTOM
    session.add(row)
    for registration in registration_repository.list_registrations(
        session, tournament.id
    ):
        registration.status = RegistrationStatus.ACCEPTED
        session.add(registration)
    session.flush()
    before = _snapshot(session, tournament)

    status = _status(session, tournament)

    assert status == DrawStatus(can_draw=True, reason=None, expected_teams=2)
    assert _snapshot(session, tournament) == before
    assert _drawn_team_count(_draw(session, tournament)) == status.expected_teams


# ---------------------------------------------------------------- HTTP


def _url(tournament_id: uuid.UUID) -> str:
    return f"{API}/organizer/tournaments/{tournament_id}/draw-status"


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


@pytest.fixture
def commits(monkeypatch: pytest.MonkeyPatch) -> list[Session]:
    """記錄所有 `session.commit()`（狀態 API 是 GET，不得 commit）。"""
    calls: list[Session] = []
    original: Callable[[Session], None] = Session.commit

    def spy(self: Session) -> None:
        calls.append(self)
        original(self)

    monkeypatch.setattr(Session, "commit", spy)
    return calls


def test_api_returns_status_without_commit(
    client: TestClient,
    session: Session,
    frozen_clock: FrozenClock,
    commits: list[Session],
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    session.commit()
    before = _snapshot(session, tournament)
    commits.clear()

    response = client.get(_url(tournament.id), headers=_auth(organizer))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "can_draw": True,
        "reason": None,
        "expected_teams": 2,
    }
    assert commits == []
    assert _snapshot(session, tournament) == before

    # 接著真的抽籤：隊數與預估相同
    drawn = client.post(
        f"{API}/tournaments/{tournament.id}/draw", headers=_auth(organizer)
    )
    assert drawn.status_code == 201, drawn.text
    assert _drawn_team_count(BracketRead.model_validate(drawn.json())) == 2
    after = client.get(_url(tournament.id), headers=_auth(organizer))
    assert after.json() == {
        "can_draw": False,
        "reason": "already_drawn",
        "expected_teams": None,
    }


def test_api_permissions(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    tournament = _open_with(session, frozen_clock, capacity=4, scores=("30", "28"))
    other = make_account(session, organizer=True)
    plain = make_account(session)
    organizer = session.get(Account, tournament.organizer_id)
    assert organizer is not None
    session.commit()

    assert client.get(_url(tournament.id)).status_code == 401
    response = client.get(_url(tournament.id), headers=_auth(plain))
    assert (response.status_code, _code(response)) == (403, "ORGANIZER_REQUIRED")
    response = client.get(_url(tournament.id), headers=_auth(other))
    assert (response.status_code, _code(response)) == (
        403,
        "TOURNAMENT_OWNER_REQUIRED",
    )
    response = client.get(_url(uuid.uuid4()), headers=_auth(organizer))
    assert (response.status_code, _code(response)) == (404, "TOURNAMENT_NOT_FOUND")
