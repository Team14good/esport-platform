---
title: '6.2／6.5 前置：competition 新增重賽時間與裁判收回的公開函式'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: 'a6f9ea8d7762f09c20d361f76dc6e2cb72fea925'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** B 的 disputes 約定（#55，D 審查後合併）要求 6.2 `replay_match` 用與 4.3 改期相同的規則檢查重賽時間、S32 要顯示可選範圍，6.5 `disqualify` 頂替後要重新檢查裁判衝突；這些規則目前都在 competition 的私有函式（`_reschedule_window`、`_unassign_if_member`），B 不能呼叫。

**Approach:** competition 只新增三個公開函式包住既有私有函式，不改既有函式的行為：`check_replay_time`、`get_replay_window`、`unassign_referee_if_member`。名稱與簽名照 `contracts/disputes.md`〈四〉。

## Boundaries & Constraints

**Always:**
- `check_replay_time(session, *, tournament, match, scheduled_at) -> None`：以 4.3 同一個 `_reschedule_window` 檢查；不符合拋與 `reschedule_match` 相同的錯誤碼與訊息（`RESCHEDULE_BEFORE_NOW`／`RESCHEDULE_BEFORE_FEEDER`／`RESCHEDULE_AFTER_NEXT_MATCH`／`RESCHEDULE_NO_VALID_TIME`，409，訊息附台北時間範圍）。不檢查賽事狀態、場次狀態、報到、主辦方（呼叫端 `replay_match` 負責），不寫入任何資料。
- `get_replay_window(session, *, match_id) -> RescheduleInfo`：同一個範圍。判斷順序：賽事不是 `published`／`ongoing` → `can_reschedule=False`、`reason="tournament_not_reschedulable"`、範圍 null；場次不是 `appealed` 或 `outcome` 不是 `forfeit`（重賽只用於棄權）→ `reason="match_not_reschedulable"`、範圍 null；其餘依範圍是否為空（空的時 `reason="no_valid_time"`，仍附 `earliest`）。不存在的場次 404 `MATCH_NOT_FOUND`。不寫入。
- `unassign_referee_if_member(session, *, match) -> None`：該場裁判是任一隊（`team_a`、`team_b`）的隊員時收回，寫 `match.referee_unassigned`（操作者為系統）、發 `RefereeUnassigned`，與 `advance` 的行為相同；不是隊員、沒有裁判、隊伍待定時不動。
- 錯誤訊息與 `reschedule_match` 共用同一段程式產生，避免分岔。
- contracts/competition.md〈公開函式〉補三列；disputes.md 的 ★ 不改（B 的檔案）。

**Never:**
- 不改 `reschedule_match`、`advance` 對外行為；不新增 API、資料表或遷移；不改 tournaments、registration、disputes。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 重賽時間合法 | appealed 場次、範圍內的時間 | 回 None、不寫入 | — |
| 早於最早可選 | 現在＋30 分鐘以前 | `RESCHEDULE_BEFORE_NOW` 409、訊息附範圍 | 不寫入 |
| 晚於下一場 | 超過下一場減間隔 | `RESCHEDULE_AFTER_NEXT_MATCH` 409 | 不寫入 |
| 申訴拖久 | 下一場已早於最早可選 | `RESCHEDULE_NO_VALID_TIME` 409；`get_replay_window` 回 `can_reschedule=False`、`no_valid_time`、附 `earliest` | — |
| 決賽重賽 | 無下一場 | `latest=None`，只限下限 | — |
| 視窗查詢非申訴中 | scheduled 等 | `can_reschedule=False`、`match_not_reschedulable` | — |
| 視窗查詢非棄權 | appealed、outcome=played | `match_not_reschedulable` | — |
| 視窗查詢賽事已取消／結束 | appealed、賽事 cancelled／finished | `tournament_not_reschedulable` | — |
| 頂替進來的隊伍含裁判 | 裁判是新隊伍隊員 | 收回、操作紀錄、事件 | — |
| 裁判不是隊員／無裁判／隊伍待定 | — | 不動、不寫紀錄 | — |

## Decisions

