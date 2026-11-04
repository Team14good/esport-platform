---
title: 'Story 4.3（第二階段）：S30 場次列表 API 與修改場次時間'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: '3b5b9cae1a95ba4b2f16c0ddcb55d328138d3bab'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段只有排程的純函式（`schedule.py`）。抽籤時已用它排好各輪時間，但主辦方還不能在 S30 看場次列表、也不能修改單一場次的時間；4.3 的 AC 與 5.1 的「已有隊伍報到就不能改時間」都還沒落地。

**Approach:** 在 competition 新增主辦方專用的場次列表 API（每場附上現在能不能改、可選的時間範圍）與修改時間 API；範圍與檢查一律用 `schedule.py` 的 `reschedule_window`／`check_reschedule`。S30 頁面等 B 的主辦方版面合併後再做（使用者 2026-11-01 決定先做後端）。分支疊在 #25 上。

## Boundaries & Constraints

**Always:**
- 只有該賽事的主辦方能用這兩個 API（`Organizer` 依賴＋`authz.ensure_tournament_owner`，403 `TOURNAMENT_OWNER_REQUIRED`）。
- 修改時間的檢查順序：
  1. 賽事不存在 → 404 `TOURNAMENT_NOT_FOUND`；場次不存在或不屬於網址上的賽事 → 404 `MATCH_NOT_FOUND`。
  2. AD-6 加鎖：先 `lock_tournament`，再 `lock_match`；之後才讀狀態、報到與相鄰場次的時間。
  3. 不是主辦方 → 403 `TOURNAMENT_OWNER_REQUIRED`。
  4. 賽事不是賽程已公布或進行中 → 409 `TOURNAMENT_NOT_RESCHEDULABLE`。
  5. 場次不是待開打，或棄權期限已過（等待判棄權）→ 409 `MATCH_NOT_RESCHEDULABLE`（使用者 2026-11-01 決定：期限已過就不能改，避免改時間把應判的棄權救回來）。
  6. 已有任一隊報到 → 409 `MATCH_ALREADY_CHECKED_IN`（5.1 補上的限制）。
  7. 依 `check_reschedule` 的原因（皆 409）：`before_now` → `RESCHEDULE_BEFORE_NOW`、`before_feeder` → `RESCHEDULE_BEFORE_FEEDER`、`after_next_match` → `RESCHEDULE_AFTER_NEXT_MATCH`、`no_valid_time` → `RESCHEDULE_NO_VALID_TIME`。訊息附上允許範圍的台北時間（例如「可選 10/26（一）12:55～14:35。」，沒有上限時只寫起點）。
- 範圍的輸入：
  - 「下一場」＝勝隊要去的場次的預定時間；準決賽取決賽與季軍賽中較早的一場（第一階段 deferred-work，A 在 #5 的審查）；決賽與季軍賽沒有下一場。
  - 「前一輪場次」＝勝隊或敗隊會進入本場的場次（`next_match_id` 或 `loser_next_match_id` 指向本場）的預定時間；第一輪與只由輪空填入的一方沒有。
  - 本場最小間隔與前一輪最小間隔都用 `round_min_gap`（棄權時限＋該輪 BO × 每局預估時間＋申訴期），BO 取 `bo_for_round`。
- 最早可選時間的「現在」改為「現在（進位到整分）＋30 分鐘」（報到開放的提前量 `checkin.CHECK_IN_LEAD`），兩隊至少有完整的報到時間；列表與修改 API 用同一個值（使用者 2026-11-01 決定）。
- 新時間必須帶時區，沒有時區回 422。
- 修改成功：寫入新的 `scheduled_at`、更新 `updated_at`；兩隊都已確定的場次經 `start_forfeit_clock` 重算棄權期限；寫操作紀錄 `match.rescheduled`（修改前後的時間與棄權期限）；發 `MatchRescheduled`（`match_id`、`scheduled_at`）。通知只發事件（期中規則 2）。
- 場次列表 API 依輪次、場次順序（季軍賽在決賽之後）列出所有場次：場次編號、兩隊（隊名或待定說明，與公開對戰樹相同）、預定時間、狀態、指派的裁判帳號 id（4.4 前為 null），以及修改時間的資訊：現在能不能改、不能改的原因代碼、允許範圍（最早、最晚；沒有上限為 null）。原因代碼與修改 API 的錯誤碼一一對應，範圍與修改 API 用同一套計算，讓 S30 的時間選擇器只開放這個範圍。
- 時間一律 `clock.now()`；`contracts/competition.md` 同步改寫。

