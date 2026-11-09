"""Story 6.5 第二階段 A：主辦方處理檢舉（`resolve_report`）與取消資格後的申訴結案。

檢舉的隊伍有外鍵到 `team.id`，所以用真的隊伍（3.1 的 API 建隊、直接改報名狀態）；
取消資格的情況用真的 competition `draw`（不用 `fake_registration`）。檢舉與申訴直接寫入
資料表。frozen_clock 凍結在 2026-10-18 11:00 UTC。
"""

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, select

from app.core import audit, clock
from app.core.config import settings
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import service as competition_service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.disputes import service
from app.modules.disputes.models import (
    Appeal,
    AppealDecision,
    AppealStatus,
    Report,
    ReportStatus,
)
from app.modules.identity.models import Account
from app.modules.registration.models import RegistrationStatus
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.competition.test_confirm_advance import _confirm, _enter_appeal, _rows
from tests.disputes.test_reports import _registration_status, _team
from tests.registration.test_teams import (
    API,
    _auth,
    _error_code,
    _make_account,
    _set_status,
    _tournament,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")

REASON = "查證屬實：隊員學生證與報名資料不符。"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", directory)
    return directory


# ---------------------------------------------------------------- 測試資料


@dataclass
class World:
    tournament: TournamentRead
    organizer: Account
    teams: list[uuid.UUID]

    @property
    def tid(self) -> uuid.UUID:
        return self.tournament.id


def _world(client: TestClient, session: Session, count: int = 3) -> World:
    """開放報名中的賽事與 `count` 支正取隊伍。"""
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    teams = [
        uuid.UUID(_team(client, session, tournament.id, f"隊伍{k}")[0]["id"])
        for k in range(1, count + 1)
    ]
    return World(tournament, organizer, teams)


def _drawn(client: TestClient, session: Session, count: int) -> World:
    """報名截止後以真的 competition `draw` 抽籤（隊伍改為已參賽）。"""
    w = _world(client, session, count)
    _set_status(session, w.tid, TournamentStatus.CLOSED)
    competition_service.draw(
        session, tournament_id=w.tid, actor_id=w.organizer.id, rng=random.Random(7)
    )
    return w


def _report(
    session: Session,
    w: World,
    reported: uuid.UUID,
    reporter: uuid.UUID | None = None,
    *,
    minutes: int = 0,
) -> Report:
    reporter = reporter or next(t for t in w.teams if t != reported)
    report = Report(
        tournament_id=w.tid,
        reporter_team_id=reporter,
        filed_by=_make_account(session).id,
        reported_team_id=reported,
        filed_at=clock.now() + timedelta(minutes=minutes),
        description="隊員不是本校學生。",
        status=ReportStatus.OPEN,
    )
    session.add(report)
    session.flush()
    return report


def _resolve(
    client: TestClient,
    account: Account,
    report_id: Any,
    *,
    substantiated: bool,
    reason: str = REASON,
) -> Any:
    return client.post(
        f"{API}/organizer/reports/{report_id}/resolution",
        json={"substantiated": substantiated, "reason": reason},
        headers=_auth(account),
    )


def _ok(
    client: TestClient, w: World, report: Report, *, substantiated: bool
) -> dict[str, Any]:
    response = _resolve(client, w.organizer, report.id, substantiated=substantiated)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _fresh(session: Session, report: Report) -> Report:
    session.expire_all()
    row = session.get(Report, report.id)
    assert row is not None
    return row


def _logs(session: Session, w: World, action: str) -> list[audit.AuditLog]:
    return [
        log for log in audit.list_for_tournament(session, w.tid) if log.action == action
    ]


def _events(session: Session, event_type: str) -> list[dict[str, Any]]:
    rows = session.exec(select(OutboxEvent).where(OutboxEvent.type == event_type))
    return [row.payload for row in rows]


def _event_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(OutboxEvent)).one()


def _round(rows: dict[str, Match], round_no: int) -> list[Match]:
    return sorted(
        (m for m in rows.values() if m.round_no == round_no and not m.is_third_place),
        key=lambda m: m.slot_no,
    )


# ---------------------------------------------------------------- 駁回


