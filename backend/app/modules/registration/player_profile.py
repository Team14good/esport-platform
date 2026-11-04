"""選手參賽資料的業務規則（Story 3.2）：段位、遊戲 ID、截圖檔名與平均段位積分；
送出報名的條件（Story 3.3）。

純函式，不碰資料庫。段位對照表來自賽事快照（tournaments 的
`TournamentRead.rank_tiers`）。
"""

import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import FieldError
from app.modules.registration.models import (
    GAME_ACCOUNT_ID_MAX_LENGTH,
    RANK_SCREENSHOT_NAME_MAX_LENGTH,
    MissingProfileField,
    SubmitBlocker,
)
from app.modules.tournaments.models import RankTierRead

RANK_TIER_NOT_ALLOWED_MESSAGE = "段位必須是賽事段位對照表中的段位"
DEFAULT_SCREENSHOT_STEM = "rank-screenshot"
_CENT = Decimal("0.01")
# 控制字元（NUL、換行等）與格式字元（U+202E 雙向覆寫、U+200B 零寬空白、U+FEFF 等）
_REMOVED_CATEGORIES = frozenset({"Cc", "Cf"})


def _remove_control_and_format_chars(value: str) -> str:
    return "".join(
        char for char in value if unicodedata.category(char) not in _REMOVED_CATEGORIES
    )


def rank_score_for(rank_tiers: Iterable[RankTierRead], rank_tier: str) -> int:
    """回傳段位 `rank_tier` 在對照表中的積分；名稱須完全相符。

    不在對照表中時拋 422 `RANK_TIER_NOT_ALLOWED`，`loc` 指向 `rank_tier` 欄位。
    """
    for tier in rank_tiers:
        if tier.name == rank_tier:
            return tier.score
    raise FieldError(
        "RANK_TIER_NOT_ALLOWED",
        RANK_TIER_NOT_ALLOWED_MESSAGE,
        loc=("body", "rank_tier"),
    )


def validate_game_account_id(value: str) -> str:
    """去掉控制與格式字元、去頭尾空白後回傳遊戲 ID。

    結果為空拋 `GAME_ACCOUNT_ID_REQUIRED`，超過 50 字拋 `GAME_ACCOUNT_ID_TOO_LONG`。
    """
    game_account_id = _remove_control_and_format_chars(value).strip()
    if not game_account_id:
        raise FieldError(
            "GAME_ACCOUNT_ID_REQUIRED",
            "請輸入遊戲 ID",
            loc=("body", "game_account_id"),
        )
    if len(game_account_id) > GAME_ACCOUNT_ID_MAX_LENGTH:
        raise FieldError(
            "GAME_ACCOUNT_ID_TOO_LONG",
            f"遊戲 ID 最多 {GAME_ACCOUNT_ID_MAX_LENGTH} 個字",
            loc=("body", "game_account_id"),
        )
    return game_account_id


def clean_file_name(file_name: str | None, *, extension: str) -> str:
    """清理上傳時的原始檔名，只用於顯示。

    取最後一段路徑（`/` 與 `\\` 都算分隔）、去掉控制與格式字元（含雙向覆寫字元）、
    去頭尾空白後截到 100 字；結果為空時用 `rank-screenshot<extension>`
    （`extension` 含點，例如 `.png`）。
    """
    name = (file_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _remove_control_and_format_chars(name)
    name = name.strip()[:RANK_SCREENSHOT_NAME_MAX_LENGTH].strip()
    return name or f"{DEFAULT_SCREENSHOT_STEM}{extension}"


def average_rank_score_decimal(scores: Iterable[int]) -> Decimal | None:
    """平均段位積分（`Decimal`），以四捨五入（ROUND_HALF_UP）取到小數第二位；
    沒有分數時回傳 None。送出報名時凍結到 Registration 的快照用這個值。"""
    values = list(scores)
    if not values:
        return None
    average = Decimal(sum(values)) / Decimal(len(values))
    return average.quantize(_CENT, rounding=ROUND_HALF_UP)


def average_rank_score(scores: Iterable[int]) -> float | None:
    """平均段位積分，以四捨五入（ROUND_HALF_UP）取到小數第二位；沒有分數時回傳 None。"""
    average = average_rank_score_decimal(scores)
    return None if average is None else float(average)


# ---------------------------------------------------------------- 送出報名的條件


@dataclass(frozen=True)
class RosterEntry:
    """送出檢查需要的一位隊員資料。"""

    display_name: str
    missing_fields: Sequence[MissingProfileField]
    school_id: uuid.UUID | None


def _names(entries: Iterable[RosterEntry]) -> str:
    return "、".join(entry.display_name for entry in entries)


def submit_blockers(
    *, starters: int, members: Sequence[RosterEntry]
) -> list[SubmitBlocker]:
    """不能送出報名的原因，依固定順序全部列出（不只第一項）；`members` 依加入順序。

    人數達先發人數 → 每位參賽資料完整 → 每位都設定了學校 → 已設學校的隊員學校相同。
    """
    blockers: list[SubmitBlocker] = []
    shortage = starters - len(members)
    if shortage > 0:
        blockers.append(
            SubmitBlocker(
                code="STARTERS_NOT_MET",
                message=f"還差 {shortage} 人才達先發人數（{starters} 人）",
            )
        )
    incomplete = [entry for entry in members if entry.missing_fields]
    if incomplete:
        blockers.append(
            SubmitBlocker(
                code="PROFILE_INCOMPLETE",
                message=f"尚未填完參賽資料：{_names(incomplete)}",
            )
        )
    no_school = [entry for entry in members if entry.school_id is None]
    if no_school:
        blockers.append(
            SubmitBlocker(
                code="SCHOOL_MISSING", message=f"尚未設定學校：{_names(no_school)}"
            )
        )
    schools = {entry.school_id for entry in members if entry.school_id is not None}
    if len(schools) > 1:
        blockers.append(
            SubmitBlocker(code="SCHOOL_MISMATCH", message="隊員的學校不一致")
        )
    return blockers
