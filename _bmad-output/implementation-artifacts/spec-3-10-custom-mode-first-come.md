---
title: 'Story 3.10：自訂模式的先到先得分配（第 1 部分：分配與遞補）'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: 'f86005e45d7a4f5790bece5a03978f8ae1640c09'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-11-roster-changes-and-disband-team.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 自訂賽事送出報名後停在 `pending`，撤回、退回、提高名額、取消資格與抽籤後退賽都不遞補，同校隊伍互打的校內賽無法分配名額（FR-39）。

**Approach:** 在 `allocation.py` 加自訂模式的獨立分支（AD-20）：送出時不檢查學校，名額有剩立即正取、否則候補；候補依送出時間排序、全部有順位、沒有每校上限；名額釋出時由最早送出的候補遞補。判定前鎖賽事（AD-6）。本部分只改 registration，不碰 tournaments。

## Decisions（2026-11-23，邱芯彤）

- 拆成兩部分、各自一個 PR（比照 3.9）。第 1 部分（本 spec）：分配、遞補、截止、抽籤後退賽、併發測試與候補說明文字，只改 registration，現在就實作。第 2 部分：建立賽事的模式選項、賽事報名連結與重設、建隊檢查 `TOURNAMENT_INVITE_REQUIRED`、S1／S2／S27、示範資料（7.1）；等 B 的 PR #103 合併並同步 main 後再做，未合併就停下來問使用者。
- 抽籤前取消資格（6.5）空出的名額，自訂賽事立即由最早送出的候補遞補（自訂賽事沒有截止補位）。
- 介面文字：候補狀態下方的遞補規則說明（自訂）為「自訂賽事依送出時間遞補，沒有每校隊數上限。」
- 第 2 部分已定（本部分不做，第 2 部分 spec 沿用）：
  - 賽事報名連結為 S2 加查詢參數 `/tournaments/{id}?invite={token}`，S2 讀到有效 token 才顯示「建立隊伍」，建隊時把 token 帶給後端。
  - 重設連結後，已建立的隊伍不受影響（連結只在建隊時檢查）。
  - 文字：S1 標籤「邀請制報名」；S2 沒有連結時「這是邀請制賽事，請向主辦方索取報名連結。」、連結已失效時「報名連結已失效，請向主辦方索取新的連結。」；S27 欄位「賽事報名連結」、說明「持有這個連結的帳號才能建立隊伍。」；重設確認框（destructive）標題與按鈕「重設報名連結」、內文「重設後舊連結立即失效，已建立的隊伍不受影響。」、成功 Toast「已重設報名連結」。

## Boundaries & Constraints

**Always:**
- 送出（自訂）：鎖賽事後判定；不檢查隊員學校（S17 也不列「未設定學校」「學校不同」）；名額有剩立即 `accepted`，否則 `waitlisted`；隊長與選手收到報名結果通知（沿用 `RegistrationAllocated`）；回應直接帶「正取」或「候補第 N 位」。
- 候補順位（自訂）：依 (送出時間, 報名 id)，所有候補都有順位，沒有「目前不在遞補順序中」。
- 遞補（自訂）：撤回（3.7，含報名截止後、抽籤前）、退回（3.8）、提高名額、抽籤前取消資格（6.5）釋出名額時，在同一交易內由最早送出的候補遞補並通知（沿用 `RegistrationBackfilled`）；沒有每校上限、不需優先期結算。取消資格只在「鎖內賽事狀態為 `open` 或 `closed`，且被取消的報名原本是 `accepted`」時遞補；抽籤後的取消資格不在這裡遞補，由 4.5 的 `backfill_drawn_from_waitlist` 取最早送出的候補接手位置。
- 報名截止（自訂）：只轉「報名截止」，不執行截止補位（3.6）；優先期結算不處理自訂賽事（維持現狀）。
- AD-20：學校檢查、階段、送出時的正取或候補判定、候補排序、遞補對象都由 `allocation.py` 依模式提供；service 只呼叫這些函式，本 Story 新增的程式不在 service 自行判斷 `mode`。校園賽的行為與既有校園賽測試結果不變。