**Ask First:**
- 改 tournaments、registration 的既有程式，或改公開 API 既有欄位。

**Never:**
- 不做 S30 頁面與時間選擇器（等 B 的主辦方版面；記入 deferred-work）、不做裁判指派（4.4）、不自動把同一輪分批、不連動調整其他場次的時間。
- 不在 service 重寫範圍規則；一律呼叫 `schedule.py`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一輪改時間 | 4 隊、第一輪待開打、無人報到，新時間在範圍內 | 200；`scheduled_at` 更新、棄權期限＝新時間＋棄權時限、操作紀錄與事件 | N/A |
| 剛好最晚 | 新時間＝下一場－本場最小間隔 | 200 | N/A |
| 晚於下一場範圍 | 再晚 1 分鐘 | — | 409 `RESCHEDULE_AFTER_NEXT_MATCH`，訊息含範圍 |
| 早於現在＋30 分 | 新時間比現在（進位到整分）＋30 分鐘早 | — | 409 `RESCHEDULE_BEFORE_NOW` |
| 剛好現在＋30 分 | 現在 10:00:20，新時間 10:31 | 200 | N/A |
| 期限已過未判 | 棄權期限已過、無人報到 | — | 409 `MATCH_NOT_RESCHEDULABLE` |
| 早於前一輪結束 | 第二輪場次改到前一輪場次＋最小間隔之前 | — | 409 `RESCHEDULE_BEFORE_FEEDER` |
| 準決賽 | 季軍賽先改得比決賽早，再改準決賽 | 上限以季軍賽計算 | 超過 → `RESCHEDULE_AFTER_NEXT_MATCH` |
| 決賽、季軍賽 | 新時間任意晚 | 200 | N/A |
| 沒有可選時間 | 前一輪結束晚於下一場範圍 | — | 409 `RESCHEDULE_NO_VALID_TIME` |
| 兩隊未確定 | 第二輪待定場次 | 200；不設棄權期限 | N/A |
| 已有隊伍報到 | A 隊已報到 | — | 409 `MATCH_ALREADY_CHECKED_IN` |
| 不是待開打 | 進行中、申訴期、已確認 | — | 409 `MATCH_NOT_RESCHEDULABLE` |
| 賽事已結束或已取消 | — | — | 409 `TOURNAMENT_NOT_RESCHEDULABLE` |
| 不是主辦方 | 其他主辦方、一般帳號 | — | 403 |
| 未登入 | — | — | 401 |
| 沒有時區 | `"2026-11-02T10:00:00"` | — | 422 |
| 場次不屬於該賽事 | 別的賽事的場次 id | — | 404 `MATCH_NOT_FOUND` |
| 拒絕 | 任何拒絕 | 時間、棄權期限、操作紀錄、事件都不變 | N/A |
| 列表 | 主辦方 GET | 所有場次依順序；可改的場次附範圍，不能改的附原因 | N/A |
| 列表的範圍一致 | 列表給的最早、最晚 | 用這兩個時間呼叫修改 API 都成功，外面一分鐘都失敗 | N/A |
| 尚未抽籤 | GET 列表 | — | 404 `BRACKET_NOT_FOUND` |

</frozen-after-approval>

## Code Map

