---
title: 'Story 4.1（第二階段）：對戰表資料表、抽籤 service 與 API'
type: 'feature'
created: '2026-10-31'
status: 'done'
baseline_commit: 'ac575c2dcf1a6f88b5ffed105f6aef879faa04d9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-bracket-generator.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.1 第一階段只有純函式 `bracket.py`，對戰表還沒有地方存，主辦方也不能抽籤；A 的 4.6、5.8 在等公開對戰樹 API，D 自己的 4.3、4.4、5.x 也都要先有 Match 資料表。B 的 2.2（#15）已提供 `lock_tournament`、`transition_tournament`，C 的 registration 抽籤用函式（`list_accepted_teams`、`finalize_for_draw`、`mark_drawn`、`get_team_names`）還沒寫。

**Approach:** 建 Bracket、Match 兩張表與遷移，寫 repository、`draw()` 等 service 與兩支 API（抽籤、公開對戰樹）。抽籤時一併依 4.3 的 `plan_round_starts` 排定各輪時間，並為兩隊都確定的場次設定棄權期限。對 registration 的呼叫集中在 competition 內一個轉接檔，C 的函式還沒合併時回 503，測試用替身；C 照約定名稱合併後不必改 competition。S27 畫面另開 spec。範圍「先做資料層＋抽籤後端，S27 畫面另開 spec」與分支疊在 `story/2-2` 上，都是使用者 2026-10-31 決定。

## Boundaries & Constraints

**Always:**
- 抽籤流程（同一交易）：`lock_tournament` → 主辦方權限 → 狀態檢查 → 狀態為 `open` 時呼叫 `finalize_for_draw` → `list_accepted_teams` → 少於 2 隊拒絕 → `plan`＋`assign`（亂數 `secrets.SystemRandom()`，service 參數可注入）→ 寫入 Bracket 與全部 Match → 排定時間 → 設定棄權期限 → `mark_drawn` → `transition_tournament(to=published)` → 操作紀錄 `bracket.drawn` → 事件 `BracketDrawn`。
- 只有 `open`、`closed` 可以抽籤；已有 Bracket 時一律拒絕（抽籤只能一次）。
- 場次結構、編號、輪空、季軍賽全部取自 `bracket.py`，不在 service 重算；`next_match_id` 指向勝隊進入的場次，準決賽另以 `loser_next_match_id` 指向季軍賽。
- 時間：同一輪所有場次（含季軍賽與決賽）的 `scheduled_at` 相同，取自 `plan_round_starts`（BO 用 `bo_for_round`、每局時間用 `TournamentRead.game_minutes`）；有順延的輪次在回應的 `delayed_rounds` 列出，讓 S27 提示主辦方。
- 棄權期限只透過 `start_forfeit_clock` 設定，只給兩隊都確定的場次，值為 `forfeit_deadline(scheduled_at, both_known_at=now, forfeit_minutes)`。
- 場次狀態只能經 `transition_match` 修改，合法轉換依 PRD〈場次狀態〉：`scheduled`→`live`／`appeal_window`／`confirmed`／`voided`；`live`→`appeal_window`／`confirmed`；`appeal_window`→`appealed`／`confirmed`；`appealed`→`confirmed`／`scheduled`。
- 鎖的順序依 AD-6：先鎖賽事，再依 id 遞增鎖場次。
- 公開 API 只回 `PublicBracket`（AD-19），隊伍只有 `{id, name}`；輪次名、待定列字串用 `bracket.py` 的 `round_name`、`source_label`。
- 輪空用 `bye_a: bool`、`bye_b: bool` 兩欄各自標示（兩方都可能來自輪空）；某一方已有隊伍、或確定不會有隊伍（例如已確認的 walkover 空缺方）時，該方的 `source_*` 為 null。（使用者 2026-10-31 決定，取代原本的 `bye_side`）
- 依 `contracts/competition.md` 的名稱與簽名實作；約定與這份 spec 不同的地方要同步改約定並在 PR 說明列出。

