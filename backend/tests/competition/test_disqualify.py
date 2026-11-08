"""Story 6.5 第一階段：competition `disqualify`（取消資格與對戰表頂替）。

沿用 test_confirm_advance 的對位（`random.Random(7)`，隊伍以「隊伍 k」稱呼）：

- 3 隊：M1 隊伍3–隊伍1；M2 隊伍2（輪空）– M1 勝者（決賽，沒有季軍賽）
- 8 隊：M1 7–8、M2 3–5、M3 1–4、M4 2–6；M5＝M1、M2 勝者；M6＝M3、M4 勝者；
  M7 決賽、M8 季軍賽
- 13 隊：M6 為輪空入座的隊伍 – M1 勝者

registration 以 `fake_registration` 替身（`get_registration_state`、`disqualify_registration`）。
"""

import uuid
from datetime import timedelta

import pytest
from sqlmodel import Session

from app.core import audit
from app.core.errors import BusinessError
from app.modules.competition import registration_port, repository, service
from app.modules.competition.models import (
    DisqualifyResult,
    Match,
    MatchOutcome,
    MatchStatus,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    draw_with,
    tournament_in,
)
from tests.competition.test_confirm_advance import (
    ROUND_2,
    _actions,
    _confirm,
    _eight_to_semis,
    _enter_appeal,
    _outbox,
    _podium_k,
    _rows,
    _set_tournament_status,
    _slots,
    _status,
    _team,
    _to_finals,
)
from tests.helpers import make_account

O = MatchOutcome  # noqa: E741
S = MatchStatus
T = TournamentStatus
pytestmark = pytest.mark.usefixtures("frozen_clock")

FORFEIT = timedelta(minutes=15)


# ---------------------------------------------------------------- 輔助


def _organizer(session: Session, tournament_id: uuid.UUID) -> uuid.UUID:
    return tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    ).organizer_id


def _dq(
    session: Session, fake: FakeRegistration, tournament_id: uuid.UUID, k: int
) -> tuple[DisqualifyResult, uuid.UUID]:
    actor = _organizer(session, tournament_id)
    result = service.disqualify(
        session, tournament_id=tournament_id, team_id=_team(fake, k), actor_id=actor
    )
    return result, actor


def _codes(rows: dict[str, Match], ids: list[uuid.UUID]) -> list[str]:
    by_id = {m.id: code for code, m in rows.items()}
    return [by_id[i] for i in ids]


def _result(match: Match) -> tuple[MatchStatus, MatchOutcome | None, uuid.UUID | None]:
    return (
        MatchStatus(match.status),
        MatchOutcome(match.outcome) if match.outcome is not None else None,
        match.winner_id,
    )


def _snapshot(
    session: Session, tournament_id: uuid.UUID
) -> dict[str, tuple[object, ...]]:
    return {
        code: (
            m.team_a_id,
            m.team_b_id,
            m.status,
            m.outcome,
            m.winner_id,
            m.forfeit_deadline,
            m.referee_account_id,
            m.updated_at,
        )
        for code, m in _rows(session, tournament_id).items()
    }


def _logs(
    session: Session, tournament_id: uuid.UUID, action: str
) -> list[audit.AuditLog]:
    return [
        log
        for log in audit.list_for_tournament(session, tournament_id)
        if log.action == action
    ]


def _update(session: Session, match: Match, **values: object) -> None:
    for key, value in values.items():
        setattr(match, key, value)
    session.add(match)
    session.flush()


# ---------------------------------------------------------------- 只改報名狀態


