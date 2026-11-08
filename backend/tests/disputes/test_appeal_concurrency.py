"""AD-6：真實 PostgreSQL 上提出申訴與 worker 期滿確認同時發生時，只有一方成功。

兩邊都先 `lock_tournament` 再 `lock_match`，鎖住後才判斷場次狀態與期限。一方持有鎖、
尚未提交時另一方開始執行：後到的一方必須等鎖，鎖到後看到前者的結果而放棄。把
`file_appeal` 改成鎖之前就判斷狀態（或不加鎖）時，申訴會在場次已確認後仍然成功，
這裡的斷言就會失敗。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture。被只增不改的
操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫（比照 registration 的併發測試）；
申訴、場次、對戰表與事件在結束時刪除，避免其他測試的 worker 挑到這些場次。
"""

import random
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import String, cast, delete, or_
from sqlmodel import Session, col, select

from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.competition import service as competition_service
from app.modules.competition.models import Bracket, Match, MatchOutcome, MatchStatus
from app.modules.disputes import service
from app.modules.disputes.models import Appeal
from app.modules.registration import service as registration_service
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.competition.conftest import (  # noqa: F401  fake_registration 是 fixture
    FakeRegistration,
    fake_registration,
)
from tests.conftest import FrozenClock
from tests.helpers import make_account, make_game, make_tournament
from tests.registration.test_team_concurrency import _demote_game_creator

DEADLINE = datetime(2026, 10, 18, 11, 30, tzinfo=UTC)
# 後到的一方在這段時間內仍未結束，代表它正在等鎖
BLOCKED_SECONDS = 0.5


@dataclass
class Committed:
    tournament_id: uuid.UUID
    bracket_id: uuid.UUID
    match_id: uuid.UUID
    captain_id: uuid.UUID


@pytest.fixture
def committed(
    frozen_clock: FrozenClock,  # noqa: ARG001  凍結時鐘（draw 與期限以它為準）
    fake_registration: FakeRegistration,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Committed]:
    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        organizer = make_account(setup, organizer=True)
        tournament = make_tournament(setup, organizer=organizer, game=game)
        row = setup.get(Tournament, tournament.id)
        assert row is not None
        row.status = TournamentStatus.CLOSED
        setup.add(row)
        setup.flush()
        fake_registration.set_team_count(2)
        bracket = competition_service.draw(
            setup,
            tournament_id=tournament.id,
            actor_id=organizer.id,
            rng=random.Random(7),
        )
        match = setup.get(Match, bracket.matches[0].id)
        assert match is not None and match.team_a_id is not None
        match.status = MatchStatus.APPEAL_WINDOW
        match.outcome = MatchOutcome.PLAYED
        match.winner_id = match.team_a_id
        match.appeal_deadline = DEADLINE
        setup.add(match)
        captain = make_account(setup)
        setup.commit()
        data = Committed(tournament.id, bracket.id, match.id, captain.id)
        team_a = match.team_a_id

    def is_captain(
        _session: Session, *, team_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        return team_id == team_a and account_id == data.captain_id

    monkeypatch.setattr(registration_service, "is_captain", is_captain)
    try:
        yield data
    finally:
        with Session(engine) as cleanup:
            appeal_ids = list(
                cleanup.exec(
                    select(Appeal.id).where(Appeal.match_id == data.match_id)
                ).all()
            )
            ids = [data.tournament_id, data.bracket_id, data.match_id, *appeal_ids]
            text = cast(OutboxEvent.payload, String)
            cleanup.execute(
                delete(OutboxEvent).where(
                    or_(*(text.contains(str(value)) for value in ids))
                )
            )
            cleanup.execute(delete(Appeal).where(col(Appeal.match_id) == data.match_id))
            cleanup.execute(
                delete(Match).where(col(Match.bracket_id) == data.bracket_id)
            )
            cleanup.execute(delete(Bracket).where(col(Bracket.id) == data.bracket_id))
            cleanup.commit()


def _file(db: Session, data: Committed) -> None:
    service.file_appeal(
        db,
        tournament_id=data.tournament_id,
        match_id=data.match_id,
        account_id=data.captain_id,
        description="比分有誤",
        attachment=None,
        content_type=None,
    )


def _run_in_thread(
    work: Callable[[Session], object],
) -> tuple[threading.Thread, list[object]]:
    """在另一條連線執行 `work` 並提交；結果（"ok"、錯誤碼或例外）放進回傳的 list。"""
    outcome: list[object] = []

    def _target() -> None:
        with Session(engine) as db:
            try:
                result = work(db)
                db.commit()
                outcome.append(("ok", result))
            except BusinessError as exc:
                outcome.append(exc.code)
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                outcome.append(repr(exc))

    thread = threading.Thread(target=_target)
    thread.start()
    return thread, outcome


def _status(match_id: uuid.UUID) -> MatchStatus:
    with Session(engine) as check:
        match = check.get(Match, match_id)
        assert match is not None
        return MatchStatus(match.status)


def _appeal_count(match_id: uuid.UUID) -> int:
    with Session(engine) as check:
        return len(check.exec(select(Appeal).where(Appeal.match_id == match_id)).all())


def test_appeal_waits_for_worker_and_is_rejected(
    committed: Committed, frozen_clock: FrozenClock
) -> None:
    """worker 先鎖住並確認場次；同時送出的申訴等鎖，鎖到後看到已確認而拒絕。"""
    with Session(engine) as worker:
        frozen_clock.set(DEADLINE)
        assert competition_service.auto_confirm_expired(worker) is True
        # 申訴請求在期限前一秒抵達：只有鎖住後重查狀態才擋得下來
        frozen_clock.set(DEADLINE - timedelta(seconds=1))
        thread, outcome = _run_in_thread(lambda db: _file(db, committed))
        thread.join(timeout=BLOCKED_SECONDS)
        assert thread.is_alive(), f"申訴沒有等 worker 的鎖：{outcome}"
        worker.commit()
    thread.join(timeout=30)
    assert not thread.is_alive()

    assert outcome == ["APPEAL_NOT_ALLOWED"]
    assert _status(committed.match_id) == MatchStatus.CONFIRMED
    assert _appeal_count(committed.match_id) == 0


def test_worker_waits_for_appeal_and_skips(
    committed: Committed, frozen_clock: FrozenClock
) -> None:
    """申訴先鎖住並把場次轉為申訴中；同時到期的 worker 等鎖，鎖到後不確認。"""
    with Session(engine) as appeal:
        frozen_clock.set(DEADLINE - timedelta(seconds=1))
        _file(appeal, committed)
        # worker 在期限到時執行：鎖外的候選查詢仍看到未提交前的申訴期
        frozen_clock.set(DEADLINE)
        thread, outcome = _run_in_thread(competition_service.auto_confirm_expired)
        thread.join(timeout=BLOCKED_SECONDS)
        assert thread.is_alive(), f"worker 沒有等申訴的鎖：{outcome}"
        appeal.commit()
    thread.join(timeout=30)
    assert not thread.is_alive()

    assert outcome == [("ok", True)]
    assert _status(committed.match_id) == MatchStatus.APPEALED
    assert _appeal_count(committed.match_id) == 1
