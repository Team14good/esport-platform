---
title: 'Story 3.6：給抽籤用的 registration 函式'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '4a758e98ee2045fe349bbf7c2f2937dd6f81268f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** D 的 4.1 抽籤經 `competition/registration_port.py` 呼叫 registration 的 `finalize_for_draw`、`list_accepted_teams`、`mark_drawn`、`get_team_names`，但這四個函式不存在，抽籤一律回 503 `REGISTRATION_UNAVAILABLE`；交接期限 11/12（epic-3-context）。

**Approach:** 在 registration `service.py` 依 contracts/competition.md〈二〉的名稱與關鍵字參數新增四個公開函式。`finalize_for_draw` 在鎖內依序做優先期結算、補做優先期後送出的報名、截止補位，全部沿用 `allocation.py` 與 3.4 的結算；competition 不需修改。

## Decisions（2026-11-04，邱芯彤）

- 3.6 第二階段拆成兩份：本份只做抽籤用的四個函式與共用的截止補位；截止 worker 另記 deferred-work（「Story 3.6 第二階段之二」）。S2「抽籤準備中」B 已做好，不在範圍內。
- 優先期還沒結束時抽籤：照合約〈二〉立即以當下已送出的報名做優先期結算（提前抽籤＝提前結束報名）；在合約〈三〉第 2 項加註 C 已確認可行。
- 抽籤時優先期後送出、仍為 `pending` 的報名：照 FR-15 補做先搶期（依送出順序，結果等同 3.5 做完後），再截止補位。
- spec 約 4,500 tokens，超過 1,600；四個函式在抽籤時一起被呼叫，拆開後仍無法抽籤，保留完整 spec。
- 提前抽籤後（賽事不是開放報名），S17／S12 的候補一律依報名截止後規則顯示順位、原因與規則說明；`_current_phase` 在賽事不是 `open` 時回截止後（取消的賽事也一樣）。（審查 #1）
- 抽籤觸發的結算、補做先搶期、截止補位與 `mark_drawn`，操作紀錄的操作者記主辦方（傳入的 `actor_id`）；worker 自動結算仍為系統（`None`）。這是 epic「操作者 system」的例外。（審查 #7）
- 本 Story 完成時刪除 deferred-work 的三項：「確認抽籤後的報名狀態名稱與 `allocation.py` 一致」、「截止補位與 4.1 的 `finalize_for_draw` 都要先呼叫 `settle_priority_window`」、「補 API 層測試：同校已有 2 隊 `drawn`」；截止 worker 的部分已由「Story 3.6 第二階段之二」涵蓋。（審查 #11）

## Boundaries & Constraints

**Always:**
- 簽名照合約（全部關鍵字參數）：
  - `list_accepted_teams(session, *, tournament_id) -> list[TeamRead]`：報名為 `accepted` 的隊伍，依隊伍 id 排序，隊伍與成員一次查出（不逐隊查詢）。
  - `finalize_for_draw(session, *, tournament_id, actor_id) -> None`
  - `mark_drawn(session, *, tournament_id, team_ids, actor_id) -> None`：`accepted` → `drawn`。
  - `get_team_names(session, *, team_ids) -> dict[UUID, str]`：只依 id 查隊名，不看賽事與報名狀態（抽籤後的公開對戰樹也用）；不存在的 id 不出現。
- `finalize_for_draw` 先 `lock_tournament()`；賽事不是 `open` 或不是校園賽時不做任何事。否則在同一交易依序：
  1. 優先期結算：沒有結算紀錄時，做與 `settle_priority_window` 相同的結算（只結算 `submitted_at <= priority_end` 的 `pending`；結算紀錄、逐筆 `status_changed` 後再寫摘要、事件），但不檢查「優先期已結束」，`settled_at` 為當下時間（可能早於 `priority_end`）。共用的私有函式只做「已鎖定、未結算」的結算，不檢查狀態與時間；worker 版保留「開放中、校園賽、優先期已結束」三個檢查與操作者 `None`。
  2. 補做先搶期：其餘仍為 `pending` 的報名依送出時間（同時再依 id）逐筆處理；每一筆都以最新狀態重建 candidates（`pending`、`accepted`、`drawn`、`waitlisted`），先 `backfill_vacancies(phase=FIRST_COME)` 並把遞補者 `mark_status` 為 `accepted`，再 `decide_first_come`；`priority_schools` 取自結算紀錄。
  3. 截止補位：剩餘名額＝max(名額 − 目前正取（`accepted`＋`drawn`）, 0)，`fill_from_waitlist` 的前 N 名改為 `accepted`。
