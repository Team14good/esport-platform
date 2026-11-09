---
title: 'Story 6.5（第一階段）：competition 取消資格與對戰表頂替'
type: 'feature'
created: '2026-11-08'
status: 'done'
baseline_commit: '41084e4cb6b6624df234368487aecc87a915fa5a'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 6.5 的檢舉資料表由 C 的 6.4 建立，還沒合併；但取消資格後的對戰表頂替規則不依賴檢舉，可以先做，讓 6.4 合併後只剩接上檢舉處理。

**Approach:** 第一階段只做 competition 的 `disqualify` 公開函式（寫在新檔 `competition/disqualification.py`，`service.py` 只新增公開函式），依 epic-6-context〈取消資格（期中版）〉的 7 種情況改報名狀態、判對手獲勝或頂替；不做 API、畫面與檢舉處理（第二階段，等 6.4）。

## Boundaries & Constraints

**Always:**
- 呼叫順序：`lock_tournament` → 鎖該賽事的場次 → 判斷 → 寫入（AD-6）。
- 以 registration 的報名狀態為「取消資格」的唯一紀錄；抽籤前與抽籤後都把報名改為 `disqualified`。
- 兩隊都在場的場次判對手獲勝時用 `MatchOutcome.DISQUALIFIED`（不能用 walkover：兩隊都在場的 walkover 會被 progression 拒絕）；確認後沿用 `advance` 晉級。
- 頂替改變場次的隊伍後，對該場呼叫 `unassign_referee_if_member`；兩隊湊齊且場次為 `scheduled` 時 `start_forfeit_clock`。
- 每個被改動的場次寫操作紀錄（操作者為 `actor_id`），回傳 `DisqualifyResult`：受影響的場次 id、頂替隊伍 id（沒有則 null）。
- 只新增 D、C 模組的檔案或公開函式，不改既有函式；列進 PR 說明給 D、C 審查。

**Never:**
- 不做候補遞補（期中版）；抽籤前只改報名狀態，空出的名額交給 3.4 的 `backfill_vacancies`。
- 不改已確認場次的結果、更早的對戰結果與名次。
- 不做檢舉處理 API、S33、S27 待處理清單、申訴一併結案（第二階段與 6.2）。

## I/O & Edge-Case Matrix

| 情況 | 狀態 | 結果 |
|---|---|---|
| 抽籤前 | 尚無對戰表，報名為待分配／正取／候補 | 只改報名狀態 |
| 進行中／申訴期／申訴中 | 該隊有 `live`、`appeal_window`、`appealed` 場次 | 該場以 DISQUALIFIED 判對手獲勝並確認、晉級；不頂替 |
| 還沒比過、對手在場 | 第一場 `scheduled` | 該場以 DISQUALIFIED 判對手獲勝並確認、晉級；對戰樹顯示「取消資格」 |
| 還沒比過、對手未定 | 第一場 `scheduled`，另一側等前一場勝隊 | 409 `DISQUALIFY_OPPONENT_PENDING`，不改任何資料（報名、場次、操作紀錄、事件都不變） |
| 已贏過、等下一場 | 下一場 `scheduled` | 由最近一場輸給它的隊伍頂替原位置 |
| 決賽隊伍、季軍賽未開打 | 決賽 `scheduled` | 準決賽輸給它的隊伍從季軍賽移到決賽；季軍賽由對手輪空（walkover）奪季軍 |
| 決賽隊伍、季軍賽另一方未定 | 決賽 `scheduled`、要由準決賽敗隊頂替，季軍賽另一方等前一場勝隊 | 409 `DISQUALIFY_OPPONENT_PENDING`，不改任何資料 |
| 決賽隊伍、季軍賽已開打或已定案 | 同上 | 不頂替，決賽以 DISQUALIFIED 由對手獲勝，亞軍從缺 |
| 等季軍賽 | 季軍賽 `scheduled` | 季軍賽由對手獲勝，不頂替 |
| 已淘汰／沒有下一場 | 全部已確認 | 只改報名狀態 |
| 賽事已結束或已取消 | — | 409 `TOURNAMENT_FINISHED`／`TOURNAMENT_CANCELLED`，不改任何資料 |
| 已取消資格 | 報名已是 `disqualified` | 409 `TEAM_ALREADY_DISQUALIFIED` |

