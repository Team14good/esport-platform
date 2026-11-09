---
title: 'Story 6.5（第二階段 B）：S27 待處理清單加入檢舉'
type: 'feature'
created: '2026-11-09'
status: 'done'
baseline_commit: '0a65b35fad38ad0bfda21cb9c850d5bdfe74d2ab'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-5-resolve-report.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** S27 的待處理清單只列申訴，`count_open_disputes` 的檢舉數一律 0；6.5 的 AC 要求「S27 的待處理清單把未結案的檢舉與申訴列在一起，標示類型與提出時間」，FR-31 要求依處理期限排序。

**Approach:** `count_open_disputes` 加入該賽事未結案的檢舉（計數與每一筆，含被檢舉隊名），依下方決定的處理期限與申訴一起排序；S27 的清單顯示「檢舉 · {被檢舉隊名}」、提出時間與處理期限，點選進 S33。檢舉在報名期間就能提出，S27 待處理區塊也在開放報名、報名截止時顯示。

## Boundaries & Constraints

**Always:**
- 只改 disputes（B）與 S27 的待處理區塊；檢舉資料只讀 `Report`（6.4 的資料表，不改表、不加遷移）。
- 隊名以 registration `get_team_names` 一次查多隊；場次以 competition 的公開函式查。
- 申訴的處理期限規則不變（6.2）。
- `OpenDisputeItem` 只新增欄位（例如 `team_name`）；`deadline` 改為可空並同步前端型別（重新產生 client）。
- S27 待處理區塊在賽事狀態為開放報名、報名截止、賽程已公布、進行中、已結束時顯示；申訴點選進 S32、檢舉點選進 S33。

**Never:**
- 不做處理期限倒數變色、逾期提醒（6.3）；不做對戰樹的取消資格標記（6.5 第二階段 C）。
- 不改 6.4 的檢舉提出流程與 S33 的處理流程。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 申訴與檢舉都有 | 1 筆未結案申訴、2 筆未結案檢舉 | `appeals=1`、`reports=2`，三筆依處理期限排序 | — |
| 已結案的檢舉 | 駁回或取消資格過的檢舉 | 不計入、不列出 | — |
| 只有檢舉、報名期間 | 開放報名中，1 筆未結案檢舉 | S27 顯示待處理區塊與該筆 | — |
| 別的賽事的檢舉 | 另一賽事有未結案檢舉 | 不計入 | — |
| 非主辦方 | 其他帳號 | — | 403 `TOURNAMENT_OWNER_REQUIRED`（沿用） |
| 檢舉期限：有下一場 | 被檢舉隊伍有待開打的場次 | 期限＝最早一場待開打場次的預定時間，與申訴一起依期限排序 | — |
| 檢舉期限：沒有下一場 | 還沒抽籤、已淘汰或已打完 | 沒有期限（`deadline=null`），排在所有有期限的項目之後、依提出時間；S27 該列不顯示處理期限；`earliest_deadline` 只看有期限的項目 | — |

## Decisions

- 2026-11-09（使用者）：6.5 第二階段拆成 A（`resolve_report`＋S33，#73 已合併）、B（本 spec：S27 待處理清單加入檢舉）、C（對戰樹取消資格標記）。
- 2026-11-09（使用者）：檢舉的處理期限＝被檢舉隊伍下一場（待開打）的預定開始時間；沒有下一場時沒有期限，排在有期限的項目之後、依提出時間。`OpenDisputeItem.deadline` 因此改為可空。
- 2026-11-09（使用者）：S27 計數分成兩行「待處理申訴 N 件」「待處理檢舉 N 件」；兩者都沒有時顯示「目前沒有待處理的申訴或檢舉。」。

</frozen-after-approval>

## Code Map

