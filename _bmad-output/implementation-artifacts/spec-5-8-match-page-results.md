---
title: 'Story 5.8（第一階段）：場次頁觀眾檢視元件'
type: 'feature'
created: '2026-10-30'
status: 'done'
baseline_commit: '25b3effcbc9c10a346bb97f5c0dd194e804d798b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-6-bracket-tree-view.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 觀眾要在 S4 場次頁看到每局比分、系列比分、狀態和同輪其他場次，也要能從對戰樹的場次卡點進 S4。現在做不到，原因有兩個：

- 上游還沒合併：公開的單場 API（含各局、遊戲名、BO、比分型態）在 contract 裡沒有定義，D 的 5.1、5.5 也都還沒合併。
- S4 路由還不存在。

對戰樹場次卡的結果標示在 4.6 已經做完，包括「只有已確認才套用勝負樣式」和「棄權」「—＋輪空」的標示。

**Approach:** 照使用者的決定，相依的 Story 還沒做的部分先用假資料，把 5.8 完整做出來，範圍如下：

- S4 路由 `/tournaments/$tournamentId/matches/$matchId`，提供觀眾檢視。
- 元件：Match header、Score display、各局列表、同輪其他場次。
- 單場輪詢。
- 對戰樹場次卡整張可以點，點了進入 S4。

所有資料都經過同一個資料來源函式取得。這個函式目前回傳由對戰樹假資料推導出的場次；等 API 合併後，只要把它換成呼叫產生的 client。

## Boundaries & Constraints

**Always:**

- **Match header**：不放在 Card 裡，共三行。
  - 第一行是「← {賽事名稱}」，`body`、`muted-foreground`，連到 S3 `/tournaments/$tournamentId/bracket`。
  - 第二行是「{輪次} · {code}」，例如「32 強 · M3」「決賽 · M31」；季軍賽只寫「季軍賽」。字級 `heading-lg`，後面接 Status badge。
  - 第三行是「{遊戲} · BO{局數} · {formatMatchDateTime(預定時間)}」，`caption`。
- **Status badge**：

  | 狀態 | 文字 | tone |
  |---|---|---|
  | 待開打 | 待開打 | `muted` |
  | 進行中 | 進行中 | `live`＋脈動點 |
  | 申訴期 | 申訴期 | `appeal` |
  | 申訴中 | 申訴中 | `appeal`＋脈動點 |
  | 已確認 | 已確認 | `confirmed` |
  | 已取消 | 已取消 | `muted` |

  「申訴中」要到 6.1 才會出現，期中不會出現，但對照表照寫。這份對照和 `BracketMatchCard` 共用同一個來源。
- **Score display**：放在 Card 裡，格式為「隊A 2 : 1 隊B」。比分用 `score` 字級，冒號用 `muted-foreground`，只計已登錄的局。
- **各局列表**：放在 Card 裡。
  - 表頭是「局」＋兩隊隊名，`overline`、`muted-foreground`。
  - 每局一列，列首寫「第 N 局」。
  - `rounds` 型態顯示「13 : 11」，等寬數字；該局勝方用 `foreground`，敗方用 `status-eliminated`。
  - 沒有已登錄的局時，整個 Card 不顯示。
- **同輪其他場次**：放在 Card 裡，標題「同輪其他場次」。
  - 每場一個連結：等寬的 `code`（季軍賽寫「季軍賽」）＋Status badge，`flex-wrap`。點擊進入該場的 S4。
  - 季軍賽和決賽互相列出。
  - 同輪沒有其他場次時，整塊不顯示。
- **版面**：
  - `≥ lg`：兩欄，左欄 `minmax(0,1fr)`、右欄 400px，欄距 20px。左欄依序是 Score display、各局列表；右欄最下方是同輪其他場次。
  - `< lg`：單欄，依序為頁首、Score display、各局列表、同輪其他場次。
  - 375px 寬時頁面沒有橫向捲軸。
- **輪詢**：
  - 每 5 秒一次；背景分頁暫停，回到前景時立即重抓。
  - 重抓時保留舊資料、不顯示 loading。比分或狀態有變動時，Score display `update-flash` 一次。
  - 連續失敗 3 次時，顯示 4.6 的 `ConnectionLostBanner`。
  - 找不到場次時顯示 `NotFoundPage`。
- **對戰樹場次卡**：整張可點，點了進入該場的 S4。可以用鍵盤操作，focus 時有可見的外框。
- 介面文字全部繁體中文。

