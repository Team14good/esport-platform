"""registration 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。

賽事只透過 tournaments 的公開函式 `get_tournament`、`lock_tournament`、
`ensure_accepting_registrations`、`transition_tournament`、`find_due_registration_end_id`
取得、檢查與改變狀態（contracts/tournaments.md）。
"""

import secrets
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import BinaryIO

from sqlmodel import Session

from app.core import audit, authz, clock, events, storage
from app.core.errors import BusinessError, FieldError
from app.modules.identity import service as identity_service
from app.modules.registration import allocation, player_profile, repository
from app.modules.registration.models import (
    InviteStatus,
    MemberRole,
    MissingProfileField,
    MyTeamCard,
    PriorityWindowSettlement,
    Registration,
    RegistrationAllocated,
    RegistrationRead,
    RegistrationStatus,
    SubmitBlocker,
    Team,
    TeamDetail,
    TeamInvitePreview,
    TeamMember,
    TeamMemberRead,
    TeamMemberRole,
    TeamRead,
    TeamSummary,
    WaitlistFields,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import (
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)

INVITE_TOKEN_BYTES = 24


# ---------------------------------------------------------------- tournaments 介面


def _get_tournament(session: Session, tournament_id: uuid.UUID) -> TournamentRead:
    return tournaments_service.get_tournament(session, tournament_id=tournament_id)


def _lock_tournament(session: Session, tournament_id: uuid.UUID) -> TournamentRead:
    """鎖住賽事列（AD-6）：建隊、加入等改變名單的操作都先鎖，再檢查身分與人數。"""
    return tournaments_service.lock_tournament(session, tournament_id=tournament_id)


def _ensure_accepting_registrations(tournament: TournamentRead) -> None:
    """賽事不是開放報名時，由 tournaments 拋 409 `REGISTRATION_CLOSED`。"""
    tournaments_service.ensure_accepting_registrations(tournament)


def _in_registration_period(tournament: TournamentRead) -> bool:
    """賽事開放報名且現在早於報名截止時間。

    open → closed 由報名截止工作（3.6 `close_registration`）在 worker 下一輪才轉，
    截止時間到了之後、轉狀態之前仍是 `open`；所以 registration 自己再比對截止時間。
    """
    return (
        tournament.status == TournamentStatus.OPEN
        and clock.now() < tournament.registration_end
    )


def _ensure_registration_period(
    tournament: TournamentRead, *, now: datetime | None = None
) -> None:
    """在報名期間（賽事開放且早於截止時間）；否則拋 409 `REGISTRATION_CLOSED`。

    賽事已轉為「報名截止」（`closed`）時與截止時間已到同樣回「這場賽事的報名已截止。」，
    其他非開放狀態由 tournaments 回「這場賽事目前不開放報名。」。`now` 讓呼叫端用同一個
    時間做檢查與寫入（送出報名的 `submitted_at`）；省略時取 `clock.now()`。
    """
    if tournament.status == TournamentStatus.CLOSED:
        raise _registration_deadline_passed()
    _ensure_accepting_registrations(tournament)
    if (now if now is not None else clock.now()) >= tournament.registration_end:
        raise _registration_deadline_passed()


# ---------------------------------------------------------------- 錯誤


def _team_not_found() -> BusinessError:
    return BusinessError("TEAM_NOT_FOUND", "找不到這支隊伍。", status_code=404)


def _invite_not_found() -> BusinessError:
    return BusinessError("TEAM_INVITE_NOT_FOUND", "這個邀請連結無效。", status_code=404)


def _already_in_tournament() -> BusinessError:
    return BusinessError(
        "ALREADY_IN_TOURNAMENT",
        "你已經在這個賽事的隊伍中，同一個賽事只能加入一支隊伍。",
        status_code=409,
    )


def _organizer_cannot_join() -> BusinessError:
    return BusinessError(
        "ORGANIZER_CANNOT_JOIN",
        "主辦方不能在自己的賽事建立或加入隊伍。",
        status_code=403,
    )


def _team_full() -> BusinessError:
    return BusinessError("TEAM_FULL", "隊伍已滿，無法再加入。", status_code=409)


def _team_name_taken() -> BusinessError:
    return BusinessError(
        "TEAM_NAME_TAKEN", "這個賽事已經有同名的隊伍。", status_code=409
    )


def _team_member_required() -> BusinessError:
    return BusinessError(
        "TEAM_MEMBER_REQUIRED", "只有隊員可以查看這支隊伍。", status_code=403
    )


def _roster_locked() -> BusinessError:
    return BusinessError("ROSTER_LOCKED", "名單已鎖定，資料無法修改。", status_code=409)


def _roster_locked_for_join() -> BusinessError:
    return BusinessError("ROSTER_LOCKED", "名單已鎖定，無法加入。", status_code=409)


def _registration_deadline_passed() -> BusinessError:
    return BusinessError(
        "REGISTRATION_CLOSED", "這場賽事的報名已截止。", status_code=409
    )


def _registration_already_submitted() -> BusinessError:
    return BusinessError(
        "REGISTRATION_ALREADY_SUBMITTED", "這支隊伍已送出報名", status_code=409
    )


def _requirements_unmet(blockers: list[SubmitBlocker]) -> BusinessError:
    return BusinessError(
        "REGISTRATION_REQUIREMENTS_UNMET",
        "；".join(blocker.message for blocker in blockers),
        status_code=409,
    )


def _rank_screenshot_required() -> FieldError:
    return FieldError(
        "RANK_SCREENSHOT_REQUIRED",
        "請上傳段位截圖",
        loc=("body", "rank_screenshot"),
    )


def _registration_not_found() -> BusinessError:
    return BusinessError(
        "REGISTRATION_NOT_FOUND", "找不到這支隊伍的報名。", status_code=404
    )


# ---------------------------------------------------------------- 報名狀態

# 期中文件 B 參、四（二）的報名狀態圖
_TRANSITIONS: dict[RegistrationStatus, frozenset[RegistrationStatus]] = {
    RegistrationStatus.FORMING: frozenset(
        {
            RegistrationStatus.PENDING,
            RegistrationStatus.ACCEPTED,
            RegistrationStatus.WAITLISTED,
            RegistrationStatus.WITHDRAWN,
        }
    ),
    RegistrationStatus.PENDING: frozenset(
        {
            RegistrationStatus.ACCEPTED,
            RegistrationStatus.WAITLISTED,
            RegistrationStatus.REJECTED,
            RegistrationStatus.WITHDRAWN,
            RegistrationStatus.DISQUALIFIED,
        }
    ),
    RegistrationStatus.ACCEPTED: frozenset(
        {
            RegistrationStatus.REJECTED,
            RegistrationStatus.WITHDRAWN,
            RegistrationStatus.DRAWN,
            RegistrationStatus.DISQUALIFIED,
        }
    ),
    RegistrationStatus.WAITLISTED: frozenset(
        {
            RegistrationStatus.ACCEPTED,
            RegistrationStatus.DRAWN,
            RegistrationStatus.REJECTED,
            RegistrationStatus.WITHDRAWN,
            RegistrationStatus.DISQUALIFIED,
        }
    ),
    RegistrationStatus.REJECTED: frozenset({RegistrationStatus.FORMING}),
    RegistrationStatus.WITHDRAWN: frozenset(),
    RegistrationStatus.DRAWN: frozenset(
        {RegistrationStatus.RETIRED, RegistrationStatus.DISQUALIFIED}
    ),
    RegistrationStatus.RETIRED: frozenset(),
    RegistrationStatus.DISQUALIFIED: frozenset(),
}


def can_transition(frm: RegistrationStatus, to: RegistrationStatus) -> bool:
    return to in _TRANSITIONS[frm]


def mark_status(
    session: Session,
    *,
    registration: Registration,
    to: RegistrationStatus,
    actor_id: uuid.UUID | None,
) -> None:
    """唯一修改報名狀態的入口；非法轉換拋 409 `REGISTRATION_INVALID_TRANSITION`。

    寫操作紀錄 `registration.status_changed`；`actor_id=None` 表示系統（worker）。
    呼叫前要先 `lock_tournament`（會改變名額的操作）。
    """
    current = registration.status
    if not can_transition(current, to):
        raise BusinessError(
            "REGISTRATION_INVALID_TRANSITION",
            "報名目前的狀態不能進行這個操作。",
            status_code=409,
        )
    registration.status = to
    session.add(registration)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=registration.tournament_id,
        action="registration.status_changed",
        entity_type="registration",
        entity_id=registration.id,
        before={"status": current},
        after={"status": to},
    )
    session.flush()