**Ask First:**
- 要改 tournaments 或 registration 模組的任何既有程式。
- 要新增約定以外的公開函式或 API。

**Never:**
- 不建 MatchGame、CheckIn、ResultScreenshot 表（各自的 Story 再建）。
- 不做 S27 畫面、改時間 API（4.3 第二階段）、指派裁判（4.4）、worker 自動抽籤（4.2 擱置）。
- 不在 competition 讀 tournaments 或 registration 的資料表；不在 service 或 repository commit。
- 不用 SQLite；不跳過或刪除既有測試。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 報名截止後抽籤 | `closed`、正取 8 隊 | 201，`BracketRead` 8 場、3 輪；賽事 `published`；8 隊標已參賽；第一輪 4 場有棄權期限 | N/A |
| 開放報名中提前抽籤 | `open`、正取 13 隊 | 先呼叫 `finalize_for_draw` 再抽籤；13 場、3 支輪空隊伍直接在第二輪；賽事 `open`→`published` | N/A |
| 輪空多於 P÷4 | `closed`、10 隊 | 兩支輪空隊伍相遇的第二輪場次兩隊確定，也有棄權期限 | N/A |
| 正取不足 | 正取 0 或 1 隊 | 不寫任何資料，賽事狀態不變 | 409 `NOT_ENOUGH_TEAMS`「正取不足 2 隊，無法抽籤」 |
| 開賽時間已過 | `start_at <= now`（`open` 或 `closed`） | 不改任何資料 | 409 `TOURNAMENT_START_PASSED`「開賽時間已過，無法抽籤」（使用者 2026-10-31 決定） |
| 重複抽籤 | 已有 Bracket | 不改任何資料 | 409 `BRACKET_ALREADY_DRAWN` |
| 狀態不對 | `upcoming`、`published`、`ongoing`、`finished`、`cancelled` | 不改任何資料 | 409 `TOURNAMENT_NOT_DRAWABLE`（已有 Bracket 時回 `BRACKET_ALREADY_DRAWN`） |
| 不是主辦方 | 其他主辦方或一般會員 | — | 403（`ensure_tournament_owner`；非主辦方帳號由 `Organizer` 依賴擋下） |
| 未登入 | 無 token | — | 401 |
| 賽事不存在 | 隨機 id | — | 404 `TOURNAMENT_NOT_FOUND` |
| registration 尚未提供函式 | C 的函式不存在 | 不寫任何資料 | 503 `REGISTRATION_UNAVAILABLE` |
| 順延 | 棄權＋BO×每局＋申訴 > 每輪間隔 | `delayed_rounds` 列出被順延的輪次 | N/A |
| 公開對戰樹 | 未登入 GET | `PublicBracket`：`round_names`、每場 `code`、隊名、待定列、`bye_a`／`bye_b`、`updated_at` | 尚未抽籤 404 `BRACKET_NOT_FOUND` |
| 場次狀態非法轉換 | 例如 `confirmed`→`live` | 狀態不變 | 409 `MATCH_INVALID_TRANSITION` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/bracket.py` -- 第一階段純函式：`plan`、`assign`、`round_name`、`source_label`、`PlannedMatch`（`code`、`round_no`、`slot_no`、`next_code`、`loser_next_code`、`bye_a/bye_b`）
- `backend/app/modules/competition/schedule.py` -- 4.3 第一階段：`plan_round_starts`、`forfeit_deadline`
- `backend/app/modules/competition/models.py` -- 已有 `MatchStatus`、`MatchOutcome`；新增表與 schema 放這裡
- `backend/app/modules/competition/{repository,service,router}.py` -- 目前只有 docstring 與空 router
- `backend/app/modules/tournaments/service.py` -- `get_tournament`、`lock_tournament`、`transition_tournament`、`bo_for_round`（2.2，#15）
- `backend/app/modules/tournaments/models.py:112` -- `Tournament` 表，外鍵目標 `tournament.id`
- `backend/app/core/{authz,audit,events,clock}.py` -- `ensure_tournament_owner`、`record`、`publish`、`now`
- `backend/app/modules/identity/deps.py` -- `Organizer` 依賴；`identity/models.py:103` 事件類別寫法
- `backend/app/alembic/versions/e4b8c1d2a6f7_story_2_2_tournament.py` -- 新遷移的 `down_revision`
- `backend/tests/conftest.py`、`backend/tests/helpers.py` -- `client`、`session`、`frozen_clock`、`organizer_headers`、`make_game`、`make_tournament`
- `backend/tests/test_migrations.py`、`backend/tests/test_auth_required.py` -- 遷移與模型一致、寫入端點未登入回 401
- `backend/tests/tournaments/test_transitions.py` -- service 層測試寫法參考
- `_bmad-output/implementation-artifacts/contracts/competition.md` -- `MatchRead`、`BracketRead`、`PublicMatch`、`PublicBracket`、API 路徑、事件 payload

## Tasks & Acceptance

**Execution:**
- [x] `competition/models.py` -- `Bracket`（`tournament_id` 唯一外鍵、`size`、`rounds`、`drawn_at`）、`Match`（約定 `MatchRead` 的欄位，加 `bracket_id`、`code`、`bye_a`、`bye_b`、`loser_next_match_id`、`updated_at`；`(bracket_id, round_no, slot_no, is_third_place)` 唯一）；schema `MatchRead`、`BracketRead`（加 `delayed_rounds: list[int]`）、`PublicTeamRef`、`PublicMatch`、`PublicBracket`；事件 `BracketDrawn`
- [x] `backend/app/alembic/versions/<rev>_story_4_1_bracket_and_match.py` -- 建兩張表，`down_revision = "e4b8c1d2a6f7"`
- [x] `competition/repository.py` -- 新增 Bracket 與場次、依賽事取 Bracket 與場次、取單場、`FOR UPDATE` 鎖單場
- [x] `competition/registration_port.py` -- 轉接 `list_accepted_teams`、`finalize_for_draw`、`mark_drawn`、`get_team_names`；registration 尚未提供時拋 `REGISTRATION_UNAVAILABLE` 503
- [x] `competition/service.py` -- `draw`、`get_bracket`、`get_public_bracket`、`get_match`、`list_team_matches`、`lock_match`、`transition_match`、`start_forfeit_clock`
- [x] `competition/router.py` -- `POST /tournaments/{tournament_id}/draw`（`Organizer`，201，回 `BracketRead`）、`GET /tournaments/{tournament_id}/bracket`（公開，回 `PublicBracket`）；確認 router 已掛進 `api/main`
- [x] `backend/tests/competition/test_draw.py`、`test_match_transitions.py`、`test_bracket_api.py` -- I/O 矩陣每一列；registration 用 monkeypatch 替身；時間用 `frozen_clock`
- [x] `contracts/competition.md` -- 補 `delayed_rounds`、`registration_port` 說明與錯誤碼

**Acceptance Criteria:**
- Given `closed`、正取 N 隊（N＝2、3、8、10、13、32），when 主辦方抽籤，then 資料表的場次數、輪空、季軍賽、`next_match_id` 都與 `bracket.plan(N)` 一致，每支隊伍恰好出現一次，賽事轉為 `published`，`mark_drawn` 收到全部 N 隊，操作紀錄與 outbox 各一筆。
- Given 抽籤成功，when 查同一輪的場次，then `scheduled_at` 相同且等於 `plan_round_starts` 的結果；兩隊都確定的場次有棄權期限，其他場次為空。
- Given 任一拒絕情況（I/O 矩陣的錯誤列），when 抽籤，then 回對應錯誤碼，賽事狀態、Bracket、Match、操作紀錄、outbox 都沒有變動。
- Given 已抽籤，when 未登入 GET 公開對戰樹，then 回 `PublicBracket`，不含 Email、學校或任何帳號資料以外的欄位；待定方有「M4 勝者」「M29 敗者」字串。
- Given 每一組（現在狀態, 目標狀態），when 呼叫 `transition_match`，then 只有約定的轉換成功，其他都拋 `MATCH_INVALID_TRANSITION`。

## Verification

- `MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "<worktree>/backend/app:/app/backend/app" -v "<worktree>/backend/tests:/app/backend/tests" backend bash scripts/test.sh` -- 全部通過，含 `test_migrations.py`、`test_auth_required.py`
- `backend/scripts/lint.sh`（同樣掛載）-- 通過
- `competition/service.py`、`registration_port.py` 分支覆蓋率 ≥ 90%（`pytest --cov=app/modules/competition --cov-branch`）

## Implementation Notes

### spec 沒寫清楚、實作時的決定

1. **503 與 `BusinessError` 只收 4xx 衝突**：`core/errors.py` 拒絕非 4xx（有 `test_business_error_status_must_be_4xx`）。不改 core，在 `registration_port.py` 建 `RegistrationUnavailableError(BusinessError)`，以 409 建立後把 `status_code` 改成 503；全域 handler 直接使用 `exc.status_code`，回應格式不變。
2. **輪空標示改為 `bye_a`／`bye_b`**（依 Spec Change Log 第 1 次）：資料表兩欄 `Boolean NOT NULL`（模型預設 False），直接取自 `PlannedMatch.bye_a/bye_b`；`MatchRead`、`PublicMatch` 同名欄位，約定同步修改。原本自行加的 `"both"` 已移除。**前端（A 的 4.6）改讀兩個布林，PR 說明需列出。**
3. **registration 函式的操作者參數**：約定寫 `actor`，但 B 的 `transition_tournament` 已改為 `actor_id`；port 一律以 `actor_id=` 呼叫 registration，約定同步改名（C 尚未實作）。
4. **`list_accepted_teams` 回 `TeamRead`**：port 只取 `.id` 回傳 `list[UUID]`；公開對戰樹的隊名用 `get_team_names`，名單中查不到的隊伍顯示「未知隊伍」，不讓公開頁 500。
5. **`delayed_rounds` 在 `get_bracket` 也有值**：不另存欄位，由賽事設定重算 `plan_round_starts`（只取決於設定，與抽籤時相同）。4.3 改時間後語意仍是「規則強制順延的輪次」。
6. **公開對戰樹的待定列**：`Bracket` 存抽籤時的 `team_count`，以 `bracket.plan(bracket.team_count)` → `source_label` 產生（不再由輪空旗標反推隊數）。該方已有隊伍、場次已取消（`voided`）、或場次已確認且 `outcome = walkover` 而該方沒有隊伍（確定不會有隊伍）時回 None。`updated_at` = max(`drawn_at`, 各場次 `updated_at`)。
7. **`transition_match` 不寫操作紀錄**：簽名沒有操作者，紀錄由呼叫端（5.5 確認結果、6.x 申訴）依情境寫入；只更新 `status` 與 `updated_at`。
8. **`start_forfeit_clock` 用在兩隊未確定的場次**拋 409 `MATCH_TEAMS_NOT_SET`（新增錯誤碼，已寫入約定）；期限需要的 `forfeit_minutes` 以 `get_tournament` 取得（同一交易內 identity map 命中，不另查）。
9. **錯誤檢查順序**：`lock_tournament`（404）→ 主辦方（403）→ 已有 Bracket（`BRACKET_ALREADY_DRAWN`）→ 狀態（`TOURNAMENT_NOT_DRAWABLE`）→ 開賽時間已過（`TOURNAMENT_START_PASSED`）→ `finalize_for_draw`（僅 `open`）→ `list_accepted_teams` → 不足 2 隊。
10. **自我參照外鍵的寫入順序**：未建 relationship，service 先產生全部場次 id，倒序（季軍賽、決賽、…、第一輪）逐筆 flush，被指向的場次先存在。
11. **`team_a_id`、`team_b_id`、`winner_id` 不建外鍵**：隊伍表屬 registration（目前不存在），不建跨模組外鍵；`referee_account_id` 指向 `account.id`。
12. **`Match` 依輪次、季軍賽在決賽之後、slot 排序**；`list_team_matches` 同序。

### 驗證結果（2026-10-31，容器內 PostgreSQL 18）

- 基準（未加本 Story 測試）：691 passed、1 failed（`test_smtp_sender_delivers_to_mailpit_from_flow`，當時 mailpit 未啟動）。
- 啟動 mailpit 後 `bash scripts/test.sh`：**776 passed、0 failed**（比基準多 84 個：`test_draw.py` 26、`test_match_transitions.py` 42、`test_bracket_api.py` 9、`test_registration_port.py` 6，以及 `test_auth_required.py` 自動多出的 `POST /tournaments/{tournament_id}/draw` 1 個），含 `test_migrations.py`、`test_auth_required.py`（新 POST 端點自動納入 401 檢查）、`test_module_structure.py`。
- `bash scripts/lint.sh`：mypy（55 檔）、ty、ruff check、ruff format --check 全部通過。
- 分支覆蓋率（`coverage run --branch --source=app/modules/competition -m pytest tests/competition`，映像沒有 pytest-cov）：`service.py` 99%（123 行缺 1、42 分支缺 1：`_bye_side` 只有 b 方輪空的分支，`bracket.plan` 目前不會產生）；`registration_port.py` 100%；`repository.py`、`router.py`、`models.py` 100%；competition 合計 99%。
- 突變檢查：暫時把 `draw` 中的 `start_forfeit_clock` 換成 `pass`、並允許 `confirmed→live`，competition 測試 3 個失敗（`test_draw_eight_teams_after_close`、`test_two_bye_teams_meeting_in_round_two_get_forfeit_deadline`、`test_forbidden_transition_is_409[confirmed-live]`），還原後全數通過。

- **第 1 次 spec 修改後（`bye_a`／`bye_b`、walkover 空缺方）重跑**：`pytest tests/competition tests/test_migrations.py` 315 passed（competition 新增 `test_public_bracket_nine_teams_three_double_byes`、`test_walkover_empty_side_has_no_source`）；`lint.sh` 全部通過；分支覆蓋率 `service.py` 100%（117 行、36 分支，原本缺的 `_bye_side` 分支已隨 `bye_side` 移除）、`registration_port.py` 100%，competition 合計 100%。全套件未重跑（協調者指示只跑上述範圍）。
- **審查修正後重跑**（`TOURNAMENT_START_PASSED`、`Bracket.team_count`、voided 空缺方、`updated_at` 測試、503 測試移除 registration 函式）：`pytest tests/competition tests/test_migrations.py` 321 passed；`lint.sh` 全部通過；`scripts/generate-client.sh` 重新產生 `frontend/src/client`（index.ts、sdk.gen.ts、types.gen.ts 只有新增）。

## Spec Change Log

- 2026-10-31 第 1 次（審查 A 的 #13 時發現）：`bye_side` 無法表示兩方都輪空的場次，空缺方的待定列也會誤顯示「M14 勝者」。使用者決定改為 `bye_a`／`bye_b`，空缺時 `source_*` 為 null，凍結區已修改。實作子代理原本自行改成 `"both"`，這次改掉；其他實作保留（KEEP：抽籤流程、排程、棄權期限、`transition_match`、registration_port 與測試）。

- 2026-10-31 第 2 次（審查 Edge Case Hunter）：開賽時間已過才抽籤，第一輪會排在過去、棄權期限已過。使用者決定拒絕抽籤，凍結區 I/O 矩陣新增一列。程式只差一個檢查，不回退，以修正方式補上（KEEP：其餘全部）。

## Review Triage Log

第 1 輪（2026-10-31）：Blind Hunter 10 項、Edge Case Hunter 7 項、Verification Gap 2 項。

| # | 來源 | 發現 | 判定 | 證據 | 處置 |
|---|------|------|------|------|------|
| 1 | VG | 公開對戰樹 `updated_at` 沒有測試驗證會隨場次前進 | medium | 唯一斷言在抽籤當下，`drawn_at` 與場次 `updated_at` 相同；把公式改成只回 `drawn_at` 測試仍會過 | patch：補測試 |
| 2 | VG、BH | 兩個 503 測試依賴「這個分支 registration 沒有函式」，C 合併後會失敗 | medium | `registration/service.py` 目前沒有任何 `def`；測試未用 `delattr` | patch：改用 `monkeypatch.delattr(..., raising=False)` |
| 3 | BH | 公開對戰樹由 `bye_*` 推回隊數再 `plan()`，依賴隱含不變式 | low | 目前不變式成立（9、10 隊測試通過），但 4.5、6.5 改動對戰表時容易壞；存 `team_count` 是直接修正 | patch：`Bracket` 加 `team_count` 欄位，刪掉推算 |
| 4 | EC | 開賽時間已過仍可抽籤，第一輪排在過去 | medium | `draw` 沒有比較 `start_at` 與 `now`；spec 未規定 → 問使用者，決定拒絕 | intent_gap → 凍結區已補（Change Log 第 2 次），patch：加 409 `TOURNAMENT_START_PASSED` |
| 5 | EC | 已取消（voided）的季軍賽空缺方仍顯示「M5 敗者」 | low | `_source` 只排除已確認的 walkover；voided 屬於「確定不會有隊伍」 | patch：voided 也回 null |
| 6 | BH | 前端 client 沒有重新產生 | medium | `frontend/src/client` 沒有 draw、bracket；CLAUDE.md 規定前端只能用產生的 client，A 第二階段要用 | patch：執行 `scripts/generate-client.sh` |
| 7 | BH、EC | `delayed_rounds` 每次用目前的賽事設定重算，設定改了會和實際時間不符 | low | 期中不能改賽事設定（2.5 擱置），`bo_for_round` 固定回賽事 BO；不會發生 | 駁回（low，日常不會遇到，修法要加欄位） |
| 8 | BH | `RegistrationUnavailableError` 先用 409 建再改成 503，繞過 `BusinessError` 的 4xx 檢查 | low | docstring 已說明原因，handler 讀 `status_code` 正常；正規做法要改 core | 駁回（low，修法要動共用模組） |
| 9 | BH | registration 回傳的形狀或參數名不同時會 500 | maybe-false | C 尚未實作；約定已寫明名稱與參數 | 駁回（若為真也只是整合時的大聲失敗） |
| 10 | BH、EC | `start_forfeit_clock` 不擋非待開打或已有期限的場次 | false | 4.3 改時間要重算期限，已有期限必須能覆蓋；非待開打的呼叫端目前不存在 | 駁回 |
| 11 | BH | 每場 `start_forfeit_clock` 都重讀賽事 | low | 32 隊最多 16 次查詢；效能可接受 | 駁回 |
| 12 | BH | 寫入順序依賴 `assign` 的回傳順序 | low | 順序錯時外鍵會大聲失敗，2～32 隊測試都通過 | 駁回 |
| 13 | BH | 遷移沒有 check constraint、`next_match_id` 索引；也沒有遷移與模型的比對 | false | `tests/test_migrations.py` 已比對遷移與模型；其他模組也沒有 check constraint | 駁回 |
| 14 | BH | 錯誤路徑沒有 HTTP 層測試；同時抽籤可能 IntegrityError | false | service 層已測每個錯誤碼；賽事列鎖讓第二個請求看到已抽籤而回 409 | 駁回 |
| 15 | BH | `finalize_for_draw` 已執行後才發現不足 2 隊，回滾沒驗證 | false | 同一交易，router 只在成功時 commit | 駁回 |
| 16 | BH | 查不到隊名時顯示「未知隊伍」不記錄 | low | 只在資料不一致時發生 | 駁回 |
| 17 | EC | registration 回傳重複隊伍會 500 | low | `assign` 拋 ValueError，大聲失敗；約定保證不重複 | 駁回 |
| 18 | EC | `transition_match` 收到未鎖定的列會遺失更新 | low | 約定要求呼叫端先 `lock_match` | 駁回 |
| 19 | EC | Tasks 還寫 `bye_side` | low | 修法是改 spec | 駁回（Tasks 文字已順手更正） |
