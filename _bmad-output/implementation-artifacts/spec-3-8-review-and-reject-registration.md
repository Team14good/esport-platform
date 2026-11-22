---
title: 'Story 3.8：主辦方檢視段位截圖與退回報名'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: '6f78368a00a284ca47d41605964142a303911ea9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-7-withdraw-registration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 主辦方看不到報名隊伍與段位截圖，也無法退回段位造假的報名，造假隊伍可能拿到名額（FR-14～FR-16、FR-18、FR-36）。

**Approach:** registration 新增主辦方報名清單 API、段位截圖授權下載 API 與 `reject_registration`。前端新增 S29（側欄「報名清單」）、Rank screenshot viewer 與退回確認對話框；S17、S12 顯示「退回」與原因，名單解鎖後可在報名期間修正重送。被退回的正取依 3.7 的規則遞補。另依 D 的決定修正「代表隊退出後畫面順位與實際遞補不一致」。

## Decisions（2026-11-22，邱芯彤）

- 退回時機：抽籤前都能退回，賽事 `open`、`closed` 皆可（與撤回一致；依期中文件 B「退回、撤回：只在抽籤前」）。截止後被退回的隊伍不能重送；名額依截止後規則遞補。
- 退回確認對話框：標題「退回報名」；原因欄標籤「退回原因」，必填，上限 200 字；確認鈕「退回報名」（destructive）。內文依賽事狀態：
  - `open`：「退回後隊伍名單會解鎖，隊伍可在報名截止前修正後重新送出。若隊伍是正取，名額會由候補遞補。」
  - `closed`：「報名已截止，退回後隊伍無法重新送出。若隊伍是正取，名額會由候補遞補。」
- 退回通知：新增事件 `RegistrationRejected`（`registration_id`、`team_id`、`tournament_id`、`reason`、`can_resubmit`）。notifications 只新增一條規則：標題「報名結果：退回」，連結 `/teams/{id}`，發給全隊。內文依 `can_resubmit`（退回當下賽事為 `open`）：
  - 可重送：「「隊名」在「賽事」的報名被主辦方退回，原因：{原因}。請在報名截止前修正後重新送出。」
  - 不可重送：「「隊名」在「賽事」的報名被主辦方退回，原因：{原因}。報名已截止，無法重新送出。」
  - 退回時只發這個事件，不發 `RegistrationAllocated`。
- S29 清單：列出送出過的報名（`submitted_at` 不為 null），含退回、撤回、取消資格、已參賽、退賽。預設依分配結果分組排序：正取 → 候補（依順位，沒有順位的排最後）→ 已送出・待分配 → 已參賽 → 退賽 → 退回 → 撤回 → 取消資格，組內依送出時間、再依報名 id。可依狀態篩選（全部與各狀態）；每頁 20 筆；篩選後沒有結果時顯示「沒有符合篩選條件的報名。」；手機卡片顯示隊名、狀態徽章、送出時間、平均段位積分與「段位截圖」「退回報名」（不可退回時不顯示「退回報名」）。
- 退回原因：S17 標頭與 S12 卡片（徽章旁，過長截斷）都顯示，全隊隊員看得到；顯示到重新送出為止，重送後不再回傳（仍留在資料庫與操作紀錄）。
- 順位修正（D 在 PR #105 留言決定，2026-11-22 05:45）：讓 `allocation.waitlist_order`（與 `_first_come_order`）接收「代表隊已退出的學校」，該校第一順位的候補排進遞補順序、顯示「候補第 N 位」並帶 `representative_backfill=true`，順位與實際遞補一致；這類候補的說明改為「本校代表隊已退出，由本校遞補」，取代先搶期的規則說明。6.5 取消資格仍不立即遞補。
  - 這與 PRD FR-17「同校專屬的遞補，不計入順位」的文字不同；採 D 的做法（順位與實際遞補一致），PR 說明要寫出這個取捨。
  - 這是 3.7 spec「不改 `allocation.py` 既有函式語意」的例外，由 D 決定；處理完刪除 deferred-work 的對應項目，並在 PR 回覆 D：本份的退回會立即遞補，實際會遇到不一致的是 6.5 取消資格的路徑。
