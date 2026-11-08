---
title: 'S27 抽籤按鈕與抽籤狀態（4.1 前端）'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '445b7cc78cc5a2df63b4fe7b8a857650adc99616'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.1 抽籤的後端（`POST /tournaments/{id}/draw`）與 C 的 registration 函式（#53）都已合併，但主辦方後台 S27 沒有「抽籤」按鈕，主辦方無法抽籤；UX 要求正取不足 2 隊時按鈕停用並寫原因，但開放報名中的正取名單要到抽籤當下（`finalize_for_draw`）才分配出來，前端沒有資料判斷。

**Approach:** competition 新增 `GET /organizer/tournaments/{id}/draw-status`，用與抽籤完全相同的程式路徑預估：在 savepoint 裡呼叫 `finalize_for_draw`、數正取隊伍，再以例外讓 savepoint 回滾，回傳是否可抽籤與原因。S27 依此顯示「抽籤」按鈕（`AlertDialog` 確認），按下後端仍再檢查一次。

## Boundaries & Constraints

**Always:**
- 狀態 API（`Organizer`，主辦方本人）回 `DrawStatus {can_draw: bool, reason: str | None, expected_teams: int | None}`；檢查順序與 `draw` 相同：`BRACKET_ALREADY_DRAWN`→`already_drawn`、狀態不是 open／closed→`not_drawable`、開賽時間已過→`start_passed`、預估正取 < 2→`not_enough_teams`；可抽籤時 `reason` 為 null。`expected_teams` 只在走到預估那一步時有值。
- 預估：賽事 `open` 時在 `session.begin_nested()` 內呼叫 `registration_port.finalize_for_draw` 與 `list_accepted_teams`，數完後拋出模組私有例外讓 savepoint 回滾（service 不呼叫 `rollback()`，AD-5）；`closed` 直接數。預估不得留下任何報名狀態、結算紀錄、操作紀錄或 outbox 事件（測試要逐項確認）。先 `lock_tournament`（AD-6）。
- 按鈕：只在 `can_draw` 為真時可按；停用時在按鈕下方寫原因：`not_enough_teams`「正取不足 2 隊，無法抽籤」、`start_passed`「開賽時間已過，無法抽籤」；`already_drawn`、`not_drawable` 時不顯示按鈕。
- 確認：`AlertDialog`（沿用 `ConfirmDialog`），開放報名中寫「抽籤只能執行一次，會立即結束報名。」，報名截止寫「抽籤只能執行一次。」；確認按鈕「抽籤」。
- 成功：提示「已完成抽籤」，重抓賽事與抽籤狀態，按鈕消失；失敗（含 409 `NOT_ENOUGH_TEAMS`）用 `notifyError` 顯示後端訊息並重抓狀態。
- 新元件放 `features/competition/`；S27 只在 B 的總覽頁插入這個元件（CONTRIBUTING 6.6，PR 說明列出）。

**Never:**
- 不改 registration、tournaments 的函式；不新增資料表或遷移；不做自動抽籤（4.2 擱置）、取消賽事、延長報名。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 優先期內提前抽籤 | open、優先期內有 ≥2 隊送出（都還是待分配） | `can_draw=true`、`expected_teams` 為分配後的數量；資料不變 | — |
| 不足 | open、只有 1 隊送出 | `can_draw=false`、`not_enough_teams`；按鈕停用寫原因 | — |
| 截止後 | closed、正取 ≥2 | 可抽籤，確認框寫「抽籤只能執行一次。」 | — |
| 已抽籤 | 已有對戰表 | `already_drawn`，不顯示按鈕 | — |
| 狀態不對 | draft、published、ongoing、finished、cancelled | `not_drawable`，不顯示按鈕 | — |
| 開賽已過 | `start_at <= now` | `start_passed`，停用寫原因 | — |
| 抽籤成功 | 按下並確認 | 201；提示「已完成抽籤」，按鈕消失 | — |
| 按下時不足 | 預估後有人變動 | 409 `NOT_ENOUGH_TEAMS`，顯示訊息並重抓 | 全部回滾 |
| 非本人 | 其他主辦方 | 403 `TOURNAMENT_OWNER_REQUIRED` | 沿用後台無權限畫面 |

## Decisions

