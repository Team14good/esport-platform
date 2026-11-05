---
title: 'Story 3.6：報名截止自動補位'
type: 'feature'
created: '2026-11-05'
status: 'done'
route: 'dispatch'
baseline_commit: 'a6f9ea8d7762f09c20d361f76dc6e2cb72fea925'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-6-draw-functions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 報名截止時間過後，賽事狀態一直停在「開放報名」（S1／S2 仍顯示開放報名），剩餘名額也不會由候補補上（FR-16）。registration 自己比對截止時間，所以截止後送出報名已會被拒，但 tournaments 的狀態沒有轉成「報名截止」。

**Approach:** 新增 worker 工作：找出報名截止時間已到、仍為開放報名的賽事，鎖住後在同一交易內沿用 `spec-3-6-draw-functions.md` 建立的鎖內私有函式補完分配與截止補位，再轉為「報名截止」；操作者為系統。

## Decisions（2026-11-05，邱芯彤）

- 截止後的錯誤訊息維持「這場賽事的報名已截止。」：賽事轉為 `closed` 後，registration 的 `_ensure_registration_period` 遇到 `closed` 自己拋 `_registration_deadline_passed()`，不讓 tournaments 的「這場賽事目前不開放報名。」出現。（spec 審查 #4）
- epics 期中版調整的「截止補位做成公開函式給 4.1 呼叫」已由 `finalize_for_draw` 取代（contracts/competition.md〈二〉），不另外公開 `fill_at_deadline`。（spec 審查 #3）
- 本份仍屬 3.6：`sprint-status.yaml` 的 3-6 先改回 `in-progress`，完成時再改為 `done`。（spec 審查 #7）
- spec 約 5,900 tokens（2026-11-05 加入回滾測試、6 項 deferred 查證與送出時間修正後），超過 1,600；找候選、worker 工作與測試拆開都無法單獨上線，保留完整 spec。
- D 在 #53 審查建議 2：本份補一個 API 層測試，鎖住「提前抽籤失敗會整筆回滾」，要證明分配確實寫入過、失敗後才消失，不只檢查前置條件。（2026-11-05）
- D 在 #53 的建議要在 PR 上回覆，草稿先給 C 確認，不直接發送。（2026-11-05）
- 送出報名跨越截止時間：`submit_registration` 的截止檢查（`_ensure_registration_period` 內的 `clock.now()`）與寫入 `submitted_at` 的 `clock.now()` 是兩次呼叫，中間有名單與資料驗證的查詢，截止前一刻送出時 `submitted_at` 可能晚於 `registration_end`。改為只取一次 `now`，同時用於檢查與 `submitted_at`，維持「已送出的報名 `submitted_at < registration_end`」；補回歸測試。（2026-11-05，C 同意必要時修正規格）
- deferred-work 用 `merge=union`，#53 刪除的 3 項被之後合併的 #51 帶回；本份連同截止相關的 3 項共刪除 6 項，每項都已查證完成或由本份處理（見 Tasks）。（2026-11-05）

## Boundaries & Constraints

**Always:**
- 找候選：tournaments 新增公開函式 `find_due_registration_end_id(session) -> UUID | None`（service 取 `clock.now()`，repository 照 `find_due_upcoming_id(session, now)` 傳入 `now`；`status == open` 且 `registration_end <= now`，依 `registration_end`、再依 id，最早到期的優先，不加鎖）。registration 不直接查賽事表；沒有任何報名的賽事也要能被找到。
- registration 新增兩個函式（照 `settle_priority_window`／`allocate_due_priority_window` 的分法）：
  - `close_registration(session, *, tournament_id) -> bool`：`_lock_tournament`，鎖內重新檢查「仍為 `open` 且 `registration_end <= now`」，不成立時不做任何事回 False。校園賽依序：沒有結算紀錄時 `_settle_locked` → `_first_come_locked` → `_fill_at_deadline_locked` → `transition_tournament(to=closed)`；自訂模式只轉狀態。回 True。
  - `close_due_registration(session) -> bool`（worker 用）：沒有候選回 False；有候選就呼叫 `close_registration` 並回 True。
- 全部操作者為 `None`（系統）；補位與分配沿用 `_allocate` 發 `RegistrationAllocated`。
- worker 工作 `close_registrations` 加進 `JOBS`，排在 `allocate_priority_windows` 之後、`start_due_tournaments` 之前（因此也在 `dispatch_outbox` 之前）。
- 重複執行結果不變：轉為 `closed` 後不再是候選。

