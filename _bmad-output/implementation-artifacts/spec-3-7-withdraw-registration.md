---
title: 'Story 3.7：抽籤前撤回報名與提高名額遞補'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: '3b41f171d8d7f1185683ef107cefa646c8a68f80'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 隊伍送出報名後無法退出，正取隊伍不能參賽時名額就浪費掉；主辦方也無法提高名額讓候補遞補（FR-9、FR-17）。

**Approach:** registration 新增「撤回報名」與 `raise_capacity`。兩者都在鎖住賽事後，把釋出的名額依當下階段的遞補規則交給候補；`allocation.py` 補上「優先期代表隊由同校次高遞補」，並接到先搶期分配。前端在 S17 加「退賽」按鈕與確認對話框，被遞補的隊伍在 S17、S12 顯示「已遞補為正取」，並收到通知。

## Decisions（2026-11-22，邱芯彤）

- 撤回與 `raise_capacity` 同一份 spec、同一個 PR。`raise_capacity` 只做後端與 API，S28 的修改畫面留給 B 的 2.5。
- 「優先期代表隊由同校次高遞補」本份新增，PR 說明告知 D（原列在 D 的期末收尾）。同校遞補也接到 `_first_come_locked`，讓 6.5 取消代表隊資格後的下一次先搶期分配走同校遞補；deferred-work 兩項（第 62-63、119-120 行）都刪除。
- 退賽確認對話框：標題「退賽」，內文「退賽後這支隊伍的報名會撤回，無法恢復。若隊伍是正取，名額會由候補遞補。」，確認鈕「退賽」（destructive）。
- 「已遞補為正取」只涵蓋名額釋出後的遞補（撤回、提高名額，以及接到 `_first_come_locked` 的同校遞補）。3.6 截止補位維持「正取」。
- 遞補通知：新增事件 `RegistrationBackfilled`（`registration_id`、`team_id`、`tournament_id`）。在 notifications 只新增一條規則：標題「報名結果：已遞補為正取」，內文「「隊名」在「賽事」已由候補遞補為正取。」，連結 `/teams/{id}`，發給該隊全員。遞補時只發這個事件，不發 `RegistrationAllocated`。
- 退賽按鈕只在抽籤前出現；抽籤後的退賽（`drawn` → `retired`）由 D 的 4.5 處理，4.5 完成前抽籤後的 S17 沒有退賽按鈕。
- spec 約 3,500 tokens（以字元數估算），超過 1,600；保留完整 spec。
- spec 審查後修正（2026-11-22）：階段判斷改用 `_current_phase`；同校遞補後一律再跑一般遞補；錯誤碼定案（見 Boundaries）；矩陣「截止後撤回」一列重寫。

## Boundaries & Constraints

**Always:**
- 撤回：只限隊長；報名狀態為 `pending`、`accepted`、`waitlisted`，且賽事為 `open` 或 `closed`。先 `_lock_tournament`，鎖內 `session.refresh` 報名並使用鎖內拿到的賽事，重新檢查後 `mark_status(to=WITHDRAWN, actor_id=隊長)`（自動寫入 `registration.status_changed`）。
- 遞補（撤回任何報名、提高名額後，在同一個鎖與交易內執行）：
  - 自訂模式、或校園賽還沒有結算紀錄（優先期內）：不遞補。
  - 先搶期或截止後一律用 `_current_phase(tournament)` 判斷，與畫面的候補順位一致。
  - 先搶期：先做同校遞補（優先期學校的代表隊已撤回或被取消資格、該校目前沒有 `accepted`／`drawn` 時，由同校 `waitlisted` 依 `sort_key` 第一名遞補），之後一律再跑 `backfill_vacancies(phase=FIRST_COME)`。
  - 截止後：`backfill_vacancies(phase=AFTER_DEADLINE)`。
  - 沒有空位時 `backfill_vacancies` 回空的，所以撤回候補也照跑，順便補上之前留下的空位。
