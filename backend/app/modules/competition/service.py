"""competition 的業務規則、資源層級權限、狀態轉換、操作紀錄與事件；不得 commit 或 rollback。"""

import secrets
import uuid
from datetime import datetime

from sqlmodel import Session

from app.core import audit, authz, clock, events
from app.core.errors import BusinessError
from app.modules.competition import bracket as bracket_rules
from app.modules.competition import registration_port, repository
from app.modules.competition import schedule as schedule_rules
from app.modules.competition.models import (
    Bracket,
    BracketDrawn,
    BracketRead,
    Match,
    MatchOutcome,
    MatchRead,
    MatchStatus,
    PublicBracket,
    PublicMatch,
    PublicTeamRef,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus

# 可以抽籤的賽事狀態：開放報名中（提前抽籤）、報名截止
_DRAWABLE = frozenset({TournamentStatus.OPEN, TournamentStatus.CLOSED})

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


def get_public_bracket(
    session: Session, *, tournament_id: uuid.UUID
) -> PublicBracket | None:
    """公開對戰樹（AD-19）：隊伍只有 `{id, name}`；尚未抽籤回 None。"""
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        return None
    matches = repository.list_matches(session, bracket.id)
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
        updated_at=updated_at,
    )


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
