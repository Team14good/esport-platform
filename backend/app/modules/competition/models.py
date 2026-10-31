"""competition 的資料表、schema 與列舉。"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core import clock
from app.core.events import Event


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


# ---------------------------------------------------------------- API schema


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
