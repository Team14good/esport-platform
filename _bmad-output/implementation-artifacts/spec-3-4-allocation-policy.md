---
title: 'Story 3.4（第一階段）：名額分配規則 AllocationPolicy'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: 'ce4482e019d6185a4120cd2f8f8024fd01cff3cc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 校園賽的名額分配（優先期代表隊、先搶期、截止補位、候補順位）是本專案最核心的業務規則，但 Registration 資料表在 3.1（未合併）、賽事在 2.2（未合併），worker、資料庫、事件與畫面都還不能做。

**Approach:** 比照 D 的 4.1、5.x 第一階段，先在 registration 寫不碰資料庫的純函式 `AllocationPolicy`：輸入報名快照（id、學校、平均段位積分、送出時間、狀態），輸出正取／候補判定與候補順位。第二階段（另一份 spec，3.1、2.2 合併後）接上 worker 工作、鎖定、`mark_status`、操作紀錄、事件與 S17／S12 顯示。

## Decisions（2026-11-01，邱芯彤）

- 本階段一次做完校園賽的 `AllocationPolicy`：優先期結算（3.4）、先搶期送出判定 `decide_first_come`（3.5）、截止補位 `fill_from_waitlist`（3.6）與兩個階段的 `waitlist_order`；3.5、3.6 的第二階段只剩接資料庫與 worker。sprint-status 上 3.5、3.6 維持 backlog。
- spec 篇幅約 2,700 tokens，超過 1600，保留完整 spec，不拆分。
- story/3-4 從 `main` 開出，與 story/3-1、story/3-2 獨立。

## Boundaries & Constraints

**Always:**
- 排序鍵只有一套（FR-14）：平均段位積分高者優先 → 送出時間早者優先 → 報名 id 小者優先。所有依積分排序的規則共用它。
- 優先期結算（FR-14）：只看結算當下為「已送出・待分配」的報名；每校取排序最前的一隊為代表隊；代表隊依排序取前「名額」隊正取，其餘代表隊與所有非代表隊列候補。
- 候補順位依階段（FR-17）：
  - 先搶期：只有「優先期沒有報名、目前也沒有正取」的學校有資格；每個有資格的學校只有最早送出的一隊有順位，依送出時間（同時再依 id）排序。
  - 報名截止後（含抽籤後）：所有候補依排序鍵排入；排入後會使該校正取超過 2 隊的略過。
- 沒有順位的候補要回傳原因代碼，對應 EXPERIENCE.md〈固定介面字串〉的三則原因；先搶期內本校優先期代表隊為正取時，另帶「代表隊退出時由同校遞補」的補充旗標。
- 截止補位（FR-16）＝報名截止後階段的順位前 N 名，不另寫一套排序。
- 結果只由輸入決定：同樣輸入重複呼叫結果相同，與輸入順序無關。

