"""Story 4.4：指派／收回場次裁判、S30 列表的可選裁判、晉級後衝突自動收回。

8 隊抽籤後第一輪 M1～M4 兩隊都已確定、M5～M8 待定；frozen_clock 凍結在 2026-10-18 11:00 UTC。
registration 的 `is_member` 以 `members` 集合替身（隊伍 id、帳號 id）控制。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core import audit, clock
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, service
from app.modules.competition.models import CheckIn, Match, MatchOutcome, MatchStatus
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, draw_with
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

# fixture 換掉替身前的真正轉接函式
_REAL_IS_MEMBER = registration_port.is_member

ACTIONS = ("match.referee_assigned", "match.referee_unassigned")
EVENTS = ("RefereeAssigned", "RefereeUnassigned")


class Setup:
    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        self.tournament, bracket = draw_with(session, fake, 8)
        self.tournament_id = self.tournament.id
        self.matches = {m.code: m for m in bracket.matches}
        organizer = session.get(Account, self.tournament.organizer_id)
        assert organizer is not None
        self.organizer = organizer
        self.session = session
        self.members: set[tuple[uuid.UUID, uuid.UUID]] = set()

    def referee(self) -> Account:
        """建立一位已接受此賽事邀請的裁判。"""
        account = make_account(self.session)
        invitation = tournaments_service.invite_referee(
            self.session,
            tournament_id=self.tournament_id,
            actor_id=self.organizer.id,
        )
        tournaments_service.accept_invitation(
            self.session, token=invitation.token, account_id=account.id
        )
        self.session.commit()
        return account

    def url(self, code: str, tournament_id: uuid.UUID | None = None) -> str:
        return (
            f"{API}/tournaments/{tournament_id or self.tournament_id}"
            f"/matches/{self.matches[code].id}/referee"
        )

    def row(self, code: str) -> Match:
        self.session.expire_all()
        row = self.session.get(Match, self.matches[code].id)
        assert row is not None
        return row

    def team(self, code: str, side: str) -> uuid.UUID:
        match = self.matches[code]
        team = match.team_a_id if side == "a" else match.team_b_id
        assert team is not None
        return team


@pytest.fixture
def setup(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> Setup:
    result = Setup(session, fake_registration)

    def is_member(_session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID):
        return (team_id, account_id) in result.members

    monkeypatch.setattr(registration_port, "is_member", is_member)
    session.commit()
    return result


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _put(client: TestClient, s: Setup, code: str, referee: Account, **kw: Any) -> Any:
    headers = kw.pop("headers", None) or _headers(client, s.organizer)
    return client.put(
        s.url(code, **kw), json={"account_id": str(referee.id)}, headers=headers
    )


def _delete(client: TestClient, s: Setup, code: str, **kw: Any) -> Any:
    headers = kw.pop("headers", None) or _headers(client, s.organizer)
    return client.delete(s.url(code, **kw), headers=headers)


def _code(response: Any) -> str:
    return response.json()["detail"]["code"]


def _counts(session: Session) -> tuple[int, int]:
    session.expire_all()
    logs = session.exec(
        select(func.count())
        .select_from(audit.AuditLog)
        .where(audit.AuditLog.action.in_(ACTIONS))  # type: ignore[attr-defined]
    ).one()
    events = session.exec(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.type.in_(EVENTS))  # type: ignore[attr-defined]
    ).one()
    return logs, events


def _logs(session: Session, action: str) -> list[audit.AuditLog]:
    return list(
        session.exec(select(audit.AuditLog).where(audit.AuditLog.action == action))
    )


def _events(session: Session, type_: str) -> list[dict[str, Any]]:
    rows = session.exec(select(OutboxEvent).where(OutboxEvent.type == type_)).all()
    return [row.payload for row in rows]


def test_assign(client: TestClient, session: Session, setup: Setup) -> None:
    referee = setup.referee()

    response = _put(client, setup, "M1", referee)

    assert response.status_code == 200
    assert response.json()["referee_account_id"] == str(referee.id)
    assert setup.row("M1").referee_account_id == referee.id
    (log,) = _logs(session, "match.referee_assigned")
    assert log.actor_id == setup.organizer.id
    assert log.before == {"referee_account_id": None}
    assert log.after == {"referee_account_id": str(referee.id)}
    assert _events(session, "RefereeAssigned") == [
        {"match_id": str(setup.matches["M1"].id), "referee_account_id": str(referee.id)}
    ]
    assert _events(session, "RefereeUnassigned") == []


def test_reassign_emits_both_events(
    client: TestClient, session: Session, setup: Setup
) -> None:
    first, second = setup.referee(), setup.referee()
    _put(client, setup, "M1", first)

    response = _put(client, setup, "M1", second)

    assert response.status_code == 200
    assert setup.row("M1").referee_account_id == second.id
    assigned = _logs(session, "match.referee_assigned")
    assert len(assigned) == 2
    assert _logs(session, "match.referee_unassigned") == []
    assert assigned[-1].before == {"referee_account_id": str(first.id)}
    assert [e["referee_account_id"] for e in _events(session, "RefereeUnassigned")] == [
        str(first.id)
    ]
    assert len(_events(session, "RefereeAssigned")) == 2


def test_one_referee_many_matches(client: TestClient, setup: Setup) -> None:
    referee = setup.referee()
    assert _put(client, setup, "M1", referee).status_code == 200
    assert _put(client, setup, "M2", referee).status_code == 200


def test_unassign_returns_scoring_to_organizer(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    _put(client, setup, "M1", referee)
    base = f"{API}/tournaments/{setup.tournament_id}/matches/{setup.matches['M1'].id}"

    def scorer(account: Account) -> bool:
        return client.get(
            f"{base}/score-entry", headers=_headers(client, account)
        ).json()["is_scorer"]

    assert scorer(referee) is True
    assert scorer(setup.organizer) is False

    response = _delete(client, setup, "M1")

    assert response.status_code == 200
    assert response.json()["referee_account_id"] is None
    assert scorer(referee) is False
    assert scorer(setup.organizer) is True
    (log,) = _logs(session, "match.referee_unassigned")
    assert log.before == {"referee_account_id": str(referee.id)}
    assert log.after == {"referee_account_id": None}
    assert [e["referee_account_id"] for e in _events(session, "RefereeUnassigned")] == [
        str(referee.id)
    ]


def test_unassign_keeps_recorded_games(
    client: TestClient, session: Session, setup: Setup
) -> None:
    for side in ("a", "b"):
        session.add(
            CheckIn(
                match_id=setup.matches["M1"].id,
                team_id=setup.team("M1", side),
                account_id=make_account(session).id,
                at=clock.now(),
            )
        )
    session.commit()
    referee = setup.referee()
    _put(client, setup, "M1", referee)
    base = f"{API}/tournaments/{setup.tournament_id}/matches/{setup.matches['M1'].id}"
    put = client.put(
        f"{base}/games/1",
        json={"winner_side": "a"},
        headers=_headers(client, referee),
    )
    assert put.status_code == 200

    _delete(client, setup, "M1")

    state = client.get(
        f"{base}/score-entry", headers=_headers(client, setup.organizer)
    ).json()
    assert state["is_scorer"] is True
    assert [g["winner_side"] for g in state["games"]] == ["a"]


def test_noop_writes_nothing(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    assert _delete(client, setup, "M1").status_code == 200  # 沒有裁判
    assert _counts(session) == (0, 0)
    _put(client, setup, "M1", referee)
    before = _counts(session)
    updated = setup.row("M1").updated_at

    assert _put(client, setup, "M1", referee).status_code == 200  # 同一人

    assert _counts(session) == before
    assert setup.row("M1").updated_at == updated


def test_not_a_referee(client: TestClient, session: Session, setup: Setup) -> None:
    outsider = make_account(session)
    session.commit()

    for who in (outsider, setup.organizer):
        response = _put(client, setup, "M1", who)
        assert response.status_code == 409
        assert _code(response) == "NOT_TOURNAMENT_REFEREE"
    assert setup.row("M1").referee_account_id is None
    assert _counts(session) == (0, 0)


def test_team_member_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    other = setup.referee()
    setup.members.add((setup.team("M1", "b"), referee.id))
    _put(client, setup, "M1", other)
    before = _counts(session)

    response = _put(client, setup, "M1", referee)

    assert response.status_code == 409
    assert _code(response) == "REFEREE_IS_TEAM_MEMBER"
    assert setup.row("M1").referee_account_id == other.id
    assert _counts(session) == before


def test_pending_side_not_checked(client: TestClient, setup: Setup) -> None:
    referee = setup.referee()
    assert _put(client, setup, "M5", referee).status_code == 200


@pytest.mark.parametrize(
    "status",
    [
        MatchStatus.APPEAL_WINDOW,
        MatchStatus.APPEALED,
        MatchStatus.CONFIRMED,
        MatchStatus.VOIDED,
    ],
)
def test_submitted_match_locked(
    client: TestClient, session: Session, setup: Setup, status: MatchStatus
) -> None:
    referee = setup.referee()
    row = setup.row("M1")
    row.status = status
    session.add(row)
    session.commit()

    for response in (_put(client, setup, "M1", referee), _delete(client, setup, "M1")):
        assert response.status_code == 409
        assert _code(response) == "MATCH_REFEREE_LOCKED"
    assert setup.row("M1").referee_account_id is None
    assert _counts(session) == (0, 0)


def test_live_match_allowed(client: TestClient, session: Session, setup: Setup) -> None:
    referee = setup.referee()
    row = setup.row("M1")
    row.status = MatchStatus.LIVE
    session.add(row)
    session.commit()

    assert _put(client, setup, "M1", referee).status_code == 200


@pytest.mark.parametrize(
    "status", [TournamentStatus.FINISHED, TournamentStatus.CANCELLED]
)
def test_tournament_not_assignable(
    client: TestClient, session: Session, setup: Setup, status: TournamentStatus
) -> None:
    referee = setup.referee()
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.commit()

    for response in (_put(client, setup, "M1", referee), _delete(client, setup, "M1")):
        assert response.status_code == 409
        assert _code(response) == "TOURNAMENT_NOT_ASSIGNABLE"
    assert _counts(session) == (0, 0)


def test_other_organizer_forbidden(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    other = make_account(session, organizer=True)
    session.commit()
    headers = _headers(client, other)

    for response in (
        _put(client, setup, "M1", referee, headers=headers),
        _delete(client, setup, "M1", headers=headers),
    ):
        assert response.status_code == 403
        assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert _counts(session) == (0, 0)


def test_non_organizer_account_forbidden(client: TestClient, setup: Setup) -> None:
    referee = setup.referee()
    response = _put(client, setup, "M1", referee, headers=_headers(client, referee))
    assert response.status_code == 403
    assert _code(response) == "ORGANIZER_REQUIRED"


def test_not_found(client: TestClient, setup: Setup) -> None:
    referee = setup.referee()
    missing = uuid.uuid4()

    response = _put(client, setup, "M1", referee, tournament_id=missing)
    assert (response.status_code, _code(response)) == (404, "TOURNAMENT_NOT_FOUND")

    bad = client.put(
        f"{API}/tournaments/{setup.tournament_id}/matches/{missing}/referee",
        json={"account_id": str(referee.id)},
        headers=_headers(client, setup.organizer),
    )
    assert (bad.status_code, _code(bad)) == (404, "MATCH_NOT_FOUND")


def test_match_of_other_tournament_not_found(
    client: TestClient,
    session: Session,
    setup: Setup,
    fake_registration: FakeRegistration,
) -> None:
    referee = setup.referee()
    other_tournament, other_bracket = draw_with(session, fake_registration, 4)
    session.commit()
    organizer = session.get(Account, other_tournament.organizer_id)
    assert organizer is not None

    response = client.put(
        f"{API}/tournaments/{other_tournament.id}/matches/{setup.matches['M1'].id}/referee",
        json={"account_id": str(referee.id)},
        headers=_headers(client, organizer),
    )

    assert (response.status_code, _code(response)) == (404, "MATCH_NOT_FOUND")


def test_list_assignable_matches_assign_api(
    client: TestClient, session: Session, setup: Setup
) -> None:
    free, member = setup.referee(), setup.referee()
    setup.members.add((setup.team("M1", "a"), member.id))
    headers = _headers(client, setup.organizer)

    rows = client.get(
        f"{API}/tournaments/{setup.tournament_id}/manage/matches", headers=headers
    ).json()
    by_id = {row["id"]: row for row in rows}
    for code in ("M1", "M2", "M5"):
        row = by_id[str(setup.matches[code].id)]
        assert row["can_assign_referee"] is True
        for account in (free, member):
            listed = str(account.id) in row["assignable_referee_ids"]
            response = _put(client, setup, code, account)
            assert (response.status_code == 200) == listed, (code, account.id)
            _delete(client, setup, code)
    m1 = by_id[str(setup.matches["M1"].id)]
    assert m1["assignable_referee_ids"] == [str(free.id)]
    # 兩位裁判在凍結時鐘下同時接受邀請，順序不固定，只比內容
    assert set(by_id[str(setup.matches["M2"].id)]["assignable_referee_ids"]) == {
        str(free.id),
        str(member.id),
    }

    row = setup.row("M2")
    row.status = MatchStatus.CONFIRMED
    session.add(row)
    session.commit()
    rows = client.get(
        f"{API}/tournaments/{setup.tournament_id}/manage/matches", headers=headers
    ).json()
    locked = next(r for r in rows if r["id"] == str(setup.matches["M2"].id))
    assert locked["can_assign_referee"] is False
    assert locked["assignable_referee_ids"] == []


def test_advance_conflict_unassigns_referee(
    client: TestClient,
    session: Session,
    setup: Setup,
) -> None:
    referee = setup.referee()
    assert _put(client, setup, "M5", referee).status_code == 200
    winner = setup.team("M1", "a")
    setup.members.add((winner, referee.id))
    m1 = setup.row("M1")
    m1.status = MatchStatus.APPEAL_WINDOW
    m1.outcome = MatchOutcome.PLAYED
    m1.winner_id = winner
    session.add(m1)
    session.flush()
    tournaments_service.lock_tournament(session, tournament_id=setup.tournament_id)
    locked = service.lock_match(session, match_id=m1.id)
    service.confirm_match(
        session,
        match=locked,
        outcome=MatchOutcome.PLAYED,
        winner_id=winner,
        actor_id=None,
    )
    session.commit()

    row = setup.row("M5")
    assert winner in (row.team_a_id, row.team_b_id)
    assert row.referee_account_id is None
    (log,) = _logs(session, "match.referee_unassigned")
    assert log.actor_id is None
    assert log.before == {"referee_account_id": str(referee.id)}
    assert log.after == {"referee_account_id": None}
    assert [e["referee_account_id"] for e in _events(session, "RefereeUnassigned")] == [
        str(referee.id)
    ]


def test_advance_without_conflict_keeps_referee(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    _put(client, setup, "M5", referee)
    winner = setup.team("M1", "a")
    m1 = setup.row("M1")
    m1.status = MatchStatus.APPEAL_WINDOW
    m1.outcome = MatchOutcome.PLAYED
    m1.winner_id = winner
    session.add(m1)
    session.flush()
    tournaments_service.lock_tournament(session, tournament_id=setup.tournament_id)
    locked = service.lock_match(session, match_id=m1.id)
    service.confirm_match(
        session,
        match=locked,
        outcome=MatchOutcome.PLAYED,
        winner_id=winner,
        actor_id=None,
    )
    session.commit()

    assert setup.row("M5").referee_account_id == referee.id
    assert _events(session, "RefereeUnassigned") == []


def test_ongoing_tournament_assignable(
    client: TestClient, session: Session, setup: Setup
) -> None:
    referee = setup.referee()
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.ONGOING
    session.add(row)
    session.commit()

    assert _put(client, setup, "M1", referee).status_code == 200
    assert _delete(client, setup, "M1").status_code == 200
    rows = client.get(
        f"{API}/tournaments/{setup.tournament_id}/manage/matches",
        headers=_headers(client, setup.organizer),
    ).json()
    row_m1 = next(r for r in rows if r["id"] == str(setup.matches["M1"].id))
    assert row_m1["can_assign_referee"] is True


def test_finished_tournament_list_not_assignable(
    client: TestClient, session: Session, setup: Setup
) -> None:
    setup.referee()
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.FINISHED
    session.add(row)
    session.commit()

    rows = client.get(
        f"{API}/tournaments/{setup.tournament_id}/manage/matches",
        headers=_headers(client, setup.organizer),
    ).json()
    assert rows
    assert all(r["can_assign_referee"] is False for r in rows)
    assert all(r["assignable_referee_ids"] == [] for r in rows)


def test_real_is_member_delegates_to_registration(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    team, member, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(registration_port, "is_member", _REAL_IS_MEMBER)
    monkeypatch.setattr(
        registration_service,
        "is_member",
        lambda _s, *, team_id, account_id: (team_id, account_id) == (team, member),
        raising=False,
    )

    assert registration_port.is_member(session, team_id=team, account_id=member)
    assert not registration_port.is_member(session, team_id=team, account_id=other)


def test_registration_without_is_member_is_503(
    client: TestClient, session: Session, setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    referee = setup.referee()
    monkeypatch.setattr(registration_port, "is_member", _REAL_IS_MEMBER)
    monkeypatch.delattr(registration_service, "is_member", raising=False)

    response = _put(client, setup, "M1", referee)

    assert response.status_code == 503
    assert _code(response) == "REGISTRATION_UNAVAILABLE"
    assert setup.row("M1").referee_account_id is None
    assert _counts(session) == (0, 0)


def test_unauthenticated_401(client: TestClient, setup: Setup) -> None:
    body = {"account_id": str(uuid.uuid4())}
    assert client.put(setup.url("M1"), json=body).status_code == 401
    assert client.delete(setup.url("M1")).status_code == 401


@pytest.mark.parametrize("body", [{}, {"account_id": "not-a-uuid"}])
def test_invalid_body_422(
    client: TestClient, session: Session, setup: Setup, body: dict[str, Any]
) -> None:
    response = client.put(
        setup.url("M1"), json=body, headers=_headers(client, setup.organizer)
    )
    assert response.status_code == 422
    assert _counts(session) == (0, 0)