- 所有狀態變更經 `mark_status`，操作者為傳入的 `actor_id`；`finalize_for_draw` 每筆改為 `accepted`／`waitlisted` 的報名發 `RegistrationAllocated`。`finalize_for_draw` 重複呼叫結果不變。
- `mark_drawn`：先 `lock_tournament()`；`team_ids` 先去重，空清單不做任何事；有任何 id 不存在、不屬於該賽事、或報名不是 `accepted` 時整批拒絕（409 `REGISTRATION_NOT_ACCEPTED`「有隊伍不是這個賽事的正取，無法標為已參賽。」），不做部分更新；只改傳入的隊伍；不發事件。不保證冪等：已是 `drawn` 再呼叫會被拒絕。
- 沒有任何報名的賽事呼叫 `finalize_for_draw` 不得拋錯（示範資料的 `load()` 會對空賽事抽籤）。

**Never:**
- 不改 competition、tournaments 模組與他人測試；不改 `allocation.py` 的規則；不改 `settle_priority_window`／worker 的既有行為（操作紀錄順序也保留）。
- 不做截止 worker、賽事轉「報名截止」、前端畫面；不做撤回、退回、代表隊退出遞補（期中擱置）。
- 不改變 `forming` 的隊伍。

## I/O & Edge-Case Matrix

