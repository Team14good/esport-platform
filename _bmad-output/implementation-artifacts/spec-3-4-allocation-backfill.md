---
title: 'Story 3.4（第一階段）審查修正：名額釋出時先由候補依順位遞補'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'c2b39623eaa9f523b8e7df50c937140dea8cf338'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #28 審查（OG-Matcha）指出：`decide_first_come` 的 docstring 假設「釋出名額時呼叫端會先在同一個鎖裡遞補」，但期中規則（epics.md〈期中範圍〉規則 6、CONTRIBUTING 6.3）規定抽籤前取消資格「不立即遞補，名額留給之後的分配」。所以先搶期會出現空位：新送出的隊伍插到有順位的候補前面，被插隊的候補卻仍顯示「候補第 1 位」。

**Approach:** 在 `allocation.py` 新增純函式，回傳空位應依當下階段的 `waitlist_order` 遞補哪些候補。呼叫端在同一個鎖裡先遞補，再判定新送出的報名。同時更新 docstring、規劃文件與 deferred-work。

## Decisions（2026-11-04，邱芯彤）

- PR #28 建議 1 選 (b)：取消資格後，在同一個鎖裡先依 `waitlist_order` 讓候補遞補，不讓新送出的隊伍插到候補前面。
- 建議 2、3 的測試已在 `4b30a23` 補上，本 spec 不重做。
- 與期中規則的配合選 (甲) 延後遞補：抽籤前取消資格本身仍不遞補，B 的 6.5 不改；空出的名額在之後分配時（先搶期新送出、截止補位），由 registration 在同一個鎖裡先讓有順位的候補遞補，再判定新送出的報名。
- 規劃文件的修改放進 #28：epics.md 規則 6 與 Story 6.5 期中版調整、CONTRIBUTING 6.3、epic-3／epic-6 context，一起在本 PR 審查。

## Boundaries & Constraints

**Always:**
- 遞補人選＝當下階段 `waitlist_order` 有順位者的前 `capacity − 目前正取數` 名；不另寫一套排序。
- 先搶期每校只有一隊有順位，所以依順位一次遞補多隊時，不會改變其他人的資格。
- 只由輸入決定，與輸入順序無關；名額為負、id 重複時拋 `ValueError`。

