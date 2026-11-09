"""Story 5.1 補遺：S12 我的隊伍下一場（`GET /me/next-matches`）。

frozen_clock 凍結在 2026-10-18 11:00 UTC；8 隊抽籤後第一輪 M1～M4 兩隊都已確定。
registration 的 `list_my_teams` 以替身取代（抽籤用的隊伍 id 不是真的隊伍），
經 `registration_port.list_drawn_teams_of_account` 呼叫。
"""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.main  # noqa: F401  確保組裝層已載入
from app.modules.competition import service
from app.modules.competition.models import Match, MatchOutcome, MatchStatus
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, draw_with
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

URL = f"{API}/me/next-matches"


class World:
    """一場 8 隊賽事，加上登入者（`me`）在 registration 替身裡的隊伍清單。"""

    def __init__(
        self,
        session: Session,
        fake: FakeRegistration,
        monkeypatch: pytest.MonkeyPatch,
        team_count: int = 8,
    ) -> None:
        self.session = session
        self.fake = fake
        self.tournament, bracket = draw_with(session, fake, team_count)
        self.bracket = bracket
        self.matches = {m.code: m for m in bracket.matches}
        self.me = make_account(session)
        # (team_id, tournament_id, registration_status)
        self.cards: list[tuple[uuid.UUID, uuid.UUID, str]] = []
        self.calls: list[uuid.UUID] = []

        def list_my_teams(_session: Session, *, account_id: uuid.UUID) -> list[Any]:
            self.calls.append(account_id)
            if account_id != self.me.id:
                return []
            return [
                SimpleNamespace(
                    team_id=team_id,
                    tournament_id=tournament_id,
                    registration_status=status,
                )
                for team_id, tournament_id, status in self.cards
            ]

        monkeypatch.setattr(registration_service, "list_my_teams", list_my_teams)

    def join(self, team_id: uuid.UUID | None, status: str = "drawn") -> uuid.UUID:
        assert team_id is not None
        self.cards.append((team_id, self.tournament.id, status))
        return team_id

    def row(self, code: str) -> Match:
        row = self.session.get(Match, self.matches[code].id)
        assert row is not None
        return row

    def confirm(self, code: str, winner_side: str) -> None:
        """模擬申訴期滿確認並晉級（5.5 `confirm_match` → `advance`）。"""
        tournaments_service.lock_tournament(
            self.session, tournament_id=self.tournament.id
        )
        locked = service.lock_match(self.session, match_id=self.matches[code].id)
        service.transition_match(
            self.session, match=locked, to=MatchStatus.APPEAL_WINDOW
        )
        winner = locked.team_a_id if winner_side == "a" else locked.team_b_id
        service.confirm_match(
            self.session,
            match=locked,
            outcome=MatchOutcome.PLAYED,
            winner_id=winner,
            actor_id=None,
        )
        self.session.commit()