**Never:**
- 不改 tournaments 模組與建立賽事流程，不做賽事報名連結（第 2 部分）。
- 不改 competition（D）的既有函式；4.5 經既有的 registration 公開函式取得結果。
- 不沿用校園賽專用的 `_first_come_locked`、`_representative_backfill_locked`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 有名額送出 | 自訂、名額有剩、隊員不同校或未設學校 | 立即正取；通知隊長與選手 | N/A |
| 額滿送出 | 自訂、名額已滿 | 候補第 N 位（依送出時間） | N/A |
| 最後一個名額 | 自訂、剩 1 名額、多隊同時送出 | 只有 1 隊正取；平行 200 筆正取不超過名額、無遺失或重複 | N/A |
| 撤回或退回 | 自訂、正取撤回或被退回、有候補 | 最早送出的候補遞補並通知；同校已有 2 隊正取也遞補 | N/A |
| 提高名額 | 自訂、提高名額、有 3 隊候補 | 依送出順序遞補到新名額 | N/A |
| 截止後撤回 | 自訂、報名截止後抽籤前，正取撤回、有候補 | 最早送出的候補遞補並通知 | N/A |
| 抽籤前取消資格 | 自訂、正取被取消資格、有候補 | 最早送出的候補遞補並通知 | N/A |
| 抽籤後取消資格 | 自訂、抽籤後取消一隊、有候補 | 取消資格本身不產生 `accepted`、不發 `RegistrationBackfilled`；由 4.5 讓最早送出的候補接手位置 | N/A |
| 沒有候補 | 自訂、名額釋出、沒有候補 | 名額空著，不出錯 | N/A |
| 報名截止 | 自訂、截止時間到 | 轉「報名截止」，不補位、正取與候補不變 | N/A |
| 抽籤後退賽 | 自訂、抽籤後退賽、有候補 | 最早送出的候補接手位置（不受每校上限） | 沒有候補時照 4.5 輪空 |
| 候補畫面 | 自訂、候補隊伍開 S17／S12 | 「候補第 N 位」＋「自訂賽事依送出時間遞補，沒有每校隊數上限。」 | N/A |
| 校園賽不變 | 校園賽各階段 | 行為與既有測試結果不變 | N/A |

</frozen-after-approval>

## 第 2 部分待決事項

第 1 部分不處理；規劃第 2 部分時逐項請使用者決定，決定後寫進第 2 部分 spec 的 Decisions。

- **開放報名前切換賽事模式**（2026-11-23 記錄）
  - 來源：B 的 PR #117（Story 2.5 抽籤前修改賽事）spec 寫「不做賽事模式的修改：自訂模式屬 3.10（C，尚未做），目前只有校園賽，API 不接受 `mode`」；AD-20 允許賽事「尚未開放」時修改模式（ARCHITECTURE-SPINE.md:190），FR-9 同。
  - 要決定：第 2 部分要不要在 2.5 的 S28 賽事設定頁加模式切換。若要做，還要決定切換時 `invite_token` 的處理（校園賽→自訂產生 token、自訂→校園賽清除），以及 `TournamentUpdate` 要新增 `mode` 欄位（B 的模組，只能新增）。
  - 備註：#117 修改賽事時以「報名開始＋優先期長度」重算 `priority_end`，與本 spec「自訂賽事優先期長度為 0」一致。
  - 時程：第 2 部分等 #117 合併後再規劃（#117 與第 2 部分改同一批 tournaments 檔案與 `CreateTournamentForm.tsx`）。

## Code Map

