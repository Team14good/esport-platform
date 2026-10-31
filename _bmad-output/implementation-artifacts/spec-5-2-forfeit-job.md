---
title: 'Story 5.2（第二階段）：逾時判棄權的 worker 工作'
type: 'feature'
created: '2026-10-30'
status: 'done'
baseline_commit: '0c7ce97869613d462156c354e244d1b6b83c9dfb'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-2-forfeit-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段已經有 `judge_forfeit` 和 `appeal_deadline`，但還沒有任何程式會在期限過後真的判棄權並寫入結果，所以賽程會卡在未報到的場次。這一步要用的 Match 資料表，以及 `lock_match`、`list_forfeit_due`、`list_check_ins`、`transition_match`，都在 D 的 4.1、5.1，還沒合併；`lock_tournament` 也在 B 的範圍，同樣還沒合併。

**Approach:** 照使用者的決定，依 `contracts/competition.md` 的約定介面把 worker 工作完整寫好。用到的 D、B 函式不直接 import，而是透過一個介面（`ForfeitPorts`）注入。測試用記憶體中的假實作，搭配真的 session（操作紀錄與事件照常寫入測試資料庫）。等 D、B 的函式合併後，只要寫一個接上真函式的轉接層，再把工作註冊到 `app/worker/jobs.py`。

## Boundaries & Constraints

**Always:**
- 每次呼叫工作，最多判一場棄權，回傳是否判了一場；交易由 `app.worker.run_once` 負責。
  - 這個工作和其他工作一樣，不能 commit 或 rollback（AD-5）。
- 「現在」一律取 `app.core.clock.now()`，同一次呼叫裡只取一次。
- 處理流程：
  1. 依序走過 `list_forfeit_due(now)` 回傳的每一場。
  2. 取得該場所屬的賽事，先鎖賽事，再鎖場次（AD-6）。
  3. 用鎖住後的資料重新呼叫 `judge_forfeit`。賽事是否已取消、場次狀態、兩隊、棄權期限、報到名單，都以鎖住後的值為準。
  4. 結果是 None 就略過，看下一場。例如兩隊都已報到、賽事已取消、狀態已不是待開打。
  5. 有結果就寫入，然後回傳 True。
  6. 全部都略過時回傳 False。
- 寫入內容：
  - `outcome`、`winner_id`（雙方棄權時為 None）、`appeal_deadline`。`appeal_deadline` 用 `appeal_deadline(decided_at=now, appeal_minutes=賽事申訴時限)` 算。
  - 用 `transition_match` 把場次轉為申訴期，不經過進行中。
  - `submitted_by`、`submitted_at` 維持空值。
  - `wins_a`、`wins_b` 不變，沒有比過局。
- 操作紀錄只用 `app.core.audit.record()`：
  - `actor_id=None`，代表 system；`tournament_id` 為該賽事；`action="match.forfeited"`；`entity_type="match"`。
  - `before` 與 `after` 都記 `status`、`outcome`、`winner_id`、`appeal_deadline`。
- 發出事件 `MatchForfeited`，payload 為：
  - `match_id`、`tournament_id`、`outcome`、`winner_id`
  - `forfeited_team_ids`：順序與 `judge_forfeit` 相同
  - `appeal_deadline`

  期中只發事件，不另寫通知。
- 重複執行沒有副作用：場次判過之後是申訴期，再跑一次會略過。

**Never:**
- 不修改 D 或 B 的檔案。`models.py`、`service.py`、`repository.py`、`router.py` 都不改，不新增資料表或遷移。
- 不 import 尚未存在的函式，也不把工作註冊進 `JOBS`。真的轉接層等合併後再寫。
- 不寫通知的收件規則（期中規則 2）。
- 不做 S4 畫面（另一份 spec，在 `story/5-8` 做）。

