---
title: 'Story 5.2（第一階段）：逾時判棄權的規則'
type: 'feature'
created: '2026-10-30'
status: 'done'
baseline_commit: '7414d3b9abd2be5aa8c64c187615a11448ad9f0b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 5.2 要讓 worker 在棄權期限過後，自動判未報到的隊伍棄權，並讓場次直接進入申訴期。但 Match 資料表、`lock_match`、`list_forfeit_due`、`list_check_ins`（D 的 4.1、5.1）都還沒合併，worker 工作與資料寫入現在還做不了。

**Approach:** 比照 D 的 5.x，第一階段先在 competition 寫不碰資料庫的純函式：判斷某場次現在該不該判棄權、判成什麼結果，以及申訴期截止時間的算法。第二階段的 worker 工作鎖住場次後，用同一個函式重新檢查並寫入結果。

## Boundaries & Constraints

**Always:**
- `judge_forfeit` 依下列順序判斷，回傳 None 表示「不判棄權」：
  1. 賽事已取消
  2. 場次不是「待開打」（`MatchStatus.SCHEDULED`）
  3. 兩隊有任一隊未確定
  4. 現在早於棄權期限
  5. 兩隊都已報到
- 剛好等於棄權期限就判棄權。這和 5.1 一致：剛好等於期限就不能報到。
- 只有一隊報到時，結果是 `outcome = forfeit`：已報到的隊伍獲勝，未報到的隊伍列為棄權。
- 兩隊都沒報到時，結果是 `outcome = double_forfeit`：沒有勝隊，兩隊都列為棄權（順序 a、b）。
- 申訴期截止時間＝判定時間＋申訴時限（分鐘）。依 FR-30，申訴期從判棄權時起算；判定時間由呼叫端傳入，第二階段就是 worker 執行時的「現在」。
- 所有 datetime 都必須帶時區，沒有時區拋 `ValueError`；回傳的時間一律是 UTC。
- 不讀時鐘：「現在」由呼叫端傳入。
- 隊伍型別用泛型 `T: Hashable`，和 D 的 `progression.py` 相同，讓第二階段直接傳 UUID。

**Never:**
- 不碰資料庫，不發事件，不寫操作紀錄。
- 除了 `app.modules.competition.models`（列舉），不 import 其他模組。
- 不修改 D 既有的檔案（epic context：5.2 只新增檔案）。
- 不做 worker 工作、通知事件、S4 畫面。這些放第二階段。

**Decisions（使用者 2026-10-30 要求全部採用推薦，不另行詢問）:**
- 只做第一階段（純規則＋測試）。第二階段等 D 的 4.1、5.1 合併後再做，範圍寫在 `deferred-work.md`。
- 申訴期從判定時間起算，不從棄權期限起算，所以 worker 延遲時兩隊仍有完整的申訴期。
- 兩隊已確定卻沒有棄權期限，或報到名單裡有不屬於這場的隊伍，或兩隊是同一隊，都視為呼叫端錯誤，拋 `ValueError`。
- 不做 code review（沿用使用者「最後統一 review」的決定）。
- spec 略超過 1600 tokens 時保留完整內容；checkpoint 不停下來，直接核准並繼續實作。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 一隊報到 | 期限 13:15、現在 13:16、待開打、只有 a 報到 | `forfeit`，勝隊 a，棄權 (b,) | N/A |
| 兩隊未報到 | 同上、無人報到 | `double_forfeit`，勝隊 None，棄權 (a, b) | N/A |
| 剛好在期限 | 現在 13:15、只有 b 報到 | `forfeit`，勝隊 b | N/A |
| 期限前 | 現在 13:14 | None | N/A |
| 兩隊都報到 | 過期限、a、b 都報到 | None | N/A |
| 兩隊未確定 | team_b 為 None、期限 None、已過預定＋時限 | None | N/A |
| 已取消賽事 | 賽事已取消、其他條件都符合 | None（優先於其他條件） | N/A |
| 非待開打 | 狀態為申訴期、進行中等 | None（重複執行沒有副作用） | N/A |
| 缺棄權期限 | 兩隊確定、期限 None | — | `ValueError` |
| 名單有外隊 | 報到名單含 c | — | `ValueError` |
| 同一隊 | team_a == team_b | — | `ValueError` |
| 申訴期截止 | 判定 13:16、時限 60 | 14:16 UTC | N/A |
| 時限不合法 | 時限 0、負數或非整數 | — | `ValueError` |
| 沒有時區 | 任一 datetime 為 naive | — | `ValueError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/forfeit.py`：新檔，放純函式。第二階段的 worker 工作鎖住場次後呼叫它。
- `backend/app/modules/competition/models.py`：只使用既有的 `MatchStatus`、`MatchOutcome`，不修改。
- `origin/story/5-1:backend/app/modules/competition/checkin.py`：D 的寫法，可參考 `_to_utc`、模組 docstring 與 `ValueError` 的訊息風格。本檔不 import 它，因為它還沒合併。
- `origin/story/5-5:backend/app/modules/competition/progression.py`：泛型 `[T: Hashable]` 與 frozen dataclass 的寫法。它的 `MatchState.loser()` 對 `forfeit` 取「非勝隊」，和本檔的結果一致。
- `backend/tests/competition/`：目前不存在，要新增 `__init__.py`。D 的分支也新增了同一個空檔，合併時不會衝突。
- `_bmad-output/implementation-artifacts/deferred-work.md`：新增一項第二階段的範圍（只新增項目，不改既有項目）。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/forfeit.py`：新增以下內容，讓第二階段的 worker、測試與日後的手動重判共用同一套規則。
  - frozen dataclass `ForfeitVerdict[T]`，欄位為 `outcome`、`winner`、`forfeited: tuple[T, ...]`
  - `judge_forfeit(*, now, tournament_cancelled, status, team_a, team_b, forfeit_deadline, checked_in) -> ForfeitVerdict[T] | None`
  - `appeal_deadline(*, decided_at, appeal_minutes) -> datetime`
- [x] `backend/tests/competition/__init__.py`、`backend/tests/competition/test_forfeit.py`：測試以下項目，作為 AC 的驗證。
  - I/O 矩陣的每一列，以及期限前後各一秒的邊界
  - 固定種子的隨機輸入，依 spec 的順序算出預期結果後比對
  - AST 檢查：只 import 允許的模組，不呼叫 `now`／`utcnow`／`today`
  - 分支覆蓋率 ≥ 90%
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`：新增一項第二階段範圍。內容包括：
  - worker 工作：用 `list_forfeit_due` 選場次，`lock_match` 後重新呼叫 `judge_forfeit`，寫入 outcome、勝隊、wins 與 `appeal_deadline`，再用 `transition_match` 轉為申訴期
  - 操作紀錄記 system；發出判棄權事件
  - S4 顯示哪一隊棄權與申訴期倒數
  - 確認 D 的轉換表允許「待開打 → 申訴期」

