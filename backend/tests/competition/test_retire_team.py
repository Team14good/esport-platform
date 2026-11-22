"""Story 4.5：抽籤後退賽與候補遞補（I/O 矩陣每列一個測試）。

沿用 test_confirm_advance 的對位（`random.Random(7)`，隊伍以「隊伍 k」稱呼）：

- 8 隊：M1 7–8、M2 3–5、M3 1–4、M4 2–6；M5＝M1、M2 勝者；M6＝M3、M4 勝者
- 13 隊：M6 為輪空入座的隊伍（由 M6 的資料取得）– M1 勝者

候補（`fake.add_waitlist`）遞補後加入 `fake.teams` 尾端，依序是隊伍 9、10…（8 隊時）。
registration 以 `fake_registration` 替身，隊長與隊員由 `fake.set_captain`／`fake.players` 控制。
學校與每校上限的順位規則在 tests/registration/test_post_draw_backfill.py。
"""

import uuid
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.core import audit, clock
from app.core.errors import BusinessError
from app.modules.competition import registration_port, repository, service
from app.modules.competition.models import CheckIn, MatchOutcome, MatchStatus
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    draw_with,
    tournament_in,
)
from tests.competition.test_confirm_advance import (
    _actions,
    _confirm,
    _outbox,
    _rows,
    _set_tournament_status,
    _slots,
    _team,
)
from tests.competition.test_disqualify import (
    _all_events,
    _logs,
    _organizer,
    _snapshot,
    _update,
)
from tests.helpers import make_account

O = MatchOutcome  # noqa: E741
S = MatchStatus
T = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

FORFEIT = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def _fake_roster(
    fake_registration: FakeRegistration, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registration_port, "is_captain", fake_registration.is_captain)
    monkeypatch.setattr(registration_port, "is_member", fake_registration.is_member)


# ---------------------------------------------------------------- 輔助


def _world(
    session: Session,
    fake: FakeRegistration,
    team_count: int = 8,
    *,
    waitlist: int = 0,
    status: TournamentStatus = T.PUBLISHED,
) -> TournamentRead:
    """已抽籤的賽事；每隊一位隊長，`waitlist` 支候補。"""
    tournament, _bracket = draw_with(session, fake, team_count)
    if status != T.PUBLISHED:
        _set_tournament_status(session, tournament.id, status)
    for team_id in fake.teams:
        fake.set_captain(team_id, make_account(session).id)
    fake.add_waitlist(waitlist)
    return tournament


def _captain(fake: FakeRegistration, k: int) -> uuid.UUID:
    return fake.captains[_team(fake, k)]


def _retire(session: Session, fake: FakeRegistration, k: int) -> uuid.UUID | None:
    result = service.retire_team(
        session, team_id=_team(fake, k), account_id=_captain(fake, k)
    )
    return result.replacement_team_id


def _unchanged_after_rejection(
    session: Session,
    fake: FakeRegistration,
    tournament_id: uuid.UUID,
    k: int,
    code: str,
    message: str | None = None,
) -> None:
    """退賽被拒絕：錯誤碼符合，場次、紀錄、事件與 registration 都沒有變。"""
    before = _snapshot(session, tournament_id)
    events = _all_events(session)
    logs = len(audit.list_for_tournament(session, tournament_id))
    calls = list(fake.calls)
    waitlist = list(fake.waitlist)
    with pytest.raises(BusinessError) as raised:
        _retire(session, fake, k)
    assert raised.value.code == code
    if message is not None:
        assert raised.value.message == message
    assert _snapshot(session, tournament_id) == before
    assert _all_events(session) == events
    assert len(audit.list_for_tournament(session, tournament_id)) == logs
    assert fake.retired == []
    assert fake.waitlist == waitlist
    assert "retire_registration" not in fake.calls[len(calls) :]


# ---------------------------------------------------------------- 第一輪退賽