以下「優先期內」指 `submitted_at <= priority_end`，學校以大寫字母、積分以數字表示。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 優先期內提前抽籤 | 名額 2；X30、Y28、Z26 各 1 隊優先期內 `pending`；優先期未結束 | X、Y `accepted`，Z `waitlisted`；結算紀錄的學校為 X、Y、Z；補位無空位 | N/A |
| 同校多隊 | 名額 4；A30、A25、A20、B28 優先期內 `pending`，優先期已結束、尚未結算 | 結算：A30、B28 正取，A25、A20 候補；補位補 A25（A20 會使 A 校超過 2 隊而略過）；共 3 隊正取、保留 1 空位 | N/A |
| 已結算 | 同上，但 worker 已結算 | 不重複結算（摘要操作紀錄仍只有 1 筆）；只補位，結果同上 | N/A |
| 優先期後送出 | 名額 3；P30 優先期內；之後依序送出 Q20、Q25、R22、P28 皆 `pending` | P30 結算正取；Q20 正取、Q25 候補（Q 校已有正取）、R22 正取、P28 候補（優先期學校）；補位無空位；之後沒有 `pending` | N/A |
| 優先期學校晚送出 | 名額 4；P30 優先期內；之後送出 P28 | P28 先搶期判為候補，截止補位再補為正取；共 2 隊正取、保留 2 空位 | N/A |
| 名額已滿 | 名額 2；2 隊 `accepted`、1 隊 `waitlisted`，已結算 | 不改任何狀態、不發事件 | N/A |
| 重複呼叫 | 已呼叫過一次 | 狀態、操作紀錄、事件都不增加 | N/A |
| 沒有報名 | 只有 `forming` 或沒有隊伍 | 不改任何報名；`list_accepted_teams` 回空清單；經 competition 抽籤回 409 `NOT_ENOUGH_TEAMS`；示範資料 `load()` 照常完成，示範賽事沒有留下結算紀錄 | N/A |
| 賽事不是開放報名 | `published`、`closed` 等 | `finalize_for_draw` 不做任何事 | N/A |
| 完整抽籤 | 開放報名中、報名截止前；至少 2 隊會正取；經 competition `draw`（操作者為主辦方） | 正取隊伍進對戰表、報名轉 `drawn`、賽事轉 `published`；分配與 `drawn` 的操作紀錄操作者為主辦方 | N/A |
| 抽籤後的候補 | 上列抽籤後，仍為 `waitlisted` 的隊伍 | 狀態不變、不在 `list_accepted_teams`；S17／S12 `waitlist_phase == "after_deadline"`（即使還沒到報名截止時間） | N/A |
| 抽籤後同校 2 隊已參賽 | A 校 2 隊 `drawn`、1 隊 `waitlisted` | 該候補 `waitlist_reason == "SCHOOL_LIMIT_REACHED"` | N/A |
| mark_drawn 混入他隊 | team_ids 含不存在、別的賽事、`forming` 或非 `accepted` 的隊伍 | 整批不改 | 409 `REGISTRATION_NOT_ACCEPTED` |
| mark_drawn 重複 id、空清單 | 重複的 id；或空清單 | 去重後照常處理；空清單不做任何事 | N/A |
| 名稱查詢 | 含不存在的 team_id；或 `drawn` 的隊伍 | 只回傳存在的；不看狀態 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/service.py:207-329` `draw` -- 只在賽事 `open` 時呼叫 `finalize_for_draw`（`:238`）；之後 `list_accepted_teams`（不足 2 隊 409 `NOT_ENOUGH_TEAMS`）、`get_team_names`（自行排序；`:362`、`:504` 抽籤後也用）、`mark_drawn(team_ids=全部正取)`、轉 `published`；同一交易。不修改
- `backend/app/modules/competition/registration_port.py` -- 執行當下以名稱查找四個函式，只讀 `TeamRead.id`；不修改
- `backend/tests/competition/conftest.py:82-104`、`test_registration_port.py` -- `fake_registration` 換掉 port 函式；`registration_without_draw_functions` 用 `delattr(raising=False)`，真函式存在後仍通過。不修改
- `backend/app/demo_data/competition.py:29-53` -- 示範抽籤在 `begin_nested()` 內，只接 `BusinessError` 並 log 略過；示範資料沒有報名，函式存在後改為 `NOT_ENOUGH_TEAMS` 略過，savepoint 回滾提前寫的結算紀錄。`tests/identity/test_demo_data.py`、`tests/tournaments/test_demo_data.py` 會真的跑 `load()`；不要輸出含「already exists, skipped」的 log
- `backend/app/modules/registration/service.py` -- `:814` `settle_priority_window`（抽出鎖內結算，更新 docstring 中「3.6 截止補位前也會呼叫本函式」）；`:375` `_current_phase`（加賽事狀態判斷）；`:357` `_candidate`、`:222` `mark_status`、`:276` `_team_read`；`_TRANSITIONS`（`accepted`→`drawn`、`waitlisted`→`accepted` 已允許）
- `backend/app/modules/registration/allocation.py` -- `backfill_vacancies`、`decide_first_come`（呼叫端契約見 docstring）、`fill_from_waitlist`（`remaining` 為負數會拋 `ValueError`）；不改
- `backend/app/modules/registration/repository.py` -- 已有 `list_registrations`、`get_settlement`；新增依 team_ids 查隊伍與報名、依賽事與狀態查隊伍與成員
- `backend/app/modules/registration/models.py` -- 沿用事件 `RegistrationAllocated`
- `backend/tests/worker/test_priority_window_allocation.py:58-140` -- `_tournament`、`_school`、`_submitted`、`_in_window` 等 helper（建出的隊伍沒有成員，不影響本 Story）；worker 測試會檢查操作紀錄順序
- `backend/tests/competition/test_draw.py:203` -- 開放報名中抽籤的測試寫法（用 `fake_registration`；本 Story 的完整抽籤測試不用它，直接呼叫 `competition.service.draw`，`actor_id` 為 `tournament.organizer_id`）

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/repository.py` -- 依 team_ids 查隊伍與報名；依賽事與狀態一次查出隊伍與成員
- [x] `backend/app/modules/registration/service.py` -- 抽出鎖內結算；新增補做先搶期與截止補位的私有函式（之後截止 worker 沿用）；四個公開函式；`mark_drawn` 的 409 錯誤；`_current_phase` 在賽事不是 `open` 時回截止後
- [x] `backend/tests/registration/test_draw_functions.py` -- I/O 矩陣每一列；操作紀錄的操作者與事件數量；經 competition `draw` 的完整抽籤（不用 `fake_registration`）；抽籤後候補的 S17／S12 回應；示範資料 `load()` 後示範賽事沒有結算紀錄
- [x] `backend/tests/registration/test_settlement_concurrency.py` -- AD-6 鎖的併發測試（照 `tests/registration/test_team_concurrency.py`：兩個 session＋`threading.Barrier` 同時結算同一場賽事，worker 對 worker、worker 對 `finalize_for_draw` 各一）；斷言兩個 session 都沒有拋錯，且只結算一次（1 筆結算紀錄、1 筆摘要操作紀錄、每筆報名只改一次狀態、事件不重複）。把鎖換成不加鎖的讀取時，第二個 session 會撞結算表主鍵而失敗，測試要因此失敗
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- 〈二〉registration 表註明四個函式已提供、〈一〉的抽籤錯誤碼加 409 `REGISTRATION_NOT_ACCEPTED`；〈三〉第 2 項依 Decisions 第 2 點加註 C 已確認（只加註，不改 D 寫的內容）
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 依 Decisions 刪除三項