**Never:**
- 不改 `allocation.py` 的規則；不改 `settle_priority_window`、`finalize_for_draw` 與三個鎖內私有函式的行為。
- 不改 tournaments 既有函式與測試，只新增公開函式與 repository 查詢（CONTRIBUTING 6.6，在 PR 說明列出）。
- 不做前端（S2「抽籤準備中」B 已完成）、不做撤回／退回／延長報名（期中擱置）、不做 3.5 送出時的即時分配。

## I/O & Edge-Case Matrix

學校以大寫字母、積分以數字表示；「到期」指 `registration_end <= now`。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 截止補位（epics 範例） | 名額 5、已結算；Z 校 2 隊正取、W 校 1 隊正取；候補依積分 E（Z）、F（W）、G（W）、H（V，優先期超過名額的代表隊）；到期 | F、H 正取，E、G 仍候補（`SCHOOL_LIMIT_REACHED`）；賽事 `closed`；F、H 各 1 則 `RegistrationAllocated`；操作紀錄操作者皆為系統 | N/A |
| 補位後仍有空位 | 名額 4、只有 2 隊正取、沒有候補；到期 | 不改報名；賽事 `closed`，空位保留 | N/A |
| 優先期還沒結算 | 優先期內送出 3 隊 `pending`、沒有結算紀錄；直接呼叫 `close_registration` | 先結算（結算紀錄與摘要的操作者為系統），再補位，再轉 `closed` | N/A |
| 優先期後送出 | 已結算；之後送出的報名仍為 `pending`；到期 | 依送出順序補做先搶期，再補位；之後沒有 `pending` | N/A |
| 沒有任何報名 | 開放報名、沒有隊伍或只有 `forming`；到期 | 賽事 `closed`；截止工作寫一筆空的結算紀錄（新行為：優先期 worker 不會結算沒有 `pending` 的賽事）；`forming` 不變 | N/A |
| 自訂模式 | `mode == custom`、有候補；到期 | 只轉 `closed`，報名不變、沒有結算紀錄 | N/A |
| 還沒到期 | `registration_end > now` | 不是候選；`close_registration` 回 False、不改任何東西 | N/A |
| 已不是開放報名 | 提前抽籤後為 `published`，或 `cancelled`；到期 | 不是候選；`close_registration` 回 False、不改任何東西 | N/A |
| 重複執行 | 已轉 `closed` | 再執行回 False；報名、操作紀錄、事件都不增加 | N/A |
| 多場到期 | 兩場都到期 | `close_due_registration` 一次處理一場，較早到期的先處理；第二次呼叫處理另一場 | N/A |
| worker 停機後一輪 | 報名開始與截止都已過、賽事仍為 `upcoming` | 同一輪先轉 `open` 再轉 `closed` | N/A |
| 截止後送出、加入、改資料 | 賽事已 `closed` | 拒絕，訊息「這場賽事的報名已截止。」 | 409 `REGISTRATION_CLOSED` |
| 截止後抽籤 | 賽事已 `closed`、早於開賽；至少 2 隊正取；經 competition `draw` | 不呼叫 `finalize_for_draw`、分配不變；正取轉 `drawn`、賽事轉 `published` | N/A |
| 截止後的候補顯示 | 賽事 `closed`、有候補 | S17／S12 `waitlist_phase == "after_deadline"`，順位與原因依截止後規則 | N/A |
| 提前抽籤失敗回滾 | 開放報名、優先期未結束、只有 1 隊優先期內 `pending`；主辦方 `POST /draw` | `finalize_for_draw` 在請求的交易內已寫入結算紀錄、狀態變更、操作紀錄與事件；抽籤因正取不足失敗後全部回滾：沒有結算紀錄、報名仍為 `pending`、該賽事沒有新的操作紀錄與 `RegistrationAllocated`、賽事仍為 `open` | 409 `NOT_ENOUGH_TEAMS` |
| 送出跨越截止時間 | 開放報名；`clock.now()` 第一次回傳 `registration_end` 前 1 微秒、之後回傳 `registration_end` 後 1 微秒；隊長送出 | 送出成功；`submitted_at` 為第一次取得的時間（早於 `registration_end`），送出操作紀錄的 `submitted_at` 相同 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/service.py` -- `_settle_locked`、`_first_come_locked`、`_fill_at_deadline_locked`、`_allocate`（直接呼叫）；`settle_priority_window`／`allocate_due_priority_window`（兩層函式的寫法）；`_lock_tournament`；`_ensure_registration_period`（`:79`，由 `_ensure_can_join`、`update_player_profile`、`submit_registration` 呼叫；改為 `closed` 時拋 `_registration_deadline_passed()`）；`_in_registration_period` 的 docstring「open → closed 要到 3.6 才有」要更新
- `backend/app/modules/tournaments/service.py` -- `open_due_registration`（找候選、鎖、重新檢查的範例）、`transition_tournament`（`open` → `closed` 已允許）；新增 `find_due_registration_end_id`
- `backend/app/modules/tournaments/repository.py` -- `find_due_upcoming_id`（查詢寫法照抄）
- `backend/app/modules/competition/service.py` `draw` -- 只在 `open` 時呼叫 `finalize_for_draw`，`closed` 可抽籤，`start_at <= now` 拒絕；不修改
- `backend/app/worker/jobs.py`、`__init__.py` -- `JOBS`；`run_once(jobs, session_factory=)`；工作拋錯時 rollback 並停止本輪該工作
- `backend/tests/worker/test_email_pipeline.py:27-38` -- `test_jobs_are_registered_in_order` 以 `==` 比對完整清單，要插入 `close_registrations`（C 在 #50 改過）；`test_check_in.py:827`、其他 worker 測試只檢查相對順序
- `backend/tests/worker/test_priority_window_allocation.py` -- helper `_tournament`、`_school`、`_submitted`、`_in_window`、`_statuses`、`_events`、`_team_page`、`_my_card`、`_waitlist`、`_own_team`；`_run` 只跑 `[allocate_priority_windows]`，不能直接沿用
- `backend/tests/registration/test_settlement_concurrency.py` -- 併發測試與資料（名額 2、3 校各 1 隊優先期內 `pending`）；會提交資料，留下仍為 `open`、報名截止 2026-10-25 11:00（`frozen_clock` 2026-10-18 11:00＋7 天）的賽事
- `backend/tests/registration/test_allocation.py` -- `fill_from_waitlist` 單元測試；3.4 第一階段已有 `test_story_3_6_example_deadline_fill` 涵蓋 E/F/G/H 範例（補位回 F、H，補位後 E、G 的原因為 `SCHOOL_LIMIT_REACHED`）。本份新增的 `test_fill_from_waitlist_epics_example_skips_schools_at_limit` 同樣是純函式測試，另外斷言補位前 E、G 在截止後順位中沒有順位；完整截止流程（鎖、結算、補位、轉 `closed`、事件與操作紀錄）由 `tests/worker/test_registration_deadline.py` 的 `test_epics_example_fills_skipping_schools_at_limit_in_one_worker_round` 驗證（2026-11-05 實作後更正：原寫「沒有 E/F/G/H 範例」不正確）
- `backend/tests/registration/test_submit_registration.py:660` -- 既有斷言「這場賽事的報名已截止。」
- `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- 〈二〉公開函式表；〈三〉`open` → `closed`
- `backend/tests/conftest.py` -- `client` 每個請求用 savepoint session（`join_transaction_mode="create_savepoint"`），router 沒有 commit 就關閉時回滾；`competition/registration_port.py` 在呼叫當下才到 `registration.service` 以名稱查找，`monkeypatch` 包住 `finalize_for_draw` 即可在同一個 session 內觀察寫入
- `backend/tests/registration/test_draw_functions.py` -- `test_draw_via_api_no_longer_returns_503`（API 抽籤寫法）、`_logs`、`_events`、`_statuses` helper
- `_bmad-output/implementation-artifacts/deferred-work.md` -- 要刪除的 6 項，依 summary 開頭辨認（行號為 2026-11-05 合併 main 後）：
  1. 第 66 行「（中）目前沒有任何工作把賽事從 `open` 轉成 `closed`」：本份處理
  2. 第 190 行「Story 3.6 第二階段：報名截止 worker 工作…公開函式 `fill_at_deadline`…S2」：worker 本份處理；`fill_at_deadline` 依 Decisions 不另公開；S2 已由 `TournamentOverview.tsx:82-84` 在 `closed` 時顯示「抽籤準備中」
  3. 第 229 行「Story 3.6 第二階段之二」：本份處理
  4. 第 217 行「Story 3.6 第二階段：確認抽籤後的報名狀態名稱」：#53 `mark_drawn` 寫入 `DRAWN`，`_ORDER_STATUSES` 含 `DRAWN`
  5. 第 220 行「Story 3.6 第二階段：截止補位與 4.1 的 `finalize_for_draw`…」：抽籤部分 #53 完成，截止部分本份處理
  6. 第 223 行「補 API 層測試：同校已有 2 隊 `drawn`」：#53 `test_after_draw_school_with_two_drawn_teams_shows_limit_reason` 在 S17、S12 都斷言 `SCHOOL_LIMIT_REACHED` 與 `after_deadline`
  - 第 184 行「Story 3.4～3.6 第二階段：先搶期送出與截止補位時…`backfill_vacancies`」不刪：3.5 送出時的即時分配仍要用。第 181 行 7.1 示範資料項目不刪：剩下的是示範資料的 registration 步驟

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/repository.py`、`service.py` -- 新增 `find_due_registration_end_id`
- [x] `backend/app/modules/registration/service.py` -- 新增 `close_registration`、`close_due_registration`；`_ensure_registration_period` 遇到 `closed` 回「報名已截止」；更新 `_in_registration_period` docstring
- [x] `backend/app/worker/jobs.py` -- 新增 `close_registrations` 並加進 `JOBS`
- [x] `backend/tests/worker/test_email_pipeline.py` -- 完整清單在 `allocate_priority_windows` 後插入 `close_registrations`（唯一修改的既有測試）
- [x] `backend/tests/registration/test_allocation.py` -- E/F/G/H 單元測試：candidates 含 Z、Z、W 三筆正取與 E、F、G、H 四筆候補，`fill_from_waitlist(remaining=2)` 回 F、H
- [x] `backend/tests/worker/test_registration_deadline.py` -- I/O 矩陣每一列；工作註冊順序（`allocate_priority_windows` 後、`start_due_tournaments` 與 `dispatch_outbox` 前）；至少一列經 `run_once([open_registrations, allocate_priority_windows, close_registrations], session_factory=...)`
- [x] `backend/tests/tournaments/test_find_due_registration_end.py` -- 新函式的單元測試（到期、未到期、非 `open`、多場時最早的）
- [x] `backend/tests/registration/test_settlement_concurrency.py` -- 新增參數組：`close_registration` 對 `close_registration`、`close_registration` 對 `finalize_for_draw`；沿用既有資料，時鐘設在 `registration_end`；斷言兩邊都沒拋錯、1 筆結算紀錄、1 筆摘要、`tournament.status_changed` 只有 1 筆、賽事最後為 `closed`、事件不重複
- [x] `backend/app/modules/registration/service.py` -- `submit_registration` 鎖住賽事後取一次 `now = clock.now()`，截止檢查與 `submitted_at` 都用它（`_ensure_registration_period` 加可選的 `now` 參數，`_ensure_can_join`、`update_player_profile` 的呼叫不變）
- [x] `backend/tests/registration/test_submit_registration.py` -- 新增「送出跨越截止時間」回歸測試（直接呼叫 `submit_registration`，不經 API，避免登入驗證等其他程式先取時間）：`monkeypatch` 讓 `app.core.clock.now` 依序回傳截止前 1 微秒、之後一律截止後 1 微秒，斷言送出成功且 `submitted_at < registration_end`；改回兩次取時間時測試要失敗（只新增測試，不改既有測試）
- [x] `backend/tests/registration/test_draw_functions.py` -- 新增「提前抽籤失敗回滾」測試：`monkeypatch` 包住 `registration.service.finalize_for_draw`，呼叫真的函式後在同一個 session 內記下結算紀錄存在、狀態變更與 `RegistrationAllocated` 筆數（斷言確實寫入過）；`POST /draw` 回 409 `NOT_ENOUGH_TEAMS` 後，以測試的 session 斷言 I/O 矩陣「提前抽籤失敗回滾」列的每一項都不存在
- [x] `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- 〈二〉加 `find_due_registration_end_id`；〈三〉`open` → `closed` 加註 C 已在 3.6 實作，轉為 `closed` 前在同一個鎖內先做優先期結算、補做先搶期、截止補位（只加註）
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 3-6 改回 `in-progress`；完成時改為 `done`
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 Code Map 列的 6 項，其他項目不動

