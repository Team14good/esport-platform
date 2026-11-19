---
title: 'Story 4.2：報名截止時自動抽籤'
type: 'feature'
created: '2026-11-19'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-draw-backend.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 期中版（〈期中範圍〉規則 5）報名截止後賽事停在「報名截止」，要等主辦方按「抽籤」才會公布賽程；主辦方沒守在電腦前，賽程就一直不公布（epics Story 4.2、NFR-4）。

**Approach:** 新增 worker 工作 `auto_draw_closed`，排在 `close_registrations` 之後：找出「報名截止、還沒抽籤、開賽時間未到」的賽事，鎖住後呼叫與 4.1 手動抽籤共用的產生對戰表函式，操作者為系統（`None`）。所以 `close_registrations`（含 3.6 截止補位）關閉的賽事，在同一個 worker 週期內就轉為「賽程已公布」。正取不足 2 隊時不抽籤、發一次事件給主辦方。

## Decisions（2026-11-19，黃鉅燊派工內容）

- 操作者記為系統：`actor_id=None`，與 3.4、3.6、5.2 等 worker 動作一致（`bracket.drawn`、`tournament.status_changed`、`registration.status_changed` 的操作者都是 `None`）。
- 「同一個抽籤 service」：把 `draw()` 在檢查與分配之後的部分（排序、`bracket.plan/assign`、排時間、棄權計時、`mark_drawn`、轉「賽程已公布」、操作紀錄、`BracketDrawn`）抽成私有函式，手動與自動共用；手動抽籤的檢查順序、錯誤碼與行為不變。
- 正取不足 2 隊：不抽籤，賽事維持「報名截止」，在同一交易發 `AutoDrawSkipped(tournament_id, accepted_teams)` 事件（1.6 擱置，只發事件、不登錄收件規則），並寫操作紀錄 `bracket.auto_draw_skipped`。
- 事件只發一次：competition 新增資料表 `auto_draw_skip`，以（`tournament_id`, `registration_end`）為唯一鍵記下「這一次報名截止已判定不足」；之後的週期不再選它。用 `registration_end` 當鍵是為了期末的 S28 延長報名（2.5）：延長後報名截止時間改變，再次截止時會重新嘗試，不需要改本 Story 的程式。
- 主辦方仍可手動抽籤：不足 2 隊的賽事按「抽籤」照 4.1 回 `NOT_ENOUGH_TEAMS`；S27 不改。
- 開賽時間已過的「報名截止」賽事不是候選（`_draw_blocked` 的 `start_passed`），不發事件。
- 部署時已停在「報名截止」、還沒抽籤的既有賽事，也會在第一個週期被自動抽籤（與驗收條件一致；示範資料與 e2e 都是開放報名中提前抽籤，不受影響）。

## Boundaries & Constraints

**Always:**
- 鎖的順序沿用 AD-6：先 `lock_tournament`，鎖內重新檢查「`closed`、沒有對戰表、開賽未到、沒有同一 `registration_end` 的略過紀錄」，不成立就不做任何事；手動與自動同時進行時只會抽一次。
- 每個候選在 savepoint 裡處理；某一場拋錯時記錄錯誤、略過它，改處理下一個候選（不重蹈 deferred-work「`close_registrations` 被一直拋錯的第一場卡住」）。
- 候選由 tournaments 新增的公開函式 `list_closed_tournament_ids(session)` 找（`closed` 且 `start_at > now`，依 `registration_end`、id 排序，不加鎖）；competition 不直接查 tournament 表。
- 測試以 `frozen_clock` 推進時間（AD-13），不等真實時間。

