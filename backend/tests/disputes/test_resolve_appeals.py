"""Story 6.2：主辦方處理申訴、S32 列表、S27 待處理、公開申訴結果、重賽時間範圍。

沿用 test_score_entry 的已抽籤 8 隊賽事（賽程已公布、BO3、win_loss）；申訴直接寫入
資料表，場次直接寫成申訴中。frozen_clock 凍結在 2026-10-18 11:00 UTC。
"""

# ruff: noqa: F811  (從 test_score_entry 匯入 fixture，參數同名是 pytest 的用法)

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core import audit, clock
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition.models import (
    Match,
    MatchGame,
    MatchOutcome,
    MatchStatus,
)
from app.modules.disputes import service
from app.modules.disputes.models import Appeal, AppealStatus
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
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
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

REPLAY_AT = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _team_names(
    fake_registration: FakeRegistration, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S32 的隊名由 registration `get_team_names` 查：改用假的 registration 的隊名。"""
    monkeypatch.setattr(
        registration_service, "get_team_names", fake_registration.get_team_names
    )


def _row(session: Session, setup: Setup, code: str = "M1") -> Match:
    session.expire_all()
    match = session.get(Match, setup.match_id(code))
    assert match is not None
    return match


def _appealed(
    session: Session,
    setup: Setup,
    *,
    code: str = "M1",
    outcome: MatchOutcome = MatchOutcome.PLAYED,
    sides: str = "aa",
    teams: str = "ab",
    deadline: timedelta = timedelta(minutes=30),
) -> list[Appeal]:
    """場次寫成申訴中（played 時依 `sides` 寫入各局、勝隊 a），`teams` 的每一隊各一筆申訴。"""
    match = _row(session, setup, code)
    now = clock.now()
    winner = "a"
    if outcome == MatchOutcome.PLAYED:
        for no, side in enumerate(sides, start=1):
            session.add(
                MatchGame(
                    match_id=match.id,
                    game_no=no,
                    winner_side=side,
                    recorded_by=setup.organizer.id,
                    recorded_at=now,
                )
            )
        match.wins_a = sides.count("a")
        match.wins_b = sides.count("b")
    match.status = MatchStatus.APPEALED
    match.outcome = outcome
    match.winner_id = setup.team(winner, code)
    match.appeal_deadline = now + deadline
    session.add(match)
    appeals = []
    for i, side in enumerate(teams):
        appeal = Appeal(
            tournament_id=setup.tournament_id,
            match_id=match.id,
            team_id=setup.team(side, code),
            filed_by=make_account(session).id,
            filed_at=now + timedelta(minutes=i),
            description=f"{side} 隊的申訴",
            status=AppealStatus.OPEN,
        )
        session.add(appeal)
        appeals.append(appeal)
    session.commit()
    return appeals


def _seat(session: Session, setup: Setup, code: str) -> None:
    """把 M1 的兩隊放進 `code` 那一場（準決賽、季軍賽要有隊伍才能申訴）。"""
    row = _row(session, setup, code)
    row.team_a_id, row.team_b_id = setup.team("a"), setup.team("b")
    session.add(row)
    session.commit()
    setup.matches[code] = setup.matches[code].model_copy(
        update={"team_a_id": row.team_a_id, "team_b_id": row.team_b_id}
    )


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _resolve_url(setup: Setup, code: str = "M1") -> str:
    return (
        f"{API}/organizer/tournaments/{setup.tournament_id}"
        f"/matches/{setup.match_id(code)}/appeal-resolution"
    )


def _resolve(
    client: TestClient,
    setup: Setup,
    body: dict[str, Any],
    *,
    account: Account | None = None,
    code: str = "M1",
) -> Any:
    return client.post(
        _resolve_url(setup, code),
        json=body,
        headers=_headers(client, account or setup.organizer),
    )


def _code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def _appeals(session: Session, setup: Setup, code: str = "M1") -> list[Appeal]:
    session.expire_all()
    statement = (
        select(Appeal)
        .where(Appeal.match_id == setup.match_id(code))
        .order_by(col(Appeal.filed_at))
    )
    return list(session.exec(statement))


def _resolved_records(session: Session, setup: Setup) -> list[audit.AuditLogRead]:
    return [
        r
        for r in audit.list_for_tournament(session, setup.tournament_id)
        if r.action == "appeal.resolved"
    ]


def _resolved_events(session: Session, setup: Setup, code: str = "M1") -> list[Any]:
    statement = select(OutboxEvent).where(OutboxEvent.type == "AppealResolved")
    return [
        e.payload
        for e in session.exec(statement)
        if e.payload["match_id"] == str(setup.match_id(code))
    ]


def _next_teams(session: Session, setup: Setup, code: str = "M1") -> set[object]:
    nxt = _row(session, setup, setup.next_code(code))
    return {nxt.team_a_id, nxt.team_b_id} - {None}


def _public_result(client: TestClient, setup: Setup, code: str = "M1") -> Any:
    return client.get(
        f"{API}/tournaments/{setup.tournament_id}"
        f"/matches/{setup.match_id(code)}/appeal-result"
    )


# ---------------------------------------------------------------- 維持


def test_uphold_closes_all_open_appeals_and_advances(
    client: TestClient, session: Session, setup: Setup
) -> None:
    filed = _appealed(session, setup)
    filed_by = [a.filed_by for a in filed]

    response = _resolve(client, setup, {"decision": "upheld", "reason": "  證據不足  "})

    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    appeals = _appeals(session, setup)
    assert [a.status for a in appeals] == [AppealStatus.CLOSED] * 2
    assert {a.decision for a in appeals} == {"upheld"}
    assert {a.reason for a in appeals} == {"證據不足"}
    assert {a.handled_by for a in appeals} == {setup.organizer.id}
    assert {a.handled_at for a in appeals} == {clock.now()}
    assert [a.filed_by for a in appeals] == filed_by
    match = _row(session, setup)
    assert match.status == MatchStatus.CONFIRMED
    assert setup.team("a") in _next_teams(session, setup)
    records = _resolved_records(session, setup)
    assert len(records) == 1
    assert records[0].after is not None
    assert records[0].after["decision"] == "upheld"
    assert len(records[0].after["appeal_ids"]) == 2
    assert _resolved_events(session, setup) == [
        {"match_id": str(match.id), "decision": "upheld"}
    ]
    assert _public_result(client, setup).json() == {"decision": "upheld"}


# ---------------------------------------------------------------- 更正


def test_correct_flips_winner_and_records_games(
    client: TestClient, session: Session, setup: Setup
) -> None:
    """AC：兩隊都申訴的場次更正後兩筆同時結案、submitted_by 不變、下一場出現新勝隊。"""
    filed = _appealed(session, setup, sides="aa")
    # 送出結果的是裁判（不是處理申訴的主辦方）：處理時改寫成主辦方會讓這個測試失敗
    referee = make_account(session)
    match = _row(session, setup)
    match.submitted_by = referee.id
    session.add(match)
    session.commit()
    filed_by = [a.filed_by for a in filed]

    response = _resolve(
        client,
        setup,
        {
            "decision": "corrected",
            "reason": "第二局比分登錄錯誤",
            "games": [
                {"winner_side": "a"},
                {"winner_side": "b"},
                {"winner_side": "b"},
            ],
        },
    )

    assert response.status_code == 200, response.text
    appeals = _appeals(session, setup)
    assert {a.decision for a in appeals} == {"corrected"}
    assert {a.status for a in appeals} == {AppealStatus.CLOSED}
    assert [a.filed_by for a in appeals] == filed_by
    match = _row(session, setup)
    assert match.submitted_by == referee.id
    assert match.status == MatchStatus.CONFIRMED
    assert match.winner_id == setup.team("b")
    teams = _next_teams(session, setup)
    assert setup.team("b") in teams and setup.team("a") not in teams
    record = _resolved_records(session, setup)[0]
    assert record.before is not None and record.after is not None
    assert [g["winner_side"] for g in record.before["games"]] == ["a", "a"]
    assert [g["winner_side"] for g in record.after["games"]] == ["a", "b", "b"]
    assert record.after["winner_id"] == str(setup.team("b"))
    assert _public_result(client, setup).json() == {"decision": "corrected"}


@pytest.mark.parametrize(
    ("sides", "code"), [("a", "SERIES_NOT_DECIDED"), ("bba", "REDUNDANT_GAMES")]
)
def test_correct_rejections_keep_appeals_open(
    client: TestClient, session: Session, setup: Setup, sides: str, code: str
) -> None:
    _appealed(session, setup)

    response = _resolve(
        client,
        setup,
        {
            "decision": "corrected",
            "reason": "更正",
            "games": [{"winner_side": s} for s in sides],
        },
    )

    assert response.status_code == 409
    assert _code(response) == code
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}
    assert _row(session, setup).status == MatchStatus.APPEALED
    assert _resolved_records(session, setup) == []
    assert _resolved_events(session, setup) == []


def test_correct_without_games_is_422(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup)

    response = _resolve(client, setup, {"decision": "corrected", "reason": "更正"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "games"]


def test_correct_with_more_than_seven_games_is_422(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup)

    response = _resolve(
        client,
        setup,
        {
            "decision": "corrected",
            "reason": "更正",
            "games": [{"winner_side": "a"}] * 8,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "games"]
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


# ---------------------------------------------------------------- 重新比賽


def test_rematch_on_forfeit_reschedules(
    client: TestClient, session: Session, make_setup: Factory
) -> None:
    setup = make_setup(check_in=("a",))
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT, teams="b")

    window = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}"
        f"/matches/{setup.match_id()}/replay-window",
        headers=_headers(client, setup.organizer),
    )
    assert window.status_code == 200
    assert window.json()["can_reschedule"] is True

    response = _resolve(
        client,
        setup,
        {
            "decision": "rematch",
            "reason": "對方網路斷線，重新比賽",
            "replay_at": REPLAY_AT.isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["decision"] == "rematch"
    match = _row(session, setup)
    assert match.status == MatchStatus.SCHEDULED
    assert match.outcome is None
    assert match.scheduled_at == REPLAY_AT
    assert match.forfeit_deadline == REPLAY_AT + timedelta(minutes=15)
    record = _resolved_records(session, setup)[0]
    assert record.after is not None
    assert record.after["scheduled_at"].startswith("2026-10-20T10:00")
    # 重新比賽後不是已確認：公開結果為 null
    assert _public_result(client, setup).json() == {"decision": None}


def test_rematch_without_replay_at_is_422(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT)

    response = _resolve(client, setup, {"decision": "rematch", "reason": "重賽"})

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["type"] == "APPEAL_REPLAY_AT_REQUIRED"
    assert detail["loc"] == ["body", "replay_at"]
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


def test_rematch_naive_replay_at_is_422(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT)

    response = _resolve(
        client,
        setup,
        {"decision": "rematch", "reason": "重賽", "replay_at": "2026-10-20T10:00:00"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "replay_at"]
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}
    assert _row(session, setup).status == MatchStatus.APPEALED


def test_public_result_after_rematch_stays_null_when_replay_confirmed(
    client: TestClient, session: Session, make_setup: Factory
) -> None:
    """最後一次處理是重新比賽：重賽打完確認後，公開結果仍為 null。"""
    setup = make_setup(check_in=("a",))
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT, teams="b")
    response = _resolve(
        client,
        setup,
        {"decision": "rematch", "reason": "重賽", "replay_at": REPLAY_AT.isoformat()},
    )
    assert response.status_code == 200, response.text
    # 重賽打完並確認（直接寫入）
    match = _row(session, setup)
    match.status = MatchStatus.CONFIRMED
    match.outcome = MatchOutcome.PLAYED
    match.winner_id = setup.team("a")
    session.add(match)
    session.commit()

    assert _public_result(client, setup).json() == {"decision": None}


def test_rematch_on_played_is_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup)

    response = _resolve(
        client,
        setup,
        {"decision": "rematch", "reason": "重賽", "replay_at": REPLAY_AT.isoformat()},
    )

    assert response.status_code == 409
    assert _code(response) == "REPLAY_ONLY_FOR_FORFEIT"
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


def test_rematch_bad_time_uses_reschedule_errors(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup, outcome=MatchOutcome.FORFEIT)

    response = _resolve(
        client,
        setup,
        {
            "decision": "rematch",
            "reason": "重賽",
            "replay_at": (clock.now() - timedelta(hours=1)).isoformat(),
        },
    )

    assert response.status_code == 409
    assert _code(response) == "RESCHEDULE_BEFORE_NOW"
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


# ---------------------------------------------------------------- 其他情況


def test_other_team_cannot_appeal_after_early_resolution(
    client: TestClient,
    session: Session,
    setup: Setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """另一隊申訴期限未到時也能處理；處理後另一隊不能再申訴。"""
    _appealed(session, setup, teams="a", deadline=timedelta(hours=1))
    captain_b = make_account(session)
    session.commit()

    def is_captain(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        return team_id == setup.team("b") and account_id == captain_b.id

    monkeypatch.setattr(registration_service, "is_captain", is_captain)

    response = _resolve(client, setup, {"decision": "upheld", "reason": "維持"})
    assert response.status_code == 200, response.text

    with pytest.raises(BusinessError) as excinfo:
        service.file_appeal(
            session,
            tournament_id=setup.tournament_id,
            match_id=setup.match_id(),
            account_id=captain_b.id,
            description="我們也要申訴",
            attachment=None,
            content_type=None,
        )
    assert excinfo.value.code == "APPEAL_NOT_ALLOWED"


def test_no_open_appeals_is_409(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup)
    assert (
        _resolve(client, setup, {"decision": "upheld", "reason": "維持"}).status_code
        == 200
    )

    response = _resolve(client, setup, {"decision": "upheld", "reason": "再一次"})

    assert response.status_code == 409
    assert _code(response) == "NO_OPEN_APPEALS"
    assert len(_resolved_records(session, setup)) == 1


def test_routes_reject_match_of_other_tournament(
    client: TestClient, session: Session, setup: Setup, make_setup: Factory
) -> None:
    """處理與重賽時間範圍：場次不屬於路徑上的賽事時 404，另一場的申訴不受影響。"""
    other = make_setup()
    _appealed(session, other, outcome=MatchOutcome.FORFEIT)
    headers = _headers(client, setup.organizer)
    base = (
        f"{API}/organizer/tournaments/{setup.tournament_id}/matches/{other.match_id()}"
    )

    responses = [
        client.post(
            f"{base}/appeal-resolution",
            json={"decision": "upheld", "reason": "維持"},
            headers=headers,
        ),
        client.get(f"{base}/replay-window", headers=headers),
    ]

    for response in responses:
        assert response.status_code == 404
        assert _code(response) == "MATCH_NOT_FOUND"
    assert {a.status for a in _appeals(session, other)} == {AppealStatus.OPEN}
    assert _row(session, other).status == MatchStatus.APPEALED


def test_non_owner_is_403(client: TestClient, session: Session, setup: Setup) -> None:
    _appealed(session, setup)
    other = make_account(session, organizer=True)
    session.commit()
    headers = _headers(client, other)
    base = f"{API}/organizer/tournaments/{setup.tournament_id}"

    responses = [
        _resolve(
            client, setup, {"decision": "upheld", "reason": "維持"}, account=other
        ),
        client.get(f"{base}/appeals", headers=headers),
        client.get(f"{base}/open-disputes", headers=headers),
        client.get(f"{base}/matches/{setup.match_id()}/replay-window", headers=headers),
    ]

    for response in responses:
        assert response.status_code == 403
        assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("  ", "APPEAL_REASON_REQUIRED"),
        ("", "APPEAL_REASON_REQUIRED"),
        ("x" * 1001, "APPEAL_REASON_TOO_LONG"),
    ],
)
def test_reason_is_required(
    client: TestClient, session: Session, setup: Setup, reason: str, code: str
) -> None:
    _appealed(session, setup)

    response = _resolve(client, setup, {"decision": "upheld", "reason": reason})

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "reason"]
    assert detail["type"] == code
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}


def test_disqualified_decision_is_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    """`disqualified` 只用於檢舉屬實時一併結案，主辦方不能直接選（6.5）。"""
    _appealed(session, setup)
    match_before = _row(session, setup)
    before = (match_before.status, match_before.outcome, match_before.winner_id)

    response = _resolve(
        client,
        setup,
        {
            "decision": "disqualified",
            "reason": "取消資格",
            "replay_at": REPLAY_AT.isoformat(),
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert (detail["type"], detail["loc"]) == (
        "APPEAL_DECISION_INVALID",
        ["body", "decision"],
    )
    assert {a.status for a in _appeals(session, setup)} == {AppealStatus.OPEN}
    row = _row(session, setup)
    assert (row.status, row.outcome, row.winner_id) == before
    assert _resolved_records(session, setup) == []
    assert _resolved_events(session, setup) == []


def test_public_result_is_null_before_handling_and_404_elsewhere(
    client: TestClient, session: Session, setup: Setup, make_setup: Factory
) -> None:
    _appealed(session, setup)
    other = make_setup()

    assert _public_result(client, setup).json() == {"decision": None}
    response = client.get(
        f"{API}/tournaments/{other.tournament_id}"
        f"/matches/{setup.match_id()}/appeal-result"
    )
    assert response.status_code == 404
    assert _code(response) == "MATCH_NOT_FOUND"


def test_public_result_for_confirmed_match_without_appeals_is_null(
    client: TestClient, session: Session, setup: Setup
) -> None:
    match = _row(session, setup)
    match.status = MatchStatus.CONFIRMED
    session.add(match)
    session.commit()

    response = _public_result(client, setup)

    assert response.status_code == 200
    assert response.json() == {"decision": None}


# ---------------------------------------------------------------- S32 列表、S27 待處理


def test_list_groups_by_match_with_open_first(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup, code="M1")
    _appealed(session, setup, code="M2", teams="b")
    assert (
        _resolve(client, setup, {"decision": "upheld", "reason": "維持"}).status_code
        == 200
    )

    response = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}/appeals",
        headers=_headers(client, setup.organizer),
    )

    assert response.status_code == 200
    groups = response.json()
    assert [g["match_code"] for g in groups] == ["M2", "M1"]
    assert [g["has_open"] for g in groups] == [True, False]
    m1 = groups[1]
    assert len(m1["appeals"]) == 2
    assert {a["team_name"] for a in m1["appeals"]} == {
        m1["team_a"]["name"],
        m1["team_b"]["name"],
    }
    assert m1["best_of"] == 3
    assert m1["score_type"] == "win_loss"
    assert "attachment_key" not in m1["appeals"][0]


def test_list_shows_original_appellant_name_after_replacement(
    client: TestClient, session: Session, setup: Setup
) -> None:
    """場次的隊伍被頂替（6.5）後，原申訴隊仍顯示自己的隊名（依 appeal.team_id 查）。"""
    _appealed(session, setup, teams="b")
    original = setup.team("b")
    expected = setup.fake.get_team_names(session, team_ids=[original])[original]
    replacement = uuid.uuid4()
    setup.fake.teams.append(replacement)
    match = _row(session, setup)
    match.team_b_id = replacement
    session.add(match)
    session.commit()

    response = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}/appeals",
        headers=_headers(client, setup.organizer),
    )

    assert response.status_code == 200
    group = response.json()[0]
    assert group["team_b"]["id"] == str(replacement)
    assert group["appeals"][0]["team_name"] == expected
    assert group["team_b"]["name"] != expected


def test_open_disputes_sorted_by_handling_deadline(
    client: TestClient, session: Session, setup: Setup
) -> None:
    """AC：一場有下一場、一場是決賽；待處理數為 2，依處理期限由近到遠。"""
    _appealed(session, setup, code="M1", teams="a")
    final_code = setup.next_code(setup.next_code("M1"))
    final = _row(session, setup, final_code)
    final.team_a_id, final.team_b_id = setup.team("a"), setup.team("b")
    session.add(final)
    session.commit()
    setup.matches[final_code] = setup.matches[final_code].model_copy(
        update={"team_a_id": final.team_a_id, "team_b_id": final.team_b_id}
    )
    _appealed(session, setup, code=final_code, teams="b", sides="aa")

    response = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}/open-disputes",
        headers=_headers(client, setup.organizer),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["appeals"] == 2
    assert body["reports"] == 0
    assert [i["match_code"] for i in body["items"]] == [final_code, "M1"]
    final_deadline = datetime.fromisoformat(body["items"][0]["deadline"])
    assert final_deadline == clock.now() + timedelta(hours=1)
    m1_next = _row(session, setup, setup.next_code("M1"))
    assert datetime.fromisoformat(body["items"][1]["deadline"]) == m1_next.scheduled_at
    assert datetime.fromisoformat(body["earliest_deadline"]) == final_deadline
    assert {i["kind"] for i in body["items"]} == {"appeal"}


def _open_disputes(client: TestClient, setup: Setup) -> Any:
    response = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}/open-disputes",
        headers=_headers(client, setup.organizer),
    )
    assert response.status_code == 200
    return response.json()


def _set_time(session: Session, setup: Setup, code: str, at: datetime) -> None:
    row = _row(session, setup, code)
    row.scheduled_at = at
    session.add(row)
    session.commit()


def _third_place_code(setup: Setup) -> str:
    return next(code for code, m in setup.matches.items() if m.is_third_place)


@pytest.mark.parametrize("earlier", ["final", "third_place"])
def test_semifinal_deadline_is_earlier_of_final_and_third_place(
    client: TestClient, session: Session, setup: Setup, earlier: str
) -> None:
    """準決賽同時等決賽（勝隊）與季軍賽（敗隊，`loser_next_match_id`）：取較早者。"""
    semi = setup.next_code("M1")
    final = setup.next_code(semi)
    third = _third_place_code(setup)
    _seat(session, setup, semi)
    _appealed(session, setup, code=semi, teams="a")
    soon = clock.now() + timedelta(hours=2)
    later = clock.now() + timedelta(hours=3)
    _set_time(session, setup, final, soon if earlier == "final" else later)
    _set_time(session, setup, third, soon if earlier == "third_place" else later)

    body = _open_disputes(client, setup)

    assert [i["match_code"] for i in body["items"]] == [semi]
    assert datetime.fromisoformat(body["items"][0]["deadline"]) == soon


def test_third_place_deadline_is_one_hour_after_filing(
    client: TestClient, session: Session, setup: Setup
) -> None:
    third = _third_place_code(setup)
    _seat(session, setup, third)
    (appeal,) = _appealed(session, setup, code=third, teams="b")
    filed_at = appeal.filed_at

    body = _open_disputes(client, setup)

    assert [i["match_code"] for i in body["items"]] == [third]
    deadline = datetime.fromisoformat(body["items"][0]["deadline"])
    assert deadline == filed_at + timedelta(hours=1)


def test_open_disputes_excludes_closed_appeals(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _appealed(session, setup, code="M1")
    assert (
        _resolve(client, setup, {"decision": "upheld", "reason": "維持"}).status_code
        == 200
    )
    _appealed(session, setup, code="M2", teams="b")

    body = _open_disputes(client, setup)

    assert body["appeals"] == 1
    assert [i["match_code"] for i in body["items"]] == ["M2"]


def test_open_disputes_empty(client: TestClient, setup: Setup) -> None:
    response = client.get(
        f"{API}/organizer/tournaments/{setup.tournament_id}/open-disputes",
        headers=_headers(client, setup.organizer),
    )

    assert response.json() == {
        "appeals": 0,
        "reports": 0,
        "earliest_deadline": None,
        "items": [],
    }
