---
title: 'Story 1.8：平台管理員審核主辦方申請'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '2cf395a9db194fd0b66e45af40240ed066253d66'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 1.7 之後申請只會停在「待審核」：平台管理員沒有後台可以審核，申請人也看不到結果，被退回時無法修改重送。

**Approach:** 建立平台管理後台（側欄版面）與 S35：以 Data table 列出申請，核准或退回（必填原因）都經確認對話框，並寫操作紀錄、發出事件；核准時申請人的 `is_organizer` 立即變成 true。S15 依最新一筆申請顯示核准或退回原因，退回時可以修改後重送。後台版面、Data table、AlertDialog 包裝是之後全站共用的元件（B 的 2.1、2.2 畫面在 11/1 後會用到）。

## Boundaries & Constraints

**Always:**
- 審核 API 一律 `PlatformAdmin`（非管理員 403 `PLATFORM_ADMIN_REQUIRED`）；前端 S35 對非管理員顯示 S38 的 403。
- 狀態只能經一個轉換函式從 `pending` 改成 `approved` 或 `rejected`（AD-11）；其他狀態回 409 `APPLICATION_NOT_PENDING`「這筆申請已經審核過了。」；不存在回 404 `APPLICATION_NOT_FOUND`。先鎖申請再鎖帳號，同時審核同一筆只有一個成功。
- 核准：申請 `approved`、帳號 `is_organizer = true`、操作紀錄 `organizer_application.approved`、事件 `OrganizerApplicationApproved(application_id)` 在同一個交易。退回：`reject_reason` 必填，去除前後空白後 1～200 字；`organizer_application.rejected`、`OrganizerApplicationRejected(application_id)`。
- 重送一律建立新的一筆申請（沿用 1.7 的送出 API），舊的退回紀錄保留。
- 確認對話框：標題寫動作、內文寫後果、確認鈕重複動作名（「核准」「退回申請」）；理由欄沒填時確認鈕停用；送出失敗時對話框不關、顯示 `detail.message`。
- 375 px 寬沒有橫向捲軸；介面全部繁體中文。

**Never:**
- 不在 notifications 登錄收件規則、不建站內通知或 Email（期中規則 2）；不做通知輪詢，申請人重新整理頁面才看到新身分。
- 不做 S36（遊戲設定、學校清單）的畫面與側欄項目（Story 2.1）；不修改 tournaments 模組。
- 不新增 `backend/tests/helpers.py`（B 的 2.1 PR 會新增同名檔案）；測試工具照 1.7 寫在測試檔內。
- 不修改 `docs/`（`docs/ai-usage/` 除外）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 列出待審核 | 管理員開啟 S35 | 預設篩選「待審核」，依送出時間由舊到新，每頁 20 筆 | N/A |
| 沒有資料 | 篩選結果為空 | Empty state「目前沒有待審核的主辦方申請。」（其他篩選：「沒有符合條件的主辦方申請。」） | N/A |
| 核准 | 待審核申請，按「核准」並確認 | 200；列表重新整理；Toast「已核准主辦方申請。」；申請人重新整理後 S15 顯示「核准」 | N/A |
| 退回 | 待審核申請，填原因後確認 | 200；Toast「已退回主辦方申請。」；申請人 S15 顯示原因＋預填原資料的表單 | 原因空白：確認鈕停用；API 422 |
| 重複審核 | 申請已不是 `pending` | 不改任何資料 | 409 `APPLICATION_NOT_PENDING`，顯示在對話框 |
| 重送 | 最新一筆為 `rejected`，修改後按「重新送出申請」 | 新增一筆 `pending`；S15 換成待審核摘要 | 同 1.7 |
| 非管理員 | 一般帳號開啟 S35 或呼叫審核 API | S38 403 | API 403 `PLATFORM_ADMIN_REQUIRED` |
| 頁碼超出 | `page` 大於總頁數 | 回傳空的 `items`，`total` 照實 | `page < 1` 回 422 |