- 同校遞補寫成 `allocation.py` 的純函式，排序沿用 `sort_key`；`_first_come_locked` 在既有的 `backfill_vacancies` 之前先呼叫它。
- 遞補一律 `mark_status(to=ACCEPTED)`、寫入 `backfilled_at`，並發 `RegistrationBackfilled`（不經 `_allocate`）。
- `raise_capacity(session, *, tournament_id, capacity, actor_id)`：先 `_lock_tournament`，再呼叫 tournaments 新增的公開函式改名額（寫操作紀錄），之後用該函式回傳的賽事（新名額）照上面的規則遞補。API 限主辦方（`ensure_tournament_owner`）。
- 錯誤碼：
  - 非隊長：403（`ensure_captain`）。
  - 報名不可撤回（組隊中、已抽籤、已撤回等，或賽事不是 `open`／`closed`）：409 `REGISTRATION_NOT_WITHDRAWABLE`。不交給 `mark_status`，因為 `forming` → `withdrawn` 是合法轉換（留給 3.11 解散隊伍）。
  - 新名額小於或等於目前名額：422 `CAPACITY_NOT_INCREASED`（`FieldError`，`loc=body.capacity`）。
  - 賽事不是 `upcoming`、`open`、`closed`：409 `CAPACITY_NOT_EDITABLE`。

**Never:**
- 不改 `allocation.py` 既有函式的語意、`_TRANSITIONS`；`disqualify_registration` 本身仍不遞補。
- 不改 tournaments、notifications 的既有函式，只新增（CONTRIBUTING 6.6，PR 說明列出）。
- 不做抽籤後退賽、降低名額、S28 畫面。

## I/O & Edge-Case Matrix

學校以大寫字母表示；括號內是學校與平均段位積分。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 優先期內撤回 | `pending`，沒有結算紀錄 | 轉 `withdrawn`，其他報名不變 | N/A |
| 先搶期撤回一般正取 | 已結算、名額已滿；A（X，先搶期正取）撤回；候補 B（Y，符合規則，最早送出）、C（Y） | A `withdrawn`，B 正取並記 `backfilled_at`、發 `RegistrationBackfilled`，C 仍候補 | N/A |
| 先搶期撤回代表隊 | P 校代表隊撤回；同校候補 P2（80）、P3（90） | P3 遞補 | N/A |
| 代表隊撤回、同校無候補 | P 校代表隊撤回，P 校沒有候補 | 走一般先搶期規則；沒有符合的候補就保留空位 | N/A |
| 6.5 取消代表隊後的先搶期分配 | P 校代表隊被取消資格；之後有隊伍在先搶期送出 | `_first_come_locked` 先由 P 校候補第一名遞補，再判定新送出的報名 | N/A |
| 截止後撤回 | `closed`、名額 5 已滿：Z 校 2 隊、W 校 1 隊（W1）、X、Y 各 1 隊正取；候補 E（Z）、F（W）、G（W）、H（V）；W1 撤回 | F 遞補；E 仍沒有順位（`SCHOOL_LIMIT_REACHED`）；G 為候補第 1 位、H 第 2 位 | N/A |
| 撤回候補 | `waitlisted` 撤回，名額已滿 | 不遞補，其餘候補順位在下次載入時更新 | N/A |
| 提高名額（先搶期） | 名額 4 已滿，改為 6；有 3 隊符合先搶期規則的候補 | 依順位遞補前 2 隊 | N/A |
| 提高名額（優先期內） | 沒有結算紀錄，名額 4→6 | 只改名額 | N/A |
| 非隊長撤回 | 選手呼叫 | 拒絕 | 403 |
| 不可撤回 | `forming`／`drawn`／`withdrawn`，或賽事已 `published` | 拒絕，不改任何資料 | 409 `REGISTRATION_NOT_WITHDRAWABLE` |
| 名額沒有提高 | 新名額小於或等於目前名額 | 拒絕 | 422 `CAPACITY_NOT_INCREASED` |
| 抽籤後改名額 | 賽事 `published` 以後 | 拒絕 | 409 `CAPACITY_NOT_EDITABLE` |
| 撤回與送出同時 | 名額已滿；正取 A 撤回、B 在先搶期送出並行 | 先撤回：A 的名額依遞補規則處理後，B 再依當下規則分配；先送出：B 依當時已滿的名額成為候補，A 撤回後再依遞補規則處理。兩種順序都不超收 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/allocation.py` -- `Candidate`(:71)、`sort_key`、`waitlist_order`(:192)、`backfill_vacancies`(:279，空位＝名額−正取數)；新增同校遞補純函式
- `backend/app/modules/registration/service.py`
  - 可沿用：`_lock_tournament`(:60)、`mark_status`(:235)、`_candidate`(:370)、`_current_phase`(:386)、`_waitlist_fields`(:412，順位每次載入時計算)、`_FIRST_COME_STATUSES`(:959)、`_priority_schools`(:962)、`_registrations_in`(:969)
  - 要改：`_settle_locked`（記下代表隊）、`_first_come_locked`(:979，先同校遞補)
  - 範本：`submit_registration`(:733，隊長檢查與鎖)、`disqualify_registration`(:1206，鎖後 refresh)
- `backend/app/modules/registration/models.py`＋Alembic 遷移 -- `Registration` 加 `backfilled_at`、`is_representative`；`RegistrationAllocated`(:159) 旁新增 `RegistrationBackfilled`；`WaitlistFields`(:224)／`TeamDetail`／`MyTeamCard` 加 `backfilled`（`accepted` 且 `backfilled_at` 有值，抽籤後不再顯示）與 `withdrawable`
- `backend/app/modules/registration/router.py` -- 新增 `POST /teams/{id}/withdrawal`（VerifiedAccount）、`POST /tournaments/{id}/capacity`（VerifiedAccount＋主辦方），router commit；兩者都要登入，不加 `PUBLIC_WRITE_ROUTES`
- `backend/app/modules/tournaments/service.py`、`repository.py` -- `lock_tournament`(:402)、`_field_error`(:241)；新增改名額的公開函式
- `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- :118 提高名額的註記更新、〈二〉加新函式（B 的 #103 也改這個檔案）
- `backend/app/core/authz.py` -- `ensure_captain`(:36)、`ensure_tournament_owner`(:54)
- `backend/app/modules/notifications/rules.py` -- :47 import 加 `RegistrationBackfilled`（唯一改到既有行的地方），規則與 `register` 呼叫加在檔尾，沿用 `_member_ids`(:79)；A 的 #102 也改了這個檔案
- 前端 `frontend/src/features/registration/`
  - `SubmitRegistrationSection.tsx`：依狀態分支；確認框範本 :177-192
  - `useSubmitRegistration.ts`：mutation 範本
  - `registration-status.tsx`：字串與 `RegistrationStatusBadge`
  - `RegistrationStatusCard.tsx`：整張卡片是 `<Link>`，只能放 span
  - 共用元件 `frontend/src/components/common/ConfirmDialog.tsx`