**Acceptance Criteria:**
- Given 開放報名的校園賽、報名截止時間已到，when worker 執行一輪，then 賽事轉為「報名截止」，剩餘名額由候補依截止後順位補上，補上的隊伍收到事件。
- Given 後端，when 執行 `scripts/test.sh`、`lint.sh`，then 全部通過，tournaments 既有測試不需修改。

## Implementation Notes

- 依賴的私有函式已隨 #53 合併（2026-11-04，D 核准）。2026-11-05 已在本分支 `git merge --no-commit origin/main`（只有 `sprint-status.yaml` 的 `last_updated` 衝突，取 main 的時間），合併結果與 `origin/main` 相同，合併尚未 commit；PR 直接對 `main`。
- 實作（2026-11-05）：`close_registration` 鎖內重新檢查後，校園賽依序 `_settle_locked`（沒有結算紀錄時）→ `_first_come_locked` → `_fill_at_deadline_locked`，最後 `transition_tournament(to=closed)`；`_ensure_registration_period` 先判斷 `closed` 再交給 tournaments，並接受可選的 `now`；`submit_registration` 鎖住賽事後取一次 `now`。
- 測試注意：凍結時鐘下同一次呼叫寫入的事件 `created_at` 相同，`_events` 依 id 排序，順序不確定；新測試對事件只比集合，順序改看操作紀錄（依寫入順序）。
- 驗證：`docker compose up -d --build --wait` 後 `scripts/test.sh` 2015 passed（覆蓋率 97%），`scripts/lint.sh` 通過。把 `submit_registration` 改回截止檢查與 `submitted_at` 各取一次時間後，「送出跨越截止時間」測試失敗。
- 實作與審查後的決定（2026-11-05，邱芯彤）：`test_allocation.py` 新增的 E/F/G/H 測試與既有的 `test_story_3_6_example_deadline_fill` 都保留，並更正 Code Map 的描述；`sprint-status.yaml` 不補做中間的 `in-progress`，維持 `done`；#53 已回覆 D，不再留言；spec 維持 `done`。記在這裡而不是 Decisions，因為 Decisions 位於 `<frozen-after-approval>` 區塊內。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-05；Blind Hunter、Edge Case Hunter、Verification Gap 三層）。Verification Gap：沒有驗證缺口。

