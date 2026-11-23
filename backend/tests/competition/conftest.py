"""competition 測試共用：registration 替身、建立指定狀態的賽事、抽籤捷徑。"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import pytest
from sqlmodel import Session, func, select

from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import registration_port, service
from app.modules.competition.models import BracketRead, Match
from app.modules.identity.models import Account
from app.modules.registration import service as registration_service
from app.modules.tournaments.models import (
    Tournament,
    TournamentRead,
    TournamentStatus,
)
from tests.helpers import make_account, make_game, make_tournament


class FrozenClockLike(Protocol):
    """`frozen_clock` fixture 的型別（tests/conftest.py 的 FrozenClock）。"""

    def set(self, at: datetime) -> None: ...

    def advance(self, delta: timedelta) -> None: ...


@dataclass
class FakeRegistration:
    """取代 `registration_port` 的四個函式，記錄呼叫順序與參數。"""

    teams: list[uuid.UUID] = field(default_factory=list)
    names: dict[uuid.UUID, str] | None = None
    calls: list[str] = field(default_factory=list)
    finalized: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    drawn: list[tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]] = field(
        default_factory=list
    )
    # 6.5：隊伍所屬的賽事（`list_accepted_teams` 時記下）與已取消資格的隊伍
    tournament_id: uuid.UUID | None = None
    disqualified: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    # 4.5：候補（依順位，第 1 位先遞補）、隊長與隊員、退賽紀錄、各隊報名狀態
    waitlist: list[uuid.UUID] = field(default_factory=list)
    captains: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    players: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    retired: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    statuses: dict[uuid.UUID, str] = field(default_factory=dict)
    backfilled: list[uuid.UUID] = field(default_factory=list)

    def set_team_count(self, count: int) -> list[uuid.UUID]:
        self.teams = [uuid.uuid4() for _ in range(count)]
        return self.teams

    def list_accepted_teams(
        self, _session: Session, *, tournament_id: uuid.UUID
    ) -> list[uuid.UUID]:
        self.calls.append("list_accepted_teams")
        self.tournament_id = tournament_id
        return list(self.teams)

    def finalize_for_draw(
        self, _session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        self.calls.append("finalize_for_draw")
        self.finalized.append((tournament_id, actor_id))

    def mark_drawn(
        self,
        _session: Session,
        *,
        tournament_id: uuid.UUID,
        team_ids: Sequence[uuid.UUID],
        actor_id: uuid.UUID,
    ) -> None:
        self.calls.append("mark_drawn")
        self.drawn.append((tournament_id, list(team_ids), actor_id))

    def get_team_names(
        self, _session: Session, *, team_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        self.calls.append("get_team_names")
        if self.names is not None:
            return dict(self.names)
        return {team_id: f"隊伍{self.teams.index(team_id) + 1}" for team_id in team_ids}

    def get_registration_state(
        self, _session: Session, *, team_id: uuid.UUID
    ) -> registration_port.RegistrationState:
        self.calls.append("get_registration_state")
        if team_id not in self.teams or self.tournament_id is None:
            raise BusinessError(
                "REGISTRATION_NOT_FOUND", "找不到這支隊伍的報名。", status_code=404
            )
        return registration_port.RegistrationState(
            tournament_id=self.tournament_id,
            disqualified=any(team == team_id for team, _ in self.disqualified),
            status=self.statuses.get(team_id, "drawn"),
        )

    def disqualify_registration(
        self, _session: Session, *, team_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        self.calls.append("disqualify_registration")
        if self.statuses.get(team_id, "drawn") != "drawn":
            raise BusinessError(
                "REGISTRATION_INVALID_TRANSITION",
                "報名目前的狀態不能進行這個操作。",
                status_code=409,
            )
        self.statuses[team_id] = "disqualified"
        self.disqualified.append((team_id, actor_id))

    def add_waitlist(self, count: int) -> list[uuid.UUID]:
        """加入 `count` 支候補隊伍（尚未在 `teams`，遞補後才加入）。"""
        added = [uuid.uuid4() for _ in range(count)]
        self.waitlist.extend(added)
        return added

    def set_captain(self, team_id: uuid.UUID, account_id: uuid.UUID) -> None:
        self.captains[team_id] = account_id
        self.players.setdefault(team_id, set()).add(account_id)

    def get_team_tournament_id(
        self, _session: Session, *, team_id: uuid.UUID
    ) -> uuid.UUID:
        known = [*self.teams, *self.waitlist]
        if team_id not in known or self.tournament_id is None:
            raise BusinessError("TEAM_NOT_FOUND", "找不到這支隊伍。", status_code=404)
        return self.tournament_id

    def is_member(
        self, _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        return account_id in self.players.get(team_id, set())

    def is_captain(
        self, _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        return self.captains.get(team_id) == account_id

    def retire_registration(
        self, _session: Session, *, team_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        self.calls.append("retire_registration")
        if self.statuses.get(team_id, "drawn") != "drawn":
            raise BusinessError(
                "REGISTRATION_INVALID_TRANSITION",
                "報名目前的狀態不能進行這個操作。",
                status_code=409,
            )
        self.statuses[team_id] = "retired"
        self.retired.append((team_id, actor_id))

    def backfill_drawn_from_waitlist(
        self, _session: Session, *, tournament_id: uuid.UUID
    ) -> uuid.UUID | None:
        self.calls.append("backfill_drawn_from_waitlist")
        if not self.waitlist:
            return None
        team_id = self.waitlist.pop(0)
        self.teams.append(team_id)
        self.backfilled.append(team_id)
        return team_id

    def has_backfill_candidate(
        self, _session: Session, *, tournament_id: uuid.UUID, leaving_team_id: uuid.UUID
    ) -> bool:
        return bool(self.waitlist)

    def list_disqualified_team_ids(
        self, _session: Session, *, tournament_id: uuid.UUID
    ) -> set[uuid.UUID]:
        # 公開對戰表每次都會查；不記入 calls，以免改變既有測試的呼叫順序斷言
        if tournament_id != self.tournament_id:
            return set()
        return {team for team, _ in self.disqualified}


@pytest.fixture
def fake_registration(monkeypatch: pytest.MonkeyPatch) -> FakeRegistration:
    fake = FakeRegistration()
    for name in (
        "list_accepted_teams",
        "finalize_for_draw",
        "mark_drawn",
        "get_team_names",
        "get_registration_state",
        "disqualify_registration",
        "list_disqualified_team_ids",
        "get_team_tournament_id",
        "retire_registration",
        "backfill_drawn_from_waitlist",
        "has_backfill_candidate",
    ):
        monkeypatch.setattr(registration_port, name, getattr(fake, name))
    return fake


@pytest.fixture
def registration_without_draw_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    """移除 registration 的四個抽籤函式（C 合併後仍能測 503）。"""
    for name in (
        "list_accepted_teams",
        "finalize_for_draw",
        "mark_drawn",
        "get_team_names",
    ):
        monkeypatch.delattr(registration_service, name, raising=False)


def tournament_in(
    session: Session,
    status: TournamentStatus,
    *,
    organizer: Account | None = None,
    **overrides: object,
) -> TournamentRead:
    """建立賽事後直接改狀態與欄位（測試用，略過轉換規則與建立時的檢查）。

    預設（frozen_clock 下）：開賽 2026-10-26 11:00 UTC、每輪間隔 180 分鐘、
    BO3、每局 40 分鐘、棄權 15 分鐘、申訴 30 分鐘。
    """
    organizer = organizer or make_account(session, organizer=True)
    created = make_tournament(session, organizer=organizer)
    row = session.get(Tournament, created.id)
    assert row is not None
    row.status = status
    for key, value in overrides.items():
        setattr(row, key, value)
    session.add(row)
    session.flush()
    return created


def draw_with(
    session: Session,
    fake: FakeRegistration,
    team_count: int,
    *,
    status: TournamentStatus = TournamentStatus.CLOSED,
    seed: int = 7,
    **overrides: object,
) -> tuple[TournamentRead, BracketRead]:
    organizer = make_account(session, organizer=True)
    tournament = tournament_in(session, status, organizer=organizer, **overrides)
    fake.set_team_count(team_count)
    bracket = service.draw(
        session,
        tournament_id=tournament.id,
        actor_id=organizer.id,
        rng=random.Random(seed),
    )
    return tournament, bracket


# 2.3 分輪 BO 測試用：預設 BO1、4 強 BO3、決賽 BO5
SEMI_BO3_FINAL_BO5 = [
    {"rounds_from_final": 1, "bo": 3},
    {"rounds_from_final": 0, "bo": 5},
]


def draw_with_round_bo(
    session: Session,
    fake: FakeRegistration,
    team_count: int,
    *,
    round_bo: list[dict[str, int]] = SEMI_BO3_FINAL_BO5,
    round_interval_minutes: int = 180,
) -> tuple[TournamentRead, BracketRead]:
    """經建立賽事 API 的同一個 service 帶入分輪 BO（預設 BO1、每局 40 分鐘），
    報名截止後抽籤。開賽 2026-10-26 11:00 UTC（frozen_clock 下）。"""
    organizer = make_account(session, organizer=True)
    game = make_game(session, default_bo=1)
    tournament = make_tournament(
        session,
        organizer=organizer,
        game=game,
        bo=1,
        round_bo=round_bo,
        round_interval_minutes=round_interval_minutes,
    )
    row = session.get(Tournament, tournament.id)
    assert row is not None
    row.status = TournamentStatus.CLOSED
    session.add(row)
    session.flush()
    fake.set_team_count(team_count)
    bracket = service.draw(
        session,
        tournament_id=tournament.id,
        actor_id=organizer.id,
        rng=random.Random(7),
    )
    return tournament, bracket


def count_matches(session: Session, tournament_id: uuid.UUID) -> int:
    statement = select(func.count()).where(Match.tournament_id == tournament_id)
    return session.exec(statement).one()


def count_outbox(session: Session, event_type: str) -> int:
    statement = select(func.count()).where(OutboxEvent.type == event_type)
    return session.exec(statement).one()
