---
title: 'D 模組期末審查缺口：順延輪次提示、棄權工作逐場隔離、追溯表與狀態收尾'
type: 'bugfix'
created: '2026-11-25'
status: 'done'
baseline_commit: '563db53'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 期末對照需求時，D 負責的 competition 模組還有幾個缺口。
- FR-23 要求抽籤結果提示主辦方「哪幾輪被順延」。後端 `BracketRead.delayed_rounds` 已經算好，前端完全沒用到；手動抽籤只跳「已完成抽籤」，自動抽籤則完全沒有提示。
- `forfeit_next_due` 遇到某一場拋出非 `ValueError` 的錯誤時，整個工作在這一輪停止。如果那場每次都失敗，排在它後面到期的場次永遠不會被判棄權。同模組的 `auto_draw_due`、`auto_confirm_expired` 都是逐場用 savepoint 隔離、記 log 後繼續。
- 追溯表漏標了幾個 Story，Story 狀態與延後項目也有過時的地方。

**Approach:**
- 在 S27 抽籤區塊加上主辦方專用的順延提示：抽籤後只要 `delayed_rounds` 不是空的就顯示，手動和自動抽籤都看得到。
- `forfeit_next_due` 改成逐場 savepoint 加 `except Exception` 記 log 後繼續。
- 補上追溯表標記、兩隊同時報到的真實併發測試，並收尾過時的狀態與延後項目。

## Boundaries & Constraints

**Always:**
- 只改 competition 模組與 D 自己的檔案。
  - 不改 `features/tournaments/OrganizerTournamentOverview.tsx`（B 的檔案）。
  - 提示由 competition 的 `DrawButton.tsx` 或它渲染的新元件負責顯示。
- 提示文字用繁體中文，不用驚嘆號，並列出輪次名稱，例如：「第 2、3 輪因前一輪 BO 數較多已順延開始時間，請到場次管理確認。」輪次名稱可以沿用 `round-name.ts`。
- 只有主辦方的 S27 看得到這則提示；公開賽程頁不顯示。
- 棄權工作的錯誤隔離要和 `service.py` 的 `auto_draw_due` 寫法一致：每場一個 `session.begin_nested()`，`except Exception` 時 `logger.exception` 後 `continue`。鎖的順序維持 AD-6：先賽事、後場次。
- `deferred-work.md` 只刪除本次處理完的項目（第 38 行 5.1 併發測試、第 41 行 4.3 準決賽上限），不改其他項目。