| # | 來源 | 發現 | 判定 | 去向與證據 |
|---|------|------|------|-----------|
| 1 | Blind、Edge、VG | 最早到期的賽事在 `close_registration` 一直拋錯時，worker 每輪都卡在它，之後到期的賽事不會關閉 | medium | defer：`run_once` 每個工作只取第一個候選的模式既有（`open_due_registration`、`allocate_due_priority_window` 相同），Design Notes 已列為已知限制；修正要改 worker 的候選處理，不是本份的小修 |
| 2 | Edge、Blind | 自訂模式截止時仍為 `pending` 的報名，轉 `closed` 後一直是 `pending` | reject | 凍結的 I/O 矩陣「自訂模式」列要求「只轉 `closed`，報名不變」；`finalize_for_draw` 對自訂模式也不改報名（`test_custom_mode_tournament_is_left_unchanged`），自訂模式的分配不在 3.6 範圍 |
| 3 | Edge、Blind | `close_due_registration` 忽略 `close_registration` 的回傳值一律回 True，可能空轉到 `max_items` | false | 符合 Boundaries「有候選就呼叫 `close_registration` 並回 True」；回 False 只發生在鎖內發現賽事已非 `open`（下一次查詢就不再是候選）或時間未到（鎖內 `clock.now()` 晚於查詢時，不會發生），不會重複空轉 |
| 4 | Edge、Blind | 新測試依賴其他測試提交的殘留賽事，日後若有測試提交更早截止的 `open` 賽事會依順序失敗 | reject（low） | 目前唯一提交資料的併發測試留下的賽事截止於 2026-10-25，新測試時鐘都早於它，Design Notes 已寫明；屬假設情境，修正要改測試範圍篩選，增加複雜度 |
| 5 | Blind | spec 檔與 AI 使用紀錄不在 diff 裡 | false | 審查用的 diff 刻意排除 spec 與 `docs/ai-usage/`；兩者都會隨 PR 提交 |
| 6 | Blind | 沒有測試「轉狀態失敗時整批分配回滾」 | reject（low） | 鎖內已確認賽事為 `open`，`open` → `closed` 是允許的轉換，`transition_tournament` 在此不會拋錯；`run_once` 工作拋錯時 rollback 是 worker 既有行為 |
| 7 | Blind | 併發測試只用 `finalize_for_draw`，沒測完整 `draw` 與截止搶鎖 | reject（low） | Tasks 指定的參數組就是 `close_registration` 對 `finalize_for_draw`；抽籤先拿鎖後賽事為 `published`，截止工作略過已由矩陣「已不是開放報名」列的測試涵蓋 |
| 8 | Blind | registration 的 `close_registration`、`close_due_registration` 與 `_ensure_registration_period` 新行為沒寫進契約 | reject（low） | 兩個函式只給同模組的 worker 工作用，沒有其他模組呼叫；`contracts/` 沒有 registration 的契約檔，錯誤訊息維持既有的「這場賽事的報名已截止。」 |
| 9 | Blind | 契約〈三〉`open` → `closed` 那一格的說明太長 | reject（low） | Tasks 要求在此加註；只是表格可讀性 |
| 10 | Blind | `find_due_registration_end_id` 的查詢沒有 `(status, registration_end)` 索引 | reject（low） | 賽事表期中規模小，加索引要另開 Alembic 遷移，超出直接修正 |
| 11 | Blind | `test_allocation.py` 混入既有測試的排版變更 | low | patch：還原成 baseline 的多行寫法（`lint.sh` 只檢查 `app/`） |
| 12 | Blind | 送出跨越截止時間的測試依賴「第一次取時間」的位置，日後多一次取時間會讓測試失敗 | reject（low） | 寫法是 Tasks 指定的；日後多一次取時間時測試會明確失敗，不會漏掉回歸 |
| 13 | Blind | 沒有測試「`closed` 時直接呼叫 `finalize_for_draw` 不做任何事」 | false | `test_draw_functions.py` 的 `test_tournament_not_open_is_left_unchanged` 以所有非 `open` 狀態（含 `closed`）參數化，斷言報名與結算紀錄不變 |
| 14 | Blind | 自訂模式只測直接呼叫，沒有經 worker 一輪 | reject（low） | `find_due_registration_end_id` 不篩模式（`test_find_due_registration_end.py` 與 repository 查詢可見），worker 只是呼叫同一個函式 |