**Never:**
- 不做 S28 延長報名（2.5）與取消賽事（2.6）；不做 1.6 的通知規則；不改前端。
- 不改 registration、tournaments 的既有函式（CONTRIBUTING 6.6），只新增 tournaments 公開函式與 repository 查詢。
- 不改 `close_registration` 的交易：關閉與抽籤是兩個工作、兩個交易，抽籤失敗不會讓報名截止回滾。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 截止後同一週期抽籤 | 開放報名、正取 3 隊、時鐘推到報名截止；跑一輪 `JOBS` 的截止＋自動抽籤 | 賽事 `published`；對戰表 3 隊；`bracket.drawn` 操作者 `None`；`BracketDrawn` 1 則；3 隊 `drawn` | N/A |
| 正取不足 | 報名截止後正取 1 隊（或 0 隊） | 賽事維持 `closed`、沒有對戰表；`AutoDrawSkipped` 1 則（`accepted_teams` = 1）；略過紀錄 1 筆 | 不拋錯 |
| 重跑 | 上一列之後再跑兩輪 | 沒有新事件、新略過紀錄或操作紀錄；工作回傳 False | N/A |
| 重複抽籤 | 已自動抽籤後再跑工作；或對同一賽事直接呼叫兩次 | 第二次不做任何事 | N/A |
| 手動與自動競爭 | 兩條連線同時手動 `draw` 與自動抽籤同一場 | 只有一份對戰表；一方成功，另一方回 `BRACKET_ALREADY_DRAWN` 或不做任何事 | N/A |
| 開賽已過 | `closed`、`start_at <= now` | 不是候選；不抽籤、不發事件 | N/A |
| 其他狀態 | `open`、`upcoming`、`published` 等 | 不是候選 | N/A |
| 一場拋錯 | 兩個候選，第一個抽籤時拋錯 | 第一個回滾並記錄錯誤；第二個照常抽籤 | savepoint |

</frozen-after-approval>

## Code Map

- `backend/app/worker/jobs.py` -- `JOBS`；新增 `auto_draw_closed`，排在 `close_registrations` 之後、`start_due_tournaments` 之前。
- `backend/app/modules/competition/service.py` -- `draw()`（約 321 行）、`_draw_blocked`、`_MIN_DRAW_TEAMS`；抽出 `_create_bracket`；新增 `auto_draw(session, *, tournament_id)`、`auto_draw_due(session)`（照 `start_due_tournament` 的 skipped＋savepoint 模式）。
- `backend/app/modules/competition/models.py` -- 新增 `AutoDrawSkip`（table）、`AutoDrawSkipped`（事件）。
- `backend/app/modules/competition/repository.py` -- 新增略過紀錄的查詢與新增。
- `backend/app/modules/competition/registration_port.py` -- `mark_drawn` 的 `actor_id` 改為 `uuid.UUID | None`（registration 的 `mark_status` 已接受 `None`）。
- `backend/app/modules/tournaments/service.py`、`repository.py` -- 新增 `list_closed_tournament_ids`（只新增，B 的模組）。
- `backend/app/alembic/versions/` -- 新遷移 `auto_draw_skip`，down_revision `f2b6d8a1c3e5`。
- 測試：`backend/tests/competition/test_auto_draw.py`（服務層＋worker）、`test_auto_draw_concurrency.py`（兩條連線）；`tests/traceability.yaml` 登記。

## Tasks & Acceptance

**Execution:**
- [x] `competition/models.py`、遷移 -- 新增 `AutoDrawSkip`、`AutoDrawSkipped`
- [x] `tournaments/repository.py`、`service.py` -- `list_closed_tournament_ids`
- [x] `competition/service.py` -- 抽出 `_create_bracket`；`auto_draw`、`auto_draw_due`
- [x] `worker/jobs.py` -- `auto_draw_closed` 加進 `JOBS`
- [x] 測試 -- I/O 矩陣每一列；手動與自動競爭用真實提交的兩條連線

**Acceptance Criteria:**
- Given 報名截止時間已到，when worker 跑一輪，then 同一輪內完成截止補位與抽籤，賽事為「賽程已公布」，操作者為系統。
- Given 4.1 的既有測試，when 重構後執行，then 全部通過（手動抽籤行為不變）。

## Implementation Notes

