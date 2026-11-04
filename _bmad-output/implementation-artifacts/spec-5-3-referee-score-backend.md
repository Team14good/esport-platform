---
title: 'Story 5.3、5.4（第二階段）：逐局比分資料表、登錄／刪除／送出 API'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: 'b746120e59b09a33eaa2cd48dee35a57f0cc979d'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-3-score-rules.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-3-score-entry-panel.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段只有比分規則（`scoring.py`）和只吃 props 的 `ScoreEntryPanel`。裁判還不能真的登錄比分、送出系列結果，場次停在「待開打」，5.5 的自動確認永遠等不到「申訴期」的場次，公開單場 API 的 `games` 一直是空的。

**Approach:** 在 competition 新增逐局資料表 `match_game` 與 `Match` 的送出欄位，加上登錄（新增或覆寫）、刪除最後一局、送出系列結果三個寫入 API，以及給 S4 面板用的讀取 API；規則全部交給 `scoring.py`，service 只負責鎖定、身分、狀態與寫入。分支疊在 #22（5.1 第二階段）上。

## Boundaries & Constraints

**Always:**
- 能登錄的人（以下稱「記分者」）：場次有指派裁判時只有該裁判；未指派時為該賽事主辦方。4.4 還沒做，期中目前一律是主辦方，但兩條路都要實作並測試。
- 寫入（登錄、刪除、送出）的檢查順序：
  1. 場次不存在或不屬於網址上的賽事 → 404 `MATCH_NOT_FOUND`。
  2. `lock_match`（AD-6），之後才讀狀態、局與報到紀錄。
  3. 賽事不接受比分 → 呼叫 tournaments `ensure_accepting_scores`，409 `TOURNAMENT_NOT_ACCEPTING_SCORES`。
  4. 不是記分者 → 403 `SCORER_REQUIRED`。
  5. 場次已送出（申訴期、申訴中、已確認）→ 409 `RESULT_ALREADY_SUBMITTED`；已取消 → 409 `MATCH_NOT_RECORDABLE`。
  6. 兩隊未確定 → 409 `MATCH_TEAMS_PENDING`；兩隊未都報到 → 409 `CHECK_IN_INCOMPLETE`。
  7. 依 `scoring.py` 的原因：`tie` → `SCORE_TIE`、`invalid_score` → `SCORE_INVALID`、`series_decided` → `SERIES_DECIDED`、`redundant_games` → `REDUNDANT_GAMES`、`invalid_game_no` → `INVALID_GAME_NO`、`not_last_game` → `NOT_LAST_GAME`，都是 409；送出時 `not_decided` → 409 `SERIES_NOT_DECIDED`，訊息「任一隊拿到 {N} 勝後才能送出。」。
- 登錄用 `PUT .../games/{game_no}`：局號＝目前局數＋1 為新增，≤ 目前局數為覆寫。比分欄位依賽事快照的 `score_type`：`win_loss` 只給 `winner_side`，`rounds` 只給 `score_a`、`score_b`。
- 回合數範圍 0–99，超出由 schema 回 422（使用者 2026-11-01 決定）。
- 登錄第一局時場次由「待開打」轉為「進行中」（經 `transition_match`）。
- 刪除只能刪最後一局；刪到沒有任何局時場次維持「進行中」，不回到待開打（使用者 2026-11-01 決定）。
- 每次登錄或刪除後，`Match.wins_a`、`wins_b` 依 `scoring.series` 重算，讓公開的 Score display 跟著更新；`updated_at` 一併更新。
- 送出：寫 `outcome = played`、`winner_id`（勝方隊伍）、`submitted_by`、`submitted_at`、`appeal_deadline = 現在＋賽事的申訴時限`，經 `transition_match` 轉為「申訴期」，發 `MatchResultSubmitted`。不寫 `confirmed_at`，勝隊不晉級（5.5 負責）。
- 操作紀錄：登錄 `match.game_recorded`（覆寫時記下修改前後的比分）、刪除 `match.game_deleted`（記下被刪的比分）、送出 `match.result_submitted`。
- 讀取 API `GET .../score-entry`（需登入）給 S4 面板：回傳登入者是不是記分者、不能登錄的原因、已登錄的局、系列結果（勝局數、勝方、能否送出、門檻、原因），以及送出後的送出者顯示名稱與時間。不是記分者時 `is_scorer = false`，其他欄位為空，不洩漏送出者。
- 公開單場 API 的 `games` 改為依局號列出已登錄的局（不含登錄者）；送出者只在讀取 API 出現，公開 API 不出現。
- `(match_id, game_no)` 唯一鍵是併發的最後防線；同時兩個登錄請求經 `lock_match` 串行，結果不會互相覆蓋。
- 時間一律 `clock.now()`；`contracts/competition.md` 同步改寫。

