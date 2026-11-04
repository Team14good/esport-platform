---
title: '6.2 前置：重新比賽時清除報到紀錄與逐局比分的公開函式（D 提供給 B）'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: '5d17b5902e99031411adacc20f810a1aead720bc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-3-referee-score-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 6.2「重新比賽」（B 負責）要讓判棄權後被申訴的場次回到待開打、清除結果與報到紀錄，依新時間重新報到。報到紀錄（`check_in`）與逐局比分（`match_game`）是 D 在 5.1、5.3 建的資料表；不清乾淨的話，重賽會回 `ALREADY_CHECKED_IN`、判棄權 worker 選不到它、第一局被當成覆寫。5.1 與 5.3 的審查都把這件事記入 deferred-work，要 D 提供公開函式。

**Approach:** 在 competition `service.py` 新增一個公開函式，只負責「清資料」：刪掉該場的報到紀錄與逐局比分，把結果相關欄位歸零，回傳清除前的內容供 B 寫操作紀錄。狀態轉換、新時間、棄權期限與通知仍由 B 的 `replay_match` 處理（約定文件：`replay_match` 由 B 寫在 competition 新增的檔案，D 審查）。

## Boundaries & Constraints

**Always:**
- 函式：`clear_for_replay(session, *, match: Match) -> ReplayCleared`。呼叫端必須先依 AD-6 `lock_tournament`、`lock_match` 取得 `match`。
- 只接受「申訴中」（`appealed`）的場次；其他狀態拋 409 `MATCH_INVALID_TRANSITION`，不改任何資料。
- 清除：該場所有 `check_in`、`match_game` 列；`outcome`、`winner_id`、`submitted_by`、`submitted_at`、`appeal_deadline`、`confirmed_at`、`forfeit_deadline` 設為 null；`wins_a`、`wins_b` 歸 0；更新 `updated_at`。
- 不改：狀態、`scheduled_at`、兩隊、裁判、`next_match_id` 等結構欄位。
- 回傳 `ReplayCleared`：清除前的報到紀錄（`CheckInRead` 清單）、各局（`PublicGame` 清單）、`outcome`、`winner_id`、`wins_a`、`wins_b`，讓 B 的操作紀錄能記「變更前後內容」。
- 不寫操作紀錄、不發事件（由 `replay_match` 依情境一次寫入，避免同一個動作兩筆紀錄）。
- `contracts/competition.md` 的公開函式表新增一列，並寫明 B 的 `replay_match` 接下來要做的事：`transition_match` 轉回待開打、寫入新時間、`start_forfeit_clock`、操作紀錄、事件。
- deferred-work 中 5.1、5.3 兩項「6.2 重新比賽要 D 提供清除函式」在本函式完成後刪除。

**Ask First:**
- 改 B 的 disputes 模組或任何既有公開函式的行為。

**Never:**
- 不寫 `replay_match`、不轉換狀態、不改時間（B 的 6.2）。
- 不做「更正結果」需要的改寫各局（6.2 的 `correct_result`，B 需要時另議）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 一方棄權後申訴 | 申訴中、A 隊已報到、`outcome=forfeit`、勝隊 A | 報到紀錄清空、結果欄位歸零；回傳含 A 隊的報到紀錄與原結果 | N/A |
| 雙方棄權後申訴 | 申訴中、無報到、`double_forfeit` | 結果欄位歸零；回傳空的報到紀錄 | N/A |
| 有比分的場次 | 申訴中、2 局、`played` | 各局刪除、勝局數歸 0；回傳兩局 | N/A |
| 狀態不對 | 待開打、申訴期、已確認 | — | 409 `MATCH_INVALID_TRANSITION`，資料不變 |
| 其他場次 | 同賽事另一場有報到與比分 | 不受影響 | N/A |
| 清除後重賽 | 呼叫後轉回待開打、重設時間與棄權期限 | 兩隊能重新報到；兩隊都報到後能登錄第 1 局（新增而非覆寫） | N/A |

</frozen-after-approval>

## Code Map