- `backend/app/modules/registration/allocation.py` -- 純函式；`AllocationPhase`(:42) 只有 FIRST_COME、AFTER_DEADLINE；`_submit_key`(:114) 已是 (送出時間, id)；`waitlist_order`(:197) 分派到 `_first_come_order`(:227)／`_after_deadline_order`(:285)；`backfill_vacancies`(:316)；`Candidate`(:73) 的 `school_id` 要改為可為 None。加 `AllocationPhase.CUSTOM`（值 `"custom"`）與依模式回答的函式：要不要檢查學校、目前階段、送出時判正取或候補、遞補對象（AD-20，ARCHITECTURE-SPINE.md:190）。此檔分支覆蓋率要 ≥ 90%（README:140，`scripts/test.sh` 與 CI 檢查），目前 100%；測試 `tests/registration/test_allocation.py`。
- `backend/app/modules/registration/service.py`
  - `submit_registration`(:968-1057)：鎖(:988) → 期間 → blockers(:1003) → 快照(:1027) → `pending`；即時分配只在 CAMPUS(:1051)。自訂另走分支，不呼叫 `settle_priority_window`。
  - 學校檢查在 `player_profile.py:117` `submit_blockers`（SCHOOL_MISSING :141、SCHOOL_MISMATCH :148），不分模式，也供 S17 的 `submit_blockers`(service.py:637)。自訂依 allocation 的回答跳過。自訂賽事送出時快照 `school_id` 一律寫 null（期中文件 B:1034；service.py:1010 現取 `entries[0].school_id`，自訂不適用）；容許 null 的地方：service.py:1010-1015 的 RuntimeError、`_candidate`(:464-472)、S29 的 `_organizer_sorted` 與 `_organizer_items`（都呼叫 `_candidate`）。
  - 候補順位：`_current_phase`(:482)、`_waitlist_order`(:537)、`_waitlist_fields`(:506)、`_first_waitlisted`(:2304) 不分模式，自訂要回 CUSTOM 階段。
  - 遞補：`_backfill_released_locked`（定義 :1390，模式判斷在 :1398）對非 CAMPUS 直接返回，撤回(:1519)、提高名額(:1545)、退回(:1848) 都經過它；改成依 allocation 的回答。`_allocate`(:1124) 發 `RegistrationAllocated`、`_backfill`(:1350) 發 `RegistrationBackfilled` 並設 `backfilled_at`，沿用。`disqualify_registration`(:2246) 目前不遞補；抽籤前（`competition/disqualification.py:324`）與抽籤後（`competition/retirement.py:335`，接著 :339 呼叫 `backfill_drawn_from_waitlist`）都會呼叫它，所以只在鎖內賽事狀態屬於 `_WITHDRAWABLE_TOURNAMENT_STATUSES`(:570，open／closed) 且原狀態為 `accepted` 時遞補。
  - 4.5：`has_backfill_candidate`(:2334) 與 `backfill_drawn_from_waitlist`(:2354) 對自訂回 False／None；competition 經 `competition/registration_port.py:189/:199` 呼叫（retirement.py 不改）。deferred-work.md:217-218 已要求 3.10 經 `allocation.py` 處理。`finalize_for_draw`(:2180) 對自訂 no-op：釋出時已即時遞補，維持即可。
  - 維持不變：`close_registration`(:1441/:1455) 自訂只轉狀態；`_priority_window_due`(:1115) 跳過自訂。