- 2026-11-05（使用者）：正取不足的停用採「後端預估＋按下再確認」：新增抽籤狀態 API，用同一套分配規則預估、不寫入。
- 2026-11-05（使用者）：核准草稿（savepoint 預估、已抽籤或狀態不對時不顯示按鈕、停用時寫原因、按鈕插入 B 的 S27）。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/service.py:209` `draw`（檢查順序、`_DRAWABLE`、`finalize_for_draw` 只在 open 時呼叫）；`registration_port.py`
- `backend/app/modules/competition/{models,router}.py` -- 新增 `DrawStatus`、`GET /organizer/tournaments/{tournament_id}/draw-status`（`Organizer` 依賴，與 4.3 的列表同樣寫法）
- 測試：`tests/registration/test_draw_functions.py`（真的 registration 函式、優先期內抽籤的資料準備）、`tests/competition/test_draw.py`、`conftest.py` 的 `FakeRegistration`
- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx` -- B 的 S27；只插入新元件
- `frontend/src/components/common/ConfirmDialog.tsx`、`lib/feedback.ts`、`features/competition/organizer-matches-queries.ts`（query／mutation 寫法）、`features/tournaments/organizer-queries.ts`（`myTournamentQueryOptions`）
- 前端測試：`tests/unit/organizer-tournaments.test.tsx`、`organizer-matches.test.tsx` 的寫法

## Tasks & Acceptance

**Execution:**
- [x] 後端：`DrawStatus`、`get_draw_status`、路由；測試涵蓋 I/O 矩陣，含「預估後報名狀態、結算紀錄、操作紀錄、outbox 事件數都不變」與「預估結果等於之後真的抽籤的隊數」
- [x] `scripts/generate-client.sh` 重新產生 client
- [x] 前端：`features/competition/DrawButton.tsx`（＋queries）、插入 S27；單元測試
- [x] contracts（API 表、錯誤碼／原因代碼）、`deferred-work.md`（刪除 S27 抽籤按鈕相關項目，若有）、`sprint-status.yaml` 4.1 註記

**Acceptance Criteria:**
- Given 優先期內兩隊已送出的 open 賽事，when 呼叫狀態 API 兩次，then 兩次都 `can_draw=true`、資料庫報名仍為待分配、沒有結算紀錄；接著抽籤成功。
- Given 主辦方在 S27 按「抽籤」並確認，when 成功，then 提示「已完成抽籤」且按鈕消失。

## Implementation Notes

