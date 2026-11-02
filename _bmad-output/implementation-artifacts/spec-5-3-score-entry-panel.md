---
title: 'Story 5.3（第一階段之二）：Score entry panel 前端元件（含 5.4 的送出）'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '6fd2a330ce4c915a043cf0129dc10943a6ef6763'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-3-score-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 裁判在 S4 用 Score entry panel（S24）逐局登錄比分並送出系列結果，但後端 API（第二階段，待 2.2）還沒有；面板的版面、文字與狀態已在 UX 定案，等 API 好了才做會趕不上 Demo。

**Approach:** 在 `features/competition` 先做只吃 props 的 `ScoreEntryPanel` 元件與元件測試。已存的局與系列結果（勝局數、勝方、能否送出、門檻）由呼叫端傳入（第二階段來自 API，伺服器用 `scoring.py` 計算）；登錄、刪除、送出以 callback 回傳。

## Boundaries & Constraints

**Always:**
- 版面、文字依 UX-DR31、EXPERIENCE.md〈比分登錄（S24）〉與〈動作停用條件〉S24、DESIGN.md Score entry panel；mockup `mockups/key-s4-match.html` (a)、(b)。
- 標題「比分登錄」；可開始時標題旁 `status-live` 徽章「可開始」，已有任何一局時不顯示；兩隊報到前整個面板停用並寫「等待雙方報到」。
- 表頭「局」＋兩隊隊名；每局一列「第 N 局」：
  - 未存：`win_loss` 為兩個隊名切換鈕、`rounds` 為兩個數字框（非負整數），列尾「登錄」。沒選勝方、數字不完整或平手時「登錄」停用（平手另寫「不能平手」）。
  - 已存：等寬文字比分（`win_loss` 顯示勝方隊名＋「勝」）＋「已登錄」＋ghost「修改」。
  - 修改中：回到輸入，「登錄」覆寫、「取消」恢復原值。同一時間只有一列在編輯或新增。
  - 送出中該列停用，避免重複送出；失敗時在該列顯示錯誤、恢復可編輯。
- 最後一局（已存、尚未送出）另有 ghost「刪除」，按下即呼叫 callback 刪除，不另外確認（使用者 2026-10-29 決定：會造成多餘局的修改要拒絕，所以要能先刪掉最後一局）。
- 伺服器回傳的拒絕原因顯示成中文：`tie`「不能平手」、`invalid_score`「比分格式不正確」、`series_decided`「已有隊伍達到勝局門檻」、`redundant_games`「這樣修改後，後面的局就不需要打了。請先刪除後面的局再修改」、`invalid_game_no`／`not_last_game`「這一局無法修改，請重新整理頁面」。
- 列下方「新增一局」；系列已有勝方時不顯示。
- 底部「系列結果預覽」＋比分（只算已存的局，由 props 傳入）；右側「送出系列結果」：不能送出時停用並寫「任一隊拿到 {N} 勝後才能送出」；可送出時開 AlertDialog，標題「送出系列結果」、內文「送出後無法再修改，只能經由申訴更正。」、確認鈕「送出系列結果」。
- 已送出：唯讀，只剩文字比分，標籤改「系列結果」，下方「{送出者顯示名稱} 送出 · 10/17（六）11:52」；沒有任何按鈕。
- 介面文字全部繁體中文，按鈕動詞＋名詞，不用「確定」、不用驚嘆號。

