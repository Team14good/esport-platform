"""逐局比分與系列結果的規則（Story 5.3、5.4 的純函式）。"""

import ast
import random
from pathlib import Path
from typing import get_args

import pytest

from app.modules.competition import scoring
from app.modules.competition.scoring import (
    GameResult,
    ScoreReason,
    check_delete,
    check_record,
    make_game,
    series,
    wins_needed,
)

SCORING_FILE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "competition"
    / "scoring.py"
)
A = GameResult(winner="a")
B = GameResult(winner="b")


def games_of(text: str) -> list[GameResult]:
    """把 "aba" 這類字串轉成各局結果。"""
    return [A if side == "a" else B for side in text]


# ---- I/O 矩陣 ----


@pytest.mark.parametrize(("bo", "expected"), [(1, 1), (3, 2), (5, 3), (7, 4)])
def test_wins_needed(bo: int, expected: int) -> None:
    assert wins_needed(bo) == expected


@pytest.mark.parametrize("bo", [0, 2, 4, 6, 8, 9, -1, True, 3.0, "3", None])
def test_wins_needed_rejects_other_bo(bo: int) -> None:
    with pytest.raises(ValueError):
        wins_needed(bo)


def test_bad_bo_is_rejected_by_series_and_check_record() -> None:
    with pytest.raises(ValueError):
        series([], bo=2)
    with pytest.raises(ValueError):
        check_record([], bo=4, game_no=1, result=A)


@pytest.mark.parametrize("side", ["a", "b"])
def test_win_loss_game(side: str) -> None:
    assert make_game("win_loss", winner=side) == GameResult(winner=side)  # type: ignore[arg-type]


def test_rounds_game_a_wins() -> None:
    assert make_game("rounds", score_a=13, score_b=11) == GameResult(
        winner="a", score_a=13, score_b=11
    )


def test_rounds_game_b_wins() -> None:
    assert make_game("rounds", score_a=0, score_b=1) == GameResult(
        winner="b", score_a=0, score_b=1
    )


@pytest.mark.parametrize(("score_a", "score_b"), [(12, 12), (0, 0)])
def test_rounds_tie(score_a: int, score_b: int) -> None:
    assert make_game("rounds", score_a=score_a, score_b=score_b) == "tie"


@pytest.mark.parametrize(("score_a", "score_b"), [(-1, 13), (13, -1), (-1, -1)])
def test_rounds_negative(score_a: int, score_b: int) -> None:
    assert make_game("rounds", score_a=score_a, score_b=score_b) == "invalid_score"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"winner": "a", "score_a": 13, "score_b": 11},  # win_loss 卻給數字
        {"score_a": 13},
        {"score_b": 11},
        {},  # 沒有勝方
        {"winner": "c"},
        {"winner": ""},
        {"winner": None},
        {"winner": "a", "score_a": 0, "score_b": 0},  # 零分也是數字
        {"winner": "a", "score_a": 0},
    ],
)
def test_win_loss_type_mismatch(kwargs: dict[str, object]) -> None:
    assert make_game("win_loss", **kwargs) == "invalid_score"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"score_a": 13},  # 少一邊
        {"score_b": 11},
        {},
        {"winner": "a"},
        {"winner": "a", "score_a": 13, "score_b": 11},  # 回合型態不收勝方
        {"score_a": True, "score_b": 0},
        {"score_a": 1.5, "score_b": 0},
        {"score_a": "13", "score_b": "11"},
    ],
)
def test_rounds_type_mismatch(kwargs: dict[str, object]) -> None:
    assert make_game("rounds", **kwargs) == "invalid_score"  # type: ignore[arg-type]


def test_unknown_score_type() -> None:
    with pytest.raises(ValueError):
        make_game("kills", winner="a")  # type: ignore[arg-type]


def test_record_next_game() -> None:
    assert check_record(games_of("a"), bo=3, game_no=2, result=B) is None


def test_record_first_game() -> None:
    assert check_record([], bo=1, game_no=1, result=A) is None


@pytest.mark.parametrize("game_no", [3, 0, -1, 4])
def test_record_skipped_game_no(game_no: int) -> None:
    assert (
        check_record(games_of("a"), bo=3, game_no=game_no, result=B)
        == "invalid_game_no"
    )


def test_record_after_series_decided() -> None:
    assert check_record(games_of("aa"), bo=3, game_no=3, result=B) == "series_decided"


def apply_record(
    games: list[GameResult], *, bo: int, game_no: int, result: GameResult
) -> list[GameResult]:
    """經 check_record 允許才登錄或覆寫，回傳新的各局；被拒絕時測試失敗。"""
    assert check_record(games, bo=bo, game_no=game_no, result=result) is None
    return [*games[: game_no - 1], result, *games[game_no:]]


