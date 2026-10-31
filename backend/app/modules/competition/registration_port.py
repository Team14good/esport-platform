"""competition 對 registration 的唯一出口（轉接檔）。

抽籤需要的四個 registration 函式（`list_accepted_teams`、`finalize_for_draw`、
`mark_drawn`、`get_team_names`，名稱與簽名見 contracts/competition.md〈二〉）
在呼叫當下才到 `app.modules.registration.service` 查找：C 的函式尚未合併時拋
503 `REGISTRATION_UNAVAILABLE`，合併後不必修改 competition。

這裡只回傳抽籤需要的資料：隊伍 id 與公開對戰樹用的隊名。
"""

import uuid
from collections.abc import Callable, Sequence
from typing import Any, cast

from sqlmodel import Session

from app.core.errors import BusinessError
from app.modules.registration import service as registration_service


class RegistrationUnavailableError(BusinessError):
    """registration 尚未提供抽籤用的函式。

    `BusinessError` 只接受 4xx，但這是「依賴的功能還沒上線」而非使用者違反規則，
    spec 規定回 503，所以建立後才把狀態碼改成 503（全域 handler 直接使用它）。
    """

    def __init__(self) -> None:
        super().__init__(
            "REGISTRATION_UNAVAILABLE",
            "報名功能尚未提供抽籤所需的資料，暫時無法抽籤。",
            status_code=409,
        )
        self.status_code = 503


def _lookup(name: str) -> Callable[..., Any]:
    func = getattr(registration_service, name, None)
    if not callable(func):
        raise RegistrationUnavailableError()
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
    return bool(_lookup("is_captain")(session, team_id=team_id, account_id=account_id))
