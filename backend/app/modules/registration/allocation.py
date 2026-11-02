"""校園賽的名額分配規則 AllocationPolicy（純函式，不碰資料庫、不讀時鐘、
只 import 標準函式庫與同模組的 `registration.models`）。

規則來源：PRD FR-14～FR-17、epic-3-context〈分配規則〉〈候補順位〉。

- `sort_key`：所有依平均段位積分排序的規則共用的排序鍵（FR-14）：
  積分高者優先 → 送出時間早者優先 → 報名 id 小者優先。
- `allocate_priority_window`：優先期結算（FR-14）。
- `decide_first_come`：先搶期送出當下判定正取或候補（FR-15）。
- `waitlist_order`：依階段算出每個候補的順位，或沒有順位的原因（FR-17）。
- `fill_from_waitlist`：截止補位（FR-16）＝報名截止後階段的順位前 N 名。

所有函式的結果只由輸入決定，與輸入順序無關。名額或剩餘名額為負、報名 id 重複時拋
`ValueError`（第二階段的 service 不會傳入，屬程式錯誤）。

「正取」包含 `accepted` 與 `drawn`（抽籤後已參賽的隊伍仍占該校名額，FR-17 的
「含抽籤後」）；其他狀態（撤回、退回、退賽、取消資格等）不計入任何規則。
"""

from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.modules.registration.models import RegistrationStatus

SCHOOL_ACCEPTED_LIMIT = 2
"""報名截止後每校最多正取隊數（FR-16、FR-17）。"""

_ACCEPTED_STATUSES = frozenset({RegistrationStatus.ACCEPTED, RegistrationStatus.DRAWN})


class AllocationPhase(StrEnum):
    """計算候補順位時的階段：先搶期、報名截止後（含抽籤後）。"""

    FIRST_COME = "first_come"
    AFTER_DEADLINE = "after_deadline"


class WaitlistReason(StrEnum):
    """候補沒有順位的原因；介面字串見 `REASON_MESSAGES`。"""

    SCHOOL_NOT_ELIGIBLE = "SCHOOL_NOT_ELIGIBLE"
    LATER_THAN_SCHOOLMATE = "LATER_THAN_SCHOOLMATE"
    SCHOOL_LIMIT_REACHED = "SCHOOL_LIMIT_REACHED"


# 與 EXPERIENCE.md〈固定介面字串〉一對一對應
REASON_MESSAGES: dict[WaitlistReason, str] = {
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
REPRESENTATIVE_BACKFILL_MESSAGE = "本校代表隊退出時，由本校平均段位積分次高的隊伍遞補。"


@dataclass(frozen=True)
class Candidate:
    """報名快照：送出時凍結的學校、平均段位積分、送出時間，加上目前狀態。"""

    id: UUID
    school_id: UUID
    avg_rank_score: Decimal
    submitted_at: datetime
    status: RegistrationStatus


@dataclass(frozen=True)
class PriorityAllocation:
    """優先期結算結果；兩者都依 `sort_key` 排序。"""

    accepted: tuple[UUID, ...]
    waitlisted: tuple[UUID, ...]


@dataclass(frozen=True)
class WaitlistEntry:
    """某個候補的順位。

    `position` 為 1 起算的「候補第 N 位」；沒有順位時為 None，並帶 `reason`。
    `representative_backfill` 只在先搶期、本校優先期代表隊為正取時為 True
    （同校專屬遞補，不計入順位）。
    """

    registration_id: UUID
    position: int | None
    reason: WaitlistReason | None
    representative_backfill: bool = False


def sort_key(candidate: Candidate) -> tuple[Decimal, datetime, UUID]:
    """FR-14 的排序鍵：平均段位積分高 → 送出時間早 → 報名 id 小。"""
    return (-candidate.avg_rank_score, candidate.submitted_at, candidate.id)


def _submit_key(candidate: Candidate) -> tuple[datetime, UUID]:
    """先搶期的送出先後：送出時間早 → 報名 id 小。"""
    return (candidate.submitted_at, candidate.id)


def _check_unique(candidates: Iterable[Candidate]) -> list[Candidate]:
    items = list(candidates)
    duplicated = [i for i, n in Counter(c.id for c in items).items() if n > 1]
    if duplicated:
        raise ValueError(f"報名 id 重複：{', '.join(map(str, sorted(duplicated)))}")
    return items


def _check_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} 不能為負：{value}")


def _accepted_per_school(candidates: Iterable[Candidate]) -> Counter[UUID]:
    return Counter(c.school_id for c in candidates if c.status in _ACCEPTED_STATUSES)


def allocate_priority_window(
    candidates: Iterable[Candidate], *, capacity: int
) -> PriorityAllocation:
    """優先期結算（FR-14）。

    只看狀態為 `pending`（已送出・待分配）的報名；每校排序最前的一隊為代表隊，
    代表隊依排序取前 `capacity` 隊正取，其餘代表隊與所有非代表隊列候補。
    只結算 `pending` 的報名：結算後再呼叫（已沒有 `pending`）會回傳空結果，不得拿來重設
    狀態；重複執行結果不變由 worker 工作負責。
    """
    _check_non_negative("capacity", capacity)
    pending = sorted(
        (
            c
            for c in _check_unique(candidates)
            if c.status == RegistrationStatus.PENDING
        ),
        key=sort_key,
    )
    seen_schools: set[UUID] = set()
    accepted: list[UUID] = []
    waitlisted: list[UUID] = []
    for c in pending:
        is_representative = c.school_id not in seen_schools
        seen_schools.add(c.school_id)
        if is_representative and len(accepted) < capacity:
            accepted.append(c.id)
        else:
            waitlisted.append(c.id)
    return PriorityAllocation(tuple(accepted), tuple(waitlisted))


