import pytest

from app.core.errors import FieldError
from app.modules.registration.player_profile import (
    average_rank_score,
    clean_file_name,
    rank_score_for,
    validate_game_account_id,
)
from app.modules.tournaments.models import RankTierRead

TIERS = [
    RankTierRead(name="鑽石", score=50),
    RankTierRead(name="白金", score=40),
    RankTierRead(name="黃金", score=30),
]


# ---------------------------------------------------------------- 段位


@pytest.mark.parametrize(("rank_tier", "score"), [("鑽石", 50), ("黃金", 30)])
def test_rank_in_table_returns_its_score(rank_tier: str, score: int) -> None:
    assert rank_score_for(TIERS, rank_tier) == score


@pytest.mark.parametrize(
    "rank_tier",
    ["大師", "", "鑽石 ", " 鑽石", "鑽", "diamond"],
)
def test_rank_not_in_table_is_rejected_on_rank_tier_field(rank_tier: str) -> None:
    with pytest.raises(FieldError) as exc_info:
        rank_score_for(TIERS, rank_tier)

    error = exc_info.value
    assert error.code == "RANK_TIER_NOT_ALLOWED"
    assert error.status_code == 422
    assert error.loc == ("body", "rank_tier")


def test_empty_table_rejects_every_rank() -> None:
    with pytest.raises(FieldError):
        rank_score_for([], "鑽石")


def test_accepts_any_iterable_of_tiers() -> None:
    assert rank_score_for(iter(TIERS), "白金") == 40


# ---------------------------------------------------------------- 遊戲 ID


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Night#TW1", "Night#TW1"),
        ("  夜貓  ", "夜貓"),
        ("x" * 50, "x" * 50),
        ("Ni\x00ght", "Night"),
        ("Night\n#TW1", "Night#TW1"),
        ("\u202eNight", "Night"),
        ("Ni\u200bght", "Night"),
        # 去掉格式字元後剛好 50 字
        ("\ufeff" + "x" * 50, "x" * 50),
    ],
)
def test_game_account_id_is_trimmed(value: str, expected: str) -> None:
    assert validate_game_account_id(value) == expected


@pytest.mark.parametrize(
    ("value", "code", "message"),
    [
        ("", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        (" \t\n", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("\x00", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("\u202e", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("\u200b\u200b", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("\ufeff", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        (" \u200b \ufeff ", "GAME_ACCOUNT_ID_REQUIRED", "請輸入遊戲 ID"),
        ("x" * 51, "GAME_ACCOUNT_ID_TOO_LONG", "遊戲 ID 最多 50 個字"),
        (f"  {'x' * 51}  ", "GAME_ACCOUNT_ID_TOO_LONG", "遊戲 ID 最多 50 個字"),
    ],
)
def test_invalid_game_account_id(value: str, code: str, message: str) -> None:
    with pytest.raises(FieldError) as exc_info:
        validate_game_account_id(value)

    error = exc_info.value
    assert (error.code, error.message) == (code, message)
    assert error.loc == ("body", "game_account_id")


# ---------------------------------------------------------------- 截圖檔名


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("段位.png", "段位.png"),
        ("../../etc/passwd.png", "passwd.png"),
        ("C:\\Users\\me\\rank.jpg", "rank.jpg"),
        ("a\x00b\x1fc\x7f.png", "abc.png"),
        ("\u202egnp.exe", "gnp.exe"),
        ("  rank.png  ", "rank.png"),
        ("x" * 120, "x" * 100),
        (None, "rank-screenshot.png"),
        ("", "rank-screenshot.png"),
        ("dir/", "rank-screenshot.png"),
        ("\x00\x01", "rank-screenshot.png"),
    ],
)
def test_clean_file_name(file_name: str | None, expected: str) -> None:
    assert clean_file_name(file_name, extension=".png") == expected


def test_clean_file_name_uses_given_extension_for_default() -> None:
    assert clean_file_name("   ", extension=".jpg") == "rank-screenshot.jpg"


# ---------------------------------------------------------------- 平均段位積分


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([], None),
        ([30], 30.0),
        ([30, 30, 10], 23.33),
        ([10, 20], 15.0),
        ([2, 1, 1], 1.33),
        ([2, 2, 1], 1.67),
        # 1 / 8 = 0.125：四捨五入為 0.13（銀行家捨入會是 0.12）
        ([1, 0, 0, 0, 0, 0, 0, 0], 0.13),
        # 3 / 8 = 0.375 → 0.38
        ([3, 0, 0, 0, 0, 0, 0, 0], 0.38),
    ],
)
def test_average_rank_score(scores: list[int], expected: float | None) -> None:
    assert average_rank_score(scores) == expected


def test_average_accepts_any_iterable() -> None:
    assert average_rank_score(iter([10, 30])) == 20.0
