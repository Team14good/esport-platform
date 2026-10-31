---
title: 'Story 5.5（第一階段）：晉級推進規則（含 5.6 的季軍賽、雙方棄權與名次）'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '1e9e0b407fd64a925cc3e2b0add792c6fb947b80'
route: 'dispatch'
review_loop_iteration: 2
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-bracket-generator.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 場次確認後要把勝隊填進下一場、準決賽敗隊填進季軍賽，遇到確定沒有隊伍的位置要自動輪空並一路推進，最後判定名次。這套規則 5.5、5.6 要用，B 的 6.2（更正結果）與 6.5（取消資格頂替）也要沿用，但 Match 資料表要等上游 2.2 合併才能建。

**Approach:** 在 competition 寫純函式 `advance(plan, states, code)`：輸入 4.1 的 `BracketPlan`、各場目前狀態與剛確認的場次，回傳依序要套用的變更清單（填位、輪空確認、季軍賽取消、起算棄權、賽事結束與名次）。第二階段的 service 在交易內鎖定後依清單寫入資料表。

## Boundaries & Constraints

**Always:**
- 勝隊依 plan 的 `next_code`／`next_side` 填入下一場；準決賽的敗隊依 `loser_next_code` 填入季軍賽的對應一方（第一場準決賽 → a，第二場 → b）。
- 一方「確定沒有隊伍」＝來源場次已確認但沒有對應的隊伍：取勝者時來源沒有勝隊；取敗者時來源沒有敗隊（雙方棄權、兩方皆空的輪空、一方空的輪空、取消資格）。
- 一般場次：一方確定沒有隊伍、另一方已有隊伍 → 以 `walkover` 確認，該隊為勝隊，繼續推進；兩方都確定沒有隊伍 → 以 `walkover`、無勝隊確認，繼續推進；另一方還在等 → 等待。
- 季軍賽：任一場準決賽沒有產生勝隊 → 季軍賽轉為 `voided`（outcome 與勝隊為空）；否則照一般場次規則（例如一場準決賽是有勝隊的輪空，另一場的敗隊以 walkover 得季軍）。
- 兩方都填入隊伍、且場次不是輪空確認時，回傳「起算棄權期限」，由 service 呼叫 `start_forfeit_clock`。
- 決賽已確認，且季軍賽已確認、已取消或不存在 → 回傳「賽事結束」與名次：冠軍＝決賽勝隊；亞軍＝決賽的另一隊，決賽是輪空時為冠軍那一側準決賽的敗隊，決賽以「取消資格」確認時從缺（FR-22，使用者 2026-10-29 決定）；季軍＝季軍賽勝隊，季軍賽取消或不存在時從缺。
- 準決賽以「取消資格」確認時，被取消資格的隊伍不進季軍賽（該側沒有敗隊），季軍賽依一般規則處理。
- 已確認或已取消的場次不會再被變更。
- 對同一個已確認的場次重複呼叫，不產生重複的變更（已填入的位置不再填）。