- 被退回的代表隊修正後重送，保留代表隊身分：重送不清 `is_representative`；「代表隊已退出的學校」改為「該校有 `is_representative` 的報名不在 `accepted`／`drawn`，且該校目前沒有 `accepted`／`drawn`」，原隊伍重送後能經同校遞補拿回名額（與該校新隊伍的待遇一致）。
- 退回後停在 `rejected`，重送時才轉 `forming`（期中文件 B 字面為「回到組隊中」；為了讓 S17 顯示「退回」與原因、讓被退回的代表隊觸發同校遞補，2026-11-22 向使用者說明後採用）。
- spec 約 7,000 tokens（以字元數估算，含 Review Triage Log），超過 1,600；保留完整 spec。
- 程式碼審查後（2026-11-22，邱芯彤，見 Review Triage Log R2、R3）：
  - 優先期已過未結算時退回：先結算時，被退回的這隊照常分配狀態但不發 `RegistrationAllocated`，只收到退回通知。
  - 「可重送」改為「退回當下仍在報名期間」（賽事 `open` 且未過 `registration_end`），取代上面「退回當下賽事為 `open`」的寫法；通知的 `can_resubmit` 與確認對話框的內文都依此判斷，截止時間到了、賽事還沒轉 `closed` 時用不可重送的文字。
  - 同意實作時自行決定的三項：截圖版本用鍵值 SHA-256 前 16 碼、非隊員回 404 `TEAM_MEMBER_NOT_FOUND`、成功 Toast「已退回報名」。
- spec 審查後修正（2026-11-22）：跨賽事檢查、退出學校的共用算法、回應模型、S29 退賽分組與 `submitted_at`、優先期已過未結算時先結算、矩陣補列（見 Review Triage Log）。

## Boundaries & Constraints

**Always:**
- 權限與歸屬（三個主辦方 API 都用 `Organizer` 依賴）：賽事不存在 404 → 不是該賽事主辦方 403 `TOURNAMENT_OWNER_REQUIRED` → 報名不屬於路徑上的賽事 404 `REGISTRATION_NOT_FOUND` → 帳號不是該報名隊伍的隊員 404。截圖下載對隊長、隊員、上傳者本人一律 403。
- 截圖下載比照 `disputes.service.open_report_attachment` 與其路由：`StreamingResponse`、依副檔名對照 jpg／png 的 media type、`Content-Disposition`、`nosniff`、`Cache-Control: private, no-store`；沒有截圖 404 `FILE_NOT_FOUND`。
- 退回：先不鎖讀賽事檢查主辦方與報名歸屬，再以 `registration.tournament_id` `_lock_tournament`、鎖內 `session.refresh` 報名並再檢查；若 `now > priority_end` 且還沒有結算紀錄，先結算（比照 `submit_registration`）；`mark_status(to=REJECTED, actor_id=主辦方)`，寫入原因與時間，寫操作紀錄 `registration.rejected`（after 帶原因），發 `RegistrationRejected`，再呼叫 3.7 的 `_backfill_released_locked`（同一個鎖與交易）。
- 可退回：報名狀態為 `pending`、`accepted`、`waitlisted`，且賽事為 `open` 或 `closed`；否則 409 `REGISTRATION_NOT_REJECTABLE`，不改任何資料。原因去除前後空白後必填、最多 200 字，違反時 422 欄位錯誤。
- 退回後報名停在 `rejected`，名單解鎖：集中一個「名單未鎖定」判斷（`forming` 或 `rejected`），套用到邀請狀態、參賽資料可編輯、送出缺漏、建隊／加入／填資料的檢查。重送時在同一交易內 `rejected → forming → pending`（沿用 `_TRANSITIONS`），重寫三個快照、清 `backfilled_at`、保留 `is_representative`；優先期結束後重送依先搶期當下判定（沿用 `submit_registration`）。
- 已退出代表隊的學校只用一個共用函式計算（Decisions 的定義），遞補（`_representative_backfill_locked`）、`_waitlist_fields`、S29 三處共用；只在 `_current_phase` 為先搶期時使用。`_DEPARTED_STATUSES` 加 `rejected`。
- 順位修正：`waitlist_order` 新增選填參數（預設為空，既有呼叫端結果不變）；先搶期時，已退出代表隊的學校其 `sort_key` 第一名候補排在一般先搶期順位之前（多校依 `sort_key`），與 `representative_backfill` 的實際遞補順序相同。`backfill_vacancies`、`fill_from_waitlist` 語意不變；`WaitlistEntry` 的 docstring 同步。
- S29 的分配結果與候補順位和 S17 一致（同一套計算），不另寫排序；平均段位積分用 `Registration.avg_rank_score` 快照。
- 跨模組只新增：notifications 新規則、2.8 的 `AUDIT_ACTION_LABELS`、B 的 `organizer-nav.ts` 側欄項目（放在「總覽」之後），PR 說明列出。

