"""Story 5.1 第二階段：報到紀錄、報到 API、給 5.2 的查詢函式與賽事開始 worker。

8 隊抽籤後第一輪 M1～M4 都排在賽事開賽時間（frozen_clock 下為 2026-10-26 11:00 UTC），
棄權期限為預定時間＋15 分鐘；M5 起兩隊未確定。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core import audit
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, repository, service
from app.modules.competition.models import (
    Bracket,
    CheckIn,
    Match,
    MatchStatus,
)
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from app.worker import jobs, run_once
from tests.competition.conftest import FakeRegistration, FrozenClockLike, draw_with
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

# fixture 換掉替身前的真正轉接函式
_REAL_IS_CAPTAIN = registration_port.is_captain

SCHEDULED = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)
OPENS = SCHEDULED - timedelta(minutes=30)
DEADLINE = SCHEDULED + timedelta(minutes=15)


class Setup:
    """已抽籤的賽事，加上每隊一位隊長帳號（替身 `is_captain`）。"""

    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        tournament, bracket = draw_with(session, fake, 8)
        self.tournament_id = tournament.id
        self.matches = {m.code: m for m in bracket.matches}
        self.captains: dict[uuid.UUID, Account] = {
            team_id: make_account(session) for team_id in fake.teams
        }
        self.outsider = make_account(session)
        self.fake = fake

    def captain_of(self, side: str, code: str = "M1") -> Account:
        match = self.matches[code]
        team_id = match.team_a_id if side == "a" else match.team_b_id
        assert team_id is not None
        return self.captains[team_id]

    def url(self, code: str = "M1", *, tournament_id: uuid.UUID | None = None) -> str:
        return (
            f"{API}/tournaments/{tournament_id or self.tournament_id}"
            f"/matches/{self.matches[code].id}/check-in"
        )


@pytest.fixture
def setup(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> Setup:
    result = Setup(session, fake_registration)

    def is_captain(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        captain = result.captains.get(team_id)
        return captain is not None and captain.id == account_id

    monkeypatch.setattr(registration_port, "is_captain", is_captain)
    session.commit()
    return result


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _check_in_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(CheckIn)).one()


def _audit_count(session: Session) -> int:
    return session.exec(
        select(func.count())
        .select_from(audit.AuditLog)
        .where(audit.AuditLog.action == "match.checked_in")
    ).one()


def _event_count(session: Session) -> int:
    return session.exec(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.type == "TeamCheckedIn")
    ).one()


def _code(response: object) -> str:
    return str(response.json()["detail"]["code"])  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 報到 API


def test_check_in_succeeds_and_status_shows_it(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS + timedelta(minutes=5))
    account = setup.captain_of("a")

    response = client.post(setup.url(), headers=_headers(client, account))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["match_id"] == str(setup.matches["M1"].id)
    assert body["team_id"] == str(setup.matches["M1"].team_a_id)
    assert body["at"].startswith("2026-10-26T10:35:00")
    assert _check_in_count(session) == 1
    assert _audit_count(session) == 1
    assert _event_count(session) == 1
    status = client.get(setup.url(), headers=_headers(client, account)).json()
    assert status["side"] == "a"
    assert status["reason"] == "already_checked_in"


def test_check_in_exactly_at_opening(
    client: TestClient, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("b")))

    assert response.status_code == 201, response.text


def test_check_in_one_minute_too_early(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS - timedelta(minutes=1))

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 409
    assert _code(response) == "CHECK_IN_NOT_OPEN"
    assert response.json()["detail"]["message"] == "10/26（一）18:30 起可報到。"
    assert _check_in_count(session) == 0
    assert _audit_count(session) == 0


def test_check_in_exactly_at_deadline_is_closed(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(DEADLINE)

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 409
    assert _code(response) == "CHECK_IN_CLOSED"
    assert _check_in_count(session) == 0
    assert _audit_count(session) == 0


def test_check_in_after_scheduled_time_before_deadline(
    client: TestClient, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(DEADLINE - timedelta(minutes=1))

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 201


def test_check_in_twice_is_already_checked_in(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    headers = _headers(client, setup.captain_of("a"))
    assert client.post(setup.url(), headers=headers).status_code == 201

    response = client.post(setup.url(), headers=headers)

    assert response.status_code == 409
    assert _code(response) == "ALREADY_CHECKED_IN"
    assert _check_in_count(session) == 1
    assert _audit_count(session) == 1


def test_teams_pending_match(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(SCHEDULED)
    # M5 兩隊未確定；任何帳號都先得到 MATCH_TEAMS_PENDING
    response = client.post(
        setup.url("M5"), headers=_headers(client, setup.captain_of("a"))
    )

    assert response.status_code == 409
    assert _code(response) == "MATCH_TEAMS_PENDING"
    assert _check_in_count(session) == 0


@pytest.mark.parametrize("who", ["outsider", "other_match_captain"])
def test_not_a_captain_of_either_team(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    who: str,
) -> None:
    frozen_clock.set(OPENS)
    account = setup.outsider if who == "outsider" else setup.captain_of("a", code="M2")

    response = client.post(setup.url(), headers=_headers(client, account))

    assert response.status_code == 403
    assert _code(response) == "CAPTAIN_REQUIRED"
    assert _check_in_count(session) == 0
    assert _audit_count(session) == 0


def test_requires_login(client: TestClient, setup: Setup) -> None:
    assert client.post(setup.url()).status_code == 401
    assert client.get(setup.url()).status_code == 401


def test_match_not_scheduled_is_not_checkable(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    match = session.get(Match, setup.matches["M1"].id)
    assert match is not None
    match.status = MatchStatus.APPEAL_WINDOW
    session.add(match)
    session.commit()

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 409
    assert _code(response) == "MATCH_NOT_CHECKABLE"
    assert _check_in_count(session) == 0


@pytest.mark.parametrize(
    "tournament_status",
    [TournamentStatus.CANCELLED, TournamentStatus.FINISHED, TournamentStatus.CLOSED],
)
def test_tournament_not_published_or_ongoing_is_not_checkable(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    tournament_status: TournamentStatus,
) -> None:
    frozen_clock.set(OPENS)
    tournament = session.get(Tournament, setup.tournament_id)
    assert tournament is not None
    tournament.status = tournament_status
    session.add(tournament)
    session.commit()

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 409
    assert _code(response) == "MATCH_NOT_CHECKABLE"


def test_ongoing_tournament_allows_check_in(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    tournament = session.get(Tournament, setup.tournament_id)
    assert tournament is not None
    tournament.status = TournamentStatus.ONGOING
    session.add(tournament)
    session.commit()

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 201


def test_unknown_match_or_wrong_tournament_is_404(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    headers = _headers(client, setup.captain_of("a"))
    other_tournament = uuid.uuid4()

    wrong_tournament = client.post(
        setup.url(tournament_id=other_tournament), headers=headers
    )
    unknown_match = client.post(
        f"{API}/tournaments/{setup.tournament_id}/matches/{uuid.uuid4()}/check-in",
        headers=headers,
    )

    for response in (wrong_tournament, unknown_match):
        assert response.status_code == 404
        assert _code(response) == "MATCH_NOT_FOUND"
    assert _check_in_count(session) == 0


def test_registration_without_is_captain_is_503(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen_clock.set(OPENS)
    # 只還原 is_captain 的替身；registration 目前沒有這個函式
    monkeypatch.setattr(registration_port, "is_captain", _REAL_IS_CAPTAIN)
    monkeypatch.delattr(registration_service, "is_captain", raising=False)

    response = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))

    assert response.status_code == 503
    assert _code(response) == "REGISTRATION_UNAVAILABLE"
    assert _check_in_count(session) == 0


def test_both_captains_check_in_without_overwriting(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    first = client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))
    frozen_clock.advance(timedelta(minutes=1))
    second = client.post(setup.url(), headers=_headers(client, setup.captain_of("b")))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["team_id"] != second.json()["team_id"]
    rows = service.list_check_ins(session, match_id=setup.matches["M1"].id)
    assert [r.team_id for r in rows] == [
        setup.matches["M1"].team_a_id,
        setup.matches["M1"].team_b_id,
    ]
    assert rows[0].at < rows[1].at
    events = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "TeamCheckedIn")
    ).all()
    assert [e.payload["both_checked_in"] for e in events] == [False, True]


def test_unique_key_is_the_last_line_of_defence(session: Session, setup: Setup) -> None:
    match = setup.matches["M1"]
    assert match.team_a_id is not None
    account = setup.captain_of("a")

    def row() -> CheckIn:
        assert match.team_a_id is not None
        return CheckIn(
            match_id=match.id,
            team_id=match.team_a_id,
            account_id=account.id,
            at=SCHEDULED,
        )

    assert repository.add_check_in(session, row()) is True
    assert repository.add_check_in(session, row()) is False
    # 外層交易沒有被弄壞
    assert _check_in_count(session) == 1


def test_duplicate_hitting_unique_key_is_409_not_500(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen_clock.set(OPENS)
    headers = _headers(client, setup.captain_of("a"))
    assert client.post(setup.url(), headers=headers).status_code == 201
    audits = _audit_count(session)
    events = _event_count(session)
    # 模擬併發：重複檢查漏看已存在的報到紀錄，只剩唯一鍵擋下
    monkeypatch.setattr(repository, "list_check_ins", lambda *_a, **_k: [])

    response = client.post(setup.url(), headers=headers)

    assert response.status_code == 409
    assert _code(response) == "ALREADY_CHECKED_IN"
    monkeypatch.undo()
    assert _check_in_count(session) == 1
    assert _audit_count(session) == audits
    assert _event_count(session) == events


@pytest.mark.parametrize("bad", ["no_deadline", "deadline_not_after_opening"])
def test_unusable_forfeit_deadline_is_not_checkable(
    client: TestClient,
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    bad: str,
) -> None:
    frozen_clock.set(OPENS)
    match = session.get(Match, setup.matches["M1"].id)
    assert match is not None
    match.forfeit_deadline = None if bad == "no_deadline" else OPENS
    session.add(match)
    session.commit()
    headers = _headers(client, setup.captain_of("a"))

    status = client.get(setup.url(), headers=headers)
    response = client.post(setup.url(), headers=headers)

    assert status.status_code == 200
    assert status.json()["reason"] == "not_checkable"
    assert status.json()["side"] == "a"
    assert response.status_code == 409
    assert _code(response) == "MATCH_NOT_CHECKABLE"
    assert _check_in_count(session) == 0
    assert _audit_count(session) == 0


def test_taipei_message_adds_year_when_crossing_year(
    session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    match = session.get(Match, setup.matches["M1"].id)
    assert match is not None
    # 台北 2027/1/2（六）09:00 開打；現在是 2026 年，開放時間 08:30 要加年份
    match.scheduled_at = datetime(2027, 1, 2, 1, 0, tzinfo=UTC)
    match.forfeit_deadline = match.scheduled_at + timedelta(minutes=15)
    session.add(match)
    session.flush()
    frozen_clock.set(datetime(2026, 12, 30, 0, 0, tzinfo=UTC))

    with pytest.raises(BusinessError) as raised:
        service.check_in(
            session,
            tournament_id=setup.tournament_id,
            match_id=match.id,
            account_id=setup.captain_of("a").id,
        )

    assert raised.value.code == "CHECK_IN_NOT_OPEN"
    assert raised.value.message == "2027/1/2（六）08:30 起可報到。"


# ---------------------------------------------------------------- 狀態查詢


_API_CODES = {
    "teams_pending": "MATCH_TEAMS_PENDING",
    "already_checked_in": "ALREADY_CHECKED_IN",
    "too_early": "CHECK_IN_NOT_OPEN",
    "closed": "CHECK_IN_CLOSED",
    "not_checkable": "MATCH_NOT_CHECKABLE",
    "not_captain": "CAPTAIN_REQUIRED",
}


def _assert_status_matches_post(
    client: TestClient, setup: Setup, account: Account, code: str
) -> None:
    headers = _headers(client, account)
    status = client.get(setup.url(code), headers=headers).json()
    response = client.post(setup.url(code), headers=headers)
    assert (status["reason"] is None) == (response.status_code == 201), (
        status,
        response.text,
    )
    if response.status_code != 201:
        assert _API_CODES[status["reason"]] == _code(response)


def test_status_reason_is_null_iff_check_in_succeeds(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    moments = [
        OPENS - timedelta(minutes=1),
        OPENS,
        SCHEDULED,
        DEADLINE - timedelta(seconds=1),
        DEADLINE,
    ]
    # a、b 隊長、別場（M2）的隊長、旁觀者；M1 可報到、M5 兩隊未確定、M3 改成申訴期
    accounts = [
        setup.captain_of("a"),
        setup.captain_of("b"),
        setup.captain_of("a", code="M2"),
        setup.outsider,
    ]
    appeal = session.get(Match, setup.matches["M3"].id)
    assert appeal is not None
    appeal.status = MatchStatus.APPEAL_WINDOW
    session.add(appeal)
    session.commit()
    for moment in moments:
        for code in ("M1", "M5", "M3"):
            for account in accounts:
                frozen_clock.set(moment)
                _assert_status_matches_post(client, setup, account, code)
                session.commit()
                for row in session.exec(select(CheckIn)).all():
                    session.delete(row)
                session.commit()


def test_status_after_checking_in_matches_post(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    for side in ("a", "b"):
        account = setup.captain_of(side)
        assert (
            client.post(setup.url(), headers=_headers(client, account)).status_code
            == 201
        )
        status = client.get(setup.url(), headers=_headers(client, account)).json()
        assert (status["side"], status["reason"]) == (side, "already_checked_in")
        _assert_status_matches_post(client, setup, account, "M1")


def test_status_reports_side_and_reason(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS - timedelta(minutes=1))
    m3 = session.get(Match, setup.matches["M3"].id)
    assert m3 is not None
    m3.status = MatchStatus.APPEAL_WINDOW
    session.add(m3)
    session.commit()

    def get(account: Account, code: str = "M1") -> dict[str, object]:
        response = client.get(setup.url(code), headers=_headers(client, account))
        assert response.status_code == 200
        data: dict[str, object] = response.json()
        return data

    b = get(setup.captain_of("b"))
    outsider = get(setup.outsider)
    pending = get(setup.captain_of("a"), "M5")
    not_checkable = get(setup.captain_of("a", "M3"), "M3")

    assert (b["side"], b["reason"]) == ("b", "too_early")
    assert str(b["opens_at"]).startswith("2026-10-26T10:30:00")
    assert (outsider["side"], outsider["reason"]) == (None, "not_captain")
    assert (pending["side"], pending["reason"]) == (None, "teams_pending")
    # 場次不可報到時，兩隊已確定仍回傳隊長的 side
    assert (not_checkable["side"], not_checkable["reason"]) == ("a", "not_checkable")


def test_status_unknown_match_is_404(client: TestClient, setup: Setup) -> None:
    response = client.get(
        f"{API}/tournaments/{setup.tournament_id}/matches/{uuid.uuid4()}/check-in",
        headers=_headers(client, setup.outsider),
    )

    assert response.status_code == 404
    assert _code(response) == "MATCH_NOT_FOUND"


# ---------------------------------------------------------------- 棄權候選


def test_forfeit_due_excludes_fully_checked_in_matches(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    # M1 兩隊都報到、M2 只有 a 報到、M3 沒人報到、M4 b 報到
    for code, sides in (("M1", "ab"), ("M2", "a"), ("M4", "b")):
        for side in sides:
            response = client.post(
                setup.url(code),
                headers=_headers(client, setup.captain_of(side, code)),
            )
            assert response.status_code == 201, response.text
    session.commit()

    before_deadline = service.list_forfeit_due(
        session, now=DEADLINE - timedelta(seconds=1)
    )
    at_deadline = service.list_forfeit_due(session, now=DEADLINE)

    assert before_deadline == []
    assert at_deadline == sorted(
        [setup.matches[c].id for c in ("M2", "M3", "M4")],
        key=lambda i: (DEADLINE, i),
    )
    assert setup.matches["M1"].id not in at_deadline
    assert len(service.list_check_ins(session, match_id=setup.matches["M1"].id)) == 2


def test_forfeit_due_is_ordered_by_deadline_not_id(
    session: Session, setup: Setup
) -> None:
    ids = [setup.matches[c].id for c in ("M1", "M2", "M3", "M4")]
    by_id = sorted(ids)
    # 期限與 id 順序相反：id 最小的期限最晚
    for rank, match_id in enumerate(by_id):
        match = session.get(Match, match_id)
        assert match is not None
        match.forfeit_deadline = DEADLINE + timedelta(minutes=10 - rank)
        session.add(match)
    session.flush()

    due = service.list_forfeit_due(session, now=DEADLINE + timedelta(hours=1))

    assert due == list(reversed(by_id))


def test_list_check_ins_is_ordered_by_time_not_insertion(
    session: Session, setup: Setup
) -> None:
    match = setup.matches["M1"]
    assert match.team_a_id is not None and match.team_b_id is not None
    later = CheckIn(
        match_id=match.id,
        team_id=match.team_a_id,
        account_id=setup.captain_of("a").id,
        at=SCHEDULED,
    )
    earlier = CheckIn(
        match_id=match.id,
        team_id=match.team_b_id,
        account_id=setup.captain_of("b").id,
        at=SCHEDULED - timedelta(minutes=20),
    )
    repository.add_check_in(session, later)  # 先插入較晚的
    repository.add_check_in(session, earlier)

    rows = service.list_check_ins(session, match_id=match.id)

    assert [r.team_id for r in rows] == [match.team_b_id, match.team_a_id]


def test_forfeit_due_only_scheduled_matches(session: Session, setup: Setup) -> None:
    match = session.get(Match, setup.matches["M3"].id)
    assert match is not None
    match.status = MatchStatus.APPEAL_WINDOW
    session.add(match)
    session.flush()

    due = service.list_forfeit_due(session, now=DEADLINE + timedelta(hours=1))

    assert setup.matches["M3"].id not in due
    assert setup.matches["M1"].id in due
    # 第二輪以後兩隊未確定，沒有棄權期限
    assert setup.matches["M5"].id not in due


# ---------------------------------------------------------------- 公開單場


def test_public_match_shows_check_in_times_without_login(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS + timedelta(minutes=2))
    client.post(setup.url(), headers=_headers(client, setup.captain_of("a")))
    session.commit()
    public_url = (
        f"{API}/tournaments/{setup.tournament_id}/matches/{setup.matches['M1'].id}"
    )

    data = client.get(public_url).json()
    pending = client.get(
        f"{API}/tournaments/{setup.tournament_id}/matches/{setup.matches['M5'].id}"
    ).json()
    bracket = client.get(f"{API}/tournaments/{setup.tournament_id}/bracket").json()

    assert data["check_in_a_at"].startswith("2026-10-26T10:32:00")
    assert data["check_in_b_at"] is None
    assert pending["check_in_a_at"] is None
    assert pending["check_in_b_at"] is None
    assert all("check_in_a_at" not in m for m in bracket["matches"])
    assert all("check_in_a_at" not in m for m in data["same_round"])


# ---------------------------------------------------------------- 賽事開始 worker


def _tournament_status(session: Session, tournament_id: uuid.UUID) -> TournamentStatus:
    session.expire_all()
    tournament = session.get(Tournament, tournament_id)
    assert tournament is not None
    return TournamentStatus(tournament.status)


def _status_changes(session: Session, tournament_id: uuid.UUID) -> int:
    return len(
        [
            r
            for r in audit.list_for_tournament(session, tournament_id)
            if r.action == "tournament.status_changed"
        ]
    )


def test_job_is_registered_before_confirm_expired_appeals() -> None:
    names = [getattr(j, "__name__", "") for j in jobs.JOBS]
    assert names.index("start_due_tournaments") < names.index("confirm_expired_appeals")


def test_start_tournament_when_opening_time_reached(
    session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS)
    before = _status_changes(session, setup.tournament_id)

    found = service.start_due_tournament(session)

    assert found is True
    assert _tournament_status(session, setup.tournament_id) == TournamentStatus.ONGOING
    records = [
        r
        for r in audit.list_for_tournament(session, setup.tournament_id)
        if r.action == "tournament.status_changed"
    ]
    assert len(records) == before + 1
    assert records[-1].actor_id is None


def test_start_tournament_not_yet_due(
    session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(OPENS - timedelta(minutes=1))

    assert service.start_due_tournament(session) is False

    assert (
        _tournament_status(session, setup.tournament_id) == TournamentStatus.PUBLISHED
    )


def test_start_tournament_twice_has_no_side_effect(
    session: Session,
    session_factory: object,
    setup: Setup,
    frozen_clock: FrozenClockLike,
) -> None:
    frozen_clock.set(OPENS + timedelta(minutes=10))
    before = _status_changes(session, setup.tournament_id)

    run_once([jobs.start_due_tournaments], session_factory=session_factory)  # type: ignore[arg-type]
    run_once([jobs.start_due_tournaments], session_factory=session_factory)  # type: ignore[arg-type]

    assert _tournament_status(session, setup.tournament_id) == TournamentStatus.ONGOING
    assert _status_changes(session, setup.tournament_id) == before + 1
    assert service.start_due_tournament(session) is False


@pytest.mark.parametrize(
    "tournament_status", [TournamentStatus.CANCELLED, TournamentStatus.FINISHED]
)
def test_start_skips_cancelled_or_finished(
    session: Session,
    setup: Setup,
    frozen_clock: FrozenClockLike,
    tournament_status: TournamentStatus,
) -> None:
    frozen_clock.set(OPENS)
    tournament = session.get(Tournament, setup.tournament_id)
    assert tournament is not None
    tournament.status = tournament_status
    session.add(tournament)
    session.flush()
    before = _status_changes(session, setup.tournament_id)

    assert service.start_due_tournament(session) is True  # 找到候選並標記略過
    assert service.start_due_tournament(session) is False  # 不會一直被選中

    assert _tournament_status(session, setup.tournament_id) == tournament_status
    assert _status_changes(session, setup.tournament_id) == before
    bracket = session.exec(
        select(Bracket).where(Bracket.tournament_id == setup.tournament_id)
    ).one()
    assert bracket.start_handled_at is not None


def test_start_uses_earliest_match_time(
    session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    # 把全部場次改期到 13:00，最早場次的報到開放時間為 12:30
    for match in session.exec(
        select(Match).where(Match.tournament_id == setup.tournament_id)
    ).all():
        match.scheduled_at = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
        session.add(match)
    session.flush()

    frozen_clock.set(datetime(2026, 10, 27, 12, 29, tzinfo=UTC))
    assert service.start_due_tournament(session) is False
    assert (
        _tournament_status(session, setup.tournament_id) == TournamentStatus.PUBLISHED
    )

    frozen_clock.set(datetime(2026, 10, 27, 12, 30, tzinfo=UTC))
    assert service.start_due_tournament(session) is True
    assert _tournament_status(session, setup.tournament_id) == TournamentStatus.ONGOING