**Never:**
- 不呼叫 API、不讀 `frontend/src/client`、不做 S4 頁面與身分判斷（呼叫端決定要不要 render）。
- 不在前端計算系列結果或勝局門檻（只顯示 props）；只做「平手、空值」這類輸入框本身的停用。
- 不做 Countdown、Status badge 等 Epic 2 或 1.8 的共用元件（徽章用現有 `Badge` 加 token 顏色）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 未報到 | 兩隊未都報到 | 面板停用、「等待雙方報到」 | N/A |
| 可開始 | 兩隊已報到、沒有局 | 「可開始」徽章、第 1 局輸入列 | N/A |
| 勝負型態登錄 | `win_loss`，選 a 按「登錄」 | `onRecord(1, {winner: "a"})` | N/A |
| 回合型態平手 | `rounds`，12：12 | 「登錄」停用、「不能平手」 | N/A |
| 回合型態登錄 | `rounds`，13：11 | `onRecord(n, {scoreA: 13, scoreB: 11})` | N/A |
| 送出中 | callback 未完成 | 該列停用 | N/A |
| 伺服器拒絕 | callback 回傳 `redundant_games` | 該列顯示對應中文、可再編輯 | 列內錯誤 |
| 修改後取消 | 按「修改」改值後「取消」 | 恢復原值、不呼叫 callback | N/A |
| 同時只編輯一列 | 正在修改第 1 局 | 其他列的「修改」「刪除」「新增一局」停用 | N/A |
| 刪除最後一局 | 3 局已存 | 只有第 3 局有「刪除」，按下 `onDelete(3)` | N/A |
| 已有勝方 | 系列勝方 a | 沒有「新增一局」、「送出系列結果」可按 | N/A |
| 未達門檻 | 門檻 2、1：0 | 「送出系列結果」停用、「任一隊拿到 2 勝後才能送出」 | N/A |
| 送出確認 | 按「送出系列結果」 | AlertDialog；確認後 `onSubmit()`，取消不呼叫 | N/A |
| 已送出 | 有送出者與時間 | 唯讀「系列結果」、「王小明 送出 · 10/17（六）11:52」、沒有按鈕 | N/A |
| 手機 | 寬 375px | 表格不超出畫面寬度（可橫向捲動或縮排） | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/ScoreEntryPanel.tsx` -- 新檔：元件（可拆 `ScoreRow` 子元件）
- `frontend/src/features/competition/match-time.ts` -- Check-in panel 的 spec 也會新增；兩個分支各自需要時，內容必須一致（合併時以先合併者為準）
- `frontend/src/components/ui/alert-dialog.tsx` -- 新檔：shadcn AlertDialog（需新增 `@radix-ui/react-alert-dialog`，用 `bun add`）；其他人的確認對話框（UX-DR15）也會用
- `frontend/src/components/ui/badge.tsx`、`button.tsx`、`input.tsx`、`card.tsx`、`table.tsx` -- 沿用
- `frontend/tests/unit/` -- 元件測試；寫法參考 `login.test.tsx`
- `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/` -- 視覺與文字來源

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/components/ui/alert-dialog.tsx` 與 `package.json`／`bun.lock` -- 新增 AlertDialog
- [x] `frontend/src/features/competition/match-time.ts` -- `formatMatchDateTime(iso, now?)`（`10/17（六）11:52`，Asia/Taipei，跨年加年份）
- [x] `frontend/src/features/competition/ScoreEntryPanel.tsx` -- props：兩隊名稱、`scoreType`、是否兩隊都已報到、已存的局、系列（`winsA`、`winsB`、`winner`、`canSubmit`、`winsNeeded`）、送出資訊或 null、`onRecord(gameNo, input)`、`onDelete(gameNo)`、`onSubmit()`；callback 回傳 Promise，拒絕時帶原因代碼 -- I/O 矩陣
- [x] `frontend/tests/unit/score-entry-panel.test.tsx` -- I/O 矩陣每一列（以角色與文字查詢） -- AC

**Acceptance Criteria:**
- Given I/O 矩陣任一列的 props 與操作，when render 並操作，then 畫面與 callback 呼叫都符合該列。
- Given 任一列送出中，when 再按一次「登錄」，then callback 只被呼叫一次。

## Implementation Notes

