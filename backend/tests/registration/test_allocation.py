"""AllocationPolicy（registration/allocation.py）的單元測試；純函式，不需資料庫。"""

import ast
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from app.modules.registration import allocation
from app.modules.registration.allocation import (
    REASON_MESSAGES,
    REPRESENTATIVE_BACKFILL_MESSAGE,
    AllocationPhase,
    Candidate,
    PriorityAllocation,
    WaitlistEntry,
    WaitlistReason,
    allocate_priority_window,
    decide_first_come,
    fill_from_waitlist,
    sort_key,
    waitlist_order,
)
from app.modules.registration.models import RegistrationStatus as S

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
FIRST = AllocationPhase.FIRST_COME
AFTER = AllocationPhase.AFTER_DEADLINE


def uid(n: int) -> UUID:
    return UUID(int=n)


def school(n: int) -> UUID:
    return UUID(int=10_000 + n)


def cand(
    n: int,
    sch: int,
    score: str | int = 1000,
    minute: int = 0,
    status: S = S.PENDING,
) -> Candidate:
    return Candidate(
        id=uid(n),
        school_id=school(sch),
        avg_rank_score=Decimal(score),
        submitted_at=T0 + timedelta(minutes=minute),
        status=status,
    )


def shuffled(items: list[Candidate], seed: int) -> list[Candidate]:
    copy = list(items)
    random.Random(seed).shuffle(copy)
    return copy


# ── 排序鍵 ─────────────────────────────────────────────


def test_sort_key_orders_by_score_then_submit_time_then_id() -> None:
    high = cand(5, 1, "1500.50", minute=9)
    early = cand(4, 2, "1500.00", minute=1)
    late_small_id = cand(1, 3, "1500.00", minute=2)
    late_big_id = cand(2, 4, "1500.00", minute=2)
    ordered = sorted([late_big_id, late_small_id, early, high], key=sort_key)
    assert ordered == [high, early, late_small_id, late_big_id]


# ── 優先期結算 ─────────────────────────────────────────


def test_priority_40_schools_for_32_slots() -> None:
    cs = [cand(i, i, 1000 + i, minute=i) for i in range(1, 41)]
    result = allocate_priority_window(cs, capacity=32)
    expected = [c.id for c in sorted(cs, key=sort_key)]
    assert result.accepted == tuple(expected[:32])
    assert result.waitlisted == tuple(expected[32:])
    assert len(result.accepted) == 32 and len(result.waitlisted) == 8


def test_priority_same_school_three_teams_only_best_accepted() -> None:
    cs = [cand(1, 1, 1200), cand(2, 1, 1500), cand(3, 1, 1300), cand(4, 2, 900)]
    result = allocate_priority_window(cs, capacity=10)
    assert result.accepted == (uid(2), uid(4))
    assert result.waitlisted == (uid(3), uid(1))


def test_priority_tie_earlier_submit_then_smaller_id_wins() -> None:
    # 同校兩隊同分：先送出者為代表隊
    r = allocate_priority_window(
        [cand(1, 1, 1000, minute=5), cand(2, 1, 1000, minute=3)], capacity=1
    )
    assert r.accepted == (uid(2),)
    # 不同校同分同時間，名額 1：id 小者正取
    r = allocate_priority_window(
        [cand(9, 1, 1000, minute=3), cand(7, 2, 1000, minute=3)], capacity=1
    )
    assert r == PriorityAllocation(accepted=(uid(7),), waitlisted=(uid(9),))


def test_priority_zero_capacity_all_waitlisted_and_empty_input() -> None:
    cs = [cand(1, 1), cand(2, 2)]
    assert allocate_priority_window(cs, capacity=0) == PriorityAllocation(
        (), (uid(1), uid(2))
    )
    assert allocate_priority_window([], capacity=5) == PriorityAllocation((), ())


def test_priority_only_pending_registrations_count() -> None:
    cs = [
        cand(1, 1, 2000, status=S.FORMING),
        cand(2, 1, 1000),
        cand(3, 2, 3000, status=S.WITHDRAWN),
        cand(4, 3, 1500, status=S.REJECTED),
    ]
    result = allocate_priority_window(cs, capacity=5)
    assert result == PriorityAllocation((uid(2),), ())


