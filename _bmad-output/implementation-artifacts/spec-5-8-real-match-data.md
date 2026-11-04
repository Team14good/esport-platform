---
title: 'Story 5.8 第二階段：S4 接上真資料、報到與比分登錄面板；修前端單元測試偶發逾時'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '70ef72360a2164c2902f1feef3490fa64a33f7d6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-8-match-page-results.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** S4 場次頁只在開發模式顯示假資料，正式 build 一律 404；隊長不能在 S4 報到，裁判（或代登的主辦方）不能在 S4 登錄比分。上游 API（#21 公開單場、#22 報到、#25 比分、#43 申訴開始時間）都已合併。另外前端單元測試在機器忙碌時偶發失敗（deferred-work 點名 A 的 `admin-applications`、`login`、`identity-switcher`、`organizer-apply` 與冷啟動逾時）。

**Approach:** `fetchMatchDetail` 改呼叫產生的 client，移除開發模式假資料；S4 右欄放 D 的 `CheckInPanel`，記分者在左欄看到 D 的 `ScoreEntryPanel`（取代公開各局列表）。偶發失敗的根因是逾時太緊：閒置時已有 57 個測試超過 1 秒、最慢 3.7 秒，`findBy*` 預設只等 1 秒、Vitest 每個測試 5 秒；同時跑 3 份測試即可重現 47～53 個失敗。改放寬全域逾時，不改任何測試的斷言。使用者 2026-11-04 決定兩件事一起做。

## Boundaries & Constraints

**Always:**
- 資料一律經產生的 client（`CompetitionService`），型別改用 `@/client` 的 `PublicMatchDetail`、`PublicGame`；API 404 拋 `MatchNotFoundError`。
- 報到面板：所有人都看得到兩隊報到狀態（`check_in_a_at`／`check_in_b_at`）；只有登入者才呼叫 `readCheckInStatus` 取得 `side`、`reason`、`opens_at`。未登入不呼叫任何需登入的 API。
- 報到倒數依 EXPERIENCE.md〈倒數與時間〉：開放前「報到開放」→ `opens_at`（`muted`）；開放後「距預定開始」→ `scheduled_at`（`live`）；過預定時間「棄權期限」→ `forfeit_deadline`（`appeal`）。兩隊未確定時不顯示倒數。
- 比分面板只在 `readScoreEntry` 回 `is_scorer: true` 時顯示，此時左欄不顯示 `MatchGameList`。寫入錯誤碼轉成面板的小寫代碼：`SCORE_TIE`→`tie`、`SCORE_INVALID`→`invalid_score`、`SERIES_DECIDED`→`series_decided`、`REDUNDANT_GAMES`→`redundant_games`、`INVALID_GAME_NO`→`invalid_game_no`、`NOT_LAST_GAME`→`not_last_game`、`SERIES_NOT_DECIDED`→`not_decided`；其他錯誤先 `notifyError` 再 reject。
- 寫入成功後重抓場次與面板狀態再 resolve（兩個面板的 callback 約定）。
- `MatchHeader` 的返回連結改成 TanStack `Link`。
- 測試逾時：`asyncUtilTimeout` 與 `testTimeout` 在全域設定放寬，不改個別測試、不跳過測試。

**Never:**
- 不改後端、不改 D 的 `CheckInPanel.tsx`、`ScoreEntryPanel.tsx` 與其測試，不改 `match-time.ts`。
- 不做提出申訴（6.1）、結算截圖（5.7）、裁判指派（4.4）。
- 不改別人的測試檔內容。

## Decisions（使用者 2026-11-04 定案）

