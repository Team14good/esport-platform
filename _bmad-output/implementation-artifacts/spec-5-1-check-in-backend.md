---
title: 'Story 5.1（第二階段）：報到紀錄、報到 API 與賽事開始'
type: 'feature'
created: '2026-11-01'
status: 'in-review'
baseline_commit: '9a0278ef8e68b69d03795507d2d5a96abc808d74'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-rules.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-panel.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段只有報到的時間規則（`checkin.py`）和只吃 props 的 `CheckInPanel`。隊長還不能真的報到，A 的 5.2 判棄權 worker 等著 `list_forfeit_due`、`list_check_ins` 才能接上，賽事到了開始時間也不會轉成「進行中」。

**Approach:** 在 competition 新增 CheckIn 資料表、`check_in` service 與 API、給 5.2 的兩個查詢函式，以及賽事開始的 worker 工作。隊長身分透過 registration 的 `is_captain`（C 的函式，比照抽籤的轉接檔，未合併時回 503）。分支疊在 #21 上，並合入 #7（第一階段）。

## Boundaries & Constraints

**Always:**
- 報到只限該場兩隊的隊長，各自為本隊報到，一隊一場只能報到一次，不能取消。隊伍由登入者是哪一隊的隊長推得，請求不帶隊伍。
- 檢查順序：場次不存在或不屬於網址上的賽事 → 404 `MATCH_NOT_FOUND`；賽事不是賽程已公布或進行中、或場次不是待開打 → 409 `MATCH_NOT_CHECKABLE`；兩隊未確定 → 409 `MATCH_TEAMS_PENDING`；不是兩隊任一隊的隊長 → 403 `CAPTAIN_REQUIRED`；接著依 `checkin.check_check_in` 的原因：`already_checked_in` → 409 `ALREADY_CHECKED_IN`，`too_early` → 409 `CHECK_IN_NOT_OPEN`（訊息含「{開放時間} 起可報到」），`closed` → 409 `CHECK_IN_CLOSED`。
- 先 `lock_match` 再讀狀態與報到紀錄（AD-6）；`(match_id, team_id)` 唯一鍵是最後防線。時間一律 `clock.now()`。
- 報到成功寫 `audit.record`（`match.checked_in`）並發 `TeamCheckedIn` 事件（含是否兩隊都已報到）。
- `list_check_ins(match_id)` 依報到時間排序；`list_forfeit_due(now)`：待開打、`forfeit_deadline <= now`、且不是兩隊都已報到的場次 id，依期限排序。
- 賽事開始 worker：賽事在「賽程已公布」、且最早場次的報到開放時間（`checkin.tournament_starts_at`）已到 → 轉為「進行中」，操作者為系統；鎖賽事後重新檢查，重複執行沒有副作用；已取消或已結束的賽事略過。
- 隊長能不能報到的原因要讓 S4 拿得到：登入者查詢時回傳本隊是 a 或 b（不是隊長為 null）與原因代碼（null 表示可報到），和報到 API 用同一套檢查。
- 報到時間公開（使用者 2026-11-01 決定）：`PublicMatchDetail` 新增 `check_in_a_at`、`check_in_b_at`（未報到為 null），未登入也看得到；同輪列表的 `PublicMatch` 不加。
- `list_forfeit_due` 排除兩隊都已報到的場次（使用者 2026-11-01 決定，回應 A 在 #16 的問題）；`contracts/competition.md` 同步改寫。

**Ask First:**
- 改 tournaments、registration 的既有程式，或改 `PublicMatch`／`PublicBracket` 既有欄位（`PublicMatchDetail` 新增上述兩個欄位已核准）。

**Never:**
- 不判棄權（A 的 5.2）、不做登錄比分（5.3）、不改時間（4.3）。
- 不改 A 的前端檔案（S4 接上 `CheckInPanel` 與產生的 client 是 A 的工作）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 正常報到 | A 隊隊長、開放後、期限前 | 201，回傳 `{match_id, team_id, at}`；狀態查詢顯示已報到 | N/A |
| 剛好開放 | 現在＝預定－30 分 | 201 | N/A |
| 太早 | 開放前 1 分 | — | 409 `CHECK_IN_NOT_OPEN` |
| 剛好期限 | 現在＝`forfeit_deadline` | — | 409 `CHECK_IN_CLOSED` |
| 重複報到 | 同隊再報一次 | — | 409 `ALREADY_CHECKED_IN` |
| 兩隊未確定 | 第二輪待定場次 | — | 409 `MATCH_TEAMS_PENDING` |
| 不是隊長 | 一般隊員、旁觀者、對手以外的隊長 | — | 403 `CAPTAIN_REQUIRED` |
| 未登入 | 無 token | — | 401 |
| 場次已不是待開打 | 申訴期、已確認 | — | 409 `MATCH_NOT_CHECKABLE` |
| registration 未提供 `is_captain` | C 尚未合併 | — | 503 `REGISTRATION_UNAVAILABLE` |
| 兩隊同時報到 | 併發 | 兩筆都成功、互不覆蓋 | N/A |
| 棄權候選 | 只有一隊報到、期限已過 | 列入 `list_forfeit_due` | N/A |
| 兩隊都報到 | 期限已過 | 不列入 | N/A |
| 公開單場 | 未登入 GET 單場，A 隊已報到 | `check_in_a_at` 為報到時間、`check_in_b_at` null | N/A |
| 賽事開始 | 最早場次 13:00、現在 12:30、賽程已公布 | 轉為進行中 | N/A |
| 賽事未到開始 | 現在 12:29 | 不變 | N/A |
| 重跑 | 已是進行中 | 不變、不重複寫紀錄 | N/A |

