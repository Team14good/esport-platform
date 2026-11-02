"""Story 4.1 第二階段：抽籤 service（I/O 矩陣與驗收條件）。"""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core import audit
from app.core.errors import BusinessError
from app.modules.competition import bracket as bracket_rules
from app.modules.competition import service
from app.modules.competition.models import BracketRead, Match, MatchRead, MatchStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    count_matches,
    count_outbox,
    draw_with,
    tournament_in,
)
from tests.helpers import make_account

S = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

# frozen_clock 下 tournament_in 的預設開賽時間與各輪時間（間隔 180 分鐘、未順延）
ROUND_1 = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)
ROUND_2 = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)
ROUND_3 = datetime(2026, 10, 26, 17, 0, tzinfo=UTC)


def _by_code(bracket: BracketRead) -> dict[str, MatchRead]:
    return {m.code: m for m in bracket.matches}


def _placed_teams(bracket: BracketRead) -> list[uuid.UUID]:
    return [
        team
        for m in bracket.matches
        for team in (m.team_a_id, m.team_b_id)
        if team is not None
    ]


# ---------------------------------------------------------------- 成功


@pytest.mark.parametrize(
    ("team_count", "match_count", "rounds", "size", "has_third"),
    [
        (2, 1, 1, 2, False),
        (3, 2, 2, 4, False),
        (8, 8, 3, 8, True),
        (10, 10, 4, 16, True),
        (13, 13, 4, 16, True),
        (32, 32, 5, 32, True),
    ],
)
def test_draw_matches_plan_and_publishes(
    session: Session,
    fake_registration: FakeRegistration,
    team_count: int,
    match_count: int,
    rounds: int,
    size: int,
    has_third: bool,
) -> None:
    tournament, bracket = draw_with(session, fake_registration, team_count)

    assert (bracket.size, bracket.rounds) == (size, rounds)
    assert len(bracket.matches) == match_count
    assert count_matches(session, tournament.id) == match_count
    assert any(m.is_third_place for m in bracket.matches) is has_third
    # 每支隊伍恰好出現一次
    placed = _placed_teams(bracket)
    assert sorted(placed) == sorted(fake_registration.teams)
    # 結構與 bracket.plan 一致：編號、輪次、位置、輪空、勝隊與敗隊去向
    plan = bracket_rules.plan(team_count)
    by_id = {m.id: m.code for m in bracket.matches}
    by_code = _by_code(bracket)
    assert set(by_code) == {p.code for p in plan.matches}
    for planned in plan.matches:
        stored = by_code[planned.code]
        assert (stored.round_no, stored.slot_no, stored.is_third_place) == (
            planned.round_no,
            planned.slot_no,
            planned.is_third_place,
        )
        assert by_id.get(stored.next_match_id) == planned.next_code  # type: ignore[arg-type]
        assert by_id.get(stored.loser_next_match_id) == planned.loser_next_code  # type: ignore[arg-type]
        assert stored.status == MatchStatus.SCHEDULED
    # 賽事已公布、mark_drawn 收到全部隊伍、操作紀錄與 outbox 各一筆
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == S.PUBLISHED
    )
    assert len(fake_registration.drawn) == 1
    assert sorted(fake_registration.drawn[0][1]) == sorted(fake_registration.teams)
    drawn_logs = [
        row
        for row in audit.list_for_tournament(session, tournament.id)
        if row.action == "bracket.drawn"
    ]
    assert len(drawn_logs) == 1
    assert drawn_logs[0].entity_id == bracket.id
    assert drawn_logs[0].after == {
        "size": size,
        "rounds": rounds,
        "team_count": team_count,
        "delayed_rounds": [],
    }
    assert count_outbox(session, "BracketDrawn") == 1


def test_draw_eight_teams_after_close(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 8)
    by_code = _by_code(bracket)
    by_id = {m.id: m.code for m in bracket.matches}

    assert fake_registration.finalized == []
    assert fake_registration.calls == ["list_accepted_teams", "mark_drawn"]
    assert {code: by_id.get(m.next_match_id) for code, m in by_code.items()} == {  # type: ignore[arg-type]
        "M1": "M5",
        "M2": "M5",
        "M3": "M6",
        "M4": "M6",
        "M5": "M7",
        "M6": "M7",
        "M7": None,
        "M8": None,
    }
    assert {
        code: by_id[m.loser_next_match_id]
        for code, m in by_code.items()
        if m.loser_next_match_id
    } == {"M5": "M8", "M6": "M8"}
    # 同一輪（含季軍賽與決賽）時間相同
    assert {code: m.scheduled_at for code, m in by_code.items()} == {
        "M1": ROUND_1,
        "M2": ROUND_1,
        "M3": ROUND_1,
        "M4": ROUND_1,
        "M5": ROUND_2,
        "M6": ROUND_2,
        "M7": ROUND_3,
        "M8": ROUND_3,
    }
    # 第一輪 4 場有棄權期限（開賽＋15 分鐘），其他場次為空
    assert {code: m.forfeit_deadline for code, m in by_code.items()} == {
        "M1": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M2": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M3": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M4": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M5": None,
        "M6": None,
        "M7": None,
        "M8": None,
    }
    assert bracket.delayed_rounds == []
    assert bracket.drawn_at == datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
    assert all(not m.bye_a and not m.bye_b for m in bracket.matches)
    assert service.get_bracket(session, tournament_id=tournament.id) == bracket


