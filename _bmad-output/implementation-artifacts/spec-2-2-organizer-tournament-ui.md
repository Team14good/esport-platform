---
title: 'Story 2.2（第二階段）：S25 我的賽事、S26 建立賽事、S27 賽事總覽'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: 'e78ab6db871219bef3cfa4f2ef2043c04b7fdfbe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-2-2-create-tournament.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段的建立賽事 API 已合併，但主辦方沒有畫面可以用：`/organizer` 還是 1.8 的佔位頁，沒有建立賽事表單，也沒有賽事後台。

**Approach:** 只做前端，呼叫既有的 `listMyTournaments`、`createTournament`、`readMyTournament`、`listGamesForOrganizer`。S25 列出賽事、S26 建立賽事表單、S27 以賽事後台側欄顯示總覽；沿用 1.8 的 `BackofficeLayout`、`DataTable`、`ConfirmDialog` 與 1.7 的 `StatusBadge`。

## Boundaries & Constraints

**Always:**
- 三頁都要登入（`requireSignedIn`），且只有主辦方能看（`AccountGate`，其他帳號 S38 403）。
- S25（`/organizer`）：側欄「我的賽事」；`DataTable`（每頁 20 筆，頁碼寫在網址 `?page=`，前端分頁）欄位為賽事名稱（連到 S27）、遊戲、狀態徽章、報名截止、開賽時間；標題列右側「建立賽事」→ S26。沒有賽事時 Empty state「你還沒有建立賽事。」＋「建立賽事」。
- 狀態徽章 tone 依 DESIGN.md：開放報名 `live`；進行中 `live`＋脈動；賽程已公布 `brand`；已取消 `destructive`；尚未開放、報名截止、已結束 `muted`。
- S26（`/organizer/tournaments/new`）欄位：賽事名稱、遊戲、名額、先發人數、替補人數、BO（1／3／5／7）、報名開始、報名截止、優先期（小時，預設 24）、開賽時間、每輪間隔（分鐘）、棄權時限（分鐘，預設 15）、申訴期（分鐘，預設 30）、直播連結（選填）。不顯示賽事模式。
- 遊戲清單用 `listGamesForOrganizer`，不設長的 `staleTime`（進入頁面就重抓）。選遊戲後帶入該遊戲的先發、替補、BO（換遊戲時重新帶入），可以修改。
- 時間欄位以 Asia/Taipei 輸入（`datetime-local`），送出時轉成帶時區的 ISO（UTC）。
- 前端先做與後端相同的檢查，錯誤顯示在欄位下方：必填、整數與下限、報名開始早於截止、截止不晚於開賽、優先期結束不晚於截止、直播連結必須 http／https、每輪間隔 < 棄權＋BO × 每局預估時間＋申訴 時顯示「每輪間隔至少 N 分鐘」。選好遊戲後，每輪間隔欄位下方一直顯示目前的最小間隔。
- 伺服器 422 寫回對應欄位（`applyFieldErrors`），其他錯誤顯示在表單頂部 `FormErrorAlert`。
- 名額 > 128 時，送出前以 `ConfirmDialog` 提醒「名額超過 128 隊，請確認沒有輸入錯誤」，確認後才送出；≤ 128 直接送出。
- 建立成功：成功 Toast「已建立賽事。」並導向 S27。
- S27（`/organizer/tournaments/$tournamentId`）：賽事後台側欄（標題為賽事名稱），最上方「查看賽事頁」連到 S2，下方「總覽」；之後的 Story 把頁面加進這個側欄。總覽顯示賽事名稱＋狀態徽章，以及模式（校園賽）、遊戲、名額、報名期間、優先期結束、開賽時間、每輪間隔、BO、先發／替補、棄權時限、申訴期、直播連結（有填時）。不存在 → 404 頁；別人的賽事（403）→ S38 403。
- 不修改 1.8 的 `BackofficeLayout`、`DataTable`、`ConfirmDialog` 與 1.7 的 `StatusBadge`；只新增檔案或公開函式。