## Decisions（2026-10-29 定案）

- **主辦方身分與 S25 佔位頁**（使用者選 A）：1.8 新增 `organizer` 身分「主辦方後台」→ `/organizer`，身分清單順序為瀏覽賽事、主辦方後台、平台管理；建立最小的 S25 佔位頁：側欄版面（第一層只有「我的賽事」）＋Empty state「你還沒有建立賽事。」，不放「建立賽事」按鈕。B 的 Story 2.2 直接接手 `frontend/src/routes/organizer/index.tsx`，PR 說明要寫出來並通知 B。S15 核准時顯示主要按鈕「前往主辦方後台」。
- **保留完整 spec**（使用者決定）：粗估約 4,300 tokens，不拆分；後台版面、Data table、AlertDialog 是本 Story 的驗收條件，也是 11/1 要交給 B 的元件。
- **S35 內容**（依 UX 推導，可在 checkpoint 調整）：篩選預設「待審核」，可選核准、退回、全部；欄位為社團名稱、學校、申請人（顯示名稱＋Email）、送出時間、狀態、操作；依送出時間由舊到新。
- **退回原因**：去除前後空白後 1～200 字。
- **分頁 API 格式**：`{items, total, page, page_size}`、`page_size` 固定 20，為全專案第一個分頁 API，之後的列表沿用。
- **`< lg` 開啟側欄的按鈕放在後台內容區頂端**（使用者決定，2026-10-29 實作後確認）：不放進全站頂欄，因為頂欄在 `< sm` 已有自己的選單鈕，兩個漢堡鈕會分不清；按鈕寫出後台名稱（例如「平台管理」）。驗收條件「從頂欄按鈕開啟 `Sheet`」以此為準。
- **不做 code review**（沿用 1.7 的使用者決定）：本 Story 驗證通過即收尾，sprint-status 停在 `review` 等最後統一審查。

</frozen-after-approval>

## Code Map

