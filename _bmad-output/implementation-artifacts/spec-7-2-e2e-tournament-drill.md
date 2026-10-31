---
title: 'Story 7.2 第一階段：端對端演練框架、身分流程與觀眾檢視（上游未合併處用假資料）'
type: 'feature'
created: '2026-10-31'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '03a09c1ca4f3ba23e5bf4d1bd86da19097d58bcf'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 專案還沒有任何端對端測試，也沒有能在 compose 裡執行 Playwright 的方式；7.2 的完整流程（建立賽事、組隊、抽籤、比分、申訴、取消資格）依賴的 2.x～6.x 都還沒合併。

**Approach:** 先做第一階段：建立能用一個指令在 compose 跑的 Playwright 多角色框架，實際跑通已存在的流程（註冊、從 Mailpit 取驗證信、登入、申請主辦方、平台管理員核准、觀眾瀏覽對戰樹與場次頁），並以桌機與 375 px 各跑一次、記錄 API 回應時間。上游未合併的步驟依完整流程寫成標註 Story 編號的待辦測試，遊戲設定以假資料驅動。

## Boundaries & Constraints

**Always:**
- 腳本只靠遊戲設定資料切換遊戲，不依遊戲名稱寫分支。
- 每個測試案例以 tag 標註 Story 與 FR 編號（例如 `@story-1.7`、`@FR-2`），給 7.3 的報告使用。
- 每次執行用不重複的 Email，可以對同一個資料庫重複執行。
- 選取元素優先用 role 與可見文字（介面是繁中），其次 `data-slot`。

**Never:**
- 不修改產品程式（`frontend/src`、`backend/app`）；只新增測試、測試設定與 compose 的 e2e 服務。
- 不在本機安裝 Bun 或 Node 套件來跑；不使用 npm。
- 不把端對端加進 CI（7.3 的測試總指令再處理）。
- 不寫通知相關步驟、不寫隊伍搜尋與晉級路徑（期中版調整）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 身分流程 | 訪客註冊、驗證、申請主辦方；管理員核准 | 申請人重新整理後身分切換器出現「主辦方後台」，可進入 `/organizer` | 驗證信 60 秒內沒到就失敗並列出 Mailpit 收件人 |
| 觀眾檢視 | 未登入開 `/dev/bracket`（32 隊進行中假資料） | 點場次卡進入場次頁，標題與卡片代碼一致，返回連結回到賽事 | N/A |
| 375 px | 同一組測試以 mobile 專案執行 | 每個頁面 `document` 沒有橫向捲軸；只有 `[data-slot=bracket-tree]` 可以橫向捲動 | N/A |
| API 回應時間 | 測試期間所有送往 API 的請求 | 每個測試附上回應時間 JSON；一般請求超過 1 秒就失敗並列出網址 | 登入（密碼雜湊）列為例外，只記錄不判定 |
| 上游未合併 | 建立賽事～頒獎、第三款遊戲、操作紀錄、10 秒更新 | 以 `test.fixme` 列出，標題註明等待的 Story，報告中顯示為待辦 | N/A |

## Decisions（2026-10-31，使用者授權直接採用建議選項）

- 分支從 `origin/story/5-8` 開 `story/7-2`：該分支已含 1.7、1.8、4.6、5.8 與它們的假資料；PR 在上游合併前會帶著那些 commit。
- 等待其他人的部分：有畫面的用該畫面的假資料（`/dev/bracket`、場次頁假資料）；沒有畫面的寫成 `test.fixme`，不自建假畫面。
- 執行方式：compose 新增 `e2e` 服務（profile `e2e`，Playwright 官方 image 加 Bun），容器內以 TCP 轉發讓瀏覽器照常使用 `localhost:5173`、`localhost:8000`，CORS 與 `VITE_API_URL` 不必改。
- 遊戲設定假資料：《特戰英豪》（`rounds`）、《英雄聯盟》（`win_loss`）與一款虛構的第三款遊戲，人數、BO、比分型態不同；之後與 7.1 第二階段的示範資料對齊。

</frozen-after-approval>