- `backend/app/modules/registration/models.py` -- 只在 `WaitlistPhase`(:328-331) 加 `"custom"`；`WaitlistReasonCode` 不加（自訂候補全部有順位）。自訂時 `waitlist_reason` 一律 null、`representative_backfill` 一律 false（`WaitlistFields` :334）。
- 前端 `frontend/src/features/registration/registration-status.tsx`（字串與 EXPERIENCE.md〈固定介面字串〉逐字對應，:199-206）-- `waitlist_phase` 為 `custom` 時顯示新字串；S12、S17、S29（`OrganizerRegistrationsPage`）都經它顯示。`scripts/generate-client.sh` 重新產生 client。
- `_bmad-output/planning-artifacts/ux-designs/.../EXPERIENCE.md`〈固定介面字串〉-- 加「遞補規則說明（自訂）」一列（registration-status 註明逐字對應）。
- 測試
  - 既有測試斷言「自訂什麼都不做」，這些正是本 Story 要改的行為，改成新的期望（不是為了讓測試通過）：`tests/registration/test_first_come_submission.py:553`、`tests/registration/test_reject_registration.py:854`、`tests/registration/test_post_draw_backfill.py:169`。維持不改：`tests/registration/test_draw_functions.py:459` 與 `tests/competition/test_draw_status.py:550`（`finalize_for_draw` 對自訂 no-op，行為不變；後者是 D 的測試）、`tests/worker/test_registration_deadline.py:451`（截止只轉狀態）。
  - 設自訂模式：`row = session.get(Tournament, id); row.mode = TournamentMode.CUSTOM`（範例 `test_reject_registration.py:118 _set_mode`、`test_post_draw_backfill.py:37`）。
  - 併發範本 `tests/registration/test_first_come_concurrency.py`（`_setup`、`_submit_all`、`_check`；`_check` 斷言每校一隊與結算存在，自訂版不適用）。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/allocation.py`、`backend/tests/registration/test_allocation.py` -- CUSTOM 分支與單元測試（分支覆蓋率 ≥ 90%）。
- [x] `backend/app/modules/registration/service.py`、`player_profile.py`、`models.py` -- 自訂的送出、跳過學校檢查、候補順位、各遞補入口、4.5 的候補查詢。
- [x] `backend/tests/registration/test_custom_mode.py` -- I/O 矩陣 registration 層各列（含先鎖再判定：另一連線先鎖住賽事，確認送出會等鎖；通知事件；校園賽不變的對照）；改寫上列三支既有測試。
- [x] `backend/tests/competition/test_custom_post_draw_backfill.py` -- 新檔（只新增，不改 D 的模組）：經 competition 的抽籤後退賽與取消資格流程，最早送出的候補接手位置、取消資格本身不產生 `accepted`（epics 4.5 自訂模式的 AC）。
- [x] `backend/tests/registration/test_first_come_concurrency.py` 或新併發檔 -- 自訂模式平行 200 筆與最後一席。
- [x] `backend/tests/traceability.yaml` -- 新檔各一列、改過的既有檔 stories 加 "3.10"。
- [x] `frontend/src/client`、`frontend/src/features/registration/registration-status.tsx`、對應單元測試（S17 與 S29 各一案例） -- 自訂候補說明。
- [x] `_bmad-output/planning-artifacts/ux-designs/` 的 EXPERIENCE.md -- 〈固定介面字串〉加「遞補規則說明（自訂）」；只加字串、不影響需求，commit 訊息 body 加一行 `Epic-Context: unaffected`（否則 epic-3 context 會被判定過期）。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 spec-4-5 的「自訂模式抽籤後退賽／取消資格的遞補沒有做」那一項（本 Story 處理完）。
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 3-10 改 `in-progress`（第 1 部分完成後仍維持 `in-progress`）。
- [x] `docs/ai-usage/C-邱芯彤.md` -- 記錄本部分的 AI 使用。

**Acceptance Criteria:**
- Given I/O 矩陣，when 檢查測試，then 每一列至少有一個會執行且通過的測試。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh`、前端測試，then 全部通過，`allocation.py` 分支覆蓋率 ≥ 90%，既有校園賽測試不需修改。
- Given 本 Story 新增的 service 程式，when 檢查，then 沒有自行判斷 `tournament.mode`，都經 `allocation.py`（AD-20）。
- Given 本部分沒有建立自訂賽事的介面，when 驗收，then 以整合測試直接把賽事設為自訂來驗證；E2E 留到第 2 部分。

## Implementation Notes

實作（2026-11-24，子代理，待人確認）：

- `allocation.py`（AD-20 依模式回答，service 只呼叫）：
  - `AllocationMode`（campus／custom，值與 `TournamentMode` 相同；allocation 不能 import tournaments，service 以 `_mode()` 轉換，有單元測試比對兩者的值）。
  - `AllocationPhase.CUSTOM = "custom"`；`waitlist_order(phase=CUSTOM)` 依 (送出時間, id) 全部有順位、沒有原因、`representative_backfill=False`；`backfill_vacancies(phase=CUSTOM)` 沿用。
  - 依模式的判斷：`checks_school`、`needs_settlement`（遞補前要不要有結算紀錄）、`backfills_on_disqualify`、`submit_allocation`（`DEFER`／`FIRST_COME`／`IMMEDIATE`）、`current_phase(mode, before_deadline=)`；送出判定 `decide_custom`（正取數未達名額即正取）。
  - `Candidate.school_id` 改為可為 None。
