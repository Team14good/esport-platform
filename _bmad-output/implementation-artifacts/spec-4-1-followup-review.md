---
title: 'S27 抽籤狀態與 6.x 前置函式的審查後續'
type: 'bugfix'
created: '2026-11-08'
status: 'done'
baseline_commit: '9edb1cfb125829284ceef770818bce9d21149e43'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-s27-draw-button.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-x-competition-hooks.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #56（S27 抽籤按鈕）、#57（6.2／6.5 前置函式）合併時，A、B 的審查留下不擋合併的建議：S27 停在頁面時抽籤狀態不會更新；預估回滾測試的結算紀錄比對無效（ORM 同一實例）且沒涵蓋「優先期已結算」；非 open／closed 賽事也查抽籤狀態；抽籤後公開賽事快取沒更新；`unassign_referee_if_member` 對錯誤狀態的場次不會報錯；約定有幾處與實作不符或沒寫呼叫端責任。

**Approach:** 只修這些項目，不改對外 API 形狀。

## Boundaries & Constraints

**Always:**
- S27：`drawStatusQueryOptions` 保留 `staleTime: 30_000`，拿掉 `refetchOnWindowFocus: false`（回到分頁且資料超過 30 秒時重抓）。抽籤狀態查詢只在 `tournament.status` 為 `open`／`closed` 時啟用。抽籤成功／失敗後另外 invalidate 公開賽事的詳情與列表查詢。
- 測試：`_snapshot` 的結算紀錄改比值；新增「open 且優先期已由 worker 結算」後預估的情境，確認預估不留痕跡且隊數等於之後實抽。前端「載入失敗」測試不等真實重試（測試用 QueryClient 不重試）。
- `unassign_referee_if_member`：場次不是 `scheduled`／`live` 時拋 `ValueError`（呼叫端程式錯誤，與 `check_replay_time` 一致），補測試。
- contracts/competition.md：draw-status 列改寫成實際順序（先不鎖讀賽事驗主辦方、再 `lock_tournament`），補 503 `REGISTRATION_UNAVAILABLE` 與非 UUID 的 422；`get_replay_window` 寫明「場次歸屬與主辦方由呼叫端檢查」；S32 收到任一 `RESCHEDULE_*` 409 都重抓範圍；4.4 段落寫明 6.2 的路徑（更正結果經 `confirm_match` → `advance` 填位時已檢查；重新比賽不換隊伍、保留裁判）。

**Never:**
- 不改 API 路徑、回應欄位、錯誤碼；不新增資料表或遷移；不改 registration、tournaments、disputes 的函式；不修改 deferred-work 既有項目。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 停在 S27 後有人送出 | 狀態超過 30 秒、切回分頁 | 重抓抽籤狀態，按鈕更新 | — |
| 30 秒內切回分頁 | — | 不重抓 | — |
| 賽事不是 open／closed | published、ongoing 等 | 不呼叫抽籤狀態 API、不顯示按鈕 | — |
| 抽籤後切到公開賽事頁 | 同一次瀏覽 | 顯示新狀態（公開查詢已 invalidate） | — |
| 優先期已結算後預估 | open、worker 已結算 | 預估不留痕跡、隊數等於實抽 | — |
| 錯誤狀態呼叫收回裁判 | appealed、confirmed、voided 等 | `ValueError`，不寫入 | — |

## Decisions

