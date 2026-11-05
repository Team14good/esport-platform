"""tournaments 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app.core import audit, authz, clock
from app.core.errors import BusinessError, FieldError
from app.modules.identity import service as identity_service
from app.modules.tournaments import repository
from app.modules.tournaments.models import (
    REFEREE_INVITATION_DAYS,
    REFEREE_INVITATION_TOKEN_BYTES,
    GameIn,
    GameRead,
    GameTitle,
    PublicRefereeInvitation,
    PublicTournament,
    RankTier,
    RankTierRead,
    RefereeInvitation,
    RefereeInvitationRead,
    RefereeRead,
    Tournament,
    TournamentCreate,
    TournamentMode,
    TournamentRead,
    TournamentReferee,
    TournamentStatus,
)

# 遊戲本身的欄位（段位表另外處理）
_GAME_FIELDS = (
    "name",
    "starters",
    "substitutes",
    "default_bo",
    "game_minutes",
    "score_type",
)


# ---------------------------------------------------------------- 遊戲設定
# 程式中不得依遊戲名稱或 id 寫分支（AD-18）：所有差異都來自設定值。


def _game_not_found() -> BusinessError:
    return BusinessError("GAME_NOT_FOUND", "找不到這款遊戲。", status_code=404)


def _game_name_taken() -> BusinessError:
    return BusinessError("GAME_NAME_TAKEN", "已經有同名的遊戲。", status_code=409)


def _sorted_tiers(tiers: list[RankTierRead]) -> list[RankTierRead]:
    """積分由高到低；同分依名稱（逐碼位）排列，與資料庫的 COLLATE "C" 一致。"""
    return sorted(tiers, key=lambda tier: (-tier.score, tier.name))


def _to_read(game: GameTitle, tiers: list[RankTier]) -> GameRead:
    return GameRead(
        id=game.id,
        name=game.name,
        starters=game.starters,
        substitutes=game.substitutes,
        default_bo=game.default_bo,
        game_minutes=game.game_minutes,
        score_type=game.score_type,
        rank_tiers=_sorted_tiers(
            [RankTierRead(name=tier.name, score=tier.score) for tier in tiers]
        ),
    )


def _new_tiers(game_id: uuid.UUID, data: GameIn) -> list[RankTier]:
    return [
        RankTier(game_id=game_id, name=tier.name, score=tier.score)
        for tier in data.rank_tiers
    ]


def _tiers_for_audit(tiers: list[RankTierRead]) -> list[dict[str, Any]]:
    return [tier.model_dump() for tier in _sorted_tiers(tiers)]


def list_games(session: Session) -> list[GameRead]:
    """所有遊戲，依名稱排序。"""
    games = repository.list_games(session)
    tiers_by_game: dict[uuid.UUID, list[RankTier]] = {game.id: [] for game in games}
    for tier in repository.list_rank_tiers(session, list(tiers_by_game)):
        tiers_by_game[tier.game_id].append(tier)
    return [_to_read(game, tiers_by_game[game.id]) for game in games]


def get_game(session: Session, *, game_id: uuid.UUID) -> GameRead:
    """讀取一款遊戲的設定（2.2 建立賽事時複製成快照）；不存在拋 404 `GAME_NOT_FOUND`。"""
    game = repository.get_game(session, game_id)
    if game is None:
        raise _game_not_found()
    return _to_read(game, repository.list_rank_tiers(session, [game.id]))


def create_game(session: Session, *, actor_id: uuid.UUID, data: GameIn) -> GameRead:
    """新增遊戲；名稱（去除前後空白、不分大小寫）重複拋 409 `GAME_NAME_TAKEN`。"""
    if repository.get_game_by_name(session, data.name) is not None:
        raise _game_name_taken()
    now = clock.now()
    game = GameTitle(
        name=data.name,
        starters=data.starters,
        substitutes=data.substitutes,
        default_bo=data.default_bo,
        game_minutes=data.game_minutes,
        score_type=data.score_type,
        created_at=now,
        updated_at=now,
    )
    tiers = _new_tiers(game.id, data)
    try:
        repository.add_game(session, game, tiers)
    except repository.DuplicateGameNameError:
        # 兩個請求同時新增同名遊戲：後到的撞到唯一索引
        raise _game_name_taken() from None

    created = _to_read(game, tiers)
    after: dict[str, Any] = {field: getattr(created, field) for field in _GAME_FIELDS}
    after["rank_tiers"] = _tiers_for_audit(created.rank_tiers)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=None,
        action="game.created",
        entity_type="game",
        entity_id=game.id,
        before=None,
        after=after,
    )
    return created


def update_game(
    session: Session, *, actor_id: uuid.UUID, game_id: uuid.UUID, data: GameIn
) -> GameRead:
    """整份替換遊戲設定（含段位表）。

    不存在拋 404 `GAME_NOT_FOUND`；改成其他遊戲的名稱拋 409 `GAME_NAME_TAKEN`。
    有變動時寫 `game.updated`，before／after 只含有變動的欄位（段位表以整份比較）。
    """
    game = repository.get_game(session, game_id, for_update=True)
    if game is None:
        raise _game_not_found()
    current = _to_read(game, repository.list_rank_tiers(session, [game.id]))

    same_name = repository.get_game_by_name(session, data.name)
    if same_name is not None and same_name.id != game.id:
        raise _game_name_taken()

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _GAME_FIELDS:
        old, new = getattr(current, field), getattr(data, field)
        if old != new:
            before[field] = old
            after[field] = new
    old_tiers = _tiers_for_audit(current.rank_tiers)
    new_tiers = _tiers_for_audit(
        [RankTierRead(name=tier.name, score=tier.score) for tier in data.rank_tiers]
    )
    if old_tiers != new_tiers:
        before["rank_tiers"] = old_tiers
        after["rank_tiers"] = new_tiers

    if not after:
        return current

    changes = {field: after[field] for field in _GAME_FIELDS if field in after}
    changes["updated_at"] = clock.now()
    try:
        repository.update_game(session, game, changes)
    except repository.DuplicateGameNameError:
        # 等鎖期間另一個請求把別款遊戲改成這個名稱
        raise _game_name_taken() from None
    if "rank_tiers" in after:
        repository.replace_rank_tiers(session, game.id, _new_tiers(game.id, data))

    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=None,
        action="game.updated",
        entity_type="game",
        entity_id=game.id,
        before=before,
        after=after,
    )
    return get_game(session, game_id=game.id)


# ---------------------------------------------------------------- 賽事
# 遊戲相關的值在建立時複製進 game_snapshot，之後只讀快照（AD-12）。

# 允許的狀態轉換（contracts/tournaments.md〈三〉）
_TRANSITIONS: dict[TournamentStatus, frozenset[TournamentStatus]] = {
    TournamentStatus.UPCOMING: frozenset(
        {TournamentStatus.OPEN, TournamentStatus.CANCELLED}
    ),
    TournamentStatus.OPEN: frozenset(
        {
            TournamentStatus.CLOSED,
            TournamentStatus.PUBLISHED,
            TournamentStatus.CANCELLED,
        }
    ),
    TournamentStatus.CLOSED: frozenset(
        {
            TournamentStatus.OPEN,
            TournamentStatus.PUBLISHED,
            TournamentStatus.CANCELLED,
        }
    ),
    TournamentStatus.PUBLISHED: frozenset(
        {TournamentStatus.ONGOING, TournamentStatus.CANCELLED}
    ),
    TournamentStatus.ONGOING: frozenset(
        {TournamentStatus.FINISHED, TournamentStatus.CANCELLED}
    ),
    TournamentStatus.FINISHED: frozenset(),
    TournamentStatus.CANCELLED: frozenset(),
}

_SCORING_STATUSES = frozenset({TournamentStatus.PUBLISHED, TournamentStatus.ONGOING})


def _tournament_not_found() -> BusinessError:
    return BusinessError("TOURNAMENT_NOT_FOUND", "找不到這場賽事。", status_code=404)


def _field_error(field: str, code: str, message: str) -> FieldError:
    return FieldError(code, message, loc=("body", field))


def _tournament_to_read(tournament: Tournament) -> TournamentRead:
    snapshot = tournament.game_snapshot
    return TournamentRead(
        id=tournament.id,
        organizer_id=tournament.organizer_id,
        name=tournament.name,
        status=tournament.status,
        mode=tournament.mode,
        capacity=tournament.capacity,
        registration_start=tournament.registration_start,
        priority_end=tournament.priority_end,
        registration_end=tournament.registration_end,
        start_at=tournament.start_at,
        round_interval_minutes=tournament.round_interval_minutes,
        forfeit_minutes=tournament.forfeit_minutes,
        appeal_minutes=tournament.appeal_minutes,
        livestream_url=tournament.livestream_url,
        game_id=tournament.game_id,
        game_name=snapshot["game_name"],
        starters=snapshot["starters"],
        substitutes=snapshot["substitutes"],
        bo=snapshot["bo"],
        game_minutes=snapshot["game_minutes"],
        score_type=snapshot["score_type"],
        rank_tiers=[RankTierRead.model_validate(t) for t in snapshot["rank_tiers"]],
    )


def min_round_interval(
    *, forfeit_minutes: int, bo: int, game_minutes: int, appeal_minutes: int
) -> int:
    """每輪間隔的下限：棄權時限＋BO × 每局預估時間＋申訴期（分鐘）。"""
    return forfeit_minutes + bo * game_minutes + appeal_minutes


def _validate_schedule(
    data: TournamentCreate, *, bo: int, game_minutes: int, now: datetime
) -> None:
    """要對照現在時間或遊戲設定的欄位檢查；違反時拋 422 並指向欄位。"""
    if data.start_at <= now:
        raise _field_error("start_at", "START_AT_PASSED", "開賽時間必須晚於現在")
    if data.registration_end > data.start_at:
        raise _field_error(
            "registration_end",
            "REGISTRATION_END_AFTER_START",
            "報名截止不能晚於開賽時間",
        )
    if data.registration_end <= now:
        raise _field_error(
            "registration_end", "REGISTRATION_END_PASSED", "報名截止必須晚於現在"
        )
    if data.registration_start >= data.registration_end:
        raise _field_error(
            "registration_start",
            "REGISTRATION_START_NOT_BEFORE_END",
            "報名開始必須早於報名截止",
        )
    # 以時間長度比較，避免極大的優先期在相加時溢位
    if timedelta(hours=data.priority_hours) > (
        data.registration_end - data.registration_start
    ):
        raise _field_error(
            "priority_hours",
            "PRIORITY_END_AFTER_REGISTRATION_END",
            "優先期結束（報名開始＋優先期）不能晚於報名截止",
        )
    minimum = min_round_interval(
        forfeit_minutes=data.forfeit_minutes,
        bo=bo,
        game_minutes=game_minutes,
        appeal_minutes=data.appeal_minutes,
    )
    if data.round_interval_minutes < minimum:
        raise _field_error(
            "round_interval_minutes",
            "ROUND_INTERVAL_TOO_SHORT",
            f"每輪間隔至少 {minimum} 分鐘",
        )


def create_tournament(
    session: Session, *, organizer_id: uuid.UUID, data: TournamentCreate
) -> TournamentRead:
    """建立賽事（期中一律校園賽）並複製遊戲快照；寫 `tournament.created`。

    遊戲不存在拋 404 `GAME_NOT_FOUND`；欄位不合法拋 422（`FieldError`，指向欄位）。
    報名開始已到時狀態為 `open`，否則為 `upcoming`（由 worker 到時開放）。
    """
    # 以 FOR SHARE 鎖住遊戲列：修改遊戲（FOR UPDATE）要等本交易結束，遊戲欄位與
    # 段位表因此取自同一個版本；多個主辦方同時以同一款遊戲建立賽事則不互相等待
    game_row = repository.get_game(session, data.game_id, for_share=True)
    if game_row is None:
        raise _game_not_found()
    game = _to_read(game_row, repository.list_rank_tiers(session, [game_row.id]))

    starters = data.starters if data.starters is not None else game.starters
    substitutes = data.substitutes if data.substitutes is not None else game.substitutes
    bo = data.bo if data.bo is not None else game.default_bo
    now = clock.now()
    _validate_schedule(data, bo=bo, game_minutes=game.game_minutes, now=now)

    registration_start = data.registration_start.astimezone(UTC)
    tournament = Tournament(
        organizer_id=organizer_id,
        game_id=game.id,
        name=data.name,
        status=(
            TournamentStatus.OPEN
            if registration_start <= now
            else TournamentStatus.UPCOMING
        ),
        mode=TournamentMode.CAMPUS,
        capacity=data.capacity,
        registration_start=registration_start,
        priority_end=registration_start + timedelta(hours=data.priority_hours),
        registration_end=data.registration_end.astimezone(UTC),
        start_at=data.start_at.astimezone(UTC),
        round_interval_minutes=data.round_interval_minutes,
        forfeit_minutes=data.forfeit_minutes,
        appeal_minutes=data.appeal_minutes,
        livestream_url=data.livestream_url,
        game_snapshot={
            "game_name": game.name,
            "starters": starters,
            "substitutes": substitutes,
            "bo": bo,
            "game_minutes": game.game_minutes,
            "score_type": game.score_type.value,
            "rank_tiers": [tier.model_dump() for tier in game.rank_tiers],
        },
        created_at=now,
        updated_at=now,
    )
    repository.add_tournament(session, tournament)

    created = _tournament_to_read(tournament)
    audit.record(
        session,
        actor_id=organizer_id,
        tournament_id=tournament.id,
        action="tournament.created",
        entity_type="tournament",
        entity_id=tournament.id,
        before=None,
        after=created.model_dump(exclude={"id"}),
    )
    return created


def get_tournament(session: Session, *, tournament_id: uuid.UUID) -> TournamentRead:
    """讀取賽事；不存在拋 404 `TOURNAMENT_NOT_FOUND`。"""
    tournament = repository.get_tournament(session, tournament_id)
    if tournament is None:
        raise _tournament_not_found()
    return _tournament_to_read(tournament)


def lock_tournament(session: Session, *, tournament_id: uuid.UUID) -> TournamentRead:
    """`SELECT ... FOR UPDATE` 鎖住賽事列並回傳最新值；鎖賽事的唯一入口（AD-6）。

    同時要鎖場次等其他資料時，先鎖賽事。不存在拋 404 `TOURNAMENT_NOT_FOUND`。
    """
    tournament = repository.get_tournament(session, tournament_id, for_update=True)
    if tournament is None:
        raise _tournament_not_found()
    return _tournament_to_read(tournament)


def _tournament_to_public(tournament: Tournament) -> PublicTournament:
    return PublicTournament(
        id=tournament.id,
        name=tournament.name,
        status=tournament.status,
        game_name=tournament.game_snapshot["game_name"],
        capacity=tournament.capacity,
        registration_start=tournament.registration_start,
        priority_end=tournament.priority_end,
        registration_end=tournament.registration_end,
        start_at=tournament.start_at,
        round_interval_minutes=tournament.round_interval_minutes,
        livestream_url=tournament.livestream_url,
    )


def list_public_tournaments(session: Session) -> list[PublicTournament]:
    """所有賽事的公開資料（不需登入），依開賽時間排序。"""
    return [
        _tournament_to_public(tournament)
        for tournament in repository.list_tournaments(session)
    ]


def get_public_tournament(
    session: Session, *, tournament_id: uuid.UUID
) -> PublicTournament:
    """一場賽事的公開資料（不需登入）；不存在拋 404 `TOURNAMENT_NOT_FOUND`。"""
    tournament = repository.get_tournament(session, tournament_id)
    if tournament is None:
        raise _tournament_not_found()
    return _tournament_to_public(tournament)


def list_organizer_tournaments(
    session: Session, *, organizer_id: uuid.UUID
) -> list[TournamentRead]:
    """某主辦方建立的賽事，新建立的在前。"""
    return [
        _tournament_to_read(tournament)
        for tournament in repository.list_tournaments_by_organizer(
            session, organizer_id
        )
    ]


def transition_tournament(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    to: TournamentStatus,
    actor_id: uuid.UUID | None,
) -> TournamentRead:
    """改變賽事狀態的唯一入口（AD-11）；寫 `tournament.status_changed`。

    呼叫前應先 `lock_tournament`（這裡也會再鎖一次，同一交易內不會等待）。
    不允許的轉換拋 409 `TOURNAMENT_INVALID_TRANSITION`；`actor_id=None` 表示系統。
    """
    tournament = repository.get_tournament(session, tournament_id, for_update=True)
    if tournament is None:
        raise _tournament_not_found()
    current = TournamentStatus(tournament.status)
    if to not in _TRANSITIONS[current]:
        raise BusinessError(
            "TOURNAMENT_INVALID_TRANSITION",
            "賽事目前的狀態不能進行這個操作。",
            status_code=409,
        )
    repository.set_tournament_status(session, tournament, to, clock.now())
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament.id,
        action="tournament.status_changed",
        entity_type="tournament",
        entity_id=tournament.id,
        before={"status": current.value},
        after={"status": to.value},
    )
    return _tournament_to_read(tournament)


def ensure_accepting_registrations(tournament: TournamentRead) -> None:
    """賽事開放報名中；否則拋 409 `REGISTRATION_CLOSED`。只看狀態，不碰資料庫。"""
    if tournament.status != TournamentStatus.OPEN:
        raise BusinessError(
            "REGISTRATION_CLOSED", "這場賽事目前不開放報名。", status_code=409
        )


def ensure_accepting_scores(tournament: TournamentRead) -> None:
    """賽程已公布或進行中；否則拋 409 `TOURNAMENT_NOT_ACCEPTING_SCORES`。不碰資料庫。"""
    if tournament.status not in _SCORING_STATUSES:
        raise BusinessError(
            "TOURNAMENT_NOT_ACCEPTING_SCORES",
            "這場賽事目前不接受比分回報。",
            status_code=409,
        )


def bo_for_round(session: Session, *, tournament_id: uuid.UUID, round_no: int) -> int:
    """某一輪（從 1 起算）的 BO；期中不做分輪 BO（2.3），一律回傳賽事的 BO。"""
    if round_no < 1:
        raise ValueError(f"round_no must start from 1: {round_no}")
    return get_tournament(session, tournament_id=tournament_id).bo


def open_due_registration(session: Session) -> bool:
    """worker 用：把一筆報名開始已到的 `upcoming` 賽事轉為 `open`（操作者為系統）。

    先找到候選、鎖住後重新檢查；已被其他 worker 處理過就不做任何事。
    回傳是否找到候選（找到就可能還有下一筆）。
    """
    now = clock.now()
    tournament_id = repository.find_due_upcoming_id(session, now)
    if tournament_id is None:
        return False
    tournament = lock_tournament(session, tournament_id=tournament_id)
    if (
        tournament.status == TournamentStatus.UPCOMING
        and tournament.registration_start <= now
    ):
        transition_tournament(
            session,
            tournament_id=tournament_id,
            to=TournamentStatus.OPEN,
            actor_id=None,
        )
    return True


# ---------------------------------------------------------------- 裁判
# 邀請 7 天有效，`expires_at <= clock.now()` 即過期。重新產生時，同賽事尚未過期的
# 舊邀請 `expires_at` 設為當下。產生與接受都先 `lock_tournament` 再碰邀請列（鎖的順序
# 一致，不會死結），所以接受不會用到已作廢的邀請，也不會與賽事轉為已結束／已取消交錯。

_REFEREE_CLOSED_STATUSES = frozenset(
    {TournamentStatus.FINISHED, TournamentStatus.CANCELLED}
)


def _invitation_not_found() -> BusinessError:
    return BusinessError(
        "REFEREE_INVITATION_NOT_FOUND", "找不到這個裁判邀請。", status_code=404
    )


def _is_expired(invitation: RefereeInvitation, now: datetime) -> bool:
    return invitation.expires_at <= now


def _is_accepting_referees(tournament: TournamentRead) -> bool:
    return tournament.status not in _REFEREE_CLOSED_STATUSES


def _invitation_to_read(
    invitation: RefereeInvitation, tournament: TournamentRead, now: datetime
) -> RefereeInvitationRead:
    return RefereeInvitationRead(
        tournament_id=invitation.tournament_id,
        token=invitation.token,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        expired=_is_expired(invitation, now),
        accepting=_is_accepting_referees(tournament),
    )


def ensure_accepting_referees(
    tournament: TournamentRead,
    *,
    message: str = "這場賽事已結束或已取消，不能再邀請裁判。",
) -> None:
    """賽事不是已結束或已取消；否則拋 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。

    產生與接受裁判邀請前檢查；不碰資料庫。`message` 讓接受邀請時換成給受邀者的說明。
    """
    if not _is_accepting_referees(tournament):
        raise BusinessError(
            "TOURNAMENT_NOT_ACCEPTING_REFEREES", message, status_code=409
        )


def invite_referee(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> RefereeInvitationRead:
    """主辦方產生新的裁判邀請（7 天有效），同賽事尚未過期的舊邀請立即作廢。

    寫 `referee_invitation.created`（不記 token）。不存在拋 404、不是主辦方本人拋 403、
    已結束或已取消拋 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
    """
    tournament = lock_tournament(session, tournament_id=tournament_id)
    authz.ensure_tournament_owner(tournament, actor_id)
    ensure_accepting_referees(tournament)

    now = clock.now()
    repository.expire_active_invitations(session, tournament_id, now)
    invitation = RefereeInvitation(
        tournament_id=tournament_id,
        token=secrets.token_urlsafe(REFEREE_INVITATION_TOKEN_BYTES),
        created_by=actor_id,
        created_at=now,
        expires_at=now + timedelta(days=REFEREE_INVITATION_DAYS),
    )
    repository.add_invitation(session, invitation)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament_id,
        action="referee_invitation.created",
        entity_type="referee_invitation",
        entity_id=invitation.id,
        before=None,
        after={"expires_at": invitation.expires_at},
    )
    return _invitation_to_read(invitation, tournament, now)


def get_current_invitation(
    session: Session, *, tournament_id: uuid.UUID
) -> RefereeInvitationRead | None:
    """同賽事最新的一筆邀請（含是否過期、賽事是否仍接受裁判）；從未產生過回 None。

    權限由呼叫端檢查。
    """
    invitation = repository.get_latest_invitation(session, tournament_id)
    if invitation is None:
        return None
    tournament = get_tournament(session, tournament_id=tournament_id)
    return _invitation_to_read(invitation, tournament, clock.now())


def preview_invitation(session: Session, *, token: str) -> PublicRefereeInvitation:
    """不需登入的邀請預覽：賽事名稱、到期時間、是否過期、賽事是否仍接受裁判
    （AD-19，不含帳號資料）。

    不存在拋 404 `REFEREE_INVITATION_NOT_FOUND`。
    """
    invitation = repository.get_invitation_by_token(session, token)
    if invitation is None:
        raise _invitation_not_found()
    tournament = get_tournament(session, tournament_id=invitation.tournament_id)
    return PublicRefereeInvitation(
        tournament_name=tournament.name,
        expires_at=invitation.expires_at,
        expired=_is_expired(invitation, clock.now()),
        accepting=_is_accepting_referees(tournament),
    )


def _referee_to_read(referee: TournamentReferee, display_name: str) -> RefereeRead:
    return RefereeRead(
        account_id=referee.account_id,
        display_name=display_name,
        accepted_at=referee.accepted_at,
    )


def accept_invitation(
    session: Session, *, token: str, account_id: uuid.UUID
) -> RefereeRead:
    """受邀者（已驗證帳號，由 router 檢查）接受邀請，成為該賽事的裁判。

    依序檢查：不存在 404 `REFEREE_INVITATION_NOT_FOUND`、過期或已作廢 409
    `REFEREE_INVITATION_EXPIRED`、已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`、
    主辦方本人 409 `ORGANIZER_CANNOT_BE_REFEREE`。已是裁判時回傳原本的資料（冪等），
    只有第一次接受寫 `referee.accepted`（不記 token）。
    """
    found = repository.get_invitation_by_token(session, token)
    if found is None:
        raise _invitation_not_found()
    # 與重新產生相同的鎖順序：先鎖賽事，再以 FOR SHARE 重新讀邀請列（取得最新的到期時間）
    tournament = lock_tournament(session, tournament_id=found.tournament_id)
    invitation = repository.get_invitation_by_token(session, token, for_share=True)
    if invitation is None:  # 邀請不會被刪除
        raise _invitation_not_found()
    now = clock.now()
    if _is_expired(invitation, now):
        raise BusinessError(
            "REFEREE_INVITATION_EXPIRED",
            "此裁判邀請已過期，請向主辦方索取新連結。",
            status_code=409,
        )
    ensure_accepting_referees(
        tournament, message="這場賽事已結束或已取消，無法接受裁判邀請。"
    )
    if tournament.organizer_id == account_id:
        raise BusinessError(
            "ORGANIZER_CANNOT_BE_REFEREE",
            "主辦方不能擔任自己賽事的裁判。",
            status_code=409,
        )

    created = repository.add_referee(
        session,
        TournamentReferee(
            tournament_id=tournament.id,
            account_id=account_id,
            invitation_id=invitation.id,
            accepted_at=now,
        ),
    )
    referee = repository.get_referee(session, tournament.id, account_id)
    if referee is None:  # 剛新增或原本就存在，不會發生
        raise RuntimeError("tournament_referee row missing after insert")
    if created:
        audit.record(
            session,
            actor_id=account_id,
            tournament_id=tournament.id,
            action="referee.accepted",
            entity_type="tournament_referee",
            entity_id=account_id,
            before=None,
            after={
                "invitation_id": invitation.id,
                "accepted_at": referee.accepted_at,
            },
        )
    names = identity_service.get_display_names(session, account_ids=[account_id])
    return _referee_to_read(referee, names[account_id])


def is_referee(
    session: Session, *, tournament_id: uuid.UUID, account_id: uuid.UUID
) -> bool:
    """帳號已接受該賽事的裁判邀請；只在該賽事有效（由 `core.authz` 判斷）。

    以主鍵 (tournament_id, account_id) 只查一列，4.4 每次指派與登錄比分都會呼叫。
    """
    referee = repository.get_referee(session, tournament_id, account_id)
    referee_tournament_ids = [referee.tournament_id] if referee is not None else []
    return authz.is_tournament_referee(referee_tournament_ids, tournament_id)


def has_referee_role(session: Session, *, account_id: uuid.UUID) -> bool:
    """帳號是不是任一賽事的裁判（接受過邀請即是，不看賽事狀態）；身分切換器用。"""
    return repository.has_any_referee_row(session, account_id)


def list_referees(session: Session, *, tournament_id: uuid.UUID) -> list[RefereeRead]:
    """某賽事的裁判（含顯示名稱），依接受邀請的時間排序。"""
    referees = repository.list_referees(session, tournament_id)
    names = identity_service.get_display_names(
        session, account_ids=[referee.account_id for referee in referees]
    )
    return [
        _referee_to_read(referee, names[referee.account_id]) for referee in referees
    ]
