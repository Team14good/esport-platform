"""Story 3.10：自訂模式的先到先得分配（第 1 部分，I/O 矩陣 registration 層）。

本部分沒有建立自訂賽事的介面，所以建立賽事後直接把賽事列改成自訂模式（比照
test_reject_registration.py 的 `_set_mode`）。前置報名直接寫入報名列（`_custom_preset`，
學校快照為 null，與自訂賽事送出時相同），被測的送出、撤回、退回、提高名額經 API；
取消資格、報名截止、抽籤後遞補呼叫 registration 的公開函式（經 competition 的流程在
tests/competition/test_custom_post_draw_backfill.py）。

平行送出在 test_custom_concurrency.py；「先鎖再判定」用另一條連線真正鎖住賽事列，在本檔檔尾。

`frozen_clock` 固定在 2026-10-18 11:00 UTC（下稱 T）；賽事報名從 T−1 小時開始、優先期
1 小時（沿用 3.5 的 `_tournament`），自訂模式不看優先期，所以 T 當下送出也立即分配。
"""

import secrets
import threading
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core.db import engine
from app.modules.identity.models import Account, School
from app.modules.registration import repository, service
from app.modules.registration.models import Registration, RegistrationStatus, Team
from app.modules.tournaments.models import (
    Tournament,
    TournamentMode,
    TournamentRead,
    TournamentStatus,
)
from tests.conftest import FrozenClock
from tests.registration.test_custom_concurrency import _setup_custom
from tests.registration.test_first_come_concurrency import _cleanup
from tests.registration.test_first_come_submission import (
    _api_team,
    _changes,
    _submit_ok,
    _tournament,
)
from tests.registration.test_raise_capacity import _raise
from tests.registration.test_reject_registration import _reject_ok, _set_mode
from tests.registration.test_settlement_concurrency import _cancel
from tests.registration.test_submit_registration import (
    _detail,
    _fill,
    _registration,
    _school,
    _set_school,
    _submit,
)
from tests.registration.test_teams import (
    API,
    _auth,
    _create_ok,
    _error_code,
    _join,
    _make_account,
    _set_status,
)
from tests.registration.test_withdraw_registration import (
    _backfilled_ids,
    _card,
    _events,
    _status,
    _withdraw_ok,
)

S = RegistrationStatus
CUSTOM_RULE_PHASE = "custom"


# ---------------------------------------------------------------- 測試資料


def _custom(
    session: Session, frozen_clock: FrozenClock, **overrides: Any
) -> TournamentRead:
    """自訂賽事（每隊 1 人就能送出，除非另給 `starters`）。"""
    tournament = _tournament(session, frozen_clock, **overrides)
    _set_mode(session, tournament.id, TournamentMode.CUSTOM)
    return service._get_tournament(session, tournament.id)


def _at(tournament: TournamentRead, minutes: int) -> datetime:
    """早於被測操作的送出時間（報名開始後 `minutes` 分鐘）。"""
    return tournament.registration_start + timedelta(minutes=minutes)


def _custom_preset(
    session: Session,
    tournament: TournamentRead,
    status: S,
    *,
    minutes: int,
    score: str = "30",
    school: School | None = None,
    team_id: Any = None,
) -> Registration:
    """直接寫入一筆已送出的報名；學校快照預設為 null（自訂賽事送出時一律為 null）。"""
    if team_id is None:
        team = Team(
            tournament_id=tournament.id,
            name=f"自訂隊-{uuid.uuid4().hex[:8]}",
            invite_token=secrets.token_urlsafe(24),
        )
        session.add(team)
        session.flush()
        registration = Registration(
            team_id=team.id, tournament_id=tournament.id, status=status
        )
    else:
        found = repository.get_registration_by_team(session, uuid.UUID(str(team_id)))
        assert found is not None
        registration = found
    registration.status = status
    registration.school_id = None if school is None else school.id
    registration.avg_rank_score = Decimal(score)
    registration.submitted_at = _at(tournament, minutes)
    session.add(registration)
    session.flush()
    return registration