**Never:**
- 不改 `_TRANSITIONS`、3.7 的遞補規則；`allocation.py` 只做上面的順位修正（D 決定的例外）。6.5 取消資格仍不遞補。
- 不放寬 `rank_screenshot_name` 只回給本人的規則；截圖不給公開或隊員端網址。
- 不做抽籤後退回、自訂模式的遞補（3.10）、隊員異動（3.11）、S27 的入口。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 優先期內退回 | `pending`，沒有結算紀錄、未過優先期 | 轉 `rejected`、記原因；不遞補；之後結算不算這隊 | N/A |
| 優先期已過、尚未結算時退回 | 賽事 `open`、`now > priority_end`、沒有結算紀錄；`pending` 被退回 | 先結算（這隊算在內），再退回並依先搶期遞補 | N/A |
| 先搶期退回正取 | 名額已滿；非代表隊的正取 A 被退回；有符合規則的候補 B | A `rejected`；B 遞補（`RegistrationBackfilled`、`backfilled_at`） | N/A |
| 先搶期退回代表隊 | P 校代表隊被退回；同校候補 P2（80）、P3（90） | P3 遞補（`is_representative`） | N/A |
| 被退回的代表隊重送 | 先搶期；P 校代表隊被退回、當時沒有同校候補，空位已由他校遞補；P 修正後重送 | P 候補，順位為「已退出代表隊」的第 1 群；下一次名額釋出時同校遞補 | N/A |
| 退回候補 | `waitlisted` 被退回，名額已滿 | 不遞補；其餘候補順位下次載入時更新 | N/A |
| 截止後退回正取 | `closed`、名額已滿；正取被退回 | `rejected`；依截止後規則（積分、每校 2 隊）遞補；對話框與通知用不可重送的文字 | 重送 409 `REGISTRATION_CLOSED` |
| 自訂模式退回 | 自訂賽事的正取被退回 | `rejected`；不遞補（3.10） | N/A |
| 6.5 取消代表隊後的順位 | 先搶期；P 校代表隊被取消資格（不遞補）；P 校候補 P2（80）、P3（90）；X 校符合先搶期的候補 | P3 候補第 1 位（`representative_backfill=true`、說明「本校代表隊已退出，由本校遞補」），X 第 2 位，P2 沒有順位；下一次送出時 P3 先遞補 | N/A |
| 退回後重送（優先期內） | `rejected`，修正後隊長送出 | `pending`，快照重寫 | N/A |
| 退回後重送（先搶期） | `rejected`，優先期已結束 | 依先搶期當下判定正取或候補 | N/A |
| 退回後的名單 | `rejected` | S17、S12 顯示「退回」與原因；可改參賽資料、可邀請（未滿時）、隊長可送出 | N/A |
| 不可退回 | `forming`／`rejected`／`withdrawn`／`drawn`，或賽事 `published` 以後 | 拒絕，不改資料 | 409 `REGISTRATION_NOT_REJECTABLE` |
| 沒有原因 | 原因為空白或超過 200 字 | 拒絕 | 422 |
| 非主辦方 | 隊長、隊員、上傳者、其他帳號呼叫清單／截圖／退回 | 拒絕 | 403 |
| 別賽事的報名 | 主辦方以自己的賽事路徑帶他賽事的報名 id 或隊員 | 拒絕，不改資料 | 404 |
| 截圖未上傳 | 隊員沒有截圖 | API 404；檢視器顯示「未上傳」 | 404 `FILE_NOT_FOUND` |
| 退回與送出同時 | 先搶期名額已滿；正取 A 被退回、B 送出並行 | 依鎖序處理，兩種順序都不超收（同 3.7） | N/A |
| 退回與抽籤同時 | 賽事 `closed`；退回正取與抽籤並行 | 先退回：遞補後抽籤；先抽籤：退回得 409；對戰表上沒有 `rejected`、沒有遺留 `accepted` | 409 |

</frozen-after-approval>

## Code Map