- 測試
  - 後端 helper：`tests/worker/test_priority_window_allocation.py`(`_submitted`:75、`_waitlist`:525)、`tests/worker/test_registration_deadline.py`(`_settled`:137)、`tests/registration/test_first_come_submission.py`(`_settled`:113)、`test_settlement_concurrency.py`、`test_allocation.py:308-326`
  - 前端：`frontend/tests/unit/team-pages.test.tsx`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/allocation.py`、`backend/tests/registration/test_allocation.py`
  - 新增同校遞補純函式與單元測試，分支覆蓋率 90%。
  - 補 epics 範例的 `waitlist_order` 測試：截止後 F=1、H=2，E、G 沒有順位。
  - 同一批報名在 FIRST_COME 與 AFTER_DEADLINE 算出不同順位，兩個階段各一個測試。
- [x] `backend/app/modules/registration/models.py`、`backend/app/alembic/versions/<新檔>.py`：`backfilled_at`、`is_representative`、`RegistrationBackfilled`、回應欄位。
- [x] `backend/app/modules/tournaments/service.py`、`repository.py`：新增改名額的公開函式（檢查狀態與名額、寫操作紀錄、回傳 `TournamentRead`）。
- [x] `backend/app/modules/registration/service.py`
  - 新增 `withdraw_registration`、`raise_capacity`，以及共用的鎖內遞補函式 `_backfill_released_locked`。
  - `_settle_locked` 記下代表隊。
  - `_first_come_locked` 先做同校遞補。
- [x] `backend/app/modules/registration/router.py`：新增兩個端點。
- [x] `backend/app/modules/notifications/rules.py`、`backend/tests/notifications/`：登錄 `RegistrationBackfilled` 規則並加測試。
- [x] `backend/tests/registration/test_withdraw_registration.py`、`test_raise_capacity.py`
  - I/O 矩陣每一列都要有測試，「撤回與送出同時」兩種順序各一個。
  - 撤回後其他候補的順位更新。
  - 先搶期與截止後各一列要用 `_current_phase` 判斷，含「worker 還沒把賽事轉為 `closed`、但已過截止時間」的情境。
- [x] `backend/tests/registration/test_settlement_concurrency.py`：新增撤回對送出的併發參數組。
- [x] `scripts/generate-client.sh`：重新產生 `frontend/src/client`。
- [x] 前端 `frontend/src/features/registration/`
  - 新增 `useWithdrawRegistration.ts`，成功後更新該隊查詢、讓 `myTeamsQueryOptions` 失效、`notifySuccess`。
  - `SubmitRegistrationSection.tsx`：`withdrawable` 時顯示「退賽」按鈕與 `ConfirmDialog`。
  - `registration-status.tsx`、`RegistrationStatusCard.tsx`：`backfilled` 時顯示「已遞補為正取」。
  - `frontend/tests/unit/team-pages.test.tsx` 加單元測試。
- [x] `_bmad-output/implementation-artifacts/contracts/tournaments.md`、`sprint-status.yaml`、`deferred-work.md`
  - `sprint-status.yaml` 的 3-7 改為 `in-progress`。
  - `deferred-work.md` 刪除第 62-63、119-120 行兩項。

**Acceptance Criteria:**
- Given 隊長在 S17，when 按「退賽」並確認，then 報名變「撤回」、按鈕消失，S12 卡片同步更新。
- Given 被遞補的隊伍，when 成員開 S17 或 S12，then 看到「已遞補為正取」並收到通知；抽籤後改顯示「已參賽」相關狀態。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh` 與前端測試，then 全部通過；既有測試只在 `_first_come_locked` 行為改變的地方調整，並在 Implementation Notes 列出。