- **兩件事一起做**：5.8 第二階段與修偶發失敗的測試放在同一個分支、同一個 PR。
- **觀眾 e2e 的 S4 測試改成 `test.fixme`**：`tests/e2e/spectator.spec.ts` 開假資料場次的測試改為 `test.fixme`，寫明等 7.1 示範資料有已抽籤的賽事再接上；記入 `deferred-work.md`（7.2）。開發模式假資料照第一階段的決定完全移除。
- **不做 code review**：沿用「最後統一 review」的決定，跳過 step-04。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 正式 build 開真場次 | API 200 | 顯示場次，不再 404 | N/A |
| 場次不存在 | API 404 | `NotFoundPage` | N/A |
| 未登入觀眾、待開打 | 兩隊已定 | 報到面板顯示兩隊狀態與倒數，沒有按鈕；不呼叫 check-in、score-entry | N/A |
| 隊長可報到 | `reason: null` | 「報到」可按；成功後顯示「已報到 HH:mm」 | 409 時面板顯示伺服器訊息 |
| 隊長太早 | `too_early` | 按鈕停用，寫「{時間} 起可報到」 | N/A |
| 兩隊未確定 | `teams_pending` | 面板停用、說明「對手確定後才能報到」 | N/A |
| 記分者 | `is_scorer: true` | 左欄是比分面板，不顯示公開各局列表 | N/A |
| 非記分者登入 | `is_scorer: false` | 只有觀眾檢視 | N/A |
| 登錄平手 | PUT 回 409 `SCORE_TIE` | 該列顯示「不能平手」 | N/A |
| 送出系列結果 | POST 200 | 面板唯讀「{送出者} 送出 · 時間」，場次轉申訴期 | N/A |
| 非比分規則錯誤 | 409 `RESULT_ALREADY_SUBMITTED` | Toast 顯示伺服器訊息，重抓資料 | reject |
| 機器忙碌 | 同時跑 3 份單元測試 | 全部通過 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/match-source.ts` -- 改呼叫 `CompetitionService.readPublicMatch`；刪開發模式分支，`matchPath` 保留（`TournamentBracketPage` 使用）
- `frontend/src/features/competition/match-types.ts` -- 刪除，改 import `@/client`（`MatchAppealWindow`、`MatchGameList`、`MatchHeader`、`MatchScoreDisplay`、`MatchSpectatorView`、`use-match-polling`、`match-fixtures` 與測試）
- `frontend/src/routes/dev/match.tsx` -- 刪除；重新產生 `routeTree.gen.ts`（CLAUDE.md 的掛整個 `frontend/` 做法）
- `frontend/src/features/competition/match-fixtures.ts` -- 只留給測試
- `frontend/src/features/competition/MatchSpectatorView.tsx` -- 加右欄 `checkIn` 插槽、左欄 `scoreEntry` 插槽（有值時取代 `MatchGameList`）；`< lg` 順序：頁首、比分、目前動作區、各局、同輪
- `frontend/src/features/competition/MatchHeader.tsx` -- 返回連結改 `Link to="/tournaments/$tournamentId/bracket"`
- 新增 `frontend/src/features/competition/MatchCheckIn.tsx`、`MatchScoreEntry.tsx` -- 用 TanStack Query 呼叫 client，把回應轉成兩個面板的 props；query key 帶 `detail.updated_at`，場次有變動就重抓；倒數歸零時 invalidate
- `frontend/src/features/identity/auth.ts` -- `useIsSignedIn()` 決定是否呼叫需登入的 API
- `frontend/src/lib/feedback.ts` `notifyError`、`frontend/src/lib/api-error.ts` `parseApiError` -- 錯誤處理
- `frontend/src/components/common/Countdown.tsx` -- `label`、`deadline`、`variant`、`onExpire`
- `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx` -- 組合以上
- `frontend/tests/unit/setup.ts`、`frontend/vitest.config.ts` -- `configure({ asyncUtilTimeout })`、`testTimeout`

## Tasks & Acceptance

**Execution:**
- [x] `match-source.ts`、刪 `match-types.ts`、刪 `routes/dev/match.tsx`、更新 import -- 接真 API
- [x] `MatchCheckIn.tsx`、`MatchScoreEntry.tsx` -- 兩個面板的資料轉接
- [x] `MatchSpectatorView.tsx`、`MatchHeader.tsx`、S4 路由 -- 版面與連結
- [x] `routeTree.gen.ts` -- 重新產生
- [x] `tests/unit/setup.ts`、`vitest.config.ts` -- 放寬逾時（`asyncUtilTimeout` 5000、`testTimeout` 15000）
- [x] `tests/unit/` -- 改寫 `match-source`、`match-route` 為 mock client；新增 `match-check-in`、`match-score-entry` 測試涵蓋 I/O 矩陣
- [x] `tests/e2e/spectator.spec.ts` -- 開假資料場次的測試改 `test.fixme`，註明等 7.1 已抽籤賽事
- [x] `deferred-work.md` -- 刪除 5.8 第一階段、5.2 申訴期區塊、偶發失敗等本 Story 處理完的項目；新增 spectator e2e 待接上一項

**Acceptance Criteria:**
- Given 正式 build，when 開啟已抽籤賽事的場次，then 看到真資料，bundle 不含假資料字串。
- Given 1280px，then 報到面板在右欄最上方；375px 時沒有橫向捲軸。
- Given 同時跑 3 份 `bun run test:unit`，then 三份都全部通過。

## Implementation Notes

- **`fetchMatchDetail`**：呼叫 `CompetitionService.readPublicMatch`。404 `MATCH_NOT_FOUND` 拋 `MatchNotFoundError`；網址的 id 不是 UUID 時後端回 422，這場一定不存在，也當成找不到（顯示 404，不顯示「連線中斷」）。這一點 spec 沒寫，是 AI 的預設，使用者可改。新增 `matchQueryKey()`，公開單場、報到狀態、比分登錄的 query key 都以它開頭；S4 的 `refresh` 只 invalidate 這個前綴，一次重抓三者，寫入成功後等它完成才 resolve。
- **`MatchHeader` 的返回連結**：4.6 第二階段合併時已經是 TanStack `Link`，本 Story 只改型別 import。
- **報到面板（`MatchCheckIn.tsx`）**：兩隊狀態取自公開單場的 `check_in_a_at`／`check_in_b_at`；登入者才呼叫 `readCheckInStatus`（key 帶 `updated_at`、`keepPreviousData`）。未登入沒有 `opens_at`，以預定時間前 30 分鐘推算（contract 的定義）。倒數階段由純函式 `checkInCountdownPhase()` 決定，階段用每次 render 當下的時間判斷，倒數歸零時強制重新 render 並 refresh。開放前的倒數下方寫「{絕對時間} 起可報到」（EXPERIENCE.md 的字串）；隊長太早時按鈕下方也有同一句，會出現兩次。報到被拒（409）時不重抓，由 D 的面板顯示伺服器訊息。
- **棄權期限倒數沒有資料**：公開單場與 `CheckInStatus` 都沒有 `forfeit_deadline`（只有主辦方的 `MatchRead` 有），spec 又禁止改後端，所以過了預定時間就不顯示倒數。`checkInCountdownPhase` 已支援第三段並有測試，`MatchCheckIn` 目前傳 `forfeitDeadline: null`；已記入 `deferred-work.md`，需要 D 補欄位。
- **比分面板（`MatchScoreEntry.tsx` 的 `useMatchScoreEntry`）**：做成 hook，回傳面板或 null，S4 依此決定左欄放面板還是 `MatchGameList`。`is_scorer: true` 之外，AI 另外加了一個條件：判棄權（已送出但沒有送出者）、場次已取消、賽事不再接受比分且沒有送出紀錄時不顯示面板（D 的面板沒有「不能登錄」的呈現，顯示出來只會讓每次操作都跳 Toast）。`bothCheckedIn` 取「原因不是 `check_in_incomplete`、`teams_pending`」。比分規則錯誤碼的對照表是 `SCORE_ERROR_REASONS`；其他錯誤 `notifyError` → refresh → reject。
- **版面**：`MatchSpectatorView` 新增 `checkIn`（右欄最上方）、`scoreEntry`（有值時取代各局列表）。`< lg` 時比分登錄、報到、申訴期都排在 `order-2`（目前動作區），依 DOM 順序是比分登錄、報到、申訴期。
- **測試逾時**：`setup.ts` 的 `configure({ asyncUtilTimeout: 5000 })`、`vitest.config.ts` 的 `testTimeout: 15000`。沒有改任何測試的斷言或跳過測試。
- **改到的既有測試**（都是 A 自己的檔案）：`match-source`、`match-route` 改成 mock client；`bracket-match-card` 的賽事 id 改從 `bracket-fixtures` import；`tournament-bracket-page`「從 S3 進入 S4」原本靠開發模式假資料，改成 mock `readPublicMatch`（第一次跑全部測試時只有這個失敗，修正後通過）。
- **`match-fixtures.ts`**：刪掉只給 `/dev/match` 用的 `simulateMatchChange`，其他推導函式留給測試。

- **主對話核對 diff 後的修正（2026-11-04）**：子代理的版本在任何狀態都放報到面板，已取消的季軍賽（`voided`、兩隊皆 null）、輪空直接確認的場次會出現「待定」「未報到」，與 EXPERIENCE.md「已取消：沒有比分與任何動作」不符。新增 `MatchCheckIn.tsx` 的 `showsCheckIn()`：待開打一律顯示（隊伍未定時面板自己停用），離開待開打後只在兩隊都有隊伍時顯示；S4 路由依它決定是否傳 `checkIn`。函式放在 `MatchCheckIn.tsx` 而不是路由檔，避免 `autoCodeSplitting` 下路由檔另外匯出。`match-check-in.test.tsx` 補「報到面板的去留」3 個測試。
- **主對話驗證（重建 frontend 後）**：typecheck 通過；biome 檢查 239 個檔案沒有錯誤；build 成功，`dist/assets` 不含 `Titan`、`tournament-fixture`、`秋季校際盃`、`dev/match`；`bun run test:unit` 58 個檔案、757 個測試全部通過；同時跑 3 份，三份都是 757 passed（約 82 秒）。修正前同樣同時跑 3 份是 47～53 個失敗；改動的 31 個檔案都是 LF。
- **沒有在瀏覽器看過真資料的版面**：本機示範資料沒有已抽籤的賽事（缺 C 的 registration 步驟），1280px／375px 只以單元測試確認 DOM 順序。依使用者的決定，沒有跑 code review。

- **PR #47 審查後補（2026-11-04）**：審查 4.4（#46）時比對 `deferred-work.md`，發現漏刪 5.3 留下的「S4 接上 `ScoreEntryPanel`（A 的工作）」，本 Story 已完成（錯誤碼對照與 `SCORE_ERROR_REASONS` 七項一致、`check_in_incomplete` 時面板停用、已送出顯示唯讀列），補刪除。

- **合併 main（4.4，#46）**：`sprint-status.yaml` 的 `last_updated` 衝突，採用 main 的值。`deferred-work.md` 設 `merge=union`，合併時救回兩邊刪掉的項目，格式也亂了；改以 main 的版本為底，重新套用本 Story 的刪除與新增。4.4 新增的「S4 要隨 `is_scorer` 顯示或隱藏」由本 Story 完成（指派會更新 `updated_at`），一併刪除。

## Spec Change Log

## Review Triage Log

2026-11-04 D（@OG-Matcha）審查 PR #47（核准，不擋合併；D 已查證每一點）：

| # | 發現 | 判定 | 處理 |
|---|------|------|------|
| 1 | 記分者面板在兩隊報到後停在「等待雙方報到」：查詢 key 只看 `updated_at`，後端報到不更新 `updated_at`；測試 harness 在 refresh 時會改 `updated_at`，所以沒抓到 | medium | D 會在後端讓報到更新 `updated_at`。前端先保險：新增 `matchVersion()`，報到與比分登錄的 key 改成 `updated_at`＋兩隊報到時間。補測試「對手報到後 updated_at 沒變仍重抓」，把 key 改回只看 `updated_at` 時該測試失敗 |
| 2 | `keepPreviousData` 會把上一場的資料帶到下一場 | medium | 新增 `samePlaceholder(matchId)`，只在同一場保留。S4 路由以場次當 key 重新掛載，原本靠這層避開；元件本身沒有防護，同一個實例換場時確實會帶過去（補的測試在改回 `keepPreviousData` 時失敗） |
| 3 | 裝置時鐘比伺服器快時，「報到開放」倒數歸零只重抓一次，伺服器仍回 `too_early` 就不再重試 | low | 新增 `tooEarlyRetryInterval()`：本機已過 `opens_at` 且仍是 `too_early` 時每 5 秒重抓；補純函式測試 |
| 4 | S4 完全沒有 e2e，可用 `page.route` 攔 API 回假資料 | low | 延後：與使用者「改 fixme、等 7.1」的決定不同，需要使用者決定；記入 `deferred-work.md` |

修正後：單元測試 58 個檔案、761 個通過（新增 4 個）；typecheck、biome（239 個檔案）、build 通過。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- 全部 running／healthy
- `docker compose exec -T frontend bun run --filter frontend build`、`typecheck`、`bunx biome check` -- 無錯誤
- `docker compose exec -T frontend bun run test:unit` -- 全部通過；另同時跑 3 份，全部通過
- 改動檔案皆為 LF

**Results（2026-11-04，重建容器後）:**
- `docker compose up -d --build --wait`：全部 healthy。
- build 成功；`dist/assets` 95 個檔案都不含「Titan」「特戰英豪」「tournament-fixture」「秋季校際盃」「dev/match」。
- typecheck 通過；biome 239 個檔案沒有錯誤。
- `bun run test:unit`：58 個檔案、754 個測試全過；同時跑 3 份，三份都是 754 passed（各約 76 秒）。
- 改動的檔案都是 LF。
- 沒有在瀏覽器實測 1280px／375px 版面：本機資料庫沒有已抽籤的賽事（7.1 示範資料的抽籤因 `REGISTRATION_UNAVAILABLE` 略過），開不到真的場次。