- 開工前先 `git fetch origin && git merge origin/main`：A 的 PR #106（3.9）也改 registration 的 service／models／router，行號可能位移。
- 後端 `backend/app/modules/registration/`
  - `allocation.py`：`WaitlistEntry`(:94-103，docstring 要改)、`waitlist_order`(:194)、`_first_come_order`(:219，旗標 :236)、3.7 的 `representative_backfill`(:308，實際遞補順序以此為準)；單元測試 `tests/registration/test_allocation.py`（分支覆蓋率 90%）。
  - `service.py`：`_TRANSITIONS`(:195-237)、`mark_status`(:244)；以 `forming` 判斷名單的 6 處（:291 邀請、:344 可編輯、:517 blockers、:641、:725、:809 送出）改用「名單未鎖定」；`submit_registration`(:779，:826-829 快照，:851-855 先結算再先搶期)；`_waitlist_fields`(:421)、`_ORDER_STATUSES`(:412)、`_current_phase`(:397)；`_DEPARTED_STATUSES`(:1075)、`_representative_backfill_locked`(:1100，departed 計算改用共用函式)、`_backfill_released_locked`(:1126)；範本 `withdraw_registration`(:1222)、`raise_capacity`(:1260)、`disqualify_registration`(:1408，從報名反查賽事)。
  - `models.py`：`Registration`(:120) 加 `reject_reason`（Text，與期中文件 B 的 ER 圖、identity 一致）、`rejected_at`，docstring「送出後不再變動」(:121-125) 更新；`TeamDetail`(:281)、`MyTeamCard` 加 `reject_reason`（只在 `rejected` 時回傳，否則 null）；`submit_blockers` 註解(:306) 更新；新增 `RegistrationRejected`（`RegistrationBackfilled`:178 旁）；原因驗證比照 `identity/models.py` 的 `REJECT_REASON_MAX_LENGTH`(:39)、`_validate_reject_reason`(:226)。
  - 新回應模型：清單列 `OrganizerRegistration`（`registration_id`、`team_id`、`team_name`、`status`、`submitted_at`、`avg_rank_score`、`WaitlistFields` 各欄、`backfilled`、`rejectable`、`reject_reason`、`members`）；`members` 每位含 `account_id`、`display_name`、`role`、`game_id`、申報段位名稱、`has_rank_screenshot`、`rank_screenshot_version`（鍵值，供前端快取鍵）。分頁回應比照 `tournaments/router.py:169` 的 audit log。
  - `router.py`（都用 `Organizer`，router commit，不加 `PUBLIC_WRITE_ROUTES`）：
    - `GET /organizer/tournaments/{tournament_id}/registrations?page=&status=`（分頁比照 `tournaments/router.py:169`，篩選比照 `identity/router.py:205`）。
    - `GET /organizer/tournaments/{tournament_id}/registrations/{registration_id}/members/{account_id}/rank-screenshot`（比照 `disputes/router.py:114-145`）。
    - `POST /organizer/tournaments/{tournament_id}/registrations/{registration_id}/rejection`（body `{reason}`，回傳更新後的 `OrganizerRegistration`）。
  - `repository.py`：視需要新增清單查詢。`TeamMember.rank_screenshot_key`(models.py:112-117)；`core/storage.py` 的 `open_file`。
  - Alembic 遷移一支。