# ---------------------------------------------------------------- 內部共用


def _max_members(tournament: TournamentRead) -> int:
    return tournament.starters + tournament.substitutes


def _invite_status(
    tournament: TournamentRead,
    member_count: int,
    registration_status: RegistrationStatus,
) -> InviteStatus:
    """已鎖定（報名不是組隊中）> 已截止（不在報名期間）> 已滿 > 有效。"""
    if registration_status != RegistrationStatus.FORMING:
        return "locked"
    if not _in_registration_period(tournament):
        return "closed"
    return "full" if member_count >= _max_members(tournament) else "active"


def _team_read(team: Team, members: list[TeamMember]) -> TeamRead:
    return TeamRead(
        id=team.id,
        tournament_id=team.tournament_id,
        name=team.name,
        members=[
            TeamMemberRole(account_id=member.account_id, role=member.role)
            for member in members
        ],
    )


def _registration_of(session: Session, team: Team) -> Registration:
    registration = repository.get_registration_by_team(session, team.id)
    assert registration is not None  # 建立隊伍時同時建立
    return registration


def _ensure_can_join(
    session: Session, tournament: TournamentRead, account_id: uuid.UUID
) -> None:
    """鎖住賽事後檢查：報名期間、不是主辦方、不在該賽事的任何隊伍。"""
    _ensure_registration_period(tournament)
    if tournament.organizer_id == account_id:
        raise _organizer_cannot_join()
    if repository.get_membership(session, tournament.id, account_id) is not None:
        raise _already_in_tournament()


def _missing_fields(member: TeamMember) -> list[MissingProfileField]:
    """尚未填寫的參賽資料，固定依遊戲 ID、段位、段位截圖的順序。"""
    missing: list[MissingProfileField] = []
    if member.game_account_id is None:
        missing.append("game_account_id")
    # 段位與積分由 update_player_profile 一起寫入；只有其中一個（示範資料、手動匯入）
    # 也算段位未填，送出條件才擋得住，不會在算平均時漏掉這位隊員
    if member.rank_tier is None or member.rank_score is None:
        missing.append("rank_tier")
    if member.rank_screenshot_key is None:
        missing.append("rank_screenshot")
    return missing


def _profile_editable(tournament: TournamentRead, registration: Registration) -> bool:
    return (
        _in_registration_period(tournament)
        and registration.status == RegistrationStatus.FORMING
    )