**Acceptance Criteria:**
- Given 開放報名、已有送出隊伍的賽事，when 主辦方經 competition 抽籤，then 不再回 503，正取隊伍進對戰表，報名為 `drawn`。
- Given 抽籤後，when 隊員打開 S17／S12，then 正取隊伍顯示「已參賽」，候補依截止後規則顯示順位或原因。
- Given 後端，when 執行 `scripts/test.sh`、`lint.sh`，then 全部通過，`tests/competition/` 不需修改。

## Implementation Notes

- 3.6 的截止補位規則已在 3.4 第一階段完成（`allocation.py` 的 `fill_from_waitlist`）；本 Story 把規則接到抽籤流程。
- 2026-11-04 核准後追加（邱芯彤同意）：Tasks 新增 `test_settlement_concurrency.py`。來源是 #50（3.4 第二階段）的審查：「AD-6 的鎖沒有測試：把 `_lock_tournament` 換成不加鎖的讀取，所有測試仍會通過」。同一份審查的另一項「優先期內抽籤時 `settle_priority_window` 什麼都不做」已由 Boundaries 的共用私有函式（不檢查優先期已結束）涵蓋，抽籤不要直接呼叫 `settle_priority_window`；3.4 spec 的 Decisions 與 deferred-work 中「在鎖內呼叫 `settle_priority_window`」的說法對提前抽籤不成立，以本 spec 為準。

- 實作（2026-11-04）：鎖內結算抽成 `_settle_locked`（worker 的 `settle_priority_window` 操作者仍為 `None`、操作紀錄順序不變）；補做先搶期 `_first_come_locked`、截止補位 `_fill_at_deadline_locked` 給下一份截止 worker 沿用；分配共用 `_allocate`（`mark_status`＋`RegistrationAllocated`）。repository 新增 `list_teams_by_ids`、`list_registrations_by_team_ids`、`list_teams_with_members_by_status`（隊伍一次、成員一次）。
- 驗證：`docker compose up -d --build --wait` 後 `scripts/test.sh` 1944 passed（含 `tests/competition/`、demo data 測試，未修改 competition 測試），`scripts/lint.sh` 通過。併發測試把 `_lock_tournament(session, tournament_id)` 換成 `_get_tournament` 後兩個參數組都失敗（第二個 session 撞 `priority_window_settlement_pkey`）。

## Spec Change Log

## Review Triage Log

