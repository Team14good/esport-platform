"""competition 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import logging
import secrets
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.core import audit, authz, clock, events
from app.core.errors import BusinessError
from app.modules.competition import bracket as bracket_rules
from app.modules.competition import checkin as checkin_rules
from app.modules.competition import progression, registration_port, repository, scoring
from app.modules.competition import schedule as schedule_rules
from app.modules.competition.models import (
    Bracket,
    BracketDrawn,
    BracketRead,
    CheckIn,
    CheckInRead,
    CheckInStatus,
    CheckInStatusReason,
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
    PublicBracket,
    PublicGame,
    PublicMatch,
    PublicMatchDetail,
    PublicPodium,
    PublicTeamRef,
    PublicTournamentRef,
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
) -> str | None:
    """待定列字串；該方已有隊伍、或確定不會有隊伍時為 None。

    確定不會有隊伍：已確認的 walkover 空缺方，或已取消（voided）場次的空缺方。
    """
    if team_id is not None:
        return None
    if match.status == MatchStatus.VOIDED:
        return None
    if match.status == MatchStatus.CONFIRMED and match.outcome == MatchOutcome.WALKOVER:
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


def draw(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    actor_id: uuid.UUID,
    rng: bracket_rules.Shuffler | None = None,
) -> BracketRead:
    """抽籤：產生對戰表與全部場次、排定時間、設定棄權期限，賽事轉為已公布。

    全部在呼叫端的同一個交易裡完成；任何一步拋錯時呼叫端不 commit，
    什麼都不會寫入。`rng` 只供測試注入，正式環境用 `secrets.SystemRandom()`。
    """
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    authz.ensure_tournament_owner(tournament, actor_id)
    if repository.get_bracket_by_tournament(session, tournament_id) is not None:
        raise BusinessError(
            "BRACKET_ALREADY_DRAWN", "這場賽事已經抽過籤了。", status_code=409
        )
    if tournament.status not in _DRAWABLE:
        raise BusinessError(
            "TOURNAMENT_NOT_DRAWABLE",
            "賽事目前的狀態不能抽籤。",
            status_code=409,
        )
    if tournament.start_at <= clock.now():
        raise BusinessError(
            "TOURNAMENT_START_PASSED", "開賽時間已過，無法抽籤", status_code=409
        )
    if tournament.status == TournamentStatus.OPEN:
        registration_port.finalize_for_draw(
            session, tournament_id=tournament_id, actor_id=actor_id
        )
    team_ids = registration_port.list_accepted_teams(
        session, tournament_id=tournament_id
    )
    if len(team_ids) < 2:
        raise BusinessError(
            "NOT_ENOUGH_TEAMS", "正取不足 2 隊，無法抽籤", status_code=409
        )

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
                source_a=_source(match, planned, "a", match.team_a_id),
                source_b=_source(match, planned, "b", match.team_b_id),
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
        appeal_deadline=match.appeal_deadline
        if match.status in _APPEAL_STATUSES
        else None,
        updated_at=max(m.updated_at for m in round_matches),
        check_in_a_at=check_in_at.get(match.team_a_id) if match.team_a_id else None,
        check_in_b_at=check_in_at.get(match.team_b_id) if match.team_b_id else None,
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
    """
    now = clock.now()
    skipped: set[uuid.UUID] = set()
    while True:
        match_id = repository.find_expired_appeal_id(
            session, now, exclude_tournaments=skipped
        )
        if match_id is None:
            return False
        candidate = repository.get_match(session, match_id)
        assert candidate is not None  # 剛查到的 id
        status = tournaments_service.get_tournament(
            session, tournament_id=candidate.tournament_id
        ).status
        if status not in _ENDED:
            break
        skipped.add(candidate.tournament_id)

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
    confirm_match(
        session,
        match=match,
        outcome=MatchOutcome(match.outcome),
        winner_id=match.winner_id,
        actor_id=None,
    )
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
    """待開打、棄權期限已到（`forfeit_deadline <= now`）、且不是兩隊都已報到的場次 id。"""
    return repository.find_forfeit_due(session, now)


def start_due_tournament(session: Session) -> bool:
    """worker 用：把一場賽程已公布、最早場次報到開放時間已到的賽事轉為進行中。

    先找候選對戰表，鎖賽事後重新檢查；賽事不是賽程已公布（已進行、已取消、已結束）
    就只標記為已處理、不做其他事。重複執行沒有副作用。回傳 True 代表處理了一個對戰表
    （轉為進行中或標記略過），worker 會再呼叫一次；沒有候選、或鎖住後發現還沒到開始時間
    （期間被改期）回傳 False。
    """
    now = clock.now()
    bracket_id = repository.find_unstarted_bracket_id(
        session, now + checkin_rules.CHECK_IN_LEAD
    )
    if bracket_id is None:
        return False
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
        return False  # 鎖住前場次被改期，還沒到；回傳 False 避免同一輪重複選到
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
        if reason == "no_valid_time":
            message = (
                f"這場目前沒有可選的時間（最早 {_taipei_text(window.earliest)}）。"
            )
        else:
            message = f"新時間不在允許範圍內，可選 {_range_text(window)}。"
        raise BusinessError(_RESCHEDULE_CODES[reason], message, status_code=409)

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
    result = []
    for match, public in zip(matches, public_matches, strict=True):
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
            )
        )
    return result
