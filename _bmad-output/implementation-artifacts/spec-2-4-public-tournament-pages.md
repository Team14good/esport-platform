---
title: 'Story 2.4（第一階段）：公開賽事列表、賽事頁總覽與 Countdown'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: 'f7e134eab94effc35e7b8deadc7da88dbd80f438'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 觀眾還沒有任何地方看到賽事：首頁是健康檢查的佔位頁，也沒有賽事頁；C 的 3.x、A 的 4.6、5.8 都在等 S2 與 Countdown 元件。

**Approach:** 新增不需登入的公開賽事 API（只回 `Public*` schema）、S1 賽事列表、S2 賽事頁的「總覽」分頁，以及全站共用的 Countdown 與 Page banner 元件。狀態徽章與「申請成為主辦方」橫幅等 1.7、1.8 合併後在第二階段補上。

## Boundaries & Constraints

**Always:**
- API：`GET /tournaments`（所有賽事）、`GET /tournaments/{tournament_id}`（不存在 404 `TOURNAMENT_NOT_FOUND`），不需登入；回傳 `PublicTournament`：`id`、`name`、`status`、`game_name`、`capacity`、`registration_start`、`priority_end`、`registration_end`、`start_at`、`round_interval_minutes`、`livestream_url`。不含 `organizer_id`、Email、學校（AD-19）。
- S1（`/`）：依狀態分組（順序見 Decisions），每筆顯示賽事名稱、遊戲、名額、報名期間、開賽時間、狀態文字；「尚未開放」另顯示報名開始時間；「已取消」標示「已取消」。點擊進 S2。沒有賽事時顯示「目前沒有公開的賽事。」。
- S2（`/tournaments/$tournamentId`）：標題列（賽事名稱、狀態）＋`Tabs`，本 Story 只有「總覽」分頁；總覽顯示名稱、遊戲、名額、報名期間、開賽時間、每輪間隔、狀態。有 `livestream_url` 時頂部「觀看直播」，另開分頁（`rel="noopener noreferrer"`）。不存在的賽事顯示 404 頁。
- S2 依狀態：「尚未開放」顯示報名開始倒數（`muted`，下方寫「{時間} 開放報名」，歸零時寫「報名開放中 · 系統處理中」），已登入者的「建立隊伍」停用並寫「{報名開始時間} 開放報名」；「開放報名」顯示報名截止倒數（`muted`，最後 24 小時 `appeal`）；「報名截止」顯示「抽籤準備中」；「已取消」頂部 destructive Page banner「此賽事已取消」。
- Countdown（`components/common/Countdown.tsx`）：說明文字＋等寬數字；≥ 24 小時「剩 2 天 5 小時」、1～24 小時「剩 5 小時 12 分」、未滿 1 小時 `mm:ss` 每秒跳動；下方「{絕對時間} {後綴}」，後綴由呼叫端指定、預設「截止」（`10/18（六）19:00`，Asia/Taipei，沿用 `features/competition/match-time.ts` 的 `formatMatchDateTime`，不修改該檔）；變體 `muted`／`live`／`appeal`／`destructive`，只有 `appeal` 有 4px 進度條；歸零後顯示歸零文字（由呼叫端指定，預設「已截止 · 系統處理中」）＋小 spinner，並呼叫 `onExpire` 讓頁面每 5 秒重抓，最多 2 分鐘，之後顯示「處理時間比預期長。重新整理頁面查看最新狀態。」。
- Page banner（`components/common/PageBanner.tsx`）：shadcn `Alert`，內容區頂部滿版；變體 `default`（可帶 outline Button、可關閉）與 `destructive`；同頁最多一則、destructive 優先。
- 路由：S2 用 `routes/tournaments/$tournamentId/index.tsx`，不建立會包住 S4（`matches/$matchId`）的 layout route；分頁列做成元件，4.6 的 S3 之後沿用。
- 375 px 寬沒有橫向捲軸。介面文字繁體中文。