| # | 來源 | 發現 | 判定 | 依據 | 處理 |
|---|------|------|------|------|------|
| 1 | blind | 送出報名與 `finalize_for_draw` 競態，抽籤後留下 `pending` | false | `submit_registration` 先 `_lock_tournament`，鎖內 `_ensure_registration_period` 檢查賽事是否開放；抽籤後已是 `published`，送出被拒 | 駁回 |
| 2 | blind | 自訂模式抽籤沒有定義 | false | 凍結區塊明訂不是校園賽時不做任何事；自訂模式分配是 3.10（擱置） | 駁回 |
| 3 | blind | 新的 deferred-work 項目 `source_spec: none` | false | step-01 拆分時的格式規定就是 `none` | 駁回 |
| 4 | blind | 凍結區塊內有審查來源的 Decisions | false | 規劃階段經使用者核准寫入，不是實作改動；修正方式是改 spec | 駁回 |
| 5 | blind | 沒有更新 registration 合約 | false | `contracts/` 只有 competition、tournaments，沒有 registration 合約 | 駁回 |
| 6 | blind | `_current_phase` 只測已公布一種狀態 | low | 分支條件是 `status == OPEN`，其他狀態走同一分支；補測試對日常使用無影響 | 駁回 |
| 7 | blind、edge | `_first_come_locked` 每筆重查全部報名（O(n²)，持鎖） | low | 一場報名數為數十筆，查詢成本可忽略；改成記憶體內更新要多一層狀態同步 | 駁回 |
| 8 | blind | 排序用 `_candidate()`，`submitted_at` 為空時拋錯 | false | `pending` 必經 `submit_registration` 寫入快照；`_candidate` 本來就對缺快照拋錯 | 駁回 |
| 9 | blind | `get_team_names` 測試在查不到隊伍時仍會通過 | low | `expected` 以條件過濾建出，會跟著結果縮小；直接改斷言即可 | patch |
| 10 | blind | `mark_drawn` 長度比對依賴報名與隊伍 1:1、不檢查賽事狀態 | false | `Registration.team_id` 為 unique；只由 competition `draw` 在同一鎖與交易內呼叫 | 駁回 |
| 11 | blind | `.in_(members)` 傳 dict | false | 迭代 dict 即 key，行為正確，沒有實害 | 駁回 |
| 12 | blind | 併發測試沒有檢查摘要的操作者、缺 draw 對 draw | low | 操作者由哪個 thread 先拿到鎖決定，非確定；draw 對 draw 與 worker 對 draw 走同一把鎖 | 駁回 |
| 13 | blind | `_allocated_events` 撈出全部事件再過濾 | low | 只在測試內，資料量小 | 駁回 |
| 14 | blind | 測試匯入其他測試檔的私有 helper | low | 沿用既有測試寫法；重新命名時測試會立刻失敗，不會靜默出錯 | 駁回 |
| 15 | blind | `settle_priority_window` docstring 過期、Code Map 行號已移動 | false | 該函式本身仍不處理優先期後的 `pending`，敘述正確；行號屬 spec 內容 | 駁回 |
| 16 | edge | 提前抽籤正取不足 2 隊時，結算紀錄已寫入 | false | competition router 只在成功時 `commit`；`BusinessError` 時不提交，示範資料用 savepoint 回滾 | 駁回 |
| 17 | edge | 併發測試 thread 逾時後仍執行清理 | low | 只在測試卡住 30 秒以上時發生，且斷言已先失敗 | 駁回 |
| 18 | verification-gap | 沒有驗證缺口 | — | 已追蹤每個分支對應的測試 | 無 |

## Design Notes

- 共用的結算抽成私有函式，worker 的 `settle_priority_window` 與 `finalize_for_draw` 各自決定「要不要檢查到期」與操作者（Decisions）。
- 補做先搶期與截止補位寫成「已鎖定賽事」的私有函式，下一份 spec 的截止 worker 鎖住賽事後直接呼叫，再轉「報名截止」；屆時再決定是否公開為 `fill_at_deadline`。
- 步驟 2 每筆都重建 candidates：`decide_first_come` 用其他報名的正取數判斷學校資格與名額，前一筆剛正取的隊伍必須算進去，否則會超收或同校兩隊正取。
- `mark_drawn` 先整批檢查再改狀態；competition 失敗會整筆回滾，但 registration 不依賴這一點。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠（含 `tests/competition/`、demo data 測試）
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