def decide_first_come(
    candidate: Candidate,
    *,
    candidates: Iterable[Candidate],
    priority_schools: Collection[UUID],
    capacity: int,
) -> RegistrationStatus:
    """先搶期送出當下的判定（FR-15）。

    `candidates` 是該賽事目前的報名（可以包含 `candidate` 本身，會被略過）。
    該校優先期沒有報名、目前也沒有正取，且正取數未達 `capacity` 時回 `accepted`，
    否則回 `waitlisted`。
    呼叫端契約：每次釋出名額（撤回、退回、提高名額）時，必須在同一個鎖與交易內先依
    `waitlist_order` 遞補，所以「有空位但仍有有順位的候補」的狀態不會傳到本函式。
    """
    _check_non_negative("capacity", capacity)
    others = [c for c in _check_unique(candidates) if c.id != candidate.id]
    accepted = _accepted_per_school(others)
    if (
        candidate.school_id not in priority_schools
        and accepted[candidate.school_id] == 0
        and accepted.total() < capacity
    ):
        return RegistrationStatus.ACCEPTED
    return RegistrationStatus.WAITLISTED


def waitlist_order(
    candidates: Iterable[Candidate],
    *,
    phase: AllocationPhase,
    priority_schools: Collection[UUID],
) -> dict[UUID, WaitlistEntry]:
    """依階段算出每個候補（`waitlisted`）的順位（FR-17）。

    `candidates` 是該賽事目前的報名；正取（`accepted`、`drawn`）用來判斷學校資格與每校上限。
    回傳以報名 id 為鍵，依「有順位者依順位，再接沒有順位者」的固定順序排列。

    - 先搶期：只有「優先期沒有報名、目前也沒有正取」的學校有資格；每個有資格的學校只有
      最早送出的一隊有順位，依送出時間（同時再依 id）排序。
    - 報名截止後：所有候補依 `sort_key` 排入；排入後會使該校正取超過 2 隊的略過。

    `priority_schools` 在報名截止後不影響順位。
    """
    items = _check_unique(candidates)
    accepted = _accepted_per_school(items)
    waiting = [c for c in items if c.status == RegistrationStatus.WAITLISTED]
    if phase == AllocationPhase.FIRST_COME:
        return _first_come_order(waiting, accepted, priority_schools)
    return _after_deadline_order(waiting, accepted)


def _first_come_order(
    waiting: list[Candidate],
    accepted: Counter[UUID],
    priority_schools: Collection[UUID],
) -> dict[UUID, WaitlistEntry]:
    positioned: list[Candidate] = []
    skipped: list[WaitlistEntry] = []
    seen_schools: set[UUID] = set()
    for c in sorted(waiting, key=_submit_key):
        in_priority = c.school_id in priority_schools
        if in_priority or accepted[c.school_id] > 0:
            # 先搶期的優先期學校不會有新的正取，所以這裡的正取就是優先期代表隊
            skipped.append(
                WaitlistEntry(
                    c.id,
                    None,
                    WaitlistReason.SCHOOL_NOT_ELIGIBLE,
                    representative_backfill=in_priority and accepted[c.school_id] > 0,
                )
            )
        elif c.school_id in seen_schools:
            skipped.append(
                WaitlistEntry(c.id, None, WaitlistReason.LATER_THAN_SCHOOLMATE)
            )
        else:
            seen_schools.add(c.school_id)
            positioned.append(c)
    entries = [WaitlistEntry(c.id, n, None) for n, c in enumerate(positioned, start=1)]
    return {e.registration_id: e for e in [*entries, *skipped]}


def _after_deadline_order(
    waiting: list[Candidate], accepted: Counter[UUID]
) -> dict[UUID, WaitlistEntry]:
    counts = Counter(accepted)
    positioned: list[WaitlistEntry] = []
    skipped: list[WaitlistEntry] = []
    for c in sorted(waiting, key=sort_key):
        if counts[c.school_id] >= SCHOOL_ACCEPTED_LIMIT:
            skipped.append(
                WaitlistEntry(c.id, None, WaitlistReason.SCHOOL_LIMIT_REACHED)
            )
            continue
        counts[c.school_id] += 1
        positioned.append(WaitlistEntry(c.id, len(positioned) + 1, None))
    return {e.registration_id: e for e in [*positioned, *skipped]}


def fill_from_waitlist(
    candidates: Iterable[Candidate], *, remaining: int
) -> tuple[UUID, ...]:
    """截止補位（FR-16）：報名截止後階段順位前 `remaining` 名的報名 id，依順位排列。

    不足 `remaining` 名時全部回傳；補位後仍有空位由呼叫端保留。
    """
    _check_non_negative("remaining", remaining)
    order = waitlist_order(
        candidates, phase=AllocationPhase.AFTER_DEADLINE, priority_schools=()
    )
    return tuple(e.registration_id for e in order.values() if e.position is not None)[
        :remaining
    ]