def test_overwrite() -> None:
    games = apply_record(games_of("ab"), bo=3, game_no=1, result=B)

    assert games == games_of("bb")
    result = series(games, bo=3)
    assert (result.wins_a, result.wins_b, result.winner) == (0, 2, "b")
    assert result.can_submit is True


def test_overwrite_last_game_that_decides() -> None:
    assert check_record(games_of("aba"), bo=3, game_no=3, result=B) is None


def test_overwrite_creates_redundant_games() -> None:
    assert check_record(games_of("aba"), bo=3, game_no=1, result=B) == "redundant_games"


def test_delete_last_game_then_overwrite() -> None:
    games = games_of("aba")
    assert check_delete(games, game_no=3) is None

    remaining = games[:-1]
    assert remaining == games_of("ab")
    assert check_record(remaining, bo=3, game_no=1, result=B) is None


@pytest.mark.parametrize("game_no", [1, 2])
def test_delete_not_last_game(game_no: int) -> None:
    assert check_delete(games_of("aba"), game_no=game_no) == "not_last_game"


@pytest.mark.parametrize("game_no", [0, 1, -1])
def test_delete_without_games(game_no: int) -> None:
    assert check_delete([], game_no=game_no) == "invalid_game_no"


@pytest.mark.parametrize("game_no", [0, 4, -1])
def test_delete_nonexistent_game(game_no: int) -> None:
    assert check_delete(games_of("aba"), game_no=game_no) == "invalid_game_no"


def test_series_decided() -> None:
    result = series(games_of("abaa"), bo=5)

    assert (result.wins_a, result.wins_b, result.winner) == (3, 1, "a")
    assert result.can_submit is True
    assert result.reason is None
    assert result.wins_needed == 3


def test_series_not_decided() -> None:
    result = series(games_of("ab"), bo=5)

    assert result.can_submit is False
    assert result.winner is None
    assert result.reason == "not_decided"
    assert result.wins_needed == 3


def test_series_empty() -> None:
    result = series([], bo=1)

    assert (result.wins_a, result.wins_b, result.winner, result.can_submit) == (
        0,
        0,
        None,
        False,
    )


# ---- 依 AC 手寫的字面案例（不經獨立規則推算） ----


@pytest.mark.parametrize(
    ("bo", "seq", "game_no", "side", "expected"),
    [
        # BO5 a,a,a,b（本身已是不合法的資料）上的覆寫
        (5, "aaab", 1, "a", "redundant_games"),
        (5, "aaab", 4, "a", "redundant_games"),
        (5, "aaab", 3, "b", None),  # 改成 a,a,b,b：未決定，沒有多餘的局
        (5, "aaab", 5, "a", "series_decided"),
        # BO1 覆寫唯一的一局
        (1, "a", 1, "b", None),
        (1, "a", 1, "a", None),
        (1, "a", 2, "b", "series_decided"),
        # BO3 a,a 覆寫第 2 局成 b；a,b 之後可以登錄第 3 局
        (3, "aa", 2, "b", None),
        (3, "ab", 3, "a", None),
        (3, "ab", 3, "b", None),
        # 其他
        (3, "ab", 1, "b", None),
        (3, "aba", 2, "a", "redundant_games"),
        (3, "aba", 1, "a", None),
        (7, "abababa", 7, "b", None),
        (7, "abababa", 1, "b", "redundant_games"),
        (7, "aaaa", 5, "b", "series_decided"),
        (7, "aaab", 4, "a", None),
    ],
)
def test_literal_record_cases(
    bo: int, seq: str, game_no: int, side: str, expected: str | None
) -> None:
    result = A if side == "a" else B
    assert (
        check_record(games_of(seq), bo=bo, game_no=game_no, result=result) == expected
    )


def test_bo3_overwrite_then_record_game_3() -> None:
    games = apply_record(games_of("aa"), bo=3, game_no=2, result=B)
    assert series(games, bo=3).can_submit is False

    games = apply_record(games, bo=3, game_no=3, result=B)
    result = series(games, bo=3)
    assert (result.wins_a, result.wins_b, result.winner, result.can_submit) == (
        1,
        2,
        "b",
        True,
    )