**Never:**
- 不碰資料庫、不讀時鐘、不 import 其他模組（只用標準函式庫與同模組的 `registration.models`）。
- 這一階段不做資料表、遷移、worker、API、事件、操作紀錄與畫面，不改 registration 既有四個檔（避免與 #23 衝突）。
- 不做自訂模式（3.10 擱置）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 40 校搶 32 名 | 40 校各 1 隊待分配，名額 32 | 正取 32、候補 8；正取為排序前 32 隊 | N/A |
| 同校 3 隊 | 同校 3 隊待分配，名額足夠 | 只有積分最高的 1 隊正取，另 2 隊候補 | N/A |
| 同分 | 兩隊積分相同 | 先送出者優先；送出時間也相同時 id 小者優先 | N/A |
| 名額為 0 或沒有報名 | — | 全部候補／空結果 | N/A |
| 先搶期送出 | 該校優先期沒有報名、目前沒有正取，名額未滿 | 正取 | N/A |
| 先搶期送出被列候補 | 該校優先期有報名；或同校已有正取；或名額已滿 | 候補 | N/A |
| 先搶期順位 | 候補中有優先期有報名的學校、無報名的學校各數隊 | 只有無報名且目前無正取學校中最早送出的一隊有順位，依送出先後編號；其餘無順位並附原因 | N/A |
| 截止後順位 | 某校已有 1 隊正取、另有 2 隊候補 | 該校候補中排序較前的一隊有順位，另一隊無順位（每校最多 2 隊） | N/A |
| 截止補位 | 剩餘名額 N | 回傳截止後順位前 N 名；不足 N 名就全回傳 | N/A |
| 輸入不合法 | 名額或剩餘名額為負、報名 id 重複 | 不產生結果 | 拋 `ValueError`（第二階段 service 不會傳入，屬程式錯誤） |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/progression.py`、`bracket.py` -- D 的第一階段純函式寫法參考：frozen dataclass 輸入輸出、模組 docstring 說明規則來源、`ValueError` 擋程式錯誤
- `backend/tests/competition/test_progression.py` -- 純函式單元測試寫法參考（不需資料庫）
- `backend/app/modules/registration/models.py` -- 已有 `RegistrationStatus`（`pending`、`accepted`、`waitlisted`…）；本模組 import 它當狀態型別（同模組內，不算跨模組）
- `backend/tests/registration/` -- main 上還沒有這個資料夾；3.1、3.2 分支各自新增空的 `__init__.py`，內容相同，合併時不會衝突
- `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:200-204` -- 候補無順位的三則原因與一則補充（原因代碼要能一對一對應）
- `_bmad-output/planning-artifacts/epics.md` FR-14～FR-17 -- 規則原文

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/allocation.py` -- 新檔：輸入快照 `Candidate`（id: UUID、school_id: UUID、avg_rank_score: Decimal、submitted_at: datetime、status）；`sort_key`；`allocate_priority_window(candidates, *, capacity)`；`waitlist_order(candidates, *, phase, priority_schools)` 回傳每個候補的順位或原因（含補充旗標）；`fill_from_waitlist(candidates, *, remaining)`；`decide_first_come(candidate, *, candidates, priority_schools, capacity)`（FR-15：優先期沒有報名、目前也沒有正取的學校，且名額未滿時正取，否則候補）
- [x] `backend/tests/registration/__init__.py`、`backend/tests/registration/test_allocation.py` -- I/O 矩陣每一列、與輸入順序無關、先搶期一校多隊候補、截止後每校上限含既有正取、補充旗標
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 新增第二階段待辦

**Acceptance Criteria:**
- Given 任何合法輸入，when 打亂輸入順序再呼叫，then 結果相同。
- Given `allocation.py`，when 以分支覆蓋率執行本模組測試，then 分支覆蓋率至少 90%（epic context 規定）。

## Implementation Notes

- 實作子代理自訂的解讀（spec 未寫明）：
  - 每校正取數把 `drawn`（已參賽）也算正取（FR-17「含抽籤後」）。
  - 先搶期的 `representative_backfill`＝學校在 `priority_schools` 且目前有正取。
  - 某校之前有隊伍因額滿列候補、目前沒有正取時，同校新送出的隊伍仍可在先搶期正取（FR-15 只限制「同校已有正取」）。
  - `waitlist_order` 在截止後階段忽略 `priority_schools`。