- `backend/app/modules/notifications/rules.py`：import 加 `RegistrationRejected`，規則加在檔尾，沿用 `_member_ids`。
- 操作紀錄：`registration.rejected` 同步 `tests/tournaments/test_audit_action_labels.py` 的 `LABELED_ACTIONS` 與 `frontend/src/features/tournaments/audit-log.ts` 的 `AUDIT_ACTION_LABELS`（「退回報名」）。
- 前端
  - `features/tournaments/organizer-nav.ts`(:27-66，B 的檔案)：「總覽」之後加「報名清單」。
  - 新頁 `routes/organizer/tournaments/$tournamentId/registrations.tsx`（範本 `audit-log.tsx:9-37`，`page`、`status` 在網址 search）；元件放 `features/registration/`；重新產生 `routeTree.gen.ts`（掛整個 `frontend/` 跑 `bunx vite build`）。
  - `components/common/DataTable.tsx`(:22-46)；篩選範本 `features/identity/AdminApplicationsPage.tsx:172-198`、`routes/admin/applications.tsx:13-33`；分頁範本 `features/disputes/ReportsPage.tsx:188-197`。
  - 狀態徽章沿用 `registration-status.tsx` 的 `RegistrationStatusBadge`；`WaitlistDetails`(:105-118) 加「本校代表隊已退出，由本校遞補」（有順位且 `representative_backfill` 時取代先搶期規則說明）。
  - 檢視器：桌機 Dialog 最大寬 960px、手機用 `ResponsiveDialog` 的 Sheet；授權 blob 載入範本 `features/competition/result-screenshot-queries.ts:33-63`，queryKey 帶 `rank_screenshot_version`；版面 `ResultScreenshotCard.tsx:56-92`；上一位／下一位與「n／N」要新做，預設第一位、隊員依隊長在前、再依加入順序。
  - 退回：`ConfirmDialog` 的 `reason`（範本 `AdminApplicationsPage.tsx:68-80`），內文依賽事狀態；檢視器與確認框用兩個受控 open state 切換。成功後讓清單查詢失效並 `notifySuccess`。
  - 空狀態：`EmptyState` 的 `action`「複製賽事頁連結」，複製寫法比照 `InviteLinkField.tsx:47-54`，連結為 `window.location.origin` ＋ `/tournaments/{id}`。
  - S17：`TeamPage.tsx`（標頭顯示原因）、`SubmitRegistrationSection.tsx`(:310-325，`rejected` 時走 `FormingSubmit`)；S12：`RegistrationStatusCard.tsx`（只能放 span）。
- 測試
  - 後端 helper：`tests/registration/test_first_come_submission.py`（`_preset`、`_settled`、`_first_come`、`_events`、`_logs`），範本 `test_withdraw_registration.py`；併發範本 `test_settlement_concurrency.py`（撤回對送出、撤回對抽籤 :611）。
  - 前端：`tests/unit/organizer-reports.test.tsx`（`renderApp`、`signInAs`、`httpError`）、`team-pages.test.tsx`；E2E `support/withdraw.ts` 的 `createOpenTournamentByApi`（回傳 `Promise<string>`；新增一個也回傳主辦方帳號的函式，不改既有函式）、`bulk.ts`、`drawn.ts`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/allocation.py`、`backend/tests/registration/test_allocation.py` -- 順位修正與 `WaitlistEntry` docstring；單元測試；既有測試不改。
- [x] `backend/app/modules/registration/models.py`、`backend/app/alembic/versions/<新檔>.py` -- `reject_reason`、`rejected_at`、`RegistrationRejected`、清單回應模型、`TeamDetail`／`MyTeamCard.reject_reason`、docstring。
- [x] `backend/app/modules/registration/service.py`、`repository.py` -- `reject_registration`、清單（一次算整個賽事的順位）、截圖開檔；名單未鎖定判斷；重送；退出學校共用函式；`_DEPARTED_STATUSES` 加 `rejected`。
- [x] `backend/app/modules/registration/router.py` -- 三個主辦方端點。
- [x] `backend/app/modules/notifications/rules.py`、`backend/tests/notifications/test_rules.py` -- 退回通知（兩種內文）。
- [x] `backend/tests/tournaments/test_audit_action_labels.py`、`frontend/src/features/tournaments/audit-log.ts` -- `registration.rejected`。
- [x] `backend/tests/registration/test_reject_registration.py`、`test_organizer_registrations.py` -- I/O 矩陣每一列；清單的篩選、分頁、分組排序與順位；截圖權限、歸屬與 header。
- [x] `backend/tests/registration/test_settlement_concurrency.py` -- 退回對送出、退回對抽籤的真實併發測試。
- [x] `backend/tests/traceability.yaml` -- 新測試檔。
- [x] `scripts/generate-client.sh`、`frontend/src/routeTree.gen.ts` -- 重新產生。
- [x] 前端 S29：路由、`features/registration/` 下的清單、檢視器、退回 hook 與元件；`organizer-nav.ts`；`registration-status.tsx` 的代表隊說明。
- [x] 前端 S17／S12：`TeamPage.tsx`、`SubmitRegistrationSection.tsx`、`RegistrationStatusCard.tsx`。
- [x] `frontend/tests/unit/` -- S29 清單、篩選、兩種空狀態、檢視器翻頁／「未上傳」／換圖後不顯示舊圖、退回對話框（兩種內文、必填、成功、409）、S17／S12 退回原因、重送、代表隊說明。
- [x] `frontend/tests/e2e/registration-reject.spec.ts`、`support/` 新增函式 -- 主辦方在 S29 看截圖、退回正取、候補遞補；隊長看到原因、修正後重送。
- [x] `sprint-status.yaml` 3-8 改 `in-progress`；`deferred-work.md` 刪除「Deferred from: spec-3-7-withdraw-registration.md」那一項，新增：3.7 撤回在優先期已過未結算時沒有先結算；先搶期新隊送出時同校遞補只在判定前執行。

**Acceptance Criteria:**
- Given 主辦方在 S29，when 點某隊「段位截圖」，then 檢視器依序顯示每位隊員的截圖（或「未上傳」），首末按鈕停用；按「退回報名」先關檢視器再開確認對話框。
- Given 隊長在 S17，when 報名被退回，then 看到「退回」與原因、收到通知，修正後可重新送出。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh`、前端測試與 `@story-3.8` E2E，then 全部通過；既有測試只在名單解鎖判斷改變的地方調整，並在 Implementation Notes 列出。

