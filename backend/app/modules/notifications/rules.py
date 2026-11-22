"""各事件的收件規則（Story 1.6；FR-37 對照表，見 spec 的〈收件規則表〉）。

每個 resolver 只經各模組 `service.py` 的公開函式查詢收件人，回傳每人一份
`NotificationDraft`。查不到實體時各模組的 service 會拋 `BusinessError`（404），
resolver 自己判斷查不到時拋 `RecipientsNotFound`，都由 `service.dispatch_event` 記錄後略過。

匯入本模組即完成登錄（`notifications.service` 匯入時就會載入）。
不在這裡登錄的：`MatchResultSubmitted`、`MatchResultConfirmed`、`TeamCheckedIn`
（不在 FR-37 對照表）；2.6 取消賽事、3.7～3.11 的事件由那些 Story 自己登錄。
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.core.events import Event
from app.modules.competition import service as competition_service
from app.modules.competition.models import (
    AutoDrawSkipped,
    BracketBackfilled,
    BracketDrawn,
    MatchOpponentsDecided,
    MatchRead,
    MatchRescheduled,
    OpponentRetired,
    RefereeAssigned,
    RefereeUnassigned,
)
from app.modules.disputes import service as disputes_service
from app.modules.disputes.models import (
    AppealDecision,
    AppealFiled,
    AppealResolved,
    ReportFiled,
    ReportResolved,
)
from app.modules.identity import service as identity_service
from app.modules.identity.models import (
    OrganizerApplicationApproved,
    OrganizerApplicationRejected,
    OrganizerApplicationSubmitted,
)
from app.modules.notifications.registry import (
    NotificationDraft,
    RecipientsNotFound,
    register,
)
from app.modules.registration import service as registration_service
from app.modules.registration.models import (
    CaptainTransferred,
    RegistrationAllocated,
    RegistrationBackfilled,
    RegistrationRejected,
    RegistrationStatus,
    TeamDisbanded,
    TeamMemberRemoved,
)
from app.modules.tournaments import service as tournaments_service

_TAIPEI = ZoneInfo("Asia/Taipei")
_WEEKDAYS = "一二三四五六日"


class MatchForfeited(Event):
    """competition 的 `MatchForfeited`（定義在 `competition/forfeit_job.py`）只取需要的欄位。

    AD-2 規定跨模組只能 import `service`、`models`，所以在這裡以同名類別讀 payload；
    事件名稱相同（`MatchForfeited`），其餘欄位在驗證時略過。
    """

    match_id: UUID


def _format_time(value: datetime) -> str:
    """台北時間，例如 `10/18（六）19:00`（與前端的絕對時間格式相同）。"""
    local = value.astimezone(_TAIPEI)
    return f"{local:%m/%d}（{_WEEKDAYS[local.weekday()]}）{local:%H:%M}"


def _drafts(
    account_ids: Iterable[uuid.UUID], *, title: str, body: str, link: str
) -> list[NotificationDraft]:
    return [
        NotificationDraft(account_id=account_id, title=title, body=body, link=link)
        for account_id in account_ids
    ]


def _member_ids(session: Session, team_id: uuid.UUID) -> list[uuid.UUID]:
    """「隊長與選手」：隊伍所有成員。"""
    team = registration_service.get_team(session, team_id=team_id)
    return [member.account_id for member in team.members]


def _match_team_ids(match: MatchRead) -> list[uuid.UUID]:
    return [t for t in (match.team_a_id, match.team_b_id) if t is not None]


def _match_link(match: MatchRead) -> str:
    return f"/tournaments/{match.tournament_id}/matches/{match.id}"


def _match_label(session: Session, match: MatchRead) -> str:
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    return f"「{tournament.name}」場次 {match.code}"


# ---------------------------------------------------------------- 主辦方申請（1.7、1.8）


def _application_submitted(
    session: Session, _event: OrganizerApplicationSubmitted
) -> list[NotificationDraft]:
    return _drafts(
        identity_service.list_platform_admin_ids(session),
        title="有新的主辦方申請",
        body="有一筆新的主辦方申請等待審核。",
        link="/admin/applications",
    )


def _application_approved(
    session: Session, event: OrganizerApplicationApproved
) -> list[NotificationDraft]:
    applicant = identity_service.get_organizer_applicant_id(
        session, event.application_id
    )
    return _drafts(
        [applicant],
        title="主辦方申請已核准",
        body="你的主辦方申請已核准，現在可以從身分切換器進入主辦方後台建立賽事。",
        link="/organizer",
    )


def _application_rejected(
    session: Session, event: OrganizerApplicationRejected
) -> list[NotificationDraft]:
    applicant = identity_service.get_organizer_applicant_id(
        session, event.application_id
    )
    return _drafts(
        [applicant],
        title="主辦方申請已退回",
        body="你的主辦方申請已退回，可以查看退回原因、修改後重新送出。",
        link="/organizer/apply",
    )


# ---------------------------------------------------------------- 報名（3.4～3.6）

_ALLOCATION_TEXT = {
    RegistrationStatus.ACCEPTED: "正取",
    RegistrationStatus.WAITLISTED: "候補",
    RegistrationStatus.REJECTED: "退回",
}


def _registration_allocated(
    session: Session, event: RegistrationAllocated
) -> list[NotificationDraft]:
    team = registration_service.get_team(session, team_id=event.team_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    result = _ALLOCATION_TEXT.get(event.status, "已更新")
    return _drafts(
        [member.account_id for member in team.members],
        title=f"報名結果：{result}",
        body=f"「{team.name}」在「{tournament.name}」的報名結果為{result}。",
        link=f"/teams/{team.id}",
    )


# ---------------------------------------------------------------- 抽籤與賽程（4.1～4.4）


def _bracket_drawn(session: Session, event: BracketDrawn) -> list[NotificationDraft]:
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    # 抽籤後報名狀態已改為 drawn：收件人取自對戰表上的隊伍
    bracket = competition_service.get_bracket(
        session, tournament_id=event.tournament_id
    )
    if bracket is None:
        raise RecipientsNotFound(
            f"bracket of tournament {event.tournament_id} not found"
        )
    team_ids = dict.fromkeys(
        team_id for match in bracket.matches for team_id in _match_team_ids(match)
    )
    recipients = [
        account_id
        for team_id in team_ids
        for account_id in _member_ids(session, team_id)
    ]
    return _drafts(
        recipients,
        title="對戰表已公布",
        body=f"「{tournament.name}」已完成抽籤，可以查看對戰表與你的場次時間。",
        link=f"/tournaments/{tournament.id}/bracket",
    )


def _auto_draw_skipped(
    session: Session, event: AutoDrawSkipped
) -> list[NotificationDraft]:
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    return _drafts(
        [tournament.organizer_id],
        title="正取不足 2 隊，無法抽籤",
        body=(
            f"「{tournament.name}」報名截止時只有 {event.accepted_teams} 隊正取，"
            "系統沒有自動抽籤。"
        ),
        link=f"/organizer/tournaments/{tournament.id}",
    )


def _teams_and_referee(session: Session, match: MatchRead) -> list[uuid.UUID]:
    recipients = [
        account_id
        for team_id in _match_team_ids(match)
        for account_id in _member_ids(session, team_id)
    ]
    if match.referee_account_id is not None:
        recipients.append(match.referee_account_id)
    return recipients


def _match_rescheduled(
    session: Session, event: MatchRescheduled
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    return _drafts(
        _teams_and_referee(session, match),
        title="場次時間已變更",
        body=(
            f"{_match_label(session, match)}的時間改為 "
            f"{_format_time(event.scheduled_at)}。"
        ),
        link=_match_link(match),
    )


def _opponents_decided(
    session: Session, event: MatchOpponentsDecided
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    captains = [
        account_id
        for team_id in _match_team_ids(match)
        for account_id in _member_ids(session, team_id)
        if registration_service.is_captain(
            session, team_id=team_id, account_id=account_id
        )
    ]
    return _drafts(
        captains,
        title="下一場對手已確定",
        body=(
            f"{_match_label(session, match)}的兩隊已確定，"
            f"預定時間 {_format_time(match.scheduled_at)}。"
        ),
        link=_match_link(match),
    )


def _match_forfeited(
    session: Session, event: MatchForfeited
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    return _drafts(
        _teams_and_referee(session, match),
        title="場次已判棄權",
        body=f"{_match_label(session, match)}因逾時未報到已判棄權。",
        link=_match_link(match),
    )


def _referee_assigned(
    session: Session, event: RefereeAssigned
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    return _drafts(
        [event.referee_account_id],
        title="你被指派為場次裁判",
        body=(
            f"你被指派為{_match_label(session, match)}的裁判，"
            f"預定時間 {_format_time(match.scheduled_at)}。"
        ),
        link="/me/referee",
    )


def _referee_unassigned(
    session: Session, event: RefereeUnassigned
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    return _drafts(
        [event.referee_account_id],
        title="你的裁判指派已取消",
        body=f"你不再是{_match_label(session, match)}的裁判。",
        link="/me/referee",
    )


# ---------------------------------------------------------------- 申訴與檢舉（6.1～6.5）

_APPEAL_DECISION_TEXT = {
    AppealDecision.UPHELD: "維持原結果",
    AppealDecision.CORRECTED: "更正結果",
    AppealDecision.REMATCH: "重新比賽",
    AppealDecision.DISQUALIFIED: "取消資格",
}


def _appeal_filed(session: Session, event: AppealFiled) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    return _drafts(
        [tournament.organizer_id],
        title="有新的申訴",
        body=f"「{tournament.name}」場次 {match.code} 有隊伍提出申訴，請在期限內處理。",
        link=f"/organizer/tournaments/{tournament.id}/appeals",
    )


def _appeal_resolved(
    session: Session, event: AppealResolved
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    decision = _APPEAL_DECISION_TEXT.get(event.decision, "已處理")
    recipients = [
        account_id
        for team_id in _match_team_ids(match)
        for account_id in _member_ids(session, team_id)
    ]
    return _drafts(
        recipients,
        title="申訴已處理",
        body=f"{_match_label(session, match)}的申訴處理結果：{decision}。",
        link=_match_link(match),
    )


def _report_filed(session: Session, event: ReportFiled) -> list[NotificationDraft]:
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    return _drafts(
        [tournament.organizer_id],
        title="有新的檢舉",
        body=f"「{tournament.name}」有隊伍提出檢舉，請查看並處理。",
        link=f"/organizer/tournaments/{tournament.id}/reports",
    )


def _report_resolved(
    session: Session, event: ReportResolved
) -> list[NotificationDraft]:
    parties = disputes_service.get_report_parties(session, report_id=event.report_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=parties.tournament_id
    )
    result = "屬實" if event.substantiated else "駁回"
    reporter = _drafts(
        _member_ids(session, parties.reporter_team_id),
        title="檢舉已處理",
        body=f"你的隊伍在「{tournament.name}」提出的檢舉處理結果：{result}。",
        link=f"/teams/{parties.reporter_team_id}",
    )
    reported = _drafts(
        _member_ids(session, parties.reported_team_id),
        title="被檢舉的處理結果",
        body=f"你的隊伍在「{tournament.name}」被檢舉，處理結果：{result}。",
        link=f"/teams/{parties.reported_team_id}",
    )
    return reporter + reported


register(OrganizerApplicationSubmitted, _application_submitted)
register(OrganizerApplicationApproved, _application_approved)
register(OrganizerApplicationRejected, _application_rejected)
register(RegistrationAllocated, _registration_allocated)
register(BracketDrawn, _bracket_drawn)
register(AutoDrawSkipped, _auto_draw_skipped)
register(MatchRescheduled, _match_rescheduled)
register(MatchOpponentsDecided, _opponents_decided)
register(MatchForfeited, _match_forfeited)
register(RefereeAssigned, _referee_assigned)
register(RefereeUnassigned, _referee_unassigned)
register(AppealFiled, _appeal_filed)
register(AppealResolved, _appeal_resolved)
register(ReportFiled, _report_filed)
register(ReportResolved, _report_resolved)


# ---------------------------------------------------------------- 遞補（3.7）


def _registration_backfilled(
    session: Session, event: RegistrationBackfilled
) -> list[NotificationDraft]:
    team = registration_service.get_team(session, team_id=event.team_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    return _drafts(
        _member_ids(session, team.id),
        title="報名結果：已遞補為正取",
        body=f"「{team.name}」在「{tournament.name}」已由候補遞補為正取。",
        link=f"/teams/{team.id}",
    )


register(RegistrationBackfilled, _registration_backfilled)


# ---------------------------------------------------------------- 退回（3.8）

_SENTENCE_END = "。．.！？!?"


def _registration_rejected(
    session: Session, event: RegistrationRejected
) -> list[NotificationDraft]:
    team = registration_service.get_team(session, team_id=event.team_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=event.tournament_id
    )
    # 原因以句末標點結尾時不再重複「。」；只有標點時沿用原字串（PR #107 審查）
    reason = event.reason.rstrip(_SENTENCE_END) or event.reason
    next_step = (
        "請在報名截止前修正後重新送出。"
        if event.can_resubmit
        else "報名已截止，無法重新送出。"
    )
    return _drafts(
        _member_ids(session, team.id),
        title="報名結果：退回",
        body=(
            f"「{team.name}」在「{tournament.name}」的報名被主辦方退回，"
            f"原因：{reason}。{next_step}"
        ),
        link=f"/teams/{team.id}",
    )


register(RegistrationRejected, _registration_rejected)


# ---------------------------------------------------------------- 抽籤後退賽與遞補（4.5）


def _bracket_backfilled(
    session: Session, event: BracketBackfilled
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    team = registration_service.get_team(session, team_id=event.team_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    return _drafts(
        _member_ids(session, team.id),
        title="已遞補進入對戰表",
        body=f"「{team.name}」已由候補遞補，接手「{tournament.name}」{match.code} 的位置。",
        link=_match_link(match),
    )


def _opponent_retired(
    session: Session, event: OpponentRetired
) -> list[NotificationDraft]:
    match = competition_service.get_match(session, match_id=event.match_id)
    captains = [
        account_id
        for account_id in _member_ids(session, event.winner_id)
        if registration_service.is_captain(
            session, team_id=event.winner_id, account_id=account_id
        )
    ]
    return _drafts(
        captains,
        title="對手退賽",
        body=f"{match.code} 的對手已退賽，你們以輪空晉級。",
        link=_match_link(match),
    )


register(BracketBackfilled, _bracket_backfilled)
register(OpponentRetired, _opponent_retired)


# ---------------------------------------------------------------- 隊員異動與解散（3.11）


def _team_label(session: Session, team_id: uuid.UUID, tournament_id: uuid.UUID) -> str:
    """「「隊名」（賽事）」：解散後隊伍沒有隊員，隊名用 `get_team_names` 查。"""
    names = registration_service.get_team_names(session, team_ids=[team_id])
    if team_id not in names:
        raise RecipientsNotFound(f"team {team_id} not found")
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    return f"「{names[team_id]}」（{tournament.name}）"


def _team_member_removed(
    session: Session, event: TeamMemberRemoved
) -> list[NotificationDraft]:
    # 被移除者在 worker 處理時已不在隊上，收件人取自事件
    label = _team_label(session, event.team_id, event.tournament_id)
    return _drafts(
        [event.account_id],
        title="已被移出隊伍",
        body=f"你已被隊長移出{label}。",
        link=f"/tournaments/{event.tournament_id}",
    )


def _captain_transferred(
    session: Session, event: CaptainTransferred
) -> list[NotificationDraft]:
    label = _team_label(session, event.team_id, event.tournament_id)
    return _drafts(
        [event.to_account_id],
        title="你成為隊長",
        body=f"{label}的隊長已轉讓給你。",
        link=f"/teams/{event.team_id}",
    )


def _team_disbanded(session: Session, event: TeamDisbanded) -> list[NotificationDraft]:
    # 所有原隊員（含隊長本人，FR-37）；解散後隊伍已沒有隊員，查解散名單
    recipients = registration_service.list_disbanded_member_ids(
        session, team_id=event.team_id
    )
    label = _team_label(session, event.team_id, event.tournament_id)
    return _drafts(
        recipients,
        title="隊伍已解散",
        body=f"{label}已被隊長解散，報名已撤回。",
        link=f"/teams/{event.team_id}",
    )


register(TeamMemberRemoved, _team_member_removed)
register(CaptainTransferred, _captain_transferred)
register(TeamDisbanded, _team_disbanded)
