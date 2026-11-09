"""competition 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import logging
import secrets
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.core import audit, authz, clock, events
from app.core.errors import BusinessError
from app.modules.competition import bracket as bracket_rules
from app.modules.competition import checkin as checkin_rules
from app.modules.competition import (
    disqualification,
    progression,
    registration_port,
    repository,
    scoring,
)
from app.modules.competition import schedule as schedule_rules
from app.modules.competition.models import (
    Bracket,
    BracketDrawn,
    BracketRead,
    CheckIn,
    CheckInRead,
    CheckInStatus,
    CheckInStatusReason,
    CorrectionResult,
    DisqualifyResult,
    DrawStatus,
    DrawStatusReason,
    GameScoreIn,
    ManagedMatch,
    Match,
    MatchGame,
    MatchOpponentsDecided,
    MatchOutcome,
    MatchRead,
    MatchRescheduled,
    MatchResultConfirmed,
    MatchResultSubmitted,
    MatchStatus,
    NextMatch,
    PublicBracket,
    PublicGame,
    PublicMatch,
    PublicMatchDetail,
    PublicPodium,
    PublicTeamRef,
    PublicTournamentRef,
    RefereeAssigned,
    RefereeMatch,
    RefereeTournamentMatches,
    RefereeUnassigned,
    ReplayCleared,
    RescheduleBlockReason,
    RescheduleInfo,
    ScoreEntryReason,
    ScoreEntryState,
    SeriesRead,
    TeamCheckedIn,
)
from app.modules.identity import service as identity_service
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus

logger = logging.getLogger(__name__)

# 可以抽籤的賽事狀態：開放報名中（提前抽籤）、報名截止
_DRAWABLE = frozenset({TournamentStatus.OPEN, TournamentStatus.CLOSED})

# 賽事已結束或已取消：worker 不再自動確認（AD-7）
_ENDED = frozenset({TournamentStatus.FINISHED, TournamentStatus.CANCELLED})

# 公開單場只在這兩個狀態顯示申訴期截止時間
_APPEAL_STATUSES = frozenset({MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED})

# `confirm_match` 只接受已開打的場次；待開打直接確認只走輪空（`confirm_walkover`、`advance`）
_CONFIRMABLE = frozenset(
    {MatchStatus.LIVE, MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED}
)

# 場次狀態的合法轉換（PRD〈場次狀態〉）
_MATCH_TRANSITIONS: dict[MatchStatus, frozenset[MatchStatus]] = {
    MatchStatus.SCHEDULED: frozenset(
        {
            MatchStatus.LIVE,
            MatchStatus.APPEAL_WINDOW,
            MatchStatus.CONFIRMED,
            MatchStatus.VOIDED,
        }
    ),
    MatchStatus.LIVE: frozenset({MatchStatus.APPEAL_WINDOW, MatchStatus.CONFIRMED}),
    MatchStatus.APPEAL_WINDOW: frozenset({MatchStatus.APPEALED, MatchStatus.CONFIRMED}),
    MatchStatus.APPEALED: frozenset({MatchStatus.CONFIRMED, MatchStatus.SCHEDULED}),
    MatchStatus.CONFIRMED: frozenset(),
    MatchStatus.VOIDED: frozenset(),
}


def _match_not_found() -> BusinessError:
    return BusinessError("MATCH_NOT_FOUND", "找不到這個場次。", status_code=404)


def _source(
    match: Match,
    planned: bracket_rules.PlannedMatch,
    side: bracket_rules.Side,
    team_id: uuid.UUID | None,
    by_code: Mapping[str, Match],
) -> str | None:
    """待定列字串；該方已有隊伍、或確定不會有隊伍時為 None。

    確定不會有隊伍：已確認的 walkover 空缺方、已取消（voided）場次的空缺方，
    或來源場次已確認卻沒有送出隊伍（例如雙方棄權；確認時晉級已同步寫入）。
    `by_code` 是同一對戰表全部場次，用來查來源場次。
    """
    if team_id is not None:
        return None
    if match.status == MatchStatus.VOIDED:
        return None
    if match.status == MatchStatus.CONFIRMED and match.outcome == MatchOutcome.WALKOVER:
        return None
    src = planned.source(side)
    if src is None:
        return None
    feeder = by_code.get(src.code)
    if feeder is not None and feeder.status == MatchStatus.CONFIRMED:
        return None
    return bracket_rules.source_label(planned, side)


def _round_starts(
    session: Session, tournament: TournamentRead, rounds: int
) -> list[schedule_rules.RoundStart]:
    return schedule_rules.plan_round_starts(
        start_at=tournament.start_at,
        rounds=rounds,
        interval_minutes=tournament.round_interval_minutes,
        best_of=[
            tournaments_service.bo_for_round(
                session, tournament_id=tournament.id, round_no=r
            )
            for r in range(1, rounds + 1)
        ],
        forfeit_minutes=tournament.forfeit_minutes,
        game_minutes=tournament.game_minutes,
        appeal_minutes=tournament.appeal_minutes,
    )


def _delayed_rounds(starts: list[schedule_rules.RoundStart]) -> list[int]:
    return [start.round_no for start in starts if start.is_delayed]


def _states(matches: list[Match]) -> dict[str, progression.MatchState[uuid.UUID]]:
    """以場次資料組出 `progression` 用的狀態（以場次編號為鍵）。"""
    return {
        match.code: progression.MatchState(
            team_a=match.team_a_id,
            team_b=match.team_b_id,
            status=MatchStatus(match.status),
            outcome=MatchOutcome(match.outcome) if match.outcome is not None else None,
            winner=match.winner_id,
        )
        for match in matches
    }


def _finished_podium(
    session: Session,
    tournament_id: uuid.UUID,
    plan: bracket_rules.BracketPlan,
    matches: list[Match],
) -> progression.Podium[uuid.UUID] | None:
    """賽事已結束時的名次；未結束、或場次資料不自洽（記錄日誌）時回 None。"""
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    if tournament.status != TournamentStatus.FINISHED:
        return None
    try:
        return progression.podium(plan, _states(matches))
    except ValueError:
        # 公開頁面不因資料不自洽而 500；名次先不顯示，等人工修正
        logger.exception("Inconsistent bracket for tournament %s", tournament_id)
        return None


def _public_podium(
    result: progression.Podium[uuid.UUID] | None,
    team_ref: Callable[[uuid.UUID | None], PublicTeamRef | None],
) -> PublicPodium | None:
    if result is None:
        return None
    return PublicPodium(
        champion=team_ref(result.champion),
        runner_up=team_ref(result.runner_up),
        third_place=team_ref(result.third_place),
    )


def _match_to_read(match: Match) -> MatchRead:
    return MatchRead.model_validate(match, from_attributes=True)


def _bracket_to_read(
    bracket: Bracket, matches: list[Match], delayed_rounds: list[int]
) -> BracketRead:
    return BracketRead(
        id=bracket.id,
        tournament_id=bracket.tournament_id,
        size=bracket.size,
        rounds=bracket.rounds,
        drawn_at=bracket.drawn_at,
        delayed_rounds=delayed_rounds,
        matches=[_match_to_read(match) for match in matches],
    )


# ---------------------------------------------------------------- 抽籤

# 抽籤至少要有的正取隊數
_MIN_DRAW_TEAMS = 2

# 不能抽籤的原因 → 抽籤 API 的錯誤碼與訊息（狀態 API 的小寫代碼與錯誤碼一一對應）
_DRAW_ERRORS: dict[DrawStatusReason, tuple[str, str]] = {
    "already_drawn": ("BRACKET_ALREADY_DRAWN", "這場賽事已經抽過籤了。"),
    "not_drawable": ("TOURNAMENT_NOT_DRAWABLE", "賽事目前的狀態不能抽籤。"),
    "start_passed": ("TOURNAMENT_START_PASSED", "開賽時間已過，無法抽籤"),
    "not_enough_teams": ("NOT_ENOUGH_TEAMS", "正取不足 2 隊，無法抽籤"),
}


def _draw_error(reason: DrawStatusReason) -> BusinessError:
    code, message = _DRAW_ERRORS[reason]
    return BusinessError(code, message, status_code=409)


def _draw_blocked(
    session: Session, tournament: TournamentRead
) -> DrawStatusReason | None:
    """抽籤在分配正取之前的檢查（依序）；呼叫端已鎖住賽事並確認是主辦方。"""
    if repository.get_bracket_by_tournament(session, tournament.id) is not None:
        return "already_drawn"
    if tournament.status not in _DRAWABLE:
        return "not_drawable"
    if tournament.start_at <= clock.now():
        return "start_passed"
    return None


class _PreviewRollback(Exception):
    """預估抽籤時拋出，讓 savepoint 回滾分配結果；帶出預估的正取隊數。"""

    def __init__(self, expected_teams: int) -> None:
        super().__init__(expected_teams)
        self.expected_teams = expected_teams


def _expected_teams(
    session: Session, *, tournament: TournamentRead, actor_id: uuid.UUID
) -> int:
    """抽籤當下會有幾隊正取。

    開放報名中與 `draw` 一樣先呼叫 `finalize_for_draw`，但在 savepoint 裡執行，
    數完隊伍就拋例外讓 savepoint 回滾：報名狀態、結算紀錄、操作紀錄與 outbox
    事件都不會留下（AD-5：service 不呼叫 rollback，由 savepoint 自己回滾）。
    """
    if tournament.status != TournamentStatus.OPEN:
        return len(
            registration_port.list_accepted_teams(session, tournament_id=tournament.id)
        )
    try:
        with session.begin_nested():
            registration_port.finalize_for_draw(
                session, tournament_id=tournament.id, actor_id=actor_id
            )
            raise _PreviewRollback(
                len(
                    registration_port.list_accepted_teams(
                        session, tournament_id=tournament.id
                    )
                )
            )
    except _PreviewRollback as preview:
        return preview.expected_teams


def get_draw_status(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> DrawStatus:
    """S27 抽籤按鈕：與 `draw` 相同的檢查順序與分配規則預估能不能抽籤，不寫入任何資料。

    先不鎖讀賽事擋掉非主辦方（不讓無權限者排隊等鎖），再鎖住賽事（AD-6）
    取得最新值，與同時進行的抽籤、優先期結算串行。
    """
    authz.ensure_tournament_owner(
        tournaments_service.get_tournament(session, tournament_id=tournament_id),
        actor_id,
    )
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    blocked = _draw_blocked(session, tournament)
    if blocked is not None:
        return DrawStatus(can_draw=False, reason=blocked, expected_teams=None)
    expected = _expected_teams(session, tournament=tournament, actor_id=actor_id)
    if expected < _MIN_DRAW_TEAMS:
        return DrawStatus(
            can_draw=False, reason="not_enough_teams", expected_teams=expected
        )
    return DrawStatus(can_draw=True, reason=None, expected_teams=expected)


def draw(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    actor_id: uuid.UUID,
    rng: bracket_rules.Shuffler | None = None,
) -> BracketRead:
    """抽籤：產生對戰表與全部場次、排定時間、設定棄權期限，賽事轉為已公布。

    全部在呼叫端的同一個交易裡完成；任何一步拋錯時呼叫端不 commit，
    什麼都不會寫入。`rng` 只供測試與示範資料注入，正式環境用 `secrets.SystemRandom()`。
    """
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    blocked = _draw_blocked(session, tournament)
    if blocked is not None:
        raise _draw_error(blocked)
    if tournament.status == TournamentStatus.OPEN:
        registration_port.finalize_for_draw(
            session, tournament_id=tournament_id, actor_id=actor_id
        )
    team_ids = registration_port.list_accepted_teams(
        session, tournament_id=tournament_id
    )
    if len(team_ids) < _MIN_DRAW_TEAMS:
        raise _draw_error("not_enough_teams")

    # 洗牌前先依隊名（相同再比 id）排序：結果只取決於亂數，不受 registration
    # 回傳順序影響，示範資料用固定種子時每次都得到同一張對戰表
    names = registration_port.get_team_names(session, team_ids=team_ids)
    team_ids = sorted(team_ids, key=lambda team: (names.get(team, ""), str(team)))

    plan = bracket_rules.plan(len(team_ids))
    assigned = bracket_rules.assign(
        team_ids, plan, rng if rng is not None else secrets.SystemRandom()
    )
    starts = _round_starts(session, tournament, plan.rounds)
    start_of_round = {start.round_no: start.start_at for start in starts}
    now = clock.now()

    bracket = Bracket(
        tournament_id=tournament_id,
        size=plan.size,
        rounds=plan.rounds,
        team_count=len(team_ids),
        drawn_at=now,
    )
    ids = {item.match.code: uuid.uuid4() for item in assigned}
    rows = [
        Match(
            id=ids[item.match.code],
            bracket_id=bracket.id,
            tournament_id=tournament_id,
            round_no=item.match.round_no,
            slot_no=item.match.slot_no,
            is_third_place=item.match.is_third_place,
            code=item.match.code,
            team_a_id=item.team_a_id,
            team_b_id=item.team_b_id,
            bye_a=item.match.bye_a,
            bye_b=item.match.bye_b,
            scheduled_at=start_of_round[item.match.round_no],
            status=MatchStatus.SCHEDULED,
            next_match_id=ids[item.match.next_code] if item.match.next_code else None,
            loser_next_match_id=(
                ids[item.match.loser_next_code] if item.match.loser_next_code else None
            ),
            updated_at=now,
        )
        for item in assigned
    ]
    # 被指向的場次（後面的輪次、季軍賽）先寫入，滿足自我參照外鍵
    repository.add_bracket(session, bracket, list(reversed(rows)))

    for row in rows:
        if row.team_a_id is not None and row.team_b_id is not None:
            start_forfeit_clock(session, match=row)

    registration_port.mark_drawn(
        session, tournament_id=tournament_id, team_ids=team_ids, actor_id=actor_id
    )
    tournaments_service.transition_tournament(
        session,
        tournament_id=tournament_id,
        to=TournamentStatus.PUBLISHED,
        actor_id=actor_id,
    )
    delayed = _delayed_rounds(starts)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=tournament_id,
        action="bracket.drawn",
        entity_type="bracket",
        entity_id=bracket.id,
        before=None,
        after={
            "size": plan.size,
            "rounds": plan.rounds,
            "team_count": len(team_ids),
            "delayed_rounds": delayed,
        },
    )
    events.publish(
        session, BracketDrawn(tournament_id=tournament_id, bracket_id=bracket.id)
    )
    matches = repository.list_matches(session, bracket.id)
    return _bracket_to_read(bracket, matches, delayed)


# ---------------------------------------------------------------- 查詢


def get_bracket(session: Session, *, tournament_id: uuid.UUID) -> BracketRead | None:
    """對戰表與全部場次；尚未抽籤回 None。"""
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        return None
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    delayed = _delayed_rounds(_round_starts(session, tournament, bracket.rounds))
    return _bracket_to_read(
        bracket, repository.list_matches(session, bracket.id), delayed
    )


def _public_matches(
    session: Session, bracket: Bracket, matches: list[Match]
) -> tuple[list[PublicMatch], Callable[[uuid.UUID | None], PublicTeamRef | None]]:
    """組 `PublicMatch`（公開對戰樹與公開單場共用）；一併回傳查隊名的 `team_ref`。"""
    plan = bracket_rules.plan(bracket.team_count)
    # 待定列要看來源場次；呼叫端可能只給部分場次，所以另外讀整張對戰表
    by_code = {m.code: m for m in repository.list_matches(session, bracket.id)}
    team_ids = sorted(
        {
            team_id
            for match in matches
            for team_id in (match.team_a_id, match.team_b_id)
            if team_id is not None
        }
    )
    names = registration_port.get_team_names(session, team_ids=team_ids)

    def team_ref(team_id: uuid.UUID | None) -> PublicTeamRef | None:
        if team_id is None:
            return None
        return PublicTeamRef(id=team_id, name=names.get(team_id, "未知隊伍"))

    public_matches = []
    for match in matches:
        planned = plan.match(match.code)
        public_matches.append(
            PublicMatch(
                id=match.id,
                code=match.code,
                round_no=match.round_no,
                slot_no=match.slot_no,
                is_third_place=match.is_third_place,
                team_a=team_ref(match.team_a_id),
                team_b=team_ref(match.team_b_id),
                source_a=_source(match, planned, "a", match.team_a_id, by_code),
                source_b=_source(match, planned, "b", match.team_b_id, by_code),
                bye_a=match.bye_a,
                bye_b=match.bye_b,
                scheduled_at=match.scheduled_at,
                status=match.status,
                outcome=match.outcome,
                winner_id=match.winner_id,
                wins_a=match.wins_a,
                wins_b=match.wins_b,
            )
        )
    return public_matches, team_ref


def get_public_bracket(
    session: Session, *, tournament_id: uuid.UUID
) -> PublicBracket | None:
    """公開對戰樹（AD-19）：隊伍只有 `{id, name}`；尚未抽籤回 None。"""
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        return None
    matches = repository.list_matches(session, bracket.id)
    plan = bracket_rules.plan(bracket.team_count)
    public_matches, team_ref = _public_matches(session, bracket, matches)
    updated_at: datetime = max(
        [bracket.drawn_at, *(match.updated_at for match in matches)]
    )
    return PublicBracket(
        tournament_id=tournament_id,
        rounds=bracket.rounds,
        round_names=[
            bracket_rules.round_name(r, bracket.rounds)
            for r in range(1, bracket.rounds + 1)
        ],
        matches=public_matches,
        podium=_public_podium(
            _finished_podium(session, tournament_id, plan, matches), team_ref
        ),
        updated_at=updated_at,
    )


def get_public_match(
    session: Session, *, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> PublicMatchDetail:
    """公開單場（AD-19）。

    賽事不存在、尚未抽籤、場次不存在、場次不屬於這個賽事，一律拋 404 `MATCH_NOT_FOUND`。
    """
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        raise _match_not_found()
    match = repository.get_match(session, match_id)
    if match is None or match.bracket_id != bracket.id:
        raise _match_not_found()
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    # list_matches 已依 slot_no 排序、季軍賽在最後
    round_matches = [
        m
        for m in repository.list_matches(session, bracket.id)
        if m.round_no == match.round_no
    ]
    public_round, _team_ref = _public_matches(session, bracket, round_matches)
    this = next(m for m in public_round if m.id == match.id)
    same_round = [m for m in public_round if m.id != match.id]
    check_in_at = {
        c.team_id: c.at for c in repository.list_check_ins(session, match.id)
    }
    # 送出結果與判棄權都把截止設為「當下＋申訴時限」，賽事建立後時限不能修改，
    # 所以開始時間由截止往回推即可，不必另存欄位
    appeal_deadline = (
        match.appeal_deadline if match.status in _APPEAL_STATUSES else None
    )
    appeal_started_at = (
        appeal_deadline - timedelta(minutes=tournament.appeal_minutes)
        if appeal_deadline is not None
        else None
    )
    return PublicMatchDetail(
        **this.model_dump(),
        tournament=PublicTournamentRef(id=tournament.id, name=tournament.name),
        game_name=tournament.game_name,
        best_of=tournaments_service.bo_for_round(
            session, tournament_id=tournament_id, round_no=match.round_no
        ),
        score_type=tournament.score_type,
        round_name="季軍賽"
        if match.is_third_place
        else bracket_rules.round_name(match.round_no, bracket.rounds),
        games=[_public_game(game) for game in repository.list_games(session, match.id)],
        same_round=same_round,
        appeal_deadline=appeal_deadline,
        appeal_started_at=appeal_started_at,
        updated_at=max(m.updated_at for m in round_matches),
        check_in_a_at=check_in_at.get(match.team_a_id) if match.team_a_id else None,
        check_in_b_at=check_in_at.get(match.team_b_id) if match.team_b_id else None,
        # 報到截止只對兩隊都確定的待開打場次有意義；其他情況的值可能已過期，不給前端以免顯示倒數
        forfeit_deadline=(
            match.forfeit_deadline
            if match.status == MatchStatus.SCHEDULED
            and match.team_a_id is not None
            and match.team_b_id is not None
            else None
        ),
    )


def get_podium(session: Session, *, tournament_id: uuid.UUID) -> PublicPodium | None:
    """名次（冠、亞、季，從缺為 None）；尚未抽籤或賽事不是已結束時回 None。

    名次取自 `progression.podium`：決賽已確認，且季軍賽已確認、已取消或不存在。
    """
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        return None
    matches = repository.list_matches(session, bracket.id)
    result = _finished_podium(
        session, tournament_id, bracket_rules.plan(bracket.team_count), matches
    )
    if result is None:
        return None
    team_ids = sorted(
        {
            team_id
            for team_id in (result.champion, result.runner_up, result.third_place)
            if team_id is not None
        }
    )
    names = registration_port.get_team_names(session, team_ids=team_ids)

    def team_ref(team_id: uuid.UUID | None) -> PublicTeamRef | None:
        if team_id is None:
            return None
        return PublicTeamRef(id=team_id, name=names.get(team_id, "未知隊伍"))

    return _public_podium(result, team_ref)


def get_match(session: Session, *, match_id: uuid.UUID) -> MatchRead:
    """單一場次；不存在拋 404 `MATCH_NOT_FOUND`。"""
    match = repository.get_match(session, match_id)
    if match is None:
        raise _match_not_found()
    return _match_to_read(match)


def list_team_matches(
    session: Session, *, tournament_id: uuid.UUID, team_id: uuid.UUID
) -> list[MatchRead]:
    """某隊在某賽事的場次，依輪次排序。"""
    return [
        _match_to_read(match)
        for match in repository.list_team_matches(session, tournament_id, team_id)
    ]


# ---------------------------------------------------------------- 場次狀態


def lock_match(session: Session, *, match_id: uuid.UUID) -> Match:
    """`SELECT … FOR UPDATE` 鎖住場次並回傳最新值；不存在拋 404 `MATCH_NOT_FOUND`。

    同時需要賽事鎖時先 `lock_tournament`；要鎖多個場次時依 id 遞增逐一呼叫（AD-6）。
    """
    match = repository.get_match(session, match_id, for_update=True)
    if match is None:
        raise _match_not_found()
    return match


def transition_match(session: Session, *, match: Match, to: MatchStatus) -> None:
    """改變場次狀態的唯一入口；不允許的轉換拋 409 `MATCH_INVALID_TRANSITION`。

    操作紀錄由呼叫端（確認結果、申訴等）依情境寫入。
    """
    current = MatchStatus(match.status)
    if to not in _MATCH_TRANSITIONS[current]:
        raise BusinessError(
            "MATCH_INVALID_TRANSITION",
            "場次目前的狀態不能進行這個操作。",
            status_code=409,
        )
    repository.set_match_status(session, match, to, clock.now())


def start_forfeit_clock(session: Session, *, match: Match) -> None:
    """設定棄權期限的唯一入口：max(預定時間, 現在)＋賽事的棄權時限。

    只給兩隊都確定的場次；否則拋 409 `MATCH_TEAMS_NOT_SET`。
    """
    if match.team_a_id is None or match.team_b_id is None:
        raise BusinessError(
            "MATCH_TEAMS_NOT_SET",
            "場次的兩隊還沒確定，不能開始計算棄權期限。",
            status_code=409,
        )
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    now = clock.now()
    deadline = schedule_rules.forfeit_deadline(
        scheduled_at=match.scheduled_at,
        both_known_at=now,
        forfeit_minutes=tournament.forfeit_minutes,
    )
    repository.set_forfeit_deadline(session, match, deadline, now)


def clear_for_replay(session: Session, *, match: Match) -> ReplayCleared:
    """重新比賽前清除該場的報到紀錄、逐局比分與結果欄位（6.2，B 的 `replay_match` 呼叫）。

    呼叫端先 `lock_tournament`（AD-6）；這裡再 `lock_match` 取最新值，以鎖住後的
    狀態判斷，只接受申訴中，其他狀態拋 409 `MATCH_INVALID_TRANSITION`、不改資料。
    不轉換狀態、不改 `scheduled_at`（棄權期限等欄位會歸零），也不寫操作紀錄或事件，
    由 `replay_match` 依情境一次寫入。整個重賽流程（清除、`transition_match`、
    新 `scheduled_at`、`start_forfeit_clock`、操作紀錄與事件）必須在同一個交易內。
    回傳清除前的內容。
    """
    match = lock_match(session, match_id=match.id)
    if MatchStatus(match.status) != MatchStatus.APPEALED:
        raise BusinessError(
            "MATCH_INVALID_TRANSITION",
            "場次目前的狀態不能進行這個操作。",
            status_code=409,
        )
    cleared = ReplayCleared(
        check_ins=list_check_ins(session, match_id=match.id),
        games=[_public_game(g) for g in repository.list_games(session, match.id)],
        outcome=MatchOutcome(match.outcome) if match.outcome is not None else None,
        winner_id=match.winner_id,
        wins_a=match.wins_a,
        wins_b=match.wins_b,
        submitted_by=match.submitted_by,
        submitted_at=match.submitted_at,
        appeal_deadline=match.appeal_deadline,
        confirmed_at=match.confirmed_at,
        forfeit_deadline=match.forfeit_deadline,
    )
    repository.clear_for_replay(session, match, clock.now())
    return cleared


# ---------------------------------------------------------------- 確認結果與晉級


def _confirm(
    session: Session,
    *,
    match: Match,
    outcome: MatchOutcome,
    winner_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
) -> None:
    """轉為已確認、寫入結果與 `confirmed_at`、操作紀錄與事件；不推進。

    先檢查轉換：不允許時拋 409 `MATCH_INVALID_TRANSITION`，不改任何資料。
    """
    before = MatchStatus(match.status)
    transition_match(session, match=match, to=MatchStatus.CONFIRMED)
    repository.set_match_result(
        session,
        match,
        outcome=outcome,
        winner_id=winner_id,
        confirmed_at=clock.now(),
    )
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action="match.confirmed",
        entity_type="match",
        entity_id=match.id,
        before={"status": before.value},
        after={
            "status": MatchStatus.CONFIRMED.value,
            "outcome": outcome.value,
            "winner_id": winner_id,
        },
    )
    events.publish(
        session, MatchResultConfirmed(match_id=match.id, winner_id=winner_id)
    )


def confirm_match(
    session: Session,
    *,
    match: Match,
    outcome: MatchOutcome,
    winner_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
) -> None:
    """寫入結果、轉為已確認、寫 `confirmed_at`，接著呼叫 `advance`。

    呼叫端要先 `lock_tournament`、再以 `lock_match` 取得 `match`（AD-6）；這裡在寫入前
    也會鎖一次賽事（同一交易內不會等待）。`actor_id=None` 表示系統。只接受進行中、
    申訴期、申訴中的場次；待開打、已確認、已取消拋 409 `MATCH_INVALID_TRANSITION`，
    不改任何資料。全部在呼叫端的交易內完成。
    """
    tournaments_service.lock_tournament(session, tournament_id=match.tournament_id)
    if MatchStatus(match.status) not in _CONFIRMABLE:
        raise BusinessError(
            "MATCH_INVALID_TRANSITION",
            "場次目前的狀態不能進行這個操作。",
            status_code=409,
        )
    _confirm(
        session, match=match, outcome=outcome, winner_id=winner_id, actor_id=actor_id
    )
    advance(session, match=match)


def confirm_walkover(session: Session, *, match: Match) -> None:
    """一方確定不會有隊伍時以 `walkover` 確認並推進（操作者為系統）。

    呼叫端要先 `lock_tournament`、再以 `lock_match` 取得 `match`（AD-6）；這裡在寫入前
    也會鎖一次賽事。勝隊為場上唯一的隊伍；兩方都沒有隊伍時無勝隊。兩隊都在時拋 409
    `MATCH_INVALID_TRANSITION`，不改任何資料。
    """
    tournaments_service.lock_tournament(session, tournament_id=match.tournament_id)
    if match.team_a_id is not None and match.team_b_id is not None:
        raise BusinessError(
            "MATCH_INVALID_TRANSITION",
            "場次目前的狀態不能進行這個操作。",
            status_code=409,
        )
    winner_id = match.team_a_id if match.team_a_id is not None else match.team_b_id
    _confirm(
        session,
        match=match,
        outcome=MatchOutcome.WALKOVER,
        winner_id=winner_id,
        actor_id=None,
    )
    advance(session, match=match)


def advance(session: Session, *, match: Match) -> None:
    """`match`（已確認）之後的晉級：依 `progression.advance` 的變更依序寫入。

    鎖的順序（AD-6）：先鎖賽事，再依 id 遞增鎖住這個對戰表的全部場次，以鎖住後的
    最新值組狀態（呼叫前對場次的修改必須已 flush）。連鎖的輪空確認、季軍賽取消、
    起算棄權期限與賽事結束都在呼叫端的同一個交易內完成；這些後續變更的操作者為系統。
    重複呼叫不會重複填位或起算；賽事已結束時不再轉換狀態或寫名次。
    `match` 尚未確認時 `progression` 拋 `ValueError`（呼叫端的程式錯誤）。
    """
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=match.tournament_id
    )
    matches = repository.lock_bracket_matches(session, match.bracket_id)
    bracket = repository.get_bracket(session, match.bracket_id)
    assert bracket is not None  # 場次的外鍵保證對戰表存在
    plan = bracket_rules.plan(bracket.team_count)
    by_code = {row.code: row for row in matches}
    changes = progression.advance(plan, _states(matches), match.code)
    for change in changes:
        match change:
            case progression.FillSlot(code=code, side=side, team=team):
                repository.set_match_team(
                    session, by_code[code], side, team, clock.now()
                )
                _unassign_if_member(session, match=by_code[code], team_id=team)
            case progression.ConfirmWalkover(code=code, winner=winner):
                _confirm(
                    session,
                    match=by_code[code],
                    outcome=MatchOutcome.WALKOVER,
                    winner_id=winner,
                    actor_id=None,
                )
            case progression.VoidMatch(code=code):
                _void(session, match=by_code[code])
            case progression.StartForfeitClock(code=code):
                target = by_code[code]
                start_forfeit_clock(session, match=target)
                events.publish(session, MatchOpponentsDecided(match_id=target.id))
            case progression.TournamentFinished(podium=result):
                _finish(session, tournament=tournament, result=result)


def _unassign_if_member(
    session: Session, *, match: Match, team_id: uuid.UUID | None
) -> None:
    """晉級填位後，指派的裁判若是新填入隊伍的隊員就自動收回（操作者為系統）。"""
    referee_id = match.referee_account_id
    if team_id is None or referee_id is None:
        return
    if not registration_port.is_member(session, team_id=team_id, account_id=referee_id):
        return
    _set_referee(session, match=match, referee_id=None, actor_id=None)
    events.publish(
        session, RefereeUnassigned(match_id=match.id, referee_account_id=referee_id)
    )


def _set_referee(
    session: Session,
    *,
    match: Match,
    referee_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
) -> None:
    """寫入裁判並記操作紀錄（`match.referee_assigned`／`match.referee_unassigned`）。"""
    before = match.referee_account_id
    repository.set_referee(session, match, referee_id, clock.now())
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action=(
            "match.referee_assigned"
            if referee_id is not None
            else "match.referee_unassigned"
        ),
        entity_type="match",
        entity_id=match.id,
        before={"referee_account_id": before},
        after={"referee_account_id": referee_id},
    )


def _void(session: Session, *, match: Match) -> None:
    """季軍賽轉為已取消（FR-21）；已排入的隊伍留在原位。"""
    before = MatchStatus(match.status)
    transition_match(session, match=match, to=MatchStatus.VOIDED)
    repository.clear_match_result(session, match, clock.now())
    audit.record(
        session,
        actor_id=None,
        tournament_id=match.tournament_id,
        action="match.voided",
        entity_type="match",
        entity_id=match.id,
        before={"status": before.value},
        after={"status": MatchStatus.VOIDED.value},
    )


def _finish(
    session: Session,
    *,
    tournament: TournamentRead,
    result: progression.Podium[uuid.UUID],
) -> None:
    """賽事轉為已結束並記錄名次。

    只處理已公布、進行中的賽事；已結束（progression 可能重複回傳）或已取消時不做任何事。
    """
    if tournament.status not in (TournamentStatus.PUBLISHED, TournamentStatus.ONGOING):
        return
    if tournament.status == TournamentStatus.PUBLISHED:
        tournaments_service.transition_tournament(
            session,
            tournament_id=tournament.id,
            to=TournamentStatus.ONGOING,
            actor_id=None,
        )
    tournaments_service.transition_tournament(
        session,
        tournament_id=tournament.id,
        to=TournamentStatus.FINISHED,
        actor_id=None,
    )
    audit.record(
        session,
        actor_id=None,
        tournament_id=tournament.id,
        action="tournament.podium",
        entity_type="tournament",
        entity_id=tournament.id,
        before=None,
        after={
            "champion": result.champion,
            "runner_up": result.runner_up,
            "third_place": result.third_place,
        },
    )


def auto_confirm_expired(session: Session) -> bool:
    """worker 用：確認一場申訴期滿（申訴期、`appeal_deadline <= now`）的場次並推進。

    沿用場次上已寫入的 `outcome`、`winner_id`，操作者為系統。先找候選，略過已結束或
    已取消賽事的場次（AD-7）；鎖住賽事與場次後重新檢查，已被處理過就不做任何事。
    回傳是否找到候選（找到就可能還有下一筆）。

    結果資料不自洽（例如完賽卻沒有勝隊，`progression` 拋 ValueError）的場次，退回
    savepoint、記錄日誌後排除，改處理下一場；否則它每一輪都會排在最前面、rollback，
    讓所有賽事後面的場次都無法確認。
    """
    now = clock.now()
    ended_tournaments: set[uuid.UUID] = set()
    broken_matches: set[uuid.UUID] = set()
    while True:
        match_id = repository.find_expired_appeal_id(
            session,
            now,
            exclude_tournaments=ended_tournaments,
            exclude_matches=broken_matches,
        )
        if match_id is None:
            return False
        candidate = repository.get_match(session, match_id)
        assert candidate is not None  # 剛查到的 id
        status = tournaments_service.get_tournament(
            session, tournament_id=candidate.tournament_id
        ).status
        if status in _ENDED:
            ended_tournaments.add(candidate.tournament_id)
            continue

        tournament = tournaments_service.lock_tournament(
            session, tournament_id=candidate.tournament_id
        )
        match = lock_match(session, match_id=match_id)
        if (
            tournament.status in _ENDED
            or match.status != MatchStatus.APPEAL_WINDOW
            or match.appeal_deadline is None
            or match.appeal_deadline > now
            or match.outcome is None
        ):
            return True
        try:
            with session.begin_nested():
                confirm_match(
                    session,
                    match=match,
                    outcome=MatchOutcome(match.outcome),
                    winner_id=match.winner_id,
                    actor_id=None,
                )
        except ValueError:
            logger.exception(
                "Match %s has an inconsistent result; auto-confirm skipped", match_id
            )
            broken_matches.add(match_id)
            continue
        return True


# ---------------------------------------------------------------- 報到（Story 5.1）

# 報到可以進行的賽事狀態
_CHECKABLE_TOURNAMENT = frozenset(
    {TournamentStatus.PUBLISHED, TournamentStatus.ONGOING}
)

# 狀態查詢的原因代碼（`CheckInPanel` 用）對應報到 API 的錯誤碼、狀態碼與訊息；
# `too_early` 的訊息含開放時間，另外組
_REJECTIONS: dict[str, tuple[str, int, str]] = {
    "not_checkable": ("MATCH_NOT_CHECKABLE", 409, "這場比賽現在不能報到。"),
    "teams_pending": ("MATCH_TEAMS_PENDING", 409, "對手還沒確定，暫時不能報到。"),
    "not_captain": ("CAPTAIN_REQUIRED", 403, "只有這場比賽兩隊的隊長可以報到。"),
    "already_checked_in": ("ALREADY_CHECKED_IN", 409, "你的隊伍已經報到了。"),
    "closed": ("CHECK_IN_CLOSED", 409, "報到已截止。"),
}

_TAIPEI = ZoneInfo("Asia/Taipei")
_WEEKDAYS = "一二三四五六日"


def _taipei_text(at: datetime) -> str:
    """絕對時間 `10/18（六）19:00`（台北時間，不標時區）；跨年才加年份。"""
    local = at.astimezone(_TAIPEI)
    this_year = clock.now().astimezone(_TAIPEI).year
    year = f"{local.year}/" if local.year != this_year else ""
    weekday = _WEEKDAYS[local.weekday()]
    return f"{year}{local.month}/{local.day}（{weekday}）{local:%H:%M}"


def _rejection(reason: str, scheduled_at: datetime) -> BusinessError:
    """原因代碼轉成報到 API 的 `BusinessError`；未知的原因一律當作 `not_checkable`。"""
    if reason == "too_early":
        opens_at = checkin_rules.check_in_opens_at(scheduled_at)
        return BusinessError(
            "CHECK_IN_NOT_OPEN",
            f"{_taipei_text(opens_at)} 起可報到。",
            status_code=409,
        )
    code, status_code, message = _REJECTIONS.get(reason, _REJECTIONS["not_checkable"])
    return BusinessError(code, message, status_code=status_code)


def _evaluate_check_in(
    session: Session, *, match: Match, account_id: uuid.UUID
) -> tuple[Literal["a", "b"] | None, uuid.UUID | None, CheckInStatusReason | None]:
    """報到與狀態查詢共用的檢查（呼叫端已視需要鎖住場次）。

    回傳（登入者所屬的一方、該隊 id、不能報到的原因代碼；可以報到時為 None）。
    兩隊都確定就先算出隊長身分，即使場次不可報到也回傳 side。
    原因順序：賽事與場次狀態、兩隊確定、隊長身分，其餘交給 `checkin.check_check_in`。
    """
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    side: Literal["a", "b"] | None = None
    team_id: uuid.UUID | None = None
    team_a, team_b = match.team_a_id, match.team_b_id
    if team_a is not None and team_b is not None:
        if registration_port.is_captain(session, team_id=team_a, account_id=account_id):
            side, team_id = "a", team_a
        elif registration_port.is_captain(
            session, team_id=team_b, account_id=account_id
        ):
            side, team_id = "b", team_b
    if (
        tournament.status not in _CHECKABLE_TOURNAMENT
        or match.status != MatchStatus.SCHEDULED
    ):
        return side, team_id, "not_checkable"
    if team_a is None or team_b is None:
        return None, None, "teams_pending"
    if team_id is None:
        return None, None, "not_captain"
    already = any(
        c.team_id == team_id for c in repository.list_check_ins(session, match.id)
    )
    try:
        reason = checkin_rules.check_check_in(
            now=clock.now(),
            scheduled_at=match.scheduled_at,
            teams_known=True,
            already_checked_in=already,
            forfeit_deadline=match.forfeit_deadline,
        )
    except ValueError:
        # 兩隊已確定卻沒有棄權期限、或期限不晚於開放時間：資料不一致，視為不能報到
        logger.warning("match %s has an unusable forfeit_deadline", match.id)
        return side, team_id, "not_checkable"
    if reason is None:
        return side, team_id, None
    if reason in ("already_checked_in", "too_early", "closed"):
        return side, team_id, reason
    return side, team_id, "not_checkable"  # teams_pending 在這裡不可能出現


def _match_in_tournament(
    session: Session, *, tournament_id: uuid.UUID, match_id: uuid.UUID
) -> Match:
    """場次不存在或不屬於該賽事拋 404 `MATCH_NOT_FOUND`。"""
    match = repository.get_match(session, match_id)
    if match is None or match.tournament_id != tournament_id:
        raise _match_not_found()
    return match


def check_in(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> CheckInRead:
    """隊長為本隊報到；隊伍由登入者是哪一隊的隊長推得。

    先鎖場次再檢查（AD-6）；任何拒絕都不寫報到紀錄與操作紀錄。
    """
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    match = lock_match(session, match_id=match_id)
    _side, team_id, reason = _evaluate_check_in(
        session, match=match, account_id=account_id
    )
    if reason is not None:
        raise _rejection(reason, match.scheduled_at)
    assert team_id is not None  # 沒有拒絕原因代表已確認是隊長
    now = clock.now()
    inserted = repository.add_check_in(
        session,
        CheckIn(match_id=match.id, team_id=team_id, account_id=account_id, at=now),
    )
    if not inserted:  # 唯一鍵是最後防線：重複報到不能變成 500
        raise _rejection("already_checked_in", match.scheduled_at)
    # 公開單場的 updated_at 取自場次，報到不更新它，前端就不會重抓（#47）
    repository.touch_match(session, match, now)
    both = len(repository.list_check_ins(session, match.id)) >= 2
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=match.tournament_id,
        action="match.checked_in",
        entity_type="match",
        entity_id=match.id,
        before=None,
        after={"team_id": team_id, "at": now, "both_checked_in": both},
    )
    events.publish(
        session,
        TeamCheckedIn(match_id=match.id, team_id=team_id, both_checked_in=both),
    )
    return CheckInRead(match_id=match.id, team_id=team_id, at=now)


def get_check_in_status(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> CheckInStatus:
    """登入者對這場的報到狀態；`reason` 為 None 若且唯若現在報到會成功。"""
    match = _match_in_tournament(
        session, tournament_id=tournament_id, match_id=match_id
    )
    side, _team_id, reason = _evaluate_check_in(
        session, match=match, account_id=account_id
    )
    return CheckInStatus(
        side=side,
        reason=reason,
        opens_at=checkin_rules.check_in_opens_at(match.scheduled_at),
    )


def list_check_ins(session: Session, *, match_id: uuid.UUID) -> list[CheckInRead]:
    """某場次的報到紀錄，依報到時間排序（5.2 判棄權用）。"""
    return [
        CheckInRead(match_id=c.match_id, team_id=c.team_id, at=c.at)
        for c in repository.list_check_ins(session, match_id)
    ]


def list_forfeit_due(session: Session, *, now: datetime) -> list[uuid.UUID]:
    """待開打、棄權期限已到（`forfeit_deadline <= now`）、且不是兩隊都已報到的場次 id。

    已取消賽事的場次不列入：賽事取消後場次停在待開打，不排除的話 5.2 的 worker
    每一輪都會把它們鎖住再略過。這裡不加鎖，工作鎖住賽事後仍會重新判斷。
    """
    due = repository.find_forfeit_due(session, now)
    cancelled = {
        tournament_id
        for tournament_id in {tournament_id for _, tournament_id in due}
        if tournaments_service.get_tournament(
            session, tournament_id=tournament_id
        ).status
        == TournamentStatus.CANCELLED
    }
    return [
        match_id for match_id, tournament_id in due if tournament_id not in cancelled
    ]


def start_due_tournament(session: Session) -> bool:
    """worker 用：把一場賽程已公布、最早場次報到開放時間已到的賽事轉為進行中。

    先找候選對戰表，鎖賽事後重新檢查；賽事不是賽程已公布（已進行、已取消、已結束）
    就只標記為已處理、不做其他事。重複執行沒有副作用。回傳 True 代表處理了一個對戰表
    （轉為進行中或標記略過），worker 會再呼叫一次；沒有候選回傳 False。

    鎖住後發現還沒到開始時間（期間被改期），或處理時拋錯，就略過這個對戰表、改看下一個
    候選：拋錯的那個在 savepoint 裡回滾並記錄錯誤，不會讓後面已到時間的賽事一直卡住。
    """
    now = clock.now()
    skipped: set[uuid.UUID] = set()
    while True:
        bracket_id = repository.find_unstarted_bracket_id(
            session, now + checkin_rules.CHECK_IN_LEAD, exclude=skipped
        )
        if bracket_id is None:
            return False
        try:
            with session.begin_nested():
                handled = _start_bracket(session, bracket_id, now)
        except Exception:
            logger.exception("Bracket %s failed to start; skipped", bracket_id)
            handled = False
        if handled:
            return True
        skipped.add(bracket_id)


def _start_bracket(session: Session, bracket_id: uuid.UUID, now: datetime) -> bool:
    """鎖賽事後處理一個候選對戰表；鎖住前被改期、還沒到開始時間回傳 False。"""
    candidate = repository.get_bracket(session, bracket_id)
    assert candidate is not None  # 剛查到的 id
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=candidate.tournament_id
    )
    session.refresh(candidate)  # 鎖住後以資料庫最新值重新檢查
    if candidate.start_handled_at is not None:
        return True
    starts_at = checkin_rules.tournament_starts_at(
        m.scheduled_at for m in repository.list_matches(session, bracket_id)
    )
    if starts_at > now:
        return False
    if tournament.status == TournamentStatus.PUBLISHED:
        tournaments_service.transition_tournament(
            session,
            tournament_id=tournament.id,
            to=TournamentStatus.ONGOING,
            actor_id=None,
        )
    repository.mark_start_handled(session, candidate, now)
    return True


# ---------------------------------------------------------------- 比分登錄與送出（Story 5.3、5.4）

# 已送出系列結果的場次：之後只能經申訴更正
_SUBMITTED = frozenset(
    {MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED, MatchStatus.CONFIRMED}
)

# 不能登錄的原因代碼（`ScoreEntryState.reason`）對應寫入 API 的錯誤碼與訊息（皆 409）
_ENTRY_REJECTIONS: dict[ScoreEntryReason, tuple[str, str]] = {
    "not_accepting_scores": (
        "TOURNAMENT_NOT_ACCEPTING_SCORES",
        "這場賽事目前不接受比分回報。",
    ),
    "result_submitted": (
        "RESULT_ALREADY_SUBMITTED",
        "系列結果已送出，無法再修改，只能經由申訴更正。",
    ),
    "not_recordable": ("MATCH_NOT_RECORDABLE", "這場比賽不能登錄比分。"),
    "teams_pending": ("MATCH_TEAMS_PENDING", "對手還沒確定，暫時不能登錄比分。"),
    "check_in_incomplete": ("CHECK_IN_INCOMPLETE", "兩隊都報到後才能登錄比分。"),
}

# `scoring.py` 的原因對應錯誤碼與訊息（皆 409）；`not_decided` 的訊息含門檻，另外組
_SCORE_REJECTIONS: dict[scoring.ScoreReason, tuple[str, str]] = {
    "tie": ("SCORE_TIE", "一局不能平手。"),
    "invalid_score": ("SCORE_INVALID", "比分格式不正確。"),
    "series_decided": ("SERIES_DECIDED", "已有隊伍達到勝局門檻，不能再新增局。"),
    "redundant_games": (
        "REDUNDANT_GAMES",
        "這樣修改後，後面的局就不需要打了。請先刪除後面的局再修改。",
    ),
    "invalid_game_no": ("INVALID_GAME_NO", "這一局無法登錄或刪除，請重新整理頁面。"),
    "not_last_game": ("NOT_LAST_GAME", "只能刪除最後一局。"),
}


def _score_rejection(reason: scoring.ScoreReason, *, wins_needed: int) -> BusinessError:
    if reason == "not_decided":
        return BusinessError(
            "SERIES_NOT_DECIDED",
            f"任一隊拿到 {wins_needed} 勝後才能送出。",
            status_code=409,
        )
    code, message = _SCORE_REJECTIONS[reason]
    return BusinessError(code, message, status_code=409)


def _is_scorer(match: Match, tournament: TournamentRead, account_id: uuid.UUID) -> bool:
    """記分者：有指派裁判時只有該裁判；未指派時為賽事主辦方。"""
    if match.referee_account_id is not None:
        return match.referee_account_id == account_id
    return tournament.organizer_id == account_id


def _entry_reason(
    session: Session, *, match: Match, tournament: TournamentRead
) -> ScoreEntryReason | None:
    """寫入檢查的第 3、5、6 步（身分另外判斷）；可以登錄為 None。

    賽事狀態沿用 tournaments 的 `ensure_accepting_scores`，兩邊不會不一致。
    """
    try:
        tournaments_service.ensure_accepting_scores(tournament)
    except BusinessError:
        return "not_accepting_scores"
    status = MatchStatus(match.status)
    if status in _SUBMITTED:
        return "result_submitted"
    if status == MatchStatus.VOIDED:
        return "not_recordable"
    if match.team_a_id is None or match.team_b_id is None:
        return "teams_pending"
    checked_in = {c.team_id for c in repository.list_check_ins(session, match.id)}
    if not {match.team_a_id, match.team_b_id} <= checked_in:
        return "check_in_incomplete"
    return None


def _to_result(game: MatchGame) -> scoring.GameResult:
    winner: scoring.Side = "a" if game.winner_side == "a" else "b"
    return scoring.GameResult(winner=winner, score_a=game.score_a, score_b=game.score_b)


def _public_game(game: MatchGame) -> PublicGame:
    return PublicGame(
        game_no=game.game_no,
        winner_side="a" if game.winner_side == "a" else "b",
        score_a=game.score_a,
        score_b=game.score_b,
    )


def _game_values(game: MatchGame) -> dict[str, object]:
    return {
        "game_no": game.game_no,
        "winner_side": game.winner_side,
        "score_a": game.score_a,
        "score_b": game.score_b,
    }


def _bo(session: Session, match: Match) -> int:
    return tournaments_service.bo_for_round(
        session, tournament_id=match.tournament_id, round_no=match.round_no
    )


def _series(games: Sequence[MatchGame], bo: int) -> scoring.Series:
    return scoring.series([_to_result(game) for game in games], bo=bo)


def _locked_for_scoring(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> tuple[Match, TournamentRead]:
    """寫入（登錄、刪除、送出）共用的檢查 1～6；通過時回傳鎖住的場次與賽事。

    順序：404 → `lock_match`（AD-6，之後才讀狀態、局與報到紀錄）→ 賽事接受比分 →
    記分者 → 場次狀態 → 兩隊確定與報到。
    """
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    match = lock_match(session, match_id=match_id)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    tournaments_service.ensure_accepting_scores(tournament)
    if not _is_scorer(match, tournament, account_id):
        raise BusinessError(
            "SCORER_REQUIRED",
            "只有這場比賽的裁判（未指派時為主辦方）可以登錄比分。",
            status_code=403,
        )
    reason = _entry_reason(session, match=match, tournament=tournament)
    if reason is not None:
        code, message = _ENTRY_REJECTIONS[reason]
        raise BusinessError(code, message, status_code=409)
    return match, tournament


def _sync_wins(session: Session, match: Match, games: Sequence[MatchGame]) -> None:
    """依 `scoring.series` 重算場次的勝局數（公開 Score display 用），一併更新 `updated_at`。"""
    result = _series(games, _bo(session, match))
    repository.set_match_wins(session, match, result.wins_a, result.wins_b, clock.now())


def record_game(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
    game_no: int,
    data: GameScoreIn,
) -> ScoreEntryState:
    """登錄第 `game_no` 局：等於目前局數＋1 為新增，不大於目前局數為覆寫。

    先鎖場次再檢查（AD-6），規則交給 `scoring.py`；第一局登錄時場次轉為進行中。
    任何拒絕都不改局、場次與操作紀錄。
    """
    match, tournament = _locked_for_scoring(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account_id
    )
    bo = _bo(session, match)
    needed = scoring.wins_needed(bo)
    result = scoring.make_game(
        tournament.score_type.value,
        winner=data.winner_side,
        score_a=data.score_a,
        score_b=data.score_b,
    )
    if not isinstance(result, scoring.GameResult):
        raise _score_rejection(result, wins_needed=needed)
    games = repository.list_games(session, match.id)
    reason = scoring.check_record(
        [_to_result(game) for game in games], bo=bo, game_no=game_no, result=result
    )
    if reason is not None:
        raise _score_rejection(reason, wins_needed=needed)

    now = clock.now()
    before: dict[str, object] | None = None
    if game_no <= len(games):
        target = games[game_no - 1]
        before = _game_values(target)
        repository.update_game(
            session,
            target,
            winner_side=result.winner,
            score_a=result.score_a,
            score_b=result.score_b,
            recorded_by=account_id,
            recorded_at=now,
        )
    else:
        target = MatchGame(
            match_id=match.id,
            game_no=game_no,
            winner_side=result.winner,
            score_a=result.score_a,
            score_b=result.score_b,
            recorded_by=account_id,
            recorded_at=now,
        )
        repository.add_game(session, target)
    after: dict[str, object] = {}
    if match.status == MatchStatus.SCHEDULED:
        # 第一局：狀態轉換一併記進操作紀錄
        transition_match(session, match=match, to=MatchStatus.LIVE)
        before = {**(before or {}), "status": MatchStatus.SCHEDULED.value}
        after["status"] = MatchStatus.LIVE.value
    _sync_wins(session, match, repository.list_games(session, match.id))
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=match.tournament_id,
        action="match.game_recorded",
        entity_type="match",
        entity_id=match.id,
        before=before,
        after={
            **_game_values(target),
            "wins_a": match.wins_a,
            "wins_b": match.wins_b,
            **after,
        },
    )
    return _score_entry(session, match=match, tournament=tournament)


def delete_game(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
    game_no: int,
) -> ScoreEntryState:
    """刪除最後一局；刪到沒有任何局時場次維持進行中（使用者 2026-11-01 決定）。"""
    match, tournament = _locked_for_scoring(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account_id
    )
    games = repository.list_games(session, match.id)
    reason = scoring.check_delete([_to_result(game) for game in games], game_no=game_no)
    if reason is not None:
        raise _score_rejection(
            reason, wins_needed=scoring.wins_needed(_bo(session, match))
        )
    target = games[game_no - 1]
    removed = _game_values(target)
    repository.delete_game(session, target)
    _sync_wins(session, match, repository.list_games(session, match.id))
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=match.tournament_id,
        action="match.game_deleted",
        entity_type="match",
        entity_id=match.id,
        before=removed,
        after={"wins_a": match.wins_a, "wins_b": match.wins_b},
    )
    return _score_entry(session, match=match, tournament=tournament)


def submit_result(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> ScoreEntryState:
    """送出系列結果：寫 `outcome = played`、勝隊、送出者與時間、申訴截止時間，轉為申訴期。

    不寫 `confirmed_at`、勝隊不晉級（申訴期滿由 `auto_confirm_expired` 確認並推進）。
    """
    match, tournament = _locked_for_scoring(
        session, tournament_id=tournament_id, match_id=match_id, account_id=account_id
    )
    result = _series(repository.list_games(session, match.id), _bo(session, match))
    if result.winner is None:
        raise _score_rejection(
            result.reason or "not_decided", wins_needed=result.wins_needed
        )
    winner_id = match.team_a_id if result.winner == "a" else match.team_b_id
    assert winner_id is not None  # `_locked_for_scoring` 已確認兩隊都確定
    before = MatchStatus(match.status)
    transition_match(session, match=match, to=MatchStatus.APPEAL_WINDOW)
    now = clock.now()
    deadline = now + timedelta(minutes=tournament.appeal_minutes)
    repository.set_match_wins(session, match, result.wins_a, result.wins_b, now)
    repository.set_match_submission(
        session,
        match,
        winner_id=winner_id,
        submitted_by=account_id,
        submitted_at=now,
        appeal_deadline=deadline,
    )
    audit.record(
        session,
        actor_id=account_id,
        tournament_id=match.tournament_id,
        action="match.result_submitted",
        entity_type="match",
        entity_id=match.id,
        before={"status": before.value},
        after={
            "status": MatchStatus.APPEAL_WINDOW.value,
            "outcome": MatchOutcome.PLAYED.value,
            "winner_id": winner_id,
            "wins_a": result.wins_a,
            "wins_b": result.wins_b,
            "appeal_deadline": deadline,
        },
    )
    events.publish(session, MatchResultSubmitted(match_id=match.id))
    return _score_entry(session, match=match, tournament=tournament)


def _score_entry(
    session: Session, *, match: Match, tournament: TournamentRead
) -> ScoreEntryState:
    """記分者看到的完整狀態（呼叫端已確認是記分者）。"""
    games = repository.list_games(session, match.id)
    result = _series(games, _bo(session, match))
    submitted_by_name: str | None = None
    if match.submitted_by is not None:
        contact = identity_service.get_account_contact(session, match.submitted_by)
        submitted_by_name = contact.display_name if contact is not None else None
    return ScoreEntryState(
        is_scorer=True,
        reason=_entry_reason(session, match=match, tournament=tournament),
        games=[_public_game(game) for game in games],
        series=SeriesRead(
            wins_a=result.wins_a,
            wins_b=result.wins_b,
            winner=result.winner,
            can_submit=result.can_submit,
            wins_needed=result.wins_needed,
            reason=result.reason,
        ),
        submitted_by_name=submitted_by_name,
        submitted_at=match.submitted_at,
    )


def get_score_entry(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    account_id: uuid.UUID,
) -> ScoreEntryState:
    """登入者對這場的比分登錄狀態；不是記分者時只回 `is_scorer = False`，其他欄位空。

    場次不存在或不屬於該賽事拋 404 `MATCH_NOT_FOUND`。
    """
    match = _match_in_tournament(
        session, tournament_id=tournament_id, match_id=match_id
    )
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    if not _is_scorer(match, tournament, account_id):
        return ScoreEntryState(is_scorer=False)
    return _score_entry(session, match=match, tournament=tournament)


# ---------------------------------------------------------------- 修改場次時間（4.3）

# 賽事要在這兩個狀態才能改場次時間
_RESCHEDULABLE_TOURNAMENT = frozenset(
    {TournamentStatus.PUBLISHED, TournamentStatus.ONGOING}
)

# 不能修改的原因 -> (錯誤碼, 訊息)；皆 409
_RESCHEDULE_BLOCKS: dict[RescheduleBlockReason, tuple[str, str]] = {
    "tournament_not_reschedulable": (
        "TOURNAMENT_NOT_RESCHEDULABLE",
        "賽事目前的狀態不能修改場次時間。",
    ),
    "match_not_reschedulable": (
        "MATCH_NOT_RESCHEDULABLE",
        "只有待開打的場次可以修改時間。",
    ),
    "forfeit_due": (
        "MATCH_NOT_RESCHEDULABLE",
        "棄權期限已過，等待系統判定棄權，不能再修改時間。",
    ),
    "already_checked_in": (
        "MATCH_ALREADY_CHECKED_IN",
        "已有隊伍報到，不能再修改這場的時間。",
    ),
    "no_valid_time": (
        "RESCHEDULE_NO_VALID_TIME",
        "這場目前沒有可選的時間。",
    ),
}

_RESCHEDULE_CODES: dict[schedule_rules.RescheduleReason, str] = {
    "before_now": "RESCHEDULE_BEFORE_NOW",
    "before_feeder": "RESCHEDULE_BEFORE_FEEDER",
    "after_next_match": "RESCHEDULE_AFTER_NEXT_MATCH",
    "no_valid_time": "RESCHEDULE_NO_VALID_TIME",
}


def _reschedule_block(
    session: Session, tournament: TournamentRead, match: Match
) -> RescheduleBlockReason | None:
    """依序檢查賽事狀態、場次狀態、棄權期限已過未判、是否已有隊伍報到；可以修改為 None。"""
    if tournament.status not in _RESCHEDULABLE_TOURNAMENT:
        return "tournament_not_reschedulable"
    if match.status != MatchStatus.SCHEDULED:
        return "match_not_reschedulable"
    checked_in = bool(repository.list_check_ins(session, match.id))
    if (
        not checked_in
        and match.forfeit_deadline is not None
        and match.forfeit_deadline <= clock.now()
    ):
        return "forfeit_due"
    if checked_in:
        return "already_checked_in"
    return None


def _reschedule_window(
    session: Session,
    tournament: TournamentRead,
    match: Match,
    matches: Sequence[Match],
    *,
    now: datetime,
) -> tuple[
    schedule_rules.RescheduleWindow,
    Callable[[datetime], schedule_rules.RescheduleReason | None],
]:
    """本場修改時間的允許範圍，與檢查新時間的函式（列表與修改 API 共用，規則都在 `schedule.py`）。

    下一場＝勝隊去的場次；準決賽取決賽與季軍賽中較早的一場。
    前一輪場次＝勝隊或敗隊會進入本場的場次。
    """

    def min_gap(round_no: int) -> int:
        return schedule_rules.round_min_gap(
            forfeit_minutes=tournament.forfeit_minutes,
            best_of=tournaments_service.bo_for_round(
                session, tournament_id=tournament.id, round_no=round_no
            ),
            game_minutes=tournament.game_minutes,
            appeal_minutes=tournament.appeal_minutes,
        )

    by_id = {m.id: m for m in matches}
    next_times = [
        by_id[next_id].scheduled_at
        for next_id in (match.next_match_id, match.loser_next_match_id)
        if next_id is not None
    ]
    feeders = [
        m for m in matches if match.id in (m.next_match_id, m.loser_next_match_id)
    ]
    # 最早可選時間：現在（進位到整分）＋報到提前量，兩隊至少有完整的報到時間
    floor = now.replace(second=0, microsecond=0)
    if floor < now:
        floor += timedelta(minutes=1)
    now = floor + checkin_rules.CHECK_IN_LEAD
    next_match_at = min(next_times) if next_times else None
    own_min_gap = min_gap(match.round_no)
    feeder_times = [m.scheduled_at for m in feeders]
    feeder_min_gap = max((min_gap(m.round_no) for m in feeders), default=0)
    window = schedule_rules.reschedule_window(
        now=now,
        next_match_at=next_match_at,
        own_min_gap=own_min_gap,
        feeder_times=feeder_times,
        feeder_min_gap=feeder_min_gap,
    )

    def check(new_at: datetime) -> schedule_rules.RescheduleReason | None:
        return schedule_rules.check_reschedule(
            new_at,
            now=now,
            next_match_at=next_match_at,
            own_min_gap=own_min_gap,
            feeder_times=feeder_times,
            feeder_min_gap=feeder_min_gap,
        )

    return window, check


def _range_text(window: schedule_rules.RescheduleWindow) -> str:
    start = _taipei_text(window.earliest)
    if window.latest is None:
        return f"{start} 起"
    return f"{start}～{_taipei_text(window.latest)}"


def _reschedule_error(
    reason: schedule_rules.RescheduleReason,
    window: schedule_rules.RescheduleWindow,
) -> BusinessError:
    """新時間不在範圍內的 409；改期（4.3）與重賽（6.2）共用，錯誤碼與訊息不分岔。"""
    if reason == "no_valid_time":
        message = f"這場目前沒有可選的時間（最早 {_taipei_text(window.earliest)}）。"
    else:
        message = f"新時間不在允許範圍內，可選 {_range_text(window)}。"
    return BusinessError(_RESCHEDULE_CODES[reason], message, status_code=409)


def reschedule_match(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
    scheduled_at: datetime,
) -> MatchRead:
    """修改待開打場次的預定時間；任何拒絕都不改時間、棄權期限、操作紀錄與事件。

    順序：404 -> `lock_tournament`、`lock_match`（AD-6）-> 主辦方 -> 賽事狀態 ->
    場次狀態 -> 已報到 -> `schedule.check_reschedule`。
    """
    tournaments_service.get_tournament(session, tournament_id=tournament_id)
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    match = lock_match(session, match_id=match_id)
    authz.ensure_tournament_owner(tournament, actor_id)
    block = _reschedule_block(session, tournament, match)
    if block is not None:
        code, message = _RESCHEDULE_BLOCKS[block]
        raise BusinessError(code, message, status_code=409)
    matches = repository.list_matches(session, match.bracket_id, fresh=True)
    now = clock.now()
    window, check = _reschedule_window(session, tournament, match, matches, now=now)
    reason = check(scheduled_at)
    if reason is not None:
        raise _reschedule_error(reason, window)

    before = {
        "scheduled_at": match.scheduled_at,
        "forfeit_deadline": match.forfeit_deadline,
    }
    scheduled_at = scheduled_at.astimezone(UTC)
    if scheduled_at == match.scheduled_at:
        return _match_to_read(match)  # 時間沒變：不寫紀錄、不發事件
    repository.set_scheduled_at(session, match, scheduled_at, now)
    if match.team_a_id is not None and match.team_b_id is not None:
        start_forfeit_clock(session, match=match)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action="match.rescheduled",
        entity_type="match",
        entity_id=match.id,
        before=before,
        after={
            "scheduled_at": match.scheduled_at,
            "forfeit_deadline": match.forfeit_deadline,
        },
    )
    events.publish(
        session,
        MatchRescheduled(match_id=match.id, scheduled_at=match.scheduled_at),
    )
    return _match_to_read(match)


# ---------------------------------------------------------------- 6.x 前置（B 呼叫）


def check_replay_time(
    session: Session,
    *,
    tournament: TournamentRead,
    match: Match,
    scheduled_at: datetime,
) -> None:
    """重新比賽的新時間以 4.3 改期同一個範圍檢查（6.2 `replay_match` 呼叫）。

    不符合拋與 `reschedule_match` 相同的 409（`RESCHEDULE_BEFORE_NOW`、
    `RESCHEDULE_BEFORE_FEEDER`、`RESCHEDULE_AFTER_NEXT_MATCH`、`RESCHEDULE_NO_VALID_TIME`，
    訊息附台北時間範圍）。不檢查賽事狀態、場次狀態、報到與主辦方（呼叫端負責），
    不寫入任何資料。呼叫端先 `lock_tournament`、`lock_match`（AD-6）；相鄰場次以資料庫
    最新值讀取。`scheduled_at` 必須帶時區（router 的欄位驗證負責），沒帶時區拋
    `ValueError`（`schedule._utc`）；`tournament` 不是 `match` 所屬的賽事也拋
    `ValueError`。兩者都是呼叫端的程式錯誤，不是業務錯誤。
    """
    if tournament.id != match.tournament_id:
        raise ValueError("tournament 不是 match 所屬的賽事")
    matches = repository.list_matches(session, match.bracket_id, fresh=True)
    window, check = _reschedule_window(
        session, tournament, match, matches, now=clock.now()
    )
    reason = check(scheduled_at)
    if reason is not None:
        raise _reschedule_error(reason, window)


def get_replay_window(session: Session, *, match_id: uuid.UUID) -> RescheduleInfo:
    """S32 重賽時間選擇器的範圍，與 `check_replay_time` 同一個規則；不寫入。

    判斷順序（與 `replay_match` 的拒絕條件一致）：場次不存在拋 404 `MATCH_NOT_FOUND`；
    賽事不是賽程已公布或進行中 → `tournament_not_reschedulable`、範圍為 None；
    場次不是申訴中或結果不是棄權（一方或雙方，6.2）→ `match_not_reschedulable`、範圍為 None；
    其餘有可選範圍時 `can_reschedule=True`，範圍為空時 `reason="no_valid_time"`，
    仍附 `earliest`、`latest`（主辦方要先到 S30 把下一場改晚）。
    本場與相鄰場次都以資料庫最新值讀取（與 `check_replay_time` 一致）。
    """
    match = repository.get_match(session, match_id)
    if match is None:
        raise _match_not_found()
    matches = repository.list_matches(session, match.bracket_id, fresh=True)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    blocked: RescheduleBlockReason | None = None
    if tournament.status not in _RESCHEDULABLE_TOURNAMENT:
        blocked = "tournament_not_reschedulable"
    elif MatchStatus(match.status) != MatchStatus.APPEALED or match.outcome not in (
        MatchOutcome.FORFEIT,
        MatchOutcome.DOUBLE_FORFEIT,
    ):
        blocked = "match_not_reschedulable"
    if blocked is not None:
        return RescheduleInfo(
            can_reschedule=False, reason=blocked, earliest=None, latest=None
        )
    window, _check = _reschedule_window(
        session, tournament, match, matches, now=clock.now()
    )
    return RescheduleInfo(
        can_reschedule=not window.is_empty,
        reason="no_valid_time" if window.is_empty else None,
        earliest=window.earliest,
        latest=window.latest,
    )


def mark_appealed(session: Session, *, match_id: uuid.UUID) -> MatchRead:
    """申訴期 → 申訴中（6.1 disputes `file_appeal` 呼叫）；已是申訴中不動。

    其他狀態拋 409 `MATCH_INVALID_TRANSITION`；不改 `appeal_deadline`。呼叫端先
    `lock_tournament`，函式內再 `lock_match`（AD-6）。實作在 `appeals.py`（B 新增）。
    """
    # appeals.py 會 import 本模組，放在函式內避免循環 import
    from app.modules.competition import appeals

    return appeals.mark_appealed(session, match_id=match_id)


def uphold_result(
    session: Session, *, match_id: uuid.UUID, actor_id: uuid.UUID
) -> MatchRead:
    """申訴處理「維持原結果」（6.2 disputes `resolve_appeals` 呼叫）。

    只接受申訴中；沿用已寫入的 outcome、勝隊呼叫 `confirm_match`（內含晉級）。
    呼叫端先 `lock_tournament`，函式內再 `lock_match`（AD-6）。實作在 `appeals.py`。
    """
    from app.modules.competition import appeals

    return appeals.uphold_result(session, match_id=match_id, actor_id=actor_id)


def correct_result(
    session: Session,
    *,
    match_id: uuid.UUID,
    games: Sequence[GameScoreIn],
    actor_id: uuid.UUID,
) -> CorrectionResult:
    """申訴處理「更正結果」（6.2）：整份替換各局、重算勝隊後確認並晉級。

    只接受申訴中、`outcome=played`；各局規則與 5.3 相同，另加 `SERIES_NOT_DECIDED`、
    `REDUNDANT_GAMES`。回傳前後各局與新勝隊。實作在 `appeals.py`。
    """
    from app.modules.competition import appeals

    return appeals.correct_result(
        session, match_id=match_id, games=games, actor_id=actor_id
    )


def replay_match(
    session: Session,
    *,
    match_id: uuid.UUID,
    scheduled_at: datetime,
    actor_id: uuid.UUID,
) -> ReplayCleared:
    """申訴處理「重新比賽」（6.2）：只用於判棄權（一方或雙方）的場次。

    清除結果與報到、回到待開打、寫入新時間並重新起算棄權；其他 outcome 拋 409
    `REPLAY_ONLY_FOR_FORFEIT`，時間不合法沿用 `RESCHEDULE_*`。實作在 `appeals.py`。
    """
    from app.modules.competition import appeals

    return appeals.replay_match(
        session, match_id=match_id, scheduled_at=scheduled_at, actor_id=actor_id
    )


def unassign_referee_if_member(session: Session, *, match: Match) -> None:
    """該場裁判是任一隊的隊員時收回（6.5 `disqualify` 頂替後呼叫）。

    檢查兩隊（`advance` 填位後只檢查新填入的一隊）；收回時與 `advance` 相同，寫
    `match.referee_unassigned`（操作者為系統）、發 `RefereeUnassigned`。裁判不是隊員、
    沒有裁判、隊伍待定的一方不動。只對待開打、進行中的場次呼叫（已結束的場次裁判
    不再有意義）；場次不是 `scheduled`、`live` 時拋 `ValueError`（呼叫端的程式錯誤，與
    `check_replay_time` 一致），不寫入。呼叫端先 `lock_tournament`、`lock_match`（AD-6）
    並已寫入頂替後的隊伍。
    """
    if MatchStatus(match.status) not in (MatchStatus.SCHEDULED, MatchStatus.LIVE):
        raise ValueError("只能對待開打或進行中的場次收回裁判")
    for team_id in (match.team_a_id, match.team_b_id):
        _unassign_if_member(session, match=match, team_id=team_id)


def list_my_referee_matches(
    session: Session, *, account_id: uuid.UUID
) -> list[RefereeTournamentMatches]:
    """S13：指派給我、未取消的場次，依賽事分組。

    組內依預定時間、代號；各組依組內最早的預定時間（同時間依賽事名稱）。沒有指派回空清單。
    已取消賽事的場次不列出（取消賽事不會把場次改成 voided，所以要在這裡過濾）；已結束的賽事仍列出。
    """
    matches = repository.list_referee_matches(session, account_id)
    if not matches:
        return []
    checked_in = repository.list_check_in_pairs(session, [m.id for m in matches])
    tournaments: dict[uuid.UUID, TournamentRead] = {}
    groups: dict[uuid.UUID, list[RefereeMatch]] = {}
    for bracket_id in dict.fromkeys(m.bracket_id for m in matches):
        bracket = repository.get_bracket(session, bracket_id)
        if bracket is None:
            # 場次的外鍵保證對戰表存在；萬一不在，略過這些場次，不讓整頁失敗
            logger.error("場次的對戰表不存在：bracket_id=%s", bracket_id)
            continue
        if bracket.tournament_id not in tournaments:
            tournaments[bracket.tournament_id] = tournaments_service.get_tournament(
                session, tournament_id=bracket.tournament_id
            )
        if tournaments[bracket.tournament_id].status == TournamentStatus.CANCELLED:
            continue
        mine = [m for m in matches if m.bracket_id == bracket_id]
        public_matches, _team_ref = _public_matches(session, bracket, mine)
        by_id = {p.id: p for p in public_matches}
        rows = groups.setdefault(bracket.tournament_id, [])
        for match in mine:
            public = by_id[match.id]
            teams = _match_teams(match)
            rows.append(
                RefereeMatch(
                    **public.model_dump(),
                    round_name="季軍賽"
                    if match.is_third_place
                    else bracket_rules.round_name(match.round_no, bracket.rounds),
                    both_checked_in=len(teams) == 2
                    and all((match.id, team_id) in checked_in for team_id in teams),
                )
            )
    result = []
    for tournament_id, rows in groups.items():
        rows.sort(key=lambda m: (m.scheduled_at, m.code))
        tournament = tournaments[tournament_id]
        result.append(
            RefereeTournamentMatches(
                tournament=PublicTournamentRef(id=tournament.id, name=tournament.name),
                matches=rows,
            )
        )
    result.sort(key=lambda g: (g.matches[0].scheduled_at, g.tournament.name))
    return result


def list_my_next_matches(session: Session, *, account_id: uuid.UUID) -> list[NextMatch]:
    """S12：登入者所屬、已參賽的每支隊伍各回最多一場下一場（只讀）。

    下一場＝該隊出現在 `team_a_id`／`team_b_id`、狀態不是已確認或已取消的場次中輪次最小的一場；
    沒有這種場次（已淘汰、賽事已結束）就不回。已取消賽事的隊伍略過（照 S13）。
    順序沿用 registration `list_my_teams`（新加入的隊伍在前）。
    """
    teams = registration_port.list_drawn_teams_of_account(
        session, account_id=account_id
    )
    if not teams:
        return []
    tournament_of = {team.team_id: team.tournament_id for team in teams}
    picked: dict[uuid.UUID, Match] = {}
    # 已依輪次排序：每隊第一次出現的就是輪次最小的一場
    for match in repository.list_unsettled_team_matches(session, list(tournament_of)):
        for team_id in _match_teams(match):
            if (
                team_id not in picked
                and tournament_of.get(team_id) == match.tournament_id
            ):
                picked[team_id] = match
    if not picked:
        return []

    tournaments: dict[uuid.UUID, TournamentRead] = {}
    brackets: dict[uuid.UUID, Bracket] = {}
    public_by_id: dict[uuid.UUID, PublicMatch] = {}
    for bracket_id in dict.fromkeys(m.bracket_id for m in picked.values()):
        bracket = repository.get_bracket(session, bracket_id)
        if bracket is None:
            # 場次的外鍵保證對戰表存在；萬一不在，略過這些場次，不讓整頁失敗
            logger.error("場次的對戰表不存在：bracket_id=%s", bracket_id)
            continue
        if bracket.tournament_id not in tournaments:
            tournaments[bracket.tournament_id] = tournaments_service.get_tournament(
                session, tournament_id=bracket.tournament_id
            )
        if tournaments[bracket.tournament_id].status == TournamentStatus.CANCELLED:
            continue
        brackets[bracket_id] = bracket
        mine = list(
            {m.id: m for m in picked.values() if m.bracket_id == bracket_id}.values()
        )
        public_matches, _team_ref = _public_matches(session, bracket, mine)
        public_by_id.update((p.id, p) for p in public_matches)

    result = []
    for team in teams:
        chosen = picked.get(team.team_id)
        if chosen is None or chosen.id not in public_by_id:
            continue
        bracket = brackets[chosen.bracket_id]
        result.append(
            NextMatch(
                **public_by_id[chosen.id].model_dump(),
                team_id=team.team_id,
                round_name="季軍賽"
                if chosen.is_third_place
                else bracket_rules.round_name(chosen.round_no, bracket.rounds),
                check_in_opens_at=checkin_rules.check_in_opens_at(chosen.scheduled_at),
                # 與公開單場相同：只對兩隊都確定的待開打場次給報到截止，其他情況的值可能已過期
                forfeit_deadline=(
                    chosen.forfeit_deadline
                    if chosen.status == MatchStatus.SCHEDULED
                    and len(_match_teams(chosen)) == 2
                    else None
                ),
            )
        )
    return result


def list_managed_matches(
    session: Session, *, tournament_id: uuid.UUID, actor_id: uuid.UUID
) -> list[ManagedMatch]:
    """S30 場次列表：依輪次、季軍賽在決賽之後；每場附上能不能改時間與可選範圍。"""
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        raise BusinessError(
            "BRACKET_NOT_FOUND", "這場賽事還沒有對戰表。", status_code=404
        )
    matches = repository.list_matches(session, bracket.id)
    public_matches, _team_ref = _public_matches(session, bracket, matches)
    now = clock.now()
    referees = tournaments_service.list_referees(session, tournament_id=tournament_id)
    member_cache: dict[tuple[uuid.UUID, uuid.UUID], bool] = {}
    result = []
    for match, public in zip(matches, public_matches, strict=True):
        can_assign = _can_assign(tournament, match)
        assignable: list[uuid.UUID] = []
        for referee in referees if can_assign else []:
            blocked = False
            for team_id in _match_teams(match):
                key = (team_id, referee.account_id)
                if key not in member_cache:
                    member_cache[key] = registration_port.is_member(
                        session, team_id=team_id, account_id=referee.account_id
                    )
                blocked = blocked or member_cache[key]
            if not blocked:
                assignable.append(referee.account_id)
        block = _reschedule_block(session, tournament, match)
        earliest: datetime | None = None
        latest: datetime | None = None
        if block is None:
            window, _check = _reschedule_window(
                session, tournament, match, matches, now=now
            )
            earliest, latest = window.earliest, window.latest
            if window.is_empty:
                block = "no_valid_time"
        result.append(
            ManagedMatch(
                id=match.id,
                code=match.code,
                round_no=match.round_no,
                slot_no=match.slot_no,
                is_third_place=match.is_third_place,
                team_a=public.team_a,
                team_b=public.team_b,
                source_a=public.source_a,
                source_b=public.source_b,
                scheduled_at=match.scheduled_at,
                status=match.status,
                referee_account_id=match.referee_account_id,
                reschedule=RescheduleInfo(
                    can_reschedule=block is None,
                    reason=block,
                    earliest=earliest,
                    latest=latest,
                ),
                assignable_referee_ids=assignable,
                can_assign_referee=can_assign,
            )
        )
    return result


# 可以指派／收回裁判的狀態
_ASSIGNABLE_TOURNAMENT = frozenset(
    {TournamentStatus.PUBLISHED, TournamentStatus.ONGOING}
)
_ASSIGNABLE_MATCH = frozenset({MatchStatus.SCHEDULED, MatchStatus.LIVE})


def _can_assign(tournament: TournamentRead, match: Match) -> bool:
    return (
        tournament.status in _ASSIGNABLE_TOURNAMENT
        and MatchStatus(match.status) in _ASSIGNABLE_MATCH
    )


def _ensure_assignable(tournament: TournamentRead, match: Match) -> None:
    if tournament.status not in _ASSIGNABLE_TOURNAMENT:
        raise BusinessError(
            "TOURNAMENT_NOT_ASSIGNABLE",
            "賽事目前的狀態不能指派裁判。",
            status_code=409,
        )
    if MatchStatus(match.status) not in _ASSIGNABLE_MATCH:
        raise BusinessError(
            "MATCH_REFEREE_LOCKED",
            "這場已送出結果或已取消，不能再更動裁判。",
            status_code=409,
        )


def _match_teams(match: Match) -> list[uuid.UUID]:
    return [t for t in (match.team_a_id, match.team_b_id) if t is not None]


def _locked_for_referee(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> Match:
    """404 -> `lock_tournament`、`lock_match`（AD-6）-> 主辦方 -> 賽事與場次狀態。"""
    tournaments_service.get_tournament(session, tournament_id=tournament_id)
    _match_in_tournament(session, tournament_id=tournament_id, match_id=match_id)
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    match = lock_match(session, match_id=match_id)
    authz.ensure_tournament_owner(tournament, actor_id)
    _ensure_assignable(tournament, match)
    return match


def assign_referee(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
    referee_account_id: uuid.UUID,
) -> MatchRead:
    """指派或改派場次的裁判；任何拒絕都不改資料、不寫紀錄、不發事件。

    順序：404 -> 鎖（AD-6）-> 主辦方 -> 賽事狀態 -> 場次狀態 -> 同一人直接回傳 ->
    必須是賽事裁判 -> 不能是已確定隊伍的隊員。
    """
    match = _locked_for_referee(
        session, tournament_id=tournament_id, match_id=match_id, actor_id=actor_id
    )
    previous = match.referee_account_id
    if previous == referee_account_id:
        return _match_to_read(match)
    if not tournaments_service.is_referee(
        session, tournament_id=tournament_id, account_id=referee_account_id
    ):
        raise BusinessError(
            "NOT_TOURNAMENT_REFEREE",
            "這個帳號不是這場賽事的裁判。",
            status_code=409,
        )
    if any(
        registration_port.is_member(
            session, team_id=team_id, account_id=referee_account_id
        )
        for team_id in _match_teams(match)
    ):
        raise BusinessError(
            "REFEREE_IS_TEAM_MEMBER",
            "裁判是這場參賽隊伍的隊員，不能指派。",
            status_code=409,
        )
    _set_referee(session, match=match, referee_id=referee_account_id, actor_id=actor_id)
    if previous is not None:
        events.publish(
            session, RefereeUnassigned(match_id=match.id, referee_account_id=previous)
        )
    events.publish(
        session,
        RefereeAssigned(match_id=match.id, referee_account_id=referee_account_id),
    )
    return _match_to_read(match)


def unassign_referee(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    match_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> MatchRead:
    """收回裁判，之後由主辦方代登；沒有裁判時直接回傳。"""
    match = _locked_for_referee(
        session, tournament_id=tournament_id, match_id=match_id, actor_id=actor_id
    )
    previous = match.referee_account_id
    if previous is None:
        return _match_to_read(match)
    _set_referee(session, match=match, referee_id=None, actor_id=actor_id)
    events.publish(
        session, RefereeUnassigned(match_id=match.id, referee_account_id=previous)
    )
    return _match_to_read(match)


# ---------------------------------------------------------------- 取消資格（6.5）


def disqualify(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    team_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> DisqualifyResult:
    """取消隊伍資格，依 epic-6-context〈取消資格（期中版）〉判對手獲勝或頂替。

    disputes `resolve_report` 屬實時呼叫；規則與對手未定時拒絕的情況見 `disqualification.py`。
    先 `lock_tournament`，再依 id 遞增鎖住對戰表的全部場次（AD-6），判斷完成後才寫入。
    報名一律改為取消資格（registration `disqualify_registration`，操作者為 `actor_id`）；
    抽籤前只改報名狀態，不做遞補。判對手獲勝以 `disqualified` 確認並沿用 `advance`
    晉級；頂替後對該場呼叫 `unassign_referee_if_member`，兩隊湊齊且待開打時
    `start_forfeit_clock`。每個被改動的場次寫操作紀錄（操作者為 `actor_id`；
    隨後晉級推進的變更操作者為系統）。

    賽事已結束或已取消拋 409 `TOURNAMENT_FINISHED`／`TOURNAMENT_CANCELLED`；隊伍不屬於
    該賽事拋 404 `REGISTRATION_NOT_FOUND`；已取消資格拋 409 `TEAM_ALREADY_DISQUALIFIED`；
    對手尚未確定拋 409 `DISQUALIFY_OPPONENT_PENDING`；報名不能轉為取消資格時 registration
    拋 409 `REGISTRATION_INVALID_TRANSITION`；任何拒絕都不改資料。不 commit（AD-5）。

    呼叫端須在同一交易把 `affected_match_ids` 每一場未結案的申訴結案（competition 不碰
    disputes 的資料表）。`affected_match_ids` 只含直接改動的場次，不含之後晉級推進連帶
    確認的場次；之後要通知時從事件或操作紀錄取得。
    """
    return disqualification.disqualify(
        session, tournament_id=tournament_id, team_id=team_id, actor_id=actor_id
    )