- callback 的約定：`onRecord`、`onDelete`、`onSubmit` 成功時 resolve `null`，伺服器拒絕時 resolve 原因代碼（`ScoreReason`，與 `scoring.py` 相同）。Promise 被 reject（連線中斷等）時面板只恢復成可操作、不顯示訊息，交給呼叫端照 UX 的 Toast 規則處理。
- 沒有任何一局時直接顯示第 1 局輸入列（不能取消）；之後的局要按「新增一局」，新增的列可「取消」。輸入列存在時「新增一局」停用。
- 防重複送出：按鈕在送出中停用之外，另用 `useRef` 擋同一個 tick 內的第二次點擊；送出中其他列的「修改」「刪除」、「新增一局」與「送出系列結果」也停用。
- 兩隊未報到時用 `<fieldset disabled>` 停用整個面板；fieldset 加 `min-w-0`，讓 `Table` 的 `overflow-x-auto` 在 375px 寬度下橫向捲動。jsdom 不排版，單元測試只檢查這個結構，實際寬度要在 S4 頁面完成後於瀏覽器確認。
- 數字框只收數字（輸入時濾掉其他字元），所以「數字不完整」就是有一格空白。
- 「送出系列結果」被拒絕時在按鈕下方顯示原因：`not_decided` 沿用「任一隊拿到 {N} 勝後才能送出」，其他代碼一律「送出失敗，請重新整理頁面」；列內遇到沒有對照的代碼顯示「操作失敗，請重新整理頁面」。
- 有列在編輯或新增中時「送出系列結果」停用並寫「請先登錄或取消正在編輯的局」；`games`、`series` 更新時清掉舊的錯誤訊息；收到 `submission` 時離開編輯狀態。
- 數字框：全形數字轉半形、去掉開頭多餘的 0、最多 3 位，按 Enter 等同「登錄」。
- `@radix-ui/react-alert-dialog@1.2.1`；`bun add` 讓 bun.lock 裡其他 Radix 套件的共用依賴重新排列（版本未變，只是巢狀位置不同）。
- `match-time.ts` 用 `en-US` 取數字與英文星期再自行組字串，避開各瀏覽器 zh-TW 格式的差異；另一個分支也會新增此檔，簽名須一致（`formatMatchDateTime(iso, now?)`、`formatClock(iso)`）。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 12 項、Edge Case Hunter 13 項、Verification Gap 4 個缺口；另加實作子代理回報的 6 個疑點。沒有需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | 實作、Blind、Edge | 正在編輯某一局時仍可送出系列結果，未登錄的輸入被丟掉 | high | 送出後無法再改。patch：編輯中停用送出並說明；送出後離開編輯 |
| 2 | Blind、Edge、實作 | 沒有對應文字的原因代碼不顯示任何訊息；送出被拒套用修改局的文字 | medium | patch：列與送出各有預設文字，送出另有對應表 |
| 3 | VG | 同一 tick 連按「登錄」的防護沒有測試能抓到 | medium | 與 5.1 面板相同。patch：同步連按測試，送出確認也補 |
| 4 | VG | 儲存或刪除進行中時其他按鈕是否停用沒有測試 | medium | patch：刪除進行中的測試 |
| 5 | VG | 刪除被拒、送出被拒（非門檻原因）、callback 拋錯都沒有測試 | low | patch |
| 6 | Blind、Edge | 被防護擋下的呼叫會清掉別列的錯誤；舊錯誤在 props 改變後仍留著 | low | patch |
| 7 | Edge | 已有勝方但不能送出時仍顯示「任一隊拿到 N 勝」 | low | 例如多餘局的狀態。patch：只在沒有勝方時顯示 |
| 8 | Edge、Blind | 全形數字被清空、沒有長度上限、保留前導 0、Enter 無作用 | low | 中文輸入法常見。patch |
| 9 | Blind | 送出確認沒顯示要送出的結果 | low | 不可逆動作。patch：對話框加一行系列比分 |
| 10 | Blind、Edge | callback 的錯誤處理約定沒寫 | low | patch：寫在 props 型別上 |
| 11 | Blind | diff 沒有 lockfile | false | 審查用的 diff 刻意排除 `bun.lock`；`bun install --frozen-lockfile` 已驗證 |
| 12 | Blind | 刪除最後一局沒有確認或復原 | false | 使用者 2026-10-29 決定不另外確認；刪了可重新登錄 |
| 13 | Blind | 修改、取消後鍵盤焦點掉到 body | defer | 無障礙改善，第二階段接上 S4 時以瀏覽器實測一併處理 |
| 14 | Edge | `rounds` 已存的局缺比分時顯示空白 | false | 伺服器以 `GameResult` 保證 rounds 一定有兩個比分 |
| 15 | 實作 | 依 #3 新增的「同步連按確認送出」測試，拿掉防護也會通過 | false | Radix 在第一次點擊就關閉對話框，第二次點不到；從介面無法觸發，測試不可能失敗，已刪除 |

## Verification

**Commands:**
- `cd frontend && bun run test:unit` -- expected: 全部通過
- `cd frontend && bun run build && bunx biome check ./src ./tests` -- expected: 通過

**結果（2026-10-29，第 1 輪修正後）：**
- 新增 54 個測試（Score entry panel 45、時間格式 9）全部通過；整體 `test:unit` 216 passed（同一容器第二次執行；冷啟動失敗與本變更無關，見 5.1 的 deferred-work）。
- `bun run build`（含 tsc）、biome、`bun install --frozen-lockfile` 通過。
- Mutation 驗證：拿掉「編輯中不能送出」→ 2 個測試失敗；系列已有勝方仍顯示「新增一局」、送出中可重複登錄 → 各有測試失敗。還原後全過。