**Decisions（使用者 2026-10-30 定案）:**
- 依約定介面把 worker 工作寫完，用假的 service 測試；D、B 合併後只接上真函式並註冊。範圍寫進 `deferred-work.md`。
- S4 的申訴期顯示另外做：先顯示「{絕對時間} 截止」，再加一個倒數插槽，等 B 的 Countdown 完成後再放進去。這部分在 `story/5-8` 另寫一份 spec。
- 先鎖賽事再鎖場次。理由是賽事已取消的判斷要以鎖住後的值為準，而且和 5.5 的鎖定順序一致。
- 不做 code review（沿用使用者「最後統一 review」的決定）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 一隊報到 | 期限 13:15、現在 13:16、只有 A 報到、申訴時限 60 | `forfeit`、勝隊 A、申訴期截止 14:16、狀態申訴期；一筆操作紀錄、一則 `MatchForfeited`；回傳 True | N/A |
| 兩隊未報到 | 同上，沒有隊伍報到 | `double_forfeit`、勝隊 None、轉為申訴期；回傳 True | N/A |
| 第一場略過 | 第一場兩隊都已報到，第二場只有 B 報到 | 第一場不變；第二場判 `forfeit`、勝隊 B；回傳 True | N/A |
| 全部略過 | 到期清單只有已取消賽事的場次 | 不寫任何東西；回傳 False | N/A |
| 沒有到期場次 | 清單為空 | 回傳 False | N/A |
| 重複執行 | 判完後再呼叫一次（清單仍列出那一場） | 狀態已是申訴期，略過；不重複寫操作紀錄與事件 | N/A |
| 鎖定順序 | 任何場次 | 先呼叫 `lock_tournament`，再呼叫 `lock_match` | N/A |
| worker 一輪 | `run_once` 跑 3 場到期場次 | 3 場都判完，每場各自一個交易 | 某一場拋錯時 rollback 那一場，其他場不受影響 |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/forfeit.py`：第一階段的 `judge_forfeit`、`appeal_deadline`、`ForfeitVerdict`，直接使用，不修改。
- `backend/app/worker/__init__.py`：`Job = Callable[[Session], bool]`、`run_once(jobs, session_factory=...)`；工作不能 commit。`backend/app/worker/jobs.py`：`make_send_email_job` 是「閉包包住依賴、回傳 Job」的寫法參考。這次不修改這兩個檔案。
- `backend/app/core/audit.py:53`：`record(session, *, actor_id, tournament_id, action, entity_type, entity_id, before, after)`；`actor_id=None` 代表 system。
- `backend/app/core/events.py`：繼承 `Event` 的類別名稱就是事件名稱，必須是過去式 PascalCase；用 `publish(session, event)` 發出。`identity/models.py:152-170` 是事件類別的寫法參考。
- `backend/app/modules/notifications/service.py:46-62`：沒有處理規則的事件類型只記日誌後略過，所以新事件不必登錄。
- `backend/tests/conftest.py`：
  - `session`（savepoint）、`session_factory`、`frozen_clock`（`set`、`advance`）
  - `backend/tests/worker/` 有 `run_once` 的測試寫法
- `contracts/competition.md`：函式名稱與欄位名稱以這份為準，例如 `MatchRead` 的 `team_a_id`、`forfeit_deadline`、`appeal_deadline`、`winner_id`、`outcome`、`status`、`tournament_id`；`TournamentRead` 的 `status`、`appeal_minutes`。
  - 轉接層之後會用到：`get_match`、`lock_match`、`list_forfeit_due`、`list_check_ins`、`transition_match`、`lock_tournament`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/forfeit_job.py`：新檔，內容如下。
  - `MatchForfeited(Event)`
  - `TournamentForfeitInfo`：frozen dataclass，欄位為 `cancelled: bool`、`appeal_minutes: int`
  - `ForfeitMatchRecord` Protocol：工作讀寫的場次屬性，名稱照 `MatchRead`
  - `ForfeitPorts` Protocol，方法如下：
    - `list_forfeit_due(session, *, now) -> Sequence[UUID]`
    - `get_tournament_id(session, *, match_id) -> UUID`
    - `lock_tournament(session, *, tournament_id) -> TournamentForfeitInfo`
    - `lock_match(session, *, match_id) -> ForfeitMatchRecord`
    - `list_checked_in_team_ids(session, *, match_id) -> Collection[UUID]`
    - `transition_to_appeal_window(session, *, match) -> None`
  - `forfeit_next_due(session, *, ports) -> bool`
  - `make_forfeit_job(ports) -> Job`：回傳的函式名稱是 `judge_forfeits`，讓 worker 的日誌看得出是哪個工作。
  - 檔頭說明第二階段之後要寫的轉接層對應到哪些 D、B 函式。
