---
title: 'Story 4.1（第二階段）：對戰表資料表、抽籤 service 與 API'
type: 'feature'
created: '2026-10-31'
status: 'in-progress'
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

**Approach:** 建 Bracket、Match 兩張表與遷移，寫 repository、`draw()` 等 service 與兩支 API（抽籤、公開對戰樹）。抽籤時一併依 4.3 的 `plan_round_starts` 排定各輪時間，並為兩隊都確定的場次設定棄權期限。對 registration 的呼叫集中在 competition 內一個轉接檔，C 的函式還沒合併時回 503，測試用替身；C 照約定名稱合併後不必改 competition。S27 畫面另開 spec。分支疊在 `story/2-2` 上（使用者 2026-10-31 決定）。

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
| 重複抽籤 | 已有 Bracket | 不改任何資料 | 409 `BRACKET_ALREADY_DRAWN` |
| 狀態不對 | `upcoming`、`published`、`ongoing`、`finished`、`cancelled` | 不改任何資料 | 409 `TOURNAMENT_NOT_DRAWABLE`（已有 Bracket 時回 `BRACKET_ALREADY_DRAWN`） |
| 不是主辦方 | 其他主辦方或一般會員 | — | 403（`ensure_tournament_owner`；非主辦方帳號由 `Organizer` 依賴擋下） |
| 未登入 | 無 token | — | 401 |
| 賽事不存在 | 隨機 id | — | 404 `TOURNAMENT_NOT_FOUND` |
| registration 尚未提供函式 | C 的函式不存在 | 不寫任何資料 | 503 `REGISTRATION_UNAVAILABLE` |
| 順延 | 棄權＋BO×每局＋申訴 > 每輪間隔 | `delayed_rounds` 列出被順延的輪次 | N/A |
| 公開對戰樹 | 未登入 GET | `PublicBracket`：`round_names`、每場 `code`、隊名、待定列、`bye_side`、`updated_at` | 尚未抽籤 404 `BRACKET_NOT_FOUND` |
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
- [ ] `competition/models.py` -- `Bracket`（`tournament_id` 唯一外鍵、`size`、`rounds`、`drawn_at`）、`Match`（約定 `MatchRead` 的欄位，加 `bracket_id`、`code`、`bye_side`、`loser_next_match_id`、`updated_at`；`(bracket_id, round_no, slot_no, is_third_place)` 唯一）；schema `MatchRead`、`BracketRead`（加 `delayed_rounds: list[int]`）、`PublicTeamRef`、`PublicMatch`、`PublicBracket`；事件 `BracketDrawn`
- [ ] `backend/app/alembic/versions/<rev>_story_4_1_bracket_and_match.py` -- 建兩張表，`down_revision = "e4b8c1d2a6f7"`
- [ ] `competition/repository.py` -- 新增 Bracket 與場次、依賽事取 Bracket 與場次、取單場、`FOR UPDATE` 鎖單場
- [ ] `competition/registration_port.py` -- 轉接 `list_accepted_teams`、`finalize_for_draw`、`mark_drawn`、`get_team_names`；registration 尚未提供時拋 `REGISTRATION_UNAVAILABLE` 503
- [ ] `competition/service.py` -- `draw`、`get_bracket`、`get_public_bracket`、`get_match`、`list_team_matches`、`lock_match`、`transition_match`、`start_forfeit_clock`
- [ ] `competition/router.py` -- `POST /tournaments/{tournament_id}/draw`（`Organizer`，201，回 `BracketRead`）、`GET /tournaments/{tournament_id}/bracket`（公開，回 `PublicBracket`）；確認 router 已掛進 `api/main`
- [ ] `backend/tests/competition/test_draw.py`、`test_match_transitions.py`、`test_bracket_api.py` -- I/O 矩陣每一列；registration 用 monkeypatch 替身；時間用 `frozen_clock`
- [ ] `contracts/competition.md` -- 補 `delayed_rounds`、`registration_port` 說明與錯誤碼

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

## Spec Change Log

## Review Triage Log