def test_draw_while_open_finalizes_first_and_places_byes_in_round_two(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament, bracket = draw_with(session, fake_registration, 13, status=S.OPEN)
    by_code = _by_code(bracket)

    assert fake_registration.calls == [
        "finalize_for_draw",
        "list_accepted_teams",
        "mark_drawn",
    ]
    assert fake_registration.finalized == [(tournament.id, tournament.organizer_id)]
    assert len(bracket.matches) == 13
    # 第一輪 5 場（位置 2、4、6、7、8）；第二輪 1～3 場的 a 方是輪空隊伍
    assert {
        code: (m.round_no, m.slot_no) for code, m in by_code.items() if m.round_no <= 2
    } == {
        "M1": (1, 2),
        "M2": (1, 4),
        "M3": (1, 6),
        "M4": (1, 7),
        "M5": (1, 8),
        "M6": (2, 1),
        "M7": (2, 2),
        "M8": (2, 3),
        "M9": (2, 4),
    }
    assert {
        code: (by_code[code].bye_a, by_code[code].bye_b)
        for code in ("M6", "M7", "M8", "M9")
    } == {
        "M6": (True, False),
        "M7": (True, False),
        "M8": (True, False),
        "M9": (False, False),
    }
    bye_teams = [by_code[code].team_a_id for code in ("M6", "M7", "M8")]
    assert all(team is not None for team in bye_teams)
    assert all(by_code[code].team_b_id is None for code in ("M6", "M7", "M8"))
    assert all(by_code[code].forfeit_deadline is None for code in ("M6", "M7", "M8"))
    assert (
        tournaments_service.get_tournament(session, tournament_id=tournament.id).status
        == S.PUBLISHED
    )
    status_logs = [
        row.after
        for row in audit.list_for_tournament(session, tournament.id)
        if row.action == "tournament.status_changed"
    ]
    assert status_logs == [{"status": "published"}]


def test_two_bye_teams_meeting_in_round_two_get_forfeit_deadline(
    session: Session, fake_registration: FakeRegistration
) -> None:
    _tournament, bracket = draw_with(session, fake_registration, 10)
    by_code = _by_code(bracket)

    assert {
        code: (by_code[code].bye_a, by_code[code].bye_b)
        for code in ("M3", "M4", "M5", "M6")
    } == {
        "M3": (True, True),
        "M4": (True, False),
        "M5": (True, True),
        "M6": (True, False),
    }
    assert {code: by_code[code].forfeit_deadline for code in by_code} == {
        "M1": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M2": datetime(2026, 10, 26, 11, 15, tzinfo=UTC),
        "M3": datetime(2026, 10, 26, 14, 15, tzinfo=UTC),
        "M4": None,
        "M5": datetime(2026, 10, 26, 14, 15, tzinfo=UTC),
        "M6": None,
        "M7": None,
        "M8": None,
        "M9": None,
        "M10": None,
    }


def test_rounds_are_delayed_when_min_gap_exceeds_interval(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 最小間隔＝15＋3×40＋30＝165 分鐘 > 每輪間隔 60 分鐘
    tournament, bracket = draw_with(
        session, fake_registration, 8, round_interval_minutes=60
    )

    assert bracket.delayed_rounds == [2, 3]
    assert sorted({(m.round_no, m.scheduled_at) for m in bracket.matches}) == [
        (1, datetime(2026, 10, 26, 11, 0, tzinfo=UTC)),
        (2, datetime(2026, 10, 26, 13, 45, tzinfo=UTC)),
        (3, datetime(2026, 10, 26, 16, 30, tzinfo=UTC)),
    ]
    fetched = service.get_bracket(session, tournament_id=tournament.id)
    assert fetched is not None
    assert fetched.delayed_rounds == [2, 3]


def test_get_bracket_before_draw_is_none(session: Session) -> None:
    tournament = tournament_in(session, S.CLOSED)

    assert service.get_bracket(session, tournament_id=tournament.id) is None
    assert service.get_public_bracket(session, tournament_id=tournament.id) is None


# ---------------------------------------------------------------- 拒絕


def _snapshot(session: Session, tournament_id: uuid.UUID) -> tuple[object, ...]:
    return (
        tournaments_service.get_tournament(session, tournament_id=tournament_id).status,
        service.get_bracket(session, tournament_id=tournament_id),
        count_matches(session, tournament_id),
        len(audit.list_for_tournament(session, tournament_id)),
        count_outbox(session, "BracketDrawn"),
    )


def _draw_error(
    session: Session, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> BusinessError:
    before = _snapshot(session, tournament_id)
    with pytest.raises(BusinessError) as excinfo:
        service.draw(
            session,
            tournament_id=tournament_id,
            actor_id=actor_id,
            rng=random.Random(1),
        )
    assert _snapshot(session, tournament_id) == before
    return excinfo.value


@pytest.mark.parametrize("status", [S.OPEN, S.CLOSED])
@pytest.mark.parametrize("minutes_after_start", [0, 1])
def test_start_passed_is_409(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    status: TournamentStatus,
    minutes_after_start: int,
) -> None:
    # 開賽 2026-10-26 11:00；現在等於或晚於開賽時間都拒絕
    tournament = tournament_in(session, status)
    fake_registration.set_team_count(8)
    frozen_clock.set(ROUND_1 + timedelta(minutes=minutes_after_start))

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert (error.code, error.status_code) == ("TOURNAMENT_START_PASSED", 409)
    assert error.message == "開賽時間已過，無法抽籤"
    assert fake_registration.calls == []


@pytest.mark.parametrize("team_count", [0, 1])
@pytest.mark.parametrize("status", [S.OPEN, S.CLOSED])
def test_not_enough_teams_is_409(
    session: Session,
    fake_registration: FakeRegistration,
    team_count: int,
    status: TournamentStatus,
) -> None:
    tournament = tournament_in(session, status)
    fake_registration.set_team_count(team_count)

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert (error.code, error.status_code) == ("NOT_ENOUGH_TEAMS", 409)
    assert error.message == "正取不足 2 隊，無法抽籤"
    assert "mark_drawn" not in fake_registration.calls


def test_second_draw_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament, _bracket = draw_with(session, fake_registration, 4)

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert (error.code, error.status_code) == ("BRACKET_ALREADY_DRAWN", 409)


def test_existing_bracket_wins_over_drawable_status(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 已有 Bracket 時，即使狀態被改回可抽籤的 closed，也回 BRACKET_ALREADY_DRAWN
    tournament, _bracket = draw_with(session, fake_registration, 4)
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.status = S.CLOSED
    session.add(row)
    session.flush()

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert error.code == "BRACKET_ALREADY_DRAWN"


@pytest.mark.parametrize(
    "status", [S.UPCOMING, S.PUBLISHED, S.ONGOING, S.FINISHED, S.CANCELLED]
)
def test_wrong_status_is_409(
    session: Session, fake_registration: FakeRegistration, status: TournamentStatus
) -> None:
    tournament = tournament_in(session, status)
    fake_registration.set_team_count(8)

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert (error.code, error.status_code) == ("TOURNAMENT_NOT_DRAWABLE", 409)
    assert fake_registration.calls == []


def test_other_organizer_is_403(
    session: Session, fake_registration: FakeRegistration
) -> None:
    tournament = tournament_in(session, S.CLOSED)
    fake_registration.set_team_count(8)
    other = make_account(session, organizer=True)

    error = _draw_error(session, tournament.id, other.id)

    assert (error.code, error.status_code) == ("TOURNAMENT_OWNER_REQUIRED", 403)
    assert fake_registration.calls == []


def test_missing_tournament_is_404(session: Session) -> None:
    with pytest.raises(BusinessError) as excinfo:
        service.draw(session, tournament_id=uuid.uuid4(), actor_id=uuid.uuid4())

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "TOURNAMENT_NOT_FOUND",
        404,
    )


@pytest.mark.parametrize("status", [S.OPEN, S.CLOSED])
@pytest.mark.usefixtures("registration_without_draw_functions")
def test_registration_unavailable_is_503(
    session: Session, status: TournamentStatus
) -> None:
    # 不換替身，並移除 registration 的抽籤函式
    tournament = tournament_in(session, status)

    error = _draw_error(session, tournament.id, tournament.organizer_id)

    assert (error.code, error.status_code) == ("REGISTRATION_UNAVAILABLE", 503)
    rows = session.exec(select(Match).where(Match.tournament_id == tournament.id))
    assert list(rows) == []