**Never:**
- 不碰資料庫、不 import 其他模組、不讀時鐘、不發事件、不寫操作紀錄。
- 不處理裁判衝突（填位後指派的裁判是隊員）：需要查隊員，由第二階段的 service 依回傳的填位結果處理。
- 不處理退賽遞補與取消資格頂替的選隊（6.5 由 B 負責，只沿用本模組的推進）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 一般晉級 | 8 隊，M1 確認、勝隊 X | 填入 M5 的 a；M5 另一方未定，不起算 | N/A |
| 下一場湊齊 | 接著 M2 確認、勝隊 Y | 填入 M5 的 b，起算 M5 棄權期限 | N/A |
| 準決賽 | M5 確認（勝 X、敗 Y） | X 進決賽、Y 進季軍賽 a | N/A |
| 雙方棄權 | 8 隊，M1 雙方棄權，M2 勝隊 Y | M5 以 walkover 確認、Y 勝，Y 再進 M7 | N/A |
| 兩方皆空連鎖 | M1、M2 都雙方棄權 | M5 以 walkover、無勝隊確認，M7 的 a 確定沒有隊伍 | N/A |
| 準決賽雙方棄權 | 4 隊，M1 雙方棄權，M2 勝 X 敗 Y | 決賽 walkover、X 冠軍；季軍賽 voided；Y 亞軍、季軍從缺；賽事結束 | N/A |
| 正常結束 | 決賽與季軍賽都已確認 | 賽事結束，冠、亞、季軍 | N/A |
| 沒有季軍賽 | 3 隊，決賽確認 | 賽事結束，只有冠軍、亞軍 | N/A |
| 決賽取消資格 | 決賽以 `disqualified` 確認、勝隊 X，季軍賽已確認 | 賽事結束，X 冠軍、亞軍從缺、季軍照季軍賽 | N/A |
| 重複呼叫 | 對同一個已處理的確認再呼叫 | 不回傳重複的填位 | N/A |
| 場次未確認 | 呼叫 `advance` 的場次不是已確認 | — | `ValueError` |
| 不存在的場次 | 不在 plan 裡的編號 | — | `KeyError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/progression.py` -- 新檔：`MatchState`（frozen dataclass：`team_a`、`team_b`、`status`、`outcome`、`winner`）、變更型別、`advance()`、`podium()`
- `backend/app/modules/competition/bracket.py` -- 4.1 的 `BracketPlan`、`PlannedMatch`（`next_code`、`next_side`、`loser_next_code`、`source_a/b`、`bye_a/b`、`is_third_place`）；只讀不改
- `backend/app/modules/competition/models.py` -- 沿用 `MatchStatus`、`MatchOutcome`；不改
- `backend/tests/competition/test_bracket.py` -- 測試寫法參考

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/progression.py` -- 新增狀態與變更型別（`FillSlot`、`ConfirmWalkover`、`VoidMatch`、`StartForfeitClock`、`TournamentFinished`）、`advance()` 與 `podium()` -- 讓 5.5、5.6、6.2、6.5 共用同一套推進規則
- [x] `backend/tests/competition/test_progression.py` -- I/O 矩陣每一列；以 4.1 的 `plan()` 產生 2～32 隊的對戰表，隨機決定每場結果（含雙方棄權）一路推進到結束，檢查不變式；分支覆蓋率 ≥ 90% -- AC

**Acceptance Criteria:**
- Given 2～32 隊任一對戰表與任意結果序列（含雙方棄權），when 依序確認並套用 `advance` 的變更直到沒有可確認的場次，then 每場最後都是已確認或已取消、恰好回傳一次「賽事結束」，且冠軍是決賽勝隊。
- Given 套用變更的結果，when 檢查每一場，then 沒有一場同一方被填兩次，也沒有已確認的場次被改動。

## Implementation Notes

- 推進用佇列：從剛確認的場次出發，依序檢查它的 `next_code` 與 `loser_next_code`；被以 walkover 確認的場次再排進佇列，連鎖輪空在同一次呼叫內推完。所有判斷都在 `states` 的副本上做，不修改呼叫端傳入的資料。
- 目的場次的每一方都依 plan 的 `source_a`／`source_b` 重新推導，不看是誰觸發的：位置已有隊伍就不再填，所以重複呼叫自然不產生填位；兩方各自是「已有隊伍」「確定沒有隊伍」「還在等」三種之一，據此決定起算、輪空或等待。
- 只有 `played`、`forfeit` 有敗隊（`MatchState.loser()`）；雙方棄權、輪空、取消資格都沒有，所以被取消資格的隊伍不會進季軍賽、決賽取消資格時亞軍從缺。
- 季軍賽先檢查「任一場準決賽已確認且沒有勝隊」→ `VoidMatch`，之後才填位；準決賽有勝隊但沒有敗隊時照一般規則 walkover（FR-21）。
- `StartForfeitClock` 只在本次呼叫有填入隊伍、且填完後兩方湊齊時回傳，每場最多一次；連鎖中湊齊的場次（例如 M2 確認 → M5 輪空 → M7 湊齊）也會回傳。
- 「賽事結束」只在本次呼叫確認或取消了決賽或季軍賽（含觸發的那場）時才檢查：條件第一次成立一定發生在這種呼叫裡，所以不會漏；對其他已處理的場次重複呼叫不會再回傳。對決賽或季軍賽重複呼叫仍會再回傳，docstring 寫明 service 依賽事狀態只處理一次。
- 入口先驗證：`code` 不在 plan → `KeyError`（沿用 `BracketPlan.match`）；`states` 缺場次、`code` 未確認、任何已確認場次的 outcome 與勝隊不一致 → `ValueError`。驗證整份 `states`，不只本次會讀到的場次，讓資料錯誤盡早浮現。
- 決賽輪空時亞軍取冠軍所在那一方的來源場次（準決賽）的敗隊；該方是抽籤直接入座（3 隊的輪空）或該場沒有敗隊時從缺。
- 測試：矩陣案例的名次一律寫成字面值；性質測試（2～32 隊 × 12 個 seed，含雙方棄權與取消資格，也會落在決賽）另檢查起算集合＝本次新湊齊的場次、名次不重複、被取消資格的隊伍不在名次裡，並有一個測試確認隨機過程真的走過決賽的每種結果。

## Spec Change Log

- 第 1 輪審查（2026-10-29）：實作子代理與 Blind Hunter 都指出，決賽以「取消資格」確認時，照 spec 字面「亞軍＝決賽另一隊」會讓被取消資格的隊伍拿亞軍，與 FR-22「亞軍從缺」及準決賽取消資格不進季軍賽的規則矛盾。屬於需求缺口，使用者選「亞軍從缺」，已寫進 frozen 區塊與 I/O 矩陣，撤回程式重新實作。避免的錯誤狀態：Podium 列出被取消資格的隊伍。KEEP：佇列式推進，連鎖輪空在同一次 `advance` 內推完；目的場次每一方都依 plan 的 `source_a`／`source_b` 重新推導（不看觸發者），重複呼叫因此自然不產生填位；只有 `played`、`forfeit` 有敗隊；季軍賽先檢查「任一場準決賽沒有勝隊」再填位；「起算棄權期限」只在本次呼叫填入隊伍後湊齊兩方時回傳；`podium()` 未結束時回 None；決賽輪空而冠軍那一側沒有敗隊時亞軍從缺；2～32 隊 × 多個 seed 的隨機性質測試、模組只 import 允許的東西、對 `states` 不做修改的測試。另外帶入第 1 輪判定為 patch 的項目（見 Review Triage Log #3～#9）。

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 7 項、Edge Case Hunter 9 項、Verification Gap 1 個缺口＋1 項其他；另加實作子代理回報的 5 個疑點。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | 實作、Blind | 決賽以取消資格確認時，被取消資格的隊伍成為亞軍 | high | 與 FR-22「亞軍從缺」矛盾。intent_gap：使用者選亞軍從缺，撤回重做 |
| 2 | Blind | 名次的預期值照抄實作邏輯，抓不到規則錯誤 | medium | `_expected_runner_up` 與 `podium` 逐行相同，所以沒抓到 #1。重做時性質測試另加「同一隊不會在名次中出現兩次」，並以矩陣案例固定每條名次規則 |
| 3 | VG | 連鎖推進中湊齊兩隊的場次，沒有測試確認會收到「起算棄權期限」 | medium | 性質測試只檢查訊號出現時兩隊都在，沒檢查訊號不能少。patch：性質測試斷言每次新湊齊的場次集合＝本次 `StartForfeitClock` 集合、不重複；加矩陣案例：8 隊依序確認 M3、M4、M6、M1（雙方棄權）、M2 → 含 `StartForfeitClock("M7")` |
| 4 | Edge、Blind | 已確認場次的 outcome 與勝隊不一致時沒有檢查 | medium | `played` 卻沒有勝隊時會被當成沒有隊伍而產生輪空。patch：`played`、`forfeit`、`disqualified` 的勝隊必須是兩隊之一，`double_forfeit` 的勝隊必須為空，否則 `ValueError` |
| 5 | Edge | `states` 缺少 plan 裡的場次時拋出不明確的 `KeyError` | low | 與「不存在的場次」的 `KeyError` 混淆。patch：缺少時拋 `ValueError` |
| 6 | Blind、Edge、VG、實作 | 對決賽或季軍賽重複呼叫，會再回傳一次「賽事結束」 | low | 純函式看不到賽事狀態，無法分辨第一次與重複呼叫。patch：docstring 寫明 service 依賽事狀態只處理一次；測試固定「對決賽重複呼叫只回傳賽事結束、沒有其他變更」 |
| 7 | Blind | 沒寫第 1 輪場次由誰起算棄權期限 | low | 第 1 輪的隊伍由抽籤入座，不經 `advance`。patch：`StartForfeitClock` docstring 註明第 1 輪由抽籤時起算 |
| 8 | Blind | 季軍賽取消規則的不對稱沒有說明 | low | 準決賽沒有勝隊才取消；沒有敗隊（取消資格、輪空）則照一般規則，這是 FR-21 原文。patch：`VoidMatch`、`podium` docstring 說明並引用 FR-21、FR-22 |
| 9 | Blind | 決賽輪空時亞軍可能也在季軍賽 | low | 只有準決賽沒有勝隊才會讓決賽輪空，而這時季軍賽已取消，所以不會發生。patch：併入 #2 的「同一隊不重複」不變式 |
| 10 | Edge | 兩場準決賽都有勝隊、都沒有敗隊時，季軍賽是無勝隊確認而不是取消 | false | spec 寫季軍賽只在準決賽沒有勝隊時取消，其餘照一般規則；名次一樣是季軍從缺 |
| 11 | Edge | 更正結果（6.2）後已填入的隊伍不會被替換 | false | 6.2 在申訴期內、確認之前更正，`advance` 只在確認後呼叫；spec 明訂已確認的場次不再變更 |
| 12 | Edge | 呼叫端套用一半就失敗，重試時不會再起算棄權期限 | false | service 在同一個交易內套用整份清單，失敗會整批回滾 |
| 13 | Blind | `_final` 找不到決賽時拋 `StopIteration` | false | plan 一定有決賽（`plan()` 產生） |
| 14 | Blind | 沒測決賽已取消時的 `podium` | false | 決賽不會被取消 |
| 15 | 實作 | 決賽輪空且冠軍那一側沒有敗隊時亞軍從缺 | low | 與季軍賽從缺一致，記在 KEEP |
| 16 | 實作 | 季軍賽取消時已排入的隊伍保留在原位 | false | spec 只要求狀態、outcome 與勝隊；名次不看季軍賽隊伍 |

第 2 輪（2026-10-29，重新實作後）：Blind Hunter 9 項、Edge Case Hunter 9 項、Verification Gap 0 個缺口（另確認 mutation 可被既有測試抓到）。沒有新的需求缺口。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 17 | Edge、Blind | 一致性檢查漏掉幾種不合理的狀態 | medium | `walkover` 兩隊都在、`played` 只有一隊、`voided` 帶勝隊、非季軍賽被取消、同一隊在兩邊都能通過。patch：一併拒絕 |
| 18 | Edge、Blind | `podium()` 沒做 `advance` 的檢查，缺場次時拋 `KeyError` | low | service 會直接呼叫它來顯示名次。patch：共用同一個檢查 |
| 19 | Blind | 重試時棄權期限會遺漏 | low | 只要整份清單在同一交易內套用就不會發生。patch：docstring 寫明 |
| 20 | Blind | FR-21「兩方確定後通知兩隊隊長」沒有對應的變更 | low | 兩隊確定的時刻就是 `StartForfeitClock`。patch：docstring 寫明 |
| 21 | Blind | 季軍賽取消時已排入的隊伍去留沒有說明與測試 | low | 同 #16。patch：docstring 寫明保留，並補測試 |
| 22 | Blind、Edge | FR-22 的頂替要改已填入的位置，`advance` 做不到 | low | spec 的 Never 明訂頂替由 6.5 的 service 負責。patch：docstring 寫明 6.5 先在原位換隊再呼叫 `advance` |
| 23 | Blind | 幾個分支只靠隨機測試覆蓋 | low | patch：補季軍賽取消資格、3 隊 M1 雙方棄權、冠軍側準決賽取消資格的決賽輪空等固定案例 |
| 24 | Blind | 性質測試沒檢查季軍賽取消條件、取消資格隊伍不再被填入 | low | patch：補這兩個不變式；亞軍不另寫一份預期邏輯，避免重蹈 #2 |
| 25 | Blind | `MatchState.loser` 與模組 docstring 和程式不符、import 白名單多了 `typing` | low | patch |
| 26 | Edge | 更正結果後已填入的隊伍不會被替換 | false | 同 #11 |
| 27 | Blind | `states` 有 plan 以外的場次時直接忽略 | false | 多的資料不影響結果，service 依賽事查詢，不會混入 |

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/progression.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過

**結果（2026-10-29，第 2 輪修正後）：**
- `scripts/test.sh`：476 passed；整體覆蓋率 96%。
- `progression.py` 分支覆蓋率 99%（158 行、78 個分支；未覆蓋的一個分支是抽籤後不可能出現的「沒有來源也沒有隊伍」）。
- `scripts/lint.sh`：ruff check、ruff format、mypy 全部通過。
- Mutation 驗證：決賽取消資格時仍給亞軍 → 25 個測試失敗（第 1 次實作時 24 個）；只對直接確認那場的下一場起算棄權期限 → 31 個測試失敗。還原後 77 個全過。
