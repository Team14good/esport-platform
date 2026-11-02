---
title: 'Story 2.1（第二階段）：S36 遊戲設定與學校清單畫面'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: '46476498fe7a5c1790c3c64f6c491cbee4156c75'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段已有遊戲與學校的管理 API，但平台管理員沒有畫面可用，只能直接呼叫 API；1.8 的後台版面與 Data table 已合併，可以接上。

**Approach:** 在平台管理後台加入 S36：遊戲列表（`/admin/games`）、新增與編輯頁（`/admin/games/new`、`/admin/games/$gameId`，含段位對照表），以及學校清單（`/admin/schools`：列出、新增、修正名稱）。只呼叫既有 API，不改後端。

## Boundaries & Constraints

**Always:**
- 沿用 1.8 的 `BackofficeLayout`、`DataTable`（< md 變卡片）、`ConfirmDialog`、Toast、`api-error` 的錯誤處理；375 px 寬沒有橫向捲軸。
- 表單在前端先依第一階段的規則驗證並顯示繁中訊息（名稱必填且 ≤100 字、先發 ≥1、替補 ≥0、BO 只能 1／3／5／7、每局時間 ≥1、段位至少一筆、段位名稱 ≤50 字且不分大小寫不重複、積分為非負整數），讓使用者看不到後端的英文 422 訊息。
- 比分型態的顯示文字：`win_loss`「只記勝負」、`rounds`「記回合比分」。
- 學校新增或改名成功後，讓 `["identity","schools"]` 查詢失效，註冊、主辦方申請與帳號頁的學校選單立即反映。
- 409（`GAME_NAME_TAKEN`、`SCHOOL_NAME_TAKEN`）顯示在名稱欄位下方；404 顯示「找不到這款遊戲」並提供回列表的連結。
- 介面文字為繁中，按鈕用動詞＋名詞（「新增遊戲」「儲存變更」「新增學校」「修正名稱」）。

**Never:**
- 不改後端 API 與 schema、不刪除或停用遊戲與學校。
- 不做離開頁面時的未儲存提醒、不做拖曳排序段位。
- 不手寫 fetch；不改 1.8 既有元件的行為（只新增側欄項目）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 遊戲列表 | 有 2 款遊戲 | Data table 列出名稱、先發／替補、預設 BO、每局時間、比分型態，點列或「編輯」進編輯頁 | 讀取失敗顯示錯誤＋「重新載入」 |
| 沒有遊戲 | 空清單 | 空狀態「還沒有遊戲。」＋「新增遊戲」 | N/A |
| 新增遊戲 | 合法資料、2 筆段位 | 呼叫 `createGame`，Toast「已新增遊戲」，回列表並看到新遊戲 | N/A |
| 前端驗證 | BO 留空或段位名稱重複 | 不送出，欄位下方顯示繁中錯誤（段位錯誤標在該列） | N/A |
| 名稱重複 | 後端回 409 `GAME_NAME_TAKEN` | 名稱欄位下方顯示後端訊息 | 表單保留輸入 |
| 編輯遊戲 | 改 BO、刪一列段位 | 表單預填現值；呼叫 `updateGame`，Toast「已儲存變更」 | 遊戲不存在顯示「找不到這款遊戲」 |
| 學校清單 | 有多筆學校 | 依名稱列出，可用關鍵字篩選，每頁 20 筆 | 讀取失敗顯示錯誤＋「重新載入」 |
| 新增學校 | 新名稱 | Dialog 送出，Toast「已新增學校」，清單與學校選單立即包含 | 409 顯示在欄位下方 |
| 修正學校名稱 | 改名 | Dialog 預填原名，送出後 Toast「已修正學校名稱」 | 409 顯示在欄位下方 |
| 非平台管理員 | 一般帳號開 `/admin/games` | 1.8 的 403 頁（`AccountGate`） | N/A |

## Decisions

- 2026-11-02（使用者）：側欄放兩個項目「遊戲設定」（`/admin/games`）與「學校清單」（`/admin/schools`），各自一頁，與「主辦方申請」同一層；頁面內不用 `Tabs`。epics 的「學校清單分頁」以側欄項目實現。
- 2026-11-02（使用者）：遊戲列表以「名稱連結＋『編輯』按鈕」進編輯頁，不做點整列；I/O Matrix「點列」以此為準，1.8 的 `DataTable` 不改。

</frozen-after-approval>

## Code Map