@pytest.mark.parametrize(
    ("bo", "seq", "winner", "can_submit", "reason"),
    [
        (1, "a", "a", True, None),
        (1, "b", "b", True, None),
        (3, "abb", "b", True, None),
        (3, "ab", None, False, "not_decided"),
        (7, "abababa", "a", True, None),
        (7, "bbbb", "b", True, None),
        (7, "bbbbab", None, False, "redundant_games"),
        (3, "aab", None, False, "redundant_games"),  # 決定勝負之後還有局
        (1, "ab", None, False, "redundant_games"),
        (5, "aaab", None, False, "redundant_games"),
    ],
)
def test_literal_series_cases(
    bo: int, seq: str, winner: str | None, can_submit: bool, reason: str | None
) -> None:
    result = series(games_of(seq), bo=bo)

    assert result.wins_a == seq.count("a")
    assert result.wins_b == seq.count("b")
    assert (result.winner, result.can_submit, result.reason) == (
        winner,
        can_submit,
        reason,
    )


# ---- 不合法的 GameResult、混用型態、不合法的局號 ----


@pytest.mark.parametrize(
    "kwargs",
    [
        {"winner": "c"},
        {"winner": None},
        {"winner": "a", "score_a": 13},  # 少一邊
        {"winner": "a", "score_b": 11},
        {"winner": "a", "score_a": -1, "score_b": -2},
        {"winner": "a", "score_a": True, "score_b": False},
        {"winner": "a", "score_a": 1.5, "score_b": 0},
        {"winner": "a", "score_a": 12, "score_b": 12},  # 平手
        {"winner": "a", "score_a": 0, "score_b": 0},
        {"winner": "a", "score_a": 11, "score_b": 13},  # 勝方與比分不符
        {"winner": "b", "score_a": 13, "score_b": 11},
    ],
)
def test_game_result_rejects_invalid(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        GameResult(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"winner": "a"},
        {"winner": "b"},
        {"winner": "a", "score_a": 1, "score_b": 0},
        {"winner": "b", "score_a": 0, "score_b": 13},
    ],
)
def test_game_result_accepts_valid(kwargs: dict[str, object]) -> None:
    game = GameResult(**kwargs)  # type: ignore[arg-type]
    assert game.winner == kwargs["winner"]


ROUND_A = GameResult(winner="a", score_a=13, score_b=11)
ROUND_B = GameResult(winner="b", score_a=5, score_b=13)


@pytest.mark.parametrize(
    ("games", "game_no", "result"),
    [
        ([ROUND_A], 2, A),  # 回合型態的系列混入勝負型態
        ([ROUND_A], 1, A),
        ([A], 2, ROUND_B),  # 勝負型態的系列混入回合型態
        ([A, B], 1, ROUND_A),
    ],
)
def test_record_rejects_mixed_score_kinds(
    games: list[GameResult], game_no: int, result: GameResult
) -> None:
    assert check_record(games, bo=5, game_no=game_no, result=result) == "invalid_score"


def test_record_same_score_kind_is_allowed() -> None:
    assert check_record([ROUND_A], bo=5, game_no=2, result=ROUND_B) is None
    assert check_record([ROUND_A], bo=5, game_no=1, result=ROUND_B) is None


@pytest.mark.parametrize("game_no", [True, False, 1.5, 2.0, "2", None])
def test_record_rejects_non_int_game_no(game_no: object) -> None:
    reason = check_record(games_of("a"), bo=3, game_no=game_no, result=B)  # type: ignore[arg-type]
    assert reason == "invalid_game_no"


@pytest.mark.parametrize("game_no", [True, 1.0, 1.5, "1", None])
def test_delete_rejects_non_int_game_no(game_no: object) -> None:
    assert check_delete(games_of("a"), game_no=game_no) == "invalid_game_no"  # type: ignore[arg-type]


def test_reasons_are_exported() -> None:
    assert set(get_args(ScoreReason)) == {
        "tie",
        "invalid_score",
        "invalid_game_no",
        "series_decided",
        "redundant_games",
        "not_last_game",
        "not_decided",
    }


# ---- 性質測試：隨機登錄、覆寫、刪除最後一局 ----


def expected_record_reason(
    games: list[GameResult], bo: int, game_no: int, result: GameResult
) -> str | None:
    """獨立於 scoring.py 的規則：用計數重算應有的結果。"""
    needed = (bo + 1) // 2
    count = len(games)

    def decided(seq: list[GameResult]) -> bool:
        return (
            max(sum(g.winner == "a" for g in seq), sum(g.winner == "b" for g in seq))
            >= needed
        )

    if 1 <= game_no <= count:
        updated = games[: game_no - 1] + [result] + games[game_no:]
        # 最後一局之前的任何前綴已達門檻 → 多餘
        if any(decided(updated[:k]) for k in range(1, count)):
            return "redundant_games"
        return None
    if game_no == count + 1:
        return "series_decided" if decided(games) else None
    return "invalid_game_no"


