"""名額分配規則 AllocationPolicy（純函式，不碰資料庫、不讀時鐘、
只 import 標準函式庫與同模組的 `registration.models`）。

規則來源：PRD FR-14～FR-17、FR-39、epic-3-context〈分配規則〉〈候補順位〉。

依賽事模式分支（AD-20）：Story 3.10 加入的模式差異（要不要檢查學校、目前階段、送出時
怎麼判定、遞補前需不需要優先期結算、取消資格要不要遞補）都由本檔依 `AllocationMode`
回答，service 只呼叫這些函式。service 裡 3.10 之前就有的模式判斷（優先期結算、報名截止、
退回前結算、抽籤前分配、公開正取名單）維持原樣，不在本檔。

- `checks_school`、`needs_settlement`、`backfills_on_disqualify`、`submit_allocation`、
  `current_phase`：依模式回答的判斷。
- `decide_custom`：自訂模式送出當下判定正取或候補（FR-39）。

- `sort_key`：所有依平均段位積分排序的規則共用的排序鍵（FR-14）：
  積分高者優先 → 送出時間早者優先 → 報名 id 小者優先。
- `allocate_priority_window`：優先期結算（FR-14）。
- `decide_first_come`：先搶期送出當下判定正取或候補（FR-15）。
- `waitlist_order`：依階段算出每個候補的順位，或沒有順位的原因（FR-17）；先搶期可傳入
  代表隊已退出的學校，讓同校遞補排進順位（Story 3.8，與實際遞補順序一致）。
- `fill_from_waitlist`：截止補位（FR-16）＝報名截止後階段的順位前 N 名。
- `backfill_vacancies`：有空位時，當下階段有順位的候補依順位遞補（PR #28 審查）。
  期中抽籤前取消資格不立即遞補，空出的名額留給之後的分配；之後分配時（先搶期新送出、
  截止補位），呼叫端在同一個鎖裡先呼叫本函式讓候補遞補，再判定新送出的報名。
- `representative_backfill`：先搶期優先期代表隊退出時，由同校平均段位積分次高的候補
  遞補（FR-17，Story 3.7）；呼叫端在 `backfill_vacancies` 之前呼叫。

自訂模式（Story 3.10）只有一個階段 `AllocationPhase.CUSTOM`：候補依送出時間（同時再依
id）排序、全部有順位、沒有每校上限，`backfill_vacancies` 與 `waitlist_order` 傳入這個
階段即可；自訂賽事的報名沒有學校快照（`school_id` 為 None）。

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


class AllocationMode(StrEnum):
    """賽事模式（AD-20）：校園賽、自訂。

    值與 tournaments 的 `TournamentMode` 相同（本檔不能 import tournaments），service 以
    `AllocationMode(tournament.mode)` 轉換。
    """

    CAMPUS = "campus"
    CUSTOM = "custom"


class AllocationPhase(StrEnum):
    """計算候補順位時的階段：校園賽的先搶期、報名截止後（含抽籤後），以及自訂模式。

    自訂模式不分報名截止前後（含抽籤後）都是 `CUSTOM`。
    """

    FIRST_COME = "first_come"
    AFTER_DEADLINE = "after_deadline"
    CUSTOM = "custom"


class SubmitAllocation(StrEnum):
    """送出報名當下要做的分配（`submit_allocation`）。

    - `DEFER`：維持 `pending`，等優先期結算（校園賽優先期內）。
    - `FIRST_COME`：先結算優先期，再依送出順序做先搶期判定（校園賽先搶期，FR-15）。
    - `IMMEDIATE`：名額有剩立即正取，否則候補（自訂模式，FR-39，`decide_custom`）。
    """

    DEFER = "defer"
    FIRST_COME = "first_come"
    IMMEDIATE = "immediate"


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
    """報名快照：送出時凍結的學校、平均段位積分、送出時間，加上目前狀態。

    自訂模式不檢查學校，`school_id` 為 None（校園賽一定有值）。
    """

    id: UUID
    school_id: UUID | None
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
    `representative_backfill` 只在先搶期為 True，兩種情況：
    - 沒有順位：本校優先期代表隊為正取（代表隊退出時才由同校遞補）。
    - 有順位：本校代表隊已退出、本校目前沒有正取，這筆是本校 `sort_key` 第一名，排在
      一般先搶期順位之前（Story 3.8，與 `representative_backfill()` 的實際遞補順序一致）。
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


def _accepted_per_school(candidates: Iterable[Candidate]) -> Counter[UUID | None]:
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
    seen_schools: set[UUID | None] = set()
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


def checks_school(mode: AllocationMode) -> bool:
    """送出報名（與 S17 的送出條件）要不要檢查隊員學校：校園賽要（FR-13），自訂不要（FR-39）。

    不檢查學校時，送出時的學校快照一律為 None。
    """
    return mode == AllocationMode.CAMPUS


def needs_settlement(mode: AllocationMode) -> bool:
    """名額釋出後遞補前，是否要先有優先期結算紀錄。

    校園賽要（優先期內不遞補，由結算分配）；自訂模式沒有優先期，釋出時立即遞補。
    """
    return mode == AllocationMode.CAMPUS


def backfills_on_disqualify(mode: AllocationMode) -> bool:
    """抽籤前取消資格空出的名額要不要立即遞補。

    校園賽不立即遞補，留給之後的分配（先搶期送出、截止補位）；自訂模式沒有截止補位，
    所以立即由最早送出的候補遞補（Story 3.10 Decisions）。呼叫端只在抽籤前（賽事開放
    報名或報名截止）、被取消的報名原本是正取時才遞補。
    """
    return mode == AllocationMode.CUSTOM


def submit_allocation(
    mode: AllocationMode, *, after_priority_window: bool
) -> SubmitAllocation:
    """送出報名當下要做的分配（見 `SubmitAllocation`）。

    `after_priority_window`：送出時間晚於優先期結束（校園賽才看）。
    """
    if mode == AllocationMode.CUSTOM:
        return SubmitAllocation.IMMEDIATE
    if after_priority_window:
        return SubmitAllocation.FIRST_COME
    return SubmitAllocation.DEFER


def current_phase(mode: AllocationMode, *, before_deadline: bool) -> AllocationPhase:
    """計算候補順位與遞補時的階段。

    自訂模式一律 `CUSTOM`；校園賽在報名期間（`before_deadline`：賽事開放且早於報名截止）
    為先搶期，其餘為報名截止後。
    """
    if mode == AllocationMode.CUSTOM:
        return AllocationPhase.CUSTOM
    if before_deadline:
        return AllocationPhase.FIRST_COME
    return AllocationPhase.AFTER_DEADLINE


def decide_custom(
    candidate: Candidate, *, candidates: Iterable[Candidate], capacity: int
) -> RegistrationStatus:
    """自訂模式送出當下的判定（FR-39）：正取數未達 `capacity` 時回 `accepted`，否則 `waitlisted`。

    `candidates` 是該賽事目前的報名（可以包含 `candidate` 本身，會被略過）；不看學校。
    呼叫端契約同 `decide_first_come`：先以 `backfill_vacancies`（`phase=CUSTOM`）讓有順位的
    候補遞補，再判定新送出的報名，新送出的隊伍才不會插到候補前面。
    """
    _check_non_negative("capacity", capacity)
    others = [c for c in _check_unique(candidates) if c.id != candidate.id]
    if sum(1 for c in others if c.status in _ACCEPTED_STATUSES) < capacity:
        return RegistrationStatus.ACCEPTED
    return RegistrationStatus.WAITLISTED


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
    呼叫端契約：本函式不處理遞補。名額可能因抽籤前取消資格（期中不立即遞補）或撤回、退回、
    提高名額而空出，所以呼叫端必須在同一個鎖與交易內，先以 `backfill_vacancies`（`phase=FIRST_COME`）
    取得應遞補的候補並改為正取，再把更新後的報名傳進本函式；否則新送出的隊伍會插到
    有順位的候補前面。
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
    departed_schools: Collection[UUID] = (),
) -> dict[UUID, WaitlistEntry]:
    """依階段算出每個候補（`waitlisted`）的順位（FR-17）。

    `candidates` 是該賽事目前的報名；正取（`accepted`、`drawn`）用來判斷學校資格與每校上限。
    回傳以報名 id 為鍵，依「有順位者依順位，再接沒有順位者」的固定順序排列。

    - 先搶期：`departed_schools`（優先期代表隊已退出的學校，由呼叫端算出）中目前沒有正取
      的學校，各由本校 `sort_key` 第一名的候補排在最前面（多校依 `sort_key`），
      `representative_backfill=True`；這些學校的其他候補沒有順位（`SCHOOL_NOT_ELIGIBLE`）。
      之後只有「優先期沒有報名、目前也沒有正取」的學校有資格；每個有資格的學校只有
      最早送出的一隊有順位，依送出時間（同時再依 id）排序。
    - 報名截止後：所有候補依 `sort_key` 排入；排入後會使該校正取超過 2 隊的略過。
    - 自訂模式：所有候補依送出時間（同時再依 id）排入，全部有順位，沒有每校上限。

    `priority_schools`、`departed_schools` 在報名截止後與自訂模式不影響順位；`departed_schools`
    預設為空，結果與 Story 3.8 之前相同（`backfill_vacancies`、`fill_from_waitlist` 不傳）。
    """
    items = _check_unique(candidates)
    accepted = _accepted_per_school(items)
    waiting = [c for c in items if c.status == RegistrationStatus.WAITLISTED]
    if phase == AllocationPhase.FIRST_COME:
        return _first_come_order(waiting, accepted, priority_schools, departed_schools)
    if phase == AllocationPhase.CUSTOM:
        return _custom_order(waiting)
    return _after_deadline_order(waiting, accepted)


def _custom_order(waiting: list[Candidate]) -> dict[UUID, WaitlistEntry]:
    return {
        c.id: WaitlistEntry(c.id, n, None)
        for n, c in enumerate(sorted(waiting, key=_submit_key), start=1)
    }


def _first_come_order(
    waiting: list[Candidate],
    accepted: Counter[UUID | None],
    priority_schools: Collection[UUID],
    departed_schools: Collection[UUID],
) -> dict[UUID, WaitlistEntry]:
    # 代表隊已退出、目前沒有正取的學校：本校 sort_key 第一名排最前（同 representative_backfill）
    representatives: dict[UUID | None, Candidate] = {}
    for c in sorted(waiting, key=sort_key):
        if (
            c.school_id in departed_schools
            and accepted[c.school_id] == 0
            and c.school_id not in representatives
        ):
            representatives[c.school_id] = c
    first = sorted(representatives.values(), key=sort_key)
    first_ids = {c.id for c in first}
    positioned: list[Candidate] = []
    skipped: list[WaitlistEntry] = []
    seen_schools: set[UUID | None] = set()
    for c in sorted(waiting, key=_submit_key):
        if c.id in first_ids:
            continue
        if c.school_id in representatives:
            # 本校的遞補名額已由 sort_key 第一名排入；遞補後本校有正取，其他隊不再遞補
            skipped.append(
                WaitlistEntry(c.id, None, WaitlistReason.SCHOOL_NOT_ELIGIBLE)
            )
            continue
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
    entries = [
        WaitlistEntry(c.id, n, None, representative_backfill=True)
        for n, c in enumerate(first, start=1)
    ]
    entries += [
        WaitlistEntry(c.id, n, None)
        for n, c in enumerate(positioned, start=len(first) + 1)
    ]
    return {e.registration_id: e for e in [*entries, *skipped]}


def _after_deadline_order(
    waiting: list[Candidate], accepted: Counter[UUID | None]
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
    return _positioned_ids(order)[:remaining]


def backfill_vacancies(
    candidates: Iterable[Candidate],
    *,
    phase: AllocationPhase,
    priority_schools: Collection[UUID],
    capacity: int,
) -> tuple[UUID, ...]:
    """有空位時應遞補的候補 id，依順位排列（PR #28 審查）。

    空位＝`capacity` − 目前正取數（`accepted`、`drawn`），不足 0 時視為 0；回傳當下
    階段 `waitlist_order` 有順位者的前「空位」名，不足時全部回傳，其餘空位保留。
    先搶期每校只有一隊有順位，報名截止後的順位已計入每校上限，自訂模式沒有每校上限，
    所以依順位一次遞補多隊不會改變其他人的資格。報名截止後階段的結果與 `fill_from_waitlist(remaining=空位)`
    相同。
    只在抽籤前使用；抽籤後的取消資格依 6.5 由對手輪空或頂替，不呼叫本函式。
    """
    _check_non_negative("capacity", capacity)
    items = _check_unique(candidates)
    vacancies = max(capacity - _accepted_per_school(items).total(), 0)
    order = waitlist_order(items, phase=phase, priority_schools=priority_schools)
    return _positioned_ids(order)[:vacancies]


def _positioned_ids(order: dict[UUID, WaitlistEntry]) -> tuple[UUID, ...]:
    return tuple(e.registration_id for e in order.values() if e.position is not None)


def representative_backfill(
    candidates: Iterable[Candidate],
    *,
    departed_schools: Collection[UUID],
    capacity: int,
) -> tuple[UUID, ...]:
    """先搶期代表隊退出時的同校遞補（FR-17，Story 3.7）：應遞補的候補 id，依 `sort_key` 排列。

    `departed_schools` 是優先期代表隊已退出（撤回、取消資格等）的學校，由呼叫端依報名的
    代表隊標記算出。其中目前沒有正取（`accepted`、`drawn`）的學校，由該校 `sort_key`
    第一名的候補遞補；目前已有正取的學校（例如已由同校遞補過）不再遞補。
    遞補數不超過空位（`capacity` − 目前正取數，不足 0 時視為 0），超過時依 `sort_key`
    取前面的。只處理同校遞補，呼叫端之後仍要以 `backfill_vacancies` 處理剩下的空位。
    """
    _check_non_negative("capacity", capacity)
    items = _check_unique(candidates)
    accepted = _accepted_per_school(items)
    vacancies = max(capacity - accepted.total(), 0)
    best: dict[UUID | None, Candidate] = {}
    for c in sorted(items, key=sort_key):
        if (
            c.status == RegistrationStatus.WAITLISTED
            and c.school_id in departed_schools
            and accepted[c.school_id] == 0
            and c.school_id not in best
        ):
            best[c.school_id] = c
    return tuple(c.id for c in sorted(best.values(), key=sort_key)[:vacancies])