**Acceptance Criteria:**
- Given 任一組帶時區的合法輸入，when 呼叫 `judge_forfeit`，then 只有在以下條件全部成立時才回傳結果：賽事未取消、場次待開打、兩隊確定、現在 ≥ 期限、至少一隊未報到。
- Given 回傳 `forfeit` 的結果，when 檢查欄位，then 勝隊必定已報到，`forfeited` 只含另一隊。
- Given 同一組輸入，when 重複呼叫，then 結果相同。

## Implementation Notes

- 呼叫端錯誤先檢查，再判斷五個「不判棄權」的條件。這些錯誤包括：沒有時區、兩隊是同一隊、名單有外隊、兩隊確定卻沒有期限。所以賽事已取消時，不合法的資料仍會拋 `ValueError`，不會被默默略過；這個先後順序和 D 的 `checkin.py` 相同。I/O 矩陣「已取消賽事優先於其他條件」指的是這五個條件。第二階段的 worker 只會選到有期限的場次，正常情況下不會遇到這些錯誤。
- `_to_utc` 照 D 的 `checkin.py` 另外寫了一份私有版本。`checkin.py` 還沒合併，所以沒有 import 它。
- `appeal_deadline` 也擋掉 bool 和浮點數。它是通用的算法，5.4 送出系列結果時也可以直接用。
- `sprint-status.yaml` 的 5-2 維持 `in-progress`，第二階段做完才改成 `review`，和 4.6 第一階段的做法相同。依使用者的決定，本次沒有跑 step-04 code review。
- 驗證結果（2026-10-30，重建 backend image 後重跑）：
  - `scripts/test.sh` 291 passed，其中新增 38 個
  - `forfeit.py` 分支覆蓋率 100%（42 行、24 個分支）
  - `scripts/lint.sh` 通過；`tests/competition` 的 ruff check 與 ruff format 也通過
  - 新增與修改的檔案都是 LF
- 開發環境：開發資料庫已被 `story/1-7` 的遷移 `c7e2a4d9b8f1` 升級過，`story/5-2` 沒有這支遷移，所以在這個分支上啟動 backend 和 worker 時，prestart 的 `alembic upgrade head` 會失敗。測試用的是獨立的 `_test` 資料庫，不受影響。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash -c "coverage run --branch -m pytest tests/competition -q && coverage report --include='app/modules/competition/forfeit.py' --fail-under=90"` -- expected: 分支覆蓋率 ≥ 90%
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過
