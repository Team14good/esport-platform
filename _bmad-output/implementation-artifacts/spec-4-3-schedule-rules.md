---
title: 'Story 4.3（第一階段）：排定與修改場次時間的規則'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '38400e8be8cd6574fb20b8da52bc181c41f9df89'
route: 'dispatch'
review_loop_iteration: 2
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.3 要依開賽日期與每輪間隔排定場次時間、讓主辦方在範圍內修改時間，但 Tournament（B 的 2.2）與 Match 資料表還不存在，`schedule()`、`reschedule()` 與 S30 都還不能做。

**Approach:** 先在 competition 寫不碰資料庫的純函式：各輪開始時間（含順延下限與提示）、棄權期限、修改時間的允許範圍與檢查。第二階段（另一份 spec）在 service 裡用它們寫入 Match、寫操作紀錄並做 S30。

## Boundaries & Constraints

**Always:**
- 同一輪所有場次同一時段；第 1 輪＝開賽時間；第 r＋1 輪＝第 r 輪開始＋max（每輪間隔, 第 r 輪的最小間隔）。最小間隔＝棄權時限＋該輪 BO × 每局預估時間＋申訴期。
- 最小間隔大於每輪間隔時，下一輪標記為「已順延」，並帶出最小間隔與順延的分鐘數，供 S27 提示主辦方。
- 季軍賽與決賽同輪，同一時段。
- 棄權期限＝max（預定開始時間, 兩隊確定的時間）＋棄權時限。
- 修改時間的允許範圍考慮比賽本身的長度（使用者 2026-10-29 決定）：
  - 最早＝max（現在, 餵給本場的前一輪場次中最晚的預定時間＋該輪最小間隔）；第一輪沒有前一輪，只看現在。
  - 最晚＝勝隊要去的下一場的預定時間－本場的最小間隔；決賽與季軍賽沒有上限。
  - 等於邊界可以。最早晚於最晚時，沒有可選的時間。
- 所有 datetime 都必須帶時區；收到沒有時區的時間拋 `ValueError`。時間加減一律先轉成 UTC 再算，避免有夏令時間的時區少算或多算一小時。
- 不讀時鐘：「現在」由呼叫端傳入。