**Never:**
- 不寫後端，不修改 D 的檔案。元件不呼叫 API，只有資料來源函式取得資料。
- 不做 Check-in panel、Score entry panel、申訴、倒數、結算截圖（D、Epic 2、Epic 6、5.7）。
- 不做 S3 路由與 S2 分頁（4.6 第二階段，依賴 B 的 S2）。
- 不修改 `docs/`（`docs/ai-usage/` 除外）。

## Decisions（使用者 2026-10-30 定案）

- **完整做 5.8，相依的部分先用假資料**：建立正式的 S4 路由，以及卡片連到 S4 的連結。
  - 資料來源函式目前回傳假資料，只在 `import.meta.env.DEV` 時提供；正式 build 時 S4 顯示 `NotFoundPage`。正式 build 不該出現假的比分，等 API 合併後才開放。
  - 換成真資料的範圍寫進 `deferred-work.md`：
    - 請 D 在 contract 補上公開的單場 API，形狀見 `match-types.ts`。
    - 後端測試要確認段位截圖不出現在任何公開 API（AD-19）。
    - 把資料來源換成產生的 client。
    - S3 路由完成後，返回連結就能用。
- **申訴期不套用勝敗樣式**：只有已確認才套用勝方粗體、敗方 `status-eliminated`，和場次卡一致，申訴期不暗示晉級。
- **沒有比分的情況**：包括待開打、棄權、雙方棄權、輪空、取消資格、已取消。兩隊隊名照常排列，中間顯示 muted 的「—」，隊名旁沿用 4.6 的標記（棄權、輪空、取消資格）。隊伍未定時，顯示 `source_*`（muted）。
- **`win_loss` 型態的各局**：兩隊欄寫「勝」「負」，樣式和 `rounds` 的勝敗相同。
- **保留完整 spec**（約 3,000 tokens），沿用 4.6 的做法。
- **不做 code review**：沿用使用者「最後統一 review」的決定。
- **分支從 `story/4-6` 開出**：要用 4.6 的元件、型別、`match-time.ts` 與輪詢設定，所以 PR 依賴 4.6 的 PR。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已確認、正常完賽 | `confirmed`、`played`、2:1 | 「隊A 2 : 1 隊B」，A 粗體，B `status-eliminated`；徽章「已確認」 | N/A |
| 進行中 | `live`、1:0、已登錄 1 局 | 比分 1 : 0，不套勝敗樣式；徽章「進行中」脈動；各局 1 列 | N/A |
| 申訴期 | `appeal_window`、2:0 | 顯示比分，不套勝敗樣式；徽章「申訴期」 | N/A |
| 待開打 | `scheduled`、隊伍已定、沒有局 | 兩隊隊名＋「—」；徽章「待開打」；不顯示各局 Card | N/A |
| 隊伍未定 | `scheduled`、team_b 為 null | B 側顯示「M4 勝者」（muted） | N/A |
| 一方棄權 | `confirmed`、`forfeit`、B 棄權 | 「—」；B 帶「棄權」並套淘汰樣式，A 套勝方樣式 | N/A |
| 雙方棄權 | `appeal_window`、`double_forfeit` | 「—」；兩隊都帶「棄權」，不套樣式 | N/A |
| win_loss 各局 | 第 1 局 A 勝 | A 欄「勝」（foreground），B 欄「負」（`status-eliminated`） | N/A |
| 季軍賽 | `is_third_place` | 標題「季軍賽」；同輪列出決賽 | N/A |
| 同輪只有自己 | 決賽、沒有季軍賽 | 不顯示同輪 Card | N/A |
| 同輪 4 場 | 8 強 M25 | 列出 M26、M27、M28，不含自己 | N/A |
| 點場次卡 | 對戰樹上點 M3 | 進入 `/tournaments/{id}/matches/{M3 的 id}` | N/A |
| 輪詢有變動 | 比分 1:0 → 2:0 | 更新比分，Score display flash 一次 | N/A |
| 輪詢失敗 | 連續失敗 3 次 | 保留舊畫面，顯示連線中斷 banner | 成功一次就消失 |
| 找不到場次 | 不存在的 matchId | `NotFoundPage` | N/A |
| 正式 build | `import.meta.env.DEV` 為 false | S4 顯示 `NotFoundPage`，不出現假資料 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/BracketMatchCard.tsx:14-43`：裡面的 `STATUS_BADGES`、`THIRD_PLACE_LABEL`、`UNSCORED_OUTCOMES`、`SCORED_STATUSES` 沒有匯出。要抽到新檔 `match-status.ts` 並匯出，再加上「待開打」（`muted`）。`BracketMatchCard` 改從新檔 import，行為不變，4.6 的測試要全部通過。
- `frontend/src/features/competition/bracket-types.ts`：`PublicMatch`、`MatchStatus`、`MatchOutcome`、`BracketSide`。本 Story 在新檔 `match-types.ts` 定義 `PublicMatchDetail`，作為第二階段要請 D 補進 contract 的提議形狀：
  - 繼承 `PublicMatch`
  - `tournament: {id, name}`、`game_name`、`best_of`、`score_type: "win_loss" | "rounds"`、`round_name`
  - `games: {game_no, winner_side: BracketSide, score_a: number | null, score_b: number | null}[]`
  - `same_round: PublicMatch[]`（不含自己）
  - `updated_at`
- `frontend/src/features/competition/use-bracket-polling.ts`：裡面有 `BRACKET_POLL_INTERVAL_MS`、`BRACKET_CONNECTION_LOST_AFTER`，以及用 `errorUpdateCount` 算失敗次數的做法。新增的 `use-match-polling.ts` 照同樣的設定寫；共用的部分可以抽成內部 helper，但不能改變 `useBracketPolling` 的行為。
- `frontend/src/features/competition/{BracketMarkTag,ConnectionLostBanner}.tsx`、`match-time.ts`（`formatMatchDateTime`）、`components/common/StatusBadge.tsx`（`tone`、`pulse`）：直接沿用。`match-time.ts` 不能修改，它要和 D 的版本保持相同。
- `frontend/src/features/competition/bracket-fixtures.ts`、`routes/dev/bracket.tsx`：假資料與預覽頁的寫法參考。新增 `match-fixtures.ts` 和 `routes/dev/match.tsx`；`import.meta.env.DEV` 為 false 時顯示 404。產生 `routeTree.gen.ts` 的方法見 CLAUDE.md。
- `frontend/src/index.css`：`--text-score`、`--text-heading-lg`、`status-*` token。如果缺 `match-aside-width`／`match-column-gap` 的 spacing token，就新增。
- UX 依據：`ux-designs/ux-se-final-project-2026-10-14/`
  - `DESIGN.md`：:130-134、:166-167、:427-437、:483-495
  - `EXPERIENCE.md`：:179-186、:226-230、:268-284、:450-463
  - `mockups/key-s4-match.html`：手機觀眾畫面
  - 示意圖 (c) 的區塊順序已經過時，以文件為準。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/match-status.ts`：抽出狀態徽章對照（另加「待開打」）、`THIRD_PLACE_LABEL`、沒有比分的狀態與結果集合。`BracketMatchCard.tsx` 改為 import 這個檔案，原本的行為不變。
