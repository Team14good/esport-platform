"""申訴相關的場次操作（Story 6.1 起，B 實作、D 審查）。

disputes 經 `service.py` 的公開函式呼叫這裡（CONTRIBUTING 6.6：competition 的既有函式
不修改，新邏輯放在新增的檔案）。呼叫端先 `lock_tournament`，這裡再 `lock_match`，
以鎖住後的狀態判斷（AD-6）。不 commit（AD-5）。
"""

import uuid

from sqlmodel import Session

from app.modules.competition import service
from app.modules.competition.models import MatchRead, MatchStatus


def mark_appealed(session: Session, *, match_id: uuid.UUID) -> MatchRead:
    """場次由申訴期轉為申訴中（第一筆申訴）；已是申訴中不動（第二隊申訴）。

    其他狀態拋 409 `MATCH_INVALID_TRANSITION`、不改資料。不改 `appeal_deadline`：
    另一隊在原期限內仍可申訴；worker `auto_confirm_expired` 只挑申訴期的場次，
    申訴中的場次等主辦方處理（6.2）。不寫操作紀錄、不發事件（由 disputes 的
    `appeal.filed`、`AppealFiled` 涵蓋）。
    """
    match = service.lock_match(session, match_id=match_id)
    if MatchStatus(match.status) != MatchStatus.APPEALED:
        # 申訴期 → 申訴中；其他狀態由唯一的狀態轉換入口拋 MATCH_INVALID_TRANSITION
        service.transition_match(session, match=match, to=MatchStatus.APPEALED)
    return service.get_match(session, match_id=match_id)
