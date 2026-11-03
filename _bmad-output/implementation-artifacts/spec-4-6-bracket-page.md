---
title: 'Story 4.6（第二階段）：S3 對戰表頁接上真資料'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: 'a8580ea371df2c106c9f844399329f33bafdccf2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-6-bracket-tree-view.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段的對戰樹元件與輪詢 hook 只在 `/dev/bracket` 以假資料運作，觀眾在 S2 看不到對戰表。現在 D 的公開對戰表 API（#19）與 B 的 S2 分頁列、`Countdown`（#29）都已合併。

**Approach:** 新增 S3 路由 `/tournaments/$tournamentId/bracket`，在 S2 分頁列加上「對戰表」，以產生的 client 輪詢 `readPublicBracket`；尚未抽籤時顯示空狀態與報名截止倒數。改用 client 型別、刪除 `/dev/bracket` 與 `bracket-types.ts`，S4 返回連結改為 TanStack `Link`。

## Boundaries & Constraints

**Always:**
- S3 與 S2 共用標題列（`TournamentHeader`）、分頁列（`TournamentTabs`，`current="bracket"`）與 Page banner；同一頁最多一則 banner：賽事已取消（destructive）優先於連線中斷（default，文字同 `ConnectionLostBanner`）。
- 對戰表 404（`BRACKET_NOT_FOUND`）時拋 `BracketNotFoundError`，不算連線失敗、照常輪詢，抽籤後 5 秒內出現；賽事 404 或 id 格式錯誤時整頁顯示 404。
- 第一階段的版型、flash、捲動與連線中斷行為不變；`frontend/src/client/`、`routeTree.gen.ts` 只用工具產生。

**Never:**
- 不改後端；不修改 B 的 `TournamentPage`、`TournamentOverview` 既有函式（只在 `TournamentTabs` 的 `TOURNAMENT_TABS` 加一項，這是它預留的擴充點）。
- 不做隊伍搜尋、晉級路徑（4.7）、Podium（Epic 5）；不動 S4 的資料來源（5.8 第二階段，等 D 的 #21）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已抽籤 | API 回 `PublicBracket` | 對戰樹；整張卡連到該場 S4 | N/A |
| 尚未開放／開放報名 | 對戰表 404 | `BracketPending`＋`Countdown`「報名截止」（variant 用 B 的 `registrationEndVariant`）；倒數歸零後重抓賽事 | N/A |
| 報名截止、未抽籤 | 對戰表 404，`closed` | `BracketPending`＋「抽籤準備中」，不顯示倒數 | N/A |
| 已取消、未抽籤 | 對戰表 404，`cancelled`（或 `published`／`ongoing`／`finished` 的資料不一致） | destructive banner（只限已取消）＋空狀態「這場賽事沒有對戰表。」，不顯示倒數 | N/A |
| 賽事不存在 | 賽事 API 404／422 | 404 頁 | 不重試 |
| 第一次載入失敗 | 對戰表非 404 錯誤、沒有舊資料 | 連線中斷 banner＋重試中 | 每 5 秒重試 |

## Decisions（2026-11-03 定案）

- **預設分頁不做**（使用者選 1A）：`/tournaments/$id` 仍固定是總覽，觀眾自己點「對戰表」；「賽程已公布、進行中時預設對戰表」寫進 `deferred-work.md`，由 B 決定做法（總覽改網址再導向，或 S1 直接連 `/bracket`）。
- **場次卡現在就連到 S4**（使用者選 2A）：在 D 的 #21 與 5.8 第二階段接上真資料前，點進去會是 404。
- **分支 `story/4-6-bracket-page`**（使用者選 3A），從最新 `main` 開出。
- **保留完整 spec**（使用者決定），不拆分。
- **沒有對戰表的已取消賽事**（2026-11-03 審查後使用者決定）：不沿用「報名截止後抽籤…」，改寫「這場賽事沒有對戰表。」；`published`／`ongoing`／`finished` 卻沒有對戰表時同一句。

</frozen-after-approval>

## Code Map

