"""Story 5.3、5.4 第二階段：逐局比分登錄、刪除、送出系列結果與 S4 讀取 API。

8 隊抽籤後第一輪 M1 兩隊已確定（BO3、申訴 30 分鐘）；預設兩隊都已報到、未指派裁判，
所以記分者是賽事主辦方。frozen_clock 凍結在 2026-10-18 11:00 UTC。
"""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, func, select

from app.core import audit, clock
from app.core.events import OutboxEvent
from app.modules.competition import repository, service
from app.modules.competition.models import (
    CheckIn,
    GameScoreIn,
    Match,
    MatchGame,
    MatchStatus,
)
from app.modules.identity.models import Account
from app.modules.tournaments.models import ScoreType, Tournament, TournamentStatus
from app.worker import jobs, run_once
from tests.competition.conftest import FakeRegistration, FrozenClockLike, draw_with
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

APPEAL = timedelta(minutes=30)


class Setup:
    """已抽籤的賽事；M1 兩隊預設都已報到。"""

    def __init__(
        self,
        session: Session,
        fake: FakeRegistration,
        *,
        score_type: ScoreType = ScoreType.WIN_LOSS,
        check_in: tuple[str, ...] = ("a", "b"),
        bo: int = 3,
    ) -> None:
        tournament, bracket = draw_with(session, fake, 8)
        row = session.get(Tournament, tournament.id)
        assert row is not None
        # 比分型態與 BO 只看賽事的遊戲快照
        row.game_snapshot = {
            **row.game_snapshot,
            "score_type": score_type.value,
            "bo": bo,
        }
        session.add(row)
        session.flush()
        self.session = session
        self.tournament_id = tournament.id
        self.matches = {m.code: m for m in bracket.matches}
        organizer = session.get(Account, tournament.organizer_id)
        assert organizer is not None
        self.organizer = organizer
        self.fake = fake
        for side in check_in:
            self.check_in(side)

    def match_id(self, code: str = "M1") -> uuid.UUID:
        return self.matches[code].id

    def team(self, side: str, code: str = "M1") -> uuid.UUID:
        match = self.matches[code]
        team_id = match.team_a_id if side == "a" else match.team_b_id
        assert team_id is not None
        return team_id

    def check_in(self, side: str, code: str = "M1") -> None:
        self.session.add(
            CheckIn(
                match_id=self.match_id(code),
                team_id=self.team(side, code),
                account_id=make_account(self.session).id,
                at=clock.now(),
            )
        )
        self.session.flush()

    def next_code(self, code: str = "M1") -> str:
        next_id = self.matches[code].next_match_id
        return next(c for c, m in self.matches.items() if m.id == next_id)

    def base(self, code: str = "M1", *, tournament_id: uuid.UUID | None = None) -> str:
        return (
            f"{API}/tournaments/{tournament_id or self.tournament_id}"
            f"/matches/{self.match_id(code)}"
        )

    def game_url(self, game_no: int, code: str = "M1") -> str:
        return f"{self.base(code)}/games/{game_no}"


Factory = Callable[..., Setup]


@pytest.fixture
def make_setup(session: Session, fake_registration: FakeRegistration) -> Factory:
    def factory(**kwargs: Any) -> Setup:
        result = Setup(session, fake_registration, **kwargs)
        session.commit()
        return result

    return factory