def test_dismiss_closes_report_only(client: TestClient, session: Session) -> None:
    w = _drawn(client, session, 4)
    rows_before = {
        c: (m.team_a_id, m.team_b_id, m.status)
        for c, m in _rows(session, w.tid).items()
    }
    report = _report(session, w, w.teams[0])

    body = _ok(client, w, report, substantiated=False)

    assert body["status"] == "dismissed"
    assert body["reason"] == REASON
    assert body["handled_by"] == str(w.organizer.id)
    assert body["reported_team_name"] == "隊伍1"
    row = _fresh(session, report)
    assert row.status == ReportStatus.DISMISSED
    assert (row.reason, row.handled_by, row.handled_at) == (
        REASON,
        w.organizer.id,
        clock.now(),
    )
    # 對戰表與報名不變
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.DRAWN
    assert {
        c: (m.team_a_id, m.team_b_id, m.status)
        for c, m in _rows(session, w.tid).items()
    } == rows_before
    logs = _logs(session, w, "report.resolved")
    assert len(logs) == 1
    assert (logs[0].entity_type, logs[0].entity_id, logs[0].actor_id) == (
        "report",
        report.id,
        w.organizer.id,
    )
    assert logs[0].before == {"status": "open", "reason": None}
    assert logs[0].after == {"status": "dismissed", "reason": REASON}
    assert {"report_id": str(report.id), "substantiated": False} in _events(
        session, "ReportResolved"
    )


# ---------------------------------------------------------------- 屬實、賽事未結束


def test_substantiated_before_draw_disqualifies_registration(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])

    body = _ok(client, w, report, substantiated=True)

    assert body["status"] == "substantiated"
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.DISQUALIFIED
    logs = _logs(session, w, "report.resolved")
    assert len(logs) == 1
    assert logs[0].after == {
        "status": "substantiated",
        "reason": REASON,
        "disqualified": True,
        "affected_match_ids": [],
        "replacement_team_id": None,
    }
    assert {"report_id": str(report.id), "substantiated": True} in _events(
        session, "ReportResolved"
    )


def test_substantiated_winner_waiting_is_replaced_by_round_one_loser(
    client: TestClient, session: Session
) -> None:
    """AC：已抽籤、某隊贏了第 1 輪等第 2 輪，屬實後第 1 輪輸給它的隊伍出現在第 2 輪。"""
    w = _drawn(client, session, 8)
    first = _round(_rows(session, w.tid), 1)[0]
    winner, loser = first.team_a_id, first.team_b_id
    assert winner is not None and loser is not None
    _confirm(session, first, MatchOutcome.PLAYED, winner)
    report = _report(session, w, winner)

    body = _ok(client, w, report, substantiated=True)

    assert body["status"] == "substantiated"
    assert _registration_status(session, winner) == RegistrationStatus.DISQUALIFIED
    rows = _rows(session, w.tid)
    second = next(m for m in rows.values() if m.id == first.next_match_id)
    assert loser in (second.team_a_id, second.team_b_id)
    assert winner not in (second.team_a_id, second.team_b_id)
    # 第 1 輪結果不變
    assert rows[first.code].winner_id == winner
    log = _logs(session, w, "report.resolved")[0]
    assert log.after is not None
    assert log.after["affected_match_ids"] == [str(second.id)]
    assert log.after["replacement_team_id"] == str(loser)


def _appealed(session: Session, w: World, match: Match) -> list[Appeal]:
    """場次寫成申訴中（team_a 勝），兩隊各一筆未結案的申訴。"""
    _enter_appeal(
        session,
        match,
        outcome=MatchOutcome.PLAYED,
        winner_id=match.team_a_id,
        deadline=clock.now() + timedelta(minutes=30),
    )
    match.status = MatchStatus.APPEALED
    session.add(match)
    appeals = []
    for i, team_id in enumerate((match.team_a_id, match.team_b_id)):
        assert team_id is not None
        appeal = Appeal(
            tournament_id=w.tid,
            match_id=match.id,
            team_id=team_id,
            filed_by=_make_account(session).id,
            filed_at=clock.now() + timedelta(minutes=i),
            description="比分登錄錯誤。",
            status=AppealStatus.OPEN,
        )
        session.add(appeal)
        appeals.append(appeal)
    session.flush()
    return appeals


