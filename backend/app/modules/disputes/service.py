"""disputes 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import BinaryIO

from sqlmodel import Session

from app.core import audit, authz, clock, events, storage
from app.core.errors import BusinessError, FieldError
from app.modules.competition import service as competition_service
from app.modules.competition.models import MatchRead, MatchStatus
from app.modules.disputes import repository
from app.modules.disputes.models import (
    APPEAL_DESCRIPTION_MAX_LENGTH,
    Appeal,
    AppealFiled,
    AppealRead,
    AppealState,
    AppealStateReason,
    AppealStatus,
)
from app.modules.registration import service as registration_service
from app.modules.tournaments import service as tournaments_service

# 可以提出申訴的場次狀態：申訴期、申訴中（第二隊在原期限內仍可申訴）
_APPEALABLE = frozenset({MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED})

# 狀態查詢的原因代碼對應提出申訴 API 的錯誤碼、狀態碼與訊息（順序即檢查順序）
_REJECTIONS: dict[AppealStateReason, tuple[str, int, str]] = {
    "not_captain": ("CAPTAIN_REQUIRED", 403, "只有這場比賽兩隊的隊長可以提出申訴。"),
    "not_appealable": ("APPEAL_NOT_ALLOWED", 409, "這場比賽現在不能提出申訴。"),
    "deadline_passed": ("APPEAL_DEADLINE_PASSED", 409, "申訴期已截止。"),
    "already_filed": ("APPEAL_ALREADY_FILED", 409, "你的隊伍已對這場比賽提出申訴。"),
}

# 雙向控制字元（U+202A–U+202E、U+2066–U+2069）：可讓畫面上的文字順序與實際內容不同
_BIDI_CONTROLS = frozenset(
    chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)

# 附件副檔名 → 下載的 Content-Type（core.storage 只存 jpg、png）
_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png"}


@dataclass(frozen=True)
class FiledAppeal:
    """`file_appeal` 的結果：router 在交易提交失敗時要刪掉剛存的附件。"""

    appeal: AppealRead
    attachment_key: str | None


def _rejection(reason: AppealStateReason) -> BusinessError:
    code, status_code, message = _REJECTIONS[reason]
    return BusinessError(code, message, status_code=status_code)


def _match_not_found() -> BusinessError:
    return BusinessError("MATCH_NOT_FOUND", "找不到這個場次。", status_code=404)


def _appeal_not_found() -> BusinessError:
    return BusinessError("APPEAL_NOT_FOUND", "找不到這筆申訴。", status_code=404)


def _to_read(appeal: Appeal) -> AppealRead:
    return AppealRead(
        id=appeal.id,
        tournament_id=appeal.tournament_id,
        match_id=appeal.match_id,
        team_id=appeal.team_id,
        filed_by=appeal.filed_by,
        filed_at=appeal.filed_at,
        description=appeal.description,
        has_attachment=appeal.attachment_key is not None,
        status=AppealStatus(appeal.status),
        decision=appeal.decision,
        reason=appeal.reason,
        handled_by=appeal.handled_by,
        handled_at=appeal.handled_at,
    )


def _keeps(ch: str) -> bool:
    """說明裡保留的字元：換行、tab 與一般字元；去掉其他控制字元與雙向控制字元。

    其他格式字元（例如組合 emoji 的 U+200D）保留，不改動隊長的原文。
    """
    if ch in "\n\t":
        return True
    if ch in _BIDI_CONTROLS:
        return False
    return unicodedata.category(ch) != "Cc"


def _clean_description(value: str) -> str:
    """去掉控制字元（保留換行、tab）與雙向控制字元、去頭尾空白；空白或超過 1000 字拋 422。"""
    cleaned = "".join(ch for ch in value if _keeps(ch)).strip()
    if not cleaned:
        raise FieldError(
            "APPEAL_DESCRIPTION_REQUIRED",
            "請輸入申訴說明",
            loc=("body", "description"),
        )
    if len(cleaned) > APPEAL_DESCRIPTION_MAX_LENGTH:
        raise FieldError(
            "APPEAL_DESCRIPTION_TOO_LONG",
            f"申訴說明最多 {APPEAL_DESCRIPTION_MAX_LENGTH} 個字",
            loc=("body", "description"),
        )
    return cleaned


def _match_in_tournament(
    session: Session, *, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> MatchRead:
    """場次不存在或不屬於該賽事拋 404 `MATCH_NOT_FOUND`（與 competition 的場次 API 一致）。"""
    match = competition_service.get_match(session, match_id=match_id)
    if match.tournament_id != tournament_id:
        raise _match_not_found()
    return match


def _captain_team(
    session: Session, *, match: MatchRead, account_id: uuid.UUID
) -> uuid.UUID | None:
    """登入者是哪一隊的隊長；兩隊都不是（或該方待定）為 None。"""
    for team_id in (match.team_a_id, match.team_b_id):
        if team_id is not None and registration_service.is_captain(
            session, team_id=team_id, account_id=account_id
        ):
            return team_id
    return None


def _evaluate(
    session: Session, *, match: MatchRead, account_id: uuid.UUID, now: datetime
) -> tuple[uuid.UUID | None, bool, AppealStateReason | None]:
    """提出申訴與狀態查詢共用的檢查（呼叫端已視需要鎖住賽事與場次）。

    回傳（登入者的隊伍、本隊是否已申訴、不能提出的原因）。順序：隊長、場次狀態、
    期限、本隊已申訴。`already_filed` 不論其他原因都照實回傳（S4 優先顯示）。
    """
    team_id = _captain_team(session, match=match, account_id=account_id)
    if team_id is None:
        return None, False, "not_captain"
    already = repository.find_team_appeal(session, match.id, team_id) is not None
    if match.status not in _APPEALABLE:
        return team_id, already, "not_appealable"
    if match.appeal_deadline is None or now >= match.appeal_deadline:
        return team_id, already, "deadline_passed"
    if already:
        return team_id, already, "already_filed"
    return team_id, already, None


def get_appeal_state(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> AppealState:
    """登入者對這場的申訴狀態（S4 入口）；`can_file` 為 True 若且唯若現在送出會成功。

    只回本隊的狀態，不透露另一隊有沒有申訴。不是兩隊隊長時 `reason="not_captain"`。
    """
    match = _match_in_tournament(
        session, tournament_id=tournament_id, match_id=match_id
    )
    _team_id, already, reason = _evaluate(
        session, match=match, account_id=account_id, now=clock.now()
    )
    return AppealState(
        can_file=reason is None,
        already_filed=already,
        deadline=match.appeal_deadline if match.status in _APPEALABLE else None,
        reason=reason,
    )


def file_appeal(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
    description: str,
    attachment: BinaryIO | None,
    content_type: str | None,
) -> FiledAppeal:
    """隊長對申訴期內的場次結果提出申訴（FR-30）。

    鎖順序與 worker `auto_confirm_expired` 相同（賽事 → 場次，AD-6），鎖住後才判斷
    狀態與期限，所以與期滿確認只有一方成功。檢查順序：說明欄位（422）→ 場次屬於
    該賽事（404）→ 隊長（403）→ 狀態（409）→ 期限（409）→ 本隊未申訴（409，唯一鍵
    是最後防線）。全部通過才存附件；之後任何失敗都刪掉附件。場次仍是申訴期時轉為
    申訴中（competition `mark_appealed`），寫 `appeal.filed`、發 `AppealFiled`。
    任何拒絕都不寫資料、紀錄與事件。
    """
    cleaned = _clean_description(description)
    # 先以不鎖定的讀取確認場次屬於該賽事：不存在的場次不必排隊等鎖
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    tournaments_service.lock_tournament(session, tournament_id=tournament_id)
    competition_service.lock_match(session, match_id=match_id)
    match = competition_service.get_match(session, match_id=match_id)
    now = clock.now()
    team_id, _already, reason = _evaluate(
        session, match=match, account_id=account_id, now=now
    )
    if reason is not None:
        raise _rejection(reason)
    assert team_id is not None  # 沒有拒絕原因代表已確認是隊長

    key = (
        storage.save_image(attachment, content_type=content_type)
        if attachment is not None
        else None
    )
    try:
        appeal = Appeal(
            tournament_id=tournament_id,
            match_id=match.id,
            team_id=team_id,
            filed_by=account_id,
            filed_at=now,
            description=cleaned,
            attachment_key=key,
            status=AppealStatus.OPEN,
        )
        if not repository.add_appeal(session, appeal):
            raise _rejection("already_filed")
        status_before = match.status
        if status_before == MatchStatus.APPEAL_WINDOW:
            match = competition_service.mark_appealed(session, match_id=match.id)
        audit.record(
            session,
            actor_id=account_id,
            tournament_id=tournament_id,
            action="appeal.filed",
            entity_type="appeal",
            entity_id=appeal.id,
            before={"match_status": status_before},
            after={
                "match_id": match.id,
                "team_id": team_id,
                "description": cleaned,
                "has_attachment": key is not None,
                "match_status": match.status,
            },
        )
        events.publish(
            session,
            AppealFiled(appeal_id=appeal.id, match_id=match.id, team_id=team_id),
        )
    except BaseException:
        if key is not None:
            storage.delete_file(key)
        raise
    return FiledAppeal(appeal=_to_read(appeal), attachment_key=key)


def open_appeal_attachment(
    session: Session, *, appeal_id: uuid.UUID, actor_id: uuid.UUID
) -> tuple[BinaryIO, str]:
    """申訴附件（二進位串流、Content-Type）；只有該賽事主辦方能下載（AD-15）。

    申訴不存在拋 404 `APPEAL_NOT_FOUND`；非主辦方 403 `TOURNAMENT_OWNER_REQUIRED`；
    沒有附件或檔案不見拋 404 `FILE_NOT_FOUND`。呼叫端負責關閉串流。
    """
    appeal = repository.get_appeal(session, appeal_id)
    if appeal is None:
        raise _appeal_not_found()
    tournament = tournaments_service.get_tournament(
        session, tournament_id=appeal.tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    if appeal.attachment_key is None:
        raise BusinessError("FILE_NOT_FOUND", "找不到這個檔案", status_code=404)
    media_type = _MEDIA_TYPES.get(
        PurePath(appeal.attachment_key).suffix, "application/octet-stream"
    )
    return storage.open_file(appeal.attachment_key), media_type
