"""Story 4.3 第二階段：S30 場次列表 API 與修改場次時間。

8 隊抽籤後（frozen_clock 為 2026-10-18 11:00 UTC）：第一輪 M1～M4 在 10-26 11:00、
第二輪 M5、M6（準決賽）在 14:00、決賽 M7 與季軍賽 M8 在 17:00（輪次間隔 180 分鐘）。
最小間隔＝棄權 15＋BO3 × 40＋申訴 30＝165 分鐘。
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.core import audit
from app.core.events import OutboxEvent
from app.modules.competition.models import CheckIn, Match, MatchStatus
from app.modules.identity.models import Account
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import (
    FakeRegistration,
    FrozenClockLike,
    draw_with,
    tournament_in,
)
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

GAP = timedelta(minutes=165)
MINUTE = timedelta(minutes=1)
NOW = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
# 最早可選時間：現在（進位到整分）＋30 分鐘
FLOOR = NOW + timedelta(minutes=30)
R1 = datetime(2026, 10, 26, 11, 0, tzinfo=UTC)
R2 = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)
R3 = datetime(2026, 10, 26, 17, 0, tzinfo=UTC)


class Setup:
    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        self.tournament, bracket = draw_with(session, fake, 8)
        self.tournament_id = self.tournament.id
        self.matches = {m.code: m for m in bracket.matches}
        organizer = session.get(Account, self.tournament.organizer_id)
        assert organizer is not None
        self.organizer = organizer
        self.session = session

    def url(self, code: str, *, tournament_id: uuid.UUID | None = None) -> str:
        return (
            f"{API}/tournaments/{tournament_id or self.tournament_id}"
            f"/matches/{self.matches[code].id}/schedule"
        )

    @property
    def list_url(self) -> str:
        return f"{API}/tournaments/{self.tournament_id}/manage/matches"

    def row(self, code: str) -> Match:
        self.session.expire_all()
        row = self.session.get(Match, self.matches[code].id)
        assert row is not None
        return row

    def update(self, code: str, **values: object) -> None:
        row = self.row(code)
        for key, value in values.items():
            setattr(row, key, value)
        self.session.add(row)
        self.session.commit()

    def snapshot(self) -> dict[str, tuple[object, object, object]]:
        self.session.expire_all()
        rows = self.session.exec(
            select(Match).where(Match.tournament_id == self.tournament_id)
        ).all()
        return {
            r.code: (r.scheduled_at, r.forfeit_deadline, r.updated_at) for r in rows
        }


@pytest.fixture
def setup(session: Session, fake_registration: FakeRegistration) -> Setup:
    result = Setup(session, fake_registration)
    session.commit()
    return result


def _headers(client: TestClient, account: Account) -> dict[str, str]:
    return bearer(token_for(client, account))


def _patch(
    client: TestClient, setup: Setup, code: str, at: datetime | str, **kwargs: object
):  # noqa: ANN202
    headers = kwargs.pop("headers", None) or _headers(client, setup.organizer)
    value = at.isoformat() if isinstance(at, datetime) else at
    return client.patch(
        setup.url(code),
        json={"scheduled_at": value},
        headers=headers,  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _code(response: object) -> str:
    return str(response.json()["detail"]["code"])  # type: ignore[attr-defined]


def _count(session: Session, action: str) -> int:
    return session.exec(
        select(func.count())
        .select_from(audit.AuditLog)
        .where(audit.AuditLog.action == action)
    ).one()


def _events(session: Session) -> int:
    return session.exec(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.type == "MatchRescheduled")
    ).one()


def _assert_rejected(
    client: TestClient,
    session: Session,
    setup: Setup,
    code: str,
    at: datetime | str,
    expected_code: str,
    status_code: int = 409,
) -> object:
    before = setup.snapshot()
    audits, events = _count(session, "match.rescheduled"), _events(session)
    response = _patch(client, setup, code, at)
    assert response.status_code == status_code, response.text
    assert _code(response) == expected_code
    assert setup.snapshot() == before
    assert _count(session, "match.rescheduled") == audits
    assert _events(session) == events
    return response


# ---------------------------------------------------------------- 修改時間


def test_first_round_reschedule_succeeds(
    client: TestClient, session: Session, setup: Setup
) -> None:
    new = R1 + timedelta(minutes=10)

    response = _patch(client, setup, "M1", new)

    assert response.status_code == 200, response.text
    assert response.json()["scheduled_at"].startswith("2026-10-26T11:10:00")
    row = setup.row("M1")
    assert row.scheduled_at == new
    assert row.forfeit_deadline == new + timedelta(minutes=15)
    assert row.updated_at == NOW
    log = session.exec(
        select(audit.AuditLog).where(audit.AuditLog.action == "match.rescheduled")
    ).one()
    assert log.entity_id == row.id
    assert log.before is not None and log.after is not None
    assert log.before["scheduled_at"].startswith("2026-10-26T11:00:00")
    assert log.before["forfeit_deadline"].startswith("2026-10-26T11:15:00")
    assert log.after["scheduled_at"].startswith("2026-10-26T11:10:00")
    assert log.after["forfeit_deadline"].startswith("2026-10-26T11:25:00")
    assert _events(session) == 1
    event = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "MatchRescheduled")
    ).one()
    assert event.payload["match_id"] == str(row.id)
    assert event.payload["scheduled_at"].startswith("2026-10-26T11:10:00")


def test_latest_boundary_ok_and_one_minute_later_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    latest = R2 - GAP
    late = _assert_rejected(
        client, session, setup, "M1", latest + MINUTE, "RESCHEDULE_AFTER_NEXT_MATCH"
    )
    assert "10/26（一）" in late.json()["detail"]["message"]  # type: ignore[attr-defined]
    assert "19:15" in late.json()["detail"]["message"]  # type: ignore[attr-defined]

    assert _patch(client, setup, "M1", latest).status_code == 200


def test_before_now_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    _assert_rejected(
        client, session, setup, "M1", FLOOR - MINUTE, "RESCHEDULE_BEFORE_NOW"
    )
    assert _patch(client, setup, "M1", FLOOR).status_code == 200


def test_floor_rounds_now_up_to_the_minute(
    client: TestClient, session: Session, setup: Setup, frozen_clock: FrozenClockLike
) -> None:
    frozen_clock.set(datetime(2026, 10, 18, 10, 0, 20, tzinfo=UTC))
    floor = datetime(2026, 10, 18, 10, 31, tzinfo=UTC)

    _assert_rejected(
        client, session, setup, "M1", floor - MINUTE, "RESCHEDULE_BEFORE_NOW"
    )
    assert _patch(client, setup, "M1", floor).status_code == 200
    assert setup.row("M1").scheduled_at == floor


def test_forfeit_due_without_check_in_blocks(
    client: TestClient, session: Session, setup: Setup
) -> None:
    setup.update("M1", forfeit_deadline=NOW)

    _assert_rejected(
        client, session, setup, "M1", R1 + MINUTE, "MATCH_NOT_RESCHEDULABLE"
    )
    info = _info(client, setup, "M1")
    assert info["reason"] == "forfeit_due"
    assert info["can_reschedule"] is False


def test_same_time_writes_nothing(
    client: TestClient, session: Session, setup: Setup
) -> None:
    before = setup.snapshot()

    response = _patch(client, setup, "M1", R1)

    assert response.status_code == 200
    assert response.json()["scheduled_at"].startswith("2026-10-26T11:00:00")
    assert setup.snapshot() == before
    assert _count(session, "match.rescheduled") == 0
    assert _events(session) == 0


def test_offset_input_is_stored_and_returned_as_utc(
    client: TestClient, setup: Setup
) -> None:
    response = _patch(client, setup, "M1", "2026-10-26T19:10:00+08:00")

    assert response.status_code == 200, response.text
    assert response.json()["scheduled_at"] == "2026-10-26T11:10:00Z"
    assert setup.row("M1").scheduled_at == R1 + timedelta(minutes=10)


def test_before_feeder_rejected(
    client: TestClient, session: Session, setup: Setup
) -> None:
    earliest = R1 + GAP  # 13:45，等於前一輪（兩場都在 11:00）結束
    _assert_rejected(
        client, session, setup, "M5", earliest - MINUTE, "RESCHEDULE_BEFORE_FEEDER"
    )
    assert _patch(client, setup, "M5", earliest).status_code == 200


def test_semifinal_upper_bound_uses_earlier_of_final_and_third(
    client: TestClient, session: Session, setup: Setup
) -> None:
    third = R2 + GAP  # 季軍賽最早 16:45，比決賽 17:00 早
    assert _patch(client, setup, "M8", third).status_code == 200
    latest = third - GAP

    _assert_rejected(
        client, session, setup, "M5", latest + MINUTE, "RESCHEDULE_AFTER_NEXT_MATCH"
    )
    assert _patch(client, setup, "M5", latest).status_code == 200


def test_final_and_third_place_have_no_upper_bound(
    client: TestClient, setup: Setup
) -> None:
    far = R3 + timedelta(days=60)

    assert _patch(client, setup, "M7", far).status_code == 200
    assert _patch(client, setup, "M8", far + timedelta(days=1)).status_code == 200


def test_no_valid_time(client: TestClient, session: Session, setup: Setup) -> None:
    # 決賽與季軍賽都排在現在附近：準決賽的最晚早於現在
    setup.update("M7", scheduled_at=NOW + timedelta(hours=1))
    setup.update("M8", scheduled_at=NOW + timedelta(hours=1))

    response = _assert_rejected(
        client, session, setup, "M5", R2, "RESCHEDULE_NO_VALID_TIME"
    )
    message = response.json()["detail"]["message"]  # type: ignore[attr-defined]
    assert message == "這場目前沒有可選的時間（最早 10/26（一）21:45）。"


def test_teams_pending_match_has_no_forfeit_deadline(
    client: TestClient, setup: Setup
) -> None:
    response = _patch(client, setup, "M5", R2 + timedelta(minutes=10))

    assert response.status_code == 200, response.text
    assert setup.row("M5").forfeit_deadline is None


def test_checked_in_team_blocks(
    client: TestClient, session: Session, setup: Setup
) -> None:
    match = setup.row("M1")
    assert match.team_a_id is not None
    session.add(
        CheckIn(
            match_id=match.id,
            team_id=match.team_a_id,
            account_id=setup.organizer.id,
            at=NOW,
        )
    )
    session.commit()

    _assert_rejected(
        client, session, setup, "M1", R1 + MINUTE, "MATCH_ALREADY_CHECKED_IN"
    )


@pytest.mark.parametrize(
    "status",
    [MatchStatus.LIVE, MatchStatus.APPEAL_WINDOW, MatchStatus.CONFIRMED],
)
def test_match_not_scheduled_rejected(
    client: TestClient, session: Session, setup: Setup, status: MatchStatus
) -> None:
    setup.update("M1", status=status)

    _assert_rejected(
        client, session, setup, "M1", R1 + MINUTE, "MATCH_NOT_RESCHEDULABLE"
    )


@pytest.mark.parametrize(
    "status", [TournamentStatus.FINISHED, TournamentStatus.CANCELLED]
)
def test_tournament_not_reschedulable(
    client: TestClient, session: Session, setup: Setup, status: TournamentStatus
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = status
    session.add(row)
    session.commit()

    _assert_rejected(
        client, session, setup, "M1", R1 + MINUTE, "TOURNAMENT_NOT_RESCHEDULABLE"
    )


def test_ongoing_tournament_is_reschedulable(
    client: TestClient, session: Session, setup: Setup
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.ONGOING
    session.add(row)
    session.commit()

    assert _patch(client, setup, "M1", R1 + MINUTE).status_code == 200


def test_other_organizer_and_plain_account_forbidden(
    client: TestClient, session: Session, setup: Setup
) -> None:
    other = make_account(session, organizer=True)
    plain = make_account(session)
    session.commit()

    for account in (other, plain):
        before = setup.snapshot()
        response = _patch(
            client, setup, "M1", R1 + MINUTE, headers=_headers(client, account)
        )
        assert response.status_code == 403
        assert setup.snapshot() == before
    response = _patch(client, setup, "M1", R1 + MINUTE, headers=_headers(client, other))
    assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"
    response = _patch(client, setup, "M1", R1 + MINUTE, headers=_headers(client, plain))
    assert _code(response) == "ORGANIZER_REQUIRED"
    response = client.get(setup.list_url, headers=_headers(client, plain))
    assert _code(response) == "ORGANIZER_REQUIRED"


def test_non_owner_gets_403_before_state_conflicts(
    client: TestClient, session: Session, setup: Setup
) -> None:
    other = make_account(session, organizer=True)
    match = setup.row("M1")
    assert match.team_a_id is not None
    session.add(
        CheckIn(
            match_id=match.id,
            team_id=match.team_a_id,
            account_id=setup.organizer.id,
            at=NOW,
        )
    )
    setup.update("M2", status=MatchStatus.LIVE)
    headers = _headers(client, other)

    # 已報到、進行中的場次：非主辦方一律 403，不透露場次狀態
    for code in ("M1", "M2"):
        response = _patch(client, setup, code, R1 + MINUTE, headers=headers)
        assert response.status_code == 403
        assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.FINISHED
    session.add(row)
    session.commit()
    response = _patch(client, setup, "M3", R1 + MINUTE, headers=headers)
    assert response.status_code == 403
    assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"


def test_requires_login(client: TestClient, setup: Setup) -> None:
    response = client.patch(setup.url("M1"), json={"scheduled_at": R1.isoformat()})
    assert response.status_code == 401
    assert client.get(setup.list_url).status_code == 401


def test_naive_datetime_is_422(client: TestClient, setup: Setup) -> None:
    before = setup.snapshot()

    response = _patch(client, setup, "M1", "2026-11-02T10:00:00")

    assert response.status_code == 422
    assert setup.snapshot() == before


def test_unknown_match_and_tournament_are_404(
    client: TestClient,
    session: Session,
    setup: Setup,
    fake_registration: FakeRegistration,
) -> None:
    other, other_bracket = draw_with(session, fake_registration, 4)
    session.commit()
    foreign = other_bracket.matches[0]
    headers = _headers(client, setup.organizer)
    body = {"scheduled_at": R1.isoformat()}

    wrong = client.patch(
        f"{API}/tournaments/{setup.tournament_id}/matches/{foreign.id}/schedule",
        json=body,
        headers=headers,
    )
    missing = client.patch(
        f"{API}/tournaments/{setup.tournament_id}/matches/{uuid.uuid4()}/schedule",
        json=body,
        headers=headers,
    )
    no_tournament = client.patch(
        f"{API}/tournaments/{uuid.uuid4()}/matches/{foreign.id}/schedule",
        json=body,
        headers=headers,
    )

    assert wrong.status_code == 404 and _code(wrong) == "MATCH_NOT_FOUND"
    assert missing.status_code == 404 and _code(missing) == "MATCH_NOT_FOUND"
    assert no_tournament.status_code == 404
    assert _code(no_tournament) == "TOURNAMENT_NOT_FOUND"


# ---------------------------------------------------------------- 列表


def test_list_matches_in_order_with_info(client: TestClient, setup: Setup) -> None:
    response = client.get(setup.list_url, headers=_headers(client, setup.organizer))

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [r["code"] for r in rows] == [f"M{i}" for i in range(1, 9)]
    assert (rows[6]["is_third_place"], rows[7]["is_third_place"]) == (False, True)
    m1, m5, m7 = rows[0], rows[4], rows[6]
    assert m1["team_a"]["name"].startswith("隊伍")
    assert m1["referee_account_id"] is None
    assert m1["reschedule"]["can_reschedule"] is True
    assert m1["reschedule"]["reason"] is None
    assert m1["reschedule"]["earliest"].startswith("2026-10-18T11:30:00")
    assert m1["reschedule"]["latest"].startswith("2026-10-26T11:15:00")
    assert m5["team_a"] is None and m5["source_a"] == "M1 勝者"
    assert m7["reschedule"]["latest"] is None
    assert rows[7]["source_a"] == "M5 敗者"


def test_list_reasons(client: TestClient, session: Session, setup: Setup) -> None:
    match = setup.row("M1")
    assert match.team_a_id is not None
    session.add(
        CheckIn(
            match_id=match.id,
            team_id=match.team_a_id,
            account_id=setup.organizer.id,
            at=NOW,
        )
    )
    setup.update("M2", status=MatchStatus.LIVE)
    setup.update("M7", scheduled_at=NOW + timedelta(hours=1))
    setup.update("M8", scheduled_at=NOW + timedelta(hours=1))

    rows = {
        r["code"]: r["reschedule"]
        for r in client.get(
            setup.list_url, headers=_headers(client, setup.organizer)
        ).json()
    }

    assert rows["M1"] == {
        "can_reschedule": False,
        "reason": "already_checked_in",
        "earliest": None,
        "latest": None,
    }
    assert rows["M2"]["reason"] == "match_not_reschedulable"
    assert rows["M5"]["reason"] == "no_valid_time"
    assert rows["M5"]["can_reschedule"] is False
    assert rows["M5"]["earliest"] is not None


def test_list_tournament_not_reschedulable(
    client: TestClient, session: Session, setup: Setup
) -> None:
    row = session.get(Tournament, setup.tournament_id)
    assert row is not None
    row.status = TournamentStatus.FINISHED
    session.add(row)
    session.commit()

    rows = client.get(setup.list_url, headers=_headers(client, setup.organizer)).json()

    assert {r["reschedule"]["reason"] for r in rows} == {"tournament_not_reschedulable"}


def test_list_forbidden_and_not_drawn(
    client: TestClient, session: Session, setup: Setup
) -> None:
    other = make_account(session, organizer=True)
    plain = make_account(session)
    organizer = setup.organizer
    undrawn = tournament_in(session, TournamentStatus.CLOSED, organizer=organizer)
    session.commit()

    for account in (other, plain):
        response = client.get(setup.list_url, headers=_headers(client, account))
        assert response.status_code == 403
    # 非主辦方查未抽籤的賽事：先 403，不透露有沒有對戰表
    response = client.get(
        f"{API}/tournaments/{undrawn.id}/manage/matches",
        headers=_headers(client, other),
    )
    assert response.status_code == 403
    assert _code(response) == "TOURNAMENT_OWNER_REQUIRED"
    response = client.get(
        f"{API}/tournaments/{undrawn.id}/manage/matches",
        headers=_headers(client, organizer),
    )
    assert response.status_code == 404
    assert _code(response) == "BRACKET_NOT_FOUND"
    response = client.get(
        f"{API}/tournaments/{uuid.uuid4()}/manage/matches",
        headers=_headers(client, organizer),
    )
    assert _code(response) == "TOURNAMENT_NOT_FOUND"


def _info(client: TestClient, setup: Setup, code: str) -> dict[str, object]:
    rows = client.get(setup.list_url, headers=_headers(client, setup.organizer)).json()
    return next(r for r in rows if r["code"] == code)["reschedule"]


@pytest.mark.parametrize("code", [f"M{i}" for i in range(1, 9)])
def test_list_window_matches_reschedule_api(
    client: TestClient, session: Session, setup: Setup, code: str
) -> None:
    # 初始排程下每一場都有可選範圍；一場改完後，相鄰場次的範圍會隨之變動，所以逐場重新取列表
    info = _info(client, setup, code)
    assert info["can_reschedule"] is True
    earliest = datetime.fromisoformat(str(info["earliest"]))
    latest = (
        None if info["latest"] is None else datetime.fromisoformat(str(info["latest"]))
    )

    if latest is not None:
        _assert_rejected(
            client, session, setup, code, latest + MINUTE, "RESCHEDULE_AFTER_NEXT_MATCH"
        )
    _assert_rejected(
        client,
        session,
        setup,
        code,
        earliest - MINUTE,
        "RESCHEDULE_BEFORE_NOW" if earliest == FLOOR else "RESCHEDULE_BEFORE_FEEDER",
    )
    if latest is not None:
        assert _patch(client, setup, code, latest).status_code == 200
        assert setup.row(code).scheduled_at == latest
        # 改完後再用新範圍驗證最早邊界
        info = _info(client, setup, code)
        earliest = datetime.fromisoformat(str(info["earliest"]))
    assert _patch(client, setup, code, earliest).status_code == 200
    assert setup.row(code).scheduled_at == earliest
