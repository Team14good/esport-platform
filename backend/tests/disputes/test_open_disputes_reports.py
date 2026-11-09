"""Story 6.5 第二階段 B：S27 待處理清單加入未結案的檢舉。

檢舉的處理期限＝被檢舉隊伍下一場待開打場次的預定時間；沒有下一場時沒有期限，
排在所有有期限的項目之後、依提出時間。測試資料沿用 6.5 第二階段 A 的真隊伍與
真的 competition `draw`。frozen_clock 凍結在 2026-10-18 11:00 UTC。
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.disputes.models import Appeal, AppealStatus, ReportStatus
from tests.competition.test_confirm_advance import _confirm, _enter_appeal, _rows
from tests.disputes.test_resolve_report import (
    World,
    _drawn,
    _open_disputes,
    _report,
    _round,
    _world,
)
from tests.registration.test_teams import API, _auth, _error_code, _make_account

pytestmark = pytest.mark.usefixtures("frozen_clock")


def _same_time(left: str | None, right: datetime) -> bool:
    """API 回的時間字串與資料庫的 datetime 是否相同時刻。"""
    assert left is not None
    return datetime.fromisoformat(left.replace("Z", "+00:00")) == right


def _one_appeal(session: Session, w: World, match: Match) -> Appeal:
    """場次寫成申訴中（team_a 勝），team_b 一筆未結案的申訴。"""
    _enter_appeal(
        session,
        match,
        outcome=MatchOutcome.PLAYED,
        winner_id=match.team_a_id,
        deadline=clock.now() + timedelta(minutes=30),
    )
    match.status = MatchStatus.APPEALED
    session.add(match)
    assert match.team_b_id is not None
    appeal = Appeal(
        tournament_id=w.tid,
        match_id=match.id,
        team_id=match.team_b_id,
        filed_by=_make_account(session).id,
        filed_at=clock.now(),
        description="比分登錄錯誤。",
        status=AppealStatus.OPEN,
    )
    session.add(appeal)
    session.flush()
    return appeal


def test_appeals_and_reports_sorted_by_deadline(
    client: TestClient, session: Session
) -> None:
    """1 筆申訴、2 筆檢舉：計數分開，三筆依處理期限排序，沒有期限的在最後。"""
    w = _drawn(client, session, 8)
    rows = _rows(session, w.tid)
    first, second = _round(rows, 1)[:2]
    next_match = next(m for m in rows.values() if m.id == first.next_match_id)
    appeal = _one_appeal(session, w, first)
    # 第 1 輪申訴中的勝隊：第 2 輪還沒排進去，沒有待開打場次 → 沒有期限
    no_next = _report(session, w, first.team_a_id, second.team_a_id, minutes=-10)  # type: ignore[arg-type]
    # 第 1 輪還沒打的隊伍：期限＝第 1 輪的預定時間（早於申訴等待的第 2 輪）
    upcoming = _report(session, w, second.team_b_id, first.team_b_id, minutes=5)  # type: ignore[arg-type]

    body = _open_disputes(client, w)

    assert (body["appeals"], body["reports"]) == (1, 2)
    assert [(item["kind"], item["id"]) for item in body["items"]] == [
        ("report", str(upcoming.id)),
        ("appeal", str(appeal.id)),
        ("report", str(no_next.id)),
    ]
    report_item, appeal_item, none_item = body["items"]
    assert _same_time(report_item["deadline"], second.scheduled_at)
    assert report_item["team_name"] is not None
    assert (report_item["match_id"], report_item["match_code"]) == (None, None)
    assert _same_time(appeal_item["deadline"], next_match.scheduled_at)
    assert (appeal_item["match_code"], appeal_item["team_name"]) == (first.code, None)
    assert none_item["deadline"] is None
    assert _same_time(body["earliest_deadline"], second.scheduled_at)


def test_report_deadline_is_next_scheduled_match_of_winner(
    client: TestClient, session: Session
) -> None:
    """贏了第 1 輪、等第 2 輪：期限＝第 2 輪的預定時間；已淘汰的隊伍沒有期限。"""
    w = _drawn(client, session, 8)
    first = _round(_rows(session, w.tid), 1)[0]
    winner, loser = first.team_a_id, first.team_b_id
    assert winner is not None and loser is not None
    _confirm(session, first, MatchOutcome.PLAYED, winner)
    rows = _rows(session, w.tid)
    next_match = next(m for m in rows.values() if m.id == first.next_match_id)
    assert winner in (next_match.team_a_id, next_match.team_b_id)
    against_winner = _report(session, w, winner, loser)
    against_loser = _report(session, w, loser, winner, minutes=1)

    body = _open_disputes(client, w)

    items = {item["id"]: item for item in body["items"]}
    assert _same_time(
        items[str(against_winner.id)]["deadline"], next_match.scheduled_at
    )
    assert items[str(against_loser.id)]["deadline"] is None
    assert [item["id"] for item in body["items"]] == [
        str(against_winner.id),
        str(against_loser.id),
    ]


def test_reports_without_deadline_sorted_by_filed_at(
    client: TestClient, session: Session
) -> None:
    """報名期間（還沒抽籤）：檢舉都沒有期限，依提出時間；`earliest_deadline` 為 null。"""
    w = _world(client, session, 3)
    later = _report(session, w, w.teams[0], w.teams[1], minutes=5)
    earlier = _report(session, w, w.teams[1], w.teams[2], minutes=-5)

    body = _open_disputes(client, w)

    assert (body["appeals"], body["reports"]) == (0, 2)
    assert body["earliest_deadline"] is None
    assert [item["id"] for item in body["items"]] == [str(earlier.id), str(later.id)]
    first = body["items"][0]
    assert _same_time(first.pop("filed_at"), earlier.filed_at)
    assert first == {
        "kind": "report",
        "id": str(earlier.id),
        "match_id": None,
        "match_code": None,
        "deadline": None,
        "team_name": "隊伍2",
    }


def test_same_deadline_and_filed_at_ordered_by_id(
    client: TestClient, session: Session
) -> None:
    """同一隊的兩筆檢舉：處理期限與提出時間都相同時依 id，順序固定。"""
    w = _drawn(client, session, 8)
    match = _round(_rows(session, w.tid), 1)[0]
    assert match.team_a_id is not None and match.team_b_id is not None
    other = _round(_rows(session, w.tid), 1)[1]
    assert other.team_a_id is not None
    reports = [
        _report(session, w, match.team_a_id, match.team_b_id),
        _report(session, w, match.team_a_id, other.team_a_id),
    ]

    body = _open_disputes(client, w)

    assert body["items"][0]["deadline"] == body["items"][1]["deadline"]
    assert body["items"][0]["filed_at"] == body["items"][1]["filed_at"]
    assert [item["id"] for item in body["items"]] == [
        str(r.id) for r in sorted(reports, key=lambda r: r.id)
    ]


def test_resolved_reports_and_other_tournaments_are_excluded(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, 3)
    kept = _report(session, w, w.teams[0], w.teams[1])
    for status, reported, reporter in (
        (ReportStatus.DISMISSED, w.teams[1], w.teams[2]),
        (ReportStatus.SUBSTANTIATED, w.teams[2], w.teams[0]),
    ):
        closed = _report(session, w, reported, reporter)
        closed.status = status
        session.add(closed)
    other = _world(client, session, 2)
    _report(session, other, other.teams[0], other.teams[1])
    session.flush()

    body = _open_disputes(client, w)

    assert body["reports"] == 1
    assert [item["id"] for item in body["items"]] == [str(kept.id)]


def test_non_organizer_forbidden(client: TestClient, session: Session) -> None:
    w = _world(client, session, 2)
    _report(session, w, w.teams[0], w.teams[1])
    other = _make_account(session)
    other.is_organizer = True
    session.add(other)
    session.flush()

    response = client.get(
        f"{API}/organizer/tournaments/{w.tid}/open-disputes",
        headers=_auth(other),
    )

    assert response.status_code == 403
    assert _error_code(response) == "TOURNAMENT_OWNER_REQUIRED"