- 2026-11-08（使用者）：S27 採 B 的建議，保留 `staleTime: 30_000`、拿掉 `refetchOnWindowFocus: false`。
- 2026-11-08（A 審查 #57 的決定，D 採用）：`unassign_referee_if_member` 對非 scheduled／live 場次拋 `ValueError`。

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/draw-queries.ts`、`DrawButton.tsx`；公開賽事查詢在 `frontend/src/features/tournaments/`（找公開詳情／列表的 queryOptions）
- `frontend/tests/unit/draw-button.test.tsx`
- `backend/tests/competition/test_draw_status.py`（`_snapshot`）；優先期結算 worker 的資料準備參考 `tests/registration/`
- `backend/app/modules/competition/service.py`（`unassign_referee_if_member`）、`backend/tests/competition/test_replay_hooks.py`
- `_bmad-output/implementation-artifacts/contracts/competition.md`

## Tasks & Acceptance

**Execution:**
- [x] 前端三項＋測試
- [x] 後端測試兩項、`unassign_referee_if_member` 狀態檢查＋測試
- [x] contracts 四處

**Acceptance Criteria:**
- Given 主辦方停在 S27 超過 30 秒，when 切回分頁，then 抽籤狀態重抓。
- Given 優先期已結算的 open 賽事，when 預估再實抽，then 預估前後資料（含結算紀錄的值）相同且隊數一致。

## Implementation Notes

- `_snapshot` 的結算紀錄改存 `{settled_at, priority_school_ids}`。變異檢查：預估後在 `_expected_teams` 外把結算的 `settled_at` 加一天（模擬預估改到結算紀錄），新測試 `test_preview_after_worker_settled_priority_window` 紅（`_snapshot(...) == before` 失敗），還原後綠。
- 新增 `test_preview_after_worker_settled_priority_window`（3 組：先搶期補上、名額已滿候補、優先期後無報名）：先以 worker 工作 `allocate_priority_windows` 結算，再預估兩次、比對快照、實抽隊數等於預估。
- 前端：公開賽事查詢用 `publicTournamentQueryOptions`、`publicTournamentsQueryOptions` 的 queryKey invalidate；`DrawButton` 以 `enabled` 限制只在 `open`／`closed` 查詢，其他狀態回傳 null。
- 偏差：frozen 說「測試用 QueryClient 不重試」，實際因 `drawStatusQueryOptions` 自帶 `retry: shouldRetry` 會覆蓋它。改為：409 業務錯誤不重試（保留原「載入失敗」測試），另補 500 伺服器錯誤的測試，用假計時器（`shouldAdvanceTime`＋`advanceTimersByTimeAsync`）跳過重試間隔，斷言重試 3 次後顯示錯誤與「重新載入」，兩條路徑都涵蓋，不需真的等待。
- 補 draw-status 的 API 層 503 測試（open、closed）；`unassign_referee_if_member` 的錯誤狀態測試先比 `_writes` 再看裁判欄位。
- `refetchOnWindowFocus` 測試以 `vi.useFakeTimers({ toFake: ["Date"] })` 推進時間、`focusManager.setFocused` 切換：29 秒內不重抓、超過 30 秒重抓並更新按鈕。
- `unassign_referee_if_member` 非 `scheduled`／`live` 拋 `ValueError`；測試涵蓋其餘所有 `MatchStatus`，並補 `live` 正常收回。
- contracts：draw-status 列（鎖順序、503、422）、`get_replay_window`（呼叫端檢查歸屬與主辦方）、`check_replay_time`（任一 `RESCHEDULE_*` 重抓）、4.4 段落（6.2 路徑）、`unassign_referee_if_member`（狀態檢查）。

## Spec Change Log

## Review Triage Log

第 1 輪（一個審查子代理兼 Blind Hunter 與 Verification Gap；無高嚴重度，確認 `advance` 走私有 `_unassign_if_member` 不受新檢查影響、6.5 頂替的場次都是 `scheduled`、hooks 沒有條件式呼叫、公開查詢 queryKey 與公開頁一致）：

- 修正：contracts draw-status 列的 503 只寫開放報名，實際報名截止呼叫 `list_accepted_teams` 也會 503；403 的說法改成「別人賽事的 `TOURNAMENT_OWNER_REQUIRED` 在取鎖之前」。
- 修正（測試）：「載入失敗」改用 409 後，500（會重試）顯示錯誤的路徑沒有測試 → 補 500＋假計時器；錯誤狀態收回裁判在 rollback 後才比對「不寫入」（空斷言）→ 拋錯後直接比；補 draw-status 的 API 層 503（open、closed）。
- 不改：公開查詢沒有 `staleTime`，切到公開頁本來就會重抓，invalidate 只是保險；公開對戰樹靠輪詢與掛載重抓；focus 測試只驗 29、31 秒兩點；`if (!drawable) return null` 與 `enabled: false` 重複保護。
- 偏差（記錄）：frozen 寫「測試用 QueryClient 不重試」，但 `drawStatusQueryOptions` 自帶 `retry` 會覆蓋，改為 409 不重試＋500 用假計時器，兩條路徑都涵蓋（意圖是不等真實重試）。

## Verification

**Commands:**
- 主 repo 執行、掛 worktree：相關測試＋`bash scripts/lint.sh`；前端 biome＋相關 vitest