## Implementation Notes

實作（2026-11-22，子代理，待人確認）：

- 順位修正：`allocation.waitlist_order(..., departed_schools=())` 新增選填參數，`_first_come_order` 先把「代表隊已退出、本校目前沒有正取」學校的 `sort_key` 第一名排在最前（多校依 `sort_key`，`representative_backfill=True`），這些學校的其他候補沒有順位（`SCHOOL_NOT_ELIGIBLE`）。`backfill_vacancies`、`fill_from_waitlist` 不傳，結果不變；既有 `test_allocation.py` 沒有改。新測試含「順位前 N 名＝`representative_backfill` 再 `backfill_vacancies` 的實際遞補順序」。
- 退出學校的共用函式 `service._departed_schools`；`_DEPARTED_STATUSES` 改為「所有狀態減去 `accepted`／`drawn`」（含 `rejected`，以及被退回後重送、目前候補的代表隊），與 Decisions 的定義一致。`_waitlist_order` 是 S17、S12、S29 共用的整場順位計算，只在先搶期傳入退出學校。
- 名單未鎖定：`_roster_unlocked`（`forming`／`rejected`）套用到邀請狀態、`profile_editable`、`submit_blockers`、加入、填資料、送出六處。重送時 `rejected → forming`（操作者隊長）、清 `backfilled_at`、保留 `is_representative`，再走原本的送出流程（快照重寫、先搶期當下判定）。`reject_reason`／`rejected_at` 重送後保留在資料庫。
- 實作時自行決定（spec 沒寫）：
  - 截圖版本 `rank_screenshot_version` 用鍵值 SHA-256 的前 16 碼，不直接回傳鍵值（`TeamMember` docstring 規定鍵值不出現在任何 API 回應）。
  - 帳號不是該隊隊員的錯誤碼 404 `TEAM_MEMBER_NOT_FOUND`（「找不到這支隊伍的這位隊員。」）；不可退回 409 訊息「這支隊伍的報名目前不能退回。」。
  - `can_resubmit` 原本照 Decisions 字面用「退回當下賽事為 `open`」；審查後使用者決定改為 `_in_registration_period`（見 Decisions「程式碼審查後」），對話框同步。
  - 下載檔名 `rank-{registration_id}-{account_id}.{jpg|png}`；成功 Toast「已退回報名」；S29 篩選選項為「全部」加上組隊中以外的 8 種狀態，順序同預設分組。
  - S29 狀態欄在徽章下顯示候補說明（`WaitlistDetails`）與「退回原因：…」（兩行截斷）；S12 卡片的原因用 `truncate` 一行，S17 標頭完整顯示。
  - 檢視器每次開啟都重新掛載（回到第一位）；`useRankScreenshotImage` 只回傳屬於目前 blob 的 object URL，換隊員或換圖的那一次 render 不會閃出舊圖。
- 跨模組只新增（PR 說明要列）：notifications `rules.py` 的 import 與檔尾 `_registration_rejected` 規則；2.8 的 `AUDIT_ACTION_LABELS`、`test_audit_action_labels.py` 加 `registration.rejected`；B 的 `organizer-nav.ts` 在「總覽」後加「報名清單」（`ListChecksIcon`）。
- 既有測試的調整：
  - `backend/tests/registration/test_teams.py` 的 `NO_WAITLIST` 加 `reject_reason`（回應多了欄位，以 `==` 比對整個回應）。
  - `frontend/tests/unit/organizer-tournaments.test.tsx`（B）側欄順序加「報名清單」、後面的索引往後一位（側欄多一項）。
  - 名單解鎖判斷與順位修正沒有使其他既有測試失敗。