def _display_names(session: Session, members: list[TeamMember]) -> list[str]:
    names: list[str] = []
    for member in members:
        contact = identity_service.get_account_contact(session, member.account_id)
        assert contact is not None  # 外鍵保證帳號存在
        names.append(contact.display_name)
    return names


def _roster_entries(
    session: Session, members: list[TeamMember], names: list[str]
) -> list[player_profile.RosterEntry]:
    """送出檢查用的隊員資料（依加入順序）；學校讀帳號目前的設定。"""
    schools = identity_service.get_account_school_ids(
        session, [member.account_id for member in members]
    )
    return [
        player_profile.RosterEntry(
            display_name=name,
            missing_fields=_missing_fields(member),
            school_id=schools.get(member.account_id),
        )
        for member, name in zip(members, names, strict=True)
    ]


def _registration_closed_blocker() -> SubmitBlocker:
    """只供畫面停用「送出報名」；伺服器送出時另回 409 `REGISTRATION_CLOSED`。"""
    return SubmitBlocker(code="REGISTRATION_CLOSED", message="已截止")


def _candidate(registration: Registration) -> allocation.Candidate:
    """報名快照轉成 `allocation.Candidate`；送出後三個快照必有值（`submit_registration`）。"""
    if (
        registration.school_id is None
        or registration.avg_rank_score is None
        or registration.submitted_at is None
    ):
        # 不用 assert（python -O 會略過）；目前沒有路徑會產生沒有快照的已送出報名
        raise RuntimeError(f"報名 {registration.id} 沒有送出時的快照")
    return allocation.Candidate(
        id=registration.id,
        school_id=registration.school_id,
        avg_rank_score=registration.avg_rank_score,
        submitted_at=registration.submitted_at,
        status=registration.status,
    )


def _current_phase(tournament: TournamentRead) -> allocation.AllocationPhase:
    """候補順位的階段：開放報名且早於報名截止為先搶期，其餘為截止後。

    賽事不是開放報名（提前抽籤後、報名截止、取消等）時，即使還沒到報名截止時間也是
    截止後（Story 3.6 Decisions）。
    """
    if (
        tournament.status == TournamentStatus.OPEN
        and clock.now() < tournament.registration_end
    ):
        return allocation.AllocationPhase.FIRST_COME
    return allocation.AllocationPhase.AFTER_DEADLINE


# 計算候補順位時參考的狀態：正取（含已參賽）決定學校資格與每校上限，候補是排序對象
_ORDER_STATUSES = frozenset(
    {
        RegistrationStatus.ACCEPTED,
        RegistrationStatus.DRAWN,
        RegistrationStatus.WAITLISTED,
    }
)


def _waitlist_fields(
    session: Session, registration: Registration, tournament: TournamentRead
) -> WaitlistFields:
    """S17、S12 的候補資訊：只在 `waitlisted` 時計算，順位只由 `allocation.waitlist_order` 決定。"""
    if registration.status != RegistrationStatus.WAITLISTED:
        return WaitlistFields(
            waitlist_position=None,
            waitlist_reason=None,
            representative_backfill=None,
            waitlist_phase=None,
        )
    settlement = repository.get_settlement(session, tournament.id)
    priority_schools = (
        frozenset(settlement.priority_school_ids) if settlement else frozenset()
    )
    phase = _current_phase(tournament)
    candidates = [
        _candidate(r)
        for r in repository.list_registrations(session, tournament.id)
        if r.status in _ORDER_STATUSES
    ]
    entry = allocation.waitlist_order(
        candidates, phase=phase, priority_schools=priority_schools
    )[registration.id]
    return WaitlistFields(
        waitlist_position=entry.position,
        waitlist_reason=None if entry.reason is None else entry.reason.value,
        representative_backfill=entry.representative_backfill,
        waitlist_phase=phase.value,
    )


def _build_detail(
    session: Session, team: Team, tournament: TournamentRead, viewer: TeamMember
) -> TeamDetail:
    members = repository.list_members(session, team.id)
    names = _display_names(session, members)
    member_reads: list[TeamMemberRead] = []
    for member, name in zip(members, names, strict=True):
        is_viewer = member.account_id == viewer.account_id
        member_reads.append(
            TeamMemberRead(
                account_id=member.account_id,
                display_name=name,
                role=member.role,
                joined_at=member.created_at,
                game_account_id=member.game_account_id,
                rank_tier=member.rank_tier,
                rank_score=member.rank_score,
                has_rank_screenshot=member.rank_screenshot_key is not None,
                # 原始檔名可能含個資，只回給本人
                rank_screenshot_name=(
                    member.rank_screenshot_name if is_viewer else None
                ),
                missing_fields=_missing_fields(member),
            )
        )
    scores = [m.rank_score for m in members if m.rank_score is not None]
    registration = _registration_of(session, team)
    max_members = _max_members(tournament)
    blockers: list[SubmitBlocker] = []
    if registration.status == RegistrationStatus.FORMING:
        if not _in_registration_period(tournament):
            blockers.append(_registration_closed_blocker())
        blockers.extend(
            player_profile.submit_blockers(
                starters=tournament.starters,
                members=_roster_entries(session, members, names),
            )
        )
    return TeamDetail(
        id=team.id,
        name=team.name,
        tournament_id=team.tournament_id,
        tournament_name=tournament.name,
        game_name=tournament.game_name,
        starters=tournament.starters,
        substitutes=tournament.substitutes,
        max_members=max_members,
        members=member_reads,
        registration_status=registration.status,
        invite_token=team.invite_token,
        invite_status=_invite_status(tournament, len(members), registration.status),
        my_role=viewer.role,
        rank_tiers=tournament.rank_tiers,
        avg_rank_score=player_profile.average_rank_score(scores),
        rank_filled_count=len(scores),
        profile_editable=_profile_editable(tournament, registration),
        submit_blockers=blockers,
        priority_end=tournament.priority_end,
        registration_end=tournament.registration_end,
        submitted_at=registration.submitted_at,
        **_waitlist_fields(session, registration, tournament).model_dump(),
    )


