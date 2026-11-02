---
title: 'Story 5.3（第一階段）：逐局比分與系列結果的規則（含 5.4 的送出條件）'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '48b7ff88599a779e3298bc4982ef07e5cb6cb3f0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 5.3 要讓裁判逐局登錄比分、送出前可覆寫某一局，5.4 要依各局算出系列比分、達到勝局門檻才能送出；但 Match、Game 資料表要等上游 2.2 合併才能建，`record_game()`、`submit_result()` 與 Score entry panel 都還不能做。

**Approach:** 先在 competition 寫不碰資料庫的純函式：檢查一局的輸入、檢查能不能登錄或覆寫第 N 局、計算系列結果與能不能送出。第二階段的 service 在鎖定場次後用它判斷再寫入；前端的「系列結果預覽」與停用說明用同一套結果。

## Boundaries & Constraints

**Always:**
- 勝局門檻＝（BO＋1）÷ 2；BO 只能是 1、3、5、7，否則 `ValueError`。期中每一輪都用賽事的 BO（期中版規則 3）。
- 比分型態只看賽事快照的 `score_type`，不依遊戲名稱分支：
  - `win_loss`：只選勝方（a 或 b），沒有數字比分。
  - `rounds`：兩隊各一個非負整數，勝方為數字大的一方；平手 → `tie`；負數 → `invalid_score`。
- 局號從 1 開始連續：
  - 新增只能是下一局（目前局數＋1）；任一隊已達勝局門檻 → `series_decided`；其他局號 → `invalid_game_no`。
  - 覆寫已登錄的局（局號 ≤ 目前局數）可以，系列結果重算。
  - 覆寫後若某一隊在最後一局之前就已達門檻（後面的局變成多餘）→ 拒絕，`redundant_games`（使用者 2026-10-29 決定）。
  - 送出前可以刪除最後一局，讓裁判先刪掉多餘的局再修改；只能刪最後一局，刪其他局 → `not_last_game`；沒有任何局 → `invalid_game_no`。
- 系列結果：兩隊各自的勝局數、勝方（達門檻的一方，未達為 None）、能不能送出（＝已有勝方）。
- 不能送出時，原因 `not_decided` 附上勝局門檻 N，供 5.4 寫「任一隊拿到 {N} 勝後才能送出」。

**Never:**
- 不碰資料庫、不 import 其他模組、不讀時鐘。
- 不檢查身分、報到狀態、場次狀態、賽事是否仍可接受比分（service 負責）。
- 不做分輪 BO（2.3 擱置）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 勝局門檻 | BO 1／3／5／7 | 1／2／3／4 | BO 為其他值 → `ValueError` |
| 勝負型態 | `win_loss`、勝方 a | 一局，a 勝 | N/A |
| 回合型態 | `rounds`、13：11 | 一局，a 勝 | N/A |
| 平手 | `rounds`、12：12 | 拒絕 | `tie` |
| 負數 | `rounds`、-1：13 | 拒絕 | `invalid_score` |
| 型態不符 | `win_loss` 卻給數字，或 `rounds` 少一邊 | 拒絕 | `invalid_score` |
| 新增下一局 | BO3、已登錄 1 局 | 可以登錄第 2 局 | N/A |
| 跳號 | BO3、已登錄 1 局、局號 3 | 拒絕 | `invalid_game_no` |
| 已達門檻 | BO3、a 已 2 勝 | 不能新增第 3 局 | `series_decided` |
| 覆寫 | BO3、a、b 各 1 勝，把第 1 局改成 b 勝 | 可以，系列 b 2 勝 | N/A |
| 覆寫造成多餘的局 | BO3、a、b、a，把第 1 局改成 b 勝 | 拒絕 | `redundant_games` |
| 刪除最後一局 | BO3、a、b、a，刪第 3 局 | 剩 a、b，之後可把第 1 局改成 b 勝 | N/A |
| 刪除非最後一局 | BO3、a、b、a，刪第 1 局 | 拒絕 | `not_last_game` |
| 系列結果 | BO5、a、b、a、a | a 3 勝、b 1 勝、勝方 a、可送出 | N/A |
| 未達門檻 | BO5、a、b | 不能送出 | `not_decided`，門檻 3 |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/scoring.py` -- 新檔：純函式。第二階段的 `record_game()`、`submit_result()`、Score entry panel 的系列結果預覽都用它
- `backend/app/modules/competition/models.py` -- 本階段不改；Game 資料表在第二階段新增
- `backend/tests/competition/test_bracket.py` -- 測試寫法參考（4.1，尚未合併時參考 PR #4）

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/scoring.py` -- 新增 `ScoreType`（`win_loss`、`rounds`）、`GameResult`（frozen dataclass：`winner` 為 `"a"`／`"b"`、`score_a`、`score_b` 可為 None）、`wins_needed(bo)`、`make_game(score_type, *, winner=None, score_a=None, score_b=None) -> GameResult | ScoreReason`、`check_record(games, *, bo, game_no, result) -> ScoreReason | None`、`check_delete(games, *, game_no) -> ScoreReason | None`、`Series`（`wins_a`、`wins_b`、`winner`、`can_submit`、`wins_needed`）與 `series(games, *, bo)`、匯出的 `ScoreReason` Literal 別名 -- 讓 service 與前端用同一套規則
- [x] `backend/tests/competition/test_scoring.py` -- I/O 矩陣每一列；BO 1～7 隨機各局序列的性質測試；分支覆蓋率 ≥ 90% -- AC