def _custom_team(
    client: TestClient,
    session: Session,
    tournament: TournamentRead,
    status: S,
    *,
    minutes: int,
    school: School | None = None,
) -> tuple[dict[str, Any], Account, Registration]:
    """經 API 建立的一人隊伍（隊長沒有學校），報名直接改成 `status`。"""
    captain = _make_account(session, display_name=f"隊長{uuid.uuid4().hex[:4]}")
    team = _create_ok(client, captain, tournament.id, name=f"隊-{uuid.uuid4().hex[:8]}")
    _fill(session, team["id"], captain)
    registration = _custom_preset(
        session, tournament, status, minutes=minutes, school=school, team_id=team["id"]
    )
    return team, captain, registration


def _allocated(session: Session, tournament: TournamentRead) -> list[dict[str, Any]]:
    return _events(session, tournament, "RegistrationAllocated")


def _no_school_team(
    client: TestClient, session: Session, tournament: TournamentRead
) -> tuple[dict[str, Any], Account]:
    """經 API 建立、填完資料、尚未送出的一人隊伍；隊長沒有設定學校。"""
    captain = _make_account(session, display_name=f"隊長{uuid.uuid4().hex[:4]}")
    team = _create_ok(client, captain, tournament.id, name=f"隊-{uuid.uuid4().hex[:8]}")
    _fill(session, team["id"], captain)
    return team, captain


def _organizer(session: Session, tournament: TournamentRead) -> Account:
    account = session.get(Account, tournament.organizer_id)
    assert account is not None
    return account


# ---------------------------------------------------------------- 送出


