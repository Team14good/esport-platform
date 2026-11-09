"""AD-6：真實 PostgreSQL 上同一隊長平行送出兩筆對同一隊伍的檢舉，只成功一筆。

`file_report` 先以 `lock_tournament` 鎖住賽事列再檢查有沒有處理中的檢舉，兩邊依序
執行；後到的一方在鎖內看到已有處理中的檢舉，回 409 `REPORT_ALREADY_FILED`。

為了讓測試真的依賴鎖，「有沒有處理中的檢舉」的查詢被包了一層：先做完檢查的執行緒會
等到另一個執行緒也做完檢查（最多 1 秒）才繼續寫入，刻意拉開檢查與寫入的時間差。
有鎖時另一個執行緒被擋在鎖外，先到的一方逾時後寫入並提交，結果只成功一筆；把鎖換成
不加鎖的讀取時，兩邊都在對方寫入前檢查完，兩筆都會寫入，這裡的斷言就會失敗
（2026-11-09 實際拿掉鎖驗證過，見 spec-6-4-file-report.md 的 Review Triage Log）。

資料要真正提交，另一條連線才看得到，所以不用外層交易的 `session` fixture。被只增不改
的操作紀錄參照的賽事、遊戲與帳號刪不掉，留在測試資料庫（比照
`tests/registration/test_settlement_concurrency.py`）；檢舉、事件、報名、隊員與隊伍在
結束時刪除，賽事改為已取消，避免被 worker 的測試撿到。
"""

import secrets
import threading
import uuid

import pytest
from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from app.core.db import engine
from app.core.errors import BusinessError
from app.core.events import OutboxEvent
from app.modules.disputes import repository as disputes_repository
from app.modules.disputes import service
from app.modules.disputes.models import Report
from app.modules.registration.models import (
    MemberRole,
    Registration,
    RegistrationStatus,
    Team,
    TeamMember,
)
from app.modules.tournaments.models import Tournament, TournamentStatus
from tests.helpers import make_account, make_game, make_tournament
from tests.registration.test_team_concurrency import _demote_game_creator


def _team_with_captain(
    session: Session, tournament_id: uuid.UUID, captain_id: uuid.UUID
) -> uuid.UUID:
    team = Team(
        tournament_id=tournament_id,
        name=f"併發檢舉-{uuid.uuid4().hex[:8]}",
        invite_token=secrets.token_urlsafe(24),
    )
    session.add(team)
    session.flush()
    session.add(
        TeamMember(
            team_id=team.id,
            tournament_id=tournament_id,
            account_id=captain_id,
            role=MemberRole.CAPTAIN,
        )
    )
    session.add(
        Registration(
            team_id=team.id,
            tournament_id=tournament_id,
            status=RegistrationStatus.ACCEPTED,
        )
    )
    session.flush()
    return team.id


def test_parallel_duplicate_reports_only_one_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_check = disputes_repository.list_open_reported_team_ids
    checks = 0
    checks_lock = threading.Lock()
    second_checked = threading.Event()
    first_timed_out: list[bool] = []

    def gated_check(session: Session, reporter_team_id: uuid.UUID) -> set[uuid.UUID]:
        nonlocal checks
        result = real_check(session, reporter_team_id)
        with checks_lock:
            checks += 1
            first = checks == 1
        if first:
            # 先檢查的一方等另一方也檢查完才寫入；有鎖時對方進不來，等到逾時。
            # 1 秒遠大於兩條連線從 Barrier 到檢查所需的時間（約數十毫秒）
            first_timed_out.append(not second_checked.wait(timeout=1))
        else:
            second_checked.set()
        return result

    monkeypatch.setattr(disputes_repository, "list_open_reported_team_ids", gated_check)

    with Session(engine) as setup:
        game = make_game(setup)
        _demote_game_creator(setup, game.id)
        tournament = make_tournament(setup, game=game)
        reporter = make_account(setup)
        reported_captain = make_account(setup)
        reporter_team_id = _team_with_captain(setup, tournament.id, reporter.id)
        reported_team_id = _team_with_captain(setup, tournament.id, reported_captain.id)
        setup.commit()
        tournament_id, reporter_id = tournament.id, reporter.id
    team_ids = [reporter_team_id, reported_team_id]

    start = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def _run() -> None:
        with Session(engine) as db:
            try:
                start.wait(timeout=10)
                service.file_report(
                    db,
                    tournament_id=tournament_id,
                    account_id=reporter_id,
                    reported_team_id=reported_team_id,
                    description="隊員不同校",
                    attachment=None,
                    content_type=None,
                )
                db.commit()
                result = "ok"
            except BusinessError as exc:
                result = exc.code
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                result = repr(exc)
        with outcomes_lock:
            outcomes.append(result)

    threads: list[threading.Thread] = []
    try:
        threads = [threading.Thread(target=_run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)

        assert sorted(outcomes) == ["REPORT_ALREADY_FILED", "ok"], outcomes
        # 兩邊都走到了檢查；先檢查的一方是等到逾時才繼續，不是被另一方喚醒，
        # 表示它持鎖等待時，另一方被擋在 `lock_tournament` 外、還沒做檢查
        assert checks == 2
        assert first_timed_out == [True]
        with Session(engine) as check:
            reports = check.exec(
                select(Report).where(Report.tournament_id == tournament_id)
            ).all()
            assert len(reports) == 1
            assert len(_filed_events(check, tournament_id)) == 1
    finally:
        for thread in threads:
            thread.join(timeout=10)
        with Session(engine) as cleanup:
            event_ids = [e.id for e in _filed_events(cleanup, tournament_id)]
            cleanup.execute(
                delete(Report).where(col(Report.tournament_id) == tournament_id)
            )
            cleanup.execute(
                delete(OutboxEvent).where(col(OutboxEvent.id).in_(event_ids))
            )
            cleanup.execute(
                delete(Registration).where(
                    col(Registration.tournament_id) == tournament_id
                )
            )
            cleanup.execute(
                delete(TeamMember).where(col(TeamMember.team_id).in_(team_ids))
            )
            cleanup.execute(delete(Team).where(col(Team.id).in_(team_ids)))
            cleanup.execute(
                update(Tournament)
                .where(col(Tournament.id) == tournament_id)
                .values(status=TournamentStatus.CANCELLED)
            )
            cleanup.commit()


def _filed_events(session: Session, tournament_id: uuid.UUID) -> list[OutboxEvent]:
    rows = session.exec(
        select(OutboxEvent).where(OutboxEvent.type == "ReportFiled")
    ).all()
    return [row for row in rows if row.payload["tournament_id"] == str(tournament_id)]
