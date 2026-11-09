"""取消資格（Story 6.5 第一階段）：改報名狀態、判對手獲勝或由最近一場輸給它的隊伍頂替。

由 `service.disqualify` 呼叫（之後 disputes 的 `resolve_report` 經這個公開函式使用）。
規則依 epic-6-context〈取消資格（期中版）〉與 spec-6-5 的情況表：

- 抽籤前、已淘汰或沒有下一場：只改報名狀態（抽籤前空出的名額交給 3.4 的分配）。
- 有進行中、申訴期、申訴中的場次：該場以 `disqualified` 判對手獲勝並確認、晉級；不頂替。
- 待開打的場次：
  - 已贏過（依輪次往前第一場不是 walkover 的勝場；它是 `played`／`forfeit` 時取它的
    敗隊，是取消資格勝時不往前找）且敗隊未被取消資格：敗隊頂替原位置；更早的結果不變。頂替時刪除被
    取消資格隊伍在該場的報到，兩隊湊齊則開始計時並發 `MatchOpponentsDecided`。
  - 決賽：頂替的是準決賽的敗隊，它在季軍賽，所以只有季軍賽仍待開打時才頂替，
    由它移到決賽、季軍賽由對手以 walkover 奪季軍；季軍賽已開打或已定案則不頂替。
  - 季軍賽、還沒比過、勝場全是輪空或 walkover、最近一場（略過 walkover）是取消資格勝、
    或敗隊已被取消資格：
    該場以 `disqualified` 判對手獲勝並確認、晉級（兩隊都在場的 walkover 會被
    progression 拒絕，也看不出取消資格）。

鎖的順序（AD-6）：`lock_tournament` → 依 id 遞增鎖住對戰表的全部場次 → 判斷 → 寫入。
全部判斷完成後才寫入，任何拒絕都不改資料。

**對手未定時拒絕**（2026-11-09 D 決定）：對手還沒確定（等另一場的勝隊），需要「把該隊
移出、標記這一方不會有隊伍」的情況，回 409 `DISQUALIFY_OPPONENT_PENDING`、不改任何資料。
`progression.advance` 只依 plan 的來源推導一方是否已定案：輪空直接入座的一方沒有來源、
永遠不會定案；由勝場進來的一方會被重新填回原隊伍，所以沒有不改既有函式的標記方式。
progression 支援「這一方確定不會有隊伍」列在 deferred-work（期中後）。
"""

import uuid
from dataclasses import dataclass

from sqlmodel import Session