# ---------------------------------------------------------------- 使用案例


def create_team(
    session: Session, *, tournament_id: uuid.UUID, account_id: uuid.UUID, name: str
) -> TeamDetail:
    """S16 建立隊伍：建立者成為隊長，同時建立「組隊中」的報名與邀請 token。"""
    tournament = _lock_tournament(session, tournament_id)
    _ensure_can_join(session, tournament, account_id)
    if repository.get_team_by_name(session, tournament.id, name) is not None:
        raise _team_name_taken()

    now = clock.now()
    team = Team(
        tournament_id=tournament.id,
        name=name,
        invite_token=secrets.token_urlsafe(INVITE_TOKEN_BYTES),
        created_at=now,
    )
    try:
        repository.add_team(session, team)
    except repository.DuplicateTeamNameError:
        raise _team_name_taken()
    captain = TeamMember(
        team_id=team.id,
        tournament_id=tournament.id,
        account_id=account_id,
        role=MemberRole.CAPTAIN,
        created_at=now,
    )
    try:
        repository.add_member(session, captain)
    except repository.DuplicateMemberError:
        raise _already_in_tournament()
    repository.add_registration(
        session,
        Registration(
            team_id=team.id,
            tournament_id=tournament.id,
            status=RegistrationStatus.FORMING,
            created_at=now,
        ),
    )
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=tournament.id,
        action="team.created",
        entity_type="team",
        entity_id=team.id,
        before=None,
        after={"name": team.name, "captain_id": account_id},
    )
    session.flush()
    return _build_detail(session, team, tournament, captain)


def preview_invite(session: Session, *, token: str) -> TeamInvitePreview:
    """S19 公開預覽：賽事名、遊戲、隊名與是否已滿；不需登入。"""
    team = repository.get_team_by_invite_token(session, token)
    if team is None:
        raise _invite_not_found()
    tournament = _get_tournament(session, team.tournament_id)
    member_count = repository.count_members(session, team.id)
    max_members = _max_members(tournament)
    return TeamInvitePreview(
        team_id=team.id,
        team_name=team.name,
        tournament_id=team.tournament_id,
        tournament_name=tournament.name,
        game_name=tournament.game_name,
        member_count=member_count,
        max_members=max_members,
        invite_status=_invite_status(
            tournament, member_count, _registration_of(session, team).status
        ),
    )


def join_team(session: Session, *, token: str, account_id: uuid.UUID) -> TeamDetail:
    """S19 以邀請連結加入隊伍，成為選手。"""
    team = repository.get_team_by_invite_token(session, token)
    if team is None:
        raise _invite_not_found()
    tournament = _lock_tournament(session, team.tournament_id)
    # 鎖之後才讀報名狀態：送出與加入同時發生時，加入一定看到送出後的結果。
    # 名單鎖定先於報名期間檢查，與邀請狀態的優先順序（locked > closed）一致
    if _registration_of(session, team).status != RegistrationStatus.FORMING:
        raise _roster_locked_for_join()
    _ensure_can_join(session, tournament, account_id)
    if repository.count_members(session, team.id) >= _max_members(tournament):
        raise _team_full()

    member = TeamMember(
        team_id=team.id,
        tournament_id=team.tournament_id,
        account_id=account_id,
        role=MemberRole.PLAYER,
        created_at=clock.now(),
    )
    try:
        repository.add_member(session, member)
    except repository.DuplicateMemberError:
        # 最後防線：鎖之外的併發寫入撞到（tournament_id, account_id）唯一鍵
        raise _already_in_tournament()
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=team.tournament_id,
        action="team.member_joined",
        entity_type="team",
        entity_id=team.id,
        before=None,
        after={"account_id": account_id, "role": MemberRole.PLAYER},
    )
    session.flush()
    return _build_detail(session, team, tournament, member)


def get_team_detail(
    session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
) -> TeamDetail:
    """S17 隊伍頁：只有隊員能看（含邀請 token）。"""
    team = repository.get_team(session, team_id)
    if team is None:
        raise _team_not_found()
    viewer = repository.get_team_member(session, team.id, account_id)
    if viewer is None:
        raise _team_member_required()
    tournament = _get_tournament(session, team.tournament_id)
    return _build_detail(session, team, tournament, viewer)


@dataclass(frozen=True)
class ProfileUpdate:
    """`update_player_profile` 的結果。

    `new_key`：這次存下的截圖鍵值（沒換截圖為 None）；交易提交失敗時由 router 刪除。
    `old_key`：被換掉的舊截圖鍵值（沒換或第一次上傳為 None）；交易提交後由 router 刪除。
    """

    detail: TeamDetail
    new_key: str | None
    old_key: str | None