## Implementation Notes

實作（2026-11-22，子代理，待人確認）：

- 純函式：`allocation.representative_backfill(candidates, *, departed_schools, capacity)`；`departed_schools` 由 service 依 `is_representative` 且狀態為 `withdrawn`／`disqualified` 算出，函式本身只看該校目前有沒有正取、取 `sort_key` 第一名，並以空位數為上限。
- service：`_backfill`（寫 `backfilled_at`、`mark_status(ACCEPTED)`、發 `RegistrationBackfilled`）、`_representative_backfill_locked`、`_backfill_released_locked`、`withdraw_registration`、`raise_capacity`；`_settle_locked` 把結算時正取的隊伍記為代表隊；`_first_come_locked` 每一筆 `pending` 判定前先呼叫 `_representative_backfill_locked`。
- 遞補（撤回、提高名額、同校遞補）的狀態變更操作者一律為系統（`None`），撤回本身的操作者為隊長、名額變更的操作者為主辦方。spec 沒有寫遞補的操作者，這是實作時的選擇。
- tournaments 新增 `raise_tournament_capacity`（含 repository `set_tournament_capacity`），操作紀錄 `tournament.capacity_changed`；錯誤訊息「賽事抽籤後不能修改名額。」「新名額必須大於目前的名額（N 隊）。」為實作時自訂。
- `backfilled`、`withdrawable` 加在 `TeamDetail`、`MyTeamCard`（不放 `WaitlistFields`，因為 `withdrawable` 要看檢視者角色），兩者都有預設值 False：其他模組自行建立 `MyTeamCard` 的測試替身（D 的 `tests/competition/test_registration_port.py`）與其他組員的前端測試 fixture 不必修改。代價是 OpenAPI 與前端型別為選填（`backfilled?: boolean`）。`withdrawable` 已包含「檢視者是隊長」。
- 退賽成功的 Toast 用「已撤回報名」（spec 沒有規定；用「已退賽」會與 `retired` 的狀態名「退賽」混淆）。「退賽」觸發鈕用 outline 樣式，確認鈕 destructive。
- 錯誤碼：撤回的非隊員為 403 `TEAM_MEMBER_REQUIRED`（比照送出報名），非隊長為 403 `TEAM_CAPTAIN_REQUIRED`（訊息「只有隊長可以退賽」）。
- 既有測試的調整（`_first_come_locked` 行為沒有使既有測試失敗）：
  - `tests/registration/test_teams.py` 的 `NO_WAITLIST` 加上 `backfilled`、`withdrawable`（回應多了欄位，以 `==` 比對整個回應）。
  - `frontend/tests/unit/team-pages.test.tsx` 的 fixture 加上兩個欄位（非必要，型別為選填）。