def test_before_draw_only_changes_registration(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament = tournament_in(session, T.OPEN)
    fake.set_team_count(3)
    fake.tournament_id = tournament.id

    result = service.disqualify(
        session,
        tournament_id=tournament.id,
        team_id=_team(fake, 2),
        actor_id=tournament.organizer_id,
    )

    assert result.affected_match_ids == []
    assert result.replacement_team_id is None
    assert fake.disqualified == [(_team(fake, 2), tournament.organizer_id)]


def test_eliminated_team_only_changes_registration(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, _rows_before = _eight_to_semis(session, fake)
    before = _snapshot(session, tournament_id)

    result, actor = _dq(session, fake, tournament_id, 8)

    assert (result.affected_match_ids, result.replacement_team_id) == ([], None)
    assert fake.disqualified == [(_team(fake, 8), actor)]
    assert _snapshot(session, tournament_id) == before


# ---------------------------------------------------------------- 進行中／申訴期／申訴中


@pytest.mark.parametrize("status", [S.LIVE, S.APPEAL_WINDOW, S.APPEALED])
@pytest.mark.parametrize(("dq", "winner"), [(7, 8), (8, 7)])
def test_active_match_is_confirmed_for_opponent(
    session: Session,
    fake_registration: FakeRegistration,
    status: MatchStatus,
    dq: int,
    winner: int,
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    if status == S.LIVE:
        _update(session, rows["M1"], status=S.LIVE)
    else:
        _enter_appeal(
            session,
            rows["M1"],
            outcome=O.PLAYED,
            winner_id=_team(fake, 7),
            deadline=ROUND_2,
        )
        _update(session, rows["M1"], status=status)

    result, actor = _dq(session, fake, tournament.id, dq)

    rows = _rows(session, tournament.id)
    assert _codes(rows, result.affected_match_ids) == ["M1"]
    assert result.replacement_team_id is None
    assert _result(rows["M1"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, winner))
    # 沿用 advance 晉級
    assert _slots(fake, rows["M5"]) == (winner, None)
    confirmed = _logs(session, tournament.id, "match.confirmed")
    assert [(log.entity_id, log.actor_id) for log in confirmed] == [
        (rows["M1"].id, actor)
    ]
    assert fake.disqualified == [(_team(fake, dq), actor)]


# ---------------------------------------------------------------- 待開打：判對手獲勝


def test_unplayed_team_with_opponent_present_loses_by_disqualification(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)

    result, actor = _dq(session, fake, tournament.id, 7)

    rows = _rows(session, tournament.id)
    assert _codes(rows, result.affected_match_ids) == ["M1"]
    assert result.replacement_team_id is None
    assert _result(rows["M1"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, 8))
    assert _slots(fake, rows["M5"]) == (8, None)
    confirmed = _logs(session, tournament.id, "match.confirmed")
    assert confirmed[0].before == {"status": "scheduled"}
    assert confirmed[0].after == {
        "status": "confirmed",
        "outcome": "disqualified",
        "winner_id": str(_team(fake, 8)),
    }
    assert confirmed[0].actor_id == actor
    assert _outbox(session, "MatchResultConfirmed") == [
        {"match_id": str(rows["M1"].id), "winner_id": str(_team(fake, 8))}
    ]
    # 公開對戰樹看得出是取消資格
    public = service.get_public_bracket(session, tournament_id=tournament.id)
    assert public is not None
    m1 = next(m for m in public.matches if m.code == "M1")
    assert m1.outcome == O.DISQUALIFIED


def test_waiting_for_third_place_gives_third_to_opponent(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, _rows_before = _to_finals(session, fake)

    result, _actor = _dq(session, fake, tournament_id, 7)

    rows = _rows(session, tournament_id)
    assert _codes(rows, result.affected_match_ids) == ["M8"]
    assert result.replacement_team_id is None
    assert _result(rows["M8"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, 2))
    # 決賽不受影響
    assert _slots(fake, rows["M7"]) == (3, 1)
    assert rows["M7"].status == S.SCHEDULED

    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 1))
    assert _status(session, tournament_id) == T.FINISHED
    assert _podium_k(fake, session, tournament_id) == (1, 3, 2)


def test_win_by_walkover_only_is_not_replaced(
    session: Session, fake_registration: FakeRegistration
) -> None:
    """隊伍7 只靠 walkover 進決賽（M2 雙方棄權）：不頂替，決賽由對手獲勝、亞軍從缺。"""
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    for code, winner in (("M3", 1), ("M4", 2)):
        _confirm(session, rows[code], O.PLAYED, _team(fake, winner))
    _confirm(session, rows["M6"], O.PLAYED, _team(fake, 1))
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 7))
    _confirm(session, rows["M2"], O.DOUBLE_FORFEIT, None)
    rows = _rows(session, tournament.id)
    assert _result(rows["M5"]) == (S.CONFIRMED, O.WALKOVER, _team(fake, 7))
    assert _slots(fake, rows["M7"]) == (7, 1)
    assert _result(rows["M8"])[0] == S.CONFIRMED

    result, _actor = _dq(session, fake, tournament.id, 7)

    rows = _rows(session, tournament.id)
    assert _codes(rows, result.affected_match_ids) == ["M7"]
    assert result.replacement_team_id is None
    assert _result(rows["M7"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, 1))
    assert _status(session, tournament.id) == T.FINISHED
    assert _podium_k(fake, session, tournament.id) == (1, None, 2)