- `competition/service.py` -- `lock_match`、`transition_match`、`start_forfeit_clock`、`_public_game`、`_check_in_to_read`（或同等）；新增 `clear_for_replay`
- `competition/repository.py` -- `list_check_ins`、`list_games`、`clear_match_result`（季軍賽取消用，可參考但不要改它的行為）；新增刪除報到與各局、重設欄位的函式
- `competition/models.py` -- 新增 `ReplayCleared`
- `contracts/competition.md` -- 公開函式表、申訴段落
- `deferred-work.md` -- 刪除 5.1、5.3 的兩項 6.2 清除項目
- 測試寫法：`tests/competition/test_score_entry.py`、`test_check_in.py`（建立申訴中場次可直接改 status 或用 `transition_match`）

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/models.py` -- `ReplayCleared`
- [x] `backend/app/modules/competition/repository.py` -- 刪除與重設
- [x] `backend/app/modules/competition/service.py` -- `clear_for_replay`
- [x] `backend/tests/competition/test_replay_clear.py` -- I/O 矩陣每一列；「清除後重賽」端對端：清除 → `transition_match` 回待開打 → 改時間＋`start_forfeit_clock` → 兩隊報到 → PUT 第 1 局成功且為新增
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- 同步
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除兩項

**Acceptance Criteria:**
- Given 一場申訴中、有報到與比分的場次，when 呼叫 `clear_for_replay` 再依約定轉回待開打，then 它與從未開打的場次在報到、比分、判棄權候選上的行為相同。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-01）：Blind Hunter 10 項、Edge Case Hunter 3 項、Verification Gap 0 個缺口。沒有 intent_gap、bad_spec。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Edge | 呼叫端傳入未鎖或過期的 `match`，狀態檢查可能讀到舊值，清掉同時被確認的結果 | low | 同類函式都在開頭自己加鎖。patch：開頭 `lock_match(match.id)` 取得最新值再檢查 |
| 2 | Blind | deferred-work 的兩項在 `replay_match` 還不存在時就刪掉，後續步驟與「同一交易」的要求沒人追 | medium | patch：新增一項指向 6.2 `replay_match`，寫明呼叫順序與同一交易 |
| 3 | Blind | `ReplayCleared` 沒有 `submitted_by`、`submitted_at`、`appeal_deadline`、`confirmed_at`、`forfeit_deadline` 的清除前值 | low | 用途是操作紀錄的變更前後。patch：補欄位 |
| 4 | Blind | docstring 與 contracts 寫「不改時間」，實際會清掉各種期限 | low | patch：改為「不改 `scheduled_at`」 |
| 5 | Blind | contracts 與測試的結構欄位漏了 `loser_next_match_id` | low | patch：補上 |
| 6 | Blind、Edge | 錯誤狀態測試漏 `voided`，且只檢查狀態與結果 | low | patch：補 `voided`，並檢查勝局數、勝隊、棄權期限不變 |
| 7 | Blind | 其他場次的測試只檢查各局，沒檢查報到紀錄還在 | low | 依賽事刪除的錯誤不會被抓到。patch：補斷言 |
| 8 | Blind、Edge | 「端對端」其實是手動照約定的步驟；棄權期限只驗非空；沒驗 `list_forfeit_due` 能再選到 | low | AC 的判棄權候選一項沒有執行過的證據。patch：改名為約定順序測試，驗確切期限與期限過後 `list_forfeit_due` 選得到 |
| 9 | Blind | 測試建的申訴中場次帶 `confirmed_at`，不合實際 | low | 用意是證明會被清掉。patch：加註解說明 |
| 10 | Blind | contracts 沒寫整個重賽要在同一交易，中途 commit 會留下無人處理的狀態 | low | patch：contracts 寫明 |
| 11 | Blind | 沒鎖賽事、沒檢查賽事狀態 | low | 呼叫端依約先鎖賽事；申訴中的場次只存在於進行中的賽事。併入 #1、#10 的文件說明 |
| 12 | VG | `updated_at` 沒有斷言 | false | VG 自己判定不算缺口：接著的 `transition_match` 會再寫入 |

## Verification

**Commands:**
- 本分支在 worktree `I:/大學課程/軟工/espory-wt/replay`，沒有 `.env`；compose 指令要在主 repo `I:/大學課程/軟工/espory-platform` 目錄執行，並把 worktree 掛進容器（`WT=I:/大學課程/軟工/espory-wt/replay`；`MSYS_NO_PATHCONV=1` 下 `/i/...` 會掛成空資料夾）：
  `MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "$WT/backend/app:/app/backend/app" -v "$WT/backend/tests:/app/backend/tests" -v "$WT/backend/scripts:/app/backend/scripts" backend bash -c "python -m pytest -q -p no:cacheprovider | tail -1; bash scripts/lint.sh"` -- expected: 全部通過
- 測試資料庫共用，不要同時跑兩組完整測試。
- 沒有新 API，不需要重新產生 client。

**結果（2026-11-01，第 1 輪修正後）：**
- 後端全套：1258 passed；`scripts/lint.sh` 通過。`test_replay_clear.py` 11 個。
- 突變驗證（主代理在容器內另外執行）：不刪報到紀錄 → 3 個失敗；不刪各局 → 2 個失敗；不檢查申訴中 → 5 個失敗；勝局數不歸零 → 1 個失敗。