- 併發：`test_settlement_concurrency.py` 新增獨立的測試函式 `test_parallel_withdraw_and_submit_never_exceed_capacity`（既有參數化測試的斷言是結算專用，無法直接加參數組）；兩條連線同時開始，先後順序由鎖決定，兩種順序的確定性測試在 `test_withdraw_registration.py`（`test_withdraw_then_submit`、`test_submit_then_withdraw`）。
- 環境：本機 `docker compose up -d --build` 需加 `BUILDX_BAKE_ENTITLEMENTS_FS=0`（bake 要求 `fs.read` 權限）。
- 驗證（2026-11-22）：`scripts/lint.sh` 通過；`scripts/test.sh` 2576 passed（覆蓋率 97%，`allocation.py` 分支 26/26）；前端 Biome、`tsc --noEmit` 通過，vitest 74 檔 1068 passed。暫時把 `_backfill_released_locked` 的階段寫死為先搶期、拿掉 `_first_come_locked` 的同校遞補後，`test_withdraw_registration.py` 有 4 個測試失敗（同校遞補兩個、截止後兩個參數組）。Playwright e2e（`bun run test`）沒有執行。

收尾確認（2026-11-22，邱芯彤）：

- 上面 5 項實作自行決定的內容（Toast「已撤回報名」、錯誤訊息、遞補操作者為系統、`backfilled`／`withdrawable` 的位置與預設 False）使用者原則上接受。
- 遞補的操作紀錄可追溯：與觸發它的撤回（隊長）或改名額（主辦方）同一交易寫入，依 `at`、`seq` 緊接在後；`test_first_come_withdraw_backfills_earliest_eligible_waitlist`、`test_raise_capacity_in_first_come_backfills_in_order` 補斷言。
- `backfilled`／`withdrawable` 缺省為 False 時只會少顯示（不顯示退賽、徽章顯示「正取」），不會誤顯示可退賽；後端只有 `_build_detail`、`list_my_teams` 建立這兩個模型，都明確給值。
- E2E（新增 `frontend/tests/e2e/registration-withdraw.spec.ts`、`support/withdraw.ts`，`@story-3.7`）抓到 bug：撤回被拒（409）後 `onError` 重新取得隊伍，`withdrawable` 變 false，`SubmitRegistrationSection` 把整個確認框卸載，錯誤訊息只閃一下。修正：退賽確認框改由 `SubmitRegistrationSection` 控制開關，開著時保持掛載，關閉後按鈕才消失。單元測試的拒絕案例改成重新取得時回傳已撤回；拿掉修正時該測試會失敗。E2E desktop、mobile-375 共 6 passed。

## Spec Change Log

## Review Triage Log

spec 審查（2026-11-22，獨立子代理）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| 1 | 矩陣「截止後撤回」的狀態不可能出現，預期結果也算錯 | high | 已修正：撤回前名額已滿 |
| 2 | 用賽事 `open`／`closed` 判斷階段，與 `_current_phase` 不一致 | high | 已修正 |
| 3 | 有同校候補時就不跑一般遞補，可能留下空位 | medium | 已修正 |
| 4 | deferred 第 119-120 行處理不到 | medium | 依使用者決定接到 `_first_come_locked` |
| 5 | 錯誤碼沒定案 | medium | 已定案 |
| 6 | 缺 epics 要求的 `waitlist_order` 兩階段測試 | medium | 已加進 Tasks |
| 7 | 抽籤後退賽按鈕的說明 | low | 寫進 Decisions |
| 8 | `raise_capacity` 要用新名額遞補 | low | 已寫進 Boundaries |
| 9 | 契約路徑、`rules.py` import 的例外 | low | 已修正 Code Map |
| 10 | `backfilled` 的定義、前端檔案 | low | 已修正 |
| 11 | 架構與併發 | 沒有問題 | 矩陣補上兩種執行順序 |

程式審查（2026-11-22，Blind Hunter、Edge Case Hunter、Verification Gap 三層獨立子代理）：

