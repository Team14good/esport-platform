---
title: 'Story 3.5：先搶期即時分配'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '453b84764d3a0eb4987f4531783000e96bb5c732'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 優先期結束後（先搶期）送出的報名一直停在「已送出・待分配」，要等報名截止或提前抽籤才被判定；隊長送出當下不知道是正取還是候補（FR-15）。

**Approach:** 在 `submit_registration` 同一個賽事鎖與交易內，先搶期送出時沿用 3.6 建立的 `_first_come_locked`：先讓有順位的候補遞補，再判定這一筆為正取或候補；回應（`TeamDetail`）直接帶結果與候補順位，前端照回應顯示。

## Decisions（2026-11-06，邱芯彤）

- 送出成功的 Toast 維持「已送出報名」，結果由 S17 徽章與候補說明依回應顯示，不新增介面字串。
- #58 已合併（`453b847`），本分支合併 `origin/main` 後實作，不另合併 `story/3-6-deadline`。
- spec 約 5,000 tokens，超過 1,600；200 筆併發測試是 epics 3.5 的驗收條件，拆開則 3.5 無法完成，保留完整 spec。
- spec 審查（2026-11-06）後修正：矩陣「同校已有先搶期正取」的原因改為 `SCHOOL_NOT_ELIGIBLE`（`allocation.py:226-236`，同校已有正取時走這條，`LATER_THAN_SCHOOLMATE` 只在同校沒有正取、有更早的候補時）；新增「優先期沒有任何報名」一列；「有空位先遞補」改成具體數字；200 筆測試改用初始資料的 139 所學校（不新增學校，`tests/identity/test_schools.py:14` 檢查總數為 139）。
- router 的 docstring「報名轉為『已送出・待分配』」改成也說明先搶期當下分配，並重新產生 client（docstring 會進 `sdk.gen.ts`）。

## Boundaries & Constraints

**Always:**
- 「先搶期送出」＝校園賽、送出時間 `now > priority_end`（`now` 是送出時取得的同一個時間，也寫入 `submitted_at`）。`now == priority_end` 屬優先期，維持 `pending` 由 worker 結算（與 `_settle_locked` 的 `submitted_at <= priority_end` 一致）。
- 先搶期送出時，在寫入 `pending` 與 `registration.submitted` 之後、同一個鎖內依序：優先期還沒結算就先結算（依 3.4 Decisions 呼叫 `settle_priority_window`，同一交易內重新鎖同一列不會阻塞；它自己判斷是否已結算）→ `_first_come_locked`。所以殘留的優先期後 `pending`（3.5 上線前送出的）依送出順序先判定，本筆最後判定。
- 結算與分配的操作者為系統（`None`，epic context「分配要寫操作紀錄，操作者 system」）；送出本身（`pending`、`registration.submitted`）的操作者仍是隊長。每筆分配沿用 `_allocate` 發 `RegistrationAllocated`。
- 回應由 `_build_detail` 在分配之後產生，帶 `waitlist_position`、`waitlist_reason`、`waitlist_phase`、`representative_backfill`；API 形狀不變；只因 router docstring 更新而重新產生 client。
- 併發整合測試在真實 PostgreSQL 平行送出 200 筆：正取數不超過名額、每校最多 1 隊正取、每筆恰好一個結果（`accepted` 或 `waitlisted`）、沒有遺失或重複的報名；每筆恰好 2 筆 `registration.status_changed`（`forming`→`pending`、`pending`→結果）與 1 則 `RegistrationAllocated`，結算紀錄 1 筆。

**Never:**
- 不改 `allocation.py` 的規則；不改 `_first_come_locked`、`_settle_locked`、`settle_priority_window` 的行為。
- 不改 tournaments、competition 的程式。
- 不做自訂模式（`custom` 送出仍維持 `pending`）、撤回、退回、代表隊被取消資格時的同校遞補（deferred-work 另列）。

## I/O & Edge-Case Matrix