def update_player_profile(
    session: Session,
    *,
    team_id: uuid.UUID,
    account_id: uuid.UUID,
    game_account_id: str,
    rank_tier: str,
    screenshot: BinaryIO | None,
    content_type: str | None,
    file_name: str | None,
) -> ProfileUpdate:
    """S18 隊員存自己的參賽資料；`screenshot` 為 None 表示保留原本的截圖。

    先查隊伍、鎖住賽事，再檢查身分、賽事與名單狀態與欄位，全部通過才存圖片。
    圖片存下之後的步驟失敗時，在這裡刪掉新檔再往外拋（router 拿不到鍵值）；
    交易提交與舊檔清理由 router 負責。
    """
    team = repository.get_team(session, team_id)
    if team is None:
        raise _team_not_found()
    tournament = _lock_tournament(session, team.tournament_id)
    member = repository.get_team_member(session, team.id, account_id)
    if member is None:
        raise _team_member_required()
    _ensure_registration_period(tournament)
    if _registration_of(session, team).status != RegistrationStatus.FORMING:
        raise _roster_locked()

    cleaned_game_account_id = player_profile.validate_game_account_id(game_account_id)
    rank_score = player_profile.rank_score_for(tournament.rank_tiers, rank_tier)
    if screenshot is None and member.rank_screenshot_key is None:
        raise _rank_screenshot_required()

    before = {
        "game_account_id": member.game_account_id,
        "rank_tier": member.rank_tier,
        "rank_score": member.rank_score,
        # 與 after 的 screenshot_replaced 一起看，才分得出首次上傳還是換圖
        "had_screenshot": member.rank_screenshot_key is not None,
    }
    new_key: str | None = None
    old_key: str | None = None
    if screenshot is not None:
        new_key = storage.save_image(screenshot, content_type=content_type)
    try:
        if new_key is not None:
            old_key = member.rank_screenshot_key
            member.rank_screenshot_key = new_key
            member.rank_screenshot_name = player_profile.clean_file_name(
                file_name, extension=PurePath(new_key).suffix
            )
        member.game_account_id = cleaned_game_account_id
        member.rank_tier = rank_tier
        member.rank_score = rank_score
        session.add(member)
        audit.record(
            session,
            actor_id=account_id,
            tournament_id=team.tournament_id,
            action="team_member.profile_updated",
            entity_type="team_member",
            entity_id=member.id,
            before=before,
            after={
                "game_account_id": cleaned_game_account_id,
                "rank_tier": rank_tier,
                "rank_score": rank_score,
                "screenshot_replaced": new_key is not None,
            },
        )
        session.flush()
        detail = _build_detail(session, team, tournament, member)
    except BaseException:
        if new_key is not None:
            storage.delete_file(new_key)
        raise
    return ProfileUpdate(detail=detail, new_key=new_key, old_key=old_key)


def submit_registration(
    session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
) -> TeamDetail:
    """S17 隊長送出報名：報名送出、名單鎖定，凍結學校、平均段位積分與送出時間。

    先查隊伍、鎖住賽事，再依序檢查隊員、隊長、報名期間、報名仍是組隊中與送出條件。
    送出條件與 S17 的 `submit_blockers` 是同一個函式，不符合時全部原因以「；」串接。
    報名先轉為 `pending`（操作者為隊長），送出本身不發事件（FR-37 只通知報名結果）。
    校園賽在先搶期（`now > priority_end`）送出時，在同一個鎖與交易內當下分配（FR-15，
    Story 3.5）：優先期還沒結算就先結算（`settle_priority_window`），再以
    `_first_come_locked` 依送出順序判定所有 `pending`（殘留的先判定，本筆最後），
    操作者為系統，每筆發 `RegistrationAllocated`；回應帶正取或候補結果與順位。
    優先期內（`now <= priority_end`）與自訂模式維持 `pending`，由 worker 或之後的分配處理。
    鎖住賽事後只取一次當下時間，截止檢查、`submitted_at` 與先搶期判斷共用，所以已送出
    的報名一定早於報名截止時間（中間的查詢跨過截止時也一樣）。
    """
    team = repository.get_team(session, team_id)
    if team is None:
        raise _team_not_found()
    tournament = _lock_tournament(session, team.tournament_id)
    now = clock.now()
    members = repository.list_members(session, team.id)
    viewer = next((m for m in members if m.account_id == account_id), None)
    if viewer is None:
        raise _team_member_required()
    authz.ensure_captain(
        _team_read(team, members), account_id, message="只有隊長可以送出報名"
    )
    _ensure_registration_period(tournament, now=now)
    registration = _registration_of(session, team)
    if registration.status != RegistrationStatus.FORMING:
        raise _registration_already_submitted()

    entries = _roster_entries(session, members, _display_names(session, members))
    blockers = player_profile.submit_blockers(
        starters=tournament.starters, members=entries
    )
    if blockers:
        raise _requirements_unmet(blockers)

    # 送出條件保證每位都有段位積分、都設了學校且學校相同
    school_id = entries[0].school_id
    scores = [m.rank_score for m in members if m.rank_score is not None]
    avg_rank_score = player_profile.average_rank_score_decimal(scores)
    if school_id is None or avg_rank_score is None:
        # 送出條件已保證；不用 assert（python -O 會略過而把 null 寫進快照）
        raise RuntimeError("送出條件通過後仍缺學校或段位積分")
    submitted_at = now
    registration.school_id = school_id
    registration.avg_rank_score = avg_rank_score
    registration.submitted_at = submitted_at
    mark_status(
        session,
        registration=registration,
        to=RegistrationStatus.PENDING,
        actor_id=account_id,
    )
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=team.tournament_id,
        action="registration.submitted",
        entity_type="registration",
        entity_id=registration.id,
        before=None,
        after={
            "school_id": school_id,
            "avg_rank_score": avg_rank_score,
            "submitted_at": submitted_at,
        },
    )
    session.flush()
    if tournament.mode == TournamentMode.CAMPUS and now > tournament.priority_end:
        # 先搶期送出：_first_come_locked 不過濾優先期內的 pending，所以一定要先結算；
        # 同一交易內重新鎖同一列不會阻塞，已結算時不做任何事
        settle_priority_window(session, tournament_id=tournament.id)
        _first_come_locked(session, tournament, actor_id=None)
        session.flush()
    return _build_detail(session, team, tournament, viewer)