@pytest.fixture
def setup(make_setup: Factory) -> Setup:
    return make_setup()


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def _put(
    client: TestClient,
    setup: Setup,
    game_no: int,
    body: dict[str, Any],
    *,
    account: Account | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    headers = headers or _headers(client, account or setup.organizer)
    return client.put(setup.game_url(game_no), json=body, headers=headers)


def _record_sides(client: TestClient, setup: Setup, sides: str) -> dict[str, str]:
    """以主辦方依序登錄 `win_loss` 的各局，例如 "aba"。"""
    headers = _headers(client, setup.organizer)
    for no, side in enumerate(sides, start=1):
        response = _put(client, setup, no, {"winner_side": side}, headers=headers)
        assert response.status_code == 200, response.text
    return headers


def _match(session: Session, setup: Setup, code: str = "M1") -> Match:
    session.expire_all()
    match = session.get(Match, setup.match_id(code))
    assert match is not None
    return match


def _games(
    session: Session, setup: Setup
) -> list[tuple[int, str, int | None, int | None]]:
    session.expire_all()
    rows = session.exec(
        select(MatchGame)
        .where(MatchGame.match_id == setup.match_id())
        .order_by(col(MatchGame.game_no))
    )
    return [(g.game_no, g.winner_side, g.score_a, g.score_b) for g in rows]


def _audits(session: Session, setup: Setup, action: str) -> list[audit.AuditLogRead]:
    return [
        r
        for r in audit.list_for_tournament(session, setup.tournament_id)
        if r.action == action
    ]


def _all_match_audits(session: Session, setup: Setup) -> int:
    return len(
        [
            r
            for r in audit.list_for_tournament(session, setup.tournament_id)
            if r.action.startswith("match.")
        ]
    )


def _outbox(session: Session, event_type: str) -> list[dict[str, object]]:
    statement = select(OutboxEvent).where(OutboxEvent.type == event_type)
    return [event.payload for event in session.exec(statement)]


def _set_status(session: Session, setup: Setup, status: MatchStatus) -> None:
    match = session.get(Match, setup.match_id())
    assert match is not None
    match.status = status
    session.add(match)
    session.commit()


# ---------------------------------------------------------------- 登錄


def test_first_game_moves_match_live(
    client: TestClient, session: Session, setup: Setup
) -> None:
    response = _put(client, setup, 1, {"winner_side": "a"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_scorer"] is True
    assert body["reason"] is None
    assert body["games"] == [
        {"game_no": 1, "winner_side": "a", "score_a": None, "score_b": None}
    ]
    assert body["series"] == {
        "wins_a": 1,
        "wins_b": 0,
        "winner": None,
        "can_submit": False,
        "wins_needed": 2,
        "reason": "not_decided",
    }
    match = _match(session, setup)
    assert match.status == MatchStatus.LIVE
    assert (match.wins_a, match.wins_b) == (1, 0)
    [record] = _audits(session, setup, "match.game_recorded")
    assert record.actor_id == setup.organizer.id
    # 第一局帶出狀態轉換
    assert record.before == {"status": "scheduled"}
    assert record.after == {
        "game_no": 1,
        "winner_side": "a",
        "score_a": None,
        "score_b": None,
        "wins_a": 1,
        "wins_b": 0,
        "status": "live",
    }


def test_later_game_audit_has_no_status(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _record_sides(client, setup, "ab")

    first, second = _audits(session, setup, "match.game_recorded")
    assert second.before is None
    assert second.after is not None
    assert "status" not in second.after


@pytest.mark.parametrize(("bo", "needed"), [(1, 1), (5, 3)])
def test_threshold_follows_tournament_bo(
    client: TestClient, make_setup: Factory, bo: int, needed: int
) -> None:
    setup = make_setup(bo=bo)
    headers = _headers(client, setup.organizer)

    state = client.get(f"{setup.base()}/score-entry", headers=headers).json()
    assert state["series"]["wins_needed"] == needed
    if needed > 1:
        response = client.post(f"{setup.base()}/submit", headers=headers)
        assert _code(response) == "SERIES_NOT_DECIDED"
        assert (
            response.json()["detail"]["message"]
            == f"任一隊拿到 {needed} 勝後才能送出。"
        )

    # a 連勝到門檻前一局都還能新增；達門檻後下一局被拒
    for no in range(1, needed + 1):
        response = _put(client, setup, no, {"winner_side": "a"}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["series"]["can_submit"] is (no == needed)
    response = _put(client, setup, needed + 1, {"winner_side": "b"}, headers=headers)
    assert _code(response) == "SERIES_DECIDED"


def test_record_updates_match_updated_at(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    frozen_clock.advance(timedelta(minutes=7))
    _put(client, setup, 1, {"winner_side": "a"})

    assert _match(session, setup).updated_at == clock.now()


def test_rounds_score(
    client: TestClient, session: Session, make_setup: Factory
) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)

    response = _put(client, setup, 1, {"score_a": 13, "score_b": 11})

    assert response.status_code == 200, response.text
    assert response.json()["games"] == [
        {"game_no": 1, "winner_side": "a", "score_a": 13, "score_b": 11}
    ]
    assert _games(session, setup) == [(1, "a", 13, 11)]


def test_rounds_tie(client: TestClient, session: Session, make_setup: Factory) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)

    response = _put(client, setup, 1, {"score_a": 12, "score_b": 12})

    assert response.status_code == 409
    assert _code(response) == "SCORE_TIE"
    assert _games(session, setup) == []


@pytest.mark.parametrize(
    "body",
    [
        {"score_a": 100, "score_b": 98},
        {"score_a": -1, "score_b": 13},
        {"score_a": 13.5, "score_b": 1},
        {"score_a": True, "score_b": 0},
        {"winner_side": "c"},
    ],
)
def test_out_of_range_is_422(
    client: TestClient, session: Session, make_setup: Factory, body: dict[str, Any]
) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)

    response = _put(client, setup, 1, body)

    assert response.status_code == 422
    assert _games(session, setup) == []


def test_rounds_upper_bound_is_accepted(
    client: TestClient, make_setup: Factory
) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)

    response = _put(client, setup, 1, {"score_a": 99, "score_b": 0})

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("score_type", "body"),
    [
        (ScoreType.WIN_LOSS, {"score_a": 13, "score_b": 11}),
        (ScoreType.WIN_LOSS, {}),
        (ScoreType.ROUNDS, {"winner_side": "a"}),
        (ScoreType.ROUNDS, {"score_a": 13}),
    ],
)
def test_wrong_fields_for_score_type(
    client: TestClient,
    session: Session,
    make_setup: Factory,
    score_type: ScoreType,
    body: dict[str, Any],
) -> None:
    setup = make_setup(score_type=score_type)

    response = _put(client, setup, 1, body)

    assert response.status_code == 409
    assert _code(response) == "SCORE_INVALID"
    assert _games(session, setup) == []


def test_skipped_game_no(client: TestClient, session: Session, setup: Setup) -> None:
    headers = _record_sides(client, setup, "a")

    response = _put(client, setup, 3, {"winner_side": "a"}, headers=headers)

    assert response.status_code == 409
    assert _code(response) == "INVALID_GAME_NO"
    assert _games(session, setup) == [(1, "a", None, None)]


def test_series_already_decided(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "aa")

    response = _put(client, setup, 3, {"winner_side": "b"}, headers=headers)

    assert response.status_code == 409
    assert _code(response) == "SERIES_DECIDED"
    assert len(_games(session, setup)) == 2


def test_overwrite_records_before_and_after(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "ab")

    response = _put(client, setup, 1, {"winner_side": "b"}, headers=headers)

    assert response.status_code == 200, response.text
    series = response.json()["series"]
    assert (series["wins_a"], series["wins_b"], series["winner"]) == (0, 2, "b")
    assert series["can_submit"] is True
    assert _games(session, setup) == [(1, "b", None, None), (2, "b", None, None)]
    match = _match(session, setup)
    assert (match.wins_a, match.wins_b) == (0, 2)
    record = _audits(session, setup, "match.game_recorded")[-1]
    assert record.before == {
        "game_no": 1,
        "winner_side": "a",
        "score_a": None,
        "score_b": None,
    }
    assert record.after is not None
    assert record.after["winner_side"] == "b"
    assert (record.after["wins_a"], record.after["wins_b"]) == (0, 2)


def test_overwrite_rounds_records_old_scores(
    client: TestClient, session: Session, make_setup: Factory
) -> None:
    setup = make_setup(score_type=ScoreType.ROUNDS)
    headers = _headers(client, setup.organizer)
    _put(client, setup, 1, {"score_a": 13, "score_b": 11}, headers=headers)

    response = _put(client, setup, 1, {"score_a": 9, "score_b": 13}, headers=headers)

    assert response.status_code == 200, response.text
    record = _audits(session, setup, "match.game_recorded")[-1]
    assert record.before == {
        "game_no": 1,
        "winner_side": "a",
        "score_a": 13,
        "score_b": 11,
    }
    assert record.after is not None
    assert (record.after["score_a"], record.after["score_b"]) == (9, 13)


def test_overwrite_creating_redundant_games(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "aba")

    response = _put(client, setup, 1, {"winner_side": "b"}, headers=headers)

    assert response.status_code == 409
    assert _code(response) == "REDUNDANT_GAMES"
    assert [g[1] for g in _games(session, setup)] == ["a", "b", "a"]


# ---------------------------------------------------------------- 刪除


def test_delete_last_game(client: TestClient, session: Session, setup: Setup) -> None:
    headers = _record_sides(client, setup, "aba")

    response = client.delete(setup.game_url(3), headers=headers)

    assert response.status_code == 200, response.text
    assert [g["winner_side"] for g in response.json()["games"]] == ["a", "b"]
    assert [g[1] for g in _games(session, setup)] == ["a", "b"]
    match = _match(session, setup)
    assert (match.wins_a, match.wins_b) == (1, 1)
    [record] = _audits(session, setup, "match.game_deleted")
    assert record.actor_id == setup.organizer.id
    assert record.before == {
        "game_no": 3,
        "winner_side": "a",
        "score_a": None,
        "score_b": None,
    }
    # 刪掉多餘的局後，原本會被拒絕的覆寫就可以了
    assert (
        _put(client, setup, 1, {"winner_side": "b"}, headers=headers).status_code == 200
    )


def test_delete_not_last_game(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "aba")

    response = client.delete(setup.game_url(1), headers=headers)

    assert response.status_code == 409
    assert _code(response) == "NOT_LAST_GAME"
    assert len(_games(session, setup)) == 3


def test_delete_without_games(client: TestClient, setup: Setup) -> None:
    response = client.delete(
        setup.game_url(1), headers=_headers(client, setup.organizer)
    )

    assert response.status_code == 409
    assert _code(response) == "INVALID_GAME_NO"


def test_delete_only_game_keeps_match_live(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "a")

    response = client.delete(setup.game_url(1), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["games"] == []
    match = _match(session, setup)
    assert match.status == MatchStatus.LIVE
    assert (match.wins_a, match.wins_b) == (0, 0)
    # 之後重新登錄第 1 局，不會再轉換狀態
    assert (
        _put(client, setup, 1, {"winner_side": "b"}, headers=headers).status_code == 200
    )
    assert _match(session, setup).status == MatchStatus.LIVE


# ---------------------------------------------------------------- 前置條件


@pytest.mark.parametrize("checked_in", [(), ("a",), ("b",)])
def test_check_in_incomplete(
    client: TestClient,
    session: Session,
    make_setup: Factory,
    checked_in: tuple[str, ...],
) -> None:
    setup = make_setup(check_in=checked_in)

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert response.status_code == 409
    assert _code(response) == "CHECK_IN_INCOMPLETE"
    assert _games(session, setup) == []
    assert _match(session, setup).status == MatchStatus.SCHEDULED


def test_check_in_of_other_match_does_not_count(
    client: TestClient, make_setup: Factory
) -> None:
    setup = make_setup(check_in=("a",))
    setup.check_in("a", code="M2")
    setup.session.commit()

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert _code(response) == "CHECK_IN_INCOMPLETE"


def test_teams_pending(client: TestClient, setup: Setup) -> None:
    response = client.put(
        setup.game_url(1, code="M5"),
        json={"winner_side": "a"},
        headers=_headers(client, setup.organizer),
    )

    assert response.status_code == 409
    assert _code(response) == "MATCH_TEAMS_PENDING"


def test_voided_match_is_not_recordable(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _set_status(session, setup, MatchStatus.VOIDED)

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert response.status_code == 409
    assert _code(response) == "MATCH_NOT_RECORDABLE"


@pytest.mark.parametrize("who", ["captain_like", "outsider", "other_organizer"])
def test_not_scorer(
    client: TestClient, session: Session, setup: Setup, who: str
) -> None:
    account = make_account(session, organizer=(who == "other_organizer"))
    session.commit()

    response = _put(client, setup, 1, {"winner_side": "a"}, account=account)

    assert response.status_code == 403
    assert _code(response) == "SCORER_REQUIRED"
    assert _games(session, setup) == []


def _assign_referee(session: Session, setup: Setup) -> Account:
    referee = make_account(session)
    match = session.get(Match, setup.match_id())
    assert match is not None
    match.referee_account_id = referee.id
    session.add(match)
    session.commit()
    return referee


def test_assigned_referee_excludes_organizer(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _assign_referee(session, setup)

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert response.status_code == 403
    assert _code(response) == "SCORER_REQUIRED"
    state = client.get(
        f"{setup.base()}/score-entry", headers=_headers(client, setup.organizer)
    ).json()
    assert state["is_scorer"] is False


def test_assigned_referee_can_record_and_submit(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = _assign_referee(session, setup)
    headers = _headers(client, referee)

    assert (
        _put(client, setup, 1, {"winner_side": "b"}, headers=headers).status_code == 200
    )
    assert (
        _put(client, setup, 2, {"winner_side": "b"}, headers=headers).status_code == 200
    )
    response = client.post(f"{setup.base()}/submit", headers=headers)

    assert response.status_code == 200, response.text
    match = _match(session, setup)
    assert match.submitted_by == referee.id
    assert match.winner_id == setup.team("b")


def test_requires_login(client: TestClient, setup: Setup) -> None:
    assert client.get(f"{setup.base()}/score-entry").status_code == 401
    assert client.put(setup.game_url(1), json={"winner_side": "a"}).status_code == 401
    assert client.delete(setup.game_url(1)).status_code == 401
    assert client.post(f"{setup.base()}/submit").status_code == 401


@pytest.mark.parametrize(
    "status", [TournamentStatus.CANCELLED, TournamentStatus.FINISHED]
)
def test_tournament_not_accepting_scores(
    client: TestClient, session: Session, setup: Setup, status: TournamentStatus
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.commit()

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert response.status_code == 409
    assert _code(response) == "TOURNAMENT_NOT_ACCEPTING_SCORES"


def test_not_accepting_scores_is_checked_before_scorer(
    client: TestClient, session: Session, setup: Setup
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.CANCELLED
    session.add(row)
    outsider = make_account(session)
    session.commit()

    response = _put(client, setup, 1, {"winner_side": "a"}, account=outsider)

    assert _code(response) == "TOURNAMENT_NOT_ACCEPTING_SCORES"


def test_scorer_is_checked_before_match_state(
    client: TestClient, session: Session, make_setup: Factory
) -> None:
    setup = make_setup(check_in=())
    outsider = make_account(session)
    session.commit()

    response = _put(client, setup, 1, {"winner_side": "a"}, account=outsider)

    assert _code(response) == "SCORER_REQUIRED"


@pytest.mark.parametrize("wrong", ["other_tournament", "missing_match"])
def test_match_not_found(
    client: TestClient,
    session: Session,
    setup: Setup,
    fake_registration: FakeRegistration,
    wrong: str,
) -> None:
    headers = _headers(client, setup.organizer)
    if wrong == "other_tournament":
        other, _bracket = draw_with(session, fake_registration, 2)
        session.commit()
        base = setup.base(tournament_id=other.id)
    else:
        base = f"{API}/tournaments/{setup.tournament_id}/matches/{uuid.uuid4()}"

    responses = [
        client.get(f"{base}/score-entry", headers=headers),
        client.put(f"{base}/games/1", json={"winner_side": "a"}, headers=headers),
        client.delete(f"{base}/games/1", headers=headers),
        client.post(f"{base}/submit", headers=headers),
    ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert _code(response) == "MATCH_NOT_FOUND"


# ---------------------------------------------------------------- 送出


def test_submit_enters_appeal_window(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    headers = _record_sides(client, setup, "aa")
    frozen_clock.advance(timedelta(minutes=3))
    now = clock.now()

    response = client.post(f"{setup.base()}/submit", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reason"] == "result_submitted"
    assert body["submitted_by_name"] == setup.organizer.display_name
    match = _match(session, setup)
    assert match.status == MatchStatus.APPEAL_WINDOW
    assert match.outcome == "played"
    assert match.winner_id == setup.team("a")
    assert match.submitted_by == setup.organizer.id
    assert match.submitted_at == now
    assert match.appeal_deadline == now + APPEAL
    assert match.confirmed_at is None
    assert (match.wins_a, match.wins_b) == (2, 0)
    # 勝隊在申訴期滿前不晉級
    assert _match(session, setup, setup.next_code()).team_a_id is None
    assert _outbox(session, "MatchResultSubmitted") == [{"match_id": str(match.id)}]
    [record] = _audits(session, setup, "match.result_submitted")
    assert record.actor_id == setup.organizer.id
    assert record.before == {"status": "live"}
    assert record.after is not None
    assert record.after["status"] == "appeal_window"
    assert record.after["outcome"] == "played"
    assert record.after["winner_id"] == str(setup.team("a"))


def test_submit_before_decided(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "a")

    response = client.post(f"{setup.base()}/submit", headers=headers)

    assert response.status_code == 409
    assert _code(response) == "SERIES_NOT_DECIDED"
    assert response.json()["detail"]["message"] == "任一隊拿到 2 勝後才能送出。"
    assert _match(session, setup).status == MatchStatus.LIVE
    assert _outbox(session, "MatchResultSubmitted") == []


def test_submit_without_games(client: TestClient, setup: Setup) -> None:
    response = client.post(
        f"{setup.base()}/submit", headers=_headers(client, setup.organizer)
    )

    assert response.status_code == 409
    assert _code(response) == "SERIES_NOT_DECIDED"


@pytest.mark.parametrize("action", ["put", "delete", "submit"])
def test_after_submit_everything_is_locked(
    client: TestClient, session: Session, setup: Setup, action: str
) -> None:
    headers = _record_sides(client, setup, "aba")
    assert client.post(f"{setup.base()}/submit", headers=headers).status_code == 200
    before = _all_match_audits(session, setup)

    if action == "put":
        response = _put(client, setup, 1, {"winner_side": "b"}, headers=headers)
    elif action == "delete":
        response = client.delete(setup.game_url(3), headers=headers)
    else:
        response = client.post(f"{setup.base()}/submit", headers=headers)

    assert response.status_code == 409
    assert _code(response) == "RESULT_ALREADY_SUBMITTED"
    assert len(_games(session, setup)) == 3
    assert _all_match_audits(session, setup) == before
    assert len(_outbox(session, "MatchResultSubmitted")) == 1


@pytest.mark.parametrize("status", [MatchStatus.APPEALED, MatchStatus.CONFIRMED])
def test_appealed_or_confirmed_is_already_submitted(
    client: TestClient, session: Session, setup: Setup, status: MatchStatus
) -> None:
    _set_status(session, setup, status)

    response = _put(client, setup, 1, {"winner_side": "a"})

    assert _code(response) == "RESULT_ALREADY_SUBMITTED"


# ---------------------------------------------------------------- 讀取


@pytest.mark.parametrize(
    "status", [TournamentStatus.CANCELLED, TournamentStatus.FINISHED]
)
def test_read_when_tournament_not_accepting_scores(
    client: TestClient, session: Session, setup: Setup, status: TournamentStatus
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.commit()

    response = client.get(
        f"{setup.base()}/score-entry", headers=_headers(client, setup.organizer)
    )

    assert response.status_code == 200
    assert response.json()["is_scorer"] is True
    assert response.json()["reason"] == "not_accepting_scores"


def test_read_teams_pending(client: TestClient, setup: Setup) -> None:
    state = client.get(
        f"{setup.base('M5')}/score-entry", headers=_headers(client, setup.organizer)
    ).json()

    assert state["reason"] == "teams_pending"


def test_read_voided_match(client: TestClient, session: Session, setup: Setup) -> None:
    _set_status(session, setup, MatchStatus.VOIDED)

    state = client.get(
        f"{setup.base()}/score-entry", headers=_headers(client, setup.organizer)
    ).json()

    assert state["reason"] == "not_recordable"


@pytest.mark.parametrize("method", ["put", "delete"])
def test_game_no_zero_is_invalid(
    client: TestClient, session: Session, setup: Setup, method: str
) -> None:
    headers = _record_sides(client, setup, "a")

    if method == "put":
        response = _put(client, setup, 0, {"winner_side": "b"}, headers=headers)
    else:
        response = client.delete(setup.game_url(0), headers=headers)

    assert response.status_code == 409
    assert _code(response) == "INVALID_GAME_NO"
    assert _games(session, setup) == [(1, "a", None, None)]


def test_read_as_scorer_before_check_in(
    client: TestClient, make_setup: Factory
) -> None:
    setup = make_setup(check_in=("a",))

    state = client.get(
        f"{setup.base()}/score-entry", headers=_headers(client, setup.organizer)
    ).json()

    assert state["is_scorer"] is True
    assert state["reason"] == "check_in_incomplete"
    assert state["games"] == []
    assert state["series"]["wins_needed"] == 2
    assert state["submitted_by_name"] is None


def test_read_as_scorer_after_submit(client: TestClient, setup: Setup) -> None:
    headers = _record_sides(client, setup, "bab")
    client.post(f"{setup.base()}/submit", headers=headers)

    state = client.get(f"{setup.base()}/score-entry", headers=headers).json()

    assert state["is_scorer"] is True
    assert state["reason"] == "result_submitted"
    assert [g["game_no"] for g in state["games"]] == [1, 2, 3]
    assert state["series"] == {
        "wins_a": 1,
        "wins_b": 2,
        "winner": "b",
        "can_submit": True,
        "wins_needed": 2,
        "reason": None,
    }
    assert state["submitted_by_name"] == setup.organizer.display_name
    assert state["submitted_at"].startswith("2026-10-18T11:00:00")


def test_read_as_non_scorer_reveals_nothing(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "aa")
    client.post(f"{setup.base()}/submit", headers=headers)
    captain = make_account(session)
    session.commit()

    state = client.get(
        f"{setup.base()}/score-entry", headers=_headers(client, captain)
    ).json()

    assert state == {
        "is_scorer": False,
        "reason": None,
        "games": [],
        "series": None,
        "submitted_by_name": None,
        "submitted_at": None,
    }


def test_public_match_lists_games_without_recorder(
    client: TestClient, setup: Setup
) -> None:
    _record_sides(client, setup, "ba")

    response = client.get(setup.base())

    assert response.status_code == 200
    body = response.json()
    assert body["games"] == [
        {"game_no": 1, "winner_side": "b", "score_a": None, "score_b": None},
        {"game_no": 2, "winner_side": "a", "score_a": None, "score_b": None},
    ]
    assert (body["wins_a"], body["wins_b"]) == (1, 1)
    assert body["status"] == "live"
    assert "submitted_by" not in response.text
    assert "recorded_by" not in response.text


def test_public_match_hides_submitter(client: TestClient, setup: Setup) -> None:
    headers = _record_sides(client, setup, "aa")
    client.post(f"{setup.base()}/submit", headers=headers)

    response = client.get(setup.base())

    assert response.status_code == 200
    assert "submitted" not in response.text


# ---------------------------------------------------------------- 重複新增與加鎖順序


def test_adding_same_game_no_twice_becomes_overwrite(
    client: TestClient, session: Session, setup: Setup
) -> None:
    """先後兩次以第 2 局新增：第一次新增、第二次看到已有 2 局而變成覆寫（循序請求，不是併發測試）。"""
    headers = _record_sides(client, setup, "a")

    first = _put(client, setup, 2, {"winner_side": "b"}, headers=headers)
    second = _put(client, setup, 2, {"winner_side": "a"}, headers=headers)

    assert (first.status_code, second.status_code) == (200, 200)
    assert _games(session, setup) == [(1, "a", None, None), (2, "a", None, None)]
    session.expire_all()
    count = session.exec(
        select(func.count())
        .select_from(MatchGame)
        .where(MatchGame.match_id == setup.match_id(), MatchGame.game_no == 2)
    ).one()
    assert count == 1


@pytest.mark.parametrize("action", ["put", "delete", "submit"])
def test_match_is_locked_before_reading_state(
    session: Session,
    setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    """AD-6：鎖住場次之後才讀局與報到紀錄（同一連線無法製造真併發，改以呼叫順序驗證）。"""
    calls: list[str] = []
    real_lock = service.lock_match
    real_games = repository.list_games
    real_check_ins = repository.list_check_ins

    def lock_match(session: Session, *, match_id: uuid.UUID) -> Match:
        calls.append("lock")
        return real_lock(session, match_id=match_id)

    def list_games(session: Session, match_id: uuid.UUID) -> list[MatchGame]:
        calls.append("games")
        return real_games(session, match_id)

    def list_check_ins(session: Session, match_id: uuid.UUID) -> list[CheckIn]:
        calls.append("check_ins")
        return real_check_ins(session, match_id)

    monkeypatch.setattr(service, "lock_match", lock_match)
    monkeypatch.setattr(repository, "list_games", list_games)
    monkeypatch.setattr(repository, "list_check_ins", list_check_ins)
    kwargs = {
        "tournament_id": setup.tournament_id,
        "match_id": setup.match_id(),
        "account_id": setup.organizer.id,
    }
    if action == "put":
        service.record_game(session, game_no=1, data=_game_in("a"), **kwargs)
    elif action == "delete":
        service.record_game(session, game_no=1, data=_game_in("a"), **kwargs)
        calls.clear()
        service.delete_game(session, game_no=1, **kwargs)
    else:
        for no in (1, 2):
            service.record_game(session, game_no=no, data=_game_in("a"), **kwargs)
        calls.clear()
        service.submit_result(session, **kwargs)

    assert calls[0] == "lock"
    assert "check_ins" in calls


def _game_in(side: Literal["a", "b"]) -> GameScoreIn:
    return GameScoreIn(winner_side=side)


# ---------------------------------------------------------------- 拒絕時不改任何資料


def _snapshot(session: Session, setup: Setup) -> tuple[object, ...]:
    match = _match(session, setup)
    return (
        _games(session, setup),
        match.status,
        match.wins_a,
        match.wins_b,
        match.updated_at,
        _all_match_audits(session, setup),
        len(_outbox(session, "MatchResultSubmitted")),
    )


@pytest.mark.parametrize(
    ("method", "game_no", "body"),
    [
        ("put", 1, {"winner_side": "b"}),  # REDUNDANT_GAMES
        ("put", 4, {"winner_side": "a"}),  # SERIES_DECIDED
        ("put", 5, {"winner_side": "a"}),  # INVALID_GAME_NO
        ("put", 1, {"score_a": 1, "score_b": 0}),  # SCORE_INVALID
        ("delete", 1, None),  # NOT_LAST_GAME
        ("delete", 5, None),  # INVALID_GAME_NO
    ],
)
def test_rejections_change_nothing(
    client: TestClient,
    session: Session,
    setup: Setup,
    method: str,
    game_no: int,
    body: dict[str, Any] | None,
) -> None:
    headers = _record_sides(client, setup, "aba")
    before = _snapshot(session, setup)

    if method == "put":
        response = _put(client, setup, game_no, body or {}, headers=headers)
    else:
        response = client.delete(setup.game_url(game_no), headers=headers)

    assert response.status_code == 409
    assert _snapshot(session, setup) == before


def test_rejected_submit_changes_nothing(
    client: TestClient, session: Session, setup: Setup
) -> None:
    headers = _record_sides(client, setup, "ab")
    before = _snapshot(session, setup)

    response = client.post(f"{setup.base()}/submit", headers=headers)

    assert response.status_code == 409
    assert _snapshot(session, setup) == before
    assert _match(session, setup).submitted_by is None


# ---------------------------------------------------------------- 端對端（AC）


def test_record_submit_then_worker_confirms_and_advances(
    client: TestClient,
    session: Session,
    session_factory: Callable[[], Session],
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    headers = _record_sides(client, setup, "aba")
    assert client.post(f"{setup.base()}/submit", headers=headers).status_code == 200
    deadline = clock.now() + APPEAL

    match = _match(session, setup)
    assert match.status == MatchStatus.APPEAL_WINDOW
    assert (match.wins_a, match.wins_b) == (2, 1)
    assert match.winner_id == setup.team("a")
    public = client.get(setup.base()).json()
    assert [g["winner_side"] for g in public["games"]] == ["a", "b", "a"]

    frozen_clock.set(deadline - timedelta(seconds=1))
    run_once([jobs.confirm_expired_appeals], session_factory=session_factory)
    assert _match(session, setup).status == MatchStatus.APPEAL_WINDOW

    frozen_clock.set(deadline)
    run_once([jobs.confirm_expired_appeals], session_factory=session_factory)

    match = _match(session, setup)
    assert match.status == MatchStatus.CONFIRMED
    assert match.confirmed_at == deadline
    assert match.outcome == "played"
    next_match = _match(session, setup, setup.next_code())
    assert setup.team("a") in (next_match.team_a_id, next_match.team_b_id)