## Design Notes

- 測試資料庫有殘留的 `open` 賽事（見 Code Map 併發測試），報名截止 2026-10-25 11:00。所以：
  - 多數矩陣列與併發測試呼叫指定賽事的 `close_registration`，斷言目標賽事的狀態、操作紀錄與事件。
  - 呼叫 `close_due_registration`／`run_once` 的測試（還沒到期、多場到期、重複執行、worker 一輪），測試賽事的 `registration_end` 與時鐘都要早於 2026-10-25 11:00（例如報名開始＋優先期＋1 小時），註解寫明原因。
- epics 範例的狀態無法經正常流程做出（Z 校 2 隊正取、代表隊在候補），測試直接寫入報名狀態與一筆 `PriorityWindowSettlement`（「已結算」必須有紀錄，否則鎖內會再結算一次）。
- 鎖內先補位、最後才 `transition_tournament`，與合約〈三〉「截止補位之後」一致。
- 找候選放在 tournaments：registration 不能查賽事表，而沒有報名的賽事也要轉狀態。呼叫方向 registration → tournaments 符合規則。
- 與抽籤併發時兩邊都先鎖賽事：抽籤先拿到鎖時賽事已是 `published`，截止工作略過；截止工作先拿到時賽事已是 `closed`，抽籤不呼叫 `finalize_for_draw`，照常從 `closed` 轉 `published`。
- 在真正的 worker 一輪裡，`allocate_priority_windows` 先執行，截止工作自己結算只發生在直接呼叫、或前一個工作失敗時。
- 已知限制（與 `open_due_registration` 相同）：最早到期的那場一直失敗時（例如缺快照的 `RuntimeError`），worker 每輪都卡在它，之後的賽事不會被關閉；錯誤會記在 log。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