from app.core import audit, clock, events
from app.core.errors import BusinessError
from app.modules.competition import registration_port, repository, service
from app.modules.competition.bracket import Side
from app.modules.competition.models import (
    DisqualifyResult,
    Match,
    MatchOpponentsDecided,
    MatchOutcome,
    MatchStatus,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentStatus

# 已開打、結果尚未確認的場次：直接判對手獲勝並確認
_ACTIVE = frozenset({MatchStatus.LIVE, MatchStatus.APPEAL_WINDOW, MatchStatus.APPEALED})
_SETTLED = frozenset({MatchStatus.CONFIRMED, MatchStatus.VOIDED})
# 有敗隊的結果（與 progression 相同）：只有這兩種勝場能找到頂替的隊伍
_HAS_LOSER = frozenset({MatchOutcome.PLAYED, MatchOutcome.FORFEIT})


@dataclass(frozen=True)
class _AwardOpponent:
    """該場以 `disqualified` 判對手獲勝並確認、晉級。"""

    match: Match
    opponent: uuid.UUID


@dataclass(frozen=True)
class _Replace:
    """`replacement` 頂替該場 `side` 的位置。

    決賽頂替時 `third` 是頂替隊伍原本所在的季軍賽（`third_side` 為它的位置），
    移出後季軍賽由對手以 walkover 獲勝。
    """

    match: Match
    side: Side
    replacement: uuid.UUID
    third: Match | None = None
    third_side: Side | None = None


type _Plan = _AwardOpponent | _Replace | None


def _side_of(match: Match, team_id: uuid.UUID) -> Side:
    if match.team_a_id == team_id:
        return "a"
    if match.team_b_id == team_id:
        return "b"
    raise ValueError(f"{match.code} 沒有這支隊伍")


def _other(side: Side) -> Side:
    return "b" if side == "a" else "a"


def _team(match: Match, side: Side) -> uuid.UUID | None:
    return match.team_a_id if side == "a" else match.team_b_id


def _loser(match: Match) -> uuid.UUID | None:
    """已確認場次的敗隊；只有 `played`、`forfeit` 有。"""
    if match.outcome not in _HAS_LOSER:
        return None
    return match.team_b_id if match.winner_id == match.team_a_id else match.team_a_id


def _opponent_pending() -> BusinessError:
    return BusinessError(
        "DISQUALIFY_OPPONENT_PENDING",
        "對手尚未確定，請等對手確定後再取消資格。",
        status_code=409,
    )


def _final_replacement(
    match: Match, side: Side, by_id: dict[uuid.UUID, Match], won_from: Match
) -> _Replace | None:
    """決賽：準決賽的敗隊頂替；它在季軍賽，季軍賽仍待開打才移過來。"""
    loser = _loser(won_from)
    assert loser is not None  # 呼叫端已確認
    if won_from.loser_next_match_id is None:
        # 沒有季軍賽（3 隊）：敗隊已淘汰，直接頂替
        return _Replace(match, side, loser)
    third = by_id[won_from.loser_next_match_id]
    if third.status != MatchStatus.SCHEDULED:
        return None
    third_side = _side_of(third, loser)
    if _team(third, _other(third_side)) is None:
        # 季軍賽的對手（另一場準決賽的敗隊）未定：移出後這一方要標記為不會有隊伍
        raise _opponent_pending()
    return _Replace(match, side, loser, third=third, third_side=third_side)


def _replacement(
    session: Session,
    match: Match,
    side: Side,
    own: list[Match],
    by_id: dict[uuid.UUID, Match],
    team_id: uuid.UUID,
) -> _Replace | None:
    """最近一場輸給它的隊伍；沒有（季軍賽、還沒贏過、只靠輪空或 walkover、最近是取消資格勝、
    敗隊已取消資格）回 None。"""
    if match.is_third_place:
        return None
    wins = [
        m for m in own if m.status == MatchStatus.CONFIRMED and m.winner_id == team_id
    ]
    is_final = match.next_match_id is None
    if is_final:
        # 決賽只看準決賽（勝隊進入決賽的那一場）
        won_from = next((m for m in wins if m.next_match_id == match.id), None)
        if won_from is None or won_from.outcome not in _HAS_LOSER:
            return None
    else:
        # 略過 walkover 勝場往前找；最近一場是取消資格勝（沒有真的打敗對手）時不往前找，
        # 比照「敗隊已取消資格」判對手獲勝（2026-11-09 使用者決定）
        won_from = next(
            (m for m in reversed(wins) if m.outcome != MatchOutcome.WALKOVER), None
        )
        if won_from is None or won_from.outcome not in _HAS_LOSER:
            return None
    loser = _loser(won_from)
    if loser is None:
        return None
    if registration_port.get_registration_state(session, team_id=loser).disqualified:
        return None
    if is_final:
        return _final_replacement(match, side, by_id, won_from)
    return _Replace(match, side, loser)


def _plan(session: Session, matches: list[Match], team_id: uuid.UUID) -> _Plan:
    """只讀已鎖住的場次與 registration，決定要做什麼；不寫入。"""
    by_id = {m.id: m for m in matches}
    own = sorted(
        (m for m in matches if team_id in (m.team_a_id, m.team_b_id)),
        key=lambda m: (m.round_no, m.is_third_place, m.slot_no),
    )
    pending = [m for m in own if m.status not in _SETTLED]
    if not pending:
        return None
    if len(pending) > 1:
        codes = "、".join(m.code for m in pending)
        raise ValueError(f"同一隊有多場未結束的場次：{codes}")
    match = pending[0]
    side = _side_of(match, team_id)
    opponent = _team(match, _other(side))
    if match.status in _ACTIVE:
        if opponent is None:
            raise ValueError(f"{match.code} 已開打卻只有一隊")
        return _AwardOpponent(match, opponent)
    replace = _replacement(session, match, side, own, by_id, team_id)
    if replace is not None:
        return replace
    if opponent is None:
        raise _opponent_pending()
    return _AwardOpponent(match, opponent)


def _record_teams(
    session: Session,
    *,
    match: Match,
    before: tuple[uuid.UUID | None, uuid.UUID | None],
    team_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action="match.teams_changed",
        entity_type="match",
        entity_id=match.id,
        before={"team_a_id": before[0], "team_b_id": before[1]},
        after={
            "team_a_id": match.team_a_id,
            "team_b_id": match.team_b_id,
            "disqualified_team_id": team_id,
        },
    )


def _award(
    session: Session, *, plan: _AwardOpponent, actor_id: uuid.UUID
) -> DisqualifyResult:
    match = plan.match
    if match.status in _ACTIVE:
        service.confirm_match(
            session,
            match=match,
            outcome=MatchOutcome.DISQUALIFIED,
            winner_id=plan.opponent,
            actor_id=actor_id,
        )
    else:
        # 待開打：`confirm_match` 只接受已開打的場次，改走 scheduled → confirmed
        service._confirm(
            session,
            match=match,
            outcome=MatchOutcome.DISQUALIFIED,
            winner_id=plan.opponent,
            actor_id=actor_id,
        )
        service.advance(session, match=match)
    return DisqualifyResult(affected_match_ids=[match.id], replacement_team_id=None)


def _replace(
    session: Session, *, plan: _Replace, team_id: uuid.UUID, actor_id: uuid.UUID
) -> DisqualifyResult:
    match = plan.match
    before = (match.team_a_id, match.team_b_id)
    # 被取消資格的隊伍若已報到，移出場次時一併刪除，否則棄權判定會看到不屬於這場的報到
    repository.delete_check_in(session, match.id, team_id)
    repository.set_match_team(session, match, plan.side, plan.replacement, clock.now())
    _record_teams(
        session, match=match, before=before, team_id=team_id, actor_id=actor_id
    )
    affected = [match.id]
    third = plan.third
    if third is not None:
        assert plan.third_side is not None
        third_before = (third.team_a_id, third.team_b_id)
        repository.delete_check_in(session, third.id, plan.replacement)
        repository.clear_match_team(session, third, plan.third_side, clock.now())
        _record_teams(
            session,
            match=third,
            before=third_before,
            team_id=team_id,
            actor_id=actor_id,
        )
        affected.append(third.id)

    service.unassign_referee_if_member(session, match=match)
    if match.team_a_id is not None and match.team_b_id is not None:
        # 與 `advance` 的填位相同：開始計時並通知兩隊隊長新的對手
        service.start_forfeit_clock(session, match=match)
        events.publish(session, MatchOpponentsDecided(match_id=match.id))
    if third is not None:
        # 季軍賽只剩對手：以 walkover 奪季軍（操作者為系統，與 advance 的輪空確認相同）
        service.confirm_walkover(session, match=third)
    return DisqualifyResult(
        affected_match_ids=affected, replacement_team_id=plan.replacement
    )


def disqualify(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    team_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> DisqualifyResult:
    """見 `service.disqualify`。"""
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    if tournament.status == TournamentStatus.FINISHED:
        raise BusinessError(
            "TOURNAMENT_FINISHED", "賽事已結束，不能取消資格。", status_code=409
        )
    if tournament.status == TournamentStatus.CANCELLED:
        raise BusinessError(
            "TOURNAMENT_CANCELLED", "賽事已取消，不能取消資格。", status_code=409
        )
    state = registration_port.get_registration_state(session, team_id=team_id)
    if state.tournament_id != tournament_id:
        raise BusinessError(
            "REGISTRATION_NOT_FOUND", "找不到這支隊伍的報名。", status_code=404
        )
    if state.disqualified:
        raise BusinessError(
            "TEAM_ALREADY_DISQUALIFIED", "這支隊伍已被取消資格。", status_code=409
        )

    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    matches = (
        repository.lock_bracket_matches(session, bracket.id)
        if bracket is not None
        else []
    )
    plan = _plan(session, matches, team_id)

    registration_port.disqualify_registration(
        session, team_id=team_id, actor_id=actor_id
    )
    match plan:
        case None:
            return DisqualifyResult(affected_match_ids=[], replacement_team_id=None)
        case _AwardOpponent():
            return _award(session, plan=plan, actor_id=actor_id)
        case _Replace():
            return _replace(session, plan=plan, team_id=team_id, actor_id=actor_id)