def test_loser_already_disqualified_is_not_used_as_replacement(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, _rows_before = _eight_to_semis(session, fake)
    _dq(session, fake, tournament_id, 8)

    result, _actor = _dq(session, fake, tournament_id, 7)

    rows = _rows(session, tournament_id)
    assert _codes(rows, result.affected_match_ids) == ["M5"]
    assert result.replacement_team_id is None
    assert _result(rows["M5"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, 3))
    assert _slots(fake, rows["M7"]) == (3, None)


# ---------------------------------------------------------------- 待開打：頂替


def test_winner_waiting_for_next_match_is_replaced_by_last_loser(
    session: Session,
    fake_registration: FakeRegistration,
    frozen_clock: FrozenClockLike,
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)
    m1_before = _result(rows["M1"])
    public_before = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public_before is not None
    frozen_clock.advance(timedelta(minutes=5))

    result, actor = _dq(session, fake, tournament_id, 7)

    rows = _rows(session, tournament_id)
    assert _codes(rows, result.affected_match_ids) == ["M5"]
    assert result.replacement_team_id == _team(fake, 8)
    # 第 1 輪輸給它的隊伍8 出現在第 2 輪同一側，第 1 輪結果不變
    assert _slots(fake, rows["M5"]) == (8, 3)
    assert rows["M5"].status == S.SCHEDULED
    assert _result(rows["M1"]) == m1_before == (S.CONFIRMED, O.PLAYED, _team(fake, 7))
    assert rows["M5"].forfeit_deadline == ROUND_2 + FORFEIT
    assert fake.disqualified == [(_team(fake, 7), actor)]
    changed = _logs(session, tournament_id, "match.teams_changed")
    assert len(changed) == 1
    assert (changed[0].entity_id, changed[0].actor_id) == (rows["M5"].id, actor)
    assert changed[0].before == {
        "team_a_id": str(_team(fake, 7)),
        "team_b_id": str(_team(fake, 3)),
    }
    assert changed[0].after == {
        "team_a_id": str(_team(fake, 8)),
        "team_b_id": str(_team(fake, 3)),
        "disqualified_team_id": str(_team(fake, 7)),
    }

    # 公開對戰表重新取得：頂替隊伍出現且 updated_at 變新
    public = service.get_public_bracket(session, tournament_id=tournament_id)
    assert public is not None
    m5 = next(m for m in public.matches if m.code == "M5")
    assert m5.team_a is not None and m5.team_a.id == _team(fake, 8)
    assert public.updated_at > public_before.updated_at


def test_replacement_with_opponent_pending_starts_clock_when_both_known(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 7))

    result, _actor = _dq(session, fake, tournament.id, 7)

    rows = _rows(session, tournament.id)
    assert result.replacement_team_id == _team(fake, 8)
    assert _slots(fake, rows["M5"]) == (8, None)
    assert rows["M5"].forfeit_deadline is None

    _confirm(session, rows["M2"], O.PLAYED, _team(fake, 3))
    rows = _rows(session, tournament.id)
    assert _slots(fake, rows["M5"]) == (8, 3)
    assert rows["M5"].forfeit_deadline == ROUND_2 + FORFEIT


def test_forfeit_win_counts_as_last_loss(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 8)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.FORFEIT, _team(fake, 7))

    result, _actor = _dq(session, fake, tournament.id, 7)

    assert result.replacement_team_id == _team(fake, 8)