- `competition/schedule.py`（#5 已合併）-- `round_min_gap`、`reschedule_window`、`check_reschedule`、`RescheduleWindow`、`RescheduleReason`；service 直接用
- `competition/service.py` -- `_round_starts`、`_public_matches`（隊名與待定說明可共用）、`lock_match`、`start_forfeit_clock`、`_match_in_tournament`、`_taipei_text`（台北時間文字）、`draw`（主辦方檢查與 AD-6 加鎖的寫法）
- `competition/repository.py` -- 已有 `list_matches`、`get_match`；需要時新增「找指向本場的場次」與寫入 `scheduled_at`；加鎖只寫在這裡
- `competition/models.py` -- 新增事件 `MatchRescheduled`、`RescheduleIn`（`scheduled_at: AwareDatetime`）、`RescheduleInfo`、`ManagedMatch`（或同等的 S30 列表型別）
- `competition/router.py` -- `GET /tournaments/{tournament_id}/manage/matches`、`PATCH /tournaments/{tournament_id}/matches/{match_id}/schedule`，用 `identity/deps.py` 的 `Organizer`
- `competition/repository.py` 的 `list_check_ins` -- 判斷是否已有隊伍報到
- `tournaments/service.py` -- `get_tournament`、`lock_tournament`、`bo_for_round`；只呼叫，不修改
- 不需要遷移（沒有新欄位）
- `contracts/competition.md` -- HTTP API 表、`ManagedMatch`、`RescheduleInfo`、錯誤碼、`MatchRescheduled`
- 測試寫法：`tests/competition/conftest.py`（`draw_with`）、`test_score_entry.py`、`test_check_in.py`（`frozen_clock`）

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/models.py` -- 型別與事件
- [x] `backend/app/modules/competition/repository.py` -- 需要的查詢與寫入
- [x] `backend/app/modules/competition/service.py` -- `reschedule_match`、`list_managed_matches`；範圍計算抽成一個私有函式，兩者共用
- [x] `backend/app/modules/competition/router.py` -- 兩個端點
- [x] `backend/tests/competition/test_reschedule.py` -- I/O 矩陣每一列；準決賽取較早一場；列表範圍與修改 API 一致（邊界內外各一分鐘）
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- 同步
- [x] `frontend/src/client/` -- `scripts/generate-client.sh` 重新產生，不手改
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 只新增：S30 頁面與時間選擇器待 B 的主辦方版面；刪除第一階段「準決賽要傳較早一場」那一項（本 Story 處理完）

**Acceptance Criteria:**
- Given 任一場次，when 列表回傳可以修改與範圍 [最早, 最晚]，then 修改 API 在範圍內（含邊界）成功、範圍外失敗，與列表結果一致。
- Given 任一被拒絕的修改，when 檢查資料庫，then 場次時間、棄權期限、操作紀錄、事件都沒有改變。

## Spec Change Log

- 2026-11-01（審查第 1 輪，intent_gap，使用者核准修改 frozen 區塊）：
  - 觸發：Blind Hunter 指出場次可以被改到「現在」，兩隊只剩棄權時限可以報到；Edge Case Hunter 指出棄權期限已過、worker 尚未判定的場次仍能改時間，等於把應判的棄權往後推；另有列表給的最早時間帶秒數，訊息顯示的整分反而被拒絕。
  - 修改：最早＝現在（進位到整分）＋30 分鐘；棄權期限已過的場次回 `MATCH_NOT_RESCHEDULABLE`；矩陣新增三列。
  - 避免的狀態：主辦方把場次改到幾分鐘後、隊伍來不及報到就被判棄權。
  - KEEP：現有的加鎖順序、`_reschedule_window` 由列表與修改 API 共用、準決賽取較早一場、拒絕時完全不寫入、31 個既有測試的結構。程式只做小幅修正，不重寫。

## Review Triage Log

第 1 輪（2026-11-01）：Blind Hunter 11 項、Edge Case Hunter 7 項、Verification Gap 2 個缺口＋1 項。intent_gap 兩項經使用者決定後修改 frozen 區塊（見 Spec Change Log），其餘照下表。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Blind | 第一輪場次可改到「現在」，報到立刻開放、兩隊只剩棄權時限 | medium | intent_gap，使用者決定最早＝現在＋30 分鐘 |
| 2 | Edge | 棄權期限已過、worker 未判的場次仍可改時間 | medium | intent_gap，使用者決定不能改（`MATCH_NOT_RESCHEDULABLE`） |
| 3 | Edge | 最早時間帶秒數，訊息與列表顯示的整分被 `before_now` 拒絕 | medium | `_taipei_text` 只到分；patch：「現在」進位到整分（與 #1 一起） |
| 4 | Blind、Edge | 新時間與原時間相同仍寫紀錄、發事件 | low | 對話框原值送出就會遇到；patch：相同時直接回傳、不寫入 |
| 5 | VG | 非主辦方遇到不能改的場次、未抽籤的列表時，順序沒有測試 | medium | 移動檢查順序測試不會失敗，且會洩漏他人賽事狀態。patch：補測試 |
| 6 | VG、Blind | 一般帳號的 `ORGANIZER_REQUIRED` 只驗 403；contracts 的錯誤順序沒寫 `Organizer` 依賴先於 404 | low | patch：補斷言、改 contracts 說明 |
| 7 | Blind | 回傳的時間保留請求的時區（例如 +08:00），列表為 UTC | low | patch：寫入前轉 UTC |
| 8 | Blind | 操作紀錄的棄權期限、事件內容、`RESCHEDULE_NO_VALID_TIME` 訊息沒有斷言；測試有錯誤註解與函式內 import | low | patch：補斷言、修註解與 import |
| 9 | Blind | 列表的範圍取 GET 當下時間，停留太久送出會被拒絕 | low | 本質如此，錯誤訊息帶新範圍。patch：寫進 S30 的 deferred-work 項目，提醒前端收到 `RESCHEDULE_*` 時重抓 |
| 10 | Blind | 列表每場查一次報到紀錄與 BO（N+1） | low | 期中規模數十場；修正要新增批次查詢。reject |
| 11 | Edge | 前一輪是輪空確認或已取消的場次仍限制最早時間 | low | 罕見；修正要加分支。reject |
| 12 | Blind | 與報到同時發生可能競態 | false | 報到同樣先 `lock_match`，兩者串行 |
| 13 | Blind | 賽事開始 worker 不知道場次被改 | false | worker 每次重算最早場次並在鎖後重檢；已開始的賽事不受影響 |
| 14 | Blind | `MatchRescheduled` 欄位太少 | false | 與 contracts 約定的事件欄位一致 |
| 15 | Edge | `next_match_id` 指向不存在的場次會 KeyError | false | 外鍵保證同一對戰表內存在 |
| 16 | Blind | 未測 CLOSED 等狀態 | false | 抽籤後賽事直接轉為賽程已公布，不會停在 CLOSED |
| 17 | VG | 測試註解說先調整其他場次但沒有 | low | 併入 #8 |

## Verification

**Commands:**
- 本分支在 worktree `I:/大學課程/軟工/espory-wt/reschedule`，沒有 `.env`；compose 指令要在主 repo `I:/大學課程/軟工/espory-platform` 目錄執行，並把 worktree 掛進容器（`WT=I:/大學課程/軟工/espory-wt/reschedule`；`MSYS_NO_PATHCONV=1` 下 `/i/...` 會掛成空資料夾）：
  `MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "$WT/backend/app:/app/backend/app" -v "$WT/backend/tests:/app/backend/tests" -v "$WT/backend/scripts:/app/backend/scripts" backend bash -c "python -m pytest -q -p no:cacheprovider | tail -1; bash scripts/lint.sh"` -- expected: 全部通過
- 測試資料庫共用，不要同時跑兩組完整測試。
- 重新產生 client（在 worktree 目錄執行）：`COMPOSE_PROJECT_NAME=espory-platform COMPOSE_ENV_FILES="I:/大學課程/軟工/espory-platform/.env" bash scripts/generate-client.sh`；之後 `bunx biome check`、`bun run build` 通過

**結果（2026-11-01，第 1 輪修正後）：**
- 後端全套：1247 passed；`scripts/lint.sh`（mypy、ty、ruff check、ruff format）通過。`test_reschedule.py` 36 個。
- 前端：biome、`bun run build` 通過；單元測試整批跑 236／239，失敗的 3 個是 identity 路由測試（login、account、forgot-password）在負載下逾時，單獨重跑 30 個全過，與本次改動無關。重新產生 client 只有新增。
- 突變驗證（主代理在容器內另外執行，只跑 `test_reschedule.py`）：已報到不擋 → 2 個失敗；期限已過不擋 → 1 個失敗；準決賽不取較早一場 → 1 個失敗；拿掉＋30 分鐘 → 7 個失敗；時間不變仍寫入 → 1 個失敗。