**Ask First:**
- 改 tournaments、identity、registration 的既有程式，或改 `PublicMatch`／`PublicMatchDetail` 既有欄位的意義（`games` 從空陣列改成真的資料不算改意義）。

**Never:**
- 不做裁判指派（4.4）、不做申訴與更正（Epic 6）、不做自動確認與晉級（5.5 已有）、不做改時間（4.3）。
- 不改 A 的前端檔案；S4 接上 `ScoreEntryPanel` 與產生的 client 是 A 的工作。本 Story 只重新產生 client。
- 不在 service 重寫比分規則；一律呼叫 `scoring.py`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一局 | 主辦方、兩隊已報到、BO3 `win_loss`，PUT 第 1 局 a 勝 | 200；場次轉進行中，`wins_a=1` | N/A |
| 回合型態 | `rounds`，13：11 | 200，a 勝 | N/A |
| 平手 | `rounds`，12：12 | — | 409 `SCORE_TIE` |
| 超出範圍 | `rounds`，100：98 | — | 422 |
| 型態不符 | `win_loss` 卻給數字 | — | 409 `SCORE_INVALID` |
| 跳號 | 已 1 局，PUT 第 3 局 | — | 409 `INVALID_GAME_NO` |
| 已達門檻 | BO3、a 已 2 勝，PUT 第 3 局 | — | 409 `SERIES_DECIDED` |
| 覆寫 | a、b，把第 1 局改成 b | 200，b 2 勝；紀錄有修改前後 | N/A |
| 覆寫造成多餘局 | a、b、a，把第 1 局改成 b | — | 409 `REDUNDANT_GAMES` |
| 刪最後一局 | a、b、a，DELETE 第 3 局 | 200，剩 a、b | N/A |
| 刪非最後一局 | DELETE 第 1 局 | — | 409 `NOT_LAST_GAME` |
| 刪光 | 只有 1 局，DELETE 第 1 局 | 200，0 局，狀態仍是進行中 | N/A |
| 未都報到 | 只有 A 隊報到 | — | 409 `CHECK_IN_INCOMPLETE` |
| 不是記分者 | 隊長、觀眾、其他主辦方 | — | 403 `SCORER_REQUIRED` |
| 已指派裁判 | 主辦方登錄 | — | 403 `SCORER_REQUIRED` |
| 指派裁判本人 | 裁判登錄 | 200 | N/A |
| 未登入 | 無 token | — | 401 |
| 已取消賽事 | 賽事已取消 | — | 409 `TOURNAMENT_NOT_ACCEPTING_SCORES` |
| 送出 | BO3 a 2 勝 | 200；申訴期、`appeal_deadline`＝現在＋申訴時限、`submitted_by` 為記分者 | N/A |
| 未達門檻送出 | 1：0 | — | 409 `SERIES_NOT_DECIDED`，訊息含門檻 |
| 送出後修改 | 申訴期的場次 PUT／DELETE／再送出 | — | 409 `RESULT_ALREADY_SUBMITTED` |
| 讀取（記分者） | 已送出 | 局、系列結果、送出者顯示名稱與時間 | N/A |
| 讀取（非記分者） | 隊長 | `is_scorer=false`，其他欄位空 | N/A |
| 公開單場 | 未登入，已登錄 2 局 | `games` 兩筆、依局號，無登錄者 | N/A |
| 併發登錄 | 兩個請求同時新增第 2 局 | 經鎖串行：先到的新增、後到的變成覆寫，都回 200；資料庫只有一筆第 2 局 | N/A |

