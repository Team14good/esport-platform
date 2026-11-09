"""disputes 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。

賽事只透過 tournaments 的 `get_tournament`、`lock_tournament`；隊伍與報名只透過
registration 的 `find_team_of_account`、`get_team`、`get_registration`、
`list_teams_by_status`、`get_team_names`、`is_captain`；場次只透過 competition 的
`get_match`、`get_public_match`、`lock_match`、`mark_appealed`、`uphold_result`、
`correct_result`、`replay_match`、`get_replay_window`（contracts/disputes.md）。
"""

import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import BinaryIO

from sqlmodel import Session

from app.core import audit, authz, clock, events, storage
from app.core.errors import BusinessError, FieldError
from app.modules.competition import service as competition_service
from app.modules.competition.models import (
    GameScoreIn,
    MatchRead,
    MatchStatus,
    RescheduleInfo,
)
from app.modules.disputes import repository
from app.modules.disputes.models import (
    APPEAL_DESCRIPTION_MAX_LENGTH,
    APPEAL_REASON_MAX_LENGTH,
    REPORT_DESCRIPTION_MAX_LENGTH,
    Appeal,
    AppealDecision,
    AppealFiled,
    AppealGroup,
    AppealItem,
    AppealRead,
    AppealResolved,
    AppealState,
    AppealStateReason,
    AppealStatus,
    OpenDisputeItem,
    OpenDisputes,
    PublicAppealResult,
    Report,
    ReportableTeam,
    ReportFiled,
    ReportRead,
    ReportStatus,
)
from app.modules.registration import service as registration_service
from app.modules.registration.models import RegistrationStatus, TeamRead
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus

# 可檢舉、可被檢舉的報名狀態：待分配、正取、候補、已參賽
REPORTABLE_STATUSES = frozenset(
    {
        RegistrationStatus.PENDING,
        RegistrationStatus.ACCEPTED,
        RegistrationStatus.WAITLISTED,
        RegistrationStatus.DRAWN,
    }
)

_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png"}


# ---------------------------------------------------------------- 錯誤


def _report_not_allowed(message: str) -> BusinessError:
    return BusinessError("REPORT_NOT_ALLOWED", message, status_code=409)


def _captain_required() -> BusinessError:
    # 與 6.1 申訴、competition 報到相同的錯誤碼（2026-11-09 與 B 協議），
    # 不用 `ensure_captain` 的 `TEAM_CAPTAIN_REQUIRED`
    return BusinessError("CAPTAIN_REQUIRED", "只有隊長可以提出檢舉。", status_code=403)


def _team_not_found() -> BusinessError:
    return BusinessError("TEAM_NOT_FOUND", "找不到這支隊伍。", status_code=404)


def _report_not_found() -> BusinessError:
    return BusinessError("REPORT_NOT_FOUND", "找不到這筆檢舉。", status_code=404)


def _file_not_found() -> BusinessError:
    return BusinessError("FILE_NOT_FOUND", "找不到這個檔案", status_code=404)


# ---------------------------------------------------------------- 檢舉人資格


def _ensure_tournament_reportable(tournament: TournamentRead) -> None:
    if tournament.status == TournamentStatus.FINISHED:
        raise _report_not_allowed("賽事已結束，不能提出檢舉。")
    if tournament.status == TournamentStatus.CANCELLED:
        raise _report_not_allowed("賽事已取消，不能提出檢舉。")


def _reporter_team(
    session: Session, tournament: TournamentRead, account_id: uuid.UUID
) -> TeamRead:
    """賽事未結束、登入者是該賽事四種報名狀態之一的隊伍隊長；回傳檢舉人的隊伍。"""
    _ensure_tournament_reportable(tournament)
    team = registration_service.find_team_of_account(
        session, tournament_id=tournament.id, account_id=account_id
    )
    if team is None or not any(
        member.account_id == account_id and member.role == authz.CAPTAIN_ROLE
        for member in team.members
    ):
        raise _captain_required()
    registration = registration_service.get_registration(session, team_id=team.id)
    if registration.status not in REPORTABLE_STATUSES:
        raise _report_not_allowed("本隊的報名尚未送出或已不在賽事中，不能提出檢舉。")
    return team