- `backend/app/modules/identity/models.py` -- `ApplicationStatus`(:26)、`OrganizerApplication`(:103，`reject_reason` 已存在，不需要遷移)、`OrganizerApplicationSubmitted`(:149) 比照新增兩個事件；`OrganizerApplicationRead`(:371)；`IdentityKey`(:336) 只有 browse、platform_admin；欄位驗證比照 1.7 的 `ClubNameField`。
- `backend/app/modules/identity/service.py` -- `submit_organizer_application`(:519) 的鎖定、audit、publish 寫法；`_application_read`(:503)；`list_identities`(:427) 依帳號組身分清單（在 platform_admin 之前加 organizer，順序依 UX-DR8：瀏覽賽事、主辦方後台、平台管理）。
- `backend/app/modules/identity/repository.py` -- `get_latest_application`(:119)、`add_organizer_application`(:134)；新增列表（count＋offset/limit、join account 與 school）與 `get_application(..., for_update=True)`。
- `backend/app/modules/identity/deps.py:49-60` -- `PlatformAdmin`；router 目前沒 import。
- `backend/app/modules/identity/router.py` -- B 的 2.1 用 `/admin/schools` 命名管理 API，1.8 照這個前綴；`tests/test_auth_required.py` 自動檢查新的寫入端點未登入回 401，不要加進 `PUBLIC_WRITE_ROUTES`。
- `backend/tests/identity/test_organizer_application.py:40,55` -- `_make_account`、`_headers`、`_school`、`_audit_rows` 的寫法；管理員帳號參考 `test_login.py:40`（`admin=True`）。
- `frontend/src/components/ui/` -- 已有 sidebar、sheet、table、pagination、select、dialog、card；**沒有** alert-dialog（要 `bun add @radix-ui/react-alert-dialog` 並照 shadcn new-york 寫元件）與 textarea（照 shadcn 寫，不需套件）。
- `frontend/src/components/layout/AppShell.tsx`、`__root.tsx` -- 全站是 TopBar＋main，目前沒有側欄版面；`ErrorPage.tsx:23,49` 的 `ErrorPage({status:403})`、`RouteErrorPage`。
- `frontend/src/features/identity/auth.ts` -- `requireSignedIn`(:225)、`useIdentities`(:123)、`useSwitchIdentity`(:179，平台管理已導向 `/admin/applications`)。
- `frontend/src/routes/login.tsx:10` -- `validateSearch` 寫法（不用 zod）。
- `frontend/src/features/identity/OrganizerApplyPage.tsx` -- `ApplicationForm`(:76) 要接受 `defaultValues`；`ApplicationSummary`(:170)；主分支(:207-236)；`organizer-application.ts` 的 `APPLICATION_STATUS_BADGES` 與「`null` 變成 `{}`」的處理。
- `frontend/src/lib/feedback.ts` -- `notifySuccess`、`notifyError`。
- UX：S35 `EXPERIENCE.md:95-99,351`；S15 各狀態 `:305-312`；Data table `:242`、`DESIGN.md:456`；AlertDialog `EXPERIENCE.md:111,246`；Sidebar `DESIGN.md:364,392,446`、UX-DR7；Empty state `DESIGN.md:457`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/identity/models.py` -- 事件 `OrganizerApplicationApproved`、`OrganizerApplicationRejected`；`OrganizerApplicationRejection{reason}`；`AdminOrganizerApplication`（`OrganizerApplicationRead` 加 `applicant_display_name`、`applicant_email`）；`OrganizerApplicationPage{items,total,page,page_size}`；`IdentityKey.ORGANIZER`。
- [x] `backend/app/modules/identity/repository.py`、`service.py` -- 轉換函式、`list_organizer_applications(status, page)`、`approve_organizer_application`、`reject_organizer_application`；`list_identities` 加主辦方。
- [x] `backend/app/modules/identity/router.py` -- 三支端點（見 Design Notes）。
- [x] `backend/tests/identity/test_organizer_application_review.py` -- I/O 矩陣後端各列、操作紀錄與事件內容、核准後立即能呼叫需要主辦方的檢查（`is_organizer`）、同時核准與退回只有一個成功、篩選與分頁、身分清單。
- [x] `scripts/generate-client.sh` -- 重新產生 `frontend/src/client`。
- [x] `frontend/src/components/ui/{alert-dialog,textarea}.tsx`、`frontend/package.json`、`bun.lock` -- shadcn 元件與套件。
- [x] `frontend/src/components/common/ConfirmDialog.tsx` -- AlertDialog 包裝（見 Design Notes）。
- [x] `frontend/src/components/common/DataTable.tsx` -- Data table（見 Design Notes）。
- [x] `frontend/src/components/layout/BackofficeLayout.tsx` -- 側欄版面，項目由呼叫端傳入，主辦方後台之後共用。
- [x] `frontend/src/routes/admin/route.tsx`、`frontend/src/routes/admin/applications.tsx` -- 後台 layout route（登入＋平台管理員檢查，非管理員顯示 403）與 S35 路由（`validateSearch`：`status`、`page`）。
- [x] `frontend/src/features/identity/admin-applications.ts`、`AdminApplicationsPage.tsx` -- 查詢、核准與退回的 mutation、S35 畫面。
- [x] `frontend/src/features/identity/OrganizerApplyPage.tsx` -- 核准與退回狀態、預填重送表單。
- [x] `frontend/src/routes/organizer/index.tsx` -- S25 佔位頁。
- [x] `frontend/tests/unit/{confirm-dialog,data-table,backoffice-layout,admin-applications}.test.tsx`、`organizer-apply.test.tsx` -- I/O 矩陣前端各列、確認鈕停用條件、篩選與分頁寫入 URL、`< md` 卡片清單、側欄 active 樣式、S15 核准與退回狀態。

**Acceptance Criteria:**
- Given 平台管理員，when 從身分切換器「平台管理」進入 S35，then 以側欄版面（240px；`< lg` 從頂欄按鈕開啟 `Sheet`，選擇項目後自動關閉）顯示 Data table。
- Given 核准一筆申請，when 申請人重新整理頁面，then 身分切換器出現「主辦方後台」並能進入 S25 佔位頁，S15 顯示「核准」。
- Given 核准或退回完成，then 資料庫有對應的操作紀錄與一則事件，worker 處理後事件標為已處理、沒有寄任何信。
- Given 375 px 寬，when 瀏覽 S35（卡片清單、對話框）與 S15 的核准、退回狀態，then 沒有橫向捲軸。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- **後台版面沒有直接用 shadcn `Sidebar`**：它的行動版斷點寫死在 `useIsMobile`（768px，spec 要 `< lg`），而且是 `fixed` 定位、會和全站 `TopBar` 重疊。`BackofficeLayout` 改成自己排版：`≥ lg` 是 `w-sidebar-width`（240px）的 `aside`，用 `sidebar-*` token；`< lg` 用 shadcn `Sheet`。開啟 Sheet 的「☰ 平台管理」按鈕放在後台內容區頂端（全站頂欄之下），沒有塞進全站 `TopBar`：`TopBar` 在 `< sm` 已經有自己的選單鈕，兩個漢堡鈕會分不清。active 樣式是左側 2px `primary` 條＋`sidebar-accent` 底（DESIGN.md〈Sidebar nav〉）。
- **`@radix-ui/react-alert-dialog` 固定在 `^1.1.23`**：1.1.24 以後依賴新版 `react-dialog`，會在 `bun.lock` 裡多一份巢狀的 Radix 套件；1.1.23 和現有的 `react-dialog@1.1.23` 共用同一份。
- **新增 `EmptyState`、`AccountGate`**（task 清單沒列，但 S35 與 S25 都需要）：`components/common/EmptyState.tsx` 照 DESIGN.md 的 Empty state（L2 標誌本體以 CSS mask 填 `muted-foreground`）；`features/identity/AccountGate.tsx` 依帳號旗標決定顯示內容或 S38 403，平台管理後台與 S25 共用。這只是畫面，權限仍由 API 檢查。
- **DataTable**：桌機表格與 `< md` 卡片清單都會渲染，用 CSS（`hidden md:block`／`md:hidden`）切換，不用 `matchMedia`，所以不會閃動；測試要用 `data-slot=data-table`／`data-table-cards` 限定範圍。分頁用 shadcn `Pagination` 外框，但頁碼改用 `Button`（shadcn 的 `PaginationLink` 是沒有 href 的 `<a>`，而且文字是英文）；`< sm` 只顯示上一頁、「第 n／N 頁」與下一頁，375px 才放得下。
- **S35 網址**：預設值（待審核、第 1 頁）不寫進網址，不認得的 `status`、`page` 都當成預設。頁碼超出（例如最後一頁的申請都審核完了）時，自動換到最後一頁。審核失敗（例如 409）關閉對話框時會重抓列表；成功時先關對話框再重抓，避免列消失時對話框被一起卸載。
- **`/admin`** 直接導向 `/admin/applications`（後台還沒有自己的首頁）。`/organizer` 對不是主辦方的帳號顯示 403。
- **後端**：`_transition_application` 收到不是 approved／rejected 的目標時拋 `ValueError`（程式錯誤，不是業務錯誤）。核准先鎖申請、再鎖帳號；退回只鎖申請。`page < 1` 與不認得的 `status` 都是 FastAPI 預設的 422。
- **併發測試**：`test_concurrent_approve_and_reject_only_one_succeeds` 用兩條真的連線（核准持有列鎖時，確認退回被擋住，等核准提交後退回得到 409），所以要提交真的資料。測試結束會刪掉申請、申請人與事件；審核者帳號被只增不改的操作紀錄參照，會留在 `_test` 資料庫裡（不是管理員、Email 隨機，不影響其他測試；資料庫每次跑測試都會重建）。
- `identity-switcher.test.tsx` 原本預期 `/admin/applications` 是 404（「平台管理頁在 Story 1.8 才建立」），已改成以平台管理員身分進入 S35。
- 手動檢查時在開發資料庫建了測試資料：`story18-applicant@example.com`（測試申請人：退回→重送→核准，已是主辦方）與三筆 `story18-applicant-with-a-very-long-email-*` 的待審核申請。375px 下 S35 卡片清單、退回對話框、S15 退回／核准狀態、S25 都沒有橫向捲軸（`scrollWidth == 375`）。

## Spec Change Log

## Review Triage Log

## Design Notes

**API**（列表的回應格式是全專案第一個分頁 API，之後 2.1、2.2 沿用）：
- `GET /api/v1/admin/organizer-applications?status=pending&page=1` → `OrganizerApplicationPage`；`status` 省略表示全部；`page_size` 固定 20；依 `created_at` 由舊到新。
- `POST /api/v1/admin/organizer-applications/{id}/approval` → 200 `AdminOrganizerApplication`。
- `POST /api/v1/admin/organizer-applications/{id}/rejection` `{reason}` → 200 `AdminOrganizerApplication`。

**轉換函式**：`_transition_application(application, to, *, reason=None)` 是唯一改 `status` 的地方；只允許 `pending → approved|rejected`。操作紀錄 `before={status}`、`after={status, reject_reason}`（核准時 `after` 另帶 `account_id`、`is_organizer: true`）。

**S35**：標題「主辦方申請」；篩選（Select）：待審核（預設）、核准、退回、全部；欄位：社團名稱、學校、申請人（顯示名稱＋Email）、送出時間、狀態（Status badge）、操作（只有待審核列有「核准」「退回申請」）。篩選或換頁寫入 URL，換篩選時回到第 1 頁。核准對話框：標題「核准主辦方申請」、內文「核准後，<申請人> 會立即取得主辦方權限。」；退回對話框：標題「退回主辦方申請」、內文「申請人會看到退回原因，並可以修改後重新申請。」、理由欄「退回原因」（textarea，200 字）。

**ConfirmDialog**：`title`、`description`、`confirmLabel`、`destructive?`、`reason?: {label, maxLength}`、`onConfirm(reason?) => Promise`；送出中確認鈕 spinner 並停用；失敗時留在對話框顯示錯誤。

**DataTable**：`columns: {key, header, cell(row), className?}[]`、`rows`、`getRowId`、`page`、`pageSize`、`total`、`onPageChange`、`toolbar?`、`empty`；表頭 `overline`＋`muted-foreground`；`< md` 每列改成一張卡片（`header: value`）；頁數超過 1 才顯示 shadcn Pagination；首次載入 Skeleton。

**S15**：最新一筆為 `approved` → 摘要＋徽章「核准」＋主要按鈕「前往主辦方後台」；`rejected` → 摘要＋`Alert`「退回原因：…」＋表單預填社團名稱與學校，按鈕「重新送出申請」，送出成功後 `setQueryData` 成新的待審核摘要。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過，coverage 達 `fail_under`。
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bun run --filter frontend typecheck` -- expected: 無錯誤。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。
- `docker compose exec backend alembic heads` -- expected: 只有一個 head（本 Story 沒有遷移）。

**Manual checks (if no CLI):**
- 管理員在 S35 核准一筆、退回一筆（沒填原因時無法送出）；申請人重新整理後看 S15 的核准、退回與重送；一般帳號開 `/admin/applications` 看到 403；375 px 寬看 S35 卡片清單與對話框。
