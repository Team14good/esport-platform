"""Story 6.5 第二階段 C：公開對戰表的「已取消資格」與隊伍取消資格理由 API。

隊伍用真的 registration（3.1 的 API 建隊、直接改報名狀態），抽籤用真的 competition
`draw`，取消資格經處理檢舉 API（`resolve_report`）。frozen_clock 凍結在 2026-10-18 11:00 UTC。
"""

import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import clock
from app.core.config import settings
from app.modules.competition import service as competition_service
from app.modules.competition.models import Match, MatchOutcome
from app.modules.disputes.models import Report, ReportStatus
from app.modules.identity.models import Account
from app.modules.tournaments.models import TournamentRead, TournamentStatus
from tests.competition.test_confirm_advance import _confirm, _enter_appeal, _rows
from tests.disputes.test_reports import _team
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


@dataclass
class World:
    tournament: TournamentRead
    organizer: Account
    teams: list[uuid.UUID]
    captains: dict[uuid.UUID, Account]

    @property
    def tid(self) -> uuid.UUID:
        return self.tournament.id


def _world(client: TestClient, session: Session, count: int) -> World:
    organizer = _make_account(session)
    organizer.is_organizer = True
    session.add(organizer)
    session.flush()
    tournament = _tournament(session, organizer=organizer)
    teams: list[uuid.UUID] = []
    captains: dict[uuid.UUID, Account] = {}
    for k in range(1, count + 1):
        body, captain = _team(client, session, tournament.id, f"隊伍{k}")
        team_id = uuid.UUID(body["id"])
        teams.append(team_id)
        captains[team_id] = captain
    return World(tournament, organizer, teams, captains)


def _drawn(client: TestClient, session: Session, count: int) -> World:
    w = _world(client, session, count)
    _set_status(session, w.tid, TournamentStatus.CLOSED)
    competition_service.draw(
        session, tournament_id=w.tid, actor_id=w.organizer.id, rng=random.Random(7)
    )
    return w