| # | 來源 | 發現 | 判定與依據 | 去向 |
|---|------|------|-----------|------|
| R1 | VG、BH | 名額可在 `upcoming` 時提高，但沒有測試；把 `UPCOMING` 拿掉測試仍全綠 | low（VG 已驗證）：契約寫 `upcoming` 可改，退化不會被抓到 | patch：補測試 |
| R2 | ECH、BH | `useWithdrawRegistration` 被 409 拒絕時只讓該隊查詢失效，S12 卡片仍是舊狀態 | low：真實但少見；修正只是多一行失效 | patch |
| R3 | ECH、BH | 代表隊被取消資格（6.5，不立即遞補）後，同校候補在 S17 仍顯示「目前不在遞補順序中」／`representative_backfill=false`，下一次送出卻會先遞補它；刪掉的 deferred 第 119-120 行 evidence 提過這個顯示問題 | medium：`waitlist_order` 不知道已退出的代表隊；修正要改 `allocation.py` 既有函式語意（Never 禁止） | defer：新增 deferred 項目 |
| R4 | ECH | `_first_come_locked` 的一般遞補仍走 `_allocate`，沒寫 `backfilled_at` | false：Decisions 明定「已遞補為正取」只涵蓋撤回、提高名額與接到 `_first_come_locked` 的同校遞補 | 駁回 |
| R5 | ECH、BH | 「代表隊已退出的學校」不會過期：當下同校沒有候補時，之後才送出的同校隊伍在下次釋出時會優先遞補 | low：與凍結區塊 Boundaries 的條件一致，需要先「代表隊撤回且當下無同校候補、之後同校又送出、再有名額釋出」才會遇到；修正要加條件 | 駁回（結案時告知使用者） |
| R6 | ECH、BH | 遷移沒有替已結算的賽事補 `is_representative` | low：只影響遷移前已結算的本機或示範資料庫（示範前會 `down -v`）；修正要寫資料遷移 | 駁回 |
| R7 | ECH | 先搶期代表隊被取消資格、截止前沒有任何觸發，截止補位改用積分順序 | false：Boundaries 規定截止後只用 `AFTER_DEADLINE` 遞補 | 駁回 |
| R8 | ECH | 併發測試是獨立函式，不是既有參數化測試的參數組 | low：Implementation Notes 已說明原因，兩種順序另有確定性測試 | 駁回 |
| R9 | BH | 取消資格在 `closed` 時永遠不遞補 | false：凍結區塊 Never 明定 `disqualify_registration` 本身不遞補 | 駁回 |
| R10 | BH | 自訂模式撤回、提高名額不遞補 | false：凍結區塊 Boundaries 明定自訂模式不遞補（3.10 處理） | 駁回 |
| R11 | BH | 撤回後隊員仍佔「同賽事只能一隊」，不能加入其他隊伍 | low：epics 3.7 只要求狀態轉撤回；離隊屬 3.11；修正是新功能 | 駁回（結案時告知使用者） |
| R12 | BH | 隊長撤回時不通知其他隊員 | low：epics 3.7 與 Decisions 只要求遞補通知；修正要新增事件與規則 | 駁回（結案時告知使用者） |
| R13 | BH | 提高名額缺同校遞補、自訂模式、tournaments 模組自己的測試 | low：同校遞補走共用的 `_backfill_released_locked`，撤回已測；其餘為重複涵蓋 | 駁回 |
| R14 | BH | 撤回缺 `closed` 時 `withdrawable=true`、截止後代表隊撤回的測試；traceability 的 FR-37 | low：`closed` 撤回已由截止後測試經 API 執行成功；FR-37 是遞補事件 | 駁回 |
| R15 | BH | 併發測試斷言較弱、沒有兩個撤回互搶的測試 | low：最終狀態與正取數兩種順序都斷言；互搶由同一把賽事鎖序列化 | 駁回 |
| R16 | BH | tournaments service 拋 `loc=body.capacity`、重複鎖 | false：Boundaries 指定 `FieldError loc=body.capacity`，沿用 tournaments 既有 `_field_error`；同交易重複鎖不等待 | 駁回 |
| R17 | BH | 確認框文字對候補也寫「若隊伍是正取」 | false：文字是 Decisions 由使用者定案 | 駁回 |
| R18 | BH | sprint-status 仍為 in-progress、差異沒含 spec | false：狀態在流程結束時更新；spec 是刻意不給這層看 | 駁回 |

## Design Notes

- 代表隊的辨認：結算紀錄只存 `priority_school_ids`，無法分辨「代表隊離開的學校」和「代表隊超過名額、整校都是候補的學校」。所以 `_settle_locked` 把當下正取的代表隊記為 `is_representative = True`，同校遞補上來的隊伍也記為 True。同校遞補的條件是：該校有 `is_representative` 且狀態為 `withdrawn`／`disqualified`（3.8 加上 `rejected`）的報名，而且該校目前沒有 `accepted`／`drawn`。遷移檔的預設值是 False。
- 先搶期每校只有一隊有順位，同校遞補放在一般遞補之前，所以名額不會被別校先拿走。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- 前端 `bun run test`、`bun run lint`（在 frontend 容器或本機 Bun）-- 通過