# ── 先搶期送出判定 ─────────────────────────────────────


def test_first_come_accepts_eligible_school_with_room() -> None:
    existing = [cand(1, 1, status=S.ACCEPTED)]
    new = cand(2, 2, minute=10, status=S.PENDING)
    assert (
        decide_first_come(
            new, candidates=existing, priority_schools={school(1)}, capacity=2
        )
        == S.ACCEPTED
    )


@pytest.mark.parametrize(
    ("priority", "existing", "capacity"),
    [
        # 該校優先期有報名
        ({school(2)}, [cand(1, 1, status=S.ACCEPTED)], 5),
        # 同校已有正取
        (set(), [cand(1, 2, status=S.ACCEPTED)], 5),
        # 名額已滿
        (set(), [cand(1, 1, status=S.ACCEPTED), cand(3, 3, status=S.ACCEPTED)], 2),
        # 名額為 0
        (set(), [], 0),
    ],
)
def test_first_come_waitlists(
    priority: set[UUID], existing: list[Candidate], capacity: int
) -> None:
    new = cand(2, 2, minute=10)
    assert (
        decide_first_come(
            new, candidates=existing, priority_schools=priority, capacity=capacity
        )
        == S.WAITLISTED
    )


def test_first_come_ignores_candidate_itself_and_counts_only_accepted() -> None:
    new = cand(2, 2, minute=10, status=S.PENDING)
    existing = [
        new,
        cand(3, 3, status=S.WAITLISTED),
        cand(4, 4, status=S.WITHDRAWN),
        cand(1, 1, status=S.ACCEPTED),
    ]
    assert (
        decide_first_come(new, candidates=existing, priority_schools=(), capacity=2)
        == S.ACCEPTED
    )


def test_first_come_skips_accepted_copy_of_candidate_itself() -> None:
    # candidates 內的本人已是正取（例如重新判定），不能把自己算成同校正取或占用名額
    me = cand(2, 2, minute=10, status=S.ACCEPTED)
    assert (
        decide_first_come(me, candidates=[me], priority_schools=(), capacity=1)
        == S.ACCEPTED
    )


def test_first_come_school_with_waitlisted_team_still_eligible() -> None:
    # 同校之前的隊伍因額滿列候補，之後有空位時同校新隊伍仍可正取（同校無正取）
    existing = [cand(1, 2, status=S.WAITLISTED)]
    new = cand(5, 2, minute=10)
    assert (
        decide_first_come(new, candidates=existing, priority_schools=(), capacity=1)
        == S.ACCEPTED
    )


# ── 先搶期候補順位 ─────────────────────────────────────


def _first_come_scenario() -> tuple[list[Candidate], set[UUID]]:
    w = S.WAITLISTED
    cs = [
        # 學校 1：優先期代表隊正取，另兩隊候補 → 不符資格＋補充旗標
        cand(1, 1, 2000, status=S.ACCEPTED),
        cand(2, 1, 1900, minute=1, status=w),
        cand(3, 1, 1800, minute=2, status=w),
        # 學校 2：優先期有報名，但代表隊也是候補（超過名額）→ 不符資格、無旗標
        cand(4, 2, 1700, minute=3, status=w),
        # 學校 3：優先期沒報名、先搶期已有正取 → 不符資格、無旗標
        cand(5, 3, 1600, minute=4, status=S.ACCEPTED),
        cand(6, 3, 1500, minute=5, status=w),
        # 學校 4：符合資格，兩隊候補；最早送出者有順位
        cand(8, 4, 900, minute=20, status=w),
        cand(7, 4, 1000, minute=7, status=w),
        # 學校 5：符合資格，一隊候補，送出比學校 4 的第一隊晚
        cand(9, 5, 3000, minute=10, status=w),
        # 學校 6：符合資格，與學校 5 同時送出、id 較大
        cand(11, 6, 100, minute=10, status=w),
        # 不參與的狀態
        cand(12, 7, status=S.WITHDRAWN),
    ]
    return cs, {school(1), school(2)}