**Never:**
- 不改後端與 API（第一階段已合併）。
- 不做 S27 的倒數、待辦、「抽籤」「取消賽事」，不做修改賽事（S28）、分輪 BO、自訂模式、賽事報名連結。
- 不處理「報名截止後沒有轉成 closed」（C 的 3.6）。
- 不改 S1、S2（2.4 第二階段）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| S25 有賽事 | 2 筆賽事 | 每列名稱連到 S27、狀態徽章 | N/A |
| S25 空 | 0 筆 | 「你還沒有建立賽事。」＋「建立賽事」連到 S26 | N/A |
| 選遊戲帶入 | 選先發 5、替補 1、BO3 的遊戲 | 三個欄位帶入 5、1、3；改選另一款時重新帶入 | N/A |
| 間隔不足 | 每局 40、BO1、棄權 15、申訴 30、間隔 80 | 不送出 | 欄位下方「每輪間隔至少 85 分鐘」 |
| 日期順序錯 | 報名截止晚於開賽 | 不送出 | 報名截止欄位顯示原因 |
| 直播連結不合法 | `ftp://x` | 不送出 | 直播連結欄位顯示原因 |
| 名額 200 | 其他欄位合法 | 先彈出提醒；按確認才呼叫 API | 按取消不送出 |
| 名額 128 | 其他欄位合法 | 不彈提醒，直接送出 | N/A |
| 合法送出 | 台北時間 2026/11/10 19:00 | API 收到 `2026-11-10T11:00:00.000Z`；Toast 並導向 S27 | N/A |
| 伺服器 422 | `registration_end` 欄位錯誤 | 顯示在報名截止欄位下方 | N/A |
| 伺服器業務錯誤 | 404 `GAME_NOT_FOUND` | 表單頂部 Alert 顯示訊息 | N/A |
| S27 總覽 | 自己的賽事 | 側欄「查看賽事頁」→ `/tournaments/{id}`、「總覽」；顯示徽章、模式、各時間 | N/A |
| S27 別人的賽事 | 403 `TOURNAMENT_OWNER_REQUIRED` | — | S38 403 |
| S27 不存在 | 404 | — | 404 頁 |
| 非主辦方 | 一般帳號開三頁 | — | S38 403 |

## Decisions

- 2026-11-02（使用者）：優先期以「小時」輸入，預設 24，與 API 的 `priority_hours` 一致（UX reconcile-architecture 第 5 點的未定事項）。
- 2026-11-02（使用者）：spec 約 3000 tokens，超過建議值，但 S25～S27 是同一條流程（建立後導向 S27），保留在同一份 spec、同一個 PR。

</frozen-after-approval>

## Code Map