## Decisions

- 2026-11-08（使用者）：本 Story 拆兩階段。第一階段只做 competition `disqualify` 與 registration 的取消報名函式；檢舉處理 API、S33、S27 待處理清單、對戰樹標記等 C 的 6.4 合併後做。
- 2026-11-08（使用者）：還沒比過任何場次、對手已在場時，以 DISQUALIFIED 確認、對手晉級，對戰樹顯示「取消資格」，不照 epic 期中版字面的 walkover（兩隊都在場的 walkover 會被 progression 拒絕，也看不出取消資格）。
- 2026-11-08（使用者）：spec 超過 1,600 tokens 仍維持完整，7 種情況在同一個 PR 完成。
- 2026-11-09（D）：對手未定時拒絕取消資格。回 409 `DISQUALIFY_OPPONENT_PENDING`（「對手尚未確定，請等對手確定後再取消資格。」），不改任何資料、progression 不動；涵蓋輪空入座等另一場勝隊的一方，以及決賽要由準決賽敗隊頂替而季軍賽另一方未定。progression 支援「這一方確定不會有隊伍」列為期中後（deferred-work）。2026-11-09 使用者同意依此修改本區塊的情況表。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/models.py` -- `Match`（team_a/b_id、bye_a/b、status、outcome、winner_id、next_match_id、loser_next_match_id、is_third_place）；`MatchOutcome.DISQUALIFIED` 已存在；新增 `DisqualifyResult` schema。
- `backend/app/modules/competition/service.py` -- 只新增 `disqualify`；沿用 `lock_match`、`transition_match`、`confirm_match`（只接受 live／appeal_window／appealed）、`confirm_walkover`（只剩一隊時）、`advance`、`start_forfeit_clock`、`unassign_referee_if_member`（只接受 scheduled／live）、`get_bracket`。`scheduled` 的場次要確認時走 `scheduled → confirmed`，可在 competition 內呼叫 `_confirm` 再 `advance`，不修改它們。
- `backend/app/modules/competition/progression.py` -- `MatchState.loser()` 判斷誰輸給它；`_check_consistent` 的 DISQUALIFIED／WALKOVER 規則；`podium` 對 DISQUALIFIED 決賽亞軍從缺；docstring 說 6.5 先換隊伍再 `advance`。
- `backend/app/modules/competition/repository.py` -- `set_match_team` 不能設 None；新增「清空某側隊伍」函式（只新增）。
- `backend/app/modules/competition/registration_port.py` -- 新增包裝新的 registration 函式。
- `backend/app/modules/registration/service.py` -- 只新增 `disqualify_registration(session, *, team_id, actor_id) -> RegistrationRead`（內部用既有 `mark_status`；competition 不能讀 registration 的 ORM，AD-2）。
- `backend/tests/competition/conftest.py`、`test_confirm_advance.py` -- `fake_registration`（要補新 port）、`draw_with`、`_eight_to_semis`、`_to_finals`、`frozen_clock`。

## Tasks & Acceptance

**Execution:**
- [x] `registration/service.py`、`competition/registration_port.py` -- 新增取消報名的公開函式與 port
- [x] `competition/repository.py` -- 新增清空場次一側隊伍的函式
- [x] `competition/disqualification.py`、`competition/service.py`、`competition/models.py` -- 實作 7 種情況與 `DisqualifyResult`
- [x] `tests/competition/test_disqualify.py`、`tests/registration/` -- 每種情況一個以上測試；含裁判是頂替隊伍隊員時被收回、頂替後兩隊湊齊開始計時、操作紀錄
- [x] `contracts/disputes.md`、`deferred-work.md`、`sprint-status.yaml` -- 補 `DisqualifyResult` 欄位；新增「6.5 第二階段：resolve_report、S33、S27 待處理清單、對戰樹取消資格標記」；6-5 改 `in-progress`

**Acceptance Criteria:**
- Given 8 隊對戰表、某隊贏了第 1 輪等第 2 輪，when 取消資格，then 第 1 輪輸給它的隊伍出現在第 2 輪同一側，第 1 輪結果不變，報名為 `disqualified`。
- Given 同一隊，when 公開對戰表重新取得，then 頂替隊伍出現且 `updated_at` 變新。

## Design Notes

- 最近一場輸給它的隊伍：依輪次往前找第一場 `played`／`forfeit` 且由它獲勝的場次的敗隊；找不到（只靠輪空或 walkover 晉級），或那隊已取消資格，就改為對手獲勝，不頂替。
- 對手還沒確定（等另一場的勝隊）：把該隊移出場次並標記這一側不會有隊伍，之後由 `advance` 讓對手以 walkover 晉級；實作時先確認 progression 支援，不支援就停下回報。決賽、季軍賽的對手未定時同樣處理。

## Implementation Notes

- 2026-11-08（實作）：**對手未定的情況 progression 不支援，已停下回報**。`progression.advance` 的 `side_team` 只依 plan 的來源推導一方是否定案：輪空直接入座的一方沒有來源、永遠不會定案；由勝場進來的一方被清空後會被重新填回原隊伍（決賽頂替時，季軍賽的那一方也會被填回已移到決賽的隊伍）。沒有不改既有函式的標記方式，所以這些情況（還沒比過／只靠 walkover 晉級而對手未定、決賽頂替而季軍賽另一方未定）`disqualify` 拋 `NotImplementedError`、不改任何資料，記在 deferred-work.md，待人決定（例如請 D 在 progression 新增「這一方確定不會有隊伍」的表示）。
  - 2026-11-09 更新：D 決定對手未定時拒絕，改拋 409 `DISQUALIFY_OPPONENT_PENDING`（`disqualification._opponent_pending`），兩個測試改為斷言 409，且報名、場次、操作紀錄、outbox 事件都不變。
- 決賽的頂替只看準決賽（勝隊進入決賽的那一場）：準決賽是 walkover／取消資格勝（沒有敗隊）時不往更早的輪次找，改為對手獲勝；其他輪次依 Design Notes 往前找第一場 `played`／`forfeit` 勝場。只有 3 隊（沒有季軍賽）時決賽直接由準決賽敗隊頂替。這是對情況表「準決賽輸給它的隊伍」的解讀，待人確認。
- 隊伍的報名不屬於傳入的賽事時回 404 `REGISTRATION_NOT_FOUND`（沿用 registration 的錯誤碼與訊息，spec 未規定）。
- 操作紀錄：判對手獲勝沿用 `_confirm` 的 `match.confirmed`（操作者 `actor_id`）；換隊新增 action `match.teams_changed`（`before`／`after` 為兩隊 id，`after` 另含 `disqualified_team_id`）。季軍賽移出隊伍後的 walkover 確認經 `confirm_walkover`，操作者為系統。
- 頂替後只對「換入隊伍的場次」呼叫 `unassign_referee_if_member`（季軍賽只是移出隊伍，不會產生裁判衝突，隨即以 walkover 確認）。
- `service.py` 在檔頭 import `disqualification`、`disqualification.py` 在檔頭 import `service`（模組互相 import，只在呼叫時取屬性）；ruff 把新的 import 併入既有的 `from app.modules.competition import (...)`。

## Spec Change Log

- 2026-11-09：依 D 在 PR #65 的決定（使用者同意修改凍結區塊），情況表「還沒比過、對手未定」由「移出場次、對手確定後以 walkover 晉級」改為 409 `DISQUALIFY_OPPONENT_PENDING`、不改任何資料，並新增「決賽隊伍、季軍賽另一方未定」一列；`disqualify` 原本在這些情況拋的 `NotImplementedError` 改為此 409。deferred-work 原「尚未支援」項目已處理而刪除，新增期中後項目「progression 支援『這一方確定不會有隊伍』」。

## Review Triage Log

2026-11-09 第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap；差異範圍為 `origin/main..` 工作區，不含本 spec）：

| # | 來源 | 發現 | 判定 | 處理 |
|---|---|---|---|---|
| 1 | Blind、Edge | `_replace` 兩隊湊齊時只 `start_forfeit_clock`，沒有像 `advance` 發 `MatchOpponentsDecided`，頂替隊伍與對手收不到新對手通知 | medium：`service.advance` 在 StartForfeitClock 會發事件，`_replace` 沒有 | patch：補發事件，頂替測試斷言 outbox |
| 2 | Edge、Blind | 被取消資格的隊伍已在待開打場次報到後被頂替，報到紀錄殘留；`forfeit.judge_forfeit` 遇到不屬於這場的報到拋 `ValueError`，棄權 worker 每輪卡在該場 | high：報到在開打前可完成，`check_in` 唯一鍵不會清除 | patch：新增 `repository.delete_check_in`，頂替時刪除（決賽頂替也刪頂替隊伍在季軍賽的報到），補測試 |
| 3 | Verification Gap、Blind | `reversed(wins)` 與略過 walkover 勝場的規則沒有兩場以上勝場的測試；docstring「只靠輪空或 walkover 晉級」與實作（略過其間 walkover 往前找）讀起來不一致 | medium（驗證缺口，已預先查證） | patch：16 隊補「最近一場敗隊頂替」「第 2 輪 walkover 改由第 1 輪敗隊頂替」兩個測試；docstring 改寫 |
| 4 | Blind | 報名不能轉為取消資格時 registration 拋 409 `REGISTRATION_INVALID_TRANSITION`，contract 與 `service.disqualify` docstring 沒列 | low：直接補文件 | patch：contract 與 docstring 補上 |
| 5 | Edge | `get_registration_state` 若讀到鎖賽事前已在 identity map 的報名，`disqualified` 可能過時 | maybe-false：第一階段 `disqualify` 一開始就 `lock_tournament`，之前不讀報名；第二階段 `resolve_report` 是否先讀報名未知，若成立為 medium | defer（未驗證） |
| 6 | Edge、Blind | 已退賽（`RETIRED`）的敗隊會被放回對戰表 | false：目前沒有任何程式把報名改為 `RETIRED`（只出現在轉換表），無法到達 | reject |
| 7 | Edge | 準決賽敗隊不在待開打的季軍賽時 `_side_of` 拋 `ValueError` | false：準決賽確認時 `advance` 一定把敗隊填入季軍賽；敗隊已取消資格時在之前就回 None | reject |
| 8 | Blind | `disqualification.py` 與 `service.py` 互相 import、呼叫 `service._confirm` | false：spec Code Map 明定在 competition 內呼叫 `_confirm`，互相 import 已記於 Implementation Notes；修正需改 spec | reject |
| 9 | Blind | 判對手獲勝的待開打場次保留 `forfeit_deadline` | false：棄權 worker 只查 `scheduled` 的場次，已確認的場次不會被處理 | reject |
| 10 | Blind | 頂替時重算棄權期限會延後對手的期限；`match.status == SCHEDULED` 多餘 | false：spec 規定兩隊湊齊時 `start_forfeit_clock`，`both_known_at=now` 是頂替隊伍得知對手的時間；多餘條件已在修正 1 一併移除 | reject |
| 11 | Blind | `assert` 在 `python -O` 會被移除；「沒有季軍賽（3 隊）」註解 | low：專案不以 `-O` 執行，條件由呼叫端保證 | reject |
| 12 | Blind | `registration_port._DISQUALIFIED` 寫死字串 | low：port 依 `_lookup` 取用 registration 函式，不 import registration 模型（AD-2）；registration 改值的機會低 | reject |
| 13 | Blind | 其他測試缺口：抽籤前不發事件、`_plan` 的兩個 `ValueError`、13 隊非輪空隊伍、registration 其他拒絕狀態、真 registration 端對端 | low：防禦性分支或已由既有測試間接涵蓋，日常使用不會遇到 | reject |

## Verification

**Commands:**
本工作樹與其他工作樹的容器同時在跑，所有 compose 指令都加 `-p espory-6-5 -f compose.yml -f "C:/Users/grace/AppData/Local/Temp/claude/8ed1151532dbf623/1fabc1f3-312d-4d81-a1f5-4b734a9929d3/scratchpad/ports-6-5.yml"`（改用 38000 等連接埠與 `flow-backend:6-5` 映像），以下簡寫為 `dc`；不要停止或重建其他專案的容器。

- `dc up -d --build --wait db backend` 後 `dc exec backend bash scripts/test.sh` -- expected: 全部通過、覆蓋率門檻通過
- `dc exec backend bash scripts/lint.sh` -- expected: mypy、ty、ruff 通過
