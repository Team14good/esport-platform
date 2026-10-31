"""晉級推進規則（純函式，不碰資料庫、只 import competition 的純模組（bracket、models）、
不讀時鐘、不發事件）。

`advance(plan, states, code)` 在某場確認後回傳依序要套用的變更清單；
`podium(plan, states)` 判定名次。第二階段的 service 在交易內鎖定後依清單寫入資料表，
裁判衝突（填入的隊伍有被指派的裁判）也由 service 依回傳的 `FillSlot` 處理。

FR-22 的取消資格頂替（替換已入座的隊伍）由 6.5 的 service 負責：先在原位置換隊伍，
再呼叫 `advance`；`advance` 本身絕不覆寫已填入的位置。
"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, replace

from app.modules.competition.bracket import BracketPlan, PlannedMatch, Side
from app.modules.competition.models import MatchOutcome, MatchStatus

# 只有正常完賽與一方棄權有敗隊；雙方棄權、輪空、取消資格都沒有（被取消資格的隊伍不晉級也不進季軍賽）
_HAS_LOSER = frozenset({MatchOutcome.PLAYED, MatchOutcome.FORFEIT})
_WINNER_REQUIRED = frozenset(
    {MatchOutcome.PLAYED, MatchOutcome.FORFEIT, MatchOutcome.DISQUALIFIED}
)
_SETTLED = frozenset({MatchStatus.CONFIRMED, MatchStatus.VOIDED})


@dataclass(frozen=True)
class MatchState[T: Hashable]:
    """某場目前的狀態；隊伍未定時為 None。"""

    team_a: T | None
    team_b: T | None
    status: MatchStatus
    outcome: MatchOutcome | None
    winner: T | None

    def team(self, side: Side) -> T | None:
        return self.team_a if side == "a" else self.team_b

    def loser(self) -> T | None:
        """已確認場次的敗隊；只有 `played`、`forfeit` 有。

        只對已確認的場次有意義；未確認的場次 outcome 為空，一律回 None。
        """
        if self.outcome not in _HAS_LOSER:
            return None
        return self.team_b if self.winner == self.team_a else self.team_a


@dataclass(frozen=True)
class FillSlot[T: Hashable]:
    """把隊伍填入某場的某一方。"""

    code: str
    side: Side
    team: T


@dataclass(frozen=True)
class ConfirmWalkover[T: Hashable]:
    """以 `walkover` 直接確認；`winner` 為 None 表示兩方都確定沒有隊伍。"""

    code: str
    winner: T | None


@dataclass(frozen=True)
class VoidMatch:
    """季軍賽轉為 `voided`（outcome 與勝隊為空）。

    只在任一場準決賽「沒有產生勝隊」時發生（FR-21）；準決賽有勝隊但沒有敗隊
    （輪空、取消資格）時，季軍賽照一般規則以 walkover 處理，不取消。
    已排入季軍賽的隊伍留在原位，只改狀態、outcome 與勝隊。
    """

    code: str


@dataclass(frozen=True)
class StartForfeitClock:
    """本次呼叫填入隊伍後兩方湊齊，由 service 呼叫 `start_forfeit_clock`。

    第 1 輪與輪空直接入座的隊伍由抽籤入座、不經 `advance`，棄權期限在抽籤時起算。
    這也是通知兩隊隊長下一場對手的時機（FR-21）。service 必須在同一個交易內套用整份
    變更清單：只套用一半就重試時，填位已存在、不會再回傳本訊號，起算就會遺失。
    """

    code: str


@dataclass(frozen=True)
class Podium[T: Hashable]:
    """名次；從缺為 None。"""

    champion: T | None
    runner_up: T | None
    third_place: T | None


@dataclass(frozen=True)
class TournamentFinished[T: Hashable]:
    """決賽已確認、季軍賽已確認／已取消／不存在：賽事結束。"""

    podium: Podium[T]


type Change[T: Hashable] = (
    FillSlot[T]
    | ConfirmWalkover[T]
    | VoidMatch
    | StartForfeitClock
    | TournamentFinished[T]
)


def _final(bracket_plan: BracketPlan) -> PlannedMatch:
    return next(
        m
        for m in bracket_plan.matches
        if m.round_no == bracket_plan.rounds and not m.is_third_place
    )


def _third(bracket_plan: BracketPlan) -> PlannedMatch | None:
    return next((m for m in bracket_plan.matches if m.is_third_place), None)


def _check_consistent[T: Hashable](pm: PlannedMatch, st: MatchState[T]) -> None:
    """場次狀態必須自洽，否則推進會誤判成輪空。"""
    code = pm.code
    if st.team_a is not None and st.team_a == st.team_b:
        raise ValueError(f"{code} 兩方是同一隊")
    if st.status == MatchStatus.VOIDED:
        if not pm.is_third_place:
            raise ValueError(f"{code} 不是季軍賽，不會被取消")
        if st.outcome is not None or st.winner is not None:
            raise ValueError(f"{code} 已取消卻有結果或勝隊")
        return
    if st.status != MatchStatus.CONFIRMED:
        return
    teams = {st.team_a, st.team_b} - {None}
    if st.outcome is None:
        raise ValueError(f"{code} 已確認但沒有結果類型")
    if st.outcome in _HAS_LOSER and len(teams) != 2:
        raise ValueError(f"{code} 完賽或棄權卻沒有兩隊")
    if st.outcome in _WINNER_REQUIRED and st.winner not in teams:
        raise ValueError(f"{code} 的勝隊不是兩隊之一")
    if st.outcome == MatchOutcome.DOUBLE_FORFEIT and st.winner is not None:
        raise ValueError(f"{code} 雙方棄權卻有勝隊")
    if st.outcome == MatchOutcome.WALKOVER:
        if len(teams) == 2:
            raise ValueError(f"{code} 兩隊都在卻以輪空確認")
        if st.winner != next(iter(teams), None):
            raise ValueError(f"{code} 的輪空勝隊不是唯一在場的隊伍")


def _validate[T: Hashable](
    bracket_plan: BracketPlan, states: Mapping[str, MatchState[T]]
) -> None:
    """`states` 缺少 plan 的場次或有不自洽的場次時拋 `ValueError`。"""
    missing = [m.code for m in bracket_plan.matches if m.code not in states]
    if missing:
        raise ValueError(f"states 缺少場次：{', '.join(missing)}")
    for m in bracket_plan.matches:
        _check_consistent(m, states[m.code])


def podium[T: Hashable](
    bracket_plan: BracketPlan, states: Mapping[str, MatchState[T]]
) -> Podium[T] | None:
    """賽事未結束時回 None；`states` 缺場次或不自洽時拋 `ValueError`。

    - 冠軍＝決賽勝隊。
    - 亞軍＝決賽的另一隊；決賽是輪空時為冠軍那一側準決賽的敗隊（該側沒有敗隊則從缺）；
      決賽以取消資格確認時從缺（FR-22）。
    - 季軍＝季軍賽勝隊；季軍賽取消（FR-21）或不存在時從缺。
    """
    _validate(bracket_plan, states)
    final_plan = _final(bracket_plan)
    final = states[final_plan.code]
    if final.status != MatchStatus.CONFIRMED:
        return None
    third_plan = _third(bracket_plan)
    third: T | None = None
    if third_plan is not None:
        third_state = states[third_plan.code]
        if third_state.status not in _SETTLED:
            return None
        third = third_state.winner

    champion = final.winner
    runner_up: T | None = None
    if final.outcome == MatchOutcome.WALKOVER:
        if champion is not None:
            side: Side = "a" if champion == final.team_a else "b"
            src = final_plan.source(side)
            if src is not None:
                runner_up = states[src.code].loser()
    else:
        # 取消資格與雙方棄權都沒有敗隊，亞軍從缺
        runner_up = final.loser()
    return Podium(champion, runner_up, third)


def advance[T: Hashable](
    bracket_plan: BracketPlan, states: Mapping[str, MatchState[T]], code: str
) -> list[Change[T]]:
    """`code` 這場確認後，回傳依序要套用的變更。

    連鎖的輪空確認在同一次呼叫內推完。目的場次的每一方都依 plan 的來源重新推導，
    已填入的位置不再填，所以重複呼叫不會產生重複的填位。
    例外：對決賽或季軍賽重複呼叫會再回傳一次 `TournamentFinished`（純函式看不到賽事狀態），
    service 要依賽事狀態只處理一次。

    `code` 不在 plan 裡 → `KeyError`；`states` 缺少 plan 的場次、`code` 尚未確認，
    或有不自洽的場次 → `ValueError`。
    """
    trigger = bracket_plan.match(code)
    _validate(bracket_plan, states)
    if states[code].status != MatchStatus.CONFIRMED:
        raise ValueError(f"{code} 尚未確認")

    work: dict[str, MatchState[T]] = {
        m.code: states[m.code] for m in bracket_plan.matches
    }
    changes: list[Change[T]] = []
    filled: set[str] = set()  # 本次呼叫有填入隊伍的場次
    clocked: set[str] = set()
    touched = {code}  # 本次確認或取消的場次
    queue = [trigger]

    def side_team(pm: PlannedMatch, side: Side) -> tuple[bool, T | None]:
        """回傳（該方是否已定案, 隊伍）；已定案而隊伍為 None ＝確定沒有隊伍。"""
        st = work[pm.code]
        team = st.team(side)
        if team is not None:
            return True, team
        src = pm.source(side)
        if src is None:
            return False, None
        src_state = work[src.code]
        if src_state.status != MatchStatus.CONFIRMED:
            return False, None
        if src.kind == "winner":
            return True, src_state.winner
        return True, src_state.loser()

    def evaluate(pm: PlannedMatch) -> None:
        st = work[pm.code]
        if st.status in _SETTLED:
            return
        if pm.is_third_place:
            semis = [s for s in (pm.source_a, pm.source_b) if s is not None]
            if any(
                work[s.code].status == MatchStatus.CONFIRMED
                and work[s.code].winner is None
                for s in semis
            ):
                changes.append(VoidMatch(pm.code))
                work[pm.code] = replace(
                    st, status=MatchStatus.VOIDED, outcome=None, winner=None
                )
                touched.add(pm.code)
                return

        resolved: dict[Side, tuple[bool, T | None]] = {}
        sides: tuple[Side, Side] = ("a", "b")
        for side in sides:
            done, team = side_team(pm, side)
            if team is not None and st.team(side) is None:
                changes.append(FillSlot(pm.code, side, team))
                st = (
                    replace(st, team_a=team)
                    if side == "a"
                    else replace(st, team_b=team)
                )
                filled.add(pm.code)
            resolved[side] = (done, team)
        work[pm.code] = st

        (done_a, team_a), (done_b, team_b) = resolved["a"], resolved["b"]
        if team_a is not None and team_b is not None:
            if pm.code in filled and pm.code not in clocked:
                changes.append(StartForfeitClock(pm.code))
                clocked.add(pm.code)
            return
        if not (done_a and done_b):
            return
        winner = team_a if team_a is not None else team_b
        changes.append(ConfirmWalkover(pm.code, winner))
        work[pm.code] = replace(
            st,
            status=MatchStatus.CONFIRMED,
            outcome=MatchOutcome.WALKOVER,
            winner=winner,
        )
        touched.add(pm.code)
        queue.append(pm)

    while queue:
        current = queue.pop(0)
        for dest in (current.next_code, current.loser_next_code):
            if dest is not None:
                evaluate(bracket_plan.match(dest))

    final_code = _final(bracket_plan).code
    third_plan = _third(bracket_plan)
    if final_code in touched or (third_plan is not None and third_plan.code in touched):
        result = podium(bracket_plan, work)
        if result is not None:
            changes.append(TournamentFinished(result))
    return changes
