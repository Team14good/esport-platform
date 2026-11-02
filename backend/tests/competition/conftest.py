"""competition 測試共用：registration 替身、建立指定狀態的賽事、抽籤捷徑。"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import pytest
from sqlmodel import Session, func, select

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
from tests.helpers import make_account, make_tournament


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

    def set_team_count(self, count: int) -> list[uuid.UUID]:
        self.teams = [uuid.uuid4() for _ in range(count)]
        return self.teams

    def list_accepted_teams(
        self, _session: Session, *, tournament_id: uuid.UUID
    ) -> list[uuid.UUID]:
        self.calls.append("list_accepted_teams")
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


@pytest.fixture
def fake_registration(monkeypatch: pytest.MonkeyPatch) -> FakeRegistration:
    fake = FakeRegistration()
    for name in (
        "list_accepted_teams",
        "finalize_for_draw",
        "mark_drawn",
        "get_team_names",
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


def count_matches(session: Session, tournament_id: uuid.UUID) -> int:
    statement = select(func.count()).where(Match.tournament_id == tournament_id)
    return session.exec(statement).one()


def count_outbox(session: Session, event_type: str) -> int:
    statement = select(func.count()).where(OutboxEvent.type == event_type)
    return session.exec(statement).one()