def _open_disputes(client: TestClient, w: World) -> dict[str, Any]:
    response = client.get(
        f"{API}/organizer/tournaments/{w.tid}/open-disputes",
        headers=_auth(w.organizer),
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_substantiated_with_appealed_match_closes_appeals(
    client: TestClient, session: Session
) -> None:
    """AC：某隊的場次在申訴中，檢舉屬實後該場判對手獲勝、申訴全部結案，S27 待處理申訴數減少。"""
    w = _drawn(client, session, 8)
    match = _round(_rows(session, w.tid), 1)[0]
    team, opponent = match.team_a_id, match.team_b_id
    appeals = _appealed(session, w, match)
    assert _open_disputes(client, w)["appeals"] == 2
    report = _report(session, w, team)  # type: ignore[arg-type]

    _ok(client, w, report, substantiated=True)

    session.expire_all()
    row = session.get(Match, match.id)
    assert row is not None
    assert (row.status, row.outcome, row.winner_id) == (
        MatchStatus.CONFIRMED,
        MatchOutcome.DISQUALIFIED,
        opponent,
    )
    for appeal in appeals:
        closed = session.get(Appeal, appeal.id)
        assert closed is not None
        assert (
            closed.status,
            closed.decision,
            closed.reason,
            closed.handled_by,
            closed.handled_at,
        ) == (
            AppealStatus.CLOSED,
            AppealDecision.DISQUALIFIED,
            REASON,
            w.organizer.id,
            clock.now(),
        )
        assert closed.filed_by == appeal.filed_by
    assert _open_disputes(client, w)["appeals"] == 0
    logs = _logs(session, w, "appeal.resolved")
    assert len(logs) == 1
    assert (logs[0].entity_type, logs[0].entity_id, logs[0].actor_id) == (
        "match",
        match.id,
        w.organizer.id,
    )
    assert logs[0].before == {
        "match_status": "appealed",
        "outcome": "played",
        "winner_id": str(team),
    }
    assert logs[0].after == {
        "decision": "disqualified",
        "reason": REASON,
        "appeal_ids": [str(a.id) for a in appeals],
        "match_status": "confirmed",
        "outcome": "disqualified",
        "winner_id": str(opponent),
        "report_id": str(report.id),
    }
    assert {"match_id": str(match.id), "decision": "disqualified"} in _events(
        session, "AppealResolved"
    )
    # S4 顯示「取消資格」
    response = client.get(f"{API}/tournaments/{w.tid}/matches/{match.id}/appeal-result")
    assert response.status_code == 200
    assert response.json() == {"decision": "disqualified"}


def test_appeals_of_unaffected_matches_stay_open(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session, 8)
    first, other = _round(_rows(session, w.tid), 1)[:2]
    appeals = _appealed(session, w, other)
    report = _report(session, w, first.team_a_id)  # type: ignore[arg-type]

    _ok(client, w, report, substantiated=True)

    session.expire_all()
    for appeal in appeals:
        row = session.get(Appeal, appeal.id)
        assert row is not None and row.status == AppealStatus.OPEN
    assert _logs(session, w, "appeal.resolved") == []


def test_other_open_reports_against_team_are_closed_together(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, 4)
    target = w.teams[0]
    report = _report(session, w, target, w.teams[1])
    other = _report(session, w, target, w.teams[2], minutes=1)
    unrelated = _report(session, w, w.teams[3], w.teams[1], minutes=2)

    _ok(client, w, report, substantiated=True)

    other_row = _fresh(session, other)
    assert (
        other_row.status,
        other_row.reason,
        other_row.handled_by,
        other_row.handled_at,
    ) == (ReportStatus.SUBSTANTIATED, REASON, w.organizer.id, clock.now())
    assert _fresh(session, unrelated).status == ReportStatus.OPEN
    logs = {log.entity_id: log for log in _logs(session, w, "report.resolved")}
    assert set(logs) == {report.id, other.id}
    assert logs[other.id].after == {
        "status": "substantiated",
        "reason": REASON,
        "with_report_id": str(report.id),
    }
    events = _events(session, "ReportResolved")
    for r in (report, other):
        assert {"report_id": str(r.id), "substantiated": True} in events


def test_disqualify_error_is_returned_and_nothing_changes(
    client: TestClient, session: Session
) -> None:
    """3 隊：輪空入座的隊伍等 M1 勝隊，對手未定 → 409 `DISQUALIFY_OPPONENT_PENDING`。"""
    w = _drawn(client, session, 3)
    rows = _rows(session, w.tid)
    seated = next(
        m
        for m in rows.values()
        if m.status == MatchStatus.SCHEDULED
        and (m.team_a_id is None) != (m.team_b_id is None)
    )
    bye_team = seated.team_a_id or seated.team_b_id
    assert bye_team is not None
    report = _report(session, w, bye_team)
    logs_before = len(audit.list_for_tournament(session, w.tid))
    events_before = _event_count(session)

    response = _resolve(client, w.organizer, report.id, substantiated=True)

    assert response.status_code == 409, response.text
    assert _error_code(response) == "DISQUALIFY_OPPONENT_PENDING"
    row = _fresh(session, report)
    assert (row.status, row.reason, row.handled_by) == (ReportStatus.OPEN, None, None)
    assert _registration_status(session, bye_team) == RegistrationStatus.DRAWN
    assert len(audit.list_for_tournament(session, w.tid)) == logs_before
    assert _event_count(session) == events_before


# ---------------------------------------------------------------- 屬實、賽事已結束或已取消


@pytest.mark.parametrize(
    "status", [TournamentStatus.FINISHED, TournamentStatus.CANCELLED]
)
def test_substantiated_after_end_only_records(
    client: TestClient, session: Session, status: TournamentStatus
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])
    other = _report(session, w, w.teams[0], w.teams[2], minutes=1)
    _set_status(session, w.tid, status)

    body = _ok(client, w, report, substantiated=True)

    assert body["status"] == "substantiated"
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.ACCEPTED
    # 沒有取消資格：其他檢舉維持處理中
    assert _fresh(session, other).status == ReportStatus.OPEN
    logs = _logs(session, w, "report.resolved")
    assert len(logs) == 1
    assert logs[0].after == {"status": "substantiated", "reason": REASON}