學校以大寫字母表示；「先搶期」指 `priority_end < now < registration_end`。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新學校、有名額 | 先搶期、已結算；X 校優先期沒有報名、目前沒有正取；名額有剩 | 回應 `registration_status == "accepted"`；1 則 `RegistrationAllocated`；操作紀錄 `pending`（隊長）→ `accepted`（系統） | N/A |
| 優先期有報名的學校 | 先搶期；A 校在結算紀錄的優先期學校中 | `waitlisted`，`waitlist_position` 為空、`waitlist_reason == "SCHOOL_NOT_ELIGIBLE"`、`waitlist_phase == "first_come"` | N/A |
| 同校已有先搶期正取 | 先搶期；X 校已有 1 隊在先搶期正取 | 第二隊 `waitlisted`，沒有順位，原因 `SCHOOL_NOT_ELIGIBLE`、`representative_backfill == False` | N/A |
| 名額已滿、有順位 | 先搶期、名額滿；候補已有 A（優先期學校）、B（X 校）；C（X 校）、D（Y 校）依序送出 | C 沒有順位；D 回應 `waitlist_position == 2`；B 在 S17 為第 1 位 | N/A |
| 有空位先遞補 | 先搶期、已結算（沒有優先期學校）；名額 2：X1、Y1 先搶期正取，B（W 校）候補第 1 位；X1 改為 `disqualified`（空 1 位，非優先期代表隊）；新學校 Z 送出 | 先把 B 遞補為正取（系統，發事件），再判定 Z：名額已滿，`waitlisted`、`waitlist_position == 1` | N/A |
| 優先期還沒結算 | 先搶期；優先期內有 `pending`、沒有結算紀錄；隊長送出 | 同一交易先結算（結算紀錄、摘要，操作者系統），再判定本筆 | N/A |
| 優先期沒有任何報名 | 先搶期；整場沒有送出過的報名、沒有結算紀錄；隊長送出（最常見的第一筆） | 寫入空的結算紀錄與 1 筆 `registration.priority_window_settled`（操作者系統），本筆依新學校判定為 `accepted` | N/A |
| 殘留的先搶期 `pending` | 已結算；先前先搶期送出、仍為 `pending` 的 P1；新送出 P2 | P1 先依送出順序判定，再判定 P2；之後沒有 `pending` | N/A |
| 優先期內送出 | `now <= priority_end` | 維持 `pending`、沒有事件（3.3／3.4 行為不變） | N/A |
| 自訂模式 | `mode == custom`、`now > priority_end` | 維持 `pending`、沒有事件 | N/A |
| 送出被拒 | 先搶期；送出條件不符或已截止 | 拒絕，不結算、不分配，既有錯誤碼不變 | 409／422 照 3.3 |
| 名額只剩 1 個、同時送出 | 先搶期；名額 2、已有 1 隊正取；10 隊各屬其他學校、平行送出 | 只有 1 隊正取，其餘 9 隊候補 | N/A |
| 200 筆平行送出 | 先搶期；名額 32；200 隊依序分配到初始資料的 139 所學校（部分學校 2 隊）、平行送出 | 正取 = 32、每校最多 1 隊正取、其餘候補；200 筆都有結果、沒有 `pending`；每筆恰好一則分配事件 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/service.py`
  - `submit_registration`（`:732`）：鎖 → 取 `now = clock.now()`（#58）→ 隊員／隊長 → 報名期間（用 `now`）→ `FORMING` → `submit_blockers` → 快照（`submitted_at = now`）→ `mark_status(PENDING, 隊長)` → `registration.submitted` → `_build_detail`；分配插在 `_build_detail` 之前。
  - `settle_priority_window`（`:909`，會 `_lock_tournament`；已結算或 `_priority_window_due` 為假時回 False）、`_priority_window_due`（`:827`，用 `clock.now()`）、`_first_come_locked`（`:966`，所有 `pending` 依 `(submitted_at, id)` 逐筆 `backfill_vacancies(FIRST_COME)` → `decide_first_come` → `_allocate`；不過濾 `submitted_at > priority_end`，所以一定要先結算）、`_allocate`（`:836`）、`_current_phase`／`_waitlist_fields`（`:387`、`:411`）
- `backend/app/modules/registration/allocation.py` -- `decide_first_come`、`backfill_vacancies`、`waitlist_order`；不改
- `backend/app/modules/registration/router.py:98-108` -- `POST /teams/{team_id}/submission` 回 `TeamDetail`、成功才 commit；只改 `:102` docstring（之後 `scripts/generate-client.sh` 重新產生，`sdk.gen.ts` 會跟著變）
- `backend/app/modules/registration/allocation.py:220-240` `_first_come_order` -- 學校在優先期學校中或已有正取 → `SCHOOL_NOT_ELIGIBLE`；同校較晚的候補 → `LATER_THAN_SCHOOLMATE`
- `frontend/src/features/registration/useSubmitRegistration.ts` -- `onSuccess` 以回應 `setQueryData`、invalidate S12、Toast `SUBMITTED_TEXT`；沒有 optimistic update。S17 徽章與 `WaitlistDetails`（`TeamPage.tsx:87-92`）、正取倒數（`SubmitRegistrationSection.tsx:272-286`）已依回應顯示
- `frontend/tests/unit/team-pages.test.tsx:744-775` -- 送出測試只 mock `pending` 回應；補 `accepted`、`waitlisted` 回應
- `backend/tests/registration/test_submit_registration.py` -- `_fill`（`:73`）、`_team`（`:93`）；`:889-892` `SUBMITTERS`／`test_parallel_submissions_succeed_only_once`（`Barrier`、`Session(engine)`、finally 清資料）。預設賽事 `priority_end` 為現在＋23 小時，既有測試在優先期內，維持 `pending` 不受影響；`:637` 一秒前送出的測試只斷言 200，不改
- `backend/tests/registration/test_settlement_concurrency.py` -- 直接寫 Team 與報名、清 `OutboxEvent`（依 payload `tournament_id`，`:207-211`）與結算紀錄的寫法；學校用初始資料、帳號與賽事被操作紀錄參照刪不掉（檔頭說明）；`test_team_concurrency.py:28` `_demote_game_creator`
- `backend/tests/worker/test_priority_window_allocation.py:75-100` `_submitted`、`_school` -- 直接寫入已送出並帶快照的報名。前置狀態（優先期學校、候補、殘留 `pending`、正取）一律直接寫入，只有被測的那一筆經 API 送出；自訂模式比照 `:483`、`test_draw_functions.py:463` 直接把 `row.mode` 改為 `CUSTOM`，取消資格直接寫 `DISQUALIFIED`
- `backend/app/core/clock.py:12-17` -- 凍結時鐘是模組全域值；同一測試的多筆送出要以 `frozen_clock.advance(...)` 拉開，否則 `submitted_at` 相同、只能依隨機 id 排序
- `backend/app/core/db.py:16` -- engine 預設 pool 15 條、`pool_timeout` 30 秒；併發測試另建 engine（用 `tests/conftest.py:39-41` 已指向測試資料庫的 `engine.url`，不讀 `settings`；`pool_size=20`、`max_overflow=0`），`ThreadPoolExecutor(max_workers=20)` 送出，不用 200 人的 `Barrier`。PostgreSQL 18 預設 `max_connections` 100，夠用。不凍結時鐘：賽事 `registration_start` 為現在−1 小時、`priority_hours=0`（`tournaments/models.py:362` 下限 0），真實時間下已在先搶期，`submitted_at` 各不相同
- `backend/tests/registration/test_allocation.py:468` `test_story_3_5_example_first_come_positions` -- epics A／B／C／D 範例的純函式測試已存在
- `test_submit_registration.py:669` `test_submit_crossing_the_deadline_uses_one_time_for_check_and_snapshot`（#58 新增）要改：截止前 1 微秒已是先搶期，斷言 `PENDING` 會失敗；第二次起 `clock.now()` 都在截止後。改為斷言 `submitted_at` 不變且狀態為 `ACCEPTED`（預設名額 16、新學校）；第二次取時間後已過截止，回應的 `waitlist_phase` 不檢查
- `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除第 180-182 行整個項目「Story 3.4～3.6 第二階段：先搶期送出與截止補位時…`backfill_vacancies`」（截止部分 #58 已完成）與第 186-188 行整個項目「Story 3.5 第二階段」；第 183-185 行代表隊同校遞補不刪

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/service.py` -- `submit_registration` 先搶期送出時結算（必要時）並 `_first_come_locked`；更新 docstring（「3.3 一律轉為 `pending`」）與 `settle_priority_window` docstring 中「3.5 處理」的說明
- [x] `backend/app/modules/registration/router.py`、`frontend/src/client` -- 更新送出 API 的 docstring，以 `scripts/generate-client.sh` 重新產生
- [x] `backend/tests/registration/test_first_come_submission.py` -- I/O 矩陣每一列（「200 筆平行送出」「名額只剩 1 個」除外）：前置狀態直接寫入，被測的一筆經 API 送出，斷言回應欄位、報名狀態、操作紀錄操作者、事件數；斷言操作紀錄或事件筆數時要把首筆送出寫入的空結算摘要算進去（或先結算）
- [x] `backend/tests/registration/test_first_come_concurrency.py` -- 200 筆與名額只剩 1 個的平行送出（設定見 Code Map `db.py` 項）；每隊 1 人（`starters=1, substitutes=0`），學校取初始資料；斷言見 Boundaries 併發項；finally 依序刪除事件（依 payload `tournament_id`）、結算紀錄、報名、隊員、隊伍
- [x] `backend/tests/registration/test_submit_registration.py` -- 只改跨越截止這一支（唯一修改的既有後端測試）
- [x] `frontend/src/features/registration/useSubmitRegistration.ts` -- Toast 維持「已送出報名」（Decisions）；只更新 docstring，說明先搶期回應已帶結果
- [x] `frontend/tests/unit/team-pages.test.tsx` -- 送出回應為 `accepted`、`waitlisted`（有順位、沒有順位）時 S17 直接顯示對應徽章與說明
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 Code Map 列的 2 項
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 3-5 改為 `in-progress`，完成時 `done`
- [x] `docs/ai-usage/C-邱芯彤.md` -- 完成後依 `docs/ai-usage/README.md` 在檔尾新增紀錄（由主流程在使用者確認後寫）

**Acceptance Criteria:**
- Given 先搶期的校園賽，when 隊長送出報名，then 回應與 S17 直接顯示「正取」、「候補第 N 位」或「候補・目前不在遞補順序中」＋原因，且結果與 `allocation.py` 一致。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh` 與前端 typecheck、biome、單元測試，then 全部通過。

