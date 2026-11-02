"""單淘汰對戰表產生器（純函式，不碰資料庫、不 import 其他模組、不讀時鐘）。

`plan(team_count)` 只由隊數決定結構；`assign(team_ids, plan, rng)` 以呼叫端注入的
亂數排定對位（正式環境傳入 `secrets.SystemRandom()`）。
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Side = Literal["a", "b"]
SourceKind = Literal["winner", "loser"]

_KIND_LABEL: dict[SourceKind, str] = {"winner": "勝者", "loser": "敗者"}


class Shuffler(Protocol):
    """`random.Random` 與 `secrets.SystemRandom` 都符合。"""

    def shuffle(self, x: list[Any], /) -> None: ...


@dataclass(frozen=True)
class MatchSource:
    """某一方的隊伍來自哪一場的勝者或敗者。"""

    code: str
    kind: SourceKind


@dataclass(frozen=True)
class PlannedMatch:
    code: str  # "M3"
    round_no: int  # 1 起算；季軍賽與決賽同輪
    slot_no: int  # 該輪位置 + 1；第一輪輪空的位置留空號；季軍賽排在決賽之後
    is_third_place: bool
    next_code: str | None  # 勝隊進入的場次；決賽與季軍賽為 None
    next_side: Side | None
    loser_next_code: str | None  # 只有準決賽有：敗隊進入季軍賽
    source_a: MatchSource | None  # 待定來源；第一輪與輪空直接入座的一方為 None
    source_b: MatchSource | None
    bye_a: bool  # 該方由輪空直接進入本場
    bye_b: bool

    def source(self, side: Side) -> MatchSource | None:
        return self.source_a if side == "a" else self.source_b


@dataclass(frozen=True)
class BracketPlan:
    team_count: int
    size: int  # P
    rounds: int
    bye_count: int
    has_third_place: bool
    matches: tuple[PlannedMatch, ...]  # 依編號順序，季軍賽在最後

    def match(self, code: str) -> PlannedMatch:
        for m in self.matches:
            if m.code == code:
                return m
        raise KeyError(code)


@dataclass(frozen=True)
class AssignedMatch[T: Hashable]:
    match: PlannedMatch
    team_a_id: T | None  # 未確定時為 None
    team_b_id: T | None


def _bit_reverse_order(count: int) -> list[int]:
    """0…count-1（count 為 2 的次方）依位元反轉排序，讓輪空交替落在上、下半區。"""
    bits = count.bit_length() - 1
    return sorted(
        range(count),
        key=lambda x: int(format(x, f"0{bits}b")[::-1], 2) if bits else 0,
    )


def _bye_pairs(size: int, bye_count: int) -> list[int]:
    """回傳第一輪輪空對的編號（第 k 對＝座位 2k、2k+1）。"""
    if bye_count == 0:
        return []
    quarter = size // 4  # 第二輪場次數；bye_count > 0 時 size ≥ 4
    order = _bit_reverse_order(quarter)
    upper = order[: min(bye_count, quarter)]
    lower = order[: bye_count - quarter] if bye_count > quarter else []
    return [2 * j for j in upper] + [2 * j + 1 for j in lower]


def round_name(round_no: int, rounds: int) -> str:
    """輪次欄的名稱：決賽、4 強、8 強、16 強…

    季軍賽與決賽同輪，但季軍賽一律顯示「季軍賽」，不可用這個函式命名。
    """
    if not 1 <= round_no <= rounds:
        raise ValueError("round_no 超出範圍")
    teams_left = 2 ** (rounds - round_no + 1)
    return "決賽" if teams_left == 2 else f"{teams_left} 強"


def source_label(match: PlannedMatch, side: Side) -> str | None:
    """待定列字串，例如「M4 勝者」「M29 敗者」；第一輪與輪空直接入座的一方回 None。

    只看靜態的 plan；隊伍已填入後由呼叫端自行隱藏這個字串。
    """
    src = match.source(side)
    if src is None:
        return None
    return f"{src.code} {_KIND_LABEL[src.kind]}"


def plan(team_count: int) -> BracketPlan:
    if team_count < 2:
        raise ValueError("隊數少於 2，無法產生對戰表")

    size = 1
    while size < team_count:
        size *= 2
    rounds = size.bit_length() - 1
    bye_count = size - team_count
    has_third = team_count >= 4
    bye_pairs = set(_bye_pairs(size, bye_count))

    # 第一輪：存在的場次位置（對編號）
    round_positions: dict[int, list[int]] = {
        1: [i for i in range(size // 2) if i not in bye_pairs]
    }
    for r in range(2, rounds + 1):
        round_positions[r] = list(range(size // 2**r))

    # 依輪次、由上到下編號，只編實際存在的場次
    codes: dict[tuple[int, int], str] = {}
    n = 0
    for r in range(1, rounds + 1):
        for pos in round_positions[r]:
            n += 1
            codes[(r, pos)] = f"M{n}"
    third_code = f"M{n + 1}" if has_third else None

    matches: list[PlannedMatch] = []
    for r in range(1, rounds + 1):
        for pos in round_positions[r]:
            src_a: MatchSource | None = None
            src_b: MatchSource | None = None
            bye_a = bye_b = False
            if r == 2:
                # 第二輪第 j 場由第 2j、2j+1 對的勝者組成
                if 2 * pos in bye_pairs:
                    bye_a = True
                else:
                    src_a = MatchSource(codes[(1, 2 * pos)], "winner")
                if 2 * pos + 1 in bye_pairs:
                    bye_b = True
                else:
                    src_b = MatchSource(codes[(1, 2 * pos + 1)], "winner")
            elif r > 2:
                src_a = MatchSource(codes[(r - 1, 2 * pos)], "winner")
                src_b = MatchSource(codes[(r - 1, 2 * pos + 1)], "winner")

            is_final = r == rounds
            matches.append(
                PlannedMatch(
                    code=codes[(r, pos)],
                    round_no=r,
                    slot_no=pos + 1,
                    is_third_place=False,
                    next_code=None if is_final else codes[(r + 1, pos // 2)],
                    next_side=None if is_final else ("a" if pos % 2 == 0 else "b"),
                    loser_next_code=third_code if r == rounds - 1 else None,
                    source_a=src_a,
                    source_b=src_b,
                    bye_a=bye_a,
                    bye_b=bye_b,
                )
            )

    if third_code is not None:
        semis = [m.code for m in matches if m.round_no == rounds - 1]
        matches.append(
            PlannedMatch(
                code=third_code,
                round_no=rounds,
                slot_no=2,
                is_third_place=True,
                next_code=None,
                next_side=None,
                loser_next_code=None,
                source_a=MatchSource(semis[0], "loser"),
                source_b=MatchSource(semis[1], "loser"),
                bye_a=False,
                bye_b=False,
            )
        )

    return BracketPlan(
        team_count=team_count,
        size=size,
        rounds=rounds,
        bye_count=bye_count,
        has_third_place=has_third,
        matches=tuple(matches),
    )


def assign[T: Hashable](
    team_ids: Sequence[T], bracket_plan: BracketPlan, rng: Shuffler
) -> tuple[AssignedMatch[T], ...]:
    """以注入的亂數把隊伍排進 plan：第一輪兩隊確定，輪空隊伍直接入第二輪。"""
    if len(team_ids) != bracket_plan.team_count:
        raise ValueError("隊伍數量與對戰表不符")
    if len(set(team_ids)) != len(team_ids):
        raise ValueError("隊伍 id 重複")

    pool = list(team_ids)
    rng.shuffle(pool)
    it = iter(pool)

    # 先排第一輪（每場兩隊），再排輪空隊伍；依 plan 順序取用，結果只取決於洗牌
    team_a: dict[str, T] = {}
    team_b: dict[str, T] = {}
    for m in bracket_plan.matches:
        if m.round_no == 1:
            team_a[m.code] = next(it)
            team_b[m.code] = next(it)
    for m in bracket_plan.matches:
        if m.bye_a:
            team_a[m.code] = next(it)
        if m.bye_b:
            team_b[m.code] = next(it)

    return tuple(
        AssignedMatch(m, team_a.get(m.code), team_b.get(m.code))
        for m in bracket_plan.matches
    )
