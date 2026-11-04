"""core.authz 的資源層級判斷：只比對傳入的資料，不查資料庫。"""

import uuid
from dataclasses import dataclass

import pytest

from app.core import authz
from app.core.errors import BusinessError


@dataclass
class _Tournament:
    organizer_id: uuid.UUID


def test_tournament_owner_passes_for_organizer() -> None:
    organizer_id = uuid.uuid4()
    authz.ensure_tournament_owner(_Tournament(organizer_id), organizer_id)


def test_tournament_owner_rejects_other_account() -> None:
    with pytest.raises(BusinessError) as exc_info:
        authz.ensure_tournament_owner(_Tournament(uuid.uuid4()), uuid.uuid4())
    assert exc_info.value.code == "TOURNAMENT_OWNER_REQUIRED"
    assert exc_info.value.status_code == 403


def test_referee_of_tournament_a_is_not_referee_of_tournament_b() -> None:
    tournament_a, tournament_b = uuid.uuid4(), uuid.uuid4()
    referee_of = [tournament_a]

    assert authz.is_tournament_referee(referee_of, tournament_a) is True
    assert authz.is_tournament_referee(referee_of, tournament_b) is False
    assert authz.is_tournament_referee([], tournament_a) is False


def test_ensure_tournament_referee() -> None:
    tournament_a, tournament_b = uuid.uuid4(), uuid.uuid4()

    authz.ensure_tournament_referee({tournament_a}, tournament_a)
    with pytest.raises(BusinessError) as exc_info:
        authz.ensure_tournament_referee({tournament_a}, tournament_b)
    assert exc_info.value.code == "TOURNAMENT_REFEREE_REQUIRED"
    assert exc_info.value.status_code == 403