## Implementation Notes

- 2026-11-06：#58 已合併（`453b847`），本分支以 `git merge origin/main` 同步（快轉）；Code Map 行號以合併後為準。#58 刪除的 6 項 deferred 沒有被 `merge=union` 帶回。
- 2026-11-06 實作：`submit_registration` 在寫入 `pending` 與 `registration.submitted` 並 flush 後，`mode == CAMPUS and now > priority_end` 時呼叫 `settle_priority_window`（已結算時不做事）再 `_first_come_locked(actor_id=None)`，最後 `_build_detail`。沒有改 `allocation.py`、`_first_come_locked`、`_settle_locked`、`settle_priority_window` 的行為（只改 docstring）。
- 測試的寫法：凍結時鐘下 `OutboxEvent` 只有 `created_at`、沒有序號，同一刻的事件只能依隨機 id 排序；所以「先遞補再判定」等順序改以操作者為系統的 `registration.status_changed`（`seq` 遞增）斷言，事件只比集合。200 筆測試建立帳號時傳 `hashed_password="x"` 跳過雜湊。

## Spec Change Log

## Review Triage Log

審查（2026-11-06，第 1 輪）：Blind Hunter 9 條、Edge Case Hunter 4 條、Verification Gap 0 條。

| # | 來源 | 位置 | 判定 | 去向 | 證據 |
|---|------|------|------|------|------|
| 1 | Blind | `service.py` `submit_registration` 新分支 | false | 駁回 | `settle_priority_window` 只在已結算或 `_priority_window_due` 為假時回 False；送出前 `_ensure_registration_period` 已確認賽事開放，`clock.now()` 不會早於 `now`（> `priority_end`），所以回 False 時一定已有結算紀錄，不會把優先期 `pending` 當先搶期判定。呼叫 `settle_priority_window` 是 Boundaries 指定的做法；跨截止那支測試的 `settled_at` 晚於截止只是記錄結算當下時間，不影響結果。 |
| 2 | Edge | `service.py:807-808` | false | 駁回 | 同 #1：送出時賽事必為開放中、時間已過 `priority_end`，回 False 只會是已結算。 |
| 3 | Edge | `service.py:804-808` | low | 駁回 | worker 恰在 `priority_end` 結算、且另一筆送出的 `now` 與它同一微秒才會發生，送出在鎖後取時間，實務上碰不到；此競態 3.4 就存在，修正要加分支。 |
| 4 | Blind | `service.py` docstring 第一行 | low | patch | 仍寫「報名從組隊中轉為待分配」，先搶期送出的結果是正取或候補；直接改文字。 |
| 5 | Blind | `router.py` docstring／`sdk.gen.ts` | low | patch | 沒說自訂模式送出維持待分配；直接補文字並重新產生 client。 |
| 6 | Blind | `test_first_come_concurrency.py` 200 筆 | low | 駁回 | 正取是否為各校最早送出的隊伍由 `test_first_come_submission.py` 與 `test_allocation.py` 驗證；併發測試的目的是不超收，Boundaries 已列斷言；補上要重算整套規則。 |
| 7 | Blind | `team-pages.test.tsx` | false | 駁回 | `SCHOOL_NOT_ELIGIBLE` 的顯示已有既有測試（`team-pages.test.tsx:1116`、`:1239`），本 Story 沒改顯示元件。 |
| 8 | Blind | `sprint-status.yaml` 3-5 註解 | low | 駁回 | 註解寫「完成」而狀態為 `in-progress` 只是暫時的，本流程結束時改為 `done` 就一致。 |
| 9 | Blind、Edge | `test_first_come_concurrency.py` `max(...)` | false | 駁回 | 兩支測試都先斷言 `Counter(outcomes)` 至少有 1 筆 `accepted` 才呼叫 `_check`，空集合走不到 `max()`。 |
| 10 | Edge | `test_first_come_concurrency.py` Barrier | false | 駁回 | 只有 10 隊的測試用 `barrier=True`，小於 `WORKERS`（20）；描述的情況沒有呼叫端。 |
| 11 | Blind | 併發測試留資料、`_events` 全表掃描 | low | 駁回 | 事件在 finally 依賽事刪除，不會累積；帳號與賽事留下是因為被只增不改的操作紀錄參照，與既有併發測試相同。 |
| 12 | Blind | 鎖持有時間 | low | 駁回 | 先搶期送出時通常只有本筆 `pending`，`_first_come_locked` 只跑一輪；200 筆測試所在的 61 支測試共 31.45 秒跑完。 |

