"""申訴相關的場次操作（Story 6.1、6.2，B 實作、D 審查）。

disputes 經 `service.py` 的公開函式呼叫這裡（CONTRIBUTING 6.6：competition 的既有函式
不修改，新邏輯放在新增的檔案）。呼叫端先 `lock_tournament`，這裡再 `lock_match`，
以鎖住後的狀態判斷（AD-6）。不 commit（AD-5）。
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlmodel import Session

from app.core import audit, clock, events
from app.core.errors import BusinessError
from app.modules.competition import repository, scoring, service
from app.modules.competition.models import (
    CorrectionResult,
    GameScoreIn,
    Match,
    MatchGame,
    MatchOutcome,
    MatchRead,
    MatchRescheduled,
    MatchStatus,
    ReplayCleared,
)
from app.modules.tournaments import service as tournaments_service


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


def _locked_appealed(
    session: Session, match_id: uuid.UUID
) -> tuple[Match, MatchOutcome]:
    """`lock_match` 後確認是申訴中；其他狀態拋 409 `MATCH_INVALID_TRANSITION`、不改資料。

    回傳鎖住的場次與已寫入的 outcome（申訴中一定有）。
    """
    match = service.lock_match(session, match_id=match_id)
    if MatchStatus(match.status) != MatchStatus.APPEALED or match.outcome is None:
        raise BusinessError(
            "MATCH_INVALID_TRANSITION",
            "場次目前的狀態不能進行這個操作。",
            status_code=409,
        )
    return match, MatchOutcome(match.outcome)


def uphold_result(
    session: Session, *, match_id: uuid.UUID, actor_id: uuid.UUID
) -> MatchRead:
    """維持原結果：沿用已寫入的 outcome、勝隊確認並晉級（`confirm_match`）。

    只接受申訴中；其他狀態拋 409 `MATCH_INVALID_TRANSITION`、不改資料。
    """
    match, outcome = _locked_appealed(session, match_id)
    service.confirm_match(
        session,
        match=match,
        outcome=outcome,
        winner_id=match.winner_id,
        actor_id=actor_id,
    )
    return service.get_match(session, match_id=match_id)


def _check_games(
    session: Session, *, match: Match, games: Sequence[GameScoreIn]
) -> tuple[list[scoring.GameResult], scoring.Series]:
    """以 5.3 的規則驗證整組新的各局，並套用 5.4 送出時的檢查（已分勝負、沒有多餘的局）。"""
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    bo = service._bo(session, match)
    needed = scoring.wins_needed(bo)
    results: list[scoring.GameResult] = []
    for game in games:
        result = scoring.make_game(
            tournament.score_type.value,
            winner=game.winner_side,
            score_a=game.score_a,
            score_b=game.score_b,
        )
        if not isinstance(result, scoring.GameResult):
            raise service._score_rejection(result, wins_needed=needed)
        results.append(result)
    series = scoring.series(results, bo=bo)
    if series.winner is None:
        raise service._score_rejection(
            series.reason or "not_decided", wins_needed=series.wins_needed
        )
    return results, series


def correct_result(
    session: Session,
    *,
    match_id: uuid.UUID,
    games: Sequence[GameScoreIn],
    actor_id: uuid.UUID,
) -> CorrectionResult:
    """更正結果：整份替換各局、重算勝局數與勝隊，再確認並晉級（`confirm_match`）。

    順序：`lock_match` → 申訴中（否則 409 `MATCH_INVALID_TRANSITION`）→ `outcome=played`
    （否則 409 `CORRECTION_ONLY_FOR_PLAYED`）→ 各局以 5.3 的規則驗證（`SCORE_TIE`、
    `SCORE_INVALID`）→ 已分勝負（409 `SERIES_NOT_DECIDED`）、沒有多餘的局（409
    `REDUNDANT_GAMES`）。任何拒絕都不改資料。前後各局由 disputes 的 `appeal.resolved`
    記錄；這裡只有 `confirm_match` 寫的 `match.confirmed`。
    """
    match, outcome = _locked_appealed(session, match_id)
    if outcome != MatchOutcome.PLAYED:
        raise BusinessError(
            "CORRECTION_ONLY_FOR_PLAYED",
            "只有正常完賽的場次可以更正結果。",
            status_code=409,
        )
    results, series = _check_games(session, match=match, games=games)
    winner_id = match.team_a_id if series.winner == "a" else match.team_b_id
    assert winner_id is not None  # 已送出結果的場次兩隊都確定

    before = [service._public_game(g) for g in repository.list_games(session, match.id)]
    now = clock.now()
    repository.delete_games(session, match.id)
    for game_no, result in enumerate(results, start=1):
        repository.add_game(
            session,
            MatchGame(
                match_id=match.id,
                game_no=game_no,
                winner_side=result.winner,
                score_a=result.score_a,
                score_b=result.score_b,
                recorded_by=actor_id,
                recorded_at=now,
            ),
        )
    repository.set_match_wins(session, match, series.wins_a, series.wins_b, now)
    # 勝隊由 confirm_match 一併寫入
    service.confirm_match(
        session,
        match=match,
        outcome=MatchOutcome.PLAYED,
        winner_id=winner_id,
        actor_id=actor_id,
    )
    after = [service._public_game(g) for g in repository.list_games(session, match.id)]
    return CorrectionResult(before_games=before, after_games=after, winner_id=winner_id)


def replay_match(
    session: Session,
    *,
    match_id: uuid.UUID,
    scheduled_at: datetime,
    actor_id: uuid.UUID,
) -> ReplayCleared:
    """重新比賽：只用於判棄權（一方或雙方）的申訴中場次；全部在呼叫端的同一個交易內。

    順序：`lock_match` → 申訴中（否則 409 `MATCH_INVALID_TRANSITION`）→ outcome 為
    `forfeit`／`double_forfeit`（否則 409 `REPLAY_ONLY_FOR_FORFEIT`）→ 賽事為賽程已公布
    或進行中（否則 409 `TOURNAMENT_NOT_RESCHEDULABLE`，與 `get_replay_window` 一致）→
    `check_replay_time`（`RESCHEDULE_*` 409）→ `clear_for_replay` → 轉回待開打 → 寫入
    新時間 → `start_forfeit_clock` → 操作紀錄 `match.replay_scheduled` → 發
    `MatchRescheduled`。裁判保留。回傳清除前的內容。
    """
    match, outcome = _locked_appealed(session, match_id)
    # 與 `get_replay_window` 共用同一份可重賽的 outcome
    if outcome not in service.REPLAYABLE_OUTCOMES:
        raise BusinessError(
            "REPLAY_ONLY_FOR_FORFEIT",
            "只有判棄權的場次可以重新比賽。",
            status_code=409,
        )
    tournament = tournaments_service.get_tournament(
        session, tournament_id=match.tournament_id
    )
    if tournament.status not in service._RESCHEDULABLE_TOURNAMENT:
        code, message = service._RESCHEDULE_BLOCKS["tournament_not_reschedulable"]
        raise BusinessError(code, message, status_code=409)
    service.check_replay_time(
        session, tournament=tournament, match=match, scheduled_at=scheduled_at
    )
    before_at = match.scheduled_at
    cleared = service.clear_for_replay(session, match=match)
    service.transition_match(session, match=match, to=MatchStatus.SCHEDULED)
    repository.set_scheduled_at(
        session, match, scheduled_at.astimezone(UTC), clock.now()
    )
    service.start_forfeit_clock(session, match=match)
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action="match.replay_scheduled",
        entity_type="match",
        entity_id=match.id,
        before={
            **cleared.model_dump(),
            "status": MatchStatus.APPEALED.value,
            "scheduled_at": before_at,
        },
        after={
            "status": MatchStatus.SCHEDULED.value,
            "scheduled_at": match.scheduled_at,
            "forfeit_deadline": match.forfeit_deadline,
        },
    )
    events.publish(
        session, MatchRescheduled(match_id=match.id, scheduled_at=match.scheduled_at)
    )
    return cleared