- 驗證：後端 761 個測試通過；`allocation.py` 分支覆蓋率 100%（98 statements、22 branches）；mypy、ty、ruff 通過。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-01；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V1 | `decide_first_come` 略過候選者本身沒有測試 | medium | 既有測試的候選者是 `pending`，本來就不計入正取；刪掉或反轉過濾條件測試仍通過 | patch |
| E1、B6 | 有空位時新送出的隊伍會插到有順位的候補前面 | low | 名額只在撤回、退回、提高名額時釋出（期中皆不做），第二階段在同一鎖內先遞補就不會發生；補 docstring 寫明呼叫端責任 | patch |
| B10 | 優先期結算重跑時回傳空結果，語意未說明 | low | 結算後已無 `pending`；第二階段可能誤用；補 docstring 一句 | patch |
| B8 | 介面字串測試只比對開頭 | low | 「一對一對應 EXPERIENCE.md」沒被驗證；改成比對全文 | patch |
| B4、E7 | deferred 沒寫明 `fill_at_deadline` 與 11/12 交接；截止補位前須先完成優先期結算 | medium | epic-3／4 context 約定 D 的 4.1 會呼叫；`fill_from_waitlist` 只看 `waitlisted`，若有殘留 `pending` 會被漏掉 | patch |
| B5 | sprint-status 3-4 註解沒照組內寫法，3-5、3-6 沒標註規則已完成 | low | D 的 4-1、5-x 都有註明第一階段範圍 | patch |
| B2 | 代表隊退出時「同校次高者遞補」的對象沒有函式 | medium | FR-17 規則；只在撤回、退回（3.7、3.8 擱置）時觸發，本階段 intent 只含判定與順位 | defer |
| V2 | 分支覆蓋率 90% 只靠 spec 的手動指令，`scripts/test.sh` 沒有 `--branch` | low | 改覆蓋率設定影響全 repo，屬既有設定 | defer |
| B1 | spec 不在 diff 中 | false | 審查流程刻意排除，spec 只交給 Edge Case Hunter | reject |
| B3 | 沒有依賽事模式分支 | false | 自訂模式（3.10）擱置，spec Never 已排除 | reject |
| B7、E2 | `decide_first_come` 不檢查候選者狀態 | low | 第二階段只在送出當下傳入剛送出的報名；加防呆屬新增分支 | reject |
| B9 | 沒有分支覆蓋率證據、有分支沒測到 | false | 實測分支覆蓋率 100%（22 branches 全覆蓋） | reject |
| B11 | 無法發現混入其他賽事的報名 | low | 呼叫端依賽事查詢；加欄位與檢查屬新增介面 | reject |
| E3 | 部分結算後重跑會超收 | false | 優先期結算在同一鎖與交易內一次完成，不存在部分結算的狀態 | reject |
| E4 | 不合法的 phase 會落到截止後規則 | low | 參數型別是 `AllocationPhase`，mypy 會擋 | reject |
| E5 | `submitted_at` 混用 naive 與 aware 時排序出錯 | low | 第二階段來自 `timestamptz`，一律帶時區 | reject |
| E6 | 平均積分為 NaN 時排序出錯 | low | 平均由本系統以整數積分計算，不會產生 NaN | reject |

## Design Notes

原因代碼與介面字串（第二階段前端顯示用）：
- `SCHOOL_NOT_ELIGIBLE`：「先搶期只遞補優先期沒有報名、目前也沒有正取的學校；報名截止後改依平均段位積分排序。」
- `LATER_THAN_SCHOOLMATE`：「先搶期每校只遞補最早送出的一隊，本校已有更早送出的候補。」
- `SCHOOL_LIMIT_REACHED`：「每校最多 2 隊正取：本校正取加上排在前面的本校候補已達 2 隊。」
- 補充旗標 `representative_backfill`：「本校代表隊退出時，由本校平均段位積分次高的隊伍遞補。」

「優先期有報名的學校」由呼叫端傳入（優先期結算時為待分配的學校集合）；期中沒有撤回、退回，第二階段直接以優先期結算的輸入學校計算並保存。報名 id 是 UUID，Python 比較 `uuid.UUID` 的順序與 PostgreSQL `uuid` 排序一致（皆依 128 位元大小）。

第二階段（記入 deferred-work）：worker 工作在優先期結束後 1 分鐘內鎖賽事、取待分配報名、呼叫本模組、以 `mark_status` 改狀態、寫操作紀錄（system）、發事件；S17／S12 顯示「正取」「候補第 N 位」或「候補・目前不在遞補順序中」＋原因；以 `frozen_clock` 推進時間測試、重複執行結果不變。

## Verification

**Commands:**
- `docker compose run --rm --no-deps -T backend bash -c "bash scripts/test.sh"` -- 全綠
- `docker compose run --rm --no-deps -T backend bash -c "coverage run --branch -m pytest tests/registration/test_allocation.py && coverage report --include=app/modules/registration/allocation.py"` -- 分支覆蓋率 ≥ 90%
- `docker compose run --rm --no-deps -T backend bash scripts/lint.sh` -- 通過