- [x] `frontend/src/features/competition/BracketMatchCard.tsx`、`BracketTree.tsx`：加上選用的 `matchHref(matchId)`。有提供時整張卡變成 TanStack `Link`，可用鍵盤操作，focus 時有外框；沒有提供時維持原本的樣子。
- [x] `frontend/src/features/competition/match-types.ts`：`PublicMatchDetail` 等型別。檔頭註明第二階段改用產生的 client 後刪除。
- [x] `frontend/src/features/competition/match-fixtures.ts`：從 `createBracketFixture` 的對戰樹推導每一場的 `PublicMatchDetail`。
  - 各局由 `wins_a`／`wins_b` 產生，局序固定。
  - 同輪場次取自同一份對戰樹。
  - 比分型態依場次交替，讓兩種都看得到。
  - 遊戲固定「特戰英豪」，BO 固定 3。
- [x] `frontend/src/features/competition/match-source.ts`：`fetchMatchDetail({tournamentId, matchId})`。
  - DEV 時從一份固定的 32 隊「進行中」假對戰樹取資料。
  - 找不到場次，或不是 DEV 時，拋出 `MatchNotFoundError`。
  - 檔頭註明第二階段換成產生的 client。
- [x] `frontend/src/features/competition/use-match-polling.ts`：設定和 `useBracketPolling` 相同。回傳 `{detail, connectionLost, lastUpdatedAt, isLoading, notFound, changed}`，其中 `changed` 表示比分或狀態有變動，用來觸發 flash。
- [x] `frontend/src/features/competition/MatchHeader.tsx`、`MatchScoreDisplay.tsx`、`MatchGameList.tsx`、`SameRoundMatches.tsx`、`MatchSpectatorView.tsx`：四個區塊，加上組合版面的元件。
- [x] `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx`：S4 路由，用 `useMatchPolling`＋`fetchMatchDetail`，`head` 標題是「{標題} · {賽事名稱} · FLOW」。
- [x] `frontend/src/routes/dev/bracket.tsx`：傳入 `matchHref`，讓預覽頁的卡片連到 S4（假資料的 tournament id 與 match id 和 `match-source` 一致）。
- [x] `frontend/src/routeTree.gen.ts`：重新產生。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`：新增一項，寫明換成真資料的範圍（見 Decisions）。
- [x] `frontend/tests/unit/{match-status,match-score-display,match-game-list,same-round-matches,match-header,use-match-polling,match-source}.test.ts(x)`，以及 `bracket-match-card.test.tsx` 補上連結：I/O 矩陣每一列都要有測試，4.6 的既有測試全部通過。

**Acceptance Criteria:**
- Given DEV 模式的 `/dev/bracket`，when 點任一張場次卡，then 進入該場的 S4，看到標題、比分、各局與同輪場次；點同輪場次可以切到另一場。
- Given S4，when 寬度是 1280px，then 兩欄、右欄 400px；when 寬度是 375px，then 單欄，順序為頁首、比分、各局、同輪，而且沒有橫向捲軸。
- Given 正式 build，when 開啟任何 S4 網址，then 顯示 404，bundle 不含假資料。
- Given 前端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- **勝敗樣式的共用**：除了徽章對照與集合，`BracketMatchCard` 的隊伍列邏輯（名稱、輪空／棄權／取消資格標記、只在已確認套勝敗）也抽成 `match-status.ts` 的 `sideView()`，場次卡與 Score display 共用；場次卡只多加比分欄，4.6 的測試全部照舊通過。
- **各局的勝敗顏色不受「申訴期不套樣式」限制**：Decisions 的限制針對系列勝負（暗示晉級）；每一局的結果在登錄時就確定，所以各局列表一律用 `foreground`／`status-eliminated`，與 `mockups/key-s4-match.html` (c)（申訴期）一致。`win_loss` 的中間欄留空，不寫「:」。
- **Score display 的敗方比分數字**也用 `status-eliminated`（mockup `.score .l`），一樣只在已確認時套用；名稱不加刪除線（DESIGN.md 只有場次卡寫刪除線）。
- **場次卡連結**：有 `matchHref` 時外層是 TanStack `Link`（`group`、`focus-visible:outline-2`），連結自己帶 `aria-label`（`matchCardAccessibleName()`，見 Review Triage Log），裡面的 article 不再帶 `aria-label`；定位用的 `className`／`style` 移到連結上。typecheck 接受 `to` 為一般字串。
- **返回連結用一般 `<a>`**：S3 路由不存在，TanStack `Link` 只接受已註冊的路由；S3 完成後改為 `Link`（已寫進 deferred-work）。
- **頁面標題**：輪詢不經過 router，所以路由另有 `loader` 呼叫一次 `fetchMatchDetail`，只回傳標題給 `head`；找不到或失敗時標題是「FLOW」。
- **換場次時重新掛載**：S4 以 `tournamentId/matchId` 當 key，點同輪其他場次時不沿用上一場的資料（`keepPreviousData`）與 flash 狀態。
- **找不到場次就停止定時重抓**：`useMatchPolling` 的 `refetchInterval` 在「沒有資料且錯誤是 `MatchNotFoundError`」時回 `false`；其餘設定與 `useBracketPolling` 相同。連續失敗次數的計算抽成 `use-consecutive-failures.ts`，兩個 hook 共用，`useBracketPolling` 的測試照舊通過。另外多回傳 `error`（第一次載入就失敗且不是 404）。
- **flash 重播**：`changed` 在下一份資料出現前維持不變；`MatchSpectatorView` 以每份資料的序號當 Score display 的 key，連續兩次變動都會重播動畫。
- **正式 build**：`match-source.ts` 只在 `if (import.meta.env.DEV)` 分支內動態 import 假資料；`/dev/match` 的假對戰樹在元件內才建立。實測 `dist/assets` 沒有「Titan」「特戰英豪」「tournament-fixture」，`/dev/match` 的 chunk 只有 271 bytes。
- **`/dev/bracket` 只有 32 隊「進行中」時卡片可點**：S4 的假資料固定是這一份對戰樹，其他設定的同一個 match id 內容不同，連過去會對不上。
- **`/dev/match` 預覽頁**：可選 11 種代表場次（含找不到場次），「模擬變動」（進行中多登錄一局、待開打改為進行中）、「模擬斷線」。
- **測試**：`render-router.tsx` 新增 `renderInRouter()`（只有根路由的 router，讓元件內的 `Link` 有 href）；另外加了 `match-route.test.tsx`，用真的路由樹測 S4 的標題、同輪切換、404 與正式 build。

- **主對話驗證（2026-10-30，重建 frontend 後重跑）**：前端 build、typecheck、biome（154 個檔案）都通過；單元測試 37 個檔案、354 個通過（新增 76 個）；`dist/assets` 53 個檔案都不含假資料字串；後端 310 passed（本 Story 沒有改後端）；改動的檔案都是 LF。依使用者的決定，沒有跑 code review。
- **sprint-status 維持 `in-progress`**：換成真資料（`deferred-work.md` 列的四件事）完成後才改成 `review`。
- **實作途中 Docker Desktop 停止**：容器以 exit 255 結束。重新啟動 Docker Desktop 並執行 `docker compose up -d --build --wait` 後恢復，與程式無關。

## Spec Change Log

## Review Triage Log

**2026-10-31 D 審查（`story/4-6...story/5-8`）**

- [已修正，擋合併] 場次卡連結的可及名稱只剩「M3」。原本的 Implementation Notes 以為連結會讀到 article 的內容，但 accname 規則下 article 的 `aria-label` 會取代內容；測試用 `toHaveTextContent` 檢查，抓不到。
  - 修正：`BracketMatchCard.tsx` 新增 `matchCardAccessibleName()`，連結帶 `aria-label`，包成連結時 article 不帶 `aria-label`。
  - 名稱格式（AI 依 D 的範例與畫面內容訂的預設，使用者未另外指定）：`{M3 或 季軍賽}，{待開打時的時間}，{A 隊名（標記）} 對 {B 隊名（標記）}，{有比分時的「2 比 1」}，{狀態}`，例如「M3，清大 Hydra 對 交大 Nova，2 比 1，已確認」。
  - 測試改用 `toHaveAccessibleName(...)`，補上已確認、季軍賽＋棄權兩種名稱。
- [已修正，隨 4.6 合併] 已確認 walkover 的空缺方顯示「M5 敗者」：4.6 依 D 的審查改成 `bye_a`／`bye_b` 並加上 walkover 空缺方的保險。2026-10-31 把 `story/4-6` 合併進來時，改套用在共用的 `match-status.ts` `sideView()`，場次卡與 Score display 都適用；`deferred-work.md` 的對應項目已刪除。
- [已修正] S4 第一次載入就失敗（不是 404）時停在 Skeleton，要連續失敗 3 次才出現橫幅：路由在 `connectionLost` 或 `error` 有值時就顯示 `ConnectionLostBanner`，Skeleton 保留、輪詢照常重試。新增 `match-route-error.test.tsx`。
- [已修正] `isMatchScoreChanged` 只比狀態與系列勝場：加比 `outcome`、`winner_id` 與各局（`game_no`、`winner_side`、`score_a/b`），6.x 更正結果時也會 flash。`use-match-polling.test.tsx` 補兩個案例。
- [PR 說明] 這個分支帶了 5.2 的 commit `03a09c1`（`MatchAppealWindow`），開 PR 時在說明註明。
- [不需處理] `PublicMatchDetail` 的提議形狀與 `scoring.py` 一致，D 會在 5.x 第二階段補進約定。
- 驗證（重建容器後）：單元測試 39 個檔案、371 個通過（新增 4 個測試、1 個檔案）；typecheck、biome（157 個檔案）通過；改動的檔案都是 LF。

## Verification

**Commands:**
- `docker compose up -d --build --wait`：五個服務都是 running／healthy。
- `docker compose exec frontend bun run --filter frontend build`：成功。
- `docker compose exec frontend bun run --filter frontend typecheck`：沒有錯誤。
- `docker compose exec frontend bunx biome check`：沒有錯誤。
- `docker compose exec frontend bun run test:unit`：全部通過。