- `frontend/src/routes/admin/route.tsx:17-19` `ADMIN_NAV` -- 加側欄項目（lucide 圖示）；`/admin` 仍轉到 `/admin/applications`，不改
- `frontend/src/routes/admin/applications.tsx`、`features/identity/AdminApplicationsPage.tsx`、`features/identity/admin-applications.ts` -- 頁面、query options、mutation＋`notifySuccess`、錯誤狀態的寫法照抄
- `frontend/src/components/common/DataTable.tsx` -- 必須傳分頁 props；列表不分頁時在前端切 20 筆一頁
- `frontend/src/components/common/{ConfirmDialog,EmptyState,FormErrorAlert}.tsx`、`components/ui/{dialog,form,select,input}.tsx`
- `frontend/src/features/identity/OrganizerApplyPage.tsx:61,98-126` -- zod＋react-hook-form＋`applyFieldErrors`＋依 `parsed.code` 分支的範例
- `frontend/src/lib/api-error.ts` -- `parseApiError`、`getErrorMessage`、`applyFieldErrors`（巢狀 `rank_tiers.0.name` 只會對到最後一段，所以段位錯誤要靠前端驗證）
- `frontend/src/client/sdk.gen.ts` -- `TournamentsService.listGames/createGame/readGame/updateGame`、`IdentityService.listSchools/createSchool/renameSchool`；型別 `GameIn`、`GameRead`、`RankTierIn`、`ScoreType`、`SchoolIn`、`PublicSchool`
- `frontend/src/features/identity/schools.ts` `useSchools()` -- key `["identity","schools"]`，`staleTime: Infinity`，異動後要 invalidate
- `frontend/tests/unit/admin-applications.test.tsx`、`auth-fixtures.ts`（`renderApp`、`signInAs`）、`helpers.ts`（`httpError`）-- 測試寫法
- `frontend/src/routeTree.gen.ts` -- 不手改，依 CLAUDE.md 掛整個 `frontend/` 跑 `bunx vite build` 產生

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/tournaments/admin-games.ts`、`frontend/src/features/identity/admin-schools.ts` -- query options 與 mutation（含學校 key 失效）
- [x] `frontend/src/features/tournaments/{AdminGamesPage,GameForm}.tsx` -- 列表與共用的新增／編輯表單（段位表可新增、刪除列）
- [x] `frontend/src/features/identity/AdminSchoolsPage.tsx` -- 列表、篩選、新增與修正名稱 Dialog
- [x] `frontend/src/routes/admin/{games/index,games/new,games/$gameId,schools}.tsx`、`routes/admin/route.tsx` -- 路由、`head` 標題、側欄
- [x] `frontend/tests/unit/admin-games.test.tsx`、`admin-schools.test.tsx` -- I/O Matrix 每列至少一個測試，含 375 px 卡片版面
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.1 改為 review（合併前由作者改 done）

**Acceptance Criteria:**
- Given 平台管理員新增遊戲，when 主辦方開建立賽事的遊戲選單，then 不需重新整理後端即可選到（沿用 `listGamesForOrganizer`）
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- 「點列進編輯頁」：1.8 的 `DataTable` 沒有列點擊的 props，依「不改 1.8 既有元件」改成名稱欄是連到編輯頁的連結，另有「編輯」按鈕。
- 新增遊戲的空白表單：預設 BO 與比分型態都不預選（要使用者選），段位表先放一列空白；刪到 0 列時顯示「至少需要一筆段位」。
- 數字欄位以文字輸入框（`inputMode="numeric"`）驗證，錯誤訊息與後端相同（「先發人數不能小於 1」等）；表單值通過驗證後才轉成 `GameIn`。
- 編輯成功後留在編輯頁（Toast「已儲存變更」）；新增成功後回列表。
- 學校清單沿用 `useSchools()`（同一個 `["identity","schools"]` 查詢），不另開管理用的 API；空狀態文案「還沒有學校。」，篩選後沒有結果「沒有符合條件的學校。」（spec 沒有指定）。
- 列表的分頁與篩選放在元件狀態，不寫進網址。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-02）：Blind Hunter 12 筆（含測試缺口細項）、Edge Case Hunter 9 筆、Verification Gap 4 筆，共 28 列。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Gap | 遊戲表單與學校 Dialog 的非 409 錯誤（500 等）沒有測試 | medium：拿掉 `setFormError` 現有測試不會失敗 | patch |
| 2 | Gap | 編輯頁非 404 的讀取錯誤沒有測試 | medium：與 #25 同一段程式，修正時一起補 | patch |
| 3 | Gap | 改名儲存後標題靠 `setQueryData` 更新，沒有測試 | low：在既有編輯測試加一個斷言即可 | patch |
| 4 | Gap、Blind | 「主辦方遊戲選單立即可選」沒有可驗證的對象 | low：後端每次讀資料庫，前端還沒有 2.2 畫面；修正方式是改 spec | 不處理（2.2 畫面不要對遊戲選單設長 `staleTime`） |
| 5 | Blind | 後端段位 422 以 `loc` 最後一段對到「遊戲名稱」欄位 | low：前端驗證擋在前面，只有 #7 的特殊字元會到後端；修正要加分支 | 不處理 |
| 6 | Blind、Edge | 段位名稱比對用 `toLowerCase()`，後端用 `casefold()`（ß／SS） | low：直接修正比較方式 | patch |
| 7 | Blind、Edge | JS `trim()` 與 Python `strip()` 去除的字元不同 | low：只有控制字元等罕見輸入，修正要自寫空白集合 | 不處理 |
| 8 | Blind | 凍結 I/O Matrix 寫「點列進編輯頁」，實作是名稱連結＋「編輯」 | intent_gap：凍結區塊同時寫「不改 1.8 既有元件」，`DataTable` 沒有列點擊，兩條無法同時滿足 | 使用者決定點名稱即可，記入 Decisions，程式不變 |
| 9 | Blind | 學校空狀態文案「還沒有學校。」「沒有符合條件的學校。」spec 沒有指定 | low：已提給使用者確認，沒有要求修改 | 不處理 |
| 10 | Blind | `codePointLength` 重複，且從 `SignupForm` 元件檔 import | low：沒有已知的分歧；搬移要改 A 的 identity 檔案 | 不處理 |
| 11 | Blind | 全形數字（注音輸入法常見的「５」）被判為「請輸入整數」 | medium：使用者輸入的是數字卻被拒 | patch |
| 12 | Blind、Edge | 載入中與讀取失敗時看不到「新增遊戲」 | low：直接修正顯示條件 | patch |
| 13 | Blind | `useCreateGame` 讓所有 detail 查詢失效，剛寫入的 detail 會白抓一次 | low：直接縮小失效範圍 | patch |
| 14 | Blind、Edge | 學校名稱沒變也呼叫 API 並顯示「已修正學校名稱」 | low：後端不寫紀錄，只是多一則 Toast；修正要加分支 | 不處理 |
| 15 | Blind | 編輯頁的 409 沒有測試 | low：與新增共用 `GameForm`，新增頁已測 | 不處理 |
| 16 | Blind | 段位 100 筆上限與 INT_MAX 訊息沒有測試 | low：邊界只有平台管理員會碰到 | 不處理 |
| 17 | Blind | 「送出中不能關 Dialog」沒有測試 | low | 不處理 |
| 18 | Blind | `SCHOOLS_QUERY_KEY` 複製 `schools.ts` 的 key，A 改 key 時失效會悄悄壞掉 | medium：註冊、主辦方申請的學校選單不會更新且沒有測試發現 | patch（加測試確認 `useSchools` 的查詢會被這個 key 失效） |
| 19 | Blind | 409 測試以 `aria-describedby.split(" ")[1]` 找訊息 | low：表單元件改版時才會壞 | 不處理 |
| 20 | Blind | `routeTree.gen.ts` 不在 diff 中 | false：產生檔刻意排除在審查 diff 外；在容器以 `bunx vite build` 產生，build 與 typecheck 通過 | 不處理 |
| 21 | Blind | 編輯頁分頁標題固定為「編輯遊戲 · FLOW」 | low | 不處理 |
| 22 | Blind | 儲存後表單保留未去空白的輸入 | low：下次進頁面即為後端的值 | 不處理 |
| 23 | Blind | `toGameIn` 的 `+ 0` 沒有說明 | low：補一行註解 | patch |
| 24 | Edge | 網址的 gameId 不是 UUID 時後端回 422，畫面顯示英文驗證訊息 | medium：手改或舊連結會看到英文 | patch（視為找不到） |
| 25 | Edge | 已載入後背景重抓失敗，表單被換成錯誤畫面，未儲存的修改消失 | medium：React Query 視窗重新聚焦會重抓 | patch（有資料時優先顯示表單） |
| 26 | Edge | 連點送出可能送兩次 | low：直接把 `isSubmitting` 納入按鈕停用 | patch |
| 27 | Edge | （主張）段位不分大小寫比對與後端一致 | 同 #6 | patch |
| 28 | Edge | （主張）使用者看不到後端英文 422 | 同 #24 | patch |

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- 五個服務 healthy
- `docker compose exec -T frontend bun run --filter frontend build`、`... typecheck`、`bunx biome check`、`bun run test:unit` -- 全部通過
- `docker compose exec -T backend bash scripts/test.sh` -- 全部通過（確認沒有誤動後端）

**Manual checks:**
- 瀏覽器以平台管理員走過新增遊戲、編輯段位、新增與修正學校；375 px 寬沒有橫向捲軸
