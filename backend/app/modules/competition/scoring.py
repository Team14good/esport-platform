"""逐局比分與系列結果的規則（Story 5.3、5.4）。

純函式：不碰資料庫、不 import 其他模組、不讀時鐘。第二階段的 `record_game()`、
`submit_result()` 在鎖定場次後用這裡判斷再寫入；前端的系列結果預覽與停用說明
則透過第二階段的 API 取得這裡算出的系列結果。身分、報到、場次狀態等檢查由
service 負責。

錯誤分兩種：
- 賽事設定或程式錯誤（BO 不是 1／3／5／7、未知的 `score_type`、不合法的
  `GameResult`）丟 `ValueError`。
- 裁判輸入的問題（比分、局號）回傳 `ScoreReason`，由呼叫端轉成業務錯誤或停用說明。

`games` 一律是已登錄各局依局號排列的序列（索引 0 為第 1 局）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, TypeGuard, TypeIs

ScoreType = Literal["win_loss", "rounds"]
Side = Literal["a", "b"]
ScoreReason = Literal[
    "tie",
    "invalid_score",
    "invalid_game_no",
    "series_decided",
    "redundant_games",
    "not_last_game",
    "not_decided",
]

SeriesReason = Literal["not_decided", "redundant_games"]

ALLOWED_BO = (1, 3, 5, 7)


def _is_int(value: object) -> TypeIs[int]:
    """整數（排除 bool 與小數）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_score(value: object) -> TypeGuard[int]:
    """非負整數（排除 bool）。"""
    return _is_int(value) and value >= 0


@dataclass(frozen=True)
class GameResult:
    """一局的結果；`win_loss` 型態沒有數字比分（兩個 score 皆為 None）。"""

    winner: Side
    score_a: int | None = None
    score_b: int | None = None

    def __post_init__(self) -> None:
        """勝方只能是 a 或 b；比分要嘛都沒有，要嘛都是非負整數、不平手且勝方分數較高。"""
        if self.winner not in ("a", "b"):
            raise ValueError(f"勝方只能是 a 或 b，收到 {self.winner!r}")
        if self.score_a is None and self.score_b is None:
            return
        if not _is_score(self.score_a) or not _is_score(self.score_b):
            raise ValueError("比分必須同時為非負整數或同時為 None")
        if self.score_a == self.score_b:
            raise ValueError("一局不能平手")
        if self.winner != ("a" if self.score_a > self.score_b else "b"):
            raise ValueError("勝方與比分不符")


@dataclass(frozen=True)
class Series:
    """系列結果：兩隊勝局數、勝方（未達門檻為 None）、能不能送出與勝局門檻。

    `reason` 在不能送出時說明原因：`not_decided`（搭配 `wins_needed` 顯示門檻），
    或 `redundant_games`（決定勝負的那一局之後還有局）；能送出時為 None。
    """

    wins_a: int
    wins_b: int
    winner: Side | None
    can_submit: bool
    wins_needed: int
    reason: SeriesReason | None


def wins_needed(bo: int) -> int:
    """勝局門檻＝（BO＋1）÷ 2；BO 只能是 1、3、5、7。"""
    if not _is_int(bo) or bo not in ALLOWED_BO:
        raise ValueError(f"BO 只能是 1、3、5、7，收到 {bo!r}")
    return (bo + 1) // 2


def make_game(
    score_type: ScoreType,
    *,
    winner: str | None = None,
    score_a: int | None = None,
    score_b: int | None = None,
) -> GameResult | ScoreReason:
    """檢查一局的輸入；合法回傳 `GameResult`，否則回傳原因。"""
    if score_type == "win_loss":
        if score_a is not None or score_b is not None:
            return "invalid_score"
        if winner == "a":
            return GameResult(winner="a")
        if winner == "b":
            return GameResult(winner="b")
        return "invalid_score"
    if score_type == "rounds":
        if winner is not None or score_a is None or score_b is None:
            return "invalid_score"
        if not _is_score(score_a) or not _is_score(score_b):
            return "invalid_score"
        if score_a == score_b:
            return "tie"
        side: Side = "a" if score_a > score_b else "b"
        return GameResult(winner=side, score_a=score_a, score_b=score_b)
    raise ValueError(f"未知的比分型態 {score_type!r}")


def _decided_at(games: Sequence[GameResult], needed: int) -> int | None:
    """回傳任一隊達到勝局門檻的那一局索引；尚未決定為 None。"""
    wins = {"a": 0, "b": 0}
    for index, game in enumerate(games):
        wins[game.winner] += 1
        if wins[game.winner] >= needed:
            return index
    return None


def series(games: Sequence[GameResult], *, bo: int) -> Series:
    """依各局計算系列結果；勝方是先達到勝局門檻的一方。

    決定勝負的那一局不是最後一局時（後面有多餘的局），勝方為 None、不能送出。
    """
    needed = wins_needed(bo)
    decided = _decided_at(games, needed)
    winner: Side | None = None
    reason: SeriesReason | None = "not_decided"
    if decided is not None and decided < len(games) - 1:
        reason = "redundant_games"
    elif decided is not None:
        winner = games[decided].winner
        reason = None
    return Series(
        wins_a=sum(1 for game in games if game.winner == "a"),
        wins_b=sum(1 for game in games if game.winner == "b"),
        winner=winner,
        can_submit=winner is not None,
        wins_needed=needed,
        reason=reason,
    )


def check_record(
    games: Sequence[GameResult], *, bo: int, game_no: int, result: GameResult
) -> ScoreReason | None:
    """能不能登錄或覆寫第 `game_no` 局；可以回傳 None，否則回傳原因。"""
    needed = wins_needed(bo)
    count = len(games)
    if not _is_int(game_no):
        return "invalid_game_no"
    if any((game.score_a is None) != (result.score_a is None) for game in games):
        # 勝負型態（沒有比分）與回合型態（有比分）不能混在同一個系列
        return "invalid_score"
    if 1 <= game_no <= count:
        updated = [*games[: game_no - 1], result, *games[game_no:]]
        decided = _decided_at(updated, needed)
        if decided is not None and decided < count - 1:
            return "redundant_games"
        return None
    if game_no == count + 1:
        if _decided_at(games, needed) is not None:
            return "series_decided"
        return None
    return "invalid_game_no"


def check_delete(games: Sequence[GameResult], *, game_no: int) -> ScoreReason | None:
    """能不能刪除第 `game_no` 局；只能刪最後一局。"""
    count = len(games)
    if not _is_int(game_no) or count == 0 or not 1 <= game_no <= count:
        return "invalid_game_no"
    if game_no != count:
        return "not_last_game"
    return None