- 後端：`models.py` 新增 `DrawStatusReason`、`DrawStatus`；`service.py` 把 `draw` 開頭的三項檢查抽成 `_draw_blocked`（回傳小寫原因），錯誤碼與訊息集中在 `_DRAW_ERRORS`／`_draw_error`，`draw` 與 `get_draw_status` 共用，保證檢查順序與原因代碼對應不會分岔；`draw` 對外行為（錯誤碼、訊息、順序）不變。
- 預估 `_expected_teams`：`open` 時 `with session.begin_nested():` 內呼叫 `registration_port.finalize_for_draw`、`list_accepted_teams`，再拋模組私有的 `_PreviewRollback(count)` 讓 savepoint 回滾，外層接住取數量；`closed` 直接數、不呼叫 `finalize_for_draw`（與 `draw` 相同）。service 沒有 `rollback()`，`test_architecture` 通過。
- 路由 `GET /organizer/tournaments/{tournament_id}/draw-status`（`Organizer` 依賴、不 commit，寫法同 `list_managed_matches`）；路徑沿用 tournaments 模組 `/organizer/tournaments/...` 的前綴，與 frozen 區塊的寫法一致。
- 測試 `tests/competition/test_draw_status.py`（29 個）：用真的 registration 函式準備優先期內提前抽籤、優先期後先搶期＋補位、同校上限等資料；每個 open 情境比對預估前後的報名狀態、結算紀錄、操作紀錄數、outbox 事件總數與賽事狀態，並接著真的 `draw` 確認隊數等於預估。HTTP 測試以 spy 包住 `Session.commit`，確認 GET 沒有 commit。曾把 `raise _PreviewRollback(...)` 改成 `return` 做變異測試，6 個「不留痕跡」測試都會失敗，確認檢查有效。
- I/O 矩陣的「draft」：`TournamentStatus` 沒有 draft，對應的是 `upcoming`；`not_drawable` 測試以「open、closed 以外的所有狀態」參數化（upcoming、published、ongoing、finished、cancelled）。
- 前端：`features/competition/draw-queries.ts`（`drawStatusQueryOptions`、`useDraw`）、`DrawButton.tsx`；S27 的 `OrganizerTournamentOverview` 只把回傳改成 fragment 並插入 `<DrawButton>`（CONTRIBUTING 6.6，PR 說明要列出）。
- 抽籤失敗時 `useDraw` 以 `notifyError` 顯示後端訊息並重抓；`ConfirmDialog` 的 `onConfirm` 吞掉 reject 讓對話框關閉，避免同一個錯誤同時出現在 Toast 與對話框內。成功／失敗都等重抓賽事、抽籤狀態、S25 列表與 S30 場次列表後 mutation 才結束。
- 抽籤狀態載入中不顯示按鈕；載入失敗見下方（後端抽籤仍會檢查，不會誤抽）。frozen 區塊沒有規定這個情況。
- `organizer-tournaments.test.tsx` 加一個 `beforeEach` mock `readDrawStatus`（回 `not_drawable`），避免既有 S27 測試打到未 mock 的 API；按鈕的測試另放 `draw-button.test.tsx`。
- 本機 frontend 映像沒有 `@radix-ui/react-alert-dialog`（主 repo 的 package.json 也是舊的，重 build 也不會有），改用一次性容器掛上 worktree 的 `package.json`、`bun.lock` 後 `bun install --frozen-lockfile` 再跑 vitest。
- `deferred-work.md` 原本沒有 S27 抽籤按鈕相關項目；審查後新增一項「預估改成不寫入的純函式試算」。
- 預覽只保證到人數檢查為止：之後的對戰表產生（洗牌、排時間、寫入場次）若失敗，預覽不會知道；按下抽籤時後端回 409，前端以錯誤 Toast 顯示後端訊息。
- 預覽會消耗 `audit_log.seq` 序列值（`finalize_for_draw` 在 savepoint 內寫操作紀錄，回滾不會歸還序列值）；`seq` 只用來排序，空洞無影響。
- `get_draw_status` 先不鎖讀賽事（`tournaments_service.get_tournament`）擋掉非主辦方，再 `lock_tournament`，無權限者不會排隊等鎖。GET 期間持有賽事列鎖，開放報名中每次預覽都重做分配後回滾；前端以 `staleTime: 30_000` 與 `refetchOnWindowFocus: false` 降低頻率，抽籤成功或失敗後的 invalidate 不受影響。根本解法（不寫入的純函式試算）列在 `deferred-work.md`。
- 多連線並發沒有自動測試：測試框架是單一連線的 savepoint，無法開兩個交易互相等鎖；靠 `draw`、`get_draw_status`、`finalize_for_draw` 都先鎖賽事列的鎖順序一致來保證，並以測試確認先鎖賽事、再查對戰表、再分配的呼叫順序。
- 抽籤狀態載入失敗時顯示「無法取得抽籤狀態」與「重新載入」按鈕（呼叫 `refetch`）；載入中仍不顯示。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap 三位審查員並行；無高嚴重度）：

- 修正：開放報名中每次預估都持有賽事列鎖並重做分配，前端預設聚焦就重抓 → `drawStatusQueryOptions` 設 `staleTime: 30_000`、`refetchOnWindowFocus: false`；`get_draw_status` 先不鎖讀賽事驗主辦方，再取鎖。
- 修正：狀態查詢失敗時按鈕無聲消失 → 顯示「無法取得抽籤狀態」與「重新載入」。
- 修正（測試）：原因代碼順序（三種組合）、closed 只有 1 隊、其他主辦方查已抽籤賽事仍 403、`finalize_for_draw` 在 savepoint 內拋錯不留痕跡、非校園賽預估等於實抽、鎖在查對戰表之前；`draw` 的兩則錯誤訊息與「狀態不對優先於開賽已過」。
- 修正（測試）：前端改用 spec 字面字串斷言（原本 import 常數，改字不會紅；變異檢查確認現在會紅）、409 後重抓賽事、成功後 invalidate S25／S30 列表、載入失敗與重試；移除固定等待。
- 延後：改成不寫入的純函式試算 → `deferred-work.md` 新增一項。
- 記錄不改：預覽只保證到人數檢查；`audit_log.seq` 空洞；多連線並發沒有自動測試（見 Implementation Notes）。
- 不採用：確認框文字與 `can_draw` 來自不同查詢（後端抽籤時再檢查，最壞只是文字落差）；連按兩次（`ConfirmDialog` 載入中已停用，後端有鎖與已抽籤檢查）。

## Verification

**Commands:**
- 主 repo 執行、掛 worktree：`bash scripts/test.sh; bash scripts/lint.sh` -- 全部通過（含 `test_architecture.py`）
- 前端：`bunx biome check src tests`、相關 vitest