def test_first_round_retire_with_waitlist_hands_over_the_slot(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=2)
    waiting = list(fake.waitlist)

    replacement = _retire(session, fake, 7)

    assert replacement == waiting[0]
    assert fake.retired == [(_team(fake, 7), _captain(fake, 7))]
    assert fake.backfilled == [waiting[0]]
    rows = _rows(session, tournament.id)
    # 隊伍 7 原本在 M1 的 a 位置，遞補隊接手同一個位置
    assert (rows["M1"].team_a_id, rows["M1"].team_b_id) == (
        waiting[0],
        _team(fake, 8),
    )
    assert rows["M1"].status == S.SCHEDULED
    assert rows["M1"].forfeit_deadline == rows["M1"].scheduled_at + FORFEIT
    changed = _logs(session, tournament.id, "match.teams_changed")
    assert len(changed) == 1
    assert changed[0].actor_id == _captain(fake, 7)
    assert changed[0].after is not None
    assert changed[0].after["retired_team_id"] == str(_team(fake, 7))
    assert changed[0].after["team_a_id"] == str(waiting[0])
    assert _outbox(session, "BracketBackfilled") == [
        {
            "match_id": str(rows["M1"].id),
            "team_id": str(waiting[0]),
            "replaced_team_id": str(_team(fake, 7)),
        }
    ]
    assert [e["match_id"] for e in _outbox(session, "MatchOpponentsDecided")] == [
        str(rows["M1"].id)
    ]
    assert _outbox(session, "OpponentRetired") == []


def test_forfeit_deadline_restarts_from_now_after_backfill(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    scheduled = _rows(session, tournament.id)["M1"].scheduled_at
    frozen_clock.set(scheduled + timedelta(minutes=5))

    _retire(session, fake, 7)

    rows = _rows(session, tournament.id)
    assert rows["M1"].forfeit_deadline == clock.now() + FORFEIT


def test_retire_without_waitlist_gives_opponent_a_walkover(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake)

    assert _retire(session, fake, 7) is None

    rows = _rows(session, tournament.id)
    assert fake.retired == [(_team(fake, 7), _captain(fake, 7))]
    assert rows["M1"].team_a_id is None
    assert rows["M1"].team_b_id == _team(fake, 8)
    assert (rows["M1"].status, rows["M1"].outcome, rows["M1"].winner_id) == (
        S.CONFIRMED,
        O.WALKOVER,
        _team(fake, 8),
    )
    # 對手晉級到 M5；M2 還沒比完，M5 只有一隊、沒有棄權期限
    assert _slots(fake, rows["M5"]) == (8, None)
    assert rows["M5"].forfeit_deadline is None
    assert _outbox(session, "OpponentRetired") == [
        {"match_id": str(rows["M1"].id), "winner_id": str(_team(fake, 8))}
    ]
    assert _outbox(session, "BracketBackfilled") == []
    actions = _actions(session, tournament.id)
    assert actions.count("match.teams_changed") == 1
    assert actions.count("match.confirmed") == 1
    confirmed = _logs(session, tournament.id, "match.confirmed")[0]
    assert confirmed.actor_id is None  # 輪空確認的操作者是系統


def test_walkover_starts_next_match_clock_when_both_teams_are_known(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M2"], O.PLAYED, _team(fake, 3))

    _retire(session, fake, 7)

    rows = _rows(session, tournament.id)
    assert _slots(fake, rows["M5"]) == (8, 3)
    assert rows["M5"].forfeit_deadline == rows["M5"].scheduled_at + FORFEIT
    decided = [e["match_id"] for e in _outbox(session, "MatchOpponentsDecided")]
    assert str(rows["M5"].id) in decided


# ---------------------------------------------------------------- 輪空隊伍


def _bye_k(session: Session, fake: FakeRegistration, tournament_id: uuid.UUID) -> int:
    """13 隊：M6 的輪空入座隊伍（M6 為它與 M1 勝者的對戰）。"""
    m6 = _rows(session, tournament_id)["M6"]
    assert m6.bye_a and m6.team_a_id is not None and m6.team_b_id is None
    return fake.teams.index(m6.team_a_id) + 1


def test_bye_team_retires_with_opponent_decided_and_waitlist(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, 13, waitlist=1)
    bye = _bye_k(session, fake, tournament.id)
    rows = _rows(session, tournament.id)
    winner = rows["M1"].team_a_id
    assert winner is not None
    _confirm(session, rows["M1"], O.PLAYED, winner)
    waiting = fake.waitlist[0]

    assert _retire(session, fake, bye) == waiting

    rows = _rows(session, tournament.id)
    assert (rows["M6"].team_a_id, rows["M6"].team_b_id) == (waiting, winner)
    assert rows["M6"].forfeit_deadline == rows["M6"].scheduled_at + FORFEIT


def test_bye_team_retires_with_opponent_decided_and_no_waitlist(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, 13)
    bye = _bye_k(session, fake, tournament.id)
    rows = _rows(session, tournament.id)
    winner = rows["M1"].team_a_id
    assert winner is not None
    _confirm(session, rows["M1"], O.PLAYED, winner)

    assert _retire(session, fake, bye) is None

    rows = _rows(session, tournament.id)
    assert (rows["M6"].status, rows["M6"].outcome) == (S.CONFIRMED, O.WALKOVER)
    assert rows["M6"].winner_id == winner
    assert rows["M10"].team_a_id == winner  # M10＝M6、M7 勝者


def test_bye_team_opponent_pending_with_waitlist_keeps_waiting(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, 13, waitlist=1)
    bye = _bye_k(session, fake, tournament.id)
    waiting = fake.waitlist[0]

    assert _retire(session, fake, bye) == waiting

    rows = _rows(session, tournament.id)
    # 遞補隊接手輪空位置；M6 仍等 M1 的勝隊
    assert (rows["M6"].team_a_id, rows["M6"].team_b_id) == (waiting, None)
    assert rows["M6"].status == S.SCHEDULED
    assert rows["M6"].forfeit_deadline is None
    assert _outbox(session, "MatchOpponentsDecided") == []


def test_bye_team_opponent_pending_without_waitlist_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, 13)
    bye = _bye_k(session, fake, tournament.id)

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        bye,
        "TEAM_NOT_RETIRABLE",
        "對手確定後才能退賽。",
    )
    status = service.get_retirement_status(
        session, team_id=_team(fake, bye), account_id=_captain(fake, bye)
    )
    assert (status.retirable, status.reason) == (False, "對手確定後才能退賽。")