## Code Map

- `frontend/playwright.config.ts` -- 已有 baseURL（`PLAYWRIGHT_BASE_URL`）、忽略 `tests/unit`、未設 base URL 時起 `bun run dev`。要加 globalSetup、desktop 與 375 px 兩個專案、輸出位置。
- `frontend/tsconfig.json`、`biome.json` -- `tests/` 會被 typecheck 與 biome 檢查（雙引號、不加分號）。
- `frontend/Dockerfile` -- `oven/bun:1.4`，依根目錄 `bun.lock` 安裝；e2e image 照這個順序。
- `compose.yml` -- 服務 `frontend:5173`、`backend:8000`、`mailpit:8025`（SMTP 1025 只在內網）、`worker`（`WORKER_POLL_SECONDS` 預設 20，驗證信最慢約 30 秒）。
- 註冊 `/signup`：h1 與按鈕「註冊帳號」；欄位 Email、密碼（用 `getByLabel("密碼", { exact: true })`）、顯示名稱；學校是 combobox，點開後 `getByRole("option", { name })`。成功導向 `/verify-email`，h1「請收信驗證」。
- 驗證信：主旨「完成 FLOW 的 Email 驗證」，連結 `${FRONTEND_HOST}/verify-email?token=…`（`backend/app/modules/notifications/service.py`、`templates/email.html`）。成功頁 h1「Email 驗證完成」。
- 登入 `/login`：Email、密碼、按鈕「登入」；登入後頂欄出現 aria-label 以「切換身分」開頭的按鈕，選單有「登出」。
- 申請主辦方 `/organizer/apply`：h1「申請成為主辦方」，欄位「社團名稱」與「學校」，按鈕「送出申請」；成功顯示「待審核」，核准後顯示「核准」與「前往主辦方後台」。
- 審核 `/admin/applications`（平台管理員＝`FIRST_ADMIN_EMAIL`）：桌機是 table（aria-label「主辦方申請」），窄螢幕是 `ul[data-slot=data-table-cards]`；用 Email 找到那一筆後按「核准」，確認對話框（alertdialog「核准主辦方申請」）再按「核准」。
- 對戰樹 `/dev/bracket`（只在 dev server）：預設 32 隊「進行中」；場次卡 `article[data-slot=bracket-match-card]`（aria-label 為場次代碼），連結 `a[data-slot=bracket-match-link]`；捲動容器 `[data-slot=bracket-tree]`。
- 場次頁 `/tournaments/tournament-fixture/matches/<id>`：h1「<輪次> · <代碼>」，`data-slot=match-back-link`、`same-round-matches`。
- `_bmad-output/planning-artifacts/epics.md` Story 7.2 -- 完整流程與期中版調整，`test.fixme` 依此列步驟。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/Dockerfile.e2e`、`compose.yml` -- 新增 `e2e` 服務（profile `e2e`，image `mcr.microsoft.com/playwright:v1.63.0-noble` 加 Bun，`depends_on` frontend、backend、worker、mailpit；傳入 `PLAYWRIGHT_BASE_URL`、`MAILPIT_URL`、`FIRST_ADMIN_*`；把 `playwright-report`、`test-results` 掛回主機）-- 一個指令執行。
- [x] `frontend/playwright.config.ts` -- globalSetup、`desktop` 與 `mobile-375`（chromium，375×812）兩個專案。
- [x] `frontend/tests/e2e/support/` -- `proxy.ts`（globalSetup：有 `E2E_PROXY` 時把 localhost:5173／8000 轉到 frontend／backend）、`mailpit.ts`（等信並取出驗證連結）、`accounts.ts`（不重複 Email、註冊＋驗證、登入）、`fixtures.ts`（記錄 API 回應時間並判定 1 秒、附加 JSON）、`layout.ts`（無橫向捲軸檢查）、`games.ts`（三款遊戲設定假資料）。
- [x] `frontend/tests/e2e/identity.spec.ts` -- 身分流程（UJ-1 前半），含 Story／FR tag。
- [x] `frontend/tests/e2e/spectator.spec.ts` -- 觀眾檢視（UJ-4 期中版）。
- [x] `frontend/tests/e2e/tournament.spec.ts` -- 依遊戲設定產生的完整流程骨架：每一步一個 `test.fixme`，標題註明等待的 Story；含第三款遊戲、操作紀錄（直接查 AuditLog）、10 秒更新。
- [x] `README.md` -- 〈測試與檢查〉加端對端測試的指令與報告位置。

**Acceptance Criteria:**
- Given compose 已啟動，when `docker compose --profile e2e run --rm e2e`，then desktop 與 mobile-375 的身分流程、觀眾檢視都通過，fixme 顯示為 skipped，主機的 `frontend/playwright-report/` 有 HTML 報告。
- Given 同一個資料庫，when 再執行一次，then 仍全部通過。
- Given 前端檢查，when typecheck 與 `bunx biome check`，then 無錯誤。

## Design Notes

- TCP 轉發而不是改 `VITE_API_URL`：前端 build 時已決定 API 網址，backend 的 CORS 只允許 `http://localhost:5173`；在 e2e 容器裡把 localhost 的兩個埠轉到對應服務，產品設定完全不動。
- 多角色：同一個測試內用 `browser.newContext()` 分出申請人、平台管理員、觀眾，各自有獨立的 localStorage。