- `service.py`：
  - 送出：`allocation.submit_allocation` 決定流程；自訂走新的 `_custom_locked`（鎖內、依送出順序判定所有 `pending`，每筆先 `_backfill_released_locked` 再 `decide_custom`，發 `RegistrationAllocated`）。不檢查學校時學校快照寫 null。
  - `_current_phase` 改呼叫 `allocation.current_phase`；`_backfill_released_locked` 的模式判斷改為 `allocation.needs_settlement`，撤回／退回／提高名額因此對自訂立即遞補。
  - `disqualify_registration`：鎖內賽事為 open／closed、原狀態為 `accepted`、且 `allocation.backfills_on_disqualify` 時遞補。
  - `has_backfill_candidate`、`backfill_drawn_from_waitlist` 拿掉「非校園賽回 False／None」，順位由 `_waitlist_order`（自訂為 CUSTOM 階段）決定。
  - `_candidate` 容許學校為 null；`_settle_locked` 的優先期學校清單略過 null（只有型別需要）。
  - 維持不變的既有模式判斷：`_priority_window_due`、`close_registration`、`reject_registration` 的先結算、`finalize_for_draw`、`list_public_accepted_teams`。
- `player_profile.submit_blockers` 加 `check_school`（預設 True，S17 與送出都傳 `allocation.checks_school`）。
- `models.py` 只在 `WaitlistPhase` 加 `"custom"`。
- 前端：重新產生 client（只有 `waitlist_phase` 型別多 `"custom"`）；`WAITLIST_PHASE_RULES.custom`；S17、S29 各一個單元測試。
- 實作時自行決定（spec 沒寫）：
  - `_custom_locked` 每筆判定前先讓有順位的候補遞補（比照 `decide_first_come` 的呼叫端契約）；名額釋出時已立即遞補，正常不會有作用。
  - 「先鎖再判定」放在 `test_custom_mode.py` 檔尾：另一連線鎖住賽事列後送出的執行緒 1.5 秒內仍未完成，持鎖方再占走最後一席並提交，送出結果必須是候補。這支測試要提交資料，所以從 `test_custom_concurrency.py` 匯入 `_setup_custom`。
  - 測試賽事名額下限為 2（`TournamentCreate` 驗證），矩陣「名額 1」的情境改為名額 2 加一支既有正取。
  - 併發測試結束時除了刪資料，另把賽事改為已取消（沿用 `test_settlement_concurrency._cancel`），避免留在資料庫的開放賽事被 worker 測試挑到。
- 改寫的既有測試（行為本來就是本 Story 要改的）：`test_first_come_submission.py::test_custom_mode_submission_is_allocated_immediately`、`test_reject_registration.py::test_custom_mode_reject_backfills_earliest_waitlisted`、`test_post_draw_backfill.py::test_backfill_in_custom_mode_takes_earliest_submitted`。其他既有測試沒有修改。
- 未做：`docs/ai-usage/C-邱芯彤.md` 的實作紀錄留給主流程（比照 3.11）；E2E 屬第 2 部分。
- 驗證（2026-11-24；`docker build` 兩個映像後 `docker compose up -d --no-build --wait`）：
  - 後端 `scripts/lint.sh` 通過；`scripts/test.sh` 2902 passed（覆蓋率 97%），`allocation.py` 分支 46/46（100%）。
  - 改動前先跑 registration／competition／worker：只有上列三支「自訂什麼都不做」的既有測試失敗（1811 passed、3 failed），其餘校園賽測試不需修改。
  - 前端 `bunx vitest run` 80 檔 1212 passed；`bunx biome check src tests`、`bunx tsc --noEmit -p tsconfig.json` 通過。
