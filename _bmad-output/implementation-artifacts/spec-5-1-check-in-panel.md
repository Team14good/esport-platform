---
title: 'Story 5.1（第一階段之二）：Check-in panel 前端元件'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '15238ac68c31ad4a6401add8837de5f5625c84df'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** S4 場次頁的 Check-in panel 要等後端 API（第二階段，待 2.2）才能接資料，但面板本身的版面、文字與停用條件已在 UX 定案；等 API 好了才開始做，Demo 前時間會不夠。

**Approach:** 在 `features/competition` 先做只吃 props 的 `CheckInPanel` 元件與元件測試。資料由呼叫端傳入（第二階段由 S4 頁面從 API 取得），報到動作以 callback 回傳；倒數由呼叫端以插槽傳入（Countdown 元件屬於 Epic 2，不在這裡重做）。

## Boundaries & Constraints

**Always:**
- 版面、文字、顏色依 UX-DR30、EXPERIENCE.md〈Check-in panel〉與〈動作停用條件〉S4 報到、DESIGN.md `check-in-panel`；mockup `mockups/key-s4-match.html`。
- 兩隊各一欄（`< sm` 上下兩列）：隊名＋「已報到 HH:mm」（`status-confirmed`）或「未報到」（`muted-foreground`）。
- 「報到」按鈕只出現在呼叫端指定的「本隊」那一欄（只有該場兩隊的隊長各自看到本隊的按鈕）；其他人只看狀態。按鈕手機滿版、高 ≥ 40px。
- 停用與說明依 `checkin.py` 的原因代碼（由呼叫端傳入）：
  - `too_early`：按鈕停用，寫「{絕對時間} 起可報到」，下方放倒數插槽。
  - `teams_pending`：整個面板停用，寫「對手確定後才能報到」（計時暫停 banner 屬於 6.3，期中不做）。
  - `already_checked_in`：按鈕消失，不可取消報到。
  - `closed`：按鈕停用，寫「已截止」。
- 按下「報到」時呼叫 callback；等待回應期間按鈕停用並顯示載入，避免重複送出；失敗時在面板內顯示錯誤訊息（`FormErrorAlert` 或同等），按鈕恢復。
- 場次不是「待開打」時面板收起，只留兩隊報到時間（「已報到 HH:mm」或「未報到」）。
- 絕對時間格式 `10/18（六）19:00`，Asia/Taipei、跨年才加年份、不標時區；「已報到」只顯示 `HH:mm`。
- 介面文字全部繁體中文，按鈕用動詞（「報到」），不用驚嘆號。

**Never:**
- 不呼叫 API、不讀 `frontend/src/client`（型別等第二階段 API 產生後再換）、不做路由與 S4 頁面本身。
- 不自己判斷能不能報到（只顯示呼叫端傳入的原因），不讀裝置時鐘決定狀態。
- 不實作 Countdown、Page banner、Status badge 等 Epic 2 或 1.8 的共用元件。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 觀眾 | 沒有本隊、兩隊未報到 | 兩欄「未報到」，沒有按鈕 | N/A |
| 隊長、太早 | 本隊 a、原因 `too_early`、開放 10/18 19:00 | a 欄按鈕停用、「10/18（六）19:00 起可報到」、倒數插槽 | N/A |
| 隊長、可報到 | 本隊 a、原因 None | 按鈕可按 | N/A |
| 送出中 | 按下後 callback 尚未完成 | 按鈕停用並顯示載入 | N/A |
| 報到失敗 | callback 拋錯或回傳錯誤訊息 | 顯示錯誤訊息、按鈕恢復 | 面板內錯誤 |
| 已報到 | a 已報到 19:32 | a 欄「已報到 19:32」、沒有按鈕 | N/A |
| 兩隊未確定 | 原因 `teams_pending` | 面板停用、「對手確定後才能報到」 | N/A |
| 已截止 | 原因 `closed` | 按鈕停用、「已截止」 | N/A |
| 離開待開打 | 場次狀態不是待開打 | 只留兩隊報到時間，沒有按鈕與倒數 | N/A |
| 手機 | 寬 375px | 上下兩列、按鈕滿版 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/CheckInPanel.tsx` -- 新檔：元件
- `frontend/src/features/competition/match-time.ts` -- 新檔：絕對時間與 `HH:mm` 格式（Asia/Taipei）；Score entry panel 也會用。Epic 2 若另有共用的時間格式，之後再合併
- `frontend/src/components/ui/card.tsx`、`button.tsx`、`loading-button.tsx` -- 沿用
- `frontend/src/components/common/FormErrorAlert.tsx` -- 錯誤訊息沿用
- `frontend/tests/unit/` -- 元件測試放這裡（`vitest.config.ts` 的 include）；寫法參考 `login.test.tsx`
- `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/`（EXPERIENCE.md、DESIGN.md、`mockups/key-s4-match.html`） -- 視覺與文字來源

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/match-time.ts` -- `formatMatchDateTime(iso, now?)`、`formatClock(iso)` -- 共用格式
- [x] `frontend/src/features/competition/CheckInPanel.tsx` -- props：兩隊（id、名稱、報到時間或 null）、本隊 side 或 null、場次是否待開打、原因代碼、開放時間、倒數插槽、`onCheckIn` -- I/O 矩陣
- [x] `frontend/tests/unit/check-in-panel.test.tsx`、`match-time.test.ts` -- I/O 矩陣每一列（以角色與文字查詢，不依賴 class 名稱）；時間格式含跨年、午夜、Asia/Taipei 換算 -- AC

**Acceptance Criteria:**
- Given I/O 矩陣任一列的 props，when render，then 畫面文字、按鈕有無與停用狀態都符合該列。
- Given 可報到，when 連按兩次「報到」，then `onCheckIn` 只被呼叫一次。