PR #59 審查（2026-11-08，OG-Matcha 與 max930000 皆核准）：合併前 1 項、建議 6 項，全部處理。

| # | 來源 | 位置 | 判定 | 去向 | 證據 |
|---|------|------|------|------|------|
| 13 | OG-Matcha | 與 main 衝突、CI 跑在 #56 合併前 | medium | patch | `git merge origin/main`；`sprint-status.yaml` 的 `last_updated` 取較新時間；`scripts/generate-client.sh` 重新產生 client，與自動合併結果相同。 |
| 14 | OG-Matcha | `test_first_come_concurrency.py` `_check` | low | patch | 補公平性斷言：扣掉既有正取的名額與學校後，正取等於依 `(submitted_at, id)` 排序、學校不重複的前幾支隊伍。推翻第 1 輪 #6 的駁回：沒有優先期學校時答案只是排序取前 N，不必重算整套規則。 |
| 15 | OG-Matcha | 優先期邊界 | low | patch | 新增 `test_submission_just_after_priority_end_is_allocated`：`priority_end` 後 1 微秒送出即正取並發 `RegistrationAllocated`。 |
| 16 | OG-Matcha | spec Tasks、ai-usage 證據 | low | patch | 勾選 Tasks 的 ai-usage 列；ai-usage 只新增不修改，#59 與 commit 寫在本次修正的新紀錄裡。 |
| 17 | max930000 | `test_first_come_submission.py` 操作者 | low | patch | 5 支測試補 `_changes` 斷言：`pending`（隊長）→ 結果（系統）；留在 `pending` 的只有 `("pending", 隊長)`。 |
| 18 | max930000 | `sprint-status.yaml` 3-4 註解 | low | patch | 改為 3.5、3.6 第二階段已於各自 spec 完成。 |
| 19 | max930000 | `team-pages.test.tsx` `as HTMLElement` | low | patch | 五處改用 `waitlistLines()`：先斷言區塊存在，再比對每行文字。 |

## Design Notes

- 為什麼重用 `_first_come_locked` 而不是只判定本筆：先搶期送出時可能有 3.5 上線前留下的先搶期 `pending`，依送出順序先判定它們才公平；它每筆都重建 candidates，前一筆剛正取的隊伍會算進名額與學校資格。
- 為什麼用 `now > priority_end`：結算只收 `submitted_at <= priority_end`。若改用 `>=`，`submitted_at == priority_end` 的報名會先被結算當成優先期、再被當成先搶期，兩邊規則衝突。
- 併發正確性來自賽事列的 `FOR UPDATE`：所有送出在鎖上排隊，`_first_come_locked` 在鎖內讀最新狀態，所以不會超收。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- 前端容器內 `bun run typecheck`、`bunx biome check`、`bun run test:unit` -- 通過