# ---------------------------------------------------------------- 拒絕


def test_check_in_blocks_retirement(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    rows = _rows(session, tournament.id)
    # 對手（隊伍 8）已報到
    repository.add_check_in(
        session,
        CheckIn(
            match_id=rows["M1"].id,
            team_id=_team(fake, 8),
            account_id=_captain(fake, 8),
            at=clock.now(),
        ),
    )

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        7,
        "TEAM_NOT_RETIRABLE",
        "已有隊伍報到，無法退賽。",
    )
    status = service.get_retirement_status(
        session, team_id=_team(fake, 7), account_id=_captain(fake, 7)
    )
    assert (status.retirable, status.reason) == (False, None)


@pytest.mark.parametrize("match_status", [S.LIVE, S.APPEAL_WINDOW, S.APPEALED])
def test_started_first_match_blocks_retirement(
    session: Session, fake_registration: FakeRegistration, match_status: MatchStatus
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    _update(session, _rows(session, tournament.id)["M1"], status=match_status)

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        7,
        "TEAM_NOT_RETIRABLE",
        "比賽已經開始，無法退賽。",
    )


@pytest.mark.parametrize("k", [7, 8])
def test_team_with_a_confirmed_match_cannot_retire(
    session: Session, fake_registration: FakeRegistration, k: int
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 7))

    # 隊伍 7 贏了在 M5 等待，隊伍 8 已淘汰；兩者都已有比賽結果
    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        k,
        "TEAM_NOT_RETIRABLE",
        "隊伍已有比賽結果，無法退賽。",
    )


def test_walkover_win_counts_as_a_confirmed_match(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    _retire(session, fake, 7)  # 隊伍 8 在 M1 以遞補後的對手比賽
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 8))
    fake.retired.clear()

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        8,
        "TEAM_NOT_RETIRABLE",
        "隊伍已有比賽結果，無法退賽。",
    )