**Never:**
- 不碰資料庫、worker、API、畫面（仍屬第二階段）。
- 不改 B 的 competition／disputes 程式碼。
- 不做「代表隊退出時由同校次高者遞補」（deferred 既有項目，3.7／3.8）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 審查範例 | 名額 2，A 被取消資格、B 正取，X1 候補第 1 位，先搶期 | 遞補回傳 X1；之後 Y1 送出 → 候補 | N/A |
| 沒有空位 | 正取數＝名額 | 空 tuple | N/A |
| 空位多於有順位候補 | 空位 3、有順位候補 1 | 回傳那 1 隊，其餘空位保留 | N/A |
| 截止後 | 截止後階段有空位 | 與 `fill_from_waitlist(remaining=空位)` 相同 | N/A |
| 正取已超過名額 | 正取數 > 名額 | 空 tuple | N/A |
| 不合法 | 名額為負、id 重複 | — | `ValueError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/allocation.py:160-184` -- `decide_first_come` 的 docstring「呼叫端契約」要改寫成：先呼叫新函式遞補
- `backend/app/modules/registration/allocation.py:187-257` -- `waitlist_order`／`_first_come_order`／`_after_deadline_order`：新函式直接取其有順位者，沿用 `_accepted_per_school`、`_check_non_negative`
- `backend/app/modules/registration/allocation.py:260-273` -- `fill_from_waitlist`：截止後階段的遞補應與它一致（可改為呼叫新函式或保留並以測試比對）
- `backend/tests/registration/test_allocation.py` -- `cand`、`school`、`shuffled` 輔助函式；424 行以後是 #28 審查補的測試
- `_bmad-output/planning-artifacts/epics.md:215`、`:2025`；`CONTRIBUTING.md:164`；`_bmad-output/implementation-artifacts/epic-6-context.md:27-28` -- 期中取消資格規則原文
- `_bmad-output/implementation-artifacts/deferred-work.md:127-129` -- 第二階段待辦，要補「名額釋出／新送出前先遞補」

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/allocation.py` -- 新增 `backfill_vacancies(candidates, *, phase, priority_schools, capacity) -> tuple[UUID, ...]`；改寫 `decide_first_come` 的呼叫端契約與模組 docstring
- [x] `backend/tests/registration/test_allocation.py` -- I/O 矩陣各列、審查範例端對端（遞補後 Y1 候補）、與輸入順序無關
- [x] `_bmad-output/planning-artifacts/epics.md:215`、`:2025` -- 「空出的正取名額留給之後的分配」後補：「之後分配時（先搶期新送出、截止補位），先由當下階段有順位的候補依順位遞補，再判定新送出的報名」
- [x] `CONTRIBUTING.md:164` -- 同上，一句話；並在 6.3 註明本 PR 更新了規則
- [x] `_bmad-output/implementation-artifacts/epic-6-context.md:28`、`epic-3-context.md:38` 附近 -- 同步同一句話（與 epics.md 同一個 commit，context 不會被判定過期）
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 新增一項：第二階段在鎖內先呼叫 `backfill_vacancies`

**Acceptance Criteria:**
- Given 先搶期有空位且有有順位的候補，when 呼叫端先 `backfill_vacancies` 再 `decide_first_come`，then 新送出的報名不會排到該候補前面。
- Given `allocation.py`，when 以 `--branch` 量測，then 分支覆蓋率維持 ≥ 90%。

## Implementation Notes

- `fill_from_waitlist` 保留原介面，與 `backfill_vacancies` 共用私有函式 `_positioned_ids`；另以測試比對截止後階段兩者結果相同。
- 空位＝`capacity` − 正取數（`accepted`、`drawn`），為負時視為 0（正取已超過名額回傳空 tuple）。
- epic-3-context〈期中範圍〉原寫「釋出名額的遞補不會發生」，已改為抽籤前取消資格的延後遞補規則並點名 `backfill_vacancies`。
- 驗證：後端 1701 個測試通過；`allocation.py` 分支覆蓋率 100%（106 statements、22 branches）；lint.sh（mypy、ty、ruff）通過。測試以 `-v` 掛載本機 `backend/app`、`backend/tests` 執行，未重建映像。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-04；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V1 | 超額測試只有 1 個有順位候補，拿掉 `max(…, 0)` 測試仍通過 | low | `(uid4,)[:-1]` 也是 `()`；已預先驗證 | patch |
| B2 | `backfill_vacancies` 沒說只能在抽籤前用 | low | `AFTER_DEADLINE` 含抽籤後、`drawn` 算正取；抽籤後呼叫會替取消資格的空位找候補，違反規則 6；補 docstring 一句 | patch |
| B5c | `decide_first_come` 新契約拿掉撤回、退回、提高名額 | low | 期末 3.7、3.8、FR-9 仍會釋出名額，舊契約涵蓋、新文字遺漏 | patch |
| B4 | epics.md 規則 6 新句子與前面括號重複 | low | 第 215 行同一句出現兩次「先搶期新送出…截止補位」 | patch |
| B7 | deferred 新項目格式與既有項目不同 | low | 既有項目以「（低）」「（中）」開頭並寫日期與審查者 | patch |
| B8a | 打亂順序測試只斷言非空 | low | 錯但穩定的實作也會通過 | patch |
| B8b | 缺「遞補後仍有空位，新送出者正取」測試 | low | I/O 矩陣以外的組合，沒有測試把關 | patch |
| B9 | 「一次遞補多隊不改變資格」沒有測試 | low | 由構造成立，但沒有測試固定 | patch |
| B1 | 釋出的是優先期代表隊時，應由同校次高者遞補（FR-17），本函式會給別校 | medium | 期中 6.5 抽籤前取消代表隊即可觸發；原 deferred（3.4 第一階段 B2）寫「期中不會發生」已不成立；修正需新增規則與函式，intent 未含 | defer |
| E1 | `decide_first_come` 沒有強制先遞補，只靠 docstring | low | 加檢查會讓每次判定多算一次順位且新增錯誤分支；呼叫端責任已寫入 docstring 與 deferred，並有對照測試 | reject |
| E2 | 優先期內有 `pending` 時空位被高估 | false | 優先期內沒有 `waitlisted`（只有 `allocate_priority_window` 會產生），有順位者為空，回傳 `()`；先搶期新送出的 `pending` 本來就不該占名額 | reject |
| B3 | 新 spec 不在 diff；沒有 AI 使用紀錄 | false | 審查流程刻意不給 Blind Hunter spec；AI 使用紀錄在流程結束時新增 | reject |
| B5a | Story 3.5、3.6 驗收條件沒同步 | low | 3.6 的「前 N 位」與 `backfill_vacancies(AFTER)` 相同；3.5 的「名額仍有剩餘」在規則 6（衝突時以它為準）已說明先遞補 | reject |
| B6 | 截止階段兩個公開函式結果相同 | low | 有測試固定兩者一致，deferred 已寫明擇一呼叫 | reject |
| B8c | 缺 `pending` 與優先期學校無正取的測試 | false | `pending` 見 E2；後者由審查範例（優先期學校 A 被取消資格）涵蓋 | reject |

## Verification

**Commands:**
- `docker compose run --rm --no-deps -T backend bash -c "bash scripts/test.sh"` -- 全綠
- `docker compose run --rm --no-deps -T backend bash -c "coverage run --branch -m pytest tests/registration/test_allocation.py && coverage report --include=app/modules/registration/allocation.py"` -- ≥ 90%
- `docker compose run --rm --no-deps -T backend bash scripts/lint.sh` -- 通過
