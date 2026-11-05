"""Story 4.4 S13：我執法的場次（`GET /me/referee/matches`）與身分清單的「裁判」。

frozen_clock 凍結在 2026-10-18 11:00 UTC；8 隊抽籤後第一輪 M1～M4 兩隊都已確定。
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

import app.main  # noqa: F401  確保組裝層已載入
from app.core import clock
from app.modules.competition.models import CheckIn, Match, MatchStatus
from app.modules.identity import service as identity_service
from app.modules.identity.models import Account, AccountRead, IdentityKey
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import FakeRegistration, draw_with
from tests.helpers import API, bearer, make_account, token_for

pytestmark = pytest.mark.usefixtures("frozen_clock")

URL = f"{API}/me/referee/matches"
IDENTITIES = f"{API}/accounts/me/identities"


class World:
    def __init__(self, session: Session, fake: FakeRegistration) -> None:
        self.session = session
        self.tournament, bracket = draw_with(session, fake, 8)
        self.matches = {m.code: m for m in bracket.matches}
        organizer = session.get(Account, self.tournament.organizer_id)
        assert organizer is not None
        self.organizer = organizer

    def invite(
        self, tournament_id: uuid.UUID, organizer: Account, who: Account
    ) -> None:
        invitation = tournaments_service.invite_referee(
            self.session, tournament_id=tournament_id, actor_id=organizer.id
        )
        tournaments_service.accept_invitation(
            self.session, token=invitation.token, account_id=who.id
        )
        self.session.commit()

    def referee(self) -> Account:
        account = make_account(self.session)
        self.invite(self.tournament.id, self.organizer, account)
        return account

    def _referee_url(self, code: str) -> str:
        return (
            f"{API}/tournaments/{self.tournament.id}"
            f"/matches/{self.matches[code].id}/referee"
        )

    def assign(self, client: TestClient, code: str, referee: Account) -> None:
        response = client.put(
            self._referee_url(code),
            json={"account_id": str(referee.id)},
            headers=bearer(token_for(client, self.organizer)),
        )
        assert response.status_code == 200, response.text

    def unassign(self, client: TestClient, code: str) -> None:
        response = client.delete(
            self._referee_url(code),
            headers=bearer(token_for(client, self.organizer)),
        )
        assert response.status_code == 200, response.text

    def row(self, code: str) -> Match:
        row = self.session.get(Match, self.matches[code].id)
        assert row is not None
        return row

    def check_in(self, code: str, *, sides: str = "ab") -> None:
        match = self.matches[code]
        for side in sides:
            team = match.team_a_id if side == "a" else match.team_b_id
            assert team is not None
            self.session.add(
                CheckIn(
                    match_id=match.id,
                    team_id=team,
                    account_id=self.organizer.id,
                    at=clock.now(),
                )
            )
        self.session.commit()


@pytest.fixture
def world(session: Session, fake_registration: FakeRegistration) -> World:
    result = World(session, fake_registration)
    session.commit()
    return result


def _get(client: TestClient, account: Account) -> list[dict[str, Any]]:
    response = client.get(URL, headers=bearer(token_for(client, account)))
    assert response.status_code == 200, response.text
    return response.json()


def _identity_keys(client: TestClient, account: Account) -> list[str]:
    response = client.get(IDENTITIES, headers=bearer(token_for(client, account)))
    return [i["key"] for i in response.json()]


def test_assigned_match_appears_and_disappears_when_unassigned(
    client: TestClient, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)

    (group,) = _get(client, referee)
    assert group["tournament"] == {
        "id": str(world.tournament.id),
        "name": world.tournament.name,
    }
    (match,) = group["matches"]
    assert match["id"] == str(world.matches["M1"].id)
    assert match["code"] == "M1"
    assert match["round_name"]
    assert match["team_a"] is not None
    assert match["both_checked_in"] is False

    world.unassign(client, "M1")
    assert _get(client, referee) == []


def test_groups_by_tournament_and_sorts_by_time(
    client: TestClient,
    session: Session,
    world: World,
    fake_registration: FakeRegistration,
) -> None:
    other, other_bracket = draw_with(session, fake_registration, 4, seed=3)
    # 替身一次只記得最近一次抽籤的隊伍；改成固定查不到名稱，隊名不是這個測試要驗的
    fake_registration.names = {}
    other_organizer = session.get(Account, other.organizer_id)
    assert other_organizer is not None
    referee = world.referee()
    world.invite(other.id, other_organizer, referee)
    world.assign(client, "M1", referee)
    world.assign(client, "M2", referee)
    other_match = other_bracket.matches[0]
    response = client.put(
        f"{API}/tournaments/{other.id}/matches/{other_match.id}/referee",
        json={"account_id": str(referee.id)},
        headers=bearer(token_for(client, other_organizer)),
    )
    assert response.status_code == 200, response.text

    # 第二個賽事的場次最早；第一個賽事的 M2 排在 M1 之前
    m1_at = world.row("M1").scheduled_at
    other_row = session.get(Match, other_match.id)
    assert other_row is not None
    other_row.scheduled_at = m1_at - timedelta(days=1)
    world.row("M2").scheduled_at = m1_at - timedelta(hours=1)
    session.commit()

    groups = _get(client, referee)
    assert [g["tournament"]["id"] for g in groups] == [
        str(other.id),
        str(world.tournament.id),
    ]
    assert [m["code"] for m in groups[1]["matches"]] == ["M2", "M1"]
    assert len(groups[0]["matches"]) == 1


def test_ready_to_start_needs_both_teams_checked_in(
    client: TestClient, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)
    world.assign(client, "M2", referee)
    world.check_in("M1")
    world.check_in("M2", sides="a")

    (group,) = _get(client, referee)
    flags = {m["code"]: m["both_checked_in"] for m in group["matches"]}
    assert flags == {"M1": True, "M2": False}
    assert all(m["status"] == "scheduled" for m in group["matches"])


def test_voided_match_not_listed(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)
    world.assign(client, "M2", referee)
    world.row("M1").status = MatchStatus.VOIDED
    session.commit()

    (group,) = _get(client, referee)
    assert [m["code"] for m in group["matches"]] == ["M2"]


def test_reassigned_match_leaves_original_referee(
    client: TestClient, world: World
) -> None:
    first, second = world.referee(), world.referee()
    world.assign(client, "M1", first)
    world.assign(client, "M1", second)

    assert _get(client, first) == []
    assert [m["code"] for g in _get(client, second) for m in g["matches"]] == ["M1"]


def test_referee_without_assignments_gets_empty_list(
    client: TestClient, world: World
) -> None:
    assert _get(client, world.referee()) == []


def test_non_referee_account_gets_empty_list(
    client: TestClient, session: Session
) -> None:
    assert _get(client, make_account(session)) == []


def test_unauthenticated_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401


def test_referee_identity_after_my_teams_before_organizer(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    organizer_referee = make_account(session, organizer=True)
    world.invite(world.tournament.id, world.organizer, organizer_referee)

    response = client.get(IDENTITIES, headers=bearer(token_for(client, referee)))
    assert response.json() == [
        {"key": "browse", "label": "瀏覽賽事", "home_path": "/"},
        {"key": "my_teams", "label": "我的隊伍", "home_path": "/me/teams"},
        {"key": "referee", "label": "裁判", "home_path": "/me/referee"},
    ]
    assert _identity_keys(client, organizer_referee) == [
        "browse",
        "my_teams",
        "referee",
        "organizer",
    ]


def test_referee_of_two_tournaments_has_one_identity(
    client: TestClient,
    session: Session,
    world: World,
    fake_registration: FakeRegistration,
) -> None:
    other, _bracket = draw_with(session, fake_registration, 4, seed=3)
    other_organizer = session.get(Account, other.organizer_id)
    assert other_organizer is not None
    referee = world.referee()
    world.invite(other.id, other_organizer, referee)

    assert _identity_keys(client, referee).count("referee") == 1


def test_non_referee_has_no_referee_identity(
    client: TestClient, session: Session
) -> None:
    assert "referee" not in _identity_keys(client, make_account(session))


def _other_tournament(
    session: Session, fake: FakeRegistration, world: World, referee: Account
) -> tuple[Any, Any, Account]:
    """第二個賽事（4 隊），並讓 referee 成為它的裁判。"""
    other, bracket = draw_with(session, fake, 4, seed=3)
    # 替身一次只記得最近一次抽籤的隊伍；隊名不是這些測試要驗的
    fake.names = {}
    organizer = session.get(Account, other.organizer_id)
    assert organizer is not None
    world.invite(other.id, organizer, referee)
    return other, bracket, organizer


def _assign_other(
    client: TestClient, tournament: Any, match: Any, organizer: Account, who: Account
) -> None:
    response = client.put(
        f"{API}/tournaments/{tournament.id}/matches/{match.id}/referee",
        json={"account_id": str(who.id)},
        headers=bearer(token_for(client, organizer)),
    )
    assert response.status_code == 200, response.text


def _set_time(session: Session, match_id: uuid.UUID, at: datetime) -> None:
    row = session.get(Match, match_id)
    assert row is not None
    row.scheduled_at = at
    session.commit()


def _flags(groups: list[dict[str, Any]]) -> dict[str, bool]:
    return {m["code"]: m["both_checked_in"] for g in groups for m in g["matches"]}


def test_pending_side_is_never_ready(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    # M5 兩方都待定；M6 只有 A 方已知且已報到
    world.assign(client, "M5", referee)
    world.assign(client, "M6", referee)
    known = world.matches["M1"].team_a_id
    assert known is not None
    world.row("M6").team_a_id = known
    session.add(
        CheckIn(
            match_id=world.matches["M6"].id,
            team_id=known,
            account_id=world.organizer.id,
            at=clock.now(),
        )
    )
    session.commit()

    assert _flags(_get(client, referee)) == {"M5": False, "M6": False}


def test_check_in_of_team_no_longer_in_match_is_ignored(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)
    world.check_in("M1")
    replacement = world.matches["M2"].team_b_id
    assert replacement is not None
    world.row("M1").team_b_id = replacement
    session.commit()

    assert _flags(_get(client, referee)) == {"M1": False}


def test_group_order_uses_earliest_time(
    client: TestClient,
    session: Session,
    world: World,
    fake_registration: FakeRegistration,
) -> None:
    referee = world.referee()
    other, bracket, organizer = _other_tournament(
        session, fake_registration, world, referee
    )
    day = datetime(2026, 11, 20, tzinfo=clock.now().tzinfo)
    world.assign(client, "M1", referee)
    world.assign(client, "M2", referee)
    _assign_other(client, other, bracket.matches[0], organizer, referee)
    _set_time(session, world.matches["M1"].id, day.replace(hour=1))  # 台北 09:00
    _set_time(session, world.matches["M2"].id, day.replace(hour=12))  # 台北 20:00
    _set_time(session, bracket.matches[0].id, day.replace(hour=4))  # 台北 12:00

    groups = _get(client, referee)
    assert [g["tournament"]["id"] for g in groups] == [
        str(world.tournament.id),
        str(other.id),
    ]


def test_group_tie_broken_by_tournament_name(
    client: TestClient,
    session: Session,
    world: World,
    fake_registration: FakeRegistration,
) -> None:
    referee = world.referee()
    other, bracket, organizer = _other_tournament(
        session, fake_registration, world, referee
    )
    world.assign(client, "M1", referee)
    _assign_other(client, other, bracket.matches[0], organizer, referee)
    at = world.row("M1").scheduled_at
    _set_time(session, bracket.matches[0].id, at)
    for tournament_id, name in ((world.tournament.id, "B盃"), (other.id, "A盃")):
        row = session.get(Tournament, tournament_id)
        assert row is not None
        row.name = name
    session.commit()

    groups = _get(client, referee)
    assert [g["tournament"]["name"] for g in groups] == ["A盃", "B盃"]


def test_match_tie_broken_by_code(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M2", referee)
    world.assign(client, "M1", referee)
    at = world.row("M1").scheduled_at
    _set_time(session, world.matches["M2"].id, at)

    (group,) = _get(client, referee)
    assert [m["code"] for m in group["matches"]] == ["M1", "M2"]


def test_round_names(client: TestClient, world: World) -> None:
    referee = world.referee()
    third = next(c for c, m in world.matches.items() if m.is_third_place)
    final = next(
        c for c, m in world.matches.items() if m.round_no == 3 and not m.is_third_place
    )
    for code in ("M1", "M5", final, third):
        world.assign(client, code, referee)

    (group,) = _get(client, referee)
    names = {m["code"]: m["round_name"] for m in group["matches"]}
    assert names == {"M1": "8 強", "M5": "4 強", final: "決賽", third: "季軍賽"}


def test_live_and_confirmed_matches_are_listed(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)
    world.assign(client, "M2", referee)
    world.row("M1").status = MatchStatus.LIVE
    world.row("M2").status = MatchStatus.CONFIRMED
    session.commit()

    (group,) = _get(client, referee)
    assert {m["code"]: m["status"] for m in group["matches"]} == {
        "M1": "live",
        "M2": "confirmed",
    }


def test_cancelled_tournament_matches_not_listed(
    client: TestClient,
    session: Session,
    world: World,
    fake_registration: FakeRegistration,
) -> None:
    referee = world.referee()
    other, bracket, organizer = _other_tournament(
        session, fake_registration, world, referee
    )
    world.assign(client, "M1", referee)
    _assign_other(client, other, bracket.matches[0], organizer, referee)
    row = session.get(Tournament, world.tournament.id)
    assert row is not None
    row.status = TournamentStatus.CANCELLED
    session.commit()

    groups = _get(client, referee)
    assert [g["tournament"]["id"] for g in groups] == [str(other.id)]


def test_finished_tournament_matches_still_listed(
    client: TestClient, session: Session, world: World
) -> None:
    referee = world.referee()
    world.assign(client, "M1", referee)
    row = session.get(Tournament, world.tournament.id)
    assert row is not None
    row.status = TournamentStatus.FINISHED
    session.commit()

    assert len(_get(client, referee)) == 1


@pytest.fixture
def restore_referee_lookup() -> Iterator[None]:
    previous = identity_service._referee_lookup
    yield
    identity_service._referee_lookup = previous


@pytest.mark.usefixtures("restore_referee_lookup")
def test_no_referee_identity_without_registered_lookup(
    session: Session, world: World
) -> None:
    account = AccountRead.model_validate(world.referee(), from_attributes=True)
    identity_service.register_referee_lookup(None)

    keys = [i.key for i in identity_service.list_identities(session, account)]
    assert IdentityKey.REFEREE not in keys


@pytest.mark.usefixtures("restore_referee_lookup")
def test_failing_lookup_omits_referee_identity(
    client: TestClient,
    world: World,
    caplog: pytest.LogCaptureFixture,
) -> None:
    referee = world.referee()

    def broken(_session: Session, _account_id: uuid.UUID) -> bool:
        raise RuntimeError("boom")

    identity_service.register_referee_lookup(broken)
    with caplog.at_level(logging.ERROR):
        response = client.get(IDENTITIES, headers=bearer(token_for(client, referee)))

    assert response.status_code == 200
    assert [i["key"] for i in response.json()] == ["browse", "my_teams"]
    assert "查詢裁判身分失敗" in caplog.text


@pytest.mark.usefixtures("restore_referee_lookup")
def test_failing_sql_in_lookup_keeps_session_usable(
    session: Session, world: World
) -> None:
    """lookup 的 SQL 失敗後，同一個 session 還能繼續查詢（A 在 #51 的建議）。"""
    referee = world.referee()
    account = AccountRead.model_validate(referee, from_attributes=True)

    def broken_sql(s: Session, _account_id: uuid.UUID) -> bool:
        s.execute(text("SELECT 1 / 0"))
        return True

    identity_service.register_referee_lookup(broken_sql)
    keys = [i.key for i in identity_service.list_identities(session, account)]

    assert IdentityKey.REFEREE not in keys
    assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_composition_registers_referee_lookup(session: Session, world: World) -> None:
    # 不碰註冊：匯入 app.main 的組裝層就該把 tournaments 的查詢接上；
    # 刪掉 app/api/main.py 的 register_referee_lookup 呼叫，這個測試會變紅
    lookup = identity_service._referee_lookup
    assert lookup is not None
    assert lookup(session, world.referee().id) is True
    assert lookup(session, make_account(session).id) is False


def test_platform_admin_who_is_referee_identity_order(
    client: TestClient, session: Session, world: World
) -> None:
    admin = make_account(session, admin=True)
    world.invite(world.tournament.id, world.organizer, admin)

    assert _identity_keys(client, admin) == [
        "browse",
        "my_teams",
        "referee",
        "platform_admin",
    ]