</frozen-after-approval>

## Code Map

- `competition/checkin.py`（#7 合入）-- `check_check_in`、`check_in_opens_at`、`tournament_starts_at`、`CheckInReason`；service 直接用，不重寫規則
- `competition/registration_port.py` -- `_lookup` 轉接寫法；新增 `is_captain(session, *, team_id, account_id) -> bool`，缺函式拋 `RegistrationUnavailableError`
- `competition/service.py` -- `lock_match`、`get_public_match`（404 判定可共用）、`auto_confirm_expired`（worker 寫法：先找候選、略過 `_ENDED`、鎖後重檢）、`_ENDED`
- `competition/repository.py` -- 新增 CheckIn 讀寫、`find_forfeit_due`、找待開始賽事的查詢；加鎖只寫在這裡
- `competition/models.py` -- 新增 `CheckIn` 表（`id, match_id FK, team_id, account_id FK, at`，唯一 `(match_id, team_id)`）、`CheckInRead`、`CheckInStatus`、事件 `TeamCheckedIn`；`Bracket` 可加欄位標記已處理開始（避免 competition 直接查 tournament 表）
- `competition/router.py` -- `POST`、`GET /tournaments/{tournament_id}/matches/{match_id}/check-in`，用 `identity/deps.py` 的 `CurrentAccount`
- `tournaments/service.py` -- `get_tournament`、`lock_tournament`、`transition_tournament(actor_id=None)`；只呼叫，不修改
- `worker/jobs.py` -- `JOBS` 只新增 `start_due_tournaments`，排在 `confirm_expired_appeals` 前
- 遷移：新增一支，`down_revision` 接目前 head `a3d5e7f9b1c4`
- `contracts/competition.md` -- HTTP API 表、`list_forfeit_due` 說明（排除兩隊都已報到）、`CheckInRead`、錯誤碼
- 測試寫法：`tests/competition/conftest.py`（`draw_with`、`FakeRegistration`）、`test_confirm_advance.py`（worker）、`test_match_api.py`

## Tasks & Acceptance

**Execution:**
- [ ] `models.py`、遷移 -- CheckIn 表與 schema
- [ ] `registration_port.py` -- `is_captain`
- [ ] `service.py` -- `check_in`、`get_check_in_status`、`list_check_ins`、`list_forfeit_due`、`start_due_tournament`（worker 單筆）
- [ ] `router.py` -- POST／GET check-in
- [ ] `worker/jobs.py` -- 註冊工作
- [ ] `tests/competition/test_check_in.py` -- I/O 矩陣每一列；併發兩隊報到；worker 重跑
- [ ] `get_public_match` -- 帶出 `check_in_a_at`、`check_in_b_at`
- [ ] 重新產生 `frontend/src/client`；更新 `contracts/competition.md`

**Acceptance Criteria:**
- Given 8 隊抽籤後第一輪場次，when 兩隊隊長在開放後各自報到，then 都回 201，`list_check_ins` 有兩筆，`list_forfeit_due` 在期限後不含這場。
- Given 任一拒絕情境，when 報到，then 回傳 I/O 矩陣的狀態碼與錯誤碼，且沒有寫入報到紀錄或操作紀錄。
- Given 狀態查詢與報到 API，when 同一時間點，then 狀態查詢回 null 原因若且唯若報到會成功。
- Given 賽程已公布的賽事到了開始時間，when worker 執行兩次，then 賽事為進行中，`tournament.status_changed` 只寫一筆。

## Verification

- 從主 repo 目錄：`MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "<worktree>/backend/app:/app/backend/app" -v "<worktree>/backend/tests:/app/backend/tests" backend bash scripts/test.sh` -- 全部通過
- `bash scripts/lint.sh` -- 通過
- 本 worktree 是 `I:/大學課程/軟工/espory-wt/checkin`，沒有 `.env`；docker compose 指令從主 repo `I:/大學課程/軟工/espory-platform` 執行，`-v` 掛 worktree 的 `backend/app`、`backend/tests`、`backend/scripts`，Git Bash 加 `MSYS_NO_PATHCONV=1`。產生 client：`COMPOSE_PROJECT_NAME=espory-platform COMPOSE_ENV_FILES=I:/大學課程/軟工/espory-platform/.env bash scripts/generate-client.sh`（在 worktree 執行）。不要在主 repo 做 checkout、stash、reset，不要 commit。

## Implementation Notes

- 審查後修正（2026-11-01）：重複報到撞唯一鍵改回 409 `ALREADY_CHECKED_IN`（`add_check_in` 用 `begin_nested` 捕捉 `IntegrityError`、回傳是否新增）；`CHECK_IN_NOT_OPEN` 訊息改台北時間；`CheckInStatus.reason` 改用 `CheckInPanel` 的小寫代碼並新增 `not_checkable`、`not_captain`（兩隊都確定時一律回傳 `side`），前端型別同步；兩隊已確定但期限缺失或不晚於開放時間回 `not_checkable`；`start_due_tournament` 鎖住後還沒到開始時間回 False；移除 `check_in.match_id` 單欄索引；`contracts/competition.md` 補檢查順序、狀態代碼與 worker 回傳值說明。

## Spec Change Log

## Review Triage Log