# ---------------------------------------------------------------- 拒絕


def test_non_owner_is_forbidden(client: TestClient, session: Session) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])
    stranger = _make_account(session)
    stranger.is_organizer = True
    session.add(stranger)
    session.flush()

    response = _resolve(client, stranger, report.id, substantiated=True)

    assert response.status_code == 403, response.text
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"
    assert _fresh(session, report).status == ReportStatus.OPEN
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.ACCEPTED


@pytest.mark.parametrize("closed", [ReportStatus.DISMISSED, ReportStatus.SUBSTANTIATED])
def test_already_resolved_is_conflict(
    client: TestClient, session: Session, closed: ReportStatus
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])
    report.status = closed
    session.add(report)
    session.flush()

    response = _resolve(client, w.organizer, report.id, substantiated=True)

    assert response.status_code == 409, response.text
    assert _error_code(response) == "REPORT_ALREADY_RESOLVED"
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.ACCEPTED
    assert _logs(session, w, "report.resolved") == []


def test_second_resolution_of_same_report_is_conflict(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])
    _ok(client, w, report, substantiated=False)

    response = _resolve(client, w.organizer, report.id, substantiated=True)

    assert response.status_code == 409
    assert _error_code(response) == "REPORT_ALREADY_RESOLVED"
    assert _fresh(session, report).status == ReportStatus.DISMISSED


def test_unknown_report_is_not_found(client: TestClient, session: Session) -> None:
    w = _world(client, session)

    response = _resolve(client, w.organizer, uuid.uuid4(), substantiated=False)

    assert response.status_code == 404
    assert _error_code(response) == "REPORT_NOT_FOUND"


def test_report_of_another_tournament_is_not_found(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    other = _world(client, session)
    report = _report(session, other, other.teams[0])

    with pytest.raises(BusinessError) as caught:
        service.resolve_report(
            session,
            tournament_id=w.tid,
            report_id=report.id,
            actor_id=w.organizer.id,
            substantiated=False,
            reason=REASON,
        )

    assert (caught.value.code, caught.value.status_code) == ("REPORT_NOT_FOUND", 404)
    assert _fresh(session, report).status == ReportStatus.OPEN


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("", "REPORT_REASON_REQUIRED"),
        ("   \n ", "REPORT_REASON_REQUIRED"),
        ("x" * 1001, "REPORT_REASON_TOO_LONG"),
    ],
)
def test_reason_is_validated(
    client: TestClient, session: Session, reason: str, code: str
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])

    response = _resolve(
        client, w.organizer, report.id, substantiated=True, reason=reason
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert (detail[0]["type"], detail[0]["loc"]) == (code, ["body", "reason"])
    assert _fresh(session, report).status == ReportStatus.OPEN
    assert _registration_status(session, w.teams[0]) == RegistrationStatus.ACCEPTED


def test_reason_is_trimmed_and_1000_chars_allowed(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session)
    report = _report(session, w, w.teams[0])

    response = _resolve(
        client,
        w.organizer,
        report.id,
        substantiated=False,
        reason="  " + "理" * 1000 + "\n",
    )

    assert response.status_code == 200, response.text
    assert _fresh(session, report).reason == "理" * 1000
