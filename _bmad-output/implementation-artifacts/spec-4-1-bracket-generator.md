---
title: 'Story 4.1（第一階段）：對戰表產生器 BracketGenerator'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: 'cb3c91550d20f7c72dfdbe2cd41271a8aebe27d0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.1 抽籤要產生含輪空與季軍賽的單淘汰對戰表，但 B 的 2.2（Tournament）與 C 的 3.x（正取隊伍）還沒完成，資料表、抽籤 API 與 S27 畫面都還不能做；同時 A 的 4.6 對戰樹需要場次編號、輪次名與待定列字串。

**Approach:** 先在 competition 寫不碰資料庫的純函式：`plan(team_count)` 算結構，`assign(team_ids, plan, rng)` 以注入的亂數排定對位，再加上輪次名、場次編號、待定來源字串。第二階段（另一份 spec）接上 Bracket／Match 資料表、`draw()`、抽籤 API 與 S27。

## Boundaries & Constraints

**Always:**
- P＝不小於隊數的最小 2 的次方；輪數＝log₂P；輪空數＝P－隊數；輪空隊伍直接出現在第二輪，第一輪不建輪空場次。
- 結構只由隊數決定：同樣隊數重複產生，輪數、場次、輪空位置都相同，只有隊伍對位不同。
- 輪空平均分散：輪空數不超過 P÷4 時，每支輪空隊伍在第二輪的對手都是第一輪的勝隊；超過時，相遇的兩支輪空隊伍在抽籤時就確定。
- 正取 4 隊以上才有季軍賽（準決賽兩場的敗隊）；場次總數＝隊數－1，有季軍賽再加 1。
- 場次編號 M1…依輪次、同輪由上到下，只編實際存在的場次；季軍賽編在最後。
- 亂數由呼叫端傳入（正式環境 `secrets.SystemRandom()`），模組內不建立亂數來源。
- 介面字串照 EXPERIENCE.md：輪次名「16 強」「8 強」「4 強」「決賽」；待定列「M4 勝者」，季軍賽「M29 敗者」。