def test_only_the_captain_can_retire(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    player = make_account(session)
    fake.players[_team(fake, 7)].add(player.id)
    before = _snapshot(session, tournament.id)

    with pytest.raises(BusinessError) as player_error:
        service.retire_team(session, team_id=_team(fake, 7), account_id=player.id)
    with pytest.raises(BusinessError) as outsider_error:
        service.retire_team(
            session, team_id=_team(fake, 7), account_id=_captain(fake, 8)
        )

    assert (player_error.value.code, player_error.value.status_code) == (
        "TEAM_CAPTAIN_REQUIRED",
        403,
    )
    assert (outsider_error.value.code, outsider_error.value.status_code) == (
        "TEAM_MEMBER_REQUIRED",
        403,
    )
    assert _snapshot(session, tournament.id) == before
    assert fake.retired == []
    assert fake.waitlist != []


def test_unknown_team_is_404(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _world(session, fake)

    with pytest.raises(BusinessError) as raised:
        service.retire_team(session, team_id=uuid.uuid4(), account_id=_captain(fake, 7))

    assert (raised.value.code, raised.value.status_code) == ("TEAM_NOT_FOUND", 404)


@pytest.mark.parametrize("status", ["waitlisted", "retired", "disqualified"])
def test_registration_must_be_drawn(
    session: Session, fake_registration: FakeRegistration, status: str
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    fake.statuses[_team(fake, 7)] = status

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        7,
        "TEAM_NOT_RETIRABLE",
        "只有已參賽的隊伍可以退賽。",
    )


@pytest.mark.parametrize("status", [T.FINISHED, T.CANCELLED])
def test_ended_tournament_cannot_retire(
    session: Session, fake_registration: FakeRegistration, status: TournamentStatus
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1, status=status)

    _unchanged_after_rejection(
        session, fake, tournament.id, 7, "TEAM_NOT_RETIRABLE", "賽事目前不能退賽。"
    )


def test_ongoing_tournament_can_retire(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _world(session, fake, waitlist=1, status=T.ONGOING)

    assert _retire(session, fake, 7) is not None


def test_retire_before_draw_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = tournament_in(session, T.CLOSED)
    fake.set_team_count(3)
    fake.tournament_id = tournament.id
    fake.set_captain(_team(fake, 1), make_account(session).id)

    with pytest.raises(BusinessError) as raised:
        _retire(session, fake, 1)

    assert raised.value.code == "TEAM_NOT_RETIRABLE"
    status = service.get_retirement_status(
        session, team_id=_team(fake, 1), account_id=_captain(fake, 1)
    )
    assert (status.retirable, status.reason) == (False, None)


# ---------------------------------------------------------------- 退賽與其他操作的順序


def test_retire_then_check_in_is_rejected(
    session: Session, fake_registration: FakeRegistration, frozen_clock: FrozenClockLike
) -> None:
    fake = fake_registration
    tournament = _world(session, fake)
    rows = _rows(session, tournament.id)
    frozen_clock.set(rows["M1"].scheduled_at - timedelta(minutes=10))
    _retire(session, fake, 7)

    # 退賽後 M1 已確認；退賽隊長的報到被拒
    with pytest.raises(BusinessError):
        service.check_in(
            session,
            tournament_id=tournament.id,
            match_id=rows["M1"].id,
            account_id=_captain(fake, 7),
        )
    assert repository.list_check_ins(session, rows["M1"].id) == []


def test_check_in_then_retire_is_rejected(
    session: Session, fake_registration: FakeRegistration, frozen_clock: FrozenClockLike
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    rows = _rows(session, tournament.id)
    frozen_clock.set(rows["M1"].scheduled_at - timedelta(minutes=10))
    service.check_in(
        session,
        tournament_id=tournament.id,
        match_id=rows["M1"].id,
        account_id=_captain(fake, 8),
    )

    _unchanged_after_rejection(
        session,
        fake,
        tournament.id,
        7,
        "TEAM_NOT_RETIRABLE",
        "已有隊伍報到，無法退賽。",
    )


def test_retire_then_disqualify_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake)
    _retire(session, fake, 7)

    with pytest.raises(BusinessError) as raised:
        service.disqualify(
            session,
            tournament_id=tournament.id,
            team_id=_team(fake, 7),
            actor_id=tournament.organizer_id,
        )

    assert raised.value.code == "REGISTRATION_INVALID_TRANSITION"


def test_disqualify_then_retire_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake)
    service.disqualify(
        session,
        tournament_id=tournament.id,
        team_id=_team(fake, 7),
        actor_id=tournament.organizer_id,
    )
    fake.retired.clear()

    with pytest.raises(BusinessError) as raised:
        _retire(session, fake, 7)

    assert raised.value.code == "TEAM_NOT_RETIRABLE"


# ---------------------------------------------------------------- 裁判衝突


def test_referee_who_is_a_member_of_the_replacement_is_unassigned(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    referee = make_account(session)
    fake.players[fake.waitlist[0]] = {referee.id}
    match = _rows(session, tournament.id)["M1"]
    _update(session, match, referee_account_id=referee.id)

    _retire(session, fake, 7)

    rows = _rows(session, tournament.id)
    assert rows["M1"].referee_account_id is None
    assert len(_logs(session, tournament.id, "match.referee_unassigned")) == 1
    assert _outbox(session, "RefereeUnassigned") == [
        {"match_id": str(match.id), "referee_account_id": str(referee.id)}
    ]


def test_unrelated_referee_stays_assigned(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    referee = make_account(session)
    _update(session, _rows(session, tournament.id)["M1"], referee_account_id=referee.id)

    _retire(session, fake, 7)

    assert _rows(session, tournament.id)["M1"].referee_account_id == referee.id


# ---------------------------------------------------------------- S17 狀態查詢


def test_status_is_retirable_for_the_captain(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _world(session, fake)

    status = service.get_retirement_status(
        session, team_id=_team(fake, 7), account_id=_captain(fake, 7)
    )

    assert (status.retirable, status.reason) == (True, None)


def test_status_for_a_player_is_not_retirable_and_for_an_outsider_is_403(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _world(session, fake)
    player = make_account(session)
    fake.players[_team(fake, 7)].add(player.id)

    status = service.get_retirement_status(
        session, team_id=_team(fake, 7), account_id=player.id
    )
    with pytest.raises(BusinessError) as raised:
        service.get_retirement_status(
            session, team_id=_team(fake, 7), account_id=_captain(fake, 8)
        )

    assert (status.retirable, status.reason) == (False, None)
    assert (raised.value.code, raised.value.status_code) == (
        "TEAM_MEMBER_REQUIRED",
        403,
    )


def test_status_of_a_cancelled_tournament_is_not_retirable(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _world(session, fake, waitlist=1, status=T.CANCELLED)

    status = service.get_retirement_status(
        session, team_id=_team(fake, 7), account_id=_captain(fake, 7)
    )

    assert status.retirable is False


def test_disqualify_of_a_first_round_team_in_a_cancelled_tournament_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    # 6.5 分流：第一場待開打的隊伍原本走退賽路徑，賽事已取消仍交給 disqualification 拒絕
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1, status=T.CANCELLED)
    before = _snapshot(session, tournament.id)

    with pytest.raises(BusinessError) as caught:
        service.disqualify(
            session,
            tournament_id=tournament.id,
            team_id=_team(fake, 7),
            actor_id=_organizer(session, tournament.id),
        )

    assert (caught.value.code, caught.value.status_code) == (
        "TOURNAMENT_CANCELLED",
        409,
    )
    assert fake.disqualified == []
    assert _snapshot(session, tournament.id) == before


def test_status_does_not_write(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = _world(session, fake, waitlist=1)
    before = _snapshot(session, tournament.id)
    events = _all_events(session)

    service.get_retirement_status(
        session, team_id=_team(fake, 7), account_id=_captain(fake, 7)
    )

    assert _snapshot(session, tournament.id) == before
    assert _all_events(session) == events
    assert fake.retired == []