def test_submit_with_capacity_is_accepted_without_school_checks(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """有名額送出：隊員學校不同、有人沒設學校也能送出，立即正取，學校快照為 null。

    送出時間在優先期內（T），校園賽會維持 `pending`；自訂不看優先期，也不結算。
    """
    tournament = _custom(session, frozen_clock, starters=3, capacity=2)
    captain = _make_account(session, display_name="阿哲")
    team = _create_ok(client, captain, tournament.id, name="自訂一隊")
    mate_a = _make_account(session, display_name="小芸")
    mate_b = _make_account(session, display_name="阿凱")
    for mate in (mate_a, mate_b):
        assert _join(client, mate, team["invite_token"]).status_code == 200
    _set_school(session, captain, _school(session))
    _set_school(session, mate_a, _school(session))
    _set_school(session, mate_b, None)
    for account in (captain, mate_a, mate_b):
        _fill(session, team["id"], account)

    before = _detail(client, captain, team["id"])
    body = _submit_ok(client, captain, team)

    # S17 不列「未設定學校」「學校不同」
    assert before["submit_blockers"] == []
    assert body["registration_status"] == "accepted"
    assert body["waitlist_position"] is None
    assert body["waitlist_phase"] is None
    registration = _registration(session, team["id"])
    assert registration.status == S.ACCEPTED
    assert registration.school_id is None
    assert registration.avg_rank_score == Decimal("30.00")
    assert registration.submitted_at == frozen_clock.now()
    assert _changes(session, tournament, registration.id) == [
        ("pending", captain.id),
        ("accepted", None),
    ]
    # 報名結果通知：沿用 RegistrationAllocated（通知規則寄給隊長與選手）
    assert _allocated(session, tournament) == [
        {
            "registration_id": str(registration.id),
            "team_id": team["id"],
            "tournament_id": str(tournament.id),
            "status": "accepted",
        }
    ]
    assert repository.get_settlement(session, tournament.id) is None


def test_campus_control_still_checks_schools(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """校園賽不變的對照：同樣沒設學校的隊伍，校園賽 S17 列出並拒絕送出。"""
    tournament = _tournament(session, frozen_clock)
    team, captain = _no_school_team(client, session, tournament)

    detail = _detail(client, captain, team["id"])
    response = _submit(client, captain, team["id"])

    assert [b["code"] for b in detail["submit_blockers"]] == ["SCHOOL_MISSING"]
    assert response.status_code == 409
    assert _error_code(response) == "REGISTRATION_REQUIREMENTS_UNMET"
    assert _registration(session, team["id"]).status == S.FORMING


def test_custom_still_checks_starters_and_profiles(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """自訂只跳過學校檢查；人數與參賽資料照常檢查。"""
    tournament = _custom(session, frozen_clock, starters=2)
    captain = _make_account(session, display_name="阿哲")
    team = _create_ok(client, captain, tournament.id, name="缺人隊")

    detail = _detail(client, captain, team["id"])
    response = _submit(client, captain, team["id"])

    assert [b["code"] for b in detail["submit_blockers"]] == [
        "STARTERS_NOT_MET",
        "PROFILE_INCOMPLETE",
    ]
    assert response.status_code == 409
    assert _registration(session, team["id"]).status == S.FORMING


def test_submit_when_full_is_waitlisted_by_submit_time(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """額滿送出：候補第 N 位（依送出時間，不看積分）；回應直接帶順位。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    _custom_preset(session, tournament, S.WAITLISTED, minutes=2, score="10")
    _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="10")
    team, captain = _no_school_team(client, session, tournament)

    body = _submit_ok(client, captain, team)

    assert body["registration_status"] == "waitlisted"
    assert body["waitlist_position"] == 3
    assert body["waitlist_reason"] is None
    assert body["representative_backfill"] is False
    assert body["waitlist_phase"] == CUSTOM_RULE_PHASE
    registration = _registration(session, team["id"])
    assert registration.school_id is None
    [event] = _allocated(session, tournament)
    assert (event["registration_id"], event["status"]) == (
        str(registration.id),
        "waitlisted",
    )


def test_last_seat_goes_to_the_first_submission(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """最後一個名額：先送出的正取，後送出的候補第 1 位。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    first, first_captain = _no_school_team(client, session, tournament)
    second, second_captain = _no_school_team(client, session, tournament)

    a = _submit_ok(client, first_captain, first)
    frozen_clock.advance(timedelta(seconds=1))
    b = _submit_ok(client, second_captain, second)

    assert a["registration_status"] == "accepted"
    assert (b["registration_status"], b["waitlist_position"]) == ("waitlisted", 1)


# ---------------------------------------------------------------- 名額釋出時遞補


def test_withdraw_backfills_earliest_even_with_two_schoolmates_accepted(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """撤回：最早送出的候補遞補並通知；同校已有 2 隊正取、積分較低也遞補（沒有每校上限）。"""
    tournament = _custom(session, frozen_clock, capacity=3)
    school_x = _school(session)
    team, captain, leaving = _custom_team(
        client, session, tournament, S.ACCEPTED, minutes=1, school=school_x
    )
    for minute in (2, 3):
        _custom_preset(session, tournament, S.ACCEPTED, minutes=minute, school=school_x)
    earliest = _custom_preset(
        session, tournament, S.WAITLISTED, minutes=4, score="10", school=school_x
    )
    later = _custom_preset(
        session,
        tournament,
        S.WAITLISTED,
        minutes=5,
        score="90",
        school=_school(session),
    )

    body = _withdraw_ok(client, captain, team["id"])

    assert body["registration_status"] == "withdrawn"
    assert _status(session, leaving) == S.WITHDRAWN
    assert _status(session, earliest) == S.ACCEPTED
    assert _status(session, later) == S.WAITLISTED
    assert _registration(session, earliest.team_id).backfilled_at == frozen_clock.now()
    assert _events(session, tournament, "RegistrationBackfilled") == [
        {
            "registration_id": str(earliest.id),
            "team_id": str(earliest.team_id),
            "tournament_id": str(tournament.id),
        }
    ]
    assert _allocated(session, tournament) == []
    assert _changes(session, tournament, earliest.id) == [("accepted", None)]
    assert repository.get_settlement(session, tournament.id) is None


def test_withdraw_without_waitlist_leaves_vacancy(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """沒有候補：名額空著，不出錯。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    team, captain, leaving = _custom_team(
        client, session, tournament, S.ACCEPTED, minutes=1
    )
    other = _custom_preset(session, tournament, S.ACCEPTED, minutes=2)

    _withdraw_ok(client, captain, team["id"])

    assert _status(session, leaving) == S.WITHDRAWN
    assert _status(session, other) == S.ACCEPTED
    assert _backfilled_ids(session, tournament) == set()


def test_withdraw_after_deadline_before_draw_backfills(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """報名截止後、抽籤前撤回：最早送出的候補遞補並通知（FR-17）。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    team, captain, _ = _custom_team(client, session, tournament, S.ACCEPTED, minutes=1)
    earliest = _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    later = _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="99")
    frozen_clock.set(tournament.registration_end + timedelta(minutes=1))
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    _withdraw_ok(client, captain, team["id"])

    assert _status(session, earliest) == S.ACCEPTED
    assert _status(session, later) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(earliest.id)}
    card = _card(client, captain, team["id"])
    assert card["registration_status"] == "withdrawn"


def test_reject_backfills_earliest_waitlisted(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """退回：最早送出的候補遞補並通知；不需優先期結算。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _, _, rejected = _custom_team(client, session, tournament, S.ACCEPTED, minutes=1)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=2)
    earliest = _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="1")
    later = _custom_preset(session, tournament, S.WAITLISTED, minutes=4, score="99")

    body = _reject_ok(client, session, tournament, rejected)

    assert body["status"] == "rejected"
    assert _status(session, earliest) == S.ACCEPTED
    assert _status(session, later) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(earliest.id)}
    assert repository.get_settlement(session, tournament.id) is None


def test_raise_capacity_backfills_in_submit_order(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """提高名額：3 隊候補，名額 2 → 4，依送出順序遞補 2 隊，剩下的變候補第 1 位。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    w1 = _custom_preset(session, tournament, S.WAITLISTED, minutes=2, score="1")
    w2 = _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="5")
    team, captain, w3 = _custom_team(
        client, session, tournament, S.WAITLISTED, minutes=4
    )

    response = _raise(client, _organizer(session, tournament), tournament, 4)

    assert response.status_code == 200, response.text
    assert [_status(session, r) for r in (w1, w2, w3)] == [
        S.ACCEPTED,
        S.ACCEPTED,
        S.WAITLISTED,
    ]
    assert _backfilled_ids(session, tournament) == {str(w1.id), str(w2.id)}
    detail = _detail(client, captain, team["id"])
    assert (detail["waitlist_position"], detail["waitlist_phase"]) == (
        1,
        CUSTOM_RULE_PHASE,
    )


def test_disqualify_accepted_before_draw_backfills(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """抽籤前取消資格（6.5）：正取被取消資格，最早送出的候補立即遞補並通知。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    target = _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    earliest = _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    later = _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="99")

    read = service.disqualify_registration(
        session, team_id=target.team_id, actor_id=tournament.organizer_id
    )

    assert read.status == S.DISQUALIFIED
    assert _status(session, earliest) == S.ACCEPTED
    assert _status(session, later) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == {str(earliest.id)}


def test_disqualify_after_deadline_before_draw_backfills(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """報名截止（`closed`）後、抽籤前取消資格也立即遞補。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    target = _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    earliest = _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    frozen_clock.set(tournament.registration_end + timedelta(minutes=1))
    _set_status(session, tournament.id, TournamentStatus.CLOSED)

    service.disqualify_registration(
        session, team_id=target.team_id, actor_id=tournament.organizer_id
    )

    assert _status(session, earliest) == S.ACCEPTED
    assert _backfilled_ids(session, tournament) == {str(earliest.id)}


def test_disqualify_waitlisted_does_not_backfill(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """被取消的報名原本是候補：沒有釋出名額，不遞補（順位往前）。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    target = _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    other = _custom_preset(session, tournament, S.WAITLISTED, minutes=3)

    service.disqualify_registration(
        session, team_id=target.team_id, actor_id=tournament.organizer_id
    )

    assert _status(session, other) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == set()


def test_campus_control_disqualify_does_not_backfill(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """校園賽不變的對照：抽籤前取消資格不立即遞補（留給之後的分配）。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _custom_preset(
        session, tournament, S.ACCEPTED, minutes=0, school=_school(session)
    )  # 名額下限為 2
    target = _custom_preset(
        session, tournament, S.ACCEPTED, minutes=1, school=_school(session)
    )
    waiting = _custom_preset(
        session, tournament, S.WAITLISTED, minutes=2, school=_school(session)
    )

    service.disqualify_registration(
        session, team_id=target.team_id, actor_id=tournament.organizer_id
    )

    assert _status(session, waiting) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == set()


def test_disqualify_after_draw_does_not_backfill_itself(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """抽籤後取消資格：取消資格本身不產生 `accepted`、不發 `RegistrationBackfilled`；
    之後由 4.5 的 `backfill_drawn_from_waitlist` 讓最早送出的候補接手。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    target = _custom_preset(session, tournament, S.DRAWN, minutes=1)
    _custom_preset(session, tournament, S.DRAWN, minutes=2)
    earliest = _custom_preset(session, tournament, S.WAITLISTED, minutes=3, score="1")
    later = _custom_preset(session, tournament, S.WAITLISTED, minutes=4, score="99")
    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)

    service.disqualify_registration(
        session, team_id=target.team_id, actor_id=tournament.organizer_id
    )

    assert _status(session, earliest) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == set()
    assert service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=target.team_id
    )
    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)
    assert chosen == earliest.team_id
    assert _status(session, earliest) == S.DRAWN
    assert _status(session, later) == S.WAITLISTED
    assert _backfilled_ids(session, tournament) == set()


def test_retire_after_draw_earliest_takes_over_without_school_limit(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """抽籤後退賽：最早送出的候補接手（同校已有 2 隊已參賽也一樣，不看積分）。"""
    tournament = _custom(session, frozen_clock, capacity=3)
    school_x = _school(session)
    leaving = _custom_preset(session, tournament, S.DRAWN, minutes=1, school=school_x)
    for minute in (2, 3):
        _custom_preset(session, tournament, S.DRAWN, minutes=minute, school=school_x)
    earliest = _custom_preset(
        session, tournament, S.WAITLISTED, minutes=4, score="1", school=school_x
    )
    _custom_preset(session, tournament, S.WAITLISTED, minutes=5, score="99")
    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)

    assert service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=leaving.team_id
    )
    service.retire_registration(
        session, team_id=leaving.team_id, actor_id=tournament.organizer_id
    )
    chosen = service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)

    assert chosen == earliest.team_id
    assert _status(session, earliest) == S.DRAWN


def test_post_draw_without_waitlist_returns_none(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """抽籤後沒有候補：沒有人可接手（4.5 照常輪空）。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    leaving = _custom_preset(session, tournament, S.DRAWN, minutes=1)
    _set_status(session, tournament.id, TournamentStatus.PUBLISHED)

    assert not service.has_backfill_candidate(
        session, tournament_id=tournament.id, leaving_team_id=leaving.team_id
    )
    assert (
        service.backfill_drawn_from_waitlist(session, tournament_id=tournament.id)
        is None
    )


# ---------------------------------------------------------------- 報名截止


def test_close_registration_only_transitions(
    session: Session, frozen_clock: FrozenClock
) -> None:
    """報名截止：只轉「報名截止」，即使有空位也不補位，正取與候補不變、不發事件。"""
    tournament = _custom(session, frozen_clock, capacity=3)
    accepted = _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    # 直接寫入的空位＋候補（正常不會出現：釋出時已立即遞補），確認截止不補位
    waiting = _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    frozen_clock.set(tournament.registration_end)

    assert service.close_registration(session, tournament_id=tournament.id)

    assert service._get_tournament(session, tournament.id).status == (
        TournamentStatus.CLOSED
    )
    assert _status(session, accepted) == S.ACCEPTED
    assert _status(session, waiting) == S.WAITLISTED
    assert _allocated(session, tournament) == []
    assert _backfilled_ids(session, tournament) == set()
    assert repository.get_settlement(session, tournament.id) is None


# ---------------------------------------------------------------- 候補畫面


def test_waitlist_views_show_custom_phase(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """S17、S12、S29：候補第 N 位、階段 `custom`、沒有原因；學校快照為 null 也能列出。"""
    tournament = _custom(session, frozen_clock, capacity=2)
    _custom_preset(session, tournament, S.ACCEPTED, minutes=0)  # 名額下限為 2
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1)
    _custom_preset(session, tournament, S.WAITLISTED, minutes=2)
    team, captain, registration = _custom_team(
        client, session, tournament, S.WAITLISTED, minutes=3
    )
    expected = {
        "waitlist_position": 2,
        "waitlist_reason": None,
        "representative_backfill": False,
        "waitlist_phase": CUSTOM_RULE_PHASE,
    }

    detail = _detail(client, captain, team["id"])
    card = _card(client, captain, team["id"])
    response = client.get(
        f"{API}/organizer/tournaments/{tournament.id}/registrations",
        headers=_auth(_organizer(session, tournament)),
    )

    assert {k: detail[k] for k in expected} == expected
    assert {k: card[k] for k in expected} == expected
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["status"] for i in items] == [
        "accepted",
        "accepted",
        "waitlisted",
        "waitlisted",
    ]
    row = next(i for i in items if i["registration_id"] == str(registration.id))
    assert {k: row[k] for k in expected} == expected


def test_campus_control_waitlist_phase_unchanged(
    client: TestClient, session: Session, frozen_clock: FrozenClock
) -> None:
    """校園賽不變的對照：報名截止後的候補階段仍是 `after_deadline`。"""
    tournament = _tournament(session, frozen_clock, capacity=2)
    _custom_preset(
        session, tournament, S.ACCEPTED, minutes=0, school=_school(session)
    )  # 名額下限為 2
    team, captain = _api_team(client, session, tournament, _school(session))
    _custom_preset(session, tournament, S.ACCEPTED, minutes=1, school=_school(session))
    _custom_preset(
        session,
        tournament,
        S.WAITLISTED,
        minutes=2,
        school=_school(session),
        team_id=team["id"],
    )
    frozen_clock.set(tournament.registration_end + timedelta(minutes=1))

    detail = _detail(client, captain, team["id"])

    assert (detail["waitlist_position"], detail["waitlist_phase"]) == (
        1,
        "after_deadline",
    )


# ---------------------------------------------------------------- 先鎖再判定（AD-6）


def test_submit_waits_for_the_tournament_lock_then_decides() -> None:
    """另一條連線先鎖住賽事列並占走最後一個名額：送出會等鎖，拿到鎖後才判定為候補。

    資料要真正提交，另一條連線才看得到，所以不用 `session` fixture（比照
    test_custom_concurrency.py）。若送出先判定再鎖（或不鎖），會在等鎖前看到空位而正取。
    """
    tournament, team_ids, submitters = _setup_custom(
        capacity=2, teams=1, preset_accepted=1
    )
    [(team_id, captain_id)] = submitters
    outcome: list[str] = []

    def _run() -> None:
        with Session(engine) as db:
            try:
                detail = service.submit_registration(
                    db, team_id=team_id, account_id=captain_id
                )
                db.commit()
                outcome.append(str(detail.registration_status))
            except Exception as exc:  # 讓非預期錯誤出現在斷言訊息裡
                outcome.append(repr(exc))

    try:
        with Session(engine) as holder:
            holder.exec(
                select(Tournament)
                .where(col(Tournament.id) == tournament.id)
                .with_for_update()
            ).one()
            submitter = threading.Thread(target=_run)
            submitter.start()
            submitter.join(timeout=1.5)
            assert submitter.is_alive(), outcome  # 等鎖中，還沒判定
            seat = Team(
                tournament_id=tournament.id,
                name=f"占位隊-{uuid.uuid4().hex[:8]}",
                invite_token=secrets.token_urlsafe(24),
            )
            holder.add(seat)
            holder.flush()
            team_ids.append(seat.id)
            holder.add(
                Registration(
                    team_id=seat.id,
                    tournament_id=tournament.id,
                    status=S.ACCEPTED,
                    avg_rank_score=Decimal(30),
                    submitted_at=tournament.registration_start,
                )
            )
            holder.commit()
        submitter.join(timeout=30)

        assert not submitter.is_alive()
        assert outcome == ["waitlisted"]
    finally:
        _cleanup(tournament.id, team_ids)
        _cancel(tournament.id)