## Verification

**Commands:**
- `docker compose --profile e2e run --rm e2e` -- expected: 通過的測試＞0、失敗 0，fixme 列為 skipped
- `docker compose exec frontend bun run typecheck`、`docker compose exec frontend bunx biome check` -- expected: 無錯誤

## Implementation Notes

- 多了 `support/env.ts`（API、Mailpit 網址與 `FIRST_ADMIN_*`）：`proxy.ts` 是 globalSetup，不能 import 會呼叫 `test.extend` 的 `fixtures.ts`，共用設定放獨立檔。
- `proxy.ts` 除了 TCP 轉發，也等前端首頁與 `/api/v1/utils/health-check` 回 200 才開始測試（compose 的 `depends_on` 只保證 frontend 容器已啟動）。
- 報告目錄是掛載點，Playwright 刪不掉、舊檔會留著；`Dockerfile.e2e` 的 ENTRYPOINT 在每次執行前先清空 `playwright-report`、`test-results` 的內容。HTML reporter 設 `open: "never"`，否則在容器裡會停住等人開報告。
- `tests/` 與 `playwright.config.ts` 以唯讀掛載進 e2e 容器，改測試不必重新 build。
- 無橫向捲軸檢查略過 TanStack 開發工具（`.TanStackRouterDevtools`、`.tsqd-parent-container`）與 `visibility: hidden` 的元素：dev server 才有、不是產品介面，第一次執行就是被收合的 Router Devtools 面板誤判。
- `browser.newContext()` 會沿用專案的 viewport：實測 mobile-375 的角色 context 寬 375、desktop 1280。
- 觀眾檢視：S3 路由還沒建立，「返回連結回到賽事」只檢查 `href` 為 `/tournaments/tournament-fixture/bracket`，不點進去（會是 404）；另外點「同輪其他場次」換場，確認標題跟著換。
- 驗證結果（2026-10-31）：`docker compose --profile e2e run --rm e2e` 連續 3 次 4 passed、76 skipped（每次約 30～40 秒）；API 回應最慢為註冊 `POST /api/v1/accounts` 約 175 ms，登入約 120～140 ms；typecheck、`bunx biome check`、`test:unit`（367 個）皆通過。
- 主對話複驗（2026-10-31）：在全新 volume 的 compose 專案 `flow-verify` 連跑 2 次 e2e，都是 4 passed、76 skipped；typecheck、`bunx biome check`、`test:unit`（38 檔 367 個）、前端 build 皆通過。實作子代理當初是在使用者本機的 compose 上跑，開發資料庫因此多了 `e2e-` 開頭的測試帳號與主辦方申請。
- sprint 狀態維持 `in-progress`：只完成第一階段，比照 4.6、5.2 分階段時的做法。

## Spec Change Log

## Review Triage Log
