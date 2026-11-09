"""competition 對 registration 的唯一出口（轉接檔）。

抽籤需要的四個 registration 函式（`list_accepted_teams`、`finalize_for_draw`、
`mark_drawn`、`get_team_names`，名稱與簽名見 contracts/competition.md〈二〉）
在呼叫當下才到 `app.modules.registration.service` 查找：C 的函式尚未合併時拋
503 `REGISTRATION_UNAVAILABLE`，合併後不必修改 competition。

這裡只回傳 competition 需要的資料：隊伍 id、公開對戰樹用的隊名，以及 S12 下一場用的
「登入者所屬、已參賽的隊伍」。
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.registration import service as registration_service

# registration 的報名狀態值（`RegistrationStatus.DISQUALIFIED`，StrEnum 可與字串比較）
_DISQUALIFIED = "disqualified"


class RegistrationUnavailableError(BusinessError):
    """registration 尚未提供 competition 需要的函式（抽籤、報到）。

    `BusinessError` 只接受 4xx，但這是「依賴的功能還沒上線」而非使用者違反規則，
    spec 規定回 503，所以建立後才把狀態碼改成 503（全域 handler 直接使用它）。
    """

    def __init__(self, action: str = "抽籤") -> None:
        super().__init__(
            "REGISTRATION_UNAVAILABLE",
            f"報名功能尚未提供{action}所需的資料，暫時無法{action}。",
            status_code=409,
        )
        self.status_code = 503


def _lookup(name: str, *, action: str = "抽籤") -> Callable[..., Any]:
    func = getattr(registration_service, name, None)
    if not callable(func):
        raise RegistrationUnavailableError(action)
    return cast(Callable[..., Any], func)


def list_accepted_teams(
    session: Session, *, tournament_id: uuid.UUID
) -> list[uuid.UUID]:
    """正取隊伍的 id（registration 回傳 `TeamRead`，這裡只取 `id`）。"""
    teams = _lookup("list_accepted_teams")(session, tournament_id=tournament_id)
    return [team.id for team in teams]


def finalize_for_draw(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """開放報名中提前抽籤時，請 registration 先完成優先期分配與截止補位。"""
    _lookup("finalize_for_draw")(
        session, tournament_id=tournament_id, actor_id=actor_id
    )


def mark_drawn(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    team_ids: Sequence[uuid.UUID],
    actor_id: uuid.UUID,
) -> None:
    """把抽籤的隊伍由正取標為已參賽。"""
    _lookup("mark_drawn")(
        session, tournament_id=tournament_id, team_ids=list(team_ids), actor_id=actor_id
    )


def get_team_names(
    session: Session, *, team_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """一次查多隊的隊名（公開對戰樹用，避免 N+1）。"""
    if not team_ids:
        return {}
    return dict(_lookup("get_team_names")(session, team_ids=list(team_ids)))


def is_captain(session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    """帳號是不是該隊的隊長（報到用）；registration 尚未提供時拋 503。"""
    lookup = _lookup("is_captain", action="報到")
    return bool(lookup(session, team_id=team_id, account_id=account_id))


def is_member(session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    """帳號是不是該隊的隊員（指派裁判用）；registration 尚未提供時拋 503。"""
    lookup = _lookup("is_member", action="指派裁判")
    return bool(lookup(session, team_id=team_id, account_id=account_id))


@dataclass(frozen=True)
class DrawnTeamRef:
    """登入者所屬、報名狀態為已參賽（`drawn`）的一支隊伍。"""

    team_id: uuid.UUID
    tournament_id: uuid.UUID


def list_drawn_teams_of_account(
    session: Session, *, account_id: uuid.UUID
) -> list[DrawnTeamRef]:
    """帳號加入、且已參賽的隊伍（S12 下一場用），順序沿用 registration `list_my_teams`。

    registration 回傳 `MyTeamCard`，這裡只讀 `team_id`、`tournament_id`、`registration_status`；
    尚未提供時拋 503。
    """
    cards = _lookup("list_my_teams", action="查詢下一場")(
        session, account_id=account_id
    )
    return [
        DrawnTeamRef(team_id=card.team_id, tournament_id=card.tournament_id)
        for card in cards
        if card.registration_status == "drawn"
    ]


@dataclass(frozen=True)
class RegistrationState:
    """取消資格判斷需要的報名資料：所屬賽事、是否已取消資格。"""

    tournament_id: uuid.UUID
    disqualified: bool


def get_registration_state(
    session: Session, *, team_id: uuid.UUID
) -> RegistrationState:
    """隊伍的報名所屬賽事與是否已取消資格（6.5）；報名不存在由 registration 拋 404。"""
    registration = _lookup("get_registration", action="取消資格")(
        session, team_id=team_id
    )
    return RegistrationState(
        tournament_id=registration.tournament_id,
        disqualified=registration.status == _DISQUALIFIED,
    )


def disqualify_registration(
    session: Session, *, team_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """把隊伍的報名改為取消資格（6.5）；registration 尚未提供時拋 503。"""
    _lookup("disqualify_registration", action="取消資格")(
        session, team_id=team_id, actor_id=actor_id
    )