def _disqualify(
    client: TestClient, session: Session, w: World, team: uuid.UUID
) -> None:
    """對 `team` 的檢舉以屬實處理（經 API）。"""
    report = Report(
        tournament_id=w.tid,
        reporter_team_id=next(t for t in w.teams if t != team),
        filed_by=_make_account(session).id,
        reported_team_id=team,
        filed_at=clock.now() - timedelta(minutes=5),
        description="隊員不是本校學生。",
        status=ReportStatus.OPEN,
    )
    session.add(report)
    session.flush()
    response = client.post(
        f"{API}/organizer/reports/{report.id}/resolution",
        json={"substantiated": True, "reason": REASON},
        headers=_auth(w.organizer),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "substantiated"


def _first_round(session: Session, w: World) -> list[Match]:
    return sorted(
        (m for m in _rows(session, w.tid).values() if m.round_no == 1),
        key=lambda m: m.slot_no,
    )


def _public_bracket(client: TestClient, w: World) -> dict[str, Any]:
    response = client.get(f"{API}/tournaments/{w.tid}/bracket")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _refs(body: dict[str, Any]) -> dict[str, bool]:
    """公開對戰表裡每支隊伍的 `disqualified`（同一隊每次出現都要一致）。"""
    flags: dict[str, bool] = {}
    for match in body["matches"]:
        for ref in (match["team_a"], match["team_b"]):
            if ref is None:
                continue
            assert set(ref) == {"id", "name", "disqualified"}
            assert (
                flags.setdefault(ref["id"], ref["disqualified"]) == ref["disqualified"]
            )
    return flags


def _reason(client: TestClient, team: uuid.UUID, account: Account | None) -> Any:
    headers = _auth(account) if account is not None else {}
    return client.get(f"{API}/teams/{team}/disqualification", headers=headers)


# ---------------------------------------------------------------- 公開對戰表


def test_winner_replaced_is_marked_and_replacement_is_not(
    client: TestClient, session: Session
) -> None:
    """AC：X 贏第 1 輪後被取消資格，X 帶標記、Y 出現在第 2 輪原位置，第 1 輪結果不變。"""
    w = _drawn(client, session, 8)
    first = _first_round(session, w)[0]
    winner, loser = first.team_a_id, first.team_b_id
    assert winner is not None and loser is not None
    _confirm(session, first, MatchOutcome.PLAYED, winner)
    assert _refs(_public_bracket(client, w)) == {str(t): False for t in w.teams}

    _disqualify(client, session, w, winner)

    body = _public_bracket(client, w)
    flags = _refs(body)
    assert flags[str(winner)] is True
    assert [team for team, dq in flags.items() if dq] == [str(winner)]
    by_id = {m["id"]: m for m in body["matches"]}
    one = by_id[str(first.id)]
    assert one["winner_id"] == str(winner)
    assert one["outcome"] == "played"
    second = by_id[str(first.next_match_id)]
    second_ids = {
        ref["id"] for ref in (second["team_a"], second["team_b"]) if ref is not None
    }
    assert str(loser) in second_ids
    assert str(winner) not in second_ids


def test_disqualified_in_appeal_window_keeps_existing_mark(
    client: TestClient, session: Session
) -> None:
    """申訴期中被取消資格：該場以 `disqualified` 判負照舊，參照也帶 `disqualified=true`。"""
    w = _drawn(client, session, 4)
    first = _first_round(session, w)[0]
    team_x, team_y = first.team_a_id, first.team_b_id
    assert team_x is not None and team_y is not None
    _enter_appeal(
        session,
        first,
        outcome=MatchOutcome.PLAYED,
        winner_id=team_x,
        deadline=clock.now() + timedelta(minutes=30),
    )

    _disqualify(client, session, w, team_x)

    body = _public_bracket(client, w)
    match = next(m for m in body["matches"] if m["id"] == str(first.id))
    assert match["outcome"] == "disqualified"
    assert match["winner_id"] == str(team_y)
    refs = {
        ref["id"]: ref["disqualified"] for ref in (match["team_a"], match["team_b"])
    }
    assert refs == {str(team_x): True, str(team_y): False}

    # 公開單場同樣帶出
    detail = client.get(f"{API}/tournaments/{w.tid}/matches/{first.id}")
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert {
        data["team_a"]["id"]: data["team_a"]["disqualified"],
        data["team_b"]["id"]: data["team_b"]["disqualified"],
    } == {str(team_x): True, str(team_y): False}


def test_disqualified_before_draw_bracket_not_found_and_reason_shown(
    client: TestClient, session: Session
) -> None:
    w = _world(client, session, 3)
    team = w.teams[0]

    _disqualify(client, session, w, team)

    assert client.get(f"{API}/tournaments/{w.tid}/bracket").status_code == 404
    response = _reason(client, team, w.captains[team])
    assert response.status_code == 200, response.text
    assert response.json()["reason"] == REASON


# ---------------------------------------------------------------- 取消資格理由


def test_member_reads_reason_and_handled_at(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session, 4)
    team = w.teams[1]
    _disqualify(client, session, w, team)

    response = _reason(client, team, w.captains[team])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reason"] == REASON
    assert body["handled_at"] is not None
    assert set(body) == {"reason", "handled_at"}


def test_non_member_is_forbidden_and_anonymous_unauthorized(
    client: TestClient, session: Session
) -> None:
    w = _drawn(client, session, 4)
    team = w.teams[1]
    _disqualify(client, session, w, team)

    other = _reason(client, team, w.captains[w.teams[2]])
    assert other.status_code == 403, other.text
    assert _error_code(other) == "TEAM_MEMBER_REQUIRED"
    assert _reason(client, team, w.organizer).status_code == 403
    assert _reason(client, uuid.uuid4(), w.captains[team]).status_code == 403
    assert _reason(client, team, None).status_code == 401


def test_not_disqualified_is_null(client: TestClient, session: Session) -> None:
    w = _drawn(client, session, 4)
    _disqualify(client, session, w, w.teams[0])

    response = _reason(client, w.teams[1], w.captains[w.teams[1]])

    assert response.status_code == 200, response.text
    assert response.json() is None


def test_substantiated_after_end_without_disqualification_is_null(
    client: TestClient, session: Session
) -> None:
    """賽事已結束只記錄屬實：報名沒有改為取消資格，不顯示理由。"""
    w = _world(client, session, 3)
    _set_status(session, w.tid, TournamentStatus.FINISHED)
    _disqualify(client, session, w, w.teams[0])

    response = _reason(client, w.teams[0], w.captains[w.teams[0]])

    assert response.status_code == 200, response.text
    assert response.json() is None