**Never:**
- 不碰資料庫、不 import 其他模組。
- 不自動把同一輪分批。
- 不檢查場次狀態與報到（第二階段的 service 與 5.1 負責）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 間隔足夠 | 4 輪、間隔 120 分、棄權 15、BO1、每局 40、申訴 30（最小 85） | 各輪相差 120 分鐘，都沒有順延 | N/A |
| 間隔不足 | 間隔 90、BO3、每局 40、棄權 15、申訴 30（最小 165） | 第 2 輪起相差 165 分鐘，標記已順延 75 分鐘 | N/A |
| 各輪 BO 不同 | BO 依輪傳入 [1, 1, 3] | 只有第 3 輪之後的間隔用 BO3 計算 | N/A |
| 1 輪（2 隊） | rounds=1 | 只有第 1 輪＝開賽時間 | N/A |
| 棄權期限 | 預定 13:00、兩隊 13:20 才確定、棄權 15 | 13:35 | N/A |
| 修改時間在範圍內 | 現在 10:00、下一場 14:00、本場最小間隔 85 分、新時間 12:35 | 允許（剛好等於最晚） | N/A |
| 早於現在 | 新時間 09:59、現在 10:00 | 拒絕，`before_now` | 回傳原因代碼 |
| 晚於最晚 | 新時間 12:36、下一場 14:00、本場最小間隔 85 分 | 拒絕，`after_next_match` | 回傳原因代碼 |
| 早於前一輪結束 | 前一輪場次 11:00 與 11:30、該輪最小間隔 85 分、現在 10:00、新時間 12:54 | 拒絕，`before_feeder`（最早 12:55） | 回傳原因代碼 |
| 沒有可選時間 | 最早晚於最晚 | 拒絕，`no_valid_time`；範圍標示為空 | 回傳原因代碼 |
| 決賽或季軍賽 | 下一場為 None、新時間任意晚 | 允許 | N/A |
| 有夏令時間的時區 | 開賽時間用 `America/New_York`，跨過夏令時間切換 | 各輪實際相差的分鐘數仍等於規則 | N/A |
| 沒有時區 | 任何輸入是 naive datetime | — | `ValueError` |
| 輪數或分鐘數不合理 | rounds < 1、BO 數量與輪數不符、分鐘數為負 | — | `ValueError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/schedule.py` -- 新檔：純函式。第二階段 service 的 `schedule()`、`reschedule()`、`start_forfeit_clock()` 與 S30 時間選擇器的範圍都用它
- `backend/app/core/clock.py` -- 不使用；「現在」由呼叫端傳入，service 會傳 `clock.now()`
- `backend/app/modules/competition/models.py` -- 本階段不改
- `backend/tests/core/test_clock.py` -- 帶時區 datetime 的測試寫法參考
- `_bmad-output/planning-artifacts/epics.md` 的 Story 2.2 -- 最小間隔例子：每局 40、BO1、棄權 15、申訴 30 → 85 分鐘

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/schedule.py` -- 新增 `RoundStart`（frozen dataclass：`round_no`、`start_at`、`required_gap`、`delayed_by`）、`round_min_gap()`、`plan_round_starts()`、`forfeit_deadline()`、`check_reschedule()`（回傳 `None` 或原因代碼 `"before_now"`／`"before_feeder"`／`"after_next_match"`／`"no_valid_time"`）與 `reschedule_window()`（輸入現在、下一場時間、本場最小間隔、前一輪場次時間與該輪最小間隔；回傳最早、最晚（可為 None）與是否為空）。`forfeit_deadline()` 的 docstring 註明兩隊都確定後才呼叫 -- 讓 service 與前端時間選擇器用同一套範圍
- [x] `backend/tests/competition/test_schedule.py` -- I/O 矩陣每一列；邊界值（剛好等於現在、剛好等於下一場）；分支覆蓋率 ≥ 90% -- AC

**Acceptance Criteria:**
- Given 任一輪數 1～6 與任意合法設定，when 呼叫 `plan_round_starts`，then 回傳的輪數正確、開始時間嚴格遞增、相鄰兩輪的差距都不小於前一輪的最小間隔。
- Given `reschedule_window` 回傳的範圍，when 以範圍內任一時間呼叫 `check_reschedule`，then 允許；範圍外則拒絕，兩者結果一致。

## Implementation Notes

- `required_gap`、`delayed_by` 與 `round_min_gap()` 都用整數分鐘，S27 可直接顯示；第 1 輪兩者為 0。`RoundStart.is_delayed` 表示已順延。
- `best_of` 可傳單一整數（期中所有輪次同一個 BO）或依輪傳入的序列；第 r 輪的 BO 只影響第 r 與 r＋1 輪之間的間隔。
- 每輪間隔必須至少 1 分鐘：為 0 時若最小間隔也為 0（每局預估 0 分鐘等），開始時間不會嚴格遞增，違反 AC。
- `reschedule_window()` 回傳 `RescheduleWindow(earliest, latest)`（NamedTuple，可解構）；下一場早於現在時範圍為空，`check_reschedule` 對任何時間都拒絕，兩者仍一致。
- 新增 `tests/competition/__init__.py`，與其他測試目錄一致。

## Spec Change Log

- 第 1 輪審查（2026-10-29）：Blind Hunter 指出修改時間的範圍沒有考慮比賽長度，可以把一場改到與勝隊下一場同時開始，或把準決賽改到 8 強賽之前。屬於需求缺口，請使用者決定，使用者選「上下限都扣比賽長度」。已寫進 frozen 區塊與 I/O 矩陣，撤回程式重新實作。避免的錯誤狀態：S30 允許排出衝突的時間。KEEP：`RoundStart` 與 `plan_round_starts` 的介面與行為、整數分鐘、`ValueError` 的檢查、I/O 矩陣每列都有測試、逐輪數 1～6 的不變式測試、範圍與檢查一致的測試；不要寫只因 `range` 就必然成立的測試（第 1 輪的「季軍賽與決賽同時段」測試不可能失敗，已刪除）。

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 10 項、Edge Case Hunter 9 項、Verification Gap 0 個缺口＋3 項其他。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Blind | 修改時間上限沒扣本場長度，可與下一場同時開始 | high | `check_reschedule` 接受 new＝next。intent_gap：使用者選上下限都扣比賽長度，撤回重做 |
| 2 | Blind | 沒有下限：準決賽可改到 8 強賽之前 | high | 範圍只看現在。與 #1 同一個需求缺口 |
| 3 | Blind、VG | 範圍為空時回傳的原因誤導 | low | 下一場早於現在時回 `after_next_match`／`before_now`。隨 #1 改為 `no_valid_time` |
| 4 | Edge、Blind | 有夏令時間的時區，datetime 加減是牆上時間 | low | Python 對 ZoneInfo 的 aware datetime 加 timedelta 不換算 UTC。service 只傳 UTC、台灣無夏令時間，但修正只要先轉 UTC。寫進 frozen 區塊，重做時處理 |
| 5 | Blind | `forfeit_deadline` 沒說兩隊未確定時怎麼辦 | low | 呼叫端只在兩隊確定時呼叫。重做時補 docstring |
| 6 | Blind、VG | 「季軍賽與決賽同時段」測試不可能失敗 | low | round_no 來自 `range`，必然只出現一次。重做時不寫這個測試 |
| 7 | VG | 90% 分支覆蓋率只靠手動指令，CI 沒有強制 | low | CI 的 `scripts/test.sh` 沒開 branch；4.1 也一樣。defer |
| 8 | Edge、Blind | `best_of` 或分鐘數是 bool、str、float | false | 參數有型別標註，mypy／ty 會擋；service 從整數欄位取值 |
| 9 | Edge | 數值大到 datetime 溢位 | false | 分鐘數來自 2.2 驗證過的賽事設定，不可能接近溢位 |
| 10 | Edge | 最後一輪的 BO 有檢查但沒用到 | false | 不合法的 BO 本來就該拒絕，沒有可接受的 plan 被誤拒 |
| 11 | Blind | 沒有檢查場次狀態 | false | spec 的 Never 明訂由 service 與 5.1 檢查 |
| 12 | Blind | sprint 狀態跳過 ready-for-dev、沒有 story 檔 | false | spec 檔就是 story 檔，隨本次 commit 一起提交 |
| 13 | Blind | 新時間可以帶秒 | low | S30 時間選擇器以分鐘為單位，不常見且修正要加規則，reject |

第 2 輪（2026-10-29，重新實作後）：Blind Hunter 12 項、Edge Case Hunter 8 項、Verification Gap 2 個缺口＋1 項其他。沒有新的需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 14 | VG | `delayed_by` 的 `max(0, …)` 拿掉後沒有測試會失敗 | medium | `test_plan_sufficient_interval` 沒檢查 `delayed_by`。patch：斷言全為 0，不變式測試也檢查 `required_gap` 與 `delayed_by` |
| 15 | VG、Blind | 缺少驗證測試：負的 `feeder_min_gap`、負的間隔、BO 序列含 0、naive 的確定時間與下一場時間 | medium | 程式有檢查但沒測。patch：補 `ValueError` 測試 |
| 16 | Blind | 原因代碼的優先順序沒測 | low | 有前一輪場次時 new < now 應回 `before_now`；只因前一輪而範圍為空應回 `no_valid_time`。patch：補測試 |
| 17 | Edge | 傳了 `feeder_times` 卻忘了 `feeder_min_gap`，預設 0 會默默忽略前一輪長度 | medium | 預設值讓錯誤呼叫不會失敗。patch：拿掉兩個參數的預設值，第一輪由呼叫端明確傳 `()` 與 `0` |
| 18 | Blind | 原因代碼回傳 `str`，呼叫端打錯字不會被型別檢查擋 | low | patch：改成匯出的 `Literal` 別名 |
| 19 | Blind | `required_gap` 的 docstring 說是「實際採用的間隔」，實際上是規則要求的最小間隔 | low | patch：改 docstring；`plan_round_starts` 註明回傳 UTC |
| 20 | Blind、VG | deferred 項目寫到這個分支沒有的 bracket.py、缺嚴重度、CI 修法不完整 | low | patch：改寫該項目（本 Story 新增的項目，尚未提交） |
| 21 | Blind | sprint 註記沒說只完成第一階段 | low | patch：註記改為第一階段完成、第二階段待 2.2、4.1 |
| 22 | Edge、Blind | 分鐘數或 BO 是 bool、float、str；數值大到溢位 | false | 同第 1 輪 #8、#9 |
| 23 | Edge | `feeder_times` 傳空的 generator | false | 型別標註是 `Sequence`；generator 不是序列，service 傳 list |
| 24 | Blind | 沒有檢查場次是否已開始或已結束 | false | 同第 1 輪 #11 |

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/schedule.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過

**結果（2026-10-29，第 2 輪修正後）：**
- `scripts/test.sh`：336 passed；整體覆蓋率 95%。
- `schedule.py` 分支覆蓋率 100%（69 行、28 個分支）。
- `scripts/lint.sh`：ruff check、ruff format、mypy 全部通過。
- Mutation 驗證：拿掉 `delayed_by` 的 `max(0, …)` → 12 個測試失敗；把 `before_now` 移到 `no_valid_time` 之前 → 1 個測試失敗。還原後 83 個全過。
