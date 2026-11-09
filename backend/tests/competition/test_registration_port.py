"""Story 4.1 第二階段：registration 轉接檔在呼叫當下查找 C 的函式。"""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.competition import registration_port
from app.modules.registration import service as registration_service
from app.modules.registration.models import MyTeamCard, RegistrationStatus

NAMES = ("list_accepted_teams", "finalize_for_draw", "mark_drawn", "get_team_names")
TOURNAMENT = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
ACTOR = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
TEAM_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEAM_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.mark.parametrize(
    "call",
    [
        lambda s: registration_port.list_accepted_teams(s, tournament_id=TOURNAMENT),
        lambda s: registration_port.finalize_for_draw(
            s, tournament_id=TOURNAMENT, actor_id=ACTOR
        ),
        lambda s: registration_port.mark_drawn(
            s, tournament_id=TOURNAMENT, team_ids=[TEAM_1], actor_id=ACTOR
        ),
        lambda s: registration_port.get_team_names(s, team_ids=[TEAM_1]),
    ],
)
def test_missing_registration_function_is_503(
    session: Session, monkeypatch: pytest.MonkeyPatch, call: Any
) -> None:
    for name in NAMES:
        monkeypatch.delattr(registration_service, name, raising=False)

    with pytest.raises(BusinessError) as excinfo:
        call(session)

    assert (excinfo.value.code, excinfo.value.status_code) == (
        "REGISTRATION_UNAVAILABLE",
        503,
    )


def test_port_forwards_to_registration_service(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def recorder(name: str, result: Any = None) -> Any:
        def func(_session: Session, **kwargs: Any) -> Any:
            calls.append((name, kwargs))
            return result

        return func

    teams = [
        SimpleNamespace(id=TEAM_1, name="甲"),
        SimpleNamespace(id=TEAM_2, name="乙"),
    ]
    monkeypatch.setattr(
        registration_service,
        "list_accepted_teams",
        recorder("list_accepted_teams", teams),
        raising=False,
    )
    monkeypatch.setattr(
        registration_service,
        "finalize_for_draw",
        recorder("finalize_for_draw"),
        raising=False,
    )
    monkeypatch.setattr(
        registration_service, "mark_drawn", recorder("mark_drawn"), raising=False
    )
    monkeypatch.setattr(
        registration_service,
        "get_team_names",
        recorder("get_team_names", {TEAM_1: "甲"}),
        raising=False,
    )

    assert registration_port.list_accepted_teams(session, tournament_id=TOURNAMENT) == [
        TEAM_1,
        TEAM_2,
    ]
    registration_port.finalize_for_draw(
        session, tournament_id=TOURNAMENT, actor_id=ACTOR
    )
    registration_port.mark_drawn(
        session, tournament_id=TOURNAMENT, team_ids=(TEAM_1, TEAM_2), actor_id=ACTOR
    )
    assert registration_port.get_team_names(session, team_ids=[TEAM_1]) == {
        TEAM_1: "甲"
    }

    assert calls == [
        ("list_accepted_teams", {"tournament_id": TOURNAMENT}),
        ("finalize_for_draw", {"tournament_id": TOURNAMENT, "actor_id": ACTOR}),
        (
            "mark_drawn",
            {
                "tournament_id": TOURNAMENT,
                "team_ids": [TEAM_1, TEAM_2],
                "actor_id": ACTOR,
            },
        ),
        ("get_team_names", {"team_ids": [TEAM_1]}),
    ]


def test_get_team_names_with_no_teams_skips_registration(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(registration_service, "get_team_names", raising=False)

    assert registration_port.get_team_names(session, team_ids=[]) == {}


def test_list_drawn_teams_reads_real_my_team_cards(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S12 下一場：用 registration 真正的 `MyTeamCard`，欄位改名時這裡會失敗。"""

    def card(team_id: uuid.UUID, status: RegistrationStatus) -> MyTeamCard:
        return MyTeamCard(
            team_id=team_id,
            team_name="隊伍",
            tournament_id=TOURNAMENT,
            tournament_name="賽事",
            game_name="遊戲",
            registration_status=status,
            waitlist_position=None,
            waitlist_reason=None,
            representative_backfill=None,
            waitlist_phase=None,
        )

    calls: list[uuid.UUID] = []

    def list_my_teams(_session: Session, *, account_id: uuid.UUID) -> list[MyTeamCard]:
        calls.append(account_id)
        return [
            card(TEAM_1, RegistrationStatus.DRAWN),
            card(TEAM_2, RegistrationStatus.ACCEPTED),
        ]

    monkeypatch.setattr(registration_service, "list_my_teams", list_my_teams)

    result = registration_port.list_drawn_teams_of_account(session, account_id=ACTOR)

    assert result == [
        registration_port.DrawnTeamRef(team_id=TEAM_1, tournament_id=TOURNAMENT)
    ]
    assert calls == [ACTOR]