**Acceptance Criteria:**
- Given 任一 BO 與任一串依 `check_record` 允許而登錄的局，when 計算 `series`，then 兩隊勝局數都不超過門檻、最多一隊達門檻，且達門檻的那一局就是最後一局。
- Given `series(...).can_submit` 為 False，when 依 `check_record` 新增下一局，then 允許；為 True 時新增被拒絕。

## Implementation Notes

- `scoring.py` 只 import `collections.abc`、`dataclasses`、`typing`；測試以 AST 檢查。
- 系列勝方取「依局號先達門檻的一方」；`check_record` 覆寫時把該局換掉再找達門檻的那一局，若不在最後一局 → `redundant_games`。
- `Series.reason`：不能送出時為 `not_decided`（門檻用 `wins_needed`）；已存的局在決定勝負之後還有局時為 `redundant_games`，此時勝方為 None、不能送出。
- `GameResult` 建立時就檢查：勝方只能是 a／b；比分都沒有，或都是非負整數、不平手且勝方分數較高，否則 `ValueError`。
- `check_record` 拒絕在同一系列混用有比分與沒比分的局（`invalid_score`）；`bo` 必須是非 bool 的整數（否則 `ValueError`），`game_no` 不是非 bool 的整數時回 `invalid_game_no`。
- 以下規格沒寫死，先這樣做，待確認：
  - 已達門檻時，局號＝目前局數＋1 回 `series_decided`；更大的局號仍回 `invalid_game_no`。
  - `check_delete` 局號不存在（0、負數、大於局數）回 `invalid_game_no`，只有存在但非最後一局才回 `not_last_game`。
  - `rounds` 型態若同時給 `winner` 視為型態不符（`invalid_score`）；bool、小數、字串比分也是 `invalid_score`；先檢查負數再檢查平手。
  - 未知的 `score_type` 與 BO 一樣丟 `ValueError`（賽事設定或程式錯誤）；裁判輸入的問題一律回傳 `ScoreReason`。
- 性質測試：BO 1／3／5／7 各 200 個種子、每個 80 步隨機登錄／覆寫／刪除（含不合法局號），以獨立的計數規則比對每次判定，並在每一步後檢查兩條 AC。
- 另有依 AC 手寫的字面案例表（不經獨立規則推算）；多餘局的隨機測試跑 BO3／5／7。
- 驗證：134 個測試通過；`scoring.py` 分支覆蓋率 100%；ruff、mypy 通過。突變測試：拿掉 `redundant_games` 檢查 → 5 個失敗；門檻改成 `bo // 2` → 多個失敗。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 11 項、Edge Case Hunter 6 項、Verification Gap 1 個缺口。沒有需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Edge、Blind | `GameResult` 可以直接建出勝方是 c、或勝方與比分矛盾的局 | medium | `check_record` 不再檢查就收下。patch：`__post_init__` 驗證 |
| 2 | Edge、Blind | 資料庫裡已有多餘的局時，`series` 仍回傳可送出 | medium | 例如 BO3 a、a、b 回傳 a 勝、可送出。patch：回傳不可送出、原因 `redundant_games` |
| 3 | Edge、Blind | 同一個系列可以混入不同比分型態的局 | low | patch：與既有的局型態不同時回 `invalid_score` |
| 4 | Blind、Edge | `wins_needed(3.0)` 回傳浮點數；局號是 bool 或小數時行為不一致 | low | patch：BO 與局號都必須是整數 |
| 5 | Blind | 模組說前端直接使用同一套結果，錯誤處理方式也沒寫 | low | patch：改寫 docstring，前端經第二階段 API 取得結果；設定錯誤拋 `ValueError`、裁判輸入回原因代碼 |
| 6 | Blind | 性質測試的預期邏輯與程式分支相同 | low | 同 5.5 的教訓。patch：另加手寫的固定案例表；`test_overwrite` 改經 `check_record`；多餘局測試涵蓋 BO3、BO7 |
| 7 | VG、Blind | `win_loss` 給 0 分、明確 `winner=None`、回合 0：0 沒有測試 | low | 改成以真假值判斷時測試不會失敗。patch：補測試 |
| 8 | Edge、Blind | 回合數沒有上限，寫入資料庫可能溢位 | defer | 第二階段的 API schema 設範圍；已記入 deferred-work |

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/scoring.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過

**結果（2026-10-29，第 1 輪修正後）：**
- `scripts/test.sh`：387 passed；整體覆蓋率 95%。
- `scoring.py` 分支覆蓋率 100%（95 行、52 個分支）。
- `scripts/lint.sh`：ruff check、ruff format、mypy 全部通過。
- Mutation 驗證：拿掉「多餘的局」檢查 → 11 個測試失敗；勝局門檻改成 BO ÷ 2 → 30 個測試失敗。還原後 134 個全過。