def list_my_teams(session: Session, *, account_id: uuid.UUID) -> list[MyTeamCard]:
    """S12 我的隊伍：帳號加入的每支隊伍與其報名狀態（新加入的在前）。"""
    cards: list[MyTeamCard] = []
    for membership in repository.list_memberships_of_account(session, account_id):
        team = repository.get_team(session, membership.team_id)
        assert team is not None  # 外鍵保證隊伍存在
        tournament = _get_tournament(session, team.tournament_id)
        registration = _registration_of(session, team)
        cards.append(
            MyTeamCard(
                team_id=team.id,
                team_name=team.name,
                tournament_id=team.tournament_id,
                tournament_name=tournament.name,
                game_name=tournament.game_name,
                registration_status=registration.status,
                **_waitlist_fields(session, registration, tournament).model_dump(),
            )
        )
    return cards


# ---------------------------------------------------------------- 優先期結算（Story 3.4）


def _priority_window_due(tournament: TournamentRead) -> bool:
    """校園賽、開放報名中，且優先期已結束。"""
    return (
        tournament.status == TournamentStatus.OPEN
        and tournament.mode == TournamentMode.CAMPUS
        and tournament.priority_end <= clock.now()
    )


def _allocate(
    session: Session,
    registration: Registration,
    status: RegistrationStatus,
    actor_id: uuid.UUID | None,
) -> None:
    """把報名分配為正取或候補：`mark_status` 並發 `RegistrationAllocated`。"""
    mark_status(session, registration=registration, to=status, actor_id=actor_id)
    events.publish(
        session,
        RegistrationAllocated(
            registration_id=registration.id,
            team_id=registration.team_id,
            tournament_id=registration.tournament_id,
            status=status,
        ),
    )


def _settle_locked(
    session: Session, tournament: TournamentRead, *, actor_id: uuid.UUID | None
) -> None:
    """已鎖定、尚未結算的賽事做優先期結算；不檢查賽事狀態與時間（由呼叫端決定）。

    只有 `pending` 且在優先期內（`submitted_at <= priority_end`）送出的報名參加結算。
    結果依 `allocation.allocate_priority_window`，逐筆改狀態並發事件，再寫結算紀錄
    （`settled_at` 為當下時間，提前抽籤時可能早於 `priority_end`）與一筆摘要。
    """
    registrations = {
        r.id: r
        for r in repository.list_registrations(session, tournament.id)
        if r.status == RegistrationStatus.PENDING
        and r.submitted_at is not None
        and r.submitted_at <= tournament.priority_end
    }
    candidates = [_candidate(r) for r in registrations.values()]
    result = allocation.allocate_priority_window(
        candidates, capacity=tournament.capacity
    )
    outcomes = [
        *((i, RegistrationStatus.ACCEPTED) for i in result.accepted),
        *((i, RegistrationStatus.WAITLISTED) for i in result.waitlisted),
    ]
    for registration_id, status in outcomes:
        _allocate(session, registrations[registration_id], status, actor_id)

    priority_school_ids = sorted({c.school_id for c in candidates})
    repository.add_settlement(
        session,
        PriorityWindowSettlement(
            tournament_id=tournament.id,
            settled_at=clock.now(),
            priority_school_ids=priority_school_ids,
        ),
    )
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament.id,
        action="registration.priority_window_settled",
        entity_type="tournament",
        entity_id=tournament.id,
        before=None,
        after={
            "capacity": tournament.capacity,
            "accepted": list(result.accepted),
            "waitlisted": list(result.waitlisted),
            "priority_school_ids": priority_school_ids,
        },
    )
    session.flush()


def settle_priority_window(session: Session, *, tournament_id: uuid.UUID) -> bool:
    """優先期結算（FR-14）：鎖住賽事，在同一個鎖與交易內完成；回傳這次是否結算。

    鎖內重新檢查：已有結算紀錄、賽事不是開放中的校園賽、或優先期還沒結束時不做任何事
    （回傳 False），所以重複呼叫結果不變。只有 `pending` 且在優先期內（`submitted_at <=
    priority_end`）送出的報名參加結算；優先期後送出的 `pending` 維持原狀，由先搶期送出
    （`submit_registration`）或報名截止、抽籤時的 `_first_come_locked` 判定。
    結果依 `allocation.allocate_priority_window`，逐筆以 `mark_status` 改狀態（操作者為
    系統）並發 `RegistrationAllocated`，再寫結算紀錄（保存優先期有報名的學校，可為空）
    與一筆 `registration.priority_window_settled` 摘要。抽籤（`finalize_for_draw`）不呼叫
    本函式：提前抽籤時優先期可能還沒結束，改直接用鎖內的 `_settle_locked`。
    """
    tournament = _lock_tournament(session, tournament_id)
    if repository.get_settlement(session, tournament.id) is not None:
        return False
    if not _priority_window_due(tournament):
        return False
    _settle_locked(session, tournament, actor_id=None)
    return True