def test_first_come_waitlist_order() -> None:
    cs, priority = _first_come_scenario()
    order = waitlist_order(cs, phase=FIRST, priority_schools=priority)
    nb = WaitlistReason.SCHOOL_NOT_ELIGIBLE
    assert list(order.values()) == [
        WaitlistEntry(uid(7), 1, None),
        WaitlistEntry(uid(9), 2, None),
        WaitlistEntry(uid(11), 3, None),
        WaitlistEntry(uid(2), None, nb, representative_backfill=True),
        WaitlistEntry(uid(3), None, nb, representative_backfill=True),
        WaitlistEntry(uid(4), None, nb),
        WaitlistEntry(uid(6), None, nb),
        WaitlistEntry(uid(8), None, WaitlistReason.LATER_THAN_SCHOOLMATE),
    ]


def test_first_come_waitlist_order_empty() -> None:
    assert waitlist_order([], phase=FIRST, priority_schools=()) == {}


# ── 報名截止後候補順位與截止補位 ───────────────────────


def _after_deadline_scenario() -> list[Candidate]:
    w = S.WAITLISTED
    return [
        # 學校 1：已有 1 隊正取，另 2 隊候補 → 排序較前的有順位，另一隊略過
        cand(1, 1, 2000, status=S.ACCEPTED),
        cand(2, 1, 1500, minute=1, status=w),
        cand(3, 1, 1400, minute=2, status=w),
        # 學校 2：已抽籤（drawn）2 隊 → 候補全部略過
        cand(4, 2, 2000, status=S.DRAWN),
        cand(5, 2, 1990, status=S.DRAWN),
        cand(6, 2, 1990, minute=3, status=w),
        # 學校 3：沒有正取，3 隊候補 → 前 2 隊有順位
        cand(7, 3, 1450, minute=4, status=w),
        cand(8, 3, 1450, minute=5, status=w),
        cand(9, 3, 1450, minute=6, status=w),
        # 學校 4：退賽隊伍不占名額
        cand(10, 4, 1000, status=S.RETIRED),
        cand(11, 4, 1000, minute=7, status=w),
    ]


def test_after_deadline_waitlist_order() -> None:
    order = waitlist_order(
        _after_deadline_scenario(), phase=AFTER, priority_schools={school(1)}
    )
    lim = WaitlistReason.SCHOOL_LIMIT_REACHED
    assert list(order.values()) == [
        WaitlistEntry(uid(2), 1, None),
        WaitlistEntry(uid(7), 2, None),
        WaitlistEntry(uid(8), 3, None),
        WaitlistEntry(uid(11), 4, None),
        WaitlistEntry(uid(6), None, lim),
        WaitlistEntry(uid(9), None, lim),
        WaitlistEntry(uid(3), None, lim),
    ]


def test_after_deadline_ignores_priority_schools() -> None:
    cs = _after_deadline_scenario()
    assert waitlist_order(cs, phase=AFTER, priority_schools=()) == waitlist_order(
        cs, phase=AFTER, priority_schools={school(1), school(3)}
    )


def test_fill_from_waitlist_takes_first_n_positions() -> None:
    cs = _after_deadline_scenario()
    assert fill_from_waitlist(cs, remaining=2) == (uid(2), uid(7))
    assert fill_from_waitlist(cs, remaining=0) == ()


def test_fill_from_waitlist_returns_all_when_fewer_than_n() -> None:
    cs = _after_deadline_scenario()
    assert fill_from_waitlist(cs, remaining=99) == (uid(2), uid(7), uid(8), uid(11))
    assert fill_from_waitlist([], remaining=3) == ()


def test_fill_matches_after_deadline_order() -> None:
    cs = _after_deadline_scenario()
    order = waitlist_order(cs, phase=AFTER, priority_schools=())
    ranked = sorted(
        (e for e in order.values() if e.position is not None),
        key=lambda e: e.position or 0,
    )
    assert fill_from_waitlist(cs, remaining=3) == tuple(
        e.registration_id for e in ranked[:3]
    )


