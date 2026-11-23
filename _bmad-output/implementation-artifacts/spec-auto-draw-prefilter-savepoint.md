---
title: '自動抽籤的預先排除放進 savepoint'
type: 'bugfix'
created: '2026-11-23'
status: 'done'
baseline_commit: 'beb855f132f1b9b50544de5b6cfa08befeac6117'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #113 把 `auto_draw_due` 的預先排除 `_skipped_and_still_short` 放進 try、但在 `begin_nested()` 外面（A 在 #113 的行內建議）。拋 Python 例外時只略過這一場；拋 SQL 錯誤時 PostgreSQL 讓外層交易進入 aborted，同一輪之後每個候選的查詢都失敗，docstring 寫的「查詢拋錯只略過這一場」不成立。

**Approach:** 預先排除移進每個候選的 savepoint 內，SQL 錯誤只回滾那一場；docstring 照實寫。補一個「預先排除拋 SQL 錯誤時，下一場照常抽籤」的測試。擁有者 2026-11-23 指示「修」。

</frozen-after-approval>

## Implementation Notes

- `auto_draw_due`：預先排除 `_skipped_and_still_short` 移進每個候選的 `begin_nested()`；`outcome` 型別宣告移到 try 前；docstring 改為「預先排除與抽籤在同一個 savepoint 內，拋錯（含 SQL 錯誤）只回滾並略過這一場」。
- 新測試 `test_due_prefilter_sql_error_skips_only_that_tournament`：已有略過紀錄的賽事在預先排除查正取時執行 `SELECT 1 / 0`（真的 SQL 錯誤），下一場照常抽籤、略過紀錄保留。
- 驗證：`test_auto_draw.py`、`test_auto_draw_concurrency.py`、worker `test_auto_draw.py` 34 passed；ruff、mypy 通過。突變檢查：換回 `beb855f` 的 `service.py`，新測試 1 failed；換回修正後 1 passed。

## Review Triage Log

- 測試沒有斷言略過紀錄保留、沒有新事件 — low，patch（補兩個斷言）。
- 替身對「仍不足」那場回 3 隊，與情境不一致 — low，patch（回 1 隊）。
- `outcome` 型別只宣告在分支內 — low，patch（移到 try 前）。
- 沒證明錯誤來自預先排除 — false：`beb855f` 的 `auto_draw` 本來就在 savepoint 內，換回舊版時新測試失敗，失敗只可能來自 savepoint 外的預先排除。
- spec 沒有紅綠證據 — 已補在 Implementation Notes。
- 只對 `list_accepted_teams` 注入錯誤 — low，reject：三個查詢同在一個函式、一起移進 savepoint。
- `auto_confirm_expired` 同類問題 — 未驗證（若為真屬 medium），defer：非本次造成，已記 deferred-work。
- 壞掉的賽事每輪重試並記錄 — low，reject：與既有 `auto_draw` 拋錯行為相同，非本次造成。
- 每輪多一個 savepoint 的開銷 — low，reject。
- 缺 AI 使用紀錄 — 開 PR 前補。
