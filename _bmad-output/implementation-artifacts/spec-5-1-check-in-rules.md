---
title: 'Story 5.1（第一階段）：隊長報到的時間規則'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '3370be6fe74b776ce528d264b3128196bca04c39'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 5.1 要讓兩隊隊長在開賽前 30 分鐘起報到，兩隊未確定時拒絕，並在最早場次的報到時間到了時把賽事轉為「進行中」；但 Match 資料表與 Tournament（B 的 2.2）還不存在，`check_in()`、S4 與 worker 都還不能做。

**Approach:** 先在 competition 寫不碰資料庫的純函式：報到開放時間、能不能報到（回傳原因代碼）、賽事開始時間。第二階段的 service 在鎖定場次後用它判斷，再寫入報到紀錄；S4 的 Check-in panel 用同一套原因顯示停用說明。

## Boundaries & Constraints

**Always:**
- 報到開放時間＝預定開始時間－30 分鐘；剛好等於開放時間可以報到。
- 拒絕的原因與檢查順序：兩隊尚未都確定 → `teams_pending`（對應 API 代碼 `MATCH_TEAMS_PENDING`）；本隊已報到 → `already_checked_in`；早於開放時間 → `too_early`；已過棄權期限 → `closed`。
- 棄權期限已過就不能報到（使用者 2026-10-29 決定：期限一到就不能報到，結果不取決於 worker 何時執行），即使 worker 還沒來得及判棄權。
- 賽事開始時間＝所有場次中最早的預定開始時間－30 分鐘；沒有場次時拋 `ValueError`。
- 所有 datetime 都必須帶時區，沒有時區拋 `ValueError`；時間比較與加減先轉 UTC。
- 不讀時鐘：「現在」由呼叫端傳入。