**Never:**
- 不做狀態徽章元件（1.7 的 `StatusBadge` 合併後在第二階段換上）、「想辦賽事？申請成為主辦方」橫幅、主辦方在 S1 的「建立賽事」（需要 1.7、1.8 與 2.2 第二階段）。
- 不掛載 3.1 的建立隊伍對話框（「開放報名」時的啟用按鈕由 C 的 3.1 接上）；不做已正取隊數（需要 registration）。
- 不做對戰表、正取隊伍分頁、頒獎台、檢舉入口、自訂模式的標示（4.6、3.9、6.4、3.10）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 公開列表 | 未登入，各狀態賽事各一場 | 200，全部列出，欄位只有 `PublicTournament` 的欄位 | N/A |
| 公開單場 | 未登入，存在的賽事 | 200 | 不存在 404 `TOURNAMENT_NOT_FOUND` |
| 不洩漏資料 | 任一公開 API | 回應不含 `organizer_id`、Email、學校 | N/A |
| S1 無賽事 | 沒有賽事 | 「目前沒有公開的賽事。」 | API 失敗顯示錯誤與重試 |
| S1 分組 | 混合狀態 | 依 Decisions 的順序分組；空的組不顯示 | N/A |
| 尚未開放 | S2，已登入 | 報名開始倒數（muted）、「建立隊伍」停用並寫開放時間 | N/A |
| 開放報名最後 24 小時 | 報名截止剩 5 小時 | 倒數「剩 5 小時 0 分」，`appeal` 變體 | N/A |
| 倒數 < 1 小時 | 剩 59:30 | `mm:ss` 每秒更新 | N/A |
| 倒數歸零 | 時間到 | 「已截止 · 系統處理中」，每 5 秒重抓；狀態改變後換成新狀態的畫面；2 分鐘仍未變顯示提示文字 | N/A |
| 直播 | 有 `livestream_url` | 「觀看直播」另開分頁 | 無連結時不顯示 |
| 已取消 | S2 | destructive banner「此賽事已取消」，不顯示倒數 | N/A |

## Decisions

