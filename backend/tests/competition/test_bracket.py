import ast
import random
import uuid
from pathlib import Path

import pytest

from app.modules.competition import bracket
from app.modules.competition.bracket import assign, plan, round_name, source_label


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def _p(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


@pytest.mark.parametrize(
    ("n", "size", "rounds", "byes", "total"),
    [
        (8, 8, 3, 0, 8),
        (13, 16, 4, 3, 13),
        (10, 16, 4, 6, 10),
        (3, 4, 2, 1, 2),
        (2, 2, 1, 0, 1),
        (32, 32, 5, 0, 32),
    ],
)
def test_matrix(n, size, rounds, byes, total) -> None:
    pl = plan(n)
    assert (pl.size, pl.rounds, pl.bye_count, len(pl.matches)) == (
        size,
        rounds,
        byes,
        total,
    )


def test_32_third_place_is_last() -> None:
    pl = plan(32)
    assert pl.matches[-1].code == "M32"
    assert pl.matches[-1].is_third_place


def test_2_and_3_have_no_third_place() -> None:
    assert not plan(2).has_third_place
    assert not plan(3).has_third_place
    assert plan(2).matches[0].next_code is None


@pytest.mark.parametrize("n", [0, 1, -3])
def test_plan_too_few(n) -> None:
    with pytest.raises(ValueError):
        plan(n)


def test_assign_count_mismatch_and_duplicates() -> None:
    with pytest.raises(ValueError):
        assign(_ids(5), plan(8), random.Random(1))
    ids = _ids(7)
    ids.append(ids[0])
    with pytest.raises(ValueError):
        assign(ids, plan(8), random.Random(1))


@pytest.mark.parametrize("n", range(2, 65))
def test_structure_invariants(n) -> None:
    pl = plan(n)
    expected = n - 1 + (1 if n >= 4 else 0)
    assert len(pl.matches) == expected
    codes = [m.code for m in pl.matches]
    assert codes == [f"M{i}" for i in range(1, expected + 1)]
    by_code = {m.code: m for m in pl.matches}
    rounds = [m.round_no for m in pl.matches if not m.is_third_place]
    assert rounds == sorted(rounds)
    for m in pl.matches:
        if m.is_third_place:
            assert m is pl.matches[-1] and m.next_code is None
            semis = [x.code for x in pl.matches if x.round_no == pl.rounds - 1]
            assert m.source_a == bracket.MatchSource(semis[0], "loser")
            assert m.source_b == bracket.MatchSource(semis[1], "loser")
        elif m.round_no == pl.rounds:
            assert m.next_code is None
        else:
            nxt = by_code[m.next_code]
            assert nxt.round_no == m.round_no + 1
            side = m.next_side
            assert side in ("a", "b")
            src = nxt.source(side)
            assert src is not None and src.code == m.code and src.kind == "winner"
        if m.round_no == pl.rounds - 1 and pl.has_third_place:
            third = by_code[m.loser_next_code]
            assert third.is_third_place
        else:
            assert m.loser_next_code is None
    # slot_no 在同輪不重複
    for r in range(1, pl.rounds + 1):
        slots = [
            m.slot_no for m in pl.matches if m.round_no == r and not m.is_third_place
        ]
        assert all(x < y for x, y in zip(slots, slots[1:], strict=False))

    for seed in (1, 2):
        out = assign(_ids(n), pl, random.Random(seed))
        seen = []
        for a in out:
            if a.match.round_no == 1:
                assert a.team_a_id is not None and a.team_b_id is not None
                seen += [a.team_a_id, a.team_b_id]
            elif a.match.round_no == 2 and not a.match.is_third_place:
                seen += [
                    t
                    for t, b in (
                        (a.team_a_id, a.match.bye_a),
                        (a.team_b_id, a.match.bye_b),
                    )
                    if b
                ]
            if a.match.round_no > 2 or a.match.is_third_place:
                assert a.team_a_id is None and a.team_b_id is None
        assert len(seen) == n and len(set(seen)) == n
        # 第二輪的 bye 旗標與隊伍一致
        for a in out:
            assert (a.team_a_id is not None) == (a.match.round_no == 1 or a.match.bye_a)


@pytest.mark.parametrize("n", range(2, 65))
def test_bye_distribution(n) -> None:
    pl = plan(n)
    byes = pl.bye_count
    if byes == 0:
        return
    quarter = pl.size // 4
    r2 = [m for m in pl.matches if m.round_no == 2 and not m.is_third_place]
    bye_sides = [int(m.bye_a) + int(m.bye_b) for m in r2]
    assert sum(bye_sides) == byes
    assert max(bye_sides) <= 2
    half = len(bye_sides) // 2
    assert abs(sum(bye_sides[:half]) - sum(bye_sides[half:])) <= 1
    if byes <= quarter:
        # 每支輪空隊伍的對手都是第一輪勝隊
        assert max(bye_sides) == 1
        for m in r2:
            if m.bye_a:
                assert m.source_b is not None
            if m.bye_b:
                assert m.source_a is not None
    else:
        assert sum(1 for s in bye_sides if s == 2) == byes - quarter
        assert all(s >= 1 for s in bye_sides)
        both = [m for m in r2 if m.bye_a and m.bye_b]
        for m in both:
            assert m.source_a is None and m.source_b is None


def test_13_bye_pairs_exact() -> None:
    pl = plan(13)
    r1 = [m.slot_no for m in pl.matches if m.round_no == 1]
    assert r1 == [2, 4, 6, 7, 8]  # 第 1、3、5、6、7 對（1 起算）
    r2 = [m for m in pl.matches if m.round_no == 2]
    # 輪空對 0、4、2 → 第二輪 j0、j2、j1 的上方；j3 由兩場第一輪勝者組成
    assert [(m.bye_a, m.bye_b) for m in r2] == [
        (True, False),
        (True, False),
        (True, False),
        (False, False),
    ]
    assert sum(m.bye_a or m.bye_b for m in r2) == 3


def test_10_has_determined_r2_match() -> None:
    pl = plan(10)
    out = assign(_ids(10), pl, random.Random(0))
    both = [
        a
        for a in out
        if a.match.round_no == 2 and a.team_a_id is not None and a.team_b_id is not None
    ]
    assert len(both) == 2


def test_assign_seed_behaviour() -> None:
    ids = _ids(13)
    pl = plan(13)
    a1 = assign(ids, pl, random.Random(1))
    a1b = assign(ids, pl, random.Random(1))
    a2 = assign(ids, pl, random.Random(2))
    assert a1 == a1b
    assert a1 != a2
    assert [x.match for x in a1] == [x.match for x in a2]
    assert plan(13) == plan(13)


def test_round_names() -> None:
    assert [round_name(r, 4) for r in range(1, 5)] == ["16 強", "8 強", "4 強", "決賽"]
    assert round_name(1, 1) == "決賽"
    with pytest.raises(ValueError):
        round_name(0, 3)
    with pytest.raises(ValueError):
        round_name(4, 3)


def test_source_labels() -> None:
    pl = plan(32)
    m = pl.matches[16]  # 第二輪第一場 M17
    assert m.round_no == 2
    assert source_label(m, "a") == "M1 勝者"
    assert source_label(m, "b") == "M2 勝者"
    third = pl.matches[-1]
    assert source_label(third, "a") == "M29 敗者"
    assert source_label(third, "b") == "M30 敗者"
    assert source_label(pl.matches[0], "a") is None
    pl13 = plan(13)
    bye_match = next(x for x in pl13.matches if x.bye_a)
    assert source_label(bye_match, "a") is None
    assert source_label(bye_match, "b") is not None


def test_14_bye_pairs_exact() -> None:
    pl = plan(14)
    assert [m.slot_no for m in pl.matches if m.round_no == 1] == [2, 3, 4, 6, 7, 8]
    r2 = [m for m in pl.matches if m.round_no == 2]
    assert [m.bye_a or m.bye_b for m in r2] == [True, False, True, False]


def test_match_lookup() -> None:
    pl = plan(8)
    assert pl.match("M8").is_third_place
    with pytest.raises(KeyError):
        pl.match("M99")


def test_module_imports_only_allowed() -> None:
    tree = ast.parse(Path(bracket.__file__).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.add(node.module)
    assert modules <= {"collections.abc", "dataclasses", "typing"}