- 遷移 `b8d4f2a6c9e1`（`down_revision = "a7c3e9f1b5d8"`）；A 的 PR #106 若也加遷移，後合併的一方改 `down_revision`。
- 驗證（2026-11-22）：
  - 後端 `scripts/lint.sh` 通過；`scripts/test.sh` 2642 passed（覆蓋率 97%，`allocation.py` 分支 34/34）；之後補的 `test_reject_then_submit`、`test_submit_then_reject` 單獨執行通過（`test_reject_registration.py` 共 31 passed，含 `test_traceability.py`）。
  - 前端 Biome、`tsc --noEmit` 通過；vitest 78 檔 1138 passed。
  - E2E `--grep @story-3.8` desktop、mobile-375 共 2 passed；`@story-3.7|@story-2.8` 8 passed。
  - 併發：把 `reject_registration` 改成不加鎖、不 refresh 時，`test_parallel_reject_and_draw` 3 次都失敗；`test_parallel_reject_and_submit_never_exceed_capacity` 抓不到這個錯誤實作（與 3.7 撤回對送出的情況相同，兩種順序的確定性測試在 `test_reject_registration.py`）。

- 審查修正後重新驗證（2026-11-22，主流程）：後端 `lint.sh` 通過、`test.sh` 2645 passed（覆蓋率 97%）；前端 Biome、`tsc --noEmit` 通過，vitest 78 檔 1140 passed；E2E `@story-3.8` desktop、mobile-375 共 2 passed。
- 使用者決定修正 R2、R3 後重新驗證（2026-11-22，主流程）：後端 `lint.sh` 通過、`test.sh` 2646 passed（覆蓋率 97%）；前端 Biome、`tsc --noEmit` 通過，vitest 78 檔 1141 passed；E2E `@story-3.8` 2 passed。新增測試：`test_reject_after_registration_end_before_close_cannot_resubmit`、前端「截止時間已過、賽事仍為開放報名：不可重送的內文」；`test_reject_after_priority_end_settles_first` 補「被退回的隊伍沒有分配事件」的斷言。

## Spec Change Log

## Review Triage Log

spec 審查（2026-11-22，獨立子代理）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| 1 | 沒檢查報名屬於路徑上的賽事，主辦方可跨賽事退回或下載 | high | 已修正：歸屬檢查順序、以報名所屬賽事加鎖、矩陣補列 |
| 2 | 截止後退回，對話框與通知仍寫「可重送」 | medium | 使用者決定：依賽事狀態兩套文字 |
| 3 | 順位修正與 PRD「不計入順位」牴觸，畫面說明矛盾 | medium | 使用者決定：採 D 的做法、改說明文字、PR 寫取捨 |
| 4 | 退出學校只看狀態，未要求 `is_representative`、未限先搶期 | medium | 已修正：共用函式、限先搶期 |
| 5 | 被退回的代表隊重送後失去同校遞補 | medium | 使用者決定：保留代表隊身分、改退出學校定義 |
| 6 | 清單、退回、截圖 API 的模型沒定義；缺 `rejectable` | medium | 已修正：Code Map 列欄位 |
| 7 | S29 分組漏 `retired`；「送出過」未定義 | medium | 已修正 |
| 8 | 優先期已過未結算時退回，該校被誤當優先期沒報名 | low | 已修正：先結算；3.7 撤回同樣缺口記 deferred |
| 9 | 原因的回傳條件；S12 是否顯示 | low | 已修正；使用者決定 S12 也顯示 |
| 10 | 矩陣缺階段前提、自訂模式、抽籤後、退回對抽籤 | low | 已補列 |
| 11 | Tasks 漏 routeTree、traceability、E2E support、docstring、repository | low | 已補 |
| 12 | 欄位名與期中文件、identity 不一致 | low | 改為 `reject_reason` |
| 13 | 檢視器寬度與手機呈現 | low | 已寫明 |
| 14 | 換截圖後快取顯示舊圖 | low | queryKey 帶版本 |
| 15 | 沒指定主辦方 API 的依賴 | low | 用 `Organizer` |
| 16 | 截圖 404 錯誤碼與 media type | low | `FILE_NOT_FOUND`、jpg／png 對照 |
| 17 | 3.11 解散要先轉 `forming`；PR #106 會讓行號位移 | low | Design Notes 與 Code Map 註明 |
| 18 | 先搶期新隊送出時同校遞補只在判定前執行 | low | 記 deferred |
| 19 | 空狀態、篩選無結果、S27 入口、側欄位置 | low | 已寫明；S27 入口不做 |