- `frontend/src/client/sdk.gen.ts:868` -- `CompetitionService.readPublicBracket({ path: { tournament_id } })`；型別 `PublicBracket`、`PublicMatch`、`MatchStatus`、`MatchOutcome`、`PublicTeamRef` 與 `bracket-types.ts` 欄位完全相同。
- `backend/app/modules/competition/router.py:26` -- 尚未抽籤（含賽事不存在）回 404 `BRACKET_NOT_FOUND`。
- `frontend/src/features/tournaments/` -- B 的模組：`TournamentPage.tsx`（S2；`TournamentHeader` 已匯出，`useTournamentTitle`、`PageSkeleton` 未匯出）、`TournamentTabs.tsx`（`TOURNAMENT_TABS`）、`queries.ts`（`publicTournamentQueryOptions`、`isTournamentNotFound`）、`TournamentOverview.tsx`（`registrationEndVariant`、倒數歸零重抓的寫法）。
- `frontend/src/components/common/` -- `Countdown.tsx`（`label`、`deadline`、`variant`、`onExpire`）、`PageBanner.tsx`（`PageBannerSlot`）。
- `frontend/src/features/competition/` -- `use-bracket-polling.ts`（`BracketNotFoundError`、`notFound`、`error`）、`BracketTree.tsx`（`matchHref`）、`BracketPending.tsx`（`countdown` 插槽）、`ConnectionLostBanner.tsx`（`formatClockWithSeconds`）、`match-source.ts`（`matchPath`）、`MatchHeader.tsx`（`bracketPath`、一般 `<a>`）。
- `bracket-types.ts` 的使用者：`BracketMatchCard`、`BracketTree`、`bracket-layout`、`bracket-fixtures`、`match-status`、`match-types`、`match-fixtures`、`MatchAppealWindow`、`MatchGameList`、`MatchScoreDisplay`、`SameRoundMatches`、`use-bracket-polling` 與 7 個測試檔。`BracketSide` 不在 client，移到 `match-status.ts`。
- `frontend/tests/unit/tournament-pages.test.tsx`、`render-router.tsx` -- 以 `vi.spyOn(TournamentsService, ...)` mock client、渲染整個路由的寫法。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/bracket-queries.ts` -- `fetchPublicBracket(tournamentId)`：呼叫 client，404 時拋 `BracketNotFoundError`。
- [x] `frontend/src/features/competition/TournamentBracketPage.tsx` -- S3：賽事查詢、標題列、banner、分頁列、對戰樹或尚未抽籤的內容（依 I/O 矩陣）；頁面標題「{賽事名稱} · FLOW」。
- [x] `frontend/src/routes/tournaments/$tournamentId/bracket.tsx` -- S3 路由。
- [x] `frontend/src/features/tournaments/TournamentTabs.tsx` -- `TOURNAMENT_TABS` 加 `{ value: "bracket", label: "對戰表", to: "/tournaments/$tournamentId/bracket" }`。
- [x] `frontend/src/features/competition/*`、`frontend/tests/unit/*` -- 型別改從 `@/client` 匯入，`BracketSide` 移到 `match-status.ts`，刪除 `bracket-types.ts`。
- [x] `frontend/src/routes/dev/bracket.tsx` -- 刪除；更新 `bracket-fixtures.ts`、`match-source.ts` 提到它的註解。
- [x] `frontend/src/features/competition/MatchHeader.tsx` -- 返回連結改用 `Link to="/tournaments/$tournamentId/bracket"`，刪除 `bracketPath`。
- [x] `frontend/src/routeTree.gen.ts` -- 重新產生。
- [x] `frontend/tests/unit/tournament-bracket-page.test.tsx` -- I/O 矩陣各列、分頁列兩個分頁、404 不顯示連線中斷、取消 banner 優先。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 新增一項：S2 在賽程已公布、進行中時預設對戰表分頁（Decisions 1A）。
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 1.7、1.8 改為 `done`（#10、#11 已合併）。`deferred-work.md` 的 5.8 項目第 (4) 點由本 Story 完成，但依規則不改既有項目，整項等 5.8 第二階段完成才刪。

**Acceptance Criteria:**
- Given 已抽籤的賽事，when 未登入觀眾在 S2 點「對戰表」，then 網址為 `/tournaments/{id}/bracket`、分頁「對戰表」為選取狀態、顯示對戰樹，之後每 5 秒輪詢。
- Given S4，when 點返回連結，then 回到該賽事的 S3。
- Given 前端，when 執行 Verification 的指令，then 全部通過，且 `/dev/bracket` 不再存在。

## Implementation Notes

- **S3 不改 B 的 S2 元件**：`TournamentBracketPage` 只匯入 B 已匯出的 `TournamentHeader`、`CANCELLED_BANNER_TEXT`、`TournamentTabs`、`publicTournamentQueryOptions`、`isTournamentNotFound`、`DRAW_PENDING_TEXT`、`registrationEndVariant`；`useTournamentTitle`、頁面骨架、錯誤畫面沒有匯出，在 S3 另寫一份（行為相同）。對 B 的檔案只有 `TournamentTabs.tsx` 的 `TOURNAMENT_TABS` 多一項。
- **連線中斷改走 `PageBannerSlot`**：S3 同時可能有取消 banner，所以不用 `ConnectionLostBanner` 元件，改由新匯出的 `connectionLostText()` 產生文字交給 `PageBannerSlot`，取消（destructive）優先、同頁只有一則。`ConnectionLostBanner` 本身改用同一個函式，S4 不受影響。
- **第一次載入就失敗**（非 404）時沒有舊畫面可保留，比照 S4 直接顯示連線中斷，不等連續 3 次。
- **`BracketSide` 移到 `match-status.ts`**：client 沒有這個型別；其他型別都從 `@/client` 匯入，欄位與原本的 `bracket-types.ts` 完全相同。
- **測試改用 router context**：`MatchHeader` 的返回連結改成 `Link` 後，`match-header`、`use-match-polling` 兩個測試要有 router；`render-router.tsx` 新增 `renderWithRouterContext()`（支援同步 `rerender`）。
- **環境**：雲端 session 的 Docker Hub 拉映像回 429，`/etc/docker/daemon.json` 改用 `mirror.gcr.io` 鏡像（只影響這個容器，不進版控）。`routeTree.gen.ts` 以本機 `bunx vite build` 產生；前端檢查先在本機以 Bun 跑過。

## Spec Change Log

## Review Triage Log

**2026-11-03 第一輪（Blind Hunter、Edge Case Hunter、Verification Gap）**

- [medium，已修正] 尚未抽籤時一次暫時失敗就顯示連線中斷並把空狀態換成骨架（EC、VG）：`useBracketPolling` 收到 404 後改記住「尚未抽籤」直到拿到資料，中間的失敗只累計連續次數；hook 測試「404 之後的連線失敗從 0 開始算」的預期跟著改（`notFound` 維持 true、`error` 為 null），S3 加頁面測試。
- [medium，已修正] 從 S3 點進 S4 時，S3 的標題還原蓋掉 S4 的標題（EC）：暫時測試重現 S4 標題變成「對戰表 · FLOW」；還原前先確認標題仍是自己設的，加測試。
- [medium，已修正] 換賽事時 `keepPreviousData` 把上一場的對戰樹顯示在新賽事底下、卡片連結混用兩場的 id（BH、EC）：S3 路由以 `tournamentId` 當 key。
- [low，已修正] 賽事查詢只在載入與倒數歸零時抓，抽籤後標題列仍顯示「報名截止」（BH）：對戰表的 `updated_at` 一變就讓賽事查詢失效重抓（首次載入也會多抓一次）。觀眾停在尚未抽籤頁面時主辦方取消賽事，仍要等對戰表變動或重新整理才會出現取消 banner，與 S2 相同。
- [low，已修正] 所有 404 都當成「尚未抽籤」（BH）：改用 `parseApiError` 只認 `BRACKET_NOT_FOUND`，加測試。
- [medium，已修正] 缺測試（VG、BH）：已載入後連續失敗 3 次的 banner 與最後更新時間、倒數歸零重抓賽事、賽事 500 的「重新載入」、422、404 轉為有資料；「已取消又連線失敗」改為等失敗處理完才斷言。反向驗證：拿掉 `connectionLost ||`、拿掉重抓、拿掉標題檢查，各有測試失敗。
- [low，已修正] `MatchGameList`、`match-fixtures` 對 `./match-status` import 兩次（BH）：合併。
- [low，駁回] 已取消且沒有對戰表時仍每 5 秒輪詢 404（BH）：只多一個公開請求，修正要為 hook 加條件；取消後才抽籤的情況也要能抓到對戰表。
- [false] sprint-status 的 4-6 仍是 `in-progress`（BH）：step-05 收尾時同步。
- [low，駁回] S3 複製了 S2 的標題、骨架、錯誤畫面（BH）：frozen 的 Never 不修改 B 的 `TournamentPage`，共用要改它；已記在 Implementation Notes，PR 說明列出。
- [false] `upcoming` 時 S3 倒數報名截止、S2 倒數報名開始（BH）：符合 frozen I/O 矩陣與 epics 4.6 AC「報名截止倒數」。
- [false] 缺 AI 使用紀錄與容器內驗證（BH）：AI 紀錄在收尾時新增；容器建置受網路政策限制，已在 Implementation Notes 說明。
- [intent_gap，已由使用者決定] 已取消、已結束等狀態沒有對戰表時仍寫「報名截止後抽籤，對戰表會出現在這裡。」（BH、EC）：使用者決定改寫「這場賽事沒有對戰表。」，已更新 Decisions 與 I/O 矩陣並加測試。改動只在 `BracketNotDrawn` 的 default 分支，沒有照流程回退全部程式碼重做。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 服務 running／healthy。
- `docker compose exec frontend bun run --filter frontend build`、`typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過。

**Manual checks (if no CLI):**
- 375px 與 1280px 開 S3：只有對戰樹容器橫向捲動；切換「總覽」「對戰表」分頁。
