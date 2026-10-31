"""Story 5.5、5.6 第二階段：確認結果、晉級推進、申訴期滿自動確認與賽事結束。

隊伍以「隊伍 k」稱呼（k 為 `FakeRegistration.teams` 的順序，1 起算）。抽籤固定
`random.Random(7)`，各隊數的第 1 輪對位（由 4.1 的 `bracket.assign` 決定）：

- 2 隊：M1 隊伍1–隊伍2
- 3 隊：M1 隊伍3–隊伍1；M2 隊伍2（輪空）– M1 勝者
- 8 隊：M1 7–8、M2 3–5、M3 1–4、M4 2–6；M5＝M1、M2 勝者；M6＝M3、M4 勝者；
  M7 決賽、M8 季軍賽
- 13 隊：M1 4–11、M2 13–8、M3 10–5、M4 12–9、M5 2–1；M6 7（輪空）–M1 勝者、
  M7 3（輪空）–M2 勝者、M8 6（輪空）–M3 勝者、M9＝M4、M5 勝者；M10＝M6、M7 勝者；
  M11＝M8、M9 勝者；M12 決賽、M13 季軍賽

整合測試一律讓編號小的隊伍贏，名次依上面的對位手算。
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, col, select

from app.core import audit
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import repository, service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from app.worker import run_once
from app.worker.jobs import confirm_expired_appeals
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    count_outbox,
    draw_with,
)

O = MatchOutcome  # noqa: E741
S = MatchStatus
T = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

# frozen_clock 的起點與 tournament_in 預設的第 2 輪時間
START = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
ROUND_2 = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)
APPEAL = timedelta(minutes=30)


# ---------------------------------------------------------------- 輔助


def _rows(session: Session, tournament_id: uuid.UUID) -> dict[str, Match]:
    session.expire_all()
    statement = select(Match).where(Match.tournament_id == tournament_id)
    return {match.code: match for match in session.exec(statement)}


def _team(fake: FakeRegistration, k: int) -> uuid.UUID:
    return fake.teams[k - 1]


def _k(fake: FakeRegistration, team_id: uuid.UUID | None) -> int | None:
    return None if team_id is None else fake.teams.index(team_id) + 1


def _slots(fake: FakeRegistration, match: Match) -> tuple[int | None, int | None]:
    return _k(fake, match.team_a_id), _k(fake, match.team_b_id)


def _enter_appeal(
    session: Session,
    match: Match,
    *,
    outcome: MatchOutcome,
    winner_id: uuid.UUID | None,
    deadline: datetime,
) -> None:
    """模擬 5.4 送出結果：申訴期、已寫 outcome 與勝隊、申訴期限。"""
    match.status = S.APPEAL_WINDOW
    match.outcome = outcome
    match.winner_id = winner_id
    match.appeal_deadline = deadline
    session.add(match)
    session.flush()


def _drain(session: Session, session_factory: Callable[[], Session]) -> int:
    """像 worker 一樣每筆一個交易執行工作，直到回傳 False；回傳回傳 True 的次數。"""
    session.flush()
    handled = 0
    for _ in range(100):
        with session_factory() as job_session:
            more = confirm_expired_appeals(job_session)
            job_session.commit()
        if not more:
            session.expire_all()
            return handled
        handled += 1
    pytest.fail("工作一直回傳 True")


def _confirm(
    session: Session,
    match: Match,
    outcome: MatchOutcome,
    winner_id: uuid.UUID | None,
) -> None:
    """模擬裁判送出後立即確認：先轉為申訴期，再 `confirm_match`（照 AD-6 先鎖賽事）。"""
    tournaments_service.lock_tournament(session, tournament_id=match.tournament_id)
    locked = service.lock_match(session, match_id=match.id)
    if locked.status == S.SCHEDULED:
        service.transition_match(session, match=locked, to=S.APPEAL_WINDOW)
    service.confirm_match(
        session, match=locked, outcome=outcome, winner_id=winner_id, actor_id=None
    )


def _set_tournament_status(
    session: Session, tournament_id: uuid.UUID, status: TournamentStatus
) -> None:
    row = session.get(Tournament, tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.flush()


def _status(session: Session, tournament_id: uuid.UUID) -> TournamentStatus:
    return tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    ).status


def _actions(session: Session, tournament_id: uuid.UUID) -> list[str]:
    return [log.action for log in audit.list_for_tournament(session, tournament_id)]


def _outbox(session: Session, event_type: str) -> list[dict[str, object]]:
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.type == event_type)
        .order_by(col(OutboxEvent.created_at), col(OutboxEvent.id))
    )
    return [event.payload for event in session.exec(statement)]


def _podium_k(
    fake: FakeRegistration, session: Session, tournament_id: uuid.UUID
) -> tuple[int | None, int | None, int | None] | None:
    podium = service.get_podium(session, tournament_id=tournament_id)
    if podium is None:
        return None
    return (
        _k(fake, podium.champion.id if podium.champion else None),
        _k(fake, podium.runner_up.id if podium.runner_up else None),
        _k(fake, podium.third_place.id if podium.third_place else None),
    )


def _eight_to_semis(
    session: Session, fake: FakeRegistration
) -> tuple[uuid.UUID, dict[str, Match]]:
    """8 隊、第 1 輪全部確認（編號小的贏）：M5 為 7–3、M6 為 1–2。"""
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    for code, winner in (("M1", 7), ("M2", 3), ("M3", 1), ("M4", 2)):
        _confirm(session, rows[code], O.PLAYED, _team(fake, winner))
    return tournament.id, _rows(session, tournament.id)


# ---------------------------------------------------------------- 整合：抽籤到結束


@pytest.mark.parametrize(
    ("team_count", "podium", "opponents_decided", "waves"),
    [
        (2, (1, 2, None), 0, 1),
        (3, (1, 2, None), 1, 2),
        (8, (1, 3, 2), 4, 3),
        (13, (1, 3, 4), 8, 4),
    ],
)
def test_full_tournament_from_draw_to_finished(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    team_count: int,
    podium: tuple[int, int, int | None],
    opponents_decided: int,
    waves: int,
) -> None:
    fake = fake_registration
    tournament, bracket = draw_with(session, fake, team_count)
    match_count = len(bracket.matches)
    wave = 0
    while True:
        rows = _rows(session, tournament.id)
        playable = [
            m
            for m in rows.values()
            if m.status == S.SCHEDULED
            and m.team_a_id is not None
            and m.team_b_id is not None
        ]
        if not playable:
            break
        wave += 1
        deadline = START + APPEAL * wave
        winners: dict[str, uuid.UUID] = {}
        for match in playable:
            assert match.team_a_id is not None and match.team_b_id is not None
            winner = min(
                (match.team_a_id, match.team_b_id), key=fake.teams.index
            )
            winners[match.code] = winner
            _enter_appeal(
                session, match, outcome=O.PLAYED, winner_id=winner, deadline=deadline
            )

        # 申訴期未滿：不確認，勝隊不出現在下一場
        frozen_clock.set(deadline - timedelta(seconds=1))
        assert _drain(session, session_factory) == 0
        rows = _rows(session, tournament.id)
        for code, winner in winners.items():
            assert rows[code].status == S.APPEAL_WINDOW
            later = [
                m
                for m in rows.values()
                if m.round_no > rows[code].round_no
                and winner in (m.team_a_id, m.team_b_id)
            ]
            assert later == []

        frozen_clock.set(deadline)
        assert _drain(session, session_factory) == len(playable)
        rows = _rows(session, tournament.id)
        for code, winner in winners.items():
            assert rows[code].status == S.CONFIRMED
            assert rows[code].winner_id == winner
            assert rows[code].confirmed_at == deadline

    assert wave == waves
    rows = _rows(session, tournament.id)
    assert {m.status for m in rows.values()} == {S.CONFIRMED}
    assert _status(session, tournament.id) == T.FINISHED
    assert _podium_k(fake, session, tournament.id) == podium

    public = service.get_public_bracket(session, tournament_id=tournament.id)
    assert public is not None and public.podium is not None
    assert public.podium.champion is not None
    assert public.podium.champion.name == f"隊伍{podium[0]}"
    assert public.podium.runner_up is not None
    assert public.podium.runner_up.name == f"隊伍{podium[1]}"
    if podium[2] is None:
        assert public.podium.third_place is None
    else:
        assert public.podium.third_place is not None
        assert public.podium.third_place.name == f"隊伍{podium[2]}"

    actions = _actions(session, tournament.id)
    assert actions.count("match.confirmed") == match_count
    assert actions.count("tournament.podium") == 1
    assert count_outbox(session, "MatchResultConfirmed") == match_count
    assert count_outbox(session, "MatchOpponentsDecided") == opponents_decided

    # 再跑一次 worker：沒有可處理的場次
    assert _drain(session, session_factory) == 0
    assert len(_actions(session, tournament.id)) == len(actions)


# ---------------------------------------------------------------- I/O 矩陣


def test_general_advance_fills_next_match_without_forfeit_clock(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + timedelta(minutes=45))

    assert _drain(session, session_factory) == 1

    rows = _rows(session, tournament.id)
    m1 = rows["M1"]
    assert (m1.status, m1.outcome, _k(fake, m1.winner_id)) == (S.CONFIRMED, O.PLAYED, 7)
    assert m1.confirmed_at == datetime(2026, 10, 18, 11, 45, tzinfo=UTC)
    assert _slots(fake, rows["M5"]) == (7, None)
    assert rows["M5"].forfeit_deadline is None
    assert rows["M5"].status == S.SCHEDULED
    assert count_outbox(session, "MatchOpponentsDecided") == 0
    assert _outbox(session, "MatchResultConfirmed") == [
        {"match_id": str(m1.id), "winner_id": str(_team(fake, 7))}
    ]
    logs = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "match.confirmed"
    ]
    assert len(logs) == 1
    assert (logs[0].actor_id, logs[0].entity_type, logs[0].entity_id) == (
        None,
        "match",
        m1.id,
    )
    assert logs[0].before == {"status": "appeal_window"}
    assert logs[0].after == {
        "status": "confirmed",
        "outcome": "played",
        "winner_id": str(_team(fake, 7)),
    }
    assert _status(session, tournament.id) == T.PUBLISHED


@pytest.mark.parametrize(
    ("both_known_at", "expected_deadline"),
    [
        # 預定 10-26 14:00 之前湊齊：期限＝預定時間＋15 分鐘
        (START + APPEAL, datetime(2026, 10, 26, 14, 15, tzinfo=UTC)),
        # 預定時間之後才湊齊：期限＝現在＋15 分鐘
        (
            datetime(2026, 10, 26, 14, 20, tzinfo=UTC),
            datetime(2026, 10, 26, 14, 35, tzinfo=UTC),
        ),
    ],
)
def test_next_match_complete_starts_forfeit_clock_and_publishes_event(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    both_known_at: datetime,
    expected_deadline: datetime,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    assert rows["M5"].scheduled_at == ROUND_2
    for code, winner in (("M1", 7), ("M2", 3)):
        _enter_appeal(
            session,
            rows[code],
            outcome=O.PLAYED,
            winner_id=_team(fake, winner),
            deadline=START + APPEAL,
        )
    frozen_clock.set(both_known_at)

    assert _drain(session, session_factory) == 2

    rows = _rows(session, tournament.id)
    assert _slots(fake, rows["M5"]) == (7, 3)
    assert rows["M5"].forfeit_deadline == expected_deadline
    assert _outbox(session, "MatchOpponentsDecided") == [
        {"match_id": str(rows["M5"].id)}
    ]


def test_appeal_window_not_expired_is_left_alone(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL - timedelta(microseconds=1))

    assert _drain(session, session_factory) == 0

    rows = _rows(session, tournament.id)
    assert rows["M1"].status == S.APPEAL_WINDOW
    assert rows["M1"].confirmed_at is None
    assert _slots(fake, rows["M5"]) == (None, None)
    assert "match.confirmed" not in _actions(session, tournament.id)


def test_appeal_window_without_deadline_is_never_confirmed(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    rows = _rows(session, tournament.id)
    rows["M1"].status = S.APPEAL_WINDOW
    rows["M1"].outcome = O.PLAYED
    rows["M1"].winner_id = _team(fake, 1)
    session.add(rows["M1"])

    assert _drain(session, session_factory) == 0
    assert _rows(session, tournament.id)["M1"].status == S.APPEAL_WINDOW


def test_semifinal_sends_winner_to_final_and_loser_to_third_place(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)

    _confirm(session, rows["M5"], O.PLAYED, _team(fake, 3))

    rows = _rows(session, tournament_id)
    assert _slots(fake, rows["M7"]) == (3, None)
    assert _slots(fake, rows["M8"]) == (7, None)
    assert rows["M7"].forfeit_deadline is None
    assert rows["M8"].forfeit_deadline is None


def test_double_forfeit_gives_opponent_walkover_and_keeps_advancing(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M2"], O.PLAYED, _team(fake, 3))
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.DOUBLE_FORFEIT,
        winner_id=None,
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL)

    assert _drain(session, session_factory) == 1

    rows = _rows(session, tournament.id)
    m1, m5 = rows["M1"], rows["M5"]
    assert (m1.status, m1.outcome, m1.winner_id) == (S.CONFIRMED, O.DOUBLE_FORFEIT, None)
    assert _slots(fake, m5) == (None, 3)
    assert (m5.status, m5.outcome, _k(fake, m5.winner_id)) == (
        S.CONFIRMED,
        O.WALKOVER,
        3,
    )
    assert m5.confirmed_at == START + APPEAL
    assert m5.forfeit_deadline is None
    # 輪空勝隊繼續晉級到決賽；輪空沒有敗隊，季軍賽 a 方確定從缺但仍等 M6
    assert _slots(fake, rows["M7"]) == (3, None)
    assert _slots(fake, rows["M8"]) == (None, None)
    assert rows["M8"].status == S.SCHEDULED
    # 凍結時鐘下 created_at 相同，outbox 的順序不固定，以內容比對
    confirmed_events = _outbox(session, "MatchResultConfirmed")
    assert len(confirmed_events) == 3
    assert {"match_id": str(m1.id), "winner_id": None} in confirmed_events
    assert {
        "match_id": str(m5.id),
        "winner_id": str(_team(fake, 3)),
    } in confirmed_events
    walkover_log = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "match.confirmed" and log.entity_id == m5.id
    ]
    assert walkover_log[0].actor_id is None
    assert walkover_log[0].before == {"status": "scheduled"}
    assert walkover_log[0].after == {
        "status": "confirmed",
        "outcome": "walkover",
        "winner_id": str(_team(fake, 3)),
    }


def test_double_forfeit_before_opponent_waits_then_walkover(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)

    _confirm(session, rows["M1"], O.DOUBLE_FORFEIT, None)
    assert _rows(session, tournament.id)["M5"].status == S.SCHEDULED

    _confirm(session, rows["M2"], O.PLAYED, _team(fake, 5))
    m5 = _rows(session, tournament.id)["M5"]
    assert (m5.status, m5.outcome, _k(fake, m5.winner_id)) == (
        S.CONFIRMED,
        O.WALKOVER,
        5,
    )


@pytest.mark.parametrize("semi_order", ["M6 first", "M5 first"])
def test_semifinal_double_forfeit_finishes_tournament(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    semi_order: str,
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)
    if semi_order == "M6 first":
        _confirm(session, rows["M6"], O.PLAYED, _team(fake, 1))
        rows = _rows(session, tournament_id)
        # 季軍賽帶著棄權期限被取消：取消時要一併清除
        rows["M8"].forfeit_deadline = START + APPEAL
        session.add(rows["M8"])
        _enter_appeal(
            session,
            rows["M5"],
            outcome=O.DOUBLE_FORFEIT,
            winner_id=None,
            deadline=START + APPEAL,
        )
    else:
        _confirm(session, rows["M5"], O.DOUBLE_FORFEIT, None)
        rows = _rows(session, tournament_id)
        assert rows["M8"].status == S.VOIDED
        _enter_appeal(
            session,
            rows["M6"],
            outcome=O.PLAYED,
            winner_id=_team(fake, 1),
            deadline=START + APPEAL,
        )
    frozen_clock.set(START + APPEAL)

    assert _drain(session, session_factory) == 1

    rows = _rows(session, tournament_id)
    final, third = rows["M7"], rows["M8"]
    assert (final.status, final.outcome, _k(fake, final.winner_id)) == (
        S.CONFIRMED,
        O.WALKOVER,
        1,
    )
    assert _slots(fake, final) == (None, 1)
    assert (third.status, third.outcome, third.winner_id) == (S.VOIDED, None, None)
    assert third.forfeit_deadline is None
    # M6 先確認時敗隊 2 已排入季軍賽且留在原位；M5 先確認時季軍賽已取消，不再填位
    assert _slots(fake, third) == ((None, 2) if semi_order == "M6 first" else (None, None))
    assert _status(session, tournament_id) == T.FINISHED
    assert _podium_k(fake, session, tournament_id) == (1, 2, None)
    voided = [
        log
        for log in audit.list_for_tournament(session, tournament_id)
        if log.action == "match.voided"
    ]
    assert len(voided) == 1
    assert (voided[0].entity_id, voided[0].actor_id) == (third.id, None)
    assert voided[0].before == {"status": "scheduled"}
    assert voided[0].after == {"status": "voided"}


def _to_finals(
    session: Session, fake: FakeRegistration
) -> tuple[uuid.UUID, dict[str, Match]]:
    """8 隊推進到決賽 3–1、季軍賽 7–2。"""
    tournament_id, rows = _eight_to_semis(session, fake)
    _confirm(session, rows["M5"], O.PLAYED, _team(fake, 3))
    _confirm(session, rows["M6"], O.PLAYED, _team(fake, 1))
    rows = _rows(session, tournament_id)
    assert _slots(fake, rows["M7"]) == (3, 1)
    assert _slots(fake, rows["M8"]) == (7, 2)
    return tournament_id, rows


@pytest.mark.parametrize(
    ("initial", "transitions"),
    [
        (T.ONGOING, [("ongoing", "finished")]),
        (T.PUBLISHED, [("published", "ongoing"), ("ongoing", "finished")]),
    ],
)
def test_final_and_third_confirmed_finishes_tournament(
    session: Session,
    fake_registration: FakeRegistration,
    initial: TournamentStatus,
    transitions: list[tuple[str, str]],
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    _set_tournament_status(session, tournament_id, initial)

    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 1))
    # 季軍賽還沒確認：還沒結束
    assert _status(session, tournament_id) == initial
    assert service.get_podium(session, tournament_id=tournament_id) is None
    public = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public is not None and public.podium is None

    _confirm(session, rows["M8"], O.PLAYED, _team(fake, 2))

    assert _status(session, tournament_id) == T.FINISHED
    logs = audit.list_for_tournament(session, tournament_id)
    status_changes = [
        (log.before, log.after, log.actor_id)
        for log in logs
        if log.action == "tournament.status_changed"
    ]
    # 第一筆是抽籤時的 closed → published
    assert status_changes[1:] == [
        ({"status": before}, {"status": after}, None) for before, after in transitions
    ]
    podium_logs = [log for log in logs if log.action == "tournament.podium"]
    assert len(podium_logs) == 1
    assert (podium_logs[0].entity_type, podium_logs[0].entity_id) == (
        "tournament",
        tournament_id,
    )
    assert podium_logs[0].actor_id is None
    assert podium_logs[0].after == {
        "champion": str(_team(fake, 1)),
        "runner_up": str(_team(fake, 3)),
        "third_place": str(_team(fake, 2)),
    }
    public = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public is not None and public.podium is not None
    assert public.podium.model_dump(mode="json") == {
        "champion": {"id": str(_team(fake, 1)), "name": "隊伍1"},
        "runner_up": {"id": str(_team(fake, 3)), "name": "隊伍3"},
        "third_place": {"id": str(_team(fake, 2)), "name": "隊伍2"},
    }


def test_final_disqualified_leaves_runner_up_empty(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)

    _confirm(session, rows["M8"], O.PLAYED, _team(fake, 7))
    _confirm(session, rows["M7"], O.DISQUALIFIED, _team(fake, 3))

    assert _status(session, tournament_id) == T.FINISHED
    assert _podium_k(fake, session, tournament_id) == (3, None, 7)


def test_finals_on_cancelled_tournament_do_not_finish_or_show_podium(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    _set_tournament_status(session, tournament_id, T.CANCELLED)

    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 1))
    _confirm(session, rows["M8"], O.PLAYED, _team(fake, 2))

    rows = _rows(session, tournament_id)
    assert (rows["M7"].status, rows["M8"].status) == (S.CONFIRMED, S.CONFIRMED)
    assert _status(session, tournament_id) == T.CANCELLED
    assert "tournament.podium" not in _actions(session, tournament_id)
    assert service.get_podium(session, tournament_id=tournament_id) is None
    public = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public is not None and public.podium is None


def test_podium_hidden_until_tournament_is_finished(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 決賽與季軍賽都已確認，但賽事狀態不是 finished（例如資料被人工改回）：不顯示名次
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 1))
    _confirm(session, rows["M8"], O.PLAYED, _team(fake, 2))
    assert _podium_k(fake, session, tournament_id) == (1, 3, 2)

    _set_tournament_status(session, tournament_id, T.ONGOING)

    assert service.get_podium(session, tournament_id=tournament_id) is None
    public = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public is not None and public.podium is None


def test_public_bracket_with_inconsistent_row_returns_without_podium(
    session: Session,
    fake_registration: FakeRegistration,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 1))
    assert _status(session, tournament.id) == T.FINISHED
    # 勝隊不是兩隊之一：progression 的檢查會拋 ValueError
    row = _rows(session, tournament.id)["M1"]
    row.winner_id = uuid.uuid4()
    session.add(row)
    session.flush()

    public = service.get_public_bracket(session, tournament_id=tournament.id)

    assert public is not None
    assert public.podium is None
    assert [m.code for m in public.matches] == ["M1"]
    assert "Inconsistent bracket" in caplog.text
    assert service.get_podium(session, tournament_id=tournament.id) is None


def test_repeated_advance_after_finish_changes_nothing(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 1))
    _confirm(session, rows["M8"], O.PLAYED, _team(fake, 2))
    logs = len(audit.list_for_tournament(session, tournament_id))
    outbox = count_outbox(session, "MatchResultConfirmed")

    for code in ("M7", "M8", "M1", "M5"):
        service.advance(session, match=service.lock_match(session, match_id=rows[code].id))

    assert _status(session, tournament_id) == T.FINISHED
    assert len(audit.list_for_tournament(session, tournament_id)) == logs
    assert count_outbox(session, "MatchResultConfirmed") == outbox
    # M5、M6、M7、M8 各在湊齊時發一次，重複推進不再發
    assert count_outbox(session, "MatchOpponentsDecided") == 4


def test_worker_twice_on_same_match_is_idempotent(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL)
    run_once([confirm_expired_appeals], session_factory=session_factory)
    session.expire_all()
    logs = len(audit.list_for_tournament(session, tournament.id))
    confirmed_at = _rows(session, tournament.id)["M1"].confirmed_at

    frozen_clock.advance(timedelta(minutes=5))
    run_once([confirm_expired_appeals], session_factory=session_factory)

    rows = _rows(session, tournament.id)
    assert rows["M1"].confirmed_at == confirmed_at
    assert _slots(fake, rows["M5"]) == (7, None)
    assert len(audit.list_for_tournament(session, tournament.id)) == logs
    assert count_outbox(session, "MatchResultConfirmed") == 1


def test_candidate_already_confirmed_after_lock_is_left_unchanged(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 找到候選後、鎖住前，另一個 worker 已經確認：重新檢查後不做任何事
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 7))
    frozen_clock.set(START + APPEAL)
    logs = len(audit.list_for_tournament(session, tournament.id))
    candidates = iter([rows["M1"].id])
    monkeypatch.setattr(
        repository,
        "find_expired_appeal_id",
        lambda _session, _now, **_kwargs: next(candidates, None),
    )

    assert confirm_expired_appeals(session) is True

    assert len(audit.list_for_tournament(session, tournament.id)) == logs
    assert count_outbox(session, "MatchResultConfirmed") == 1
    assert confirm_expired_appeals(session) is False


@pytest.mark.parametrize("ended", [T.CANCELLED, T.FINISHED])
def test_worker_skips_cancelled_or_finished_tournament(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    ended: TournamentStatus,
) -> None:
    fake = fake_registration
    stopped, _bracket = draw_with(session, fake, 8)
    stopped_rows = _rows(session, stopped.id)
    _enter_appeal(
        session,
        stopped_rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + timedelta(minutes=10),
    )
    _set_tournament_status(session, stopped.id, ended)
    stopped_teams = list(fake.teams)
    # 另一場進行中賽事的場次期限較晚：worker 跳過前者後仍會處理它
    active, _bracket = draw_with(session, fake, 2)
    active_rows = _rows(session, active.id)
    _enter_appeal(
        session,
        active_rows["M1"],
        outcome=O.PLAYED,
        winner_id=fake.teams[0],
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL)

    assert _drain(session, session_factory) == 1

    stopped_rows = _rows(session, stopped.id)
    assert stopped_rows["M1"].status == S.APPEAL_WINDOW
    assert stopped_rows["M5"].team_a_id is None
    assert _status(session, stopped.id) == ended
    assert "match.confirmed" not in _actions(session, stopped.id)
    assert stopped_teams[6] not in (
        stopped_rows["M5"].team_a_id,
        stopped_rows["M5"].team_b_id,
    )
    assert _rows(session, active.id)["M1"].status == S.CONFIRMED
    assert _status(session, active.id) == T.FINISHED


def test_tournament_cancelled_between_find_and_lock_is_skipped(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL)
    # 找候選時賽事仍為已公布，鎖住時已被取消
    published = tournaments_service.get_tournament(session, tournament_id=tournament.id)
    _set_tournament_status(session, tournament.id, T.CANCELLED)
    monkeypatch.setattr(
        tournaments_service, "get_tournament", lambda _session, **_kw: published
    )

    assert confirm_expired_appeals(session) is True

    assert _rows(session, tournament.id)["M1"].status == S.APPEAL_WINDOW


def test_candidate_not_yet_due_after_lock_is_left_unchanged(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 鎖住後重新檢查期限：候選的期限其實還沒到（例如申訴期被延長）就不確認
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _enter_appeal(
        session,
        rows["M1"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 7),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL - timedelta(seconds=1))
    candidates = iter([rows["M1"].id])
    monkeypatch.setattr(
        repository,
        "find_expired_appeal_id",
        lambda _session, _now, **_kwargs: next(candidates, None),
    )

    assert confirm_expired_appeals(session) is True

    rows = _rows(session, tournament.id)
    assert rows["M1"].status == S.APPEAL_WINDOW
    assert _slots(fake, rows["M5"]) == (None, None)


def test_match_without_outcome_does_not_block_later_expired_match(
    session: Session,
    session_factory: Callable[[], Session],
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    # 用真正的 finder：期限較早但沒有 outcome 的場次被排除，後面期滿的場次照常確認
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    bad = rows["M1"]
    bad.status = S.APPEAL_WINDOW
    bad.appeal_deadline = START + timedelta(minutes=5)
    session.add(bad)
    _enter_appeal(
        session,
        rows["M2"],
        outcome=O.PLAYED,
        winner_id=_team(fake, 3),
        deadline=START + APPEAL,
    )
    frozen_clock.set(START + APPEAL)

    assert _drain(session, session_factory) == 1

    rows = _rows(session, tournament.id)
    assert (rows["M1"].status, rows["M1"].confirmed_at) == (S.APPEAL_WINDOW, None)
    assert rows["M2"].status == S.CONFIRMED
    assert _slots(fake, rows["M5"]) == (None, 3)


def test_appeal_window_without_outcome_is_not_confirmed(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,  # noqa: ARG001  # 只為了凍結時鐘
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    rows = _rows(session, tournament.id)
    rows["M1"].status = S.APPEAL_WINDOW
    rows["M1"].appeal_deadline = START
    session.add(rows["M1"])
    session.flush()
    candidates = iter([rows["M1"].id])
    monkeypatch.setattr(
        repository,
        "find_expired_appeal_id",
        lambda _session, _now, **_kwargs: next(candidates, None),
    )

    assert confirm_expired_appeals(session) is True
    assert _rows(session, tournament.id)["M1"].status == S.APPEAL_WINDOW


@pytest.mark.parametrize("status", [S.SCHEDULED, S.CONFIRMED, S.VOIDED])
def test_confirm_match_on_unplayed_or_settled_match_is_409_and_changes_nothing(
    session: Session,
    fake_registration: FakeRegistration,
    status: MatchStatus,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    match = service.lock_match(session, match_id=_rows(session, tournament.id)["M1"].id)
    match.status = status
    session.add(match)
    session.flush()
    actions = _actions(session, tournament.id)

    with pytest.raises(BusinessError) as excinfo:
        service.confirm_match(
            session,
            match=match,
            outcome=O.PLAYED,
            winner_id=_team(fake, 1),
            actor_id=None,
        )

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "MATCH_INVALID_TRANSITION",
        409,
    )
    row = _rows(session, tournament.id)["M1"]
    assert row.updated_at == START
    assert (row.status, row.outcome, row.winner_id, row.confirmed_at) == (
        status,
        None,
        None,
        None,
    )
    assert _actions(session, tournament.id) == actions
    assert count_outbox(session, "MatchResultConfirmed") == 0


@pytest.mark.parametrize("status", [S.LIVE, S.APPEAL_WINDOW, S.APPEALED])
def test_confirm_match_accepts_played_statuses(
    session: Session, fake_registration: FakeRegistration, status: MatchStatus
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    match = service.lock_match(session, match_id=_rows(session, tournament.id)["M1"].id)
    match.status = status
    session.add(match)
    session.flush()

    service.confirm_match(
        session, match=match, outcome=O.PLAYED, winner_id=_team(fake, 1), actor_id=None
    )

    row = _rows(session, tournament.id)["M1"]
    assert (row.status, row.confirmed_at) == (S.CONFIRMED, START)
    assert _status(session, tournament.id) == T.FINISHED


def test_confirm_match_records_actor(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    actor = tournament.organizer_id
    match = service.lock_match(session, match_id=_rows(session, tournament.id)["M3"].id)
    service.transition_match(session, match=match, to=S.LIVE)

    service.confirm_match(
        session, match=match, outcome=O.FORFEIT, winner_id=_team(fake, 4), actor_id=actor
    )

    logs = [
        log
        for log in audit.list_for_tournament(session, tournament.id)
        if log.action == "match.confirmed"
    ]
    assert [(log.actor_id, log.after) for log in logs] == [
        (
            actor,
            {
                "status": "confirmed",
                "outcome": "forfeit",
                "winner_id": str(_team(fake, 4)),
            },
        )
    ]
    assert _slots(fake, _rows(session, tournament.id)["M6"]) == (4, None)


def test_two_team_tournament_finishes_without_third_place(
    session: Session,
    fake_registration: FakeRegistration,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    rows = _rows(session, tournament.id)

    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 2))

    assert _status(session, tournament.id) == T.FINISHED
    assert _podium_k(fake, session, tournament.id) == (2, 1, None)


# ---------------------------------------------------------------- confirm_walkover、advance


def test_confirm_walkover_confirms_lone_team_and_advances(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 8))
    m5 = service.lock_match(session, match_id=rows["M5"].id)

    service.confirm_walkover(session, match=m5)

    rows = _rows(session, tournament.id)
    assert (rows["M5"].status, rows["M5"].outcome, _k(fake, rows["M5"].winner_id)) == (
        S.CONFIRMED,
        O.WALKOVER,
        8,
    )
    assert rows["M5"].confirmed_at == START
    assert _slots(fake, rows["M7"]) == (8, None)


def test_confirm_walkover_without_teams_has_no_winner(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    m5 = service.lock_match(session, match_id=_rows(session, tournament.id)["M5"].id)

    service.confirm_walkover(session, match=m5)

    rows = _rows(session, tournament.id)
    assert (rows["M5"].status, rows["M5"].outcome, rows["M5"].winner_id) == (
        S.CONFIRMED,
        O.WALKOVER,
        None,
    )
    # 準決賽沒有勝隊：季軍賽取消
    assert rows["M8"].status == S.VOIDED


def test_confirm_walkover_with_both_teams_is_409(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    m1 = service.lock_match(session, match_id=_rows(session, tournament.id)["M1"].id)

    with pytest.raises(BusinessError) as excinfo:
        service.confirm_walkover(session, match=m1)

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "MATCH_INVALID_TRANSITION",
        409,
    )
    assert _rows(session, tournament.id)["M1"].status == S.SCHEDULED


def test_advance_on_unconfirmed_match_raises(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    match = service.lock_match(session, match_id=_rows(session, tournament.id)["M1"].id)

    with pytest.raises(ValueError, match="尚未確認"):
        service.advance(session, match=match)


def test_get_podium_without_bracket_is_none(session: Session) -> None:
    assert service.get_podium(session, tournament_id=uuid.uuid4()) is None


def test_find_expired_appeal_prefers_earliest_deadline(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,  # noqa: ARG001  # 只為了凍結時鐘
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    for code, minutes in (("M1", 20), ("M2", 10), ("M3", 40)):
        _enter_appeal(
            session,
            rows[code],
            outcome=O.PLAYED,
            winner_id=rows[code].team_a_id,
            deadline=START + timedelta(minutes=minutes),
        )
    now = START + APPEAL

    assert repository.find_expired_appeal_id(session, now) == rows["M2"].id
    assert (
        repository.find_expired_appeal_id(
            session, now, exclude_tournaments={tournament.id}
        )
        is None
    )