- 瀏覽器檢視（2026-11-24，使用者要求；審查修正後）：暫時的 Playwright 腳本（看完即刪，不提交）建立名額 2 的賽事後以 SQL 改為自訂，桌機與 375 px 各 2 passed、各 7 張截圖。
  - S17：第 1 隊改成混校（隊員分屬世新大學、龍華科技大學）仍可送出，沒有學校相關條件；送出後立即顯示「候補第 2 位」與自訂遞補說明；資料庫確認學校快照為 null。
  - S12、S29：候補列顯示「候補第 N 位」與「自訂賽事依送出時間遞補，沒有每校隊數上限。」；375 px 改為卡片，無水平捲動。
  - 正取隊撤回（API）後，S29 顯示最早送出的候補「已遞補為正取」、第 1 隊升為「候補第 1 位」；被遞補隊的 S17 徽章為「已遞補為正取」。
  - 沒有發現要修正的畫面問題。

## Spec Change Log

## Review Triage Log

spec 審查（2026-11-23，獨立子代理；主流程抽查 #1、#2、#4 屬實）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| 1 | 取消資格的遞補沒限定抽籤前；抽籤後 `retirement.py:335` 也呼叫 `disqualify_registration`，會先遞補成 `accepted` 再被 4.5 頂替，造成重複遞補 | high | 已修正：限定 open／closed 且原為 `accepted`；矩陣加「抽籤後取消資格」列 |
| 2 | spec 要求在 service 多處加 `if mode`，違反 AD-20「其他程式不得自行依模式分支」，也與 Boundaries 矛盾 | medium | 已修正：allocation 依模式提供判斷，service 只呼叫；加 AC |
| 3 | 自訂賽事的學校快照沒講死（現取第一位隊員的學校） | medium | 已修正：一律 null，列出要容許 null 的地方（含 S29） |
| 4 | 4.5 自訂 AC 沒有經 competition 的整合測試；deferred 項目處理完未刪除 | medium | 已修正：新增 competition 測試檔；Tasks 加刪除 deferred 項目 |
| 5 | `WaitlistReasonCode` 不該加自訂值；新階段的值未指定 | low | 已修正：只加 `WaitlistPhase="custom"` |
| 6 | 既有測試清單缺目錄；`finalize_for_draw` 兩支測試行為不變卻列在要改 | low | 已修正：補目錄，兩支改列為維持 |
| 7 | 新字串沒寫回 EXPERIENCE.md；S29 也會顯示 | low | 已修正：Tasks 加 EXPERIENCE.md 與 S29 測試 |
| 8 | AC 太少；「先鎖再判定」無可測方式 | low | 已修正：AC 加矩陣每列有測試；寫出另一連線先鎖的測法 |
| 9 | 截止後、抽籤前撤回是否遞補沒寫 | low | 已修正：依 FR-17 照樣遞補，矩陣加列 |