**Never:**
- 不改 notifications 模組；FR-37「收回裁判時通知主辦方」不在本次範圍。
- 不改後端 `delayed_rounds` 的計算方式；前端不得自行重算順延輪次，一律讀後端的值。
- 不為了讓測試通過而刪除測試。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 有順延 | 已抽籤，`delayed_rounds=[2,3]`，主辦方開 S27 | 顯示一則提示，列出第 2、3 輪（或對應的輪次名稱） | N/A |
| 沒有順延 | 已抽籤，`delayed_rounds=[]` | 不顯示提示 | N/A |
| 尚未抽籤 | 開放報名或報名截止 | 照舊顯示抽籤按鈕，不顯示提示 | N/A |
| 已結束或已取消 | `delayed_rounds` 不是空的 | 不顯示提示 | N/A |
| 賽程讀取失敗 | bracket API 錯誤 | 不顯示提示，也不擋其他區塊 | 靜默 |
| 棄權：單場一次性失敗 | 三場到期，中間那場套用判決時拋錯一次 | 同一輪第一、三場都完成判決，失敗那場回滾；下一輪補判 | `logger.exception` |
| 棄權：單場永久失敗 | 中間那場每次都拋錯 | 其餘場次照常判決；失敗那場每輪都記 log，不寫任何紀錄或事件 | `logger.exception` |
| 兩隊同時報到 | 兩條真實 DB 連線，兩隊隊長同時報到同一場 | 兩隊都報到成功，沒有死結或重複紀錄 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/DrawButton.tsx`：S27 抽籤區塊；抽籤後目前 `return null`（`drawable` 只有 open／closed）。
- `frontend/src/features/competition/bracket-queries.ts`：賽程查詢；回傳的 `BracketRead.delayed_rounds` 是 `number[]`。
- `frontend/src/features/competition/round-name.ts`：輪次名稱。
- `frontend/src/features/competition/draw-queries.ts`：抽籤成功後要讓賽程查詢失效或重抓，讓提示馬上出現。
- `backend/app/modules/competition/forfeit_job.py:197-235`：`forfeit_next_due`。
- `backend/app/modules/competition/service.py:530-552`：`auto_draw_due`，savepoint 與錯誤隔離的參考寫法。
- `backend/tests/competition/test_forfeit_job.py:492`：`test_run_once_failure_rolls_back_only_that_match`。目前斷言「失敗後本輪停止」，這次改成新行為。`FakePorts.fail_transition_once` 可以拿來模擬一次性失敗。
- `backend/tests/competition/test_retire_concurrency.py`：用兩條真實連線測併發的寫法範本。
- `backend/tests/competition/test_check_in.py:412-470`：現有的報到順序測試。
- `backend/tests/traceability.yaml`：每個測試檔都要標 `stories`／`frs`。
- `_bmad-output/implementation-artifacts/`：`spec-4-2-auto-draw.md`、`spec-5-7-settlement-screenshot.md`、`sprint-status.yaml`、`deferred-work.md`。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/DelayedRoundsNotice.tsx`（新檔）與 `DrawButton.tsx`：抽籤後、賽事還沒結束或取消時，讀賽程，`delayed_rounds` 不是空的就顯示提示（用 `role="status"`）。
- [x] `frontend/src/features/competition/draw-queries.ts`：抽籤成功後讓賽程查詢失效。
- [x] `frontend/tests/unit/`：新增或擴充測試，涵蓋矩陣中前端的五列。
- [x] `backend/app/modules/competition/forfeit_job.py`：逐場 savepoint 加 `except Exception`，同步更新 docstring。
- [x] `backend/tests/competition/test_forfeit_job.py`：把一次性失敗的測試改成新行為，並新增永久失敗的測試。
- [x] `backend/tests/competition/test_check_in_concurrency.py`（新檔）：照 `test_retire_concurrency.py` 的寫法測兩隊同時報到，並加進 `traceability.yaml`。
- [x] `backend/tests/traceability.yaml`：逐一讀下列測試檔的內容，把實際驗證到的 Story 補進 `stories`。
  - `notifications/test_rules.py`：4.1–4.5 中有測到的通知。
  - `tournaments/test_update_tournament.py`：4.2。
  - `competition/test_next_matches.py`：4.3。
  - `competition/test_referee_matches.py`、`test_reschedule.py`、`test_retire_team*.py`、`test_retire_concurrency.py`、`test_assign_referee.py`：5.1、5.3、5.5 中有測到的。
  - 只標實際有測到的 Story，不要硬標。
- [x] `_bmad-output/implementation-artifacts/`：
  - `spec-4-2-auto-draw.md`、`spec-5-7-settlement-screenshot.md` 的 status 改為 `done`。
  - `sprint-status.yaml` 的 epic-4、epic-5 改為 `done`；5-1、5-4、5-5 註解中的 #43、#49 歸屬改為 D（用 `gh pr view 43 --json author`、`gh pr view 49 --json author` 確認作者）。
  - `deferred-work.md` 刪除第 38、41 行的兩筆項目。

**Acceptance Criteria:**
- Given 已抽籤且有順延，when 主辦方開 S27，then 不必重新整理就能看到提示；公開賽程頁沒有這則提示。
- Given 背景工作每輪執行，when 某場永久出錯，then 其他到期場次在同一輪就完成棄權判決。

## Implementation Notes

- 順延輪次原以為已有 GET API，實際只有 `POST /draw` 回傳；第 1 次修訂後改由 `DrawStatus.delayed_rounds` 提供，重新產生 client。輪次名稱讀既有的公開賽程 `round_names`（後端提供），讀取失敗時不顯示提示。
- `get_draw_status` 已抽籤時不加鎖直接回傳；未抽籤才鎖賽事，鎖內發現剛被抽完仍回順延輪次。
- `forfeit_next_due` 新增 `failed_ids` keyword 參數，`make_forfeit_job` 閉包持有，同一輪略過已失敗場次、工作回傳 False 時清空。
- 暫時拿掉 `begin_nested` 時，新的兩個失敗測試會失敗（2 failed, 14 passed），還原後 16 passed。
- `audit_log` 有禁止刪除的觸發器，所以 `test_check_in.py` 的 `_audit_count` 改為只算仍對應現存場次的紀錄。
- #43、#49 作者經 `gh pr view` 確認為 OG-Matcha。

## Spec Change Log

