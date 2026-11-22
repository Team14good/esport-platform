"""抽籤後退賽與候補遞補（Story 4.5），以及 6.5 取消資格接上同一套遞補。

隊長在 S17 退賽：先 `lock_tournament`、再依 id 遞增鎖住對戰表全部場次（AD-6），在鎖內
確認隊伍的第一場仍待開打且沒有人報到後，才開始寫入（任何拒絕都不改資料）：

1. registration 把報名轉「退賽」（操作者為隊長），讓退賽隊的學校名額先釋出。
2. registration 取候補第 1 位（轉「已參賽」、操作者為系統）。
3. 有候補：遞補隊接手同一個位置；兩隊確定時重設棄權期限並通知對手。
   沒有候補：移出退賽隊，該場以 `walkover` 確認、對手晉級。

可退賽的條件：該隊沒有任何已確認的場次，且唯一未結束的場次是 `scheduled`
（輪空入座的隊伍，第一場就是第二輪那一場）。輪空隊伍的對手未定又沒有候補時拒絕：
移出後那一方永遠不會有隊伍，`progression` 沒有「這一方不會有隊伍」的標記（見
`disqualification.py` 的說明），所以要等對手確定。

6.5 取消資格（`disqualify`）：隊伍符合同樣的條件（沒有已確認場次、唯一未結束的場次待開打）
時改走這裡的遞補：有候補就接手位置（含刪除被取消隊伍的報到）；沒有候補維持 6.5 現狀，
以 `disqualified` 判對手獲勝並晉級；對手未定又沒有候補維持 409
`DISQUALIFY_OPPONENT_PENDING`。其他情況（第一場已開打、已贏過、抽籤前、不在對戰表）一律
交給 `disqualification.disqualify`。
"""

import uuid
from dataclasses import dataclass

from sqlmodel import Session

from app.core import audit, clock, events
from app.core.errors import BusinessError
from app.modules.competition import (
    disqualification,
    registration_port,
    repository,
    service,
)
from app.modules.competition.bracket import Side
from app.modules.competition.models import (
    BracketBackfilled,
    DisqualifyResult,
    Match,
    MatchOpponentsDecided,
    MatchOutcome,
    MatchStatus,
    OpponentRetired,
    RetirementStatus,
    RetireResult,
)
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.models import TournamentRead, TournamentStatus

_SETTLED = frozenset({MatchStatus.CONFIRMED, MatchStatus.VOIDED})
_RETIRABLE_TOURNAMENT = frozenset(
    {TournamentStatus.PUBLISHED, TournamentStatus.ONGOING}
)
_OPPONENT_PENDING_MESSAGE = "對手確定後才能退賽。"


class _NotRetirable(BusinessError):
    """409 `TEAM_NOT_RETIRABLE`；`show` 為真時 S17 仍顯示停用的按鈕與原因。"""

    def __init__(self, message: str, *, show: bool = False) -> None:
        super().__init__("TEAM_NOT_RETIRABLE", message, status_code=409)
        self.show = show


@dataclass(frozen=True)
class _Target:
    """隊伍唯一未結束、待開打的場次，與它所在的一方、對手（未定為 None）。"""

    match: Match
    side: Side
    opponent: uuid.UUID | None


def _other(side: Side) -> Side:
    return "b" if side == "a" else "a"


def _team(match: Match, side: Side) -> uuid.UUID | None:
    return match.team_a_id if side == "a" else match.team_b_id


def _locate(matches: list[Match], team_id: uuid.UUID) -> _Target | str:
    """找出可退賽的場次；不符合時回傳原因（給退賽的錯誤訊息，6.5 只看有沒有）。"""
    own = [m for m in matches if team_id in (m.team_a_id, m.team_b_id)]
    if not own:
        return "這支隊伍不在對戰表上，無法退賽。"
    if any(m.status == MatchStatus.CONFIRMED for m in own):
        return "隊伍已有比賽結果，無法退賽。"
    pending = [m for m in own if m.status not in _SETTLED]
    if len(pending) != 1:
        return "找不到隊伍待開打的場次，無法退賽。"
    match = pending[0]
    if match.status != MatchStatus.SCHEDULED:
        return "比賽已經開始，無法退賽。"
    side: Side = "a" if match.team_a_id == team_id else "b"
    return _Target(match, side, _team(match, _other(side)))


def _has_check_in(session: Session, match: Match) -> bool:
    teams = (match.team_a_id, match.team_b_id)
    return any(c.team_id in teams for c in repository.list_check_ins(session, match.id))