實作審查（2026-11-24，三個獨立子代理：Blind Hunter、Edge Case Hunter、Verification Gap；Verification Gap 沒有找到測試缺口）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| R1 | `disqualify_registration` docstring 開頭「本身不做遞補」不分模式，與新增的自訂段落矛盾 | low | patch：限定校園賽 |
| R2 | `allocation.py` 模組說明寫 service「不自行判斷模式」，但 service 仍有 5 處既有的模式判斷 | low | patch：改成只描述本 Story 新增的部分 |
| R3 | `decide_custom` 經 `_accepted_per_school(...).total()` 計算正取數，自訂模式依賴以學校為鍵的程式 | low | patch：直接計數 |
| R4 | `test_allocation.py` 既有校園賽測試 `test_story_3_6_example_deadline_fill` 有純格式的改動，與 AC「既有校園賽測試不需修改」不符 | low | patch：還原 |
| R5 | `test_withdraw_after_deadline_before_draw_backfills` 的註解「截止後仍依送出時間排順位」沒有對應斷言 | low | patch：刪除註解（遞補對象已由 earliest／later 斷言） |
| R6 | 先鎖再判定測試 `join(timeout=30)` 後沒檢查執行緒已結束 | low | patch：加 `assert not submitter.is_alive()` |
| R7 | competition `retirement.py:123`、`:330` 對手未定時：自訂賽事以前一律拒絕，現在有候補就允許（`has_backfill_candidate` 不再對自訂回 False） | low | 不改程式：與校園賽 4.5 行為一致，是本 Story 預期的結果；D 的模組，在 PR 說明列出 |
| R8 | competition `service.py:2605` `disqualify` docstring「抽籤前只改報名狀態，不做遞補」對自訂賽事已不成立 | low | 不改程式：D 的模組不能改既有函式（CLAUDE.md），在 PR 說明列出請 D 更新 |
| R9 | `_candidate` 拿掉校園賽學校快照為 null 的檢查；`_settle_locked` 過濾 null 學校 | low | 駁回：校園賽送出時已在 `submit_registration` 拋 RuntimeError 保證有學校，不會發生；補檢查要加模式參數 |
| R10 | 取消資格遞補沿用 `_WITHDRAWABLE_TOURNAMENT_STATUSES` | false | 駁回：spec Code Map 指定以此集合判斷抽籤前 |
| R11 | 沒有經 API 檢查報名截止後與抽籤後的 `waitlist_phase` | low | 駁回：`current_phase` 對自訂不看 `before_deadline`，單元測試已涵蓋 |
| R12 | 先鎖再判定測試以 1.5 秒 `is_alive` 判斷等鎖，執行緒啟動慢時會因錯的理由通過 | low | 駁回：極少發生，改成確定性的鎖等待偵測要另寫查詢 `pg_locks` |
| R13 | 沒有候補的退賽測試沒檢查輪空的對戰表 | low | 駁回：輪空機制屬 4.5，已有 4.5 的測試；本測試確認沒有接手隊伍 |
| R14 | `_custom_locked` 多筆 `pending` 與送出時有空位加候補的路徑沒有測試；逐筆查詢為 O(n²) | low | 駁回：送出在同一交易內立即判定，自訂賽事不會殘留 `pending`（建立賽事目前一律校園賽） |
| R15 | 自訂賽事殘留 `pending` 時截止與抽籤不會分配 | false | 駁回：同 R14，沒有路徑會產生殘留的自訂 `pending` |
| R16 | 兩筆送出時間相同時，候補順序依 id 而非取得鎖的順序 | low | 駁回：spec 規定依（送出時間, 報名 id）；微秒級相同機率極低 |
| R17 | competition 測試 `_preset` 寫入學校快照，與真實自訂送出（null）不同 | low | 駁回：competition 不讀學校（grep 0 筆），自訂順位不看學校 |
| R18 | 前端沒有 S12 的單元測試 | low | 駁回：Tasks 指定 S17 與 S29；S12 用同一函式，後端測試已檢查卡片欄位 |
| R19 | `traceability.yaml` 的 competition 測試沒列 FR-37 | false | 駁回：該檔不檢查通知，FR-37 是通知 |
| R20 | 審查用的 diff 沒有包含 spec 與 AI 使用紀錄 | false | 駁回：刻意排除（spec 只給 Edge Case Hunter；AI 紀錄在流程最後寫） |
| R21 | 新增的 deferred-work 第 2 部分項目沒提到切換模式的待決事項 | false | 駁回：該項目在本次 baseline 前已新增，deferred-work 只新增不修改；待決事項已在本 spec |

## Design Notes

- 自訂賽事的學校快照可為 null：FR-13 只要求校園賽同校，期中文件 B:1034 寫「自訂賽事與組隊中為空」。
- 遞補在釋出名額的同一交易內完成，所以截止與 `finalize_for_draw` 不需另外補位。

## Verification

**Commands:**
- `docker build -f backend/Dockerfile -t flow-backend:latest .`、`docker build -f frontend/Dockerfile -t espory-platform-frontend:latest .` 後 `docker compose up -d --no-build --wait`
- `docker compose exec -T backend bash scripts/test.sh` -- 全綠，`allocation.py` 分支覆蓋率 ≥ 90%
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- frontend 容器內 `bunx vitest run`、`bunx biome check`、`bunx tsc --noEmit -p tsconfig.json` -- 通過