def allocate_due_priority_window(session: Session) -> bool:
    """worker 用：結算一場優先期已結束、尚未結算的賽事；回傳是否結算了一場。

    候選是「有 `pending`、尚未結算」的賽事（registration 不能直接查賽事表），以
    `get_tournament` 篩出到期的，再交給 `settle_priority_window` 在鎖內重新檢查。
    沒有到期的候選時回傳 False，worker 才會換下一個工作。
    """
    for tournament_id in repository.list_unsettled_pending_tournament_ids(session):
        if _priority_window_due(_get_tournament(session, tournament_id)):
            if settle_priority_window(session, tournament_id=tournament_id):
                return True
    return False


# ---------------------------------------------------------------- 抽籤前的分配（Story 3.6）

# 先搶期判定時參考的狀態：待分配的報名不計入正取，但要能出現在 candidates 裡
_FIRST_COME_STATUSES = _ORDER_STATUSES | {RegistrationStatus.PENDING}


def _priority_schools(
    session: Session, tournament_id: uuid.UUID
) -> frozenset[uuid.UUID]:
    settlement = repository.get_settlement(session, tournament_id)
    return frozenset(settlement.priority_school_ids) if settlement else frozenset()


def _registrations_in(
    session: Session, tournament_id: uuid.UUID, statuses: frozenset[RegistrationStatus]
) -> dict[uuid.UUID, Registration]:
    return {
        r.id: r
        for r in repository.list_registrations(session, tournament_id)
        if r.status in statuses
    }


def _first_come_locked(
    session: Session, tournament: TournamentRead, *, actor_id: uuid.UUID | None
) -> None:
    """已鎖定的賽事補做先搶期（FR-15）：仍為 `pending` 的報名依送出時間（同時再依 id）逐筆判定。

    每一筆都以最新狀態重建 candidates：先讓當下有順位的候補依 `backfill_vacancies`
    遞補為正取，再以 `decide_first_come` 判定這一筆；前一筆剛正取的隊伍因此會算進
    學校資格與名額。`priority_schools` 取自結算紀錄（沒有紀錄時為空集合）。
    """
    priority_schools = _priority_schools(session, tournament.id)
    pending = sorted(
        _registrations_in(
            session, tournament.id, frozenset({RegistrationStatus.PENDING})
        ).values(),
        key=lambda r: (_candidate(r).submitted_at, r.id),
    )
    for registration in pending:
        current = _registrations_in(session, tournament.id, _FIRST_COME_STATUSES)
        backfilled = allocation.backfill_vacancies(
            [_candidate(r) for r in current.values()],
            phase=allocation.AllocationPhase.FIRST_COME,
            priority_schools=priority_schools,
            capacity=tournament.capacity,
        )
        for registration_id in backfilled:
            _allocate(
                session, current[registration_id], RegistrationStatus.ACCEPTED, actor_id
            )
        status = allocation.decide_first_come(
            _candidate(registration),
            candidates=[_candidate(r) for r in current.values()],
            priority_schools=priority_schools,
            capacity=tournament.capacity,
        )
        _allocate(session, registration, status, actor_id)


def _fill_at_deadline_locked(
    session: Session, tournament: TournamentRead, *, actor_id: uuid.UUID | None
) -> None:
    """已鎖定的賽事做截止補位（FR-16）：剩餘名額由候補依報名截止後的順位補上。

    剩餘名額＝max(名額 − 目前正取（`accepted`＋`drawn`）, 0)；`fill_from_waitlist` 的
    前 N 名改為正取，補位後仍有空位就保留。重複呼叫時已沒有可補的候補，結果不變。
    """
    current = _registrations_in(session, tournament.id, _ORDER_STATUSES)
    accepted = sum(
        1
        for r in current.values()
        if r.status in (RegistrationStatus.ACCEPTED, RegistrationStatus.DRAWN)
    )
    remaining = max(tournament.capacity - accepted, 0)
    for registration_id in allocation.fill_from_waitlist(
        [_candidate(r) for r in current.values()], remaining=remaining
    ):
        _allocate(
            session, current[registration_id], RegistrationStatus.ACCEPTED, actor_id
        )


# ---------------------------------------------------------------- 報名截止（Story 3.6）


def close_registration(session: Session, *, tournament_id: uuid.UUID) -> bool:
    """報名截止（FR-16）：鎖住賽事，在同一個鎖與交易內完成分配再轉「報名截止」。

    鎖內重新檢查賽事仍為開放報名且報名截止時間已到；不成立時不做任何事（回傳 False），
    所以重複呼叫結果不變。校園賽依序：沒有結算紀錄時先做優先期結算（沒有報名也寫一筆
    空的結算紀錄）、補做先搶期、截止補位，最後轉為 `closed`；自訂模式只轉狀態。
    操作者全部為系統（`None`），分配與補位發 `RegistrationAllocated`。
    """
    tournament = _lock_tournament(session, tournament_id)
    if (
        tournament.status != TournamentStatus.OPEN
        or tournament.registration_end > clock.now()
    ):
        return False
    if tournament.mode == TournamentMode.CAMPUS:
        if repository.get_settlement(session, tournament.id) is None:
            _settle_locked(session, tournament, actor_id=None)
        _first_come_locked(session, tournament, actor_id=None)
        _fill_at_deadline_locked(session, tournament, actor_id=None)
    tournaments_service.transition_tournament(
        session,
        tournament_id=tournament.id,
        to=TournamentStatus.CLOSED,
        actor_id=None,
    )
    session.flush()
    return True