def assert_acceptance(games: list[GameResult], bo: int) -> None:
    needed = (bo + 1) // 2
    wins_a = sum(g.winner == "a" for g in games)
    wins_b = sum(g.winner == "b" for g in games)
    expected_winner = "a" if wins_a == needed else "b" if wins_b == needed else None

    result = series(games, bo=bo)

    # AC 1：勝局數不超過門檻、最多一隊達門檻、達門檻的那一局就是最後一局
    assert wins_a <= needed and wins_b <= needed
    assert not (wins_a == needed and wins_b == needed)
    if expected_winner is not None:
        assert games[-1].winner == expected_winner
        before = games[:-1]
        assert sum(g.winner == "a" for g in before) < needed
        assert sum(g.winner == "b" for g in before) < needed

    assert (result.wins_a, result.wins_b) == (wins_a, wins_b)
    assert result.winner == expected_winner
    assert result.can_submit is (expected_winner is not None)
    assert result.wins_needed == needed
    assert result.reason == (None if result.can_submit else "not_decided")

    # AC 2：未能送出時可新增下一局；能送出時新增被拒絕
    for nxt in (A, B):
        reason = check_record(games, bo=bo, game_no=len(games) + 1, result=nxt)
        assert reason == ("series_decided" if result.can_submit else None)


def run_random_sequence(bo: int, seed: int, counts: dict[str, int]) -> None:
    """隨機操作 80 步，只套用規則允許的操作，每一步後檢查兩條 AC。"""
    rng = random.Random(seed * 10 + bo)
    games: list[GameResult] = []

    for _ in range(80):
        op = rng.choice(["record", "record", "overwrite", "delete", "bad"])
        result = rng.choice([A, B])
        if op == "record":
            game_no = len(games) + 1
        elif op == "overwrite":
            game_no = rng.randint(1, max(len(games), 1))
        elif op == "delete":
            game_no = rng.randint(0, len(games) + 1)
        else:
            game_no = rng.choice([0, -1, len(games) + 2, len(games) + 1 + bo])

        if op == "delete":
            reason = check_delete(games, game_no=game_no)
            expected = (
                "invalid_game_no"
                if not games or not 1 <= game_no <= len(games)
                else None
                if game_no == len(games)
                else "not_last_game"
            )
            assert reason == expected
            if reason is None:
                games.pop()
                counts["delete"] += 1
        else:
            reason = check_record(games, bo=bo, game_no=game_no, result=result)
            assert reason == expected_record_reason(games, bo, game_no, result)
            if reason is None:
                if game_no == len(games) + 1:
                    games.append(result)
                    counts["record"] += 1
                else:
                    games[game_no - 1] = result
                    counts["overwrite"] += 1
        if reason is not None:
            counts["rejected"] += 1

        assert_acceptance(games, bo)


@pytest.mark.parametrize("bo", [1, 3, 5, 7])
def test_random_sequences_keep_acceptance_criteria(bo: int) -> None:
    counts = {"record": 0, "overwrite": 0, "delete": 0, "rejected": 0}
    for seed in range(200):
        run_random_sequence(bo, seed, counts)

    # 確保每種操作都真的走過，測試不會空轉
    assert all(value > 0 for value in counts.values()), counts


@pytest.mark.parametrize("bo", [3, 5, 7])
def test_random_sequences_reach_redundant_rejection(bo: int) -> None:
    """覆寫造成多餘的局在隨機序列中確實會被拒絕（BO3 起才可能發生）。"""
    rejected = 0
    for seed in range(200):
        rng = random.Random(seed)
        games: list[GameResult] = []
        for _ in range(30):
            result = rng.choice([A, B])
            if games and rng.random() < 0.5:
                game_no = rng.randint(1, len(games))
            else:
                game_no = len(games) + 1
            reason = check_record(games, bo=bo, game_no=game_no, result=result)
            if reason == "redundant_games":
                rejected += 1
            elif reason is None:
                if game_no == len(games) + 1:
                    games.append(result)
                else:
                    games[game_no - 1] = result
            assert_acceptance(games, bo)
    assert rejected > 0


# ---- 結構：不 import 其他模組或 app.core ----


def test_scoring_imports_only_allowed_stdlib() -> None:
    tree = ast.parse(SCORING_FILE.read_text(encoding="utf-8"))
    allowed = {"__future__", "collections.abc", "dataclasses", "typing"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "不得使用相對 import"
            imported.add(node.module or "")

    assert imported, "應該至少 import 了標準函式庫"
    assert imported <= allowed, imported - allowed


def test_scoring_file_is_the_imported_module() -> None:
    assert Path(scoring.__file__).resolve() == SCORING_FILE