# ── 與輸入順序無關、重複呼叫結果相同 ───────────────────


@pytest.mark.parametrize("seed", range(5))
def test_results_independent_of_input_order(seed: int) -> None:
    pri = [cand(i, i % 7, 1000 + (i * 37) % 11, minute=i % 4) for i in range(1, 30)]
    fc, fc_priority = _first_come_scenario()
    after = _after_deadline_scenario()
    new = cand(99, 8, minute=30)

    base = (
        allocate_priority_window(pri, capacity=4),
        waitlist_order(fc, phase=FIRST, priority_schools=fc_priority),
        waitlist_order(after, phase=AFTER, priority_schools=()),
        fill_from_waitlist(after, remaining=3),
        decide_first_come(new, candidates=fc, priority_schools=fc_priority, capacity=5),
    )
    again = (
        allocate_priority_window(shuffled(pri, seed), capacity=4),
        waitlist_order(
            shuffled(fc, seed), phase=FIRST, priority_schools=frozenset(fc_priority)
        ),
        waitlist_order(shuffled(after, seed), phase=AFTER, priority_schools=()),
        fill_from_waitlist(shuffled(after, seed), remaining=3),
        decide_first_come(
            new,
            candidates=shuffled(fc, seed),
            priority_schools=list(fc_priority),
            capacity=5,
        ),
    )
    assert base == again
    # dict 的排列順序也一致
    assert list(base[1]) == list(again[1])
    assert list(base[2]) == list(again[2])


# ── 輸入不合法 ─────────────────────────────────────────


def test_negative_capacity_or_remaining_raises() -> None:
    with pytest.raises(ValueError, match="capacity"):
        allocate_priority_window([], capacity=-1)
    with pytest.raises(ValueError, match="capacity"):
        decide_first_come(cand(1, 1), candidates=[], priority_schools=(), capacity=-1)
    with pytest.raises(ValueError, match="remaining"):
        fill_from_waitlist([], remaining=-1)


def test_duplicate_registration_id_raises() -> None:
    dup = [cand(1, 1), cand(1, 2, status=S.WAITLISTED)]
    with pytest.raises(ValueError, match="重複"):
        allocate_priority_window(dup, capacity=1)
    with pytest.raises(ValueError, match="重複"):
        waitlist_order(dup, phase=AFTER, priority_schools=())
    with pytest.raises(ValueError, match="重複"):
        fill_from_waitlist(dup, remaining=1)
    with pytest.raises(ValueError, match="重複"):
        decide_first_come(cand(2, 3), candidates=dup, priority_schools=(), capacity=1)


# ── 介面字串與相依 ─────────────────────────────────────


def test_reason_messages_cover_every_reason() -> None:
    # 與 EXPERIENCE.md〈固定介面字串〉第 201～204 行逐字相同
    assert REASON_MESSAGES == {
        WaitlistReason.SCHOOL_NOT_ELIGIBLE: (
            "先搶期只遞補優先期沒有報名、目前也沒有正取的學校；"
            "報名截止後改依平均段位積分排序。"
        ),
        WaitlistReason.LATER_THAN_SCHOOLMATE: (
            "先搶期每校只遞補最早送出的一隊，本校已有更早送出的候補。"
        ),
        WaitlistReason.SCHOOL_LIMIT_REACHED: (
            "每校最多 2 隊正取：本校正取加上排在前面的本校候補已達 2 隊。"
        ),
    }
    assert REPRESENTATIVE_BACKFILL_MESSAGE == (
        "本校代表隊退出時，由本校平均段位積分次高的隊伍遞補。"
    )


def test_allocation_imports_only_stdlib_and_registration_models() -> None:
    tree = ast.parse(Path(allocation.__file__).read_text(encoding="utf-8"))
    app_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("app")
    }
    plain = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert app_imports == {"app.modules.registration.models"}
    assert not any(name.startswith("app") for name in plain)