def close_due_registration(session: Session) -> bool:
    """worker 用：關閉一場報名截止已到、仍為開放報名的賽事；回傳是否找到候選。

    候選由 tournaments `find_due_registration_end_id` 找（最早到期的優先），再交給
    `close_registration` 在鎖內重新檢查；沒有候選時回傳 False，worker 才會換下一個工作。
    """
    tournament_id = tournaments_service.find_due_registration_end_id(session)
    if tournament_id is None:
        return False
    close_registration(session, tournament_id=tournament_id)
    return True


# ---------------------------------------------------------------- 公開函式（給其他模組）


def get_team(session: Session, *, team_id: uuid.UUID) -> TeamRead:
    """不存在拋 404 `TEAM_NOT_FOUND`。"""
    team = repository.get_team(session, team_id)
    if team is None:
        raise _team_not_found()
    return _team_read(team, repository.list_members(session, team.id))


def get_registration(session: Session, *, team_id: uuid.UUID) -> RegistrationRead:
    """隊伍的報名（與隊伍一對一）；不存在拋 404 `REGISTRATION_NOT_FOUND`。"""
    registration = repository.get_registration_by_team(session, team_id)
    if registration is None:
        raise _registration_not_found()
    return RegistrationRead.model_validate(registration, from_attributes=True)


def is_member(session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    return repository.get_team_member(session, team_id, account_id) is not None


def is_captain(session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    member = repository.get_team_member(session, team_id, account_id)
    return member is not None and member.role == MemberRole.CAPTAIN


# ---------------------------------------------------------------- 抽籤用（competition 4.1，Story 3.6）


def _registration_not_accepted() -> BusinessError:
    return BusinessError(
        "REGISTRATION_NOT_ACCEPTED",
        "有隊伍不是這個賽事的正取，無法標為已參賽。",
        status_code=409,
    )


def finalize_for_draw(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """開放報名中抽籤前完成分配（提前抽籤＝提前結束報名）；重複呼叫結果不變。

    先鎖住賽事；賽事不是開放報名或不是校園賽時不做任何事。否則在同一個交易依序：

    1. 優先期結算：沒有結算紀錄時立即以當下已送出的優先期內報名結算（不檢查優先期
       是否已結束）。
    2. 補做先搶期：優先期後送出、仍為 `pending` 的報名依送出順序判定。
    3. 截止補位：剩餘名額由候補依報名截止後的順位補上。

    所有狀態變更與結算摘要的操作者都是 `actor_id`（抽籤的主辦方）。
    """
    tournament = _lock_tournament(session, tournament_id)
    if (
        tournament.status != TournamentStatus.OPEN
        or tournament.mode != TournamentMode.CAMPUS
    ):
        return
    if repository.get_settlement(session, tournament.id) is None:
        _settle_locked(session, tournament, actor_id=actor_id)
    _first_come_locked(session, tournament, actor_id=actor_id)
    _fill_at_deadline_locked(session, tournament, actor_id=actor_id)


def list_accepted_teams(
    session: Session, *, tournament_id: uuid.UUID
) -> list[TeamRead]:
    """報名為正取（`accepted`）的隊伍，依隊伍 id 排序；隊伍與成員一次查出。"""
    return [
        _team_read(team, members)
        for team, members in repository.list_teams_with_members_by_status(
            session, tournament_id, RegistrationStatus.ACCEPTED
        )
    ]


def mark_drawn(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    team_ids: Sequence[uuid.UUID],
    actor_id: uuid.UUID,
) -> None:
    """抽籤的隊伍由正取（`accepted`）改為已參賽（`drawn`）；不發事件。

    先鎖住賽事；`team_ids` 去重，空清單不做任何事。有任何 id 不存在、不屬於該賽事、
    或報名不是正取時整批拒絕（409 `REGISTRATION_NOT_ACCEPTED`），不做部分更新。
    已是 `drawn` 再呼叫也會被拒絕。
    """
    _lock_tournament(session, tournament_id)
    unique_ids = set(team_ids)
    if not unique_ids:
        return
    registrations = repository.list_registrations_by_team_ids(session, unique_ids)
    if len(registrations) != len(unique_ids) or any(
        r.tournament_id != tournament_id or r.status != RegistrationStatus.ACCEPTED
        for r in registrations
    ):
        raise _registration_not_accepted()
    for registration in registrations:
        mark_status(
            session,
            registration=registration,
            to=RegistrationStatus.DRAWN,
            actor_id=actor_id,
        )


def get_team_names(
    session: Session, *, team_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """依隊伍 id 一次查隊名；不看賽事與報名狀態，不存在的 id 不出現。"""
    return {
        team.id: team.name
        for team in repository.list_teams_by_ids(session, set(team_ids))
    }


# ---------------------------------------------------------------- 檢舉用（disputes 6.4）


def find_team_of_account(
    session: Session, *, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> TeamRead | None:
    """帳號在該賽事所屬的隊伍（不限角色）；不在任何隊伍時回 None。

    同一帳號在一個賽事最多只在一支隊伍（`uq_team_member_tournament_id_account_id`）。
    """
    membership = repository.get_membership(session, tournament_id, account_id)
    if membership is None:
        return None
    team = repository.get_team(session, membership.team_id)
    if team is None:
        return None
    return _team_read(team, repository.list_members(session, team.id))


def list_teams_by_status(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    statuses: Collection[RegistrationStatus],
) -> list[TeamSummary]:
    """某賽事報名狀態在 `statuses` 之內的隊伍（只有 id、隊名，依隊伍 id 排列）。"""
    return [
        TeamSummary(id=team.id, name=team.name)
        for team in repository.list_teams_by_status(session, tournament_id, statuses)
    ]