def _assess_retirement(
    session: Session,
    *,
    tournament: TournamentRead,
    matches: list[Match],
    team_id: uuid.UUID,
) -> _Target:
    """可退賽時回傳目標場次，否則拋 `_NotRetirable`；只讀（鎖與否由呼叫端決定）。"""
    if tournament.status not in _RETIRABLE_TOURNAMENT:
        raise _NotRetirable("賽事目前不能退賽。")
    state = registration_port.get_registration_state(session, team_id=team_id)
    if state.status != "drawn":
        raise _NotRetirable("只有已參賽的隊伍可以退賽。")
    located = _locate(matches, team_id)
    if isinstance(located, str):
        raise _NotRetirable(located)
    if _has_check_in(session, located.match):
        raise _NotRetirable("已有隊伍報到，無法退賽。")
    if located.opponent is None and not registration_port.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=team_id
    ):
        raise _NotRetirable(_OPPONENT_PENDING_MESSAGE, show=True)
    return located


def _opponent_pending() -> BusinessError:
    return BusinessError(
        "DISQUALIFY_OPPONENT_PENDING",
        "對手尚未確定，請等對手確定後再取消資格。",
        status_code=409,
    )


def _ensure_member(
    session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    if not registration_port.is_member(session, team_id=team_id, account_id=account_id):
        raise BusinessError(
            "TEAM_MEMBER_REQUIRED", "只有隊員可以操作這支隊伍。", status_code=403
        )


def _captain_required() -> BusinessError:
    return BusinessError("TEAM_CAPTAIN_REQUIRED", "只有隊長可以退賽。", status_code=403)


def get_retirement_status(
    session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
) -> RetirementStatus:
    """S17：登入者能不能替這支隊伍退賽；只讀、不鎖（真正的判斷在 `retire_team` 的鎖內重做）。

    非隊員 403 `TEAM_MEMBER_REQUIRED`、隊伍不存在 404 `TEAM_NOT_FOUND`；非隊長、尚未抽籤、
    不符合條件時回 `retirable=False`（只有「對手未定、沒有候補」帶 `reason`）。
    """
    tournament_id = registration_port.get_team_tournament_id(session, team_id=team_id)
    _ensure_member(session, team_id=team_id, account_id=account_id)
    if not registration_port.is_captain(
        session, team_id=team_id, account_id=account_id
    ):
        return RetirementStatus(retirable=False)
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        return RetirementStatus(retirable=False)
    tournament = tournaments_service.get_tournament(
        session, tournament_id=tournament_id
    )
    try:
        _assess_retirement(
            session,
            tournament=tournament,
            matches=repository.list_matches(session, bracket.id, fresh=True),
            team_id=team_id,
        )
    except _NotRetirable as error:
        return RetirementStatus(
            retirable=False, reason=error.message if error.show else None
        )
    return RetirementStatus(retirable=True)


def _record_teams(
    session: Session,
    *,
    match: Match,
    before: tuple[uuid.UUID | None, uuid.UUID | None],
    actor_id: uuid.UUID,
    extra: dict[str, uuid.UUID],
) -> None:
    audit.record(
        session,
        actor_id=actor_id,
        tournament_id=match.tournament_id,
        action="match.teams_changed",
        entity_type="match",
        entity_id=match.id,
        before={"team_a_id": before[0], "team_b_id": before[1]},
        after={"team_a_id": match.team_a_id, "team_b_id": match.team_b_id, **extra},
    )


def _backfill(
    session: Session,
    *,
    target: _Target,
    leaving_team_id: uuid.UUID,
    replacement: uuid.UUID,
    actor_id: uuid.UUID,
    audit_key: str,
) -> None:
    """遞補隊接手 `target` 的位置：換隊、紀錄、收回衝突的裁判、兩隊確定時重設棄權期限。"""
    match = target.match
    before = (match.team_a_id, match.team_b_id)
    # 離開的隊伍若已報到（只有 6.5 會發生），一併刪除，否則棄權判定會看到不屬於這場的報到
    repository.delete_check_in(session, match.id, leaving_team_id)
    repository.set_match_team(session, match, target.side, replacement, clock.now())
    _record_teams(
        session,
        match=match,
        before=before,
        actor_id=actor_id,
        extra={audit_key: leaving_team_id},
    )
    service.unassign_referee_if_member(session, match=match)
    if match.team_a_id is not None and match.team_b_id is not None:
        service.start_forfeit_clock(session, match=match)
        events.publish(session, MatchOpponentsDecided(match_id=match.id))
    events.publish(
        session,
        BracketBackfilled(
            match_id=match.id, team_id=replacement, replaced_team_id=leaving_team_id
        ),
    )


def retire_team(
    session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
) -> RetireResult:
    """隊長替隊伍退賽，見模組說明；不 commit（AD-5）。

    404 `TEAM_NOT_FOUND`、403 `TEAM_MEMBER_REQUIRED`／`TEAM_CAPTAIN_REQUIRED`、409
    `TEAM_NOT_RETIRABLE`（賽事不在公布／進行中、尚未抽籤、報名不是已參賽、已有比賽結果、
    第一場已開始、已有隊伍報到、對手未定又沒有候補）；任何拒絕都不改資料。
    """
    tournament_id = registration_port.get_team_tournament_id(session, team_id=team_id)
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    _ensure_member(session, team_id=team_id, account_id=account_id)
    if not registration_port.is_captain(
        session, team_id=team_id, account_id=account_id
    ):
        raise _captain_required()
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    if bracket is None:
        raise _NotRetirable("尚未抽籤，無法退賽。")
    matches = repository.lock_bracket_matches(session, bracket.id)
    target = _assess_retirement(
        session, tournament=tournament, matches=matches, team_id=team_id
    )

    registration_port.retire_registration(session, team_id=team_id, actor_id=account_id)
    replacement = registration_port.backfill_drawn_from_waitlist(
        session, tournament_id=tournament_id
    )
    match = target.match
    if replacement is not None:
        _backfill(
            session,
            target=target,
            leaving_team_id=team_id,
            replacement=replacement,
            actor_id=account_id,
            audit_key="retired_team_id",
        )
        return RetireResult(match_id=match.id, replacement_team_id=replacement)

    # 沒有候補：對手一定已確定（`_assess_retirement` 預先確認過）；預估與實際不一致時拒絕，
    # 由 router 回滾整個交易
    if target.opponent is None:
        raise _NotRetirable(_OPPONENT_PENDING_MESSAGE, show=True)
    before = (match.team_a_id, match.team_b_id)
    repository.clear_match_team(session, match, target.side, clock.now())
    _record_teams(
        session,
        match=match,
        before=before,
        actor_id=account_id,
        extra={"retired_team_id": team_id},
    )
    service.confirm_walkover(session, match=match)
    events.publish(
        session, OpponentRetired(match_id=match.id, winner_id=target.opponent)
    )
    return RetireResult(match_id=match.id, replacement_team_id=None)


def disqualify(
    session: Session,
    *,
    tournament_id: uuid.UUID,
    team_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> DisqualifyResult:
    """見 `service.disqualify`：第一場待開打的隊伍接上遞補，其他情況交給 `disqualification`。"""
    tournament = tournaments_service.lock_tournament(
        session, tournament_id=tournament_id
    )
    if tournament.status in (TournamentStatus.FINISHED, TournamentStatus.CANCELLED):
        return disqualification.disqualify(
            session, tournament_id=tournament_id, team_id=team_id, actor_id=actor_id
        )
    state = registration_port.get_registration_state(session, team_id=team_id)
    bracket = repository.get_bracket_by_tournament(session, tournament_id)
    target: _Target | str = "尚未抽籤"
    if (
        state.tournament_id == tournament_id
        and not state.disqualified
        and bracket is not None
    ):
        target = _locate(repository.lock_bracket_matches(session, bracket.id), team_id)
    if isinstance(target, str):
        return disqualification.disqualify(
            session, tournament_id=tournament_id, team_id=team_id, actor_id=actor_id
        )

    has_candidate = registration_port.has_backfill_candidate(
        session, tournament_id=tournament_id, leaving_team_id=team_id
    )
    if target.opponent is None and not has_candidate:
        raise _opponent_pending()
    registration_port.disqualify_registration(
        session, team_id=team_id, actor_id=actor_id
    )
    replacement = (
        registration_port.backfill_drawn_from_waitlist(
            session, tournament_id=tournament_id
        )
        if has_candidate
        else None
    )
    match = target.match
    if replacement is not None:
        _backfill(
            session,
            target=target,
            leaving_team_id=team_id,
            replacement=replacement,
            actor_id=actor_id,
            audit_key="disqualified_team_id",
        )
        return DisqualifyResult(
            affected_match_ids=[match.id], replacement_team_id=replacement
        )

    # 沒有候補：與 6.5 現狀相同，以 `disqualified` 判對手獲勝並晉級；預估與實際不一致時
    # 拒絕，由呼叫端回滾整個交易
    if target.opponent is None:
        raise _opponent_pending()
    service._confirm(
        session,
        match=match,
        outcome=MatchOutcome.DISQUALIFIED,
        winner_id=target.opponent,
        actor_id=actor_id,
    )
    service.advance(session, match=match)
    return DisqualifyResult(affected_match_ids=[match.id], replacement_team_id=None)