- 2026-11-19 實作（Claude Code，依派工內容自行定 Decisions，沒有經過 Checkpoint 1 的人工核准；PR 為 Draft，請 D 本人核准 spec 後再改 ready）。
- `draw()` 只把「確認正取至少 2 隊」之後的部分搬進 `_create_bracket`，程式碼本身沒有改；4.1 既有測試（`test_draw.py`、`test_draw_status.py`、`test_bracket_api.py`）照跑通過。
- `auto_draw` 鎖內檢查重用 `_draw_blocked`（已抽籤、狀態、開賽已過），另外要求狀態必須是 `closed`：`open` 的賽事交給 `close_registrations` 先關閉，自動抽籤不做提前抽籤。
- `registration_port.mark_drawn` 的 `actor_id` 型別放寬為 `uuid.UUID | None`；registration 的 `mark_drawn` 本身沒改（它把 `actor_id` 傳給已接受 `None` 的 `mark_status`），所以沒有動到 C 的函式。
- 動到 B 的 tournaments：只新增 `service.list_closed_tournament_ids` 與 `repository.list_closed_before_start_ids`。
- 動到 A 的 worker 測試：`tests/worker/test_email_pipeline.py` 的 `JOBS` 順序清單加上 `auto_draw_closed`。
- 測試資料庫裡有其他併發測試提交後留下、狀態為「報名截止」的賽事（`test_settlement_concurrency.py` 中報名截止的那幾組），`auto_draw_due` 會一起處理到（都在測試的外層交易裡、結束時回滾）；新測試的斷言一律只看自己建立的賽事。
- 審查（1 個子代理，只讀程式）提出 6 點、沒有 high，處理如下：
  1. （medium）`AutoDrawSkipped` 期中只寫進 outbox，worker 的 `dispatch_outbox` 找不到處理程式就標為已處理，主辦方實際收不到，之後補 1.6 也不會補發。這就是〈期中範圍〉規則 2 的既定做法（「期中已發出的事件不補發」），不改程式；記進 deferred-work，1.6 時決定要不要改為「送達後才記略過」。
  2. （low）某場賽事每輪都抽籤失敗時只寫 log，主辦方看不到；與 `start_due_tournament` 相同模式，記進 deferred-work。
  3. （low）已判定不足的賽事每輪都被 `lock_tournament`：已修正，`auto_draw_due` 先以不加鎖的讀取排除有略過紀錄的賽事，鎖內仍再查一次。
  4. （low）registration 的 `mark_drawn` 型別註記仍是 `uuid.UUID`：不改 C 的函式（CONTRIBUTING 6.6），在 contracts/competition.md 註明，請 C 之後放寬。
  5. （low）併發測試靠 Barrier 同時起跑，不保證每次交錯在讀寫之間：測試說明改寫為機率性偵測；服務層另有「先手動後自動」「先自動後手動」的確定性測試。
  6. （low）`auto_draw` 只看狀態是 `closed`、不看報名截止時間：延長報名（2.5）照 `_TRANSITIONS` 應轉回 `open`，記進 deferred-work 提醒 2.5 必須轉回 `open`。
- 驗證（2026-11-20，worktree 掛進 backend 容器，測試資料庫 `app_story42_test`）：
  - 全部後端測試：2434 passed、1 failed（`test_smtp_sender_delivers_to_mailpit_from_flow`，本次只啟動 db、沒啟動 mailpit，連不上 SMTP，與本 Story 無關）。
  - 審查修正後重跑 `tests/competition tests/worker tests/tournaments tests/registration` 加架構、遷移、追溯、模組結構測試：1876 passed。
  - `scripts/lint.sh`（mypy、ty、ruff check、ruff format --check）通過；新測試檔 ruff、mypy 通過。
  - 變異測試：把 `auto_draw_closed` 改成直接回 False，`tests/worker/test_auto_draw.py` 3 項中 2 項失敗；還原後 29 項（4.2 相關＋`test_email_pipeline`）通過。
- `epic-4-context.md` 依 git 規則判斷為過期（之後有 #50 與 #1 動到 planning-artifacts，前者只改規則 6），本次沒有重新產生，直接讀 epics.md 的 Story 4.2 與〈期中範圍〉。
- 前端不改：自動抽籤後 S27 的抽籤區塊依既有的抽籤狀態 API 消失；正取不足時仍顯示「正取不足 2 隊，無法抽籤」。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose exec -T backend pytest tests/competition tests/worker tests/tournaments tests/registration tests/test_architecture.py tests/test_migrations.py` -- expected: 全部通過
- `docker compose exec -T backend bash scripts/lint.sh`（或 README 的 lint 指令） -- expected: ruff、mypy 無錯誤