**Never:**
- 不碰資料庫、不 import 其他模組、不讀時鐘。
- 這一階段不做資料表、遷移、API、事件、操作紀錄與畫面。
- 隊數少於 2 不產生對戰表（拋 `ValueError`，由第二階段的 service 轉成業務錯誤）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 8 隊 | `plan(8)` | P=8、3 輪、0 輪空、8 場（含季軍賽） | N/A |
| 13 隊 | `plan(13)` | P=16、4 輪、3 輪空、13 場；3 支輪空隊伍在第二輪都對上第一輪勝隊 | N/A |
| 10 隊（輪空多於 P÷4） | `plan(10)` | 6 輪空；有第二輪場次在抽籤時就兩隊確定 | N/A |
| 3 隊 | `plan(3)` | 2 輪、1 輪空、2 場、沒有季軍賽 | N/A |
| 2 隊 | `plan(2)` | 1 輪（決賽）、1 場 | N/A |
| 32 隊 | `plan(32)` | 5 輪、32 場、季軍賽為 M32 | N/A |
| 少於 2 隊 | `plan(1)`、`plan(0)` | — | `ValueError` |
| 隊伍數與 plan 不符 | `assign(5 隊, plan(8), rng)` | — | `ValueError` |
| 隊伍重複 | `assign` 有重複的隊伍 id | — | `ValueError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/bracket.py` -- 新檔：純函式與不可變資料結構。competition 內的其他檔案與 4.6 的 schema 組裝會用它
- `backend/app/modules/competition/models.py` -- 已有 `MatchStatus`、`MatchOutcome`；本階段不改
- `backend/app/modules/identity/service.py:111` -- 既有用 `secrets` 的寫法參考；本模組只接收 rng，不自己建
- `backend/tests/test_module_structure.py` -- 只要求四個 layer 檔存在；新增 `bracket.py` 不違反
- `backend/tests/core/test_clock.py` -- 純函式測試的寫法參考（不需要 db fixture）
- `backend/pyproject.toml:72` -- coverage 沒開 branch；本模組的 90% 分支覆蓋率另外用指令檢查，不改全域設定
- `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:178,413` -- 待定列字串、場次編號規則

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/bracket.py` -- 新增 `BracketPlan`、`PlannedMatch`（frozen dataclass）、`plan()`、`assign()`、`round_name()`、`source_label()` -- 結構與對位分離，結構可預先驗證
- [x] `backend/tests/competition/__init__.py`、`backend/tests/competition/test_bracket.py` -- I/O 矩陣每一列；2～32 隊每一種的場次數、輪空數、編號連續、`next` 指向正確；固定種子的 `random.Random` 驗證對位會變、結構不變；輪空分散的兩條規則逐一檢查 2～64 隊 -- AC 與 90% 分支覆蓋率

**Acceptance Criteria:**
- Given 2～64 之間任一隊數，when 呼叫 `plan`，then 場次數＝隊數－1（4 隊以上再加 1）、每支隊伍恰好出現一次（第一輪或第二輪）、除決賽與季軍賽外每場都有下一場。
- Given 同一個 plan 與兩個不同種子的 rng，when 呼叫 `assign`，then 結構相同而對位不同；相同種子結果相同。
- Given 每一場，when 呼叫 `source_label`，then 待定方顯示來源場次的編號與「勝者」或「敗者」，第一輪與輪空直接入座的一方沒有待定字串。

## Implementation Notes

- 實作子代理自訂：輪空對裡隊伍坐上方座位；洗牌後先排第一輪、再依 plan 順序排輪空隊伍（spec 未規定，結果只取決於洗牌）。
- 新增 `AssignedMatch`、`MatchSource` 兩個 frozen dataclass，`PlannedMatch` 以 `bye_a`／`bye_b` 標示輪空直接入座的一方。
- 介面約定（PR #3）同步改用 `bye_side` 與「4 強」；2026-10-31 使用者決定改為 `bye_a`／`bye_b`，確定不會有隊伍時 `source_*` 為 null（見 spec-4-1-draw-backend 的 Spec Change Log）。
- spec 初稿漏了本節、Spec Change Log 與 Review Triage Log 三個範本區段，審查時補回。
- 驗證（2026-10-29，審查修正後）：`scripts/test.sh` 全部 399 個測試通過；`bracket.py` 分支覆蓋率 100%（48 個分支）；`scripts/lint.sh` 通過。
- 突變測試：把 `_bit_reverse_order(quarter)` 換成 `list(range(quarter))` → 39 個測試失敗（含 `test_14_bye_pairs_exact`）；把季軍賽 `source_b` 改成 `semis[0]` → 62 個測試失敗。兩者在審查修正前都不會失敗。
- sprint 狀態維持 `in-progress`（不照 step-05 改成 `review`）：本 spec 只是 4.1 第一階段，資料表、`draw()`、抽籤 API 與 S27 留給第二階段 spec（見 Review Triage Log #8）。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-29）：Blind Hunter 10 項、Edge Case Hunter 4 項、Verification Gap 2 項。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | VG、Blind | 輪空分散順序沒有測試釘住 | medium | 13、10 隊在依序與位元反轉兩種順序下結果相同；14 隊可分辨（依序會兩個輪空都在上半區）。patch：加 14 隊精確位置與上下半區平衡斷言 |
| 2 | VG | 季軍賽 `source_b` 沒有斷言 | low | 測試只檢查 side a，改錯來源不會失敗。patch：補斷言 |
| 3 | Edge、Blind | 季軍賽用 `round_name` 會得到「決賽」 | low | 季軍賽與決賽同 round_no；UX 規定季軍賽一律顯示「季軍賽」，4.6 有誤用風險。patch：docstring 註明 |
| 4 | Blind | `source_label` docstring 說「已確定」回 None | low | 函式只看靜態 plan，看不到結果。patch：改 docstring |
| 5 | Blind | 同輪由上到下沒有檢查 | low | 測試只檢查編號連續與輪次遞增。patch：補 slot_no 遞增斷言 |
| 6 | Blind | 「沒有亂數來源」測試太弱 | low | 只查屬性名稱，`from random import shuffle` 也會通過。patch：改用 ast 檢查 import |
| 7 | Blind | 測試以真假值判斷隊伍 id | low | `assign` 對任何 Hashable 泛型，id 為 0 時測試誤判。patch：改 `is not None` |
| 8 | Blind | sprint 狀態沒標第一階段 | medium | 4.1 只完成第一階段，改成 review 會誤導組員。step-05 處理：sprint 維持 in-progress 並加註 |
| 9 | Blind | 分支覆蓋率沒有證據 | false | Verification 指令會重跑並記錄；`bits else 0` 由 3 隊（P=4）覆蓋 |
| 10 | Edge、Blind | 非整數隊數 | false | 參數有型別標註，mypy／ty 會擋；第二階段以 `len()` 傳入 |
| 11 | Edge | 沒有隊數上限 | low | 名額由 2.2 建立賽事時限制；不常見且修正要加防護，reject |
| 12 | Edge | 手動組出不一致的 plan 會拋 StopIteration | false | plan 只由 `plan()` 產生；不可能的狀態大聲失敗是正確行為 |
| 13 | Blind | `BracketPlan.match()` 線性搜尋 | low | n ≤ 64 影響可忽略，修正要加快取，reject |

## Design Notes

座位模型：P 個座位兩兩成對（第 k 對＝座位 2k、2k+1）；第二輪第 j 場由第 2j、2j+1 對的勝者組成。輪空對＝只有一個座位有隊伍的對。

選輪空對：把第二輪場次 0…Q－1（Q＝P÷4）依位元反轉排序，讓輪空交替落在上、下半區。先在每場的上方對各放一個輪空，放完 Q 個還有剩，再依同樣順序放在下方對（此時兩支輪空隊伍在第二輪相遇）。

```text
13 隊：P=16、Q=4、順序 [0,2,1,3] → 輪空對 0、4、2
第一輪場次＝第 1、3、5、6、7 對（5 場）；第二輪 j0＝輪空 vs 第 1 對勝者 …
```

`slot_no`＝該輪的位置＋1（第一輪輪空的位置留空號）；編號 M 只算實際存在的場次。

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh tests/competition` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/bracket.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過