- 2026-11-05（使用者授權「先把自己能做的事情做」；D 在 #55 審查提議、B 依此更新約定並合併）：三個函式的名稱、簽名、行為照 `contracts/disputes.md`〈四〉。
- 2026-11-05（D）：`get_replay_window` 對非申訴中的場次回 `match_not_reschedulable` 而非拋錯，讓 S32 只看一個欄位。
- 2026-11-05（使用者，審查後）：`get_replay_window` 另外擋「賽事不是賽程已公布或進行中」（`tournament_not_reschedulable`）與「結果不是棄權」（`match_not_reschedulable`），與 `replay_match` 的拒絕條件一致。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/service.py`：`_reschedule_window`（約 1614）、`reschedule_match`（約 1687，錯誤訊息）、`_unassign_if_member`（約 767）、`advance`
- `backend/app/modules/competition/models.py`：`RescheduleInfo`
- 測試：`tests/competition/test_reschedule.py`、`test_replay_clear.py`、`test_assign_referee.py`、`test_confirm_advance.py` 的資料準備

## Tasks & Acceptance

**Execution:**
- [x] 三個公開函式；`reschedule_match` 的錯誤訊息抽成共用 helper
- [x] 測試涵蓋 I/O 矩陣，含「與 `reschedule_match` 對同一時間給出相同錯誤碼與訊息」與「不寫入」
- [x] contracts/competition.md、sprint-status 註記（sprint-status 不需改，見偏差）

**Acceptance Criteria:**
- Given 申訴中的場次與下一場已過近的情況，when `check_replay_time`，then 拋 `RESCHEDULE_NO_VALID_TIME`，且 `get_replay_window` 回 `no_valid_time`。
- Given 裁判是某隊隊員，when `unassign_referee_if_member`，then 裁判被收回、寫一筆系統操作紀錄、發一個 `RefereeUnassigned`。

## Implementation Notes

- `service.py` 新增 `_reschedule_error(reason, window)`，產生 `RESCHEDULE_*` 409 的錯誤碼與訊息；`reschedule_match` 改呼叫它（訊息文字逐字不變），`check_replay_time` 也呼叫它，兩邊不會分岔。
- 三個公開函式放在 `reschedule_match` 之後的「6.x 前置（B 呼叫）」段落，只包既有私有函式：
  - `check_replay_time`：`repository.list_matches(fresh=True)`（與 `reschedule_match` 相同，讀相鄰場次最新值）→ `_reschedule_window` → `_reschedule_error`。不檢查任何狀態、不寫入。
  - `get_replay_window`：`repository.get_match`（不加鎖，唯讀；不存在 404）→ `list_matches(fresh=True)`（本場與相鄰場次讀最新值，與 `check_replay_time` 一致）→ 賽事不是 published／ongoing 回 `tournament_not_reschedulable` → 不是 `appealed` 或 `outcome` 不是 `forfeit` 回 `match_not_reschedulable`（兩者範圍皆 None）→ 算同一個範圍，空的時 `no_valid_time` 並附 `earliest`、`latest`（與 S30 列表 `list_managed_matches` 的作法相同）。
  - `check_replay_time` 開頭檢查 `tournament.id != match.tournament_id` 時拋 `ValueError`（呼叫端的程式錯誤，不是業務錯誤）。
  - `unassign_referee_if_member`：對 `team_a_id`、`team_b_id` 依序呼叫 `_unassign_if_member`；第一次收回後裁判已是 None，第二次直接返回，所以裁判同時是兩隊隊員也只寫一筆紀錄、發一個事件（有測試）。
- 測試 `tests/competition/test_replay_hooks.py`（第 1 輪審查後 37 個）：沿用 `test_reschedule` 的 8 隊對戰表與 `Setup`，`is_member` 以集合替身（同 `test_assign_referee`）。「相同錯誤」的等價情境是**同一場、同一時間**：先以 `appealed` 呼叫 `check_replay_time`，不 rollback 直接比對「不寫入」，再把場次改回 `scheduled` 呼叫 `reschedule_match`，比對 code、message、status（涵蓋 BEFORE_NOW、BEFORE_FEEDER、AFTER_NEXT_MATCH、NO_VALID_TIME）。「不寫入」比對全部場次欄位（狀態、時間、棄權期限、裁判、`updated_at`）、該賽事操作紀錄數、outbox 事件總數；比對前先 flush 再 `expire_all`，拋錯前若寫過欄位（即使未 commit）也會被看到。另有：M1 範圍訊息逐字斷言、季軍賽早於決賽時準決賽取較早的一場、轉回 scheduled 與有報到資料時結果與 appealed 相同、相鄰場次被其他交易改過（`update()` 不同步 identity map）時讀到新值、tournament／match 不符與沒帶時區拋 `ValueError`、`get_replay_window` 的 outcome 不是棄權與賽事 cancelled／finished／closed、一方待定時收回已定那隊的隊員裁判。`is_member` 替身以 None 呼叫時直接失敗，並記錄呼叫，無裁判與兩隊待定時斷言沒呼叫。
- 變異檢查（都已改回）：
  - `unassign_referee_if_member` 只檢查 `team_a` → `test_member_referee_is_unassigned[sides1]` 紅。
  - 第 1 輪：`check_replay_time` 拋錯前先 `set_scheduled_at`（先寫再拋）→ `test_same_error_as_reschedule_match` 5 組與 `test_window_for_appealed_match_matches_check` 紅。
  - 第 1 輪：`_reschedule_window` 只看 `next_match_id` → `test_semifinal_uses_earlier_of_final_and_third_place` 紅。
  - 第 1 輪：`get_replay_window` 拿掉 `fresh=True` → `test_reads_latest_neighbour_times` 紅。
- 偏差：
  - `sprint-status.yaml` 不需改（B 的 6.x 未開工，沒有合適的註記處）；Tasks 第三項以 contracts 完成。
  - contracts/competition.md 除〈公開函式〉加三列外，也把 4.4 段落「目前只有 `advance` 實作，6.2、6.5 做到時補上」改成指向 `unassign_referee_if_member`（D 自己的約定文件，避免與新函式矛盾）。
  - `check_replay_time` 的 `scheduled_at` 必須帶時區（沒帶時區由 `schedule._utc` 拋 `ValueError`，有測試）；與 4.3 一樣交給 router 的欄位驗證，寫在 docstring 與約定。
  - 沒有新增 API，OpenAPI 不變，不需重新產生 client。

## Spec Change Log

- 2026-11-05 第 1 輪審查後（使用者核准）：`get_replay_window` 加賽事狀態與 outcome 判斷；I/O 矩陣補兩列。

## Review Triage Log

第 1 輪（Blind Hunter 只看 diff、Edge Case Hunter 兼 Verification Gap；無高嚴重度）：

- 修正（spec 缺口，使用者決定）：`get_replay_window` 對已取消／已結束賽事、非棄權的申訴場次仍回可改 → 加 `tournament_not_reschedulable`、`match_not_reschedulable` 判斷。
- 修正：`get_replay_window` 讀相鄰場次沒用最新值，與 `check_replay_time` 範圍可能不同 → `fresh=True`；`check_replay_time` 傳入的賽事與場次不符時拋 `ValueError`。
- 修正（測試）：錯誤路徑的「不寫入」在 rollback 後才比對，必定相等 → 不 rollback、flush 後比對（變異「先寫再拋」6 個轉紅）；錯誤訊息兩邊共用 helper 是循環比對 → 加逐字斷言；季軍賽與決賽同時間，測不到「準決賽取較早一場」→ 錯開時間（變異轉紅）；`is_member` 替身對 None 回 False，測不到待定檢查 → 改為斷言；補一方待定、狀態與報到不影響結果、讀最新值（變異轉紅）。
- 修正（文件）：約定註明 `unassign_referee_if_member` 檢查兩隊（與 `advance` 不同）、只對 scheduled／live 呼叫；S32 收到 `RESCHEDULE_BEFORE_NOW` 要重抓範圍；時區錯誤是 `ValueError` 不是 `TypeError`。
- 不改：`reschedule_match` 只多一層 helper，錯誤碼、訊息、順序不變（兩位審查員都確認）。

## Verification

**Commands:**
- 主 repo 執行、掛 worktree：`bash scripts/test.sh; bash scripts/lint.sh` -- 全部通過（含 `test_architecture.py`）