def test_referee_who_is_member_of_replacement_is_unassigned(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)
    referee = make_account(session)
    _update(session, rows["M5"], referee_account_id=referee.id)

    def is_member(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        return (team_id, account_id) == (_team(fake, 8), referee.id)

    monkeypatch.setattr(registration_port, "is_member", is_member)

    _dq(session, fake, tournament_id, 7)

    rows = _rows(session, tournament_id)
    assert rows["M5"].referee_account_id is None
    unassigned = _logs(session, tournament_id, "match.referee_unassigned")
    assert [(log.entity_id, log.actor_id) for log in unassigned] == [
        (rows["M5"].id, None)
    ]
    assert _outbox(session, "RefereeUnassigned") == [
        {"match_id": str(rows["M5"].id), "referee_account_id": str(referee.id)}
    ]


def test_referee_not_member_is_kept(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)
    referee = make_account(session)
    _update(session, rows["M5"], referee_account_id=referee.id)
    monkeypatch.setattr(
        registration_port, "is_member", lambda _s, *, team_id, account_id: False
    )

    _dq(session, fake, tournament_id, 7)

    assert _rows(session, tournament_id)["M5"].referee_account_id == referee.id
    assert _logs(session, tournament_id, "match.referee_unassigned") == []


def test_finalist_without_third_place_is_replaced_by_semifinal_loser(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 3)
    rows = _rows(session, tournament.id)
    _confirm(session, rows["M1"], O.PLAYED, _team(fake, 3))
    assert _slots(fake, _rows(session, tournament.id)["M2"]) == (2, 3)

    result, _actor = _dq(session, fake, tournament.id, 3)

    rows = _rows(session, tournament.id)
    assert _codes(rows, result.affected_match_ids) == ["M2"]
    assert result.replacement_team_id == _team(fake, 1)
    assert _slots(fake, rows["M2"]) == (2, 1)


def test_finalist_replaced_by_semifinal_loser_moved_from_third_place(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    referee = make_account(session)
    _update(session, rows["M7"], referee_account_id=referee.id)
    monkeypatch.setattr(
        registration_port,
        "is_member",
        lambda _s, *, team_id, account_id: team_id == _team(fake, 2),
    )

    result, actor = _dq(session, fake, tournament_id, 1)

    rows = _rows(session, tournament_id)
    assert _codes(rows, result.affected_match_ids) == ["M7", "M8"]
    assert result.replacement_team_id == _team(fake, 2)
    # 準決賽輸給隊伍1 的隊伍2 由季軍賽移到決賽，季軍賽由隊伍7 輪空奪季軍
    assert _slots(fake, rows["M7"]) == (3, 2)
    assert rows["M7"].status == S.SCHEDULED
    assert rows["M7"].referee_account_id is None
    assert _slots(fake, rows["M8"]) == (7, None)
    assert _result(rows["M8"]) == (S.CONFIRMED, O.WALKOVER, _team(fake, 7))
    changed = _logs(session, tournament_id, "match.teams_changed")
    assert [(log.entity_id, log.actor_id) for log in changed] == [
        (rows["M7"].id, actor),
        (rows["M8"].id, actor),
    ]
    assert changed[1].after == {
        "team_a_id": str(_team(fake, 7)),
        "team_b_id": None,
        "disqualified_team_id": str(_team(fake, 1)),
    }
    # 季軍賽的輪空確認操作者為系統
    confirmed = _logs(session, tournament_id, "match.confirmed")
    assert (confirmed[-1].entity_id, confirmed[-1].actor_id) == (rows["M8"].id, None)
    assert "match.referee_unassigned" in _actions(session, tournament_id)

    _confirm(session, rows["M7"], O.PLAYED, _team(fake, 3))
    assert _status(session, tournament_id) == T.FINISHED
    assert _podium_k(fake, session, tournament_id) == (3, 2, 7)


@pytest.mark.parametrize("third_state", ["live", "confirmed"])
def test_finalist_not_replaced_when_third_place_started_or_settled(
    session: Session, fake_registration: FakeRegistration, third_state: str
) -> None:
    fake = fake_registration
    tournament_id, rows = _to_finals(session, fake)
    if third_state == "live":
        _update(session, rows["M8"], status=S.LIVE)
    else:
        _confirm(session, rows["M8"], O.PLAYED, _team(fake, 7))

    result, _actor = _dq(session, fake, tournament_id, 1)

    rows = _rows(session, tournament_id)
    assert _codes(rows, result.affected_match_ids) == ["M7"]
    assert result.replacement_team_id is None
    assert _result(rows["M7"]) == (S.CONFIRMED, O.DISQUALIFIED, _team(fake, 3))
    assert _slots(fake, rows["M8"]) == (7, 2)
    if third_state == "confirmed":
        assert _status(session, tournament_id) == T.FINISHED
        # 亞軍從缺
        assert _podium_k(fake, session, tournament_id) == (3, None, 7)


# ---------------------------------------------------------------- 拒絕


@pytest.mark.parametrize(
    ("status", "code"),
    [(T.FINISHED, "TOURNAMENT_FINISHED"), (T.CANCELLED, "TOURNAMENT_CANCELLED")],
)
def test_finished_or_cancelled_tournament_is_rejected(
    session: Session,
    fake_registration: FakeRegistration,
    status: TournamentStatus,
    code: str,
) -> None:
    fake = fake_registration
    tournament_id, _rows_before = _eight_to_semis(session, fake)
    _set_tournament_status(session, tournament_id, status)
    before = _snapshot(session, tournament_id)

    with pytest.raises(BusinessError) as caught:
        _dq(session, fake, tournament_id, 7)

    assert (caught.value.code, caught.value.status_code) == (code, 409)
    assert fake.disqualified == []
    assert _snapshot(session, tournament_id) == before


def test_already_disqualified_team_is_rejected(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, _rows_before = _eight_to_semis(session, fake)
    _dq(session, fake, tournament_id, 7)
    before = _snapshot(session, tournament_id)

    with pytest.raises(BusinessError) as caught:
        _dq(session, fake, tournament_id, 7)

    assert (caught.value.code, caught.value.status_code) == (
        "TEAM_ALREADY_DISQUALIFIED",
        409,
    )
    assert len(fake.disqualified) == 1
    assert _snapshot(session, tournament_id) == before


def test_team_of_another_tournament_is_not_found(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    _tournament, _bracket = draw_with(session, fake, 8)
    other = tournament_in(session, T.ONGOING)

    with pytest.raises(BusinessError) as caught:
        service.disqualify(
            session,
            tournament_id=other.id,
            team_id=_team(fake, 1),
            actor_id=other.organizer_id,
        )

    assert (caught.value.code, caught.value.status_code) == (
        "REGISTRATION_NOT_FOUND",
        404,
    )
    assert fake.disqualified == []


# ---------------------------------------------------------------- 尚未支援：對手未定


def test_unplayed_bye_team_with_pending_opponent_is_not_supported(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 13)
    m6 = _rows(session, tournament.id)["M6"]
    assert m6.bye_a and m6.team_a_id is not None and m6.team_b_id is None
    bye_team = fake.teams.index(m6.team_a_id) + 1
    before = _snapshot(session, tournament.id)

    with pytest.raises(NotImplementedError):
        _dq(session, fake, tournament.id, bye_team)

    assert fake.disqualified == []
    assert _snapshot(session, tournament.id) == before


def test_finalist_with_pending_opponent_is_not_supported(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament_id, rows = _eight_to_semis(session, fake)
    _confirm(session, rows["M5"], O.PLAYED, _team(fake, 3))
    rows = _rows(session, tournament_id)
    assert _slots(fake, rows["M7"]) == (3, None)
    assert _slots(fake, rows["M8"]) == (7, None)
    before = _snapshot(session, tournament_id)

    with pytest.raises(NotImplementedError):
        _dq(session, fake, tournament_id, 3)

    assert fake.disqualified == []
    assert _snapshot(session, tournament_id) == before


def test_repository_clear_match_team_clears_one_side(
    session: Session, fake_registration: FakeRegistration
) -> None:
    fake = fake_registration
    tournament, _bracket = draw_with(session, fake, 2)
    row = _rows(session, tournament.id)["M1"]
    at = row.updated_at + timedelta(minutes=1)

    repository.clear_match_team(session, row, "b", at)

    row = _rows(session, tournament.id)["M1"]
    assert _slots(fake, row) == (1, None)
    assert row.updated_at == at
    repository.clear_match_team(session, row, "a", at)
    assert _slots(fake, _rows(session, tournament.id)["M1"]) == (None, None)
