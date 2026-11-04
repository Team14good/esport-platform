"""competition 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core import clock
from app.core.events import Event
from app.modules.competition.scoring import SeriesReason
from app.modules.tournaments.models import ScoreType


class MatchStatus(StrEnum):
    """場次狀態：待開打、進行中、申訴期、申訴中、已確認、已取消（AD-11）。"""

    SCHEDULED = "scheduled"
    LIVE = "live"
    APPEAL_WINDOW = "appeal_window"
    APPEALED = "appealed"
    CONFIRMED = "confirmed"
    VOIDED = "voided"


class MatchOutcome(StrEnum):
    """場次結果類型：正常完賽、一方棄權、雙方棄權、輪空、取消資格判負。"""

    PLAYED = "played"
    FORFEIT = "forfeit"
    DOUBLE_FORFEIT = "double_forfeit"
    WALKOVER = "walkover"
    DISQUALIFIED = "disqualified"


MATCH_CODE_MAX_LENGTH = 10


# ---------------------------------------------------------------- 資料表


class Bracket(SQLModel, table=True):
    """一場賽事的對戰表；每場賽事最多一份（抽籤只能一次）。"""

    __tablename__ = "bracket"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", unique=True)
    # P：不小於隊數的最小 2 的次方
    size: int
    rounds: int
    # 抽籤時的正取隊數；公開對戰樹以它重建 `bracket.plan`（待定列字串）
    team_count: int
    drawn_at: datetime = Field(sa_type=DateTime(timezone=True))
    # worker 處理過「賽事開始」的時間（轉為進行中，或賽事已不是賽程已公布而略過）；
    # 標記後不再被選為候選，避免 competition 直接查 tournament 表
    start_handled_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )


class Match(SQLModel, table=True):
    """場次。結構、編號與輪空取自 `bracket.py`；狀態只能經 `service.transition_match` 修改。"""

    __tablename__ = "match"
    __table_args__ = (
        UniqueConstraint(
            "bracket_id",
            "round_no",
            "slot_no",
            "is_third_place",
            name="uq_match_bracket_round_slot",
        ),
        # worker 找申訴期滿的場次
        Index("ix_match_status_appeal_deadline", "status", "appeal_deadline"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    bracket_id: uuid.UUID = Field(foreign_key="bracket.id", index=True)
    tournament_id: uuid.UUID = Field(foreign_key="tournament.id", index=True)
    round_no: int
    slot_no: int
    is_third_place: bool
    code: str = Field(max_length=MATCH_CODE_MAX_LENGTH)
    # 未確定時為 None；隊伍屬 registration，不建跨模組外鍵
    team_a_id: uuid.UUID | None = Field(default=None)
    team_b_id: uuid.UUID | None = Field(default=None)
    # 該方由輪空直接進入本場；輪空多於 P÷4 時兩方都可能是
    bye_a: bool = False
    bye_b: bool = False
    referee_account_id: uuid.UUID | None = Field(default=None, foreign_key="account.id")
    scheduled_at: datetime = Field(sa_type=DateTime(timezone=True))
    status: MatchStatus = Field(sa_type=String(16))
    outcome: MatchOutcome | None = Field(default=None, sa_type=String(16))
    winner_id: uuid.UUID | None = Field(default=None)
    wins_a: int = 0
    wins_b: int = 0
    # 兩隊都確定才有值；只能經 `service.start_forfeit_clock` 設定
    forfeit_deadline: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    appeal_deadline: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    # 只在轉為已確認時寫入（含輪空確認）
    confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    # 勝隊進入的場次；決賽與季軍賽為 None
    next_match_id: uuid.UUID | None = Field(default=None, foreign_key="match.id")
    # 只有準決賽有：敗隊進入季軍賽
    loser_next_match_id: uuid.UUID | None = Field(default=None, foreign_key="match.id")
    updated_at: datetime = Field(
        default_factory=clock.now, sa_type=DateTime(timezone=True)
    )
    # 送出系列結果的記分者與時間（5.4）；判棄權、輪空確認時為 None
    submitted_by: uuid.UUID | None = Field(default=None, foreign_key="account.id")
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class MatchGame(SQLModel, table=True):
    """逐局比分（5.3）；`(match_id, game_no)` 唯一鍵是併發的最後防線。

    規則由 `scoring.py` 判斷；`win_loss` 型態兩個比分為 None。
    """

    __tablename__ = "match_game"
    __table_args__ = (
        UniqueConstraint("match_id", "game_no", name="uq_match_game_match_game_no"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    match_id: uuid.UUID = Field(foreign_key="match.id")
    # 1 起算、連續
    game_no: int
    winner_side: str = Field(sa_type=String(1))
    score_a: int | None = Field(default=None)
    score_b: int | None = Field(default=None)
    # 最後一次登錄（新增或覆寫）的記分者與時間
    recorded_by: uuid.UUID = Field(foreign_key="account.id")
    recorded_at: datetime = Field(sa_type=DateTime(timezone=True))


class CheckIn(SQLModel, table=True):
    """隊長報到紀錄；一隊一場只能報到一次、不能取消，唯一鍵是併發的最後防線。"""

    __tablename__ = "check_in"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_check_in_match_team"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    match_id: uuid.UUID = Field(foreign_key="match.id")
    # 隊伍屬 registration，不建跨模組外鍵
    team_id: uuid.UUID
    account_id: uuid.UUID = Field(foreign_key="account.id")
    at: datetime = Field(sa_type=DateTime(timezone=True))


# ---------------------------------------------------------------- 事件


class BracketDrawn(Event):
    """抽籤完成、對戰表已公布。"""

    tournament_id: uuid.UUID
    bracket_id: uuid.UUID


class MatchResultConfirmed(Event):
    """場次結果已確認（含輪空確認）；雙方棄權或兩方都沒有隊伍時 `winner_id` 為 None。"""

    match_id: uuid.UUID
    winner_id: uuid.UUID | None


class MatchOpponentsDecided(Event):
    """晉級填位後這一場的兩隊都已確定（通知兩隊隊長下一場對手）。"""

    match_id: uuid.UUID


class MatchResultSubmitted(Event):
    """記分者送出系列結果，場次進入申訴期（5.4）。"""

    match_id: uuid.UUID


class TeamCheckedIn(Event):
    """一隊完成報到；`both_checked_in` 表示這場兩隊都已報到。"""

    match_id: uuid.UUID
    team_id: uuid.UUID
    both_checked_in: bool


# ---------------------------------------------------------------- API schema


class CheckInRead(BaseModel):
    match_id: uuid.UUID
    team_id: uuid.UUID
    at: datetime


CheckInStatusReason = Literal[
    "teams_pending",
    "already_checked_in",
    "too_early",
    "closed",
    "not_checkable",
    "not_captain",
]


class CheckInStatus(BaseModel):
    """登入者對某場次的報到狀態（S4 Check-in panel 用，和報到 API 同一套檢查）。"""

    # 登入者是 a 或 b 隊的隊長；不是隊長、或兩隊未確定時為 None
    side: Literal["a", "b"] | None
    # None 代表現在可以報到；否則是 `CheckInPanel` 吃的原因代碼
    reason: CheckInStatusReason | None
    # 報到開放時間
    opens_at: datetime


class MatchRead(BaseModel):
    id: uuid.UUID
    tournament_id: uuid.UUID
    round_no: int
    slot_no: int
    is_third_place: bool
    code: str
    team_a_id: uuid.UUID | None
    team_b_id: uuid.UUID | None
    bye_a: bool
    bye_b: bool
    referee_account_id: uuid.UUID | None
    scheduled_at: datetime
    status: MatchStatus
    outcome: MatchOutcome | None
    winner_id: uuid.UUID | None
    wins_a: int
    wins_b: int
    forfeit_deadline: datetime | None
    appeal_deadline: datetime | None
    next_match_id: uuid.UUID | None
    loser_next_match_id: uuid.UUID | None


class BracketRead(BaseModel):
    id: uuid.UUID
    tournament_id: uuid.UUID
    size: int
    rounds: int
    drawn_at: datetime
    # 因最小間隔大於每輪間隔而被順延的輪次（S27 提示主辦方）
    delayed_rounds: list[int]
    matches: list[MatchRead]


class PublicTeamRef(BaseModel):
    id: uuid.UUID
    name: str


class PublicMatch(BaseModel):
    """公開 API 用（AD-19）：不含 Email、學校、截圖鍵值。"""

    id: uuid.UUID
    code: str
    round_no: int
    slot_no: int
    is_third_place: bool
    team_a: PublicTeamRef | None
    team_b: PublicTeamRef | None
    # 待定時的說明，例如「M4 勝者」「M29 敗者」；該方已有隊伍、或確定不會有隊伍時為 None
    source_a: str | None
    source_b: str | None
    # 該方由輪空直接進入本輪，前端標「輪空」
    bye_a: bool
    bye_b: bool
    scheduled_at: datetime
    status: MatchStatus
    outcome: MatchOutcome | None
    winner_id: uuid.UUID | None
    wins_a: int
    wins_b: int


class PublicPodium(BaseModel):
    """名次；從缺為 None。"""

    champion: PublicTeamRef | None
    runner_up: PublicTeamRef | None
    third_place: PublicTeamRef | None


class PublicBracket(BaseModel):
    tournament_id: uuid.UUID
    rounds: int
    round_names: list[str]
    matches: list[PublicMatch]
    # 賽事結束後才有；未結束為 None
    podium: PublicPodium | None
    updated_at: datetime


class PublicGame(BaseModel):
    """已登錄的一局（公開）；段位截圖不出現在公開 API（AD-19）。"""

    # 1 起算
    game_no: int
    winner_side: Literal["a", "b"]
    # rounds 型態的回合數；win_loss 型態為 None
    score_a: int | None
    score_b: int | None


class PublicTournamentRef(BaseModel):
    id: uuid.UUID
    name: str


class PublicMatchDetail(PublicMatch):
    """公開單場（5.8 S4 場次頁）：`PublicMatch` 加上賽事、輪次與同輪場次。"""

    tournament: PublicTournamentRef
    game_name: str
    # 本輪 BO
    best_of: int
    score_type: ScoreType
    round_name: str
    # 逐局資料表（5.3 第二階段）建立前一律為空
    games: list[PublicGame]
    # 同一輪的其他場次（不含自己），依 slot_no、季軍賽在最後
    same_round: list[PublicMatch]
    # 只在申訴期、申訴中有值，其他狀態為 None
    appeal_deadline: datetime | None
    # 這場與同輪其他場次 updated_at 的最大值
    updated_at: datetime
    # 兩隊的報到時間（公開）；未報到或該方未確定為 None
    check_in_a_at: datetime | None = None
    check_in_b_at: datetime | None = None


# ---------------------------------------------------------------- 比分登錄（5.3、5.4）

# 回合數範圍（使用者 2026-11-01 決定）；超出由 schema 回 422
ROUND_SCORE_MAX = 99

RoundScore = Annotated[int, PydanticField(ge=0, le=ROUND_SCORE_MAX, strict=True)]


class GameScoreIn(BaseModel):
    """登錄一局的比分。`win_loss` 只給 `winner_side`；`rounds` 只給 `score_a`、`score_b`。

    型態不符（例如 `win_loss` 給數字）由 `scoring.make_game` 判斷，回 409 `SCORE_INVALID`。
    名稱避開 tournaments 的 `GameIn`（遊戲設定），以免 OpenAPI schema 重名。
    """

    winner_side: Literal["a", "b"] | None = None
    score_a: RoundScore | None = None
    score_b: RoundScore | None = None


class SeriesRead(BaseModel):
    """系列結果（`scoring.series` 的結果）。"""

    wins_a: int
    wins_b: int
    # 達到勝局門檻的一方；未達（或有多餘的局）為 None
    winner: Literal["a", "b"] | None
    can_submit: bool
    # 勝局門檻＝（BO＋1）÷ 2
    wins_needed: int
    # 不能送出的原因：`not_decided`（搭配門檻顯示）或 `redundant_games`；能送出為 None
    reason: SeriesReason | None


ScoreEntryReason = Literal[
    "not_accepting_scores",
    "result_submitted",
    "not_recordable",
    "teams_pending",
    "check_in_incomplete",
]


class ScoreEntryState(BaseModel):
    """登入者對某場次的比分登錄狀態（S4 Score entry panel 用）。

    不是記分者時 `is_scorer` 為 False，其他欄位都是空值（不洩漏送出者）。
    """

    is_scorer: bool
    # 現在不能登錄的原因（和寫入 API 同一套檢查，比分規則的原因不在這裡）；可以登錄為 None
    reason: ScoreEntryReason | None = None
    # 已登錄的局，依局號
    games: list[PublicGame] = []
    series: SeriesRead | None = None
    # 送出者的顯示名稱與送出時間；尚未送出為 None
    submitted_by_name: str | None = None
    submitted_at: datetime | None = None