- `backend/app/modules/disputes/service.py:814` -- `count_open_disputes`：目前只走申訴、`reports=0`；`_handling_deadline`（申訴期限）與 `_owned_tournament` 沿用；`registration_service.get_team_names` 的用法見 :299、:754。
- `backend/app/modules/disputes/repository.py:126` -- `list_tournament_reports`（全部、未結案在前）；新增「某賽事未結案檢舉」查詢（或在 service 過濾）。
- `backend/app/modules/disputes/models.py:263` -- `OpenDisputeItem`（`kind` 已含 `report`、`match_id`／`match_code` 可空）、`OpenDisputes`。
- `backend/app/modules/competition/service.py:633` -- `list_team_matches`（依輪次，含 `status`、`scheduled_at`），找被檢舉隊伍的下一場。
- `frontend/src/features/disputes/OpenDisputesPanel.tsx` -- 目前一律連到 `appeals`、顯示 `match_code` 與期限；改依 `kind` 連到 `reports` 並顯示隊名。
- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx:226` -- `DISPUTE_STATUSES` 加入 `open`、`closed`（A 的檔案，只改這個集合，PR 說明列出）。
- `backend/tests/disputes/`、`frontend/tests/unit/organizer-appeals.test.tsx` -- 既有 `open-disputes` 測試與 S27 面板測試的寫法。

## Tasks & Acceptance

**Execution:**
- [x] `disputes/{repository,service,models}.py` -- 加入未結案檢舉、處理期限、隊名
- [x] `backend/tests/disputes/test_open_disputes_reports.py` -- 覆蓋 I/O 矩陣與檢舉期限規則（含沒有期限時的排序）
- [x] `frontend/src/client/` -- 若 schema 有變，重新產生
- [x] `OpenDisputesPanel.tsx`、`OrganizerTournamentOverview.tsx` -- 檢舉列、連結、顯示狀態
- [x] `frontend/tests/unit/` -- S27 混合清單、檢舉連到 S33、報名期間顯示
- [x] `deferred-work.md`、`sprint-status.yaml` -- 刪除已處理的兩個 S27 檢舉項目（spec-6-2 的與「6.5 第二階段（B）」）；6-5 註記更新

**Acceptance Criteria:**
- Given 一筆申訴與一筆檢舉都未結案，when 主辦方開啟 S27，then 兩筆列在一起、分別標示「申訴」「檢舉」與提出時間，點選分別進 S32、S33。

## Implementation Notes

- 2026-11-09（實作）：「待開打」取場次狀態 `scheduled`；進行中、申訴期、申訴中的場次不算下一場（例如第 1 輪申訴中的勝隊，第 2 輪還沒排入，沒有期限）。同一隊的多筆檢舉共用同一次查詢結果。
- `OpenDisputeItem.team_name` 預設 None：檢舉為被檢舉隊名，申訴維持 None（S27 申訴列照舊顯示場次代碼）。產生的前端型別為 `team_name?: string | null`。
- S27 計數改成兩行「待處理申訴 N 件」「待處理檢舉 N 件」；兩者都沒有時的空狀態由「目前沒有待處理的申訴。」改為「目前沒有待處理的申訴或檢舉。」（`NO_OPEN_DISPUTES_TEXT`）。此文字 spec 沒有規定，使用者已確認（見 Decisions）。
- 前端 `sortOpenItems` 與後端排序一致：沒有期限視為無限遠，再依提出時間。
- `contracts/disputes.md` 的 `count_open_disputes` 列同步改寫為本 spec 的期限與排序規則。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-09，Blind Hunter、Edge Case Hunter、Verification Gap；VG 沒有發現缺口）：

| # | 來源 | 發現 | 判定 | 處置 |
|---|---|---|---|---|
| 1 | ECH、BH | 已取消的賽事 S27 不顯示未結案檢舉 | false：取消賽事（2.6）期中未實作，沒有途徑讓賽事變成已取消 | 不處理 |
| 2 | BH | 沒有測試斷言 `upcoming` 等狀態不顯示待處理區塊 | low：區塊顯示範圍改壞時測試不會失敗；補一個參數化測試即可 | patch |
| 3 | BH | 同期限、同提出時間的兩筆排序不固定（`_open_item_order`、`sortOpenItems` 沒有 id）；排序鍵重複放 `filed_at` 當佔位 | low：畫面順序可能每次不同；直接加 id、改清楚的排序鍵 | patch |
| 4 | BH | 檢舉隊名的「未知隊伍」後備文字 spec 沒寫 | low：被檢舉隊伍有外鍵、碰不到；與 6.2 申訴的寫法一致 | 不處理 |
| 5 | BH | 空狀態文字與計數分兩行是 spec 沒規定的介面文字 | 需使用者確認的介面文字 | 請使用者確認 |
| 6 | BH | 沒有已結束賽事的檢舉測試 | low：已結束時沒有待開打場次，自然為 null | 不處理 |
| 7 | BH | `contracts/competition.md` 的 `list_team_matches` 用途沒補 S27 | low：約定少記一個呼叫者 | patch |
| 8 | BH | `contracts/disputes.md` 的 `count_open_disputes` 只標 6.2 | low：直接加註 6.5 | patch |
| 9 | BH | spec 的 Verification 寫了本機暫存路徑 | low：修法是改 spec | 不處理 |
| 10 | BH | Code Map 的行號會過期 | low：修法是改 spec | 不處理 |
| 11 | BH | 測試註解依賴第 2 輪尚未排入的實作細節 | low：要加前置斷言，日常不會遇到 | 不處理 |
| 12 | BH | 每個被檢舉隊伍各查一次場次 | low：檢舉很少 | 不處理 |
| 13 | BH | 舊測試的名稱與說明仍寫「檢舉為 0」 | low：測試仍正確，只是描述舊 | 不處理 |

## Verification

本工作樹與其他工作樹的容器同時在跑，compose 指令都加 `-p espory-6-5b -f compose.yml -f "C:/Users/grace/AppData/Local/Temp/claude/4f4394f69a1cf9f9/1fabc1f3-312d-4d81-a1f5-4b734a9929d3/scratchpad/ports-6-5b.yml"`（以下簡寫 `dc`）；不要停止或重建其他專案的容器。

**Commands:**
- `dc up -d --build --wait db backend mailpit` 後 `dc exec backend bash scripts/test.sh` -- expected: 全部通過、覆蓋率門檻通過
- `dc exec backend bash scripts/lint.sh` -- expected: mypy、ty、ruff 通過
- 前端 build、typecheck、biome、單元測試（README〈測試與檢查〉）-- expected: 全部通過