@pytest.fixture
def world(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> World:
    result = World(session, fake_registration, monkeypatch)
    session.commit()
    return result


def _get(client: TestClient, account: Account) -> list[dict[str, Any]]:
    response = client.get(URL, headers=bearer(token_for(client, account)))
    assert response.status_code == 200, response.text
    rows: list[dict[str, Any]] = response.json()
    return rows


def test_scheduled_match_with_both_teams(client: TestClient, world: World) -> None:
    m1 = world.matches["M1"]
    team = world.join(m1.team_a_id)

    (row,) = _get(client, world.me)

    assert row["team_id"] == str(team)
    assert row["id"] == str(m1.id)
    assert row["code"] == "M1"
    assert row["round_name"] == "8 強"
    assert row["status"] == "scheduled"
    assert row["team_a"]["id"] == str(m1.team_a_id)
    assert row["team_b"]["id"] == str(m1.team_b_id)
    assert row["team_b"]["name"]
    opens_at = datetime.fromisoformat(row["check_in_opens_at"])
    assert opens_at == m1.scheduled_at - timedelta(minutes=30)
    assert row["forfeit_deadline"] is not None
    assert world.calls == [world.me.id]


def test_both_sides_of_same_match_each_get_a_row(
    client: TestClient, world: World
) -> None:
    m1 = world.matches["M1"]
    world.join(m1.team_a_id)
    world.join(m1.team_b_id)

    rows = _get(client, world.me)

    assert [(r["team_id"], r["code"]) for r in rows] == [
        (str(m1.team_a_id), "M1"),
        (str(m1.team_b_id), "M1"),
    ]


def test_order_follows_my_teams(client: TestClient, world: World) -> None:
    world.join(world.matches["M3"].team_a_id)
    world.join(world.matches["M1"].team_b_id)

    rows = _get(client, world.me)

    assert [r["code"] for r in rows] == ["M3", "M1"]


def test_winner_moves_to_next_round_with_pending_opponent(
    client: TestClient, world: World
) -> None:
    m1 = world.matches["M1"]
    winner = world.join(m1.team_a_id)
    world.confirm("M1", "a")

    (row,) = _get(client, world.me)

    assert row["team_id"] == str(winner)
    assert row["round_name"] == "4 強"
    assert row["status"] == "scheduled"
    mine, other = (
        ("team_a", "source_b")
        if row["team_a"] and row["team_a"]["id"] == str(winner)
        else ("team_b", "source_a")
    )
    assert row[mine]["id"] == str(winner)
    # 對手未定：沿用 S3 的來源文字（例如「M2 勝者」），沒有報到截止
    assert row[other] and row[other].endswith("勝者")
    assert row["forfeit_deadline"] is None


def test_next_match_updates_when_opponent_decided(
    client: TestClient, world: World
) -> None:
    winner = world.join(world.matches["M1"].team_a_id)
    world.confirm("M1", "a")
    first = _get(client, world.me)[0]
    world.confirm("M2", "b")

    (row,) = _get(client, world.me)

    assert row["id"] == first["id"]
    teams = {row["team_a"]["id"], row["team_b"]["id"]}
    assert teams == {str(winner), str(world.matches["M2"].team_b_id)}
    assert row["forfeit_deadline"] is not None


def test_fields_are_per_team_with_mixed_rounds(
    client: TestClient, world: World
) -> None:
    """兩隊在不同輪：報到截止各自依自己那一場判斷（不沿用別隊的場次）。"""
    world.join(world.matches["M3"].team_a_id)
    world.join(world.matches["M1"].team_a_id)
    world.confirm("M1", "a")

    rows = {r["code"]: r for r in _get(client, world.me)}

    assert rows["M3"]["forfeit_deadline"] is not None
    assert rows["M3"]["round_name"] == "8 強"
    assert rows["M5"]["forfeit_deadline"] is None
    assert rows["M5"]["round_name"] == "4 強"


def test_bye_team_next_match_is_round_two(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """6 隊（P=8）：首輪輪空的隊伍直接以第二輪那場為下一場，對手待定時沒有報到截止。"""
    world = World(session, fake_registration, monkeypatch, team_count=6)
    session.commit()
    bye_match = next(
        m for m in world.bracket.matches if m.round_no == 2 and (m.bye_a or m.bye_b)
    )
    bye_team = bye_match.team_a_id if bye_match.bye_a else bye_match.team_b_id
    world.join(bye_team)

    (row,) = _get(client, world.me)

    assert row["id"] == str(bye_match.id)
    assert row["round_name"] == "4 強"
    assert row["status"] == "scheduled"
    pending = "team_b" if bye_match.bye_a else "team_a"
    assert row[pending] is None
    assert row["forfeit_deadline"] is None


def test_semifinal_loser_goes_to_third_place_and_winner_to_final(
    session: Session,
    fake_registration: FakeRegistration,
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    """4 隊：兩場準決賽確認後，敗隊的下一場是季軍賽、勝隊的是決賽。"""
    world = World(session, fake_registration, monkeypatch, team_count=4)
    session.commit()
    semis = [m for m in world.bracket.matches if m.round_no == 1]
    final = next(
        m for m in world.bracket.matches if m.round_no == 2 and not m.is_third_place
    )
    third = next(m for m in world.bracket.matches if m.is_third_place)
    winner = world.join(semis[0].team_a_id)
    loser = world.join(semis[0].team_b_id)
    for semi in semis:
        world.confirm(semi.code, "a")

    rows = {r["team_id"]: r for r in _get(client, world.me)}

    assert rows[str(winner)]["id"] == str(final.id)
    assert rows[str(winner)]["round_name"] == "決賽"
    assert rows[str(loser)]["id"] == str(third.id)
    assert rows[str(loser)]["round_name"] == "季軍賽"
    assert rows[str(loser)]["is_third_place"] is True
    # 兩隊都已確定，季軍賽有報到截止
    assert rows[str(loser)]["forfeit_deadline"] is not None


def test_eliminated_team_has_no_next_match(client: TestClient, world: World) -> None:
    world.join(world.matches["M1"].team_b_id)
    world.confirm("M1", "a")

    assert _get(client, world.me) == []


@pytest.mark.parametrize(
    "status",
    [MatchStatus.LIVE, MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED],
)
def test_unsettled_statuses_still_count(
    client: TestClient, session: Session, world: World, status: MatchStatus
) -> None:
    world.join(world.matches["M1"].team_a_id)
    world.row("M1").status = status
    session.commit()

    (row,) = _get(client, world.me)

    assert row["code"] == "M1"
    assert row["status"] == status.value
    # 只有待開打給報到截止
    assert row["forfeit_deadline"] is None


def test_voided_match_is_not_next(
    client: TestClient, session: Session, world: World
) -> None:
    world.join(world.matches["M1"].team_a_id)
    world.row("M1").status = MatchStatus.VOIDED
    session.commit()

    assert _get(client, world.me) == []


@pytest.mark.parametrize(
    "status", ["forming", "pending", "accepted", "waitlisted", "disqualified"]
)
def test_only_drawn_teams(client: TestClient, world: World, status: str) -> None:
    world.join(world.matches["M1"].team_a_id, status)

    assert _get(client, world.me) == []


def test_cancelled_tournament_is_skipped(
    client: TestClient, session: Session, world: World
) -> None:
    world.join(world.matches["M1"].team_a_id)
    row = session.get(Tournament, world.tournament.id)
    assert row is not None
    row.status = TournamentStatus.CANCELLED
    session.commit()

    assert _get(client, world.me) == []


def test_team_listed_under_other_tournament_is_ignored(
    client: TestClient, world: World
) -> None:
    """隊伍 id 對到別場賽事的場次時不算（隊伍只屬於一場賽事）。"""
    team_id = world.matches["M1"].team_a_id
    assert team_id is not None
    world.cards.append((team_id, uuid.uuid4(), "drawn"))

    assert _get(client, world.me) == []


def test_no_teams_returns_empty_list(client: TestClient, world: World) -> None:
    assert _get(client, world.me) == []


def test_other_account_sees_nothing(client: TestClient, world: World) -> None:
    world.join(world.matches["M1"].team_a_id)
    stranger = make_account(world.session)
    world.session.commit()

    assert _get(client, stranger) == []


def test_unauthenticated_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401


def test_registration_without_list_my_teams_is_503(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(registration_service, "list_my_teams")

    response = client.get(URL, headers=bearer(token_for(client, world.me)))

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REGISTRATION_UNAVAILABLE"