程式碼審查（2026-11-22，三個獨立子代理：blind、edge-case、verification-gap）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| R1 | S29 前端沒有分頁與「頁碼超出以 replace 導回最後一頁」的測試（verification-gap） | medium | patch：新增兩個分頁測試 |
| R2 | 優先期已過未結算時退回，先結算會對被退回的隊伍發 `RegistrationAllocated`，隊伍同時收到「正取」與「退回」通知 | low | 使用者決定修正：`_settle_locked` 的 `silent_ids` 讓被退回的這隊不發分配事件；測試補斷言 |
| R3 | `can_resubmit` 與對話框依賽事狀態，報名截止到 worker 轉 `closed` 之間退回會寫「可重送」但實際 409（blind、edge-case） | low | 使用者決定修正：`can_resubmit=_in_registration_period`；前端 `rejectDescription` 同時看狀態與 `registration_end`；新增後端、前端測試 |
| R4 | 前端 `tournament.data?.status` 為 undefined 時顯示可重送文字 | low | 隨 R3 修正：賽事資料未載入時改顯示不可重送的文字 |
| R5 | `test_allocation.py` 既有測試被改格式，違反「既有測試不改」 | low | patch：還原成 baseline |
| R6 | `reject_registration` 呼叫兩次 `clock.now()` | low | reject：相差微秒，不影響結算判斷或顯示 |
| R7 | 清單 API 接受 `status=forming`（回空頁而非 422） | low | reject：無害，前端不提供此選項 |
| R8 | `rejected_at` 沒有回傳；操作紀錄 payload 不完整 | low | reject：spec 只要求 after 帶原因，狀態變更另有 `registration.status_changed` |
| R9 | `_DEPARTED_STATUSES` 比「加 `rejected`」寬，重送中的代表隊會讓同校候補先遞補（blind、edge-case） | low | reject：符合 Decisions 的退出學校定義與「與該校新隊伍待遇一致」；判定前遞補已記 deferred |
| R10 | E2E 沒檢查退回通知 | low | reject：`test_reject_registration.py` 檢查事件，`test_rules.py` 檢查內文；通知由 worker 非同步送出 |
| R11 | `createOpenTournamentWithOrganizerByApi` 與既有函式重複 | low | reject：spec 規定新增函式、不改既有函式 |
| R12 | media type 對照分在 service 與 router 兩處 | low | reject：目前只存 jpg／png，沒有會分歧的呼叫端 |
| R13 | 可退回條件重用 `_can_withdraw` | maybe-false | reject：spec 規定兩者條件相同，沒有已知會分歧的變更 |
| R14 | S29 只處理 403，404 沒有 ErrorPage | false | 上層 layout 處理賽事 404，與 audit-log、reports 頁相同模式 |
| R15 | 檢視器「n／N」沒有 `aria-live` | low | patch：加 `aria-live="polite"`；方向鍵翻頁不做 |
| R16 | 原因以「。」結尾時通知出現「。。」 | low | patch：串接前去掉句末標點，加測試 |
| R17 | 主辦方可下載未送出（組隊中）隊伍的截圖 | low | reject：須手動組網址，且仍限該賽事主辦方；修正要加檢查分支 |

## Design Notes

- 退回後停在 `rejected`：epics 要求 S17 顯示「退回」與原因；被退回的代表隊要能觸發同校遞補；優先期結算只算 `pending`，退回且未重送的學校自然視為優先期沒有報名（FR-15）。重送時才走狀態圖的 `rejected → forming`。
- 「名單未鎖定」集中成一個判斷函式，3.11 的移除隊員、退出、解散也會用到；3.11 讓被退回的隊伍解散時要先轉 `forming` 再轉 `withdrawn`（`_TRANSITIONS[REJECTED]` 只有 `FORMING`）。
- S29 一次算整個賽事的 `waitlist_order`，避免每列重查。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- frontend 容器內 `bunx vitest run`、`bunx biome check`、`bunx tsc --noEmit -p tsconfig.json` -- 通過
- `docker compose --profile e2e run --rm e2e bunx playwright test --grep @story-3.8` -- 通過