## Implementation Notes

- props：`teams: { a, b }`（`id`、`name`、`checkedInAt`；對手未定的一側為 null，顯示「待定」）、`ownSide: "a" | "b" | null`、`isScheduled`、`teamsPending`、`reason`（與 `checkin.py` 的 `CheckInReason` 同名的四個字串，第二階段換成產生的型別）、`opensAt`、`countdown?`、`onCheckIn`。
- `onCheckIn` 回傳 `Promise<string | undefined> | Promise<void>`：拋錯時以 `parseApiError` 轉成 `FormErrorAlert`；回傳非空字串時當成錯誤訊息。完成後按鈕即恢復，所以呼叫端要在重新取得場次資料後才 resolve，按鈕才會依新的 `reason` 消失。
- 防重複送出：`LoadingButton` 的 `loading` 停用按鈕，另用 ref 擋同一個 tick 內的第二次點擊；送出中加 `aria-busy`，測試以此判斷「顯示載入」。
- 錯誤訊息記下當時的 `isScheduled`／`teamsPending`／`reason`，重新取得資料後狀態變了就不再顯示。本隊 `checkedInAt` 已有值時，即使 `reason` 還沒更新也不顯示按鈕。不認得的原因代碼：按鈕停用，寫「目前無法報到，請重新整理頁面」。
- 停用說明以 `aria-describedby` 連到按鈕；`match-time` 收到空字串或無效時間時回傳空字串，不讓畫面壞掉。
- 按鈕、停用說明、錯誤與倒數都放在本隊那一欄；觀眾（`ownSide` 為 null）的倒數放在兩隊下方。倒數只在待開打時顯示，內容（含 `teams_pending` 時要不要給）由呼叫端決定。
- 兩隊未確定（`teamsPending` 或 `reason` 為 `teams_pending`）：清單加 `aria-disabled` 並降低不透明度，兩隊下方寫「對手確定後才能報到」，觀眾也看得到；隊長的按鈕停用。
- `match-time.ts` 用 `Intl.DateTimeFormat`（`en-US`、`Asia/Taipei`、`hourCycle: "h23"`）取各欄位，星期用對照表轉中文，不依賴執行環境的中文語系資料；跨年以台北時間的年份比較。
- 手機版的上下兩列與滿版按鈕是 CSS（`sm:grid-cols-2`、`w-full h-touch-target`），jsdom 量不到版面；測試只確認兩隊是依序的清單項目、按鈕在本隊那一項內。
- 測試：`match-time.test.ts` 9 個、`check-in-panel.test.tsx` 20 個。突變檢查：讓按鈕送出中仍可按 →「送出中」失敗；拿掉跨年加年份 → 兩個跨年測試失敗；拿掉 ref 防護 →「同一個 tick 內連按兩次」失敗。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 11 項、Edge Case Hunter 9 項、Verification Gap 2 個缺口；另加實作子代理回報的 7 個疑點。沒有需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Blind、Edge、實作 | 對手未定時 props 無法表示，觀眾也看不到「對手確定後才能報到」 | medium | 原因代碼是依觀看者給的，觀眾沒有。patch：隊伍可為 null（顯示「待定」），另加 `teamsPending` 給所有人 |
| 2 | VG | 「連按只呼叫一次」的測試拿掉同一 tick 的防護也會通過 | medium | 第二次 userEvent 點擊時按鈕已停用。patch：同步連續 `fireEvent.click` 的測試 |
| 3 | Blind、Edge | 時間字串格式錯誤時整個面板 render 失敗 | medium | `formatToParts` 拋 `RangeError`。patch：無效日期回傳空字串（兩個分支的 `match-time.ts` 同步） |
| 4 | Blind、Edge | 狀態改變後舊的伺服器錯誤仍留著 | low | patch：原因、場次狀態改變時清除 |
| 5 | Edge | 本隊已有報到時間但原因尚未更新時仍顯示按鈕 | low | patch：任一成立就視為已報到 |
| 6 | Blind | 停用原因沒有連到按鈕，整面板停用只有視覺 | low | patch：`aria-describedby`、`aria-disabled`，並以此測試停用 |
| 7 | Blind | 未知的原因代碼會留下沒有說明的停用按鈕 | low | patch：窮舉 switch＋預設說明 |
| 8 | Blind、Edge | 一個測試在結束後才 resolve | low | patch：等待按鈕恢復；補非 HTTP 錯誤、回傳空字串的測試 |
| 9 | Blind | `onCheckIn` 用字串表示失敗不直觀 | false | 與 Score entry panel 的 callback 約定一致（回傳原因或訊息），第二階段接 API 時再統一 |
| 10 | 實作 | spec 例子的 10/18 在 2026 年是星期日 | false | 只是例子，測試以 mockup 的日期驗證 |
| 11 | 實作 | 按鈕放在本隊欄，DESIGN.md 放在兩欄下方 | false | spec 依 UX-DR30「各自看到本隊的報到按鈕」，兩者不衝突 |

## Verification

**Commands:**
- `cd frontend && bun run test:unit` -- expected: 全部通過
- `cd frontend && bunx tsc -p tsconfig.build.json --noEmit && bunx biome check ./src ./tests` -- expected: 通過

**結果（2026-10-29，第 1 輪修正後）：**
- 新增 29 個測試（Check-in panel 20、時間格式 9）全部通過；整體 `test:unit` 191 passed（同一容器第二次執行；第一次的冷啟動失敗與本變更無關，見 deferred-work）。
- `bun run build`（含 tsc）與 biome 通過。
- Mutation 驗證：拿掉同一 tick 的連按防護 → 1 個測試失敗；送出中按鈕不停用、拿掉跨年加年份 → 各有測試失敗。還原後全過。