def _clean_description(description: str) -> str:
    cleaned = description.strip()
    if not 1 <= len(cleaned) <= REPORT_DESCRIPTION_MAX_LENGTH:
        raise FieldError(
            "REPORT_DESCRIPTION_INVALID",
            "說明須為 1～1000 字。",
            loc=("body", "description"),
        )
    return cleaned


def _to_read(report: Report, names: dict[uuid.UUID, str]) -> ReportRead:
    return ReportRead(
        id=report.id,
        tournament_id=report.tournament_id,
        reporter_team_id=report.reporter_team_id,
        reporter_team_name=names.get(report.reporter_team_id, ""),
        reported_team_id=report.reported_team_id,
        reported_team_name=names.get(report.reported_team_id, ""),
        filed_by=report.filed_by,
        filed_at=report.filed_at,
        description=report.description,
        has_attachment=report.attachment_key is not None,
        status=report.status,
        reason=report.reason,
        handled_by=report.handled_by,
        handled_at=report.handled_at,
    )


# ---------------------------------------------------------------- 公開函式


@dataclass(frozen=True)
class FiledReport:
    """`file_report` 的內部結果（只給 router）：commit 失敗時 router 用鍵值刪掉新檔。"""

    report: ReportRead
    attachment_key: str | None


def list_reportable_teams(
    session: Session, *, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> list[ReportableTeam]:
    """S20 選單：檢舉人資格檢查後，回同賽事四種報名狀態、不是自己的隊伍（依隊名、再依 id）。

    檢舉人資格不符時拋與 `file_report` 相同的錯誤。
    """
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    reporter = _reporter_team(session, tournament, account_id)
    open_ids = repository.list_open_reported_team_ids(session, reporter.id)
    teams = registration_service.list_teams_by_status(
        session, tournament_id=tournament.id, statuses=REPORTABLE_STATUSES
    )
    return sorted(
        (
            ReportableTeam(
                id=team.id, name=team.name, has_open_report=team.id in open_ids
            )
            for team in teams
            if team.id != reporter.id
        ),
        key=lambda team: (team.name, team.id),
    )


def file_report(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    account_id: uuid.UUID,
    reported_team_id: uuid.UUID,
    description: str,
    attachment: BinaryIO | None,
    content_type: str | None,
) -> FiledReport:
    """隊長對同賽事的他隊提出檢舉（S20）。

    先鎖住賽事再依序檢查（錯誤碼見 spec-6-4）：賽事未結束、檢舉人是四種報名狀態隊伍的
    隊長、對象不是自己、對象在此賽事且為四種狀態、對同一對象沒有處理中的檢舉、說明
    1～1000 字；全部通過才存附件。建立檢舉、寫 `report.filed`、發 `ReportFiled` 在同一
    交易；存檔後任何步驟失敗都先刪新檔再往外拋。被檢舉隊伍的狀態不變。
    """
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    reporter = _reporter_team(session, tournament, account_id)
    if reported_team_id == reporter.id:
        raise BusinessError("REPORT_SELF", "不能檢舉自己的隊伍。", status_code=422)
    try:
        reported = registration_service.get_team(session, team_id=reported_team_id)
    except BusinessError as exc:
        if exc.code == "TEAM_NOT_FOUND":
            raise _team_not_found() from None
        raise
    if reported.tournament_id != tournament.id:
        raise _team_not_found()
    reported_registration = registration_service.get_registration(
        session, team_id=reported.id
    )
    if reported_registration.status not in REPORTABLE_STATUSES:
        raise _report_not_allowed("這支隊伍的報名尚未送出或已不在賽事中，不能檢舉。")
    if reported.id in repository.list_open_reported_team_ids(session, reporter.id):
        raise BusinessError(
            "REPORT_ALREADY_FILED", "已檢舉這支隊伍，主辦方處理中。", status_code=409
        )
    cleaned = _clean_description(description)

    attachment_key: str | None = None
    if attachment is not None:
        attachment_key = storage.save_image(attachment, content_type=content_type)
    try:
        report = repository.add_report(
            session,
            Report(
                tournament_id=tournament.id,
                reporter_team_id=reporter.id,
                filed_by=account_id,
                reported_team_id=reported.id,
                filed_at=clock.now(),
                description=cleaned,
                attachment_key=attachment_key,
                status=ReportStatus.OPEN,
            ),
        )
        audit.record(
            session,
            actor_id=account_id,
            tournament_id=tournament.id,
            action="report.filed",
            entity_type="report",
            entity_id=report.id,
            before=None,
            after={
                "reporter_team_id": reporter.id,
                "reported_team_id": reported.id,
                "description": cleaned,
                "has_attachment": attachment_key is not None,
            },
        )
        events.publish(
            session,
            ReportFiled(
                report_id=report.id,
                tournament_id=tournament.id,
                reported_team_id=reported.id,
            ),
        )
        read = _to_read(
            report, {reporter.id: reporter.name, reported.id: reported.name}
        )
    except BaseException:
        if attachment_key is not None:
            storage.delete_file(attachment_key)
        raise
    return FiledReport(report=read, attachment_key=attachment_key)


def list_tournament_reports(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> list[ReportRead]:
    """S33：該賽事主辦方才能看；處理中在前，各組依提出時間由舊到新、再依 id。"""
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    reports = repository.list_tournament_reports(session, tournament.id)
    team_ids = {r.reporter_team_id for r in reports} | {
        r.reported_team_id for r in reports
    }
    names = registration_service.get_team_names(session, team_ids=list(team_ids))
    return [_to_read(report, names) for report in reports]


def open_report_attachment(
    session: Session, *, report_id: uuid.UUID, actor_id: uuid.UUID
) -> tuple[BinaryIO, str]:
    """開啟檢舉附件，回傳（檔案, media type）；呼叫端負責關閉檔案。

    檢舉不存在 404 `REPORT_NOT_FOUND` → 非該賽事主辦方 403 `TOURNAMENT_OWNER_REQUIRED`
    → 沒有附件 404 `FILE_NOT_FOUND`。
    """
    report = repository.get_report(session, report_id)
    if report is None:
        raise _report_not_found()
    tournament = tournaments_service.get_tournament(
        session, tournament_id=report.tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    if report.attachment_key is None:
        raise _file_not_found()
    media_type = _MEDIA_TYPES.get(PurePath(report.attachment_key).suffix)
    if media_type is None:
        raise _file_not_found()
    return storage.open_file(report.attachment_key), media_type


# ---------------------------------------------------------------- 申訴（6.1）

# 可以提出申訴的場次狀態：申訴期、申訴中（第二隊在原期限內仍可申訴）
_APPEALABLE = frozenset({MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED})

# 賽事已結束或已取消時不能申訴（與 6.4 檢舉一致）
_ENDED_TOURNAMENT = frozenset({TournamentStatus.FINISHED, TournamentStatus.CANCELLED})

# 決賽與季軍賽沒有等待結果的下一場：處理期限為申訴提出後 1 小時
_FINAL_HANDLING_TIME = timedelta(hours=1)

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


def _appeal_to_read(appeal: Appeal) -> AppealRead:
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


def _clean_appeal_description(value: str) -> str:
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
    session: Session,
    *,
    tournament: TournamentRead,
    match: MatchRead,
    account_id: uuid.UUID,
    now: datetime,
) -> tuple[uuid.UUID | None, bool, AppealStateReason | None]:
    """提出申訴與狀態查詢共用的檢查（呼叫端已視需要鎖住賽事與場次）。

    回傳（登入者的隊伍、本隊是否已申訴、不能提出的原因）。順序：隊長、賽事已結束或
    已取消與場次狀態（皆為 `not_appealable`）、期限、本隊已申訴。`already_filed` 不論其他原因都照實回傳（S4 優先顯示）。
    「本隊已申訴」只看未結案的申訴：重新比賽後上一輪的申訴已結案，原申訴隊可以再申訴。
    """
    team_id = _captain_team(session, match=match, account_id=account_id)
    if team_id is None:
        return None, False, "not_captain"
    already = repository.find_open_team_appeal(session, match.id, team_id) is not None
    if tournament.status in _ENDED_TOURNAMENT or match.status not in _APPEALABLE:
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
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    _team_id, already, reason = _evaluate(
        session,
        tournament=tournament,
        match=match,
        account_id=account_id,
        now=clock.now(),
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
    該賽事（404）→ 隊長（403）→ 賽事已結束或已取消、場次狀態（409）→ 期限（409）→ 本隊沒有未結案的申訴
    （409，未結案申訴的部分唯一索引是最後防線）。全部通過才存附件；之後任何失敗都刪掉附件。場次仍是申訴期時轉為
    申訴中（competition `mark_appealed`），寫 `appeal.filed`、發 `AppealFiled`。
    任何拒絕都不寫資料、紀錄與事件。
    """
    cleaned = _clean_appeal_description(description)
    # 先以不鎖定的讀取確認場次屬於該賽事：不存在的場次不必排隊等鎖
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    competition_service.lock_match(session, match_id=match_id)
    match = competition_service.get_match(session, match_id=match_id)
    now = clock.now()
    team_id, _already, reason = _evaluate(
        session, tournament=tournament, match=match, account_id=account_id, now=now
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
    return FiledAppeal(appeal=_appeal_to_read(appeal), attachment_key=key)


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
        raise _file_not_found()
    media_type = _MEDIA_TYPES.get(PurePath(appeal.attachment_key).suffix)
    if media_type is None:
        raise _file_not_found()
    return storage.open_file(appeal.attachment_key), media_type


# ---------------------------------------------------------------- 處理申訴（6.2）


def _owned_tournament(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """賽事不存在 404；不是主辦方 403 `TOURNAMENT_OWNER_REQUIRED`。"""
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)


def _clean_appeal_reason(value: str) -> str:
    """處理理由：與申訴說明相同的清理，去頭尾空白後 1～1000 字；否則拋 422（指向 reason）。"""
    cleaned = "".join(ch for ch in value if _keeps(ch)).strip()
    if not cleaned:
        raise FieldError(
            "APPEAL_REASON_REQUIRED", "請輸入處理理由", loc=("body", "reason")
        )
    if len(cleaned) > APPEAL_REASON_MAX_LENGTH:
        raise FieldError(
            "APPEAL_REASON_TOO_LONG",
            f"處理理由最多 {APPEAL_REASON_MAX_LENGTH} 個字",
            loc=("body", "reason"),
        )
    return cleaned


def resolve_appeals(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
    decision: AppealDecision,
    reason: str,
    games: Sequence[GameScoreIn] | None,
    replay_at: datetime | None,
) -> list[AppealRead]:
    """主辦方處理同一場次的申訴：未結案的申訴一次以相同決定與理由結案（FR-31）。

    順序：理由（422）→ 決定需要的欄位（`corrected` 的 `games`、`rematch` 的 `replay_at`，
    422）→ 場次屬於該賽事（404）→ `lock_tournament` → 主辦方（403）→ `lock_match` →
    有未結案申訴（409 `NO_OPEN_APPEALS`）→ competition `uphold_result`／
    `correct_result`／`replay_match`（狀態、outcome 等檢查在 competition）→ 結案（寫
    `handled_by`、`handled_at`，不改 `filed_by`）→ 操作紀錄 `appeal.resolved`（更正時含
    前後各局）→ 發 `AppealResolved`。另一隊的申訴期限未到也可以處理；處理後場次不再是
    申訴期或申訴中，另一隊不能再申訴。任何拒絕都不寫資料。
    """
    cleaned = _clean_appeal_reason(reason)
    if decision == AppealDecision.CORRECTED and games is None:
        raise FieldError(
            "APPEAL_GAMES_REQUIRED", "請輸入更正後的各局", loc=("body", "games")
        )
    if decision == AppealDecision.REMATCH and replay_at is None:
        raise FieldError(
            "APPEAL_REPLAY_AT_REQUIRED",
            "請選擇重新比賽的時間",
            loc=("body", "replay_at"),
        )
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    competition_service.lock_match(session, match_id=match_id)
    appeals = repository.list_open_match_appeals(session, match_id)
    if not appeals:
        raise BusinessError(
            "NO_OPEN_APPEALS", "這場比賽沒有待處理的申訴。", status_code=409
        )
    match = competition_service.get_match(session, match_id=match_id)
    before: dict[str, object] = {
        "match_status": match.status,
        "outcome": match.outcome,
        "winner_id": match.winner_id,
    }
    after: dict[str, object] = {}
    if decision == AppealDecision.UPHELD:
        competition_service.uphold_result(session, match_id=match_id, actor_id=actor_id)
    elif decision == AppealDecision.CORRECTED:
        assert games is not None  # 上面已檢查
        correction = competition_service.correct_result(
            session, match_id=match_id, games=games, actor_id=actor_id
        )
        before["games"] = correction.before_games
        after["games"] = correction.after_games
    else:
        assert replay_at is not None  # 上面已檢查
        before["scheduled_at"] = match.scheduled_at
        competition_service.replay_match(
            session, match_id=match_id, scheduled_at=replay_at, actor_id=actor_id
        )
    match = competition_service.get_match(session, match_id=match_id)
    if decision == AppealDecision.REMATCH:
        after["scheduled_at"] = match.scheduled_at

    repository.close_appeals(
        session,
        appeals,
        decision=decision,
        reason=cleaned,
        handled_by=actor_id,
        handled_at=clock.now(),
    )
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament_id,
        action="appeal.resolved",
        entity_type="match",
        entity_id=match_id,
        before=before,
        after={
            "decision": decision,
            "reason": cleaned,
            "appeal_ids": [appeal.id for appeal in appeals],
            "match_status": match.status,
            "outcome": match.outcome,
            "winner_id": match.winner_id,
            **after,
        },
    )
    events.publish(session, AppealResolved(match_id=match_id, decision=decision))
    return [_appeal_to_read(appeal) for appeal in appeals]


def list_tournament_appeals(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> list[AppealGroup]:
    """S32：該賽事的申訴依場次分組；有未結案申訴的場次在前，依最早一筆未結案申訴的
    提出時間（重新比賽後再申訴時不以上一輪的申訴排序）；已結案的場次依最早提出時間。

    只有該賽事主辦方（403 `TOURNAMENT_OWNER_REQUIRED`）。附件只回 `has_attachment`。
    """
    _owned_tournament(session, tournament_id=tournament_id, actor_id=actor_id)
    by_match: dict[uuid.UUID, list[Appeal]] = {}
    all_appeals = repository.list_tournament_appeals(session, tournament_id)
    for appeal in all_appeals:
        by_match.setdefault(appeal.match_id, []).append(appeal)
    # 隊名依申訴的 team_id 查：場次的隊伍被頂替（6.5）後，原申訴隊仍顯示隊名
    names = registration_service.get_team_names(
        session, team_ids=list({appeal.team_id for appeal in all_appeals})
    )
    groups: list[AppealGroup] = []
    for match_id, appeals in by_match.items():
        detail = competition_service.get_public_match(
            session, tournament_id=tournament_id, match_id=match_id
        )
        groups.append(
            AppealGroup(
                match_id=detail.id,
                match_code=detail.code,
                round_name=detail.round_name,
                is_third_place=detail.is_third_place,
                scheduled_at=detail.scheduled_at,
                match_status=detail.status,
                outcome=detail.outcome,
                winner_id=detail.winner_id,
                wins_a=detail.wins_a,
                wins_b=detail.wins_b,
                score_type=detail.score_type,
                best_of=detail.best_of,
                games=detail.games,
                team_a=detail.team_a,
                team_b=detail.team_b,
                has_open=any(a.status == AppealStatus.OPEN for a in appeals),
                appeals=[
                    AppealItem(
                        **_appeal_to_read(appeal).model_dump(),
                        team_name=names.get(appeal.team_id, "未知隊伍"),
                    )
                    for appeal in appeals
                ],
            )
        )

    def sort_key(group: AppealGroup) -> tuple[bool, datetime]:
        open_at = [a.filed_at for a in group.appeals if a.status == AppealStatus.OPEN]
        return (
            not group.has_open,
            min(open_at) if open_at else group.appeals[0].filed_at,
        )

    groups.sort(key=sort_key)
    return groups


def _handling_deadline(
    session: Session,
    *,
    match: MatchRead,
    filed_at: datetime,
    cache: dict[uuid.UUID, MatchRead],
) -> datetime:
    """處理期限：等待這場結果的下一場（勝隊、敗隊去的場次）中最早的預定時間。

    決賽與季軍賽沒有下一場，為申訴提出後 1 小時。
    """
    times: list[datetime] = []
    for next_id in (match.next_match_id, match.loser_next_match_id):
        if next_id is None:
            continue
        if next_id not in cache:
            cache[next_id] = competition_service.get_match(session, match_id=next_id)
        times.append(cache[next_id].scheduled_at)
    return min(times) if times else filed_at + _FINAL_HANDLING_TIME


def count_open_disputes(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> OpenDisputes:
    """S27 待處理：未結案的申訴與每筆的處理期限，依期限由近到遠；檢舉在 6.5 接上前一律 0（檢舉的處理期限由 6.5 決定）。

    只有該賽事主辦方（403 `TOURNAMENT_OWNER_REQUIRED`）。
    """
    _owned_tournament(session, tournament_id=tournament_id, actor_id=actor_id)
    cache: dict[uuid.UUID, MatchRead] = {}
    items: list[OpenDisputeItem] = []
    for appeal in repository.list_tournament_appeals(
        session, tournament_id, open_only=True
    ):
        if appeal.match_id not in cache:
            cache[appeal.match_id] = competition_service.get_match(
                session, match_id=appeal.match_id
            )
        match = cache[appeal.match_id]
        items.append(
            OpenDisputeItem(
                kind="appeal",
                id=appeal.id,
                match_id=match.id,
                match_code=match.code,
                filed_at=appeal.filed_at,
                deadline=_handling_deadline(
                    session, match=match, filed_at=appeal.filed_at, cache=cache
                ),
            )
        )
    items.sort(key=lambda item: (item.deadline, item.filed_at))
    return OpenDisputes(
        appeals=len(items),
        reports=0,
        earliest_deadline=items[0].deadline if items else None,
        items=items,
    )


def get_public_appeal_result(
    session: Session, *, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> PublicAppealResult:
    """S4：已確認的場次經申訴處理的結果（`upheld`／`corrected`）；不含申訴內容（AD-19）。

    沒有申訴、尚未處理、場次未確認或處理結果是重新比賽時為 None。場次不屬於該賽事 404。
    """
    match = _match_in_tournament(
        session, tournament_id=tournament_id, match_id=match_id
    )
    if match.status != MatchStatus.CONFIRMED:
        return PublicAppealResult(decision=None)
    handled = [
        (appeal.handled_at, appeal.decision)
        for appeal in repository.list_match_appeals(session, match_id)
        if appeal.status == AppealStatus.CLOSED and appeal.handled_at is not None
    ]
    if not handled:
        return PublicAppealResult(decision=None)
    _at, decision = max(handled, key=lambda pair: pair[0])
    if decision == AppealDecision.UPHELD:
        return PublicAppealResult(decision="upheld")
    if decision == AppealDecision.CORRECTED:
        return PublicAppealResult(decision="corrected")
    return PublicAppealResult(decision=None)


def get_replay_window(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> RescheduleInfo:
    """S32 重新比賽的時間範圍（competition `get_replay_window`）；只有該賽事主辦方。"""
    _owned_tournament(session, tournament_id=tournament_id, actor_id=actor_id)
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    return competition_service.get_replay_window(session, match_id=match_id)