- 2026-11-25 第 1 次修訂（實作回報觸發）：原本以為已有 GET API 回傳 `delayed_rounds`，實際上只有 `POST /draw` 的回應有。實作子代理因此在前端重算一份規則，形成第二個真實來源，日後後端規則一改兩邊就會分歧。修訂內容：允許在 `GET /organizer/tournaments/{id}/draw-status` 的 `DrawStatus` 加上 `delayed_rounds: list[int]`（已抽籤時用 `get_bracket` 同一套計算填入，其他情況為空陣列），並重新產生 client；前端改讀這個欄位，刪除 `delayed-rounds.ts` 的重算。擁有者沒有回覆，依「照建議走」規則採用。KEEP：`DelayedRoundsNotice` 的文字與輪次名稱格式、只在 published／ongoing 顯示、讀取失敗靜默、`forfeit_job` 與其他後端與文件變更全部保留。

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap）：

| # | 來源 | 判定 | 證據／處理 |
|---|------|------|-----------|
| 1 | VG 主要、BH | medium → patch | 兩個棄權失敗測試都在寫入前丟錯；拿掉 savepoint 仍會通過。補真實 SQL 錯誤（`SELECT 1 / 0`）與 audit 寫入後才失敗兩種測試。 |
| 2 | BH、VG、ECH | medium → patch | `get_draw_status` 先 `lock_tournament`（service.py:317）才判斷已抽籤；S27 在 published／ongoing 會和報到、比分、棄權搶賽事列鎖。已抽籤路徑改為不加鎖讀取後提早回傳。 |
| 3 | BH、VG、ECH | medium → patch | `test_check_in_concurrency.py` 的 cleanup 沒刪 `match.checked_in` 操作紀錄，`test_check_in.py` 斷言全域筆數，執行順序一換就失敗。 |
| 4 | ECH | low → patch | `run_once` 每輪最多呼叫工作 `max_items` 次，永久失敗那場每次呼叫都被重試並記 traceback；同一輪內略過已失敗的場次。 |
| 5 | BH、VG、ECH | medium → patch | 凍結矩陣「賽程讀取失敗 → 不顯示提示」，實作卻顯示只有號碼的提示；改成依矩陣不顯示。 |
| 6 | BH | low → patch | 永久失敗測試沒在第一次 `run_once` 後就檢查其他場次，補上「同一輪」的斷言。 |
| 7 | BH | false | 刪除 4.3 延後項目：`service.py` 的 `reschedule` 已取 `min(next_times)`，且有 `test_reschedule.py::test_semifinal_upper_bound_uses_earlier_of_final_and_third`，早已修好。 |
| 8 | BH | low → reject | Spec 的 Code Map／驗證指令過時；由主代理直接更新 spec，不改程式。 |
| 9 | BH | low → reject | 提示整個進行中都存在：矩陣明定順延不為空且未結束就顯示，屬於設計。 |
| 10 | ECH | low → reject | 主辦方停在 S27 時自動抽籤，要重新整理才看到提示；要補輪詢，日常少見。 |
| 11 | ECH | low → reject | 執行緒 join 逾時後 cleanup 可能卡住：只在測試本身已失敗時發生。 |
| 12 | BH | low → reject | 追溯表只補 Story 沒補 FR：檢查只要求至少一個，不影響正確性。 |
| 13 | BH | low → reject | 永久失敗沒有告警：既有 `auto_draw_due` 同樣只記 log（deferred-work 已列）。 |
| 14 | BH | false | #43、#49 歸屬未查：已用 `gh pr view` 確認作者為 OG-Matcha（實作回報）。 |
| 15 | BH | low → reject | 沒有「抽籤後立即出現提示」的整合測試；`draw-queries` 抽籤後讓 draw-status 與賽程失效，單元測試已涵蓋顯示。 |

## Verification

**Commands:**
- `docker compose up -d --build --wait`，再跑 `docker compose exec -T backend bash scripts/tests-start.sh tests/competition/test_draw_status.py tests/competition/test_forfeit_job.py tests/competition/test_check_in_concurrency.py tests/competition/test_check_in.py tests/test_traceability.py`：預期全部通過（若 traceability 檢查檔名不同，用 `ls backend/tests | grep -i trace` 找實際檔名）。
- `docker compose exec -T backend bash scripts/lint.sh`：預期結束碼 0。
- 前端：`docker compose run --rm --no-deps -T frontend bunx vitest run tests/unit/<新測試檔>`，或照 `frontend/package.json` 的 test 指令：預期全部通過；`bunx tsc --noEmit` 與 biome lint 結束碼 0。
- 收尾一定要 `docker compose down`，並刪除 worktree 裡的 `.env`。

**Manual checks:**
- `git diff origin/main --stat` 只包含 competition、D 的測試、traceability、重新產生的 `frontend/src/client/` 與 `_bmad-output` 的檔案；另外 `organizer-tournaments`、`custom-mode-invite` 測試只補 mock 欄位。