**Never:**
- 不碰資料庫、不 import 其他模組。
- 不判斷誰是隊長、不檢查場次狀態（service 用 `is_captain` 與 `MatchStatus` 檢查）。
- 不判棄權（5.2 由 A 負責）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 開放時間 | 預定 13:00 | 12:30 | N/A |
| 剛好開放 | 現在 12:30、預定 13:00、兩隊確定、未報到 | 允許 | N/A |
| 太早 | 現在 12:29 | `too_early`，並可取得開放時間 12:30 | 回傳原因代碼 |
| 兩隊未確定 | 兩隊未確定、現在 12:45 | `teams_pending`（優先於其他原因） | 回傳原因代碼 |
| 已報到 | 本隊已報到、現在 12:45 | `already_checked_in` | 回傳原因代碼 |
| 過了預定時間 | 現在 13:10、棄權期限 13:15 | 允許 | N/A |
| 剛好在期限 | 現在 13:15、棄權期限 13:15 | `closed` | 回傳原因代碼 |
| 賽事開始時間 | 場次 13:00、10:00、11:00 | 09:30 | N/A |
| 沒有場次 | 空清單 | — | `ValueError` |
| 沒有時區 | 任何輸入是 naive datetime | — | `ValueError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/checkin.py` -- 新檔：純函式。第二階段的 `check_in()`、S4 Check-in panel、worker 的 `start_tournament` 都用它
- `backend/app/modules/competition/schedule.py` -- 4.3 的 `forfeit_deadline()` 算出棄權期限；本檔只接收算好的值，不 import（4.3 尚未合併）
- `backend/tests/core/test_clock.py` -- 帶時區 datetime 的測試寫法參考

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/checkin.py` -- 新增 `CHECK_IN_LEAD`（30 分鐘的 `timedelta`）、`check_in_opens_at(scheduled_at)`、`check_check_in(*, now, scheduled_at, teams_known, already_checked_in, forfeit_deadline) -> CheckInReason | None`（`forfeit_deadline` 在兩隊未確定時為 None）、匯出的 `CheckInReason` Literal 別名、`tournament_starts_at(scheduled_times)` -- 讓 service、S4 與 worker 用同一套規則
- [x] `backend/tests/competition/test_checkin.py` -- I/O 矩陣每一列；邊界值；分支覆蓋率 ≥ 90% -- AC

**Acceptance Criteria:**
- Given 任一組輸入，when 呼叫 `check_check_in`，then 回傳 None 若且唯若 兩隊確定、本隊未報到、開放時間 ≤ 現在 < 棄權期限。
- Given 兩隊未確定、輸入都帶時區，when 呼叫 `check_check_in`，then 不論其他輸入都回傳 `teams_pending`。

## Implementation Notes

- `check_check_in` 先驗證所有 datetime 都帶時區，再依序檢查原因；所以兩隊未確定但傳入 naive datetime 時拋 `ValueError`，不回傳 `teams_pending`（矩陣「任何輸入是 naive」優先）。
- 兩隊已確定卻沒給 `forfeit_deadline`，或期限不晚於開放時間（報到窗口永遠不會打開），視為呼叫端錯誤，拋 `ValueError`。因此「太早」與「已截止」不會同時成立，兩者的檢查順序無法從外部觀察。
- `tournament_starts_at` 直接呼叫 `check_in_opens_at`，兩處共用同一個公式。
- `tzinfo` 存在但 `utcoffset()` 為 None 也視為沒有時區。
- 回傳的時間（開放時間、賽事開始時間）一律是 UTC；加減先轉 UTC，所以跨日光節約時實際相差 30 分鐘，不是牆上時間 30 分鐘。
- `CheckInReason` 用 `type` 敘述定義（`TypeAliasType`），取值用 `get_args(CheckInReason.__value__)`。
- 測試：I/O 矩陣、開放與期限的邊界、America/New_York 日光節約（春季跳時與秋季重複時段的 fold=0／1）、5000 組固定種子的隨機輸入依 spec 順序算出確切原因並比對、AST 檢查只 import `collections.abc`、`datetime`、`typing` 且不呼叫 `now`／`utcnow`／`today`；每個 `ValueError` 測試都用 `match=` 指定分支。分支覆蓋率 100%；把期限比較改成 `>`、開放比較改成 `<=`、提前時間改成 29 分鐘、不轉 UTC 直接相減、對調「已報到」與「太早」的順序，都會讓測試失敗。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 9 項、Edge Case Hunter 5 項、Verification Gap 2 個缺口＋1 項其他。沒有需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | VG、Blind | 調換 `too_early` 與 `closed` 的順序，沒有測試會失敗 | medium | 性質測試只比對允許與否。patch：性質測試依 spec 順序算出預期原因並比對 |
| 2 | Blind、Edge | 棄權期限早於開放時間時，回傳「太早」但永遠不會開放 | low | 實際的棄權期限一定不早於預定時間（4.3 `forfeit_deadline`），屬於呼叫錯誤。patch：拋 `ValueError` |
| 3 | VG、Edge | 兩隊未確定時傳入沒有時區的時間會拋錯，與 AC2「不論其他輸入」字面不符，也沒有測試 | low | 程式先驗證輸入是刻意的（I/O 矩陣「任何輸入是 naive → ValueError」）。patch：AC2 改為「輸入都帶時區」，補測試 |
| 4 | Blind | 沒有測試保證不讀時鐘 | low | import 白名單擋不住 `datetime.now()`。patch：AST 檢查不呼叫 now／utcnow／today |
| 5 | Blind | 夏令時間結束的重複小時沒有測試 | low | patch：補 fold=0／1 的案例 |
| 6 | Blind | `tournament_starts_at` 重複寫一次開放時間公式 | low | patch：改呼叫 `check_in_opens_at` |
| 7 | Blind | `pytest.raises(ValueError)` 沒有 `match=`，別的原因拋錯也會通過 | low | patch |
| 8 | Blind | 模組沒有定義棄權期限的算法 | false | 棄權期限由 4.3 的 `forfeit_deadline()` 計算，本模組刻意只接收結果（Code Map） |
| 9 | Blind | 只有 `teams_pending` 對應到 API 代碼 | false | API 代碼與 `BusinessError` 在第二階段的 service 定義 |
| 10 | Edge | 接近 `datetime.min` 時溢位 | false | 預定時間來自賽事設定，不可能接近西元 1 年 |
| 11 | Edge | 兩隊已確定但沒有棄權期限時，先拋錯而不是回「已報到」 | false | 兩隊確定時 `start_forfeit_clock` 一定已設定期限；缺少是呼叫錯誤 |

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/checkin.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過

**結果（2026-10-29，第 1 輪修正後）：**
- `scripts/test.sh`：291 passed；整體覆蓋率 95%。
- `checkin.py` 分支覆蓋率 100%（35 行、16 個分支）。
- `scripts/lint.sh`：ruff check、ruff format、mypy 全部通過。
- Mutation 驗證：「剛好在期限」改成仍可報到 → 2 個測試失敗；提前 30 分鐘改成 29 分鐘 → 12 個測試失敗。還原後 38 個全過。