- `frontend/src/routes/organizer/index.tsx` -- 1.8 的 S25 佔位頁，本 Story 接手改寫；側欄 `ORGANIZER_NAV` 移到 features 共用
- `frontend/src/components/layout/BackofficeLayout.tsx` -- `BackofficeNavItem.to` 是 `LinkOptions["to"]`、沒有 `params`；S27 側欄以已代入 id 的實際路徑當 `to`，不改這個檔案
- `frontend/src/components/common/{DataTable,ConfirmDialog,StatusBadge,EmptyState,FormErrorAlert}.tsx` -- 直接沿用；`ConfirmDialog` 的 `onConfirm` resolve 後才關閉
- `frontend/src/routes/admin/applications.tsx`、`features/identity/AdminApplicationsPage.tsx` -- `validateSearch` 頁碼與 `DataTable` 的用法範本
- `frontend/src/features/identity/OrganizerApplyPage.tsx` -- react-hook-form＋zod＋`applyFieldErrors`＋`FormErrorAlert`＋`notifySuccess` 的表單範本
- `frontend/src/features/tournaments/{queries,status}.ts` -- 2.4 的公開查詢與 `TOURNAMENT_STATUS_LABEL`、`formatInterval`；新增主辦方查詢與徽章 tone，不改既有匯出
- `frontend/src/features/competition/match-time.ts` `formatMatchDateTime`、`frontend/src/lib/datetime.ts` `formatDateTime` -- 顯示用（Asia/Taipei）
- `frontend/src/components/layout/ErrorPage.tsx` `RouteErrorPage` -- 404／403 自動對應
- `frontend/tests/unit/backoffice-layout.test.tsx` -- 「S25 佔位頁」的 describe 斷言沒有「建立賽事」，本 Story 改為新行為（A 的測試檔，PR 說明列出）
- `frontend/tests/unit/{auth-fixtures,helpers}.ts` -- `signInAs`、`renderApp`、`httpError`
- 後端參考（不改）：`backend/app/modules/tournaments/service.py:264-311` 檢查順序與訊息；`models.py` 欄位下限（先發 ≥ 1、替補 ≥ 0、名額 ≥ 2、間隔 ≥ 1、名稱 ≤ 100 字、網址 ≤ 2048 字）

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/tournaments/status.ts` -- 新增 `TOURNAMENT_STATUS_BADGE`（tone、pulse）
- [x] `frontend/src/features/tournaments/TournamentStatusBadge.tsx` -- 包 `StatusBadge`，2.4 第二階段可沿用
- [x] `frontend/src/features/tournaments/organizer-queries.ts` -- 主辦方賽事清單、單筆、遊戲清單的 queryOptions 與建立的 mutation
- [x] `frontend/src/lib/datetime.ts` -- 新增 `taipeiLocalToIso`（`datetime-local` 值 → UTC ISO）
- [x] `frontend/src/features/tournaments/organizer-nav.ts` -- `ORGANIZER_NAV`、`tournamentNav(id)`
- [x] `frontend/src/features/tournaments/{OrganizerTournamentsPage,CreateTournamentForm,OrganizerTournamentOverview}.tsx` -- 三個畫面
- [x] `frontend/src/routes/organizer/{index.tsx,tournaments/new.tsx,tournaments/$tournamentId/route.tsx,tournaments/$tournamentId/index.tsx}` -- 路由；`route.tsx` 放賽事後台版面與 `Outlet`，之後的頁面接在下面；重新產生 `routeTree.gen.ts`
- [x] `frontend/tests/unit/organizer-tournaments.test.tsx`、`backoffice-layout.test.tsx` -- I/O Matrix 每列至少一個測試；佔位頁測試改為新行為
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 source_spec 為 2.2 的兩筆（S25～S27、名額 128 提醒）

**Acceptance Criteria:**
- Given 主辦方從身分切換器進入主辦方後台，when 開啟，then 到 S25
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- 賽事後台版面放在 `features/tournaments/OrganizerTournamentOverview.tsx` 的 `OrganizerTournamentLayout`（`route.tsx` 只負責 `AccountGate` 與 `Outlet`），版面與總覽共用同一個 `readMyTournament` 快取；403、404 不重試。
- S26 的表單值一律是字串，檢查集中在一個 `superRefine`（任一欄位錯誤時其他欄位的錯誤也一起顯示）；resolver 只建立一次，檢查時讀最新的遊戲清單。名額 > 128 的確認對話框：`onConfirm` 只啟動 mutation（不等待結果）就 resolve，對話框隨即關閉，伺服器的欄位錯誤寫回表單而不是留在對話框。
- 「報名截止、開賽時間必須晚於現在」前端不檢查（spec 的前端檢查清單沒有列），由伺服器 422 寫回欄位。
- `BackofficeLayout` 的連結是預設的模糊比對 active：之後在 `$tournamentId` 底下加頁面時，「總覽」在子頁面也會是 active，屆時要決定是否在 `BackofficeNavItem` 加 `activeOptions`（屬 A 的元件，只能新增）。
- 驗證環境：worktree 沒有 `.env`，且 compose 專案已由主 checkout 啟動；改以 `docker build -f frontend/Dockerfile -t espory-2-2-ui-frontend .` 建立獨立映像執行 build、typecheck、test:unit。以 bind mount 掛載原始碼執行整套測試時，Windows 檔案系統太慢，各檔第一個測試的 `findBy*` 會逾時（與本 Story 無關）。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-02）：Blind Hunter 13 筆、Edge Case Hunter 7 筆、Verification Gap 2 筆＋1 筆其他。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Edge | 驗證（async resolver）期間連按送出，`create.isPending` 尚未生效，會呼叫兩次建立 API | medium：會建立重複賽事；按鈕只看 `isPending` | patch |
| 2 | Edge | 名額 > 128 的確認鈕連按兩次，`submit(pendingBody)` 執行兩次 | medium：與 #1 同一根因（送出沒有防重入） | patch |
| 3 | Edge | 送出中離開頁面，per-call `onSuccess` 不執行，沒有 Toast | low：賽事已建立、S25 會出現；日常少見，修正要搬動回呼 | 不處理 |
| 4 | Edge | 背景重抓遊戲清單失敗時，已有快取仍停用選單並顯示錯誤 | low：重試 3 次後才會發生；修正是直接改條件 | patch |
| 5 | Edge | `datetime-local` 值帶毫秒會被判為不合法 | false：沒有設定 `step`，瀏覽器的值只到分鐘 | 不處理 |
| 6 | Edge | 直播連結長度以 UTF-16 計算，後端以字元計算 | low：直接改成 `[...url].length` | patch |
| 7 | Edge | 棄權或申訴清空時最小間隔提示消失 | false：欄位空白時沒有可計算的最小間隔 | 不處理 |
| 8 | Blind | 送出失敗後修正 BO、開賽時間等，依賴它們的其他欄位錯誤（每輪間隔、報名截止、優先期）不會更新 | low：日常會遇到（修正日期順序），錯誤訊息留在已不成立的欄位 | patch |
| 9 | Blind | 業務錯誤只顯示在長表單頂部，沒有捲動或聚焦 | low：EXPERIENCE 規定業務錯誤放表單頂部；S26 唯一可能的業務錯誤（`GAME_NOT_FOUND`）沒有刪除遊戲的 API，幾乎不會發生 | 不處理 |
| 10 | Blind | `GAME_NOT_FOUND` 後 `game_id` 仍是不存在的遊戲 | low：tournaments 沒有刪除遊戲的 API，只有手動竄改請求才會遇到 | 不處理 |
| 11 | Blind | 確認對話框的註解寫「先關閉再送出」，與程式順序不符 | low：直接修正註解；Implementation Notes 已同步改寫 | patch |
| 12 | Blind | `toTournamentCreate` 轉換失敗時送出原字串 | false：只在 schema 通過後呼叫，schema 已拒絕無法轉換的值 | 不處理 |
| 13 | Blind | `parsePage` 從 identity 的 admin-applications 匯入 | low：跨 feature 依賴，但函式穩定；搬到 lib 需新增公開函式 | 不處理 |
| 14 | Blind | S27 側欄沒有回到「我的賽事」，S26 沒有返回動作 | low：側欄項目由凍結的 intent 決定；身分切換器的「主辦方後台」可回 S25 | 不處理 |
| 15 | Blind | S27 頁面標題是通用文字，載入與錯誤時側欄消失 | low：外觀問題 | 不處理 |
| 16 | Blind、Gap | `GAME_NOT_FOUND` 後重抓遊戲清單沒有測試 | low：刪掉該分支測試照樣通過 | patch（補測試） |
| 17 | Blind、Gap | 網址頁碼超過最後一頁的修正沒有測試；拿掉 clamp 會讓有賽事的主辦方看到空狀態 | medium：沒有測試守住 | patch（補測試） |
| 18 | Blind | 其他未測分支（遊戲清單錯誤、空遊戲清單、S27 一般錯誤、422 視為 404） | low：不在 I/O Matrix，行為單純 | 不處理 |
| 19 | Blind | Verification 寫 `docker compose`，實際在獨立映像執行 | false：已在獨立映像執行 build、typecheck、biome、test:unit（Implementation Notes 記載原因） | 不處理 |
| 20 | Blind | 沒有 AI 使用紀錄 | false：在 bmad-build 完成時新增 | 不處理 |
| 21 | Blind | 動到 A 的測試檔沒有追蹤 | false：Code Map 已記載，開 PR 時列在說明 | 不處理 |
| 22 | Blind | 數字輸入框滾輪會改值、超大數字精度 | low：瀏覽器行為，全站相同；超大值仍被擋下 | 不處理 |
| 23 | Gap | `staleTime: 0` 與全站預設相同，沒有實際作用 | false：不是缺陷，是明示意圖的註記 | 不處理 |

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- 服務 healthy
- `docker compose exec frontend bun run --filter frontend build`、`... typecheck`、`... lint`（biome）-- 通過
- `docker compose exec frontend bun run --filter frontend test:unit` -- 全部通過