- 2026-11-02（使用者）：2.4 拆兩階段。第一階段不等 1.7、1.8：公開 API、S1、S2 總覽、Countdown、Page banner；狀態先以文字顯示。狀態徽章、「申請成為主辦方」橫幅、主辦方的「建立賽事」入口在 1.7、1.8 合併後的第二階段補上。
- 2026-11-02（使用者）：S1 分組順序為「觀眾最關心的在前」：進行中 → 開放報名 → 尚未開放 → 報名截止 → 賽程已公布 → 已結束 → 已取消。組內依開賽時間由近到遠；已結束、已取消依開賽時間由新到舊。
- 2026-11-02（使用者）：Countdown 下方那行的後綴可由呼叫端指定，預設「截止」；報名開始倒數寫「{時間} 開放報名」（例：「11/5（三）19:00 開放報名」）。
- 2026-11-02（使用者）：Countdown 歸零文字也可由呼叫端指定，預設「已截止 · 系統處理中」；報名開始倒數歸零時寫「報名開放中 · 系統處理中」。第二輪審查發現的這項 intent_gap，經使用者同意當成小修正處理，不還原程式重做。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/{models,service,router}.py` -- 已有 `TournamentRead`、`get_tournament`、`TournamentStatus`；新增 `PublicTournament`、`list_public_tournaments`、公開路由（無權限依賴，參考 `identity/router.py:47` `GET /schools`）。不要用 `PublicTournamentRef`（competition 已有同名）
- `backend/tests/test_auth_required.py` -- 只檢查寫入 API，公開 GET 不用登錄
- `frontend/src/routes/index.tsx` -- 目前是健康檢查佔位頁，整個換成 S1
- `frontend/src/routes/tournaments/$tournamentId/` -- 5.8（未合併）會新增 `matches/$matchId.tsx`；S2 用同資料夾的 `index.tsx`
- `frontend/src/components/layout/AppShell.tsx:8` -- 內容區；Page banner 放在頁面內容最上方
- `frontend/src/features/competition/match-time.ts:45` `formatMatchDateTime` -- 絕對時間格式；D 的檔案，只 import 不修改
- `frontend/src/features/identity/auth.ts:107` `useIsSignedIn` -- 「建立隊伍」停用按鈕只給登入者
- `frontend/src/components/ui/{tabs,alert,skeleton,card}.tsx` -- 已有
- 等這些元件的插槽：`CheckInPanel.countdown?`（main）、4.6／5.8 的 `BracketPending.countdown?`、`MatchAppealWindow.countdown?`（appeal 變體＋進度條）
- UX：`EXPERIENCE.md:38-40,256-264,529-558,237`；`DESIGN.md:427-453`；epics.md:737-777

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/{models,service,router}.py` -- `PublicTournament`、`list_public_tournaments`、`get_public_tournament`、`GET /tournaments`、`GET /tournaments/{tournament_id}`
- [x] `backend/tests/tournaments/test_public_tournaments.py` -- 未登入可讀、404、回應欄位白名單
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh`
- [x] `frontend/src/components/common/{Countdown,PageBanner}.tsx` -- 共用元件
- [x] `frontend/src/features/tournaments/` -- 狀態文字對照、S1 列表、S2 標題與分頁列、總覽、查詢 hooks
- [x] `frontend/src/routes/index.tsx`、`frontend/src/routes/tournaments/$tournamentId/index.tsx`、`routeTree.gen.ts`
- [x] `frontend/tests/unit/` -- Countdown（格式、變體、每秒跳動、歸零與 2 分鐘逾時，用 fake timers）、PageBanner、S1 分組與空狀態、S2 各狀態

**Acceptance Criteria:**
- Given 375 px 寬的手機，when 瀏覽 S1 與 S2，then 沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- Countdown 歸零後由元件自己計時：立即呼叫一次 `onExpire`，之後每 5 秒一次，滿 2 分鐘停止並改顯示提示；頁面只要把 `refetch` 傳進來。狀態改變後頁面換掉這個 Countdown（`key` 含狀態與目標時間），計時跟著重設。
- `appeal` 進度條的起點用 `startsAt`；S2 報名截止沒有傳，預設以截止前 24 小時為起點（對應「最後 24 小時」）。4.6／5.8 的申訴期倒數應傳入申訴期開始時間。
- 報名截止倒數的變體以函式傳入（`registrationEndVariant`），倒數跨過 24 小時時不需重抓就會換成 `appeal`。
- S2 用 `useQuery` 而非路由 loader：歸零後重抓失敗時保留畫面資料；404 與 id 格式錯誤（422）都顯示 404 頁。
- 首頁換成 S1 後，`tests/unit/home.test.tsx`（健康檢查）刪除；`auth-fixtures.ts` 的 `renderApp` 改為 mock 公開賽事列表；`auth.test.tsx` 兩個測試原本等首頁的「FLOW」標題，改等 S1 的「賽事」標題（A 的測試檔，只改等待條件）。

## Spec Change Log

### 2026-11-02 第一輪審查 → intent_gap 迴圈（review_loop_iteration 1）

- **觸發的發現**：Blind Hunter、Edge Case Hunter 都指出「尚未開放」的報名開始倒數，下方寫「{時間} 截止」，意思相反。根因在凍結區塊（Countdown 一律寫「截止」），屬於 intent_gap。
- **修改**：使用者決定後綴可由呼叫端指定、預設「截止」，報名開始寫「開放報名」；已寫入凍結區塊的 Countdown、S2「尚未開放」兩條與 Decisions。第一輪的程式已還原（保存在 scratchpad 的 `impl-2-4-round1.patch`），依本 spec 重新實作。
- **避免的錯誤狀態**：報名開始時間被標成「截止」，觀眾誤以為報名已結束或即將結束。
- **KEEP（第一輪做對、重新實作時保留）**：
  - S2 用 `routes/tournaments/$tournamentId/index.tsx`，不建立 layout route；分頁列做成 `TournamentTabs` 元件。
  - Countdown 歸零後由元件自己計時：立即呼叫一次 `onExpire`，之後每 5 秒一次，滿 2 分鐘停止並顯示提示；頁面以 `key`（含狀態與目標時間）在狀態改變後換掉 Countdown。
  - `appeal` 進度條起點用 `startsAt`，未傳時以截止前 24 小時為起點；報名截止倒數的變體以函式傳入，跨過 24 小時不需重抓就換成 `appeal`。
  - S2 用 `useQuery`：歸零後重抓失敗時保留畫面資料；404 與 id 格式錯誤（422）都顯示 404 頁。
  - 首頁換成 S1 後刪除 `tests/unit/home.test.tsx`；`auth-fixtures.ts` 的 `renderApp` 改為 mock 公開賽事列表；`auth.test.tsx` 只改等待條件（A 的測試檔，PR 說明要列出）。
  - 後端 `PublicTournament` 11 個欄位、`list_tournaments` 依開賽時間排序、公開路由無權限依賴。

## Review Triage Log

第一輪（2026-11-02）：Blind Hunter 13 筆、Edge Case Hunter 4 筆、Verification Gap 3 筆。因有 intent_gap，程式重新產生，下列 patch 項目改寫進〈Design Notes〉由重新實作一併處理。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind、Edge | 報名開始倒數下方寫「截止」 | medium：觀眾會誤解；根因在凍結區塊 | intent_gap（已由使用者決定） |
| 2 | Gap、Blind | id 格式錯誤（422）顯示 404 頁沒有前後端測試 | low：拿掉 422 判斷也不會有測試失敗 | 寫進 Design Notes |
| 3 | Gap、Blind | 歸零後重抓失敗保留畫面、S2 首次載入 500 與重新載入、頁面層級 2 分鐘逾時沒有測試 | low：Implementation Notes 宣稱的行為可能退化 | 寫進 Design Notes |
| 4 | Gap | `appeal` 進度條預設起點沒有測試 | low | 寫進 Design Notes |
| 5 | Edge | 同一個 Countdown 換了 `deadline` 後仍卡在「已截止」 | low：S2 以 `key` 換掉不會發生，但 4.6、5.8 會重用 | 寫進 Design Notes |
| 6 | Blind | S2 查詢自訂 `retry` 蓋掉全站 `shouldRetryQuery`，輪詢重抓又各自重試 | low：直接修正 | 寫進 Design Notes |
| 7 | Blind | S1 分組標題「進行中1」數字黏在一起 | low：螢幕閱讀器唸成一個詞 | 寫進 Design Notes |
| 8 | Blind | default 變體的 Page banner 用 `role="alert"` | low：每次進頁面被打斷式朗讀 | 寫進 Design Notes |
| 9 | Blind | S1 沒有頁面標題、S2 標題沒有賽事名稱 | low：直接修正 | 寫進 Design Notes |
| 10 | Blind | `TournamentTabs` 的 `to` 型別寫死，4.6 加分頁要改既有型別 | low：直接放寬型別 | 寫進 Design Notes |
| 11 | Blind、Edge | 公開列表沒有上限，回傳所有賽事 | low：期中賽事數量少 | defer |
| 12 | Edge | `STATUS_GROUP_ORDER` 沒有完整性檢查，新狀態的賽事會消失 | low：TypeScript 型別可涵蓋，新增狀態的機會低 | 不處理 |
| 13 | Blind | OpenAPI 沒有宣告 404 | low：既有 API 都是同樣寫法 | 不處理 |
| 14 | Blind | 刪掉首頁健康檢查後沒有替代說明 | false：README〈啟動〉已有 `curl .../health-check` | 不處理 |
| 15 | Blind | 開頁時已過期會立即多抓一次 | low：只多一次請求 | 不處理 |
| 16 | Blind | spec 與 sprint 狀態不一致、AI 使用紀錄缺 | false：在完成步驟處理 | 不處理 |
第二輪（2026-11-02）：Blind Hunter 12 筆、Edge Case Hunter 4 筆、Verification Gap 1 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 17 | Blind | 報名開始倒數歸零時寫「已截止 · 系統處理中」 | medium：與第一輪同樣的誤解；根因在凍結區塊 | intent_gap，使用者決定後當成小修正（不還原），patch |
| 18 | Blind、Edge | 換了 `deadline` 後第一次 render 用凍結的舊時間 | low：閃一次錯誤數字；直接修正 | patch |
| 19 | Blind | 歸零文字出現在新掛上的 `role="status"`，螢幕閱讀器可能不唸 | low：直接修正 | patch |
| 20 | Blind、Edge | `document.title` 離開 S2 後沒有還原，S1 或另一場 S2 可能留著舊名稱 | low：直接修正 | patch |
| 21 | Blind | `TournamentTab` 仍寫死；`TournamentTabPath` 會匹配 5.8 的場次路由，合併後 typecheck 可能壞 | medium：會壞在別人的 PR | patch |
| 22 | Gap | 公開 API 四個時間欄位的值沒有測試 | low：對調欄位也不會有測試失敗 | patch |
| 23 | Blind | `contracts/tournaments.md` 沒有補上 `PublicTournament` 與公開 API | low：直接補文件 | patch |
| 24 | Blind | Never 的「已正取隊數」「開放報名時啟用建立隊伍」沒有記進 `deferred-work.md` | low：跨組員待辦可能遺失 | defer |
| 25 | Blind | S2 漏了「優先期結束」倒數 | false：epics.md Story 2.4 寫明優先期結束倒數在 S27（主辦方），不在 S2 | 不處理 |
| 26 | Blind | 改了 A 的 `renderApp`、刪除 `home.test.tsx`、換掉 `routes/index.tsx` | low：首頁換成 S1 的必要連帶修改；在 PR 說明列出，請 A 確認 | 不處理（列入 PR 說明） |
| 27 | Blind | 剩幾天、幾小時時仍每秒重新 render | low：效能影響小 | 不處理 |
| 28 | Blind | 375 px 與 Manual checks 沒有紀錄 | false：實作代理已在瀏覽器以 375 px 檢查 S1、S2 三種狀態，`scrollWidth` 皆為 375 | 不處理 |

## Design Notes

重新實作時一併做到（第一輪審查的修正）：

- Countdown 的 `deadline` 改變時，重設「已截止」與 2 分鐘逾時的狀態。
- S2 查詢的 `retry`：`!isTournamentNotFound(e) && shouldRetryQuery(n, e)`（沿用 `lib/query-client.ts`）；倒數歸零後的輪詢重抓不重試。
- S1 分組標題的筆數與文字分開，可存取名稱為「進行中（1 場）」。
- Page banner：`destructive` 用 `role="alert"`，`default` 用 `role="status"`。
- 頁面標題：S1「賽事 · FLOW」，S2「{賽事名稱} · FLOW」。
- `TournamentTabs` 每個分頁的 `to` 型別放寬，之後的 Story 只要在 `TOURNAMENT_TABS` 新增項目。
- 測試另外涵蓋：前端 422 顯示 404 頁且不重試；後端 `GET /tournaments/not-a-uuid` 回 422；歸零後重抓失敗仍保留畫面；S2 首次載入 500 顯示錯誤與「重新載入」；頁面層級 2 分鐘逾時文字；未傳 `startsAt` 剩 12 小時時進度條寬度 50%；報名開始倒數下方為「{時間} 開放報名」。
## Verification

**Commands:**
- `docker compose up -d --build --wait` -- 五個服務 healthy
- `docker compose exec backend bash scripts/test.sh`、`docker compose exec backend bash scripts/lint.sh` -- 通過
- `docker compose exec frontend bun run --filter frontend build`、`docker compose exec frontend bun run --filter frontend typecheck`、`docker compose exec frontend bunx biome check`、`docker compose exec frontend bun run test:unit` -- 通過

**Manual checks:**
- 在瀏覽器開 S1、S2（含 375 px），未登入也能看到；建立「尚未開放」「開放報名」各一場賽事確認倒數與按鈕