</frozen-after-approval>

## Code Map

- `competition/scoring.py`（#8 已合併）-- `make_game`、`check_record`、`check_delete`、`series`、`wins_needed`、`ScoreReason`；service 直接用
- `competition/service.py` -- `lock_match`、`transition_match`、`_match_in_tournament`（404 判定）、`_evaluate_check_in` 的寫法、`get_public_match`（填 `games`）
- `competition/repository.py` -- 新增 `MatchGame` 讀寫（依局號排序、新增、覆寫、刪除）、送出欄位寫入、`list_check_ins`（判斷兩隊都報到）；加鎖只寫在這裡
- `competition/models.py` -- 新增 `MatchGame` 表（`id, match_id FK, game_no, winner_side String(1), score_a, score_b, recorded_by FK account, recorded_at`，唯一 `(match_id, game_no)`）、`Match.submitted_by`（FK account，可空）、`Match.submitted_at`、事件 `MatchResultSubmitted`、`GameIn`、`SeriesRead`、`ScoreEntryState`
- `competition/router.py` -- `GET .../score-entry`、`PUT`／`DELETE .../games/{game_no}`、`POST .../submit`，用 `CurrentAccount`；寫入回傳最新的 `ScoreEntryState`
- `tournaments/service.py` -- `get_tournament`、`ensure_accepting_scores`、`bo_for_round`；只呼叫，不修改
- `identity/service.py` -- `get_account_contact` 取送出者 `display_name`；只呼叫，不修改
- `core/authz.py` -- `ensure_tournament_owner` 可用於主辦方判斷（但錯誤碼要轉成 `SCORER_REQUIRED`，或自行比對 `organizer_id`）
- 遷移：新增一支，`down_revision` 接目前 head `b5c7e9a1d3f2`
- `contracts/competition.md` -- HTTP API 表、`ScoreEntryState`、錯誤碼、`games` 說明
- 測試寫法：`tests/competition/conftest.py`（`draw_with`、`FakeRegistration`）、`test_check_in.py`（報到 API 與 `frozen_clock`）、`test_match_api.py`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/models.py` -- `MatchGame` 表、`Match.submitted_by`、`submitted_at`、`MatchResultSubmitted`、`GameIn`（`winner_side`、`score_a`、`score_b` 皆可空，回合數 0–99）、`SeriesRead`、`ScoreEntryState`
- [x] `backend/app/alembic/versions/<rev>_story_5_3_match_game.py` -- 新表與兩個欄位；`down_revision = "b5c7e9a1d3f2"`
- [x] `backend/app/modules/competition/repository.py` -- 局的 CRUD 與送出寫入
- [x] `backend/app/modules/competition/service.py` -- `record_game`、`delete_game`、`submit_result`、`get_score_entry`；`get_public_match` 填 `games`
- [x] `backend/app/modules/competition/router.py` -- 四個端點
- [x] `backend/tests/competition/test_score_entry.py` -- I/O 矩陣每一列；記分者兩條路；操作紀錄與事件內容；送出後 5.5 的 `auto_confirm_expired` 能接手確認（端對端一條）
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- 同步
- [x] `frontend/src/client/` -- `scripts/generate-client.sh` 重新產生，不手改
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 只新增：6.2 重新比賽要清掉 `match_game`；4.4 指派後 S4 的記分者判斷要接上；S4 接面板（A）

**Acceptance Criteria:**
- Given 一場兩隊都報到的 BO3 場次，when 主辦方依序登錄 a、b、a 並送出，then 場次為申訴期、`wins_a=2`、`wins_b=1`、`winner_id` 為 A 隊，公開單場 API 列出三局；申訴期滿後 worker 把它確認並讓 A 隊晉級。
- Given 任一寫入被拒絕，when 檢查資料庫，then 局、場次狀態、勝局數、操作紀錄都沒有改變。

## Implementation Notes

- 請求 schema 命名為 `GameScoreIn`（Code Map 寫 `GameIn`）：tournaments 已有 `GameIn`（遊戲設定），同名會讓 FastAPI 把兩者都改成 `app__modules__...__GameIn`，弄壞前端既有的 `GameIn` 型別。
- 回合數用嚴格整數 0–99（`strict=True`）：`13.5`、`true`、`"13"` 也回 422；`winner_side` 不是 a／b 回 422。型態不符（`win_loss` 給數字、`rounds` 給勝方或少一邊）回 409 `SCORE_INVALID`。
- `ScoreEntryState.reason` 的小寫代碼與寫入錯誤碼一一對應：`not_accepting_scores`、`result_submitted`、`not_recordable`、`teams_pending`、`check_in_incomplete`；賽事狀態判斷直接沿用 `ensure_accepting_scores`。送出者欄位名為 `submitted_by_name`。
- 送出時若存的局有多餘的局（`series.reason = redundant_games`）回 409 `REDUNDANT_GAMES`，其他未達門檻回 `SERIES_NOT_DECIDED`。
- 局號路徑參數不設範圍，0、負數、跳號都交給 `scoring.check_record`／`check_delete` 回 `INVALID_GAME_NO`。
- 併發：測試環境所有 session 共用一條連線，無法製造真併發；以「同一局先後兩次新增 → 後者變覆寫、只有一筆」與「呼叫順序：`lock_match` 先於讀局與報到紀錄」兩種測試代替。
- 驗證（2026-11-01）：後端全套 1201 passed（新增 `test_score_entry.py` 66 個）；`scripts/lint.sh`（mypy、ty、ruff）通過；重新產生 client 只新增型別與 SDK 函式；`bunx biome check ./src`、`bun run build` 通過。突變：拿掉兩隊報到檢查 → 5 失敗；拿掉 `lock_match` → 3 失敗；送出不轉申訴期 → 6 失敗。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-01）：Blind Hunter 12 項、Edge Case Hunter 7 項、Verification Gap 2 個缺口。沒有 intent_gap、bad_spec。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | VG | 測試全部是 BO3，`_bo` 回傳常數 3 也不會失敗 | medium | 已核實 `Setup` 沒傳 `bo`。patch：補 BO1、BO5 的門檻、`SERIES_DECIDED`、送出訊息測試 |
| 2 | VG、Blind | 記分者在賽事不接受比分時讀 `score-entry`，`not_accepting_scores` 沒有測試；`teams_pending`、`not_recordable` 的讀取也沒測 | low | 寫入路徑在更早一步就拋錯，拿掉 `_entry_reason` 的 try/except 測試不會失敗。patch：補讀取端每個原因 |
| 3 | Blind | 第一局把場次轉為進行中，操作紀錄沒記狀態變化 | low | `transition_match` 註明紀錄由呼叫端寫；`match.game_recorded` 的 before 為 None。patch：轉換時 before／after 加 `status` |
| 4 | Blind | `test_same_game_twice_becomes_overwrite` 名稱與段落標題自稱併發，實際是先後兩次請求 | low | patch：改說明，不宣稱測了併發（真實兩條連線的測試已在 5.1 記入 deferred-work） |
| 5 | Blind | deferred-work 的 6.2 重賽項目漏了 `appeal_deadline`、`confirmed_at` | low | 本次新增的項目，`submit_result` 會寫 `appeal_deadline`。patch：補上 |
| 6 | Blind | sprint-status 的 5-3 註解仍寫「第二階段待 2.2、4.1」 | low | patch：收尾時更新 |
| 7 | Edge | 賽事在未加鎖的 `get_tournament` 與 commit 之間被取消，比分仍會寫入 | maybe-false | 取消（2.6）尚未實作，無法重現；同類問題 5.1 已記入 deferred-work。defer：2.6 實作取消時要鎖賽事並與比分寫入串行 |
| 8 | Blind、Edge | `add_game` 撞唯一鍵是 500，不像報到用 `begin_nested` 轉 409 | low | 所有寫入都經 `_locked_for_scoring` 先 `lock_match`，沒有繞過鎖的路徑；修正要加分支。reject |
| 9 | Blind、Edge | 資料庫沒有 CHECK 約束；`winner_side` 不是 a／b 時 `_to_result` 會當成 b | low | 目前只有 API 一條寫入路徑且已驗證；加約束屬新增防護。reject（6.x 若新增寫入路徑再評估） |
| 10 | Blind | 覆寫沒有樂觀鎖（舊分頁會蓋掉新結果） | low | 記分者只有一人，spec 允許覆寫；需要新增 API 欄位。reject |
| 11 | Blind | 送出的操作紀錄沒有 `submitted_by`、`submitted_at` | false | 操作紀錄本身就有 `actor_id`（送出者）與寫入時間 |
| 12 | Blind | `ensure_accepting_scores` 呼叫兩次，`_ENTRY_REJECTIONS` 的對應在寫入路徑用不到 | low | 訊息與錯誤碼都沿用 tournaments，不會不一致；讀取路徑仍需要該原因。reject |
| 13 | Blind | `game_no` 應 `Path(ge=1)` 回 422；新端點沒宣告錯誤回應 | false | 矩陣規定跳號為 409 `INVALID_GAME_NO`，局號 0 同屬局號錯誤；錯誤碼已寫在 contracts |
| 14 | Blind | diff 沒有包含產生的 client 與 spec | false | client 是腳本產生、spec 依流程只給 Edge Case Hunter |
| 15 | Edge | 6.2 重賽保留舊的局 | false | 6.2 尚未實作，已列在本次新增的 deferred-work 項目（#5 補齊欄位） |
| 16 | Edge | deferred-work 刪除了第一階段「回合數沒有上限」 | false | 本 Story 以 0–99 處理完畢，規則允許處理完時刪除 |
| 17 | Edge | 請求 schema 名稱 `GameScoreIn` 與 spec 的 `GameIn` 不同 | false | 避免與 tournaments 的 `GameIn` 衝突，已寫在 Implementation Notes |

## Verification

**Commands:**
- 本分支在 worktree `I:/大學課程/軟工/espory-wt/referee`，沒有 `.env`；compose 指令要在主 repo `I:/大學課程/軟工/espory-platform` 目錄執行，並把 worktree 掛進容器（`WT=I:/大學課程/軟工/espory-wt/referee`；`MSYS_NO_PATHCONV=1` 下 `/i/...` 會掛成空資料夾）：
  `MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "$WT/backend/app:/app/backend/app" -v "$WT/backend/tests:/app/backend/tests" -v "$WT/backend/scripts:/app/backend/scripts" backend bash -c "python -m pytest -q -p no:cacheprovider | tail -1; bash scripts/lint.sh"` -- expected: 全部通過
- 測試資料庫共用，不要同時跑兩組完整測試。
- 重新產生 client（在 worktree 目錄執行）：`COMPOSE_PROJECT_NAME=espory-platform COMPOSE_ENV_FILES="I:/大學課程/軟工/espory-platform/.env" bash scripts/generate-client.sh`
- `scripts/generate-client.sh` 後 `git diff --exit-code frontend/src/client` 只有預期變更；`bunx biome check`、`bun run build` 通過
- 突變：拿掉兩隊報到檢查、拿掉 `lock_match`、送出不轉申訴期 → 各自有測試失敗

**結果（2026-11-01，第 1 輪修正後）：**
- 後端全套：1210 passed；`scripts/lint.sh`（ty、ruff check、ruff format）通過。`test_score_entry.py` 75 個。
- 前端：單元測試 239 passed；biome 通過；`bun run build` 通過。重新產生 client 只有新增，沒有改到既有型別。
- 突變驗證（主代理在容器內另外執行，只跑 `test_score_entry.py`）：拿掉兩隊報到檢查 → 5 個失敗；比分寫入改成不加鎖讀場次 → 3 個失敗；送出不轉申訴期 → 6 個失敗；`_bo` 寫死 3 → 2 個失敗；第一局不轉進行中 → 8 個失敗。