- [x] `backend/tests/competition/test_forfeit_job.py`：用假的 `ForfeitPorts`（記憶體中的場次與賽事，記錄呼叫順序）搭配真的 `session` 與 `frozen_clock`，涵蓋 I/O 矩陣的每一列。
  - 驗證操作紀錄用 `audit.list_for_tournament` 或直接查表；驗證事件用 `OutboxEvent` 查表。
  - 「worker 一輪」那一列要用 `run_once`＋`session_factory`。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`：新增一項。內容是：
  - 合併後要寫轉接層，並把 `make_forfeit_job(轉接層)` 加進 `JOBS`
  - 轉接層要對應的函式
  - 請 D 評估 `list_forfeit_due` 是否排除「兩隊都已報到」的場次，避免每輪重複略過

**Acceptance Criteria:**
- Given 判棄權完成，when 讀取場次，then `submitted_by`、`submitted_at` 為空，`wins_a`、`wins_b` 不變。
- Given 工作在同一輪被連續呼叫，when 到期清單只剩略過的場次，then 回傳 False，`run_once` 停止呼叫這個工作。
- Given 後端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- 寫入順序：先記下 `before`，寫入 `outcome`、`winner_id`、`appeal_deadline`，再呼叫 `transition_to_appeal_window`，之後才寫操作紀錄、發事件。轉換失敗時操作紀錄與事件都還沒寫。
- `ForfeitMatchRecord` 的唯讀屬性用 property 宣告，`outcome`、`winner_id`、`appeal_deadline` 是可寫屬性。Protocol 方法只放 docstring（不放 `...`），所以不會被算成沒跑到的程式行。
- `make_forfeit_job` 的回傳型別照 spec 用 `app.worker.Job`。這是第一個 import `app.worker` 的模組檔案；`app.worker` 只依賴 `app.core.db`，沒有循環 import。
- 假的 `ForfeitPorts`：`lock_match` 回傳複本，轉換成功才存回，模擬交易回滾；`list_forfeit_due` 只看期限、不看狀態，用來模擬清單仍列出已判過或略過的場次。
- 「worker 一輪」的失敗案例讓第二場的轉換失敗一次：第一場已 commit，第二、三場不變；下一輪三場都判完。
- 尚未處理的風險（已寫進 `deferred-work.md` 或在此說明）：
  - 略過的場次的鎖會留到交易結束。
  - 某一場資料不合法，讓 `judge_forfeit` 拋 `ValueError` 時，那一場每輪都排在前面，這個工作每輪都會在那裡停下。正常情況下 D 的資料不會這樣，所以這次沒有另外處理。
- `sprint-status.yaml` 的 5-2 維持 `in-progress`：轉接層、註冊 `JOBS` 與 S4（`story/5-8`）都還沒做。
- 驗證結果（2026-10-30，重建 backend image 後）：
  - `scripts/test.sh` 303 passed，其中新增 12 個
  - `forfeit_job.py` 分支覆蓋率 100%（63 行、4 個分支）
  - `scripts/lint.sh` 通過；`tests/competition` 的 ruff check 與 ruff format 也通過
  - 新增與修改的檔案都是 LF

- **主對話驗收後的修正（2026-10-30）**：
  - 資料不合法的場次改為記錄日誌後略過，不再卡住後面到期的場次。上面「尚未處理的風險」第二點因此已處理，補了 `test_invalid_match_is_logged_and_skipped`。
  - 回傳型別改成檔內定義的 `ForfeitJob = Callable[[Session], bool]`，模組不再 import `app.worker`。worker 是呼叫模組的一方，模組不應該反過來依賴它。
  - 重跑結果：`scripts/test.sh` 304 passed；`forfeit_job.py` 分支覆蓋率 100%（69 行、4 個分支）；lint 通過。
- 依使用者的決定，沒有跑 code review。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose run --rm --no-deps -T backend bash scripts/test.sh`：全部通過。開發資料庫在這個分支沒有 1.7 的遷移，backend 服務可能起不來，所以改用 `run`。
- `docker compose run --rm --no-deps -T backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/forfeit_job.py' --fail-under=90"`：分支覆蓋率至少 90%。
- `docker compose run --rm --no-deps -T backend bash scripts/lint.sh`：通過。
