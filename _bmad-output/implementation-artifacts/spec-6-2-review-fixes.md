---
title: 'Story 6.2 審查後續：處理 #69 合併後 A 與 D 的建議'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
baseline_commit: 'd5dee8902e3f484444ffa15740dcb2c0f3f5537f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-2-resolve-appeals.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 6.2（#69）合併後，A 的 bmad-code-review（17 項）與 D 的審查（5 項）指出幾個使用者看得到的問題（另一分頁已處理時錯誤訊息消失、S32 與 S4 在兩輪處理時顯示不同結果、雙方棄權的確認文字寫「勝隊晉級」）、過時的註解與約定，以及多處「拿掉程式測試仍會過」的測試缺口。

**Approach:** 在既有 6.2 程式上做最小修正並補測試；不改 6.2 的需求與介面。

## Boundaries & Constraints

**Always:**
- 409 `NO_OPEN_APPEALS`（另一分頁已處理）時，主辦方要看到後端訊息：以錯誤 Toast 顯示，列表重抓後對話框可以關閉，不能無聲消失。
- S32 的狀態與決定以 `handled_at` 最新的一筆為準，與 S4 公開結果（最後一次處理）一致。
- 雙方棄權場次的確認文字不寫「勝隊晉級」，依 `outcome` 區分。
- 「可重賽的 outcome」只定義一份，`appeals.py` 與 `get_replay_window` 共用。
- 處理後 `useRefetchAppeals` 另外 invalidate 主辦方賽事詳情與 `["competition","managed-matches", tid]`（決賽處理後 S27 摘要要變成已結束）。
- 文件：刪除 `deferred-work.md` 中 6.1 已處理的「`file_appeal` 沒檢查賽事狀態」項目；`contracts/disputes.md` 的 `AppealItem` 隊名來源改為 registration `get_team_names`；`contracts/competition.md` 公開函式表補 `uphold_result`、`correct_result`、`replay_match`（`correct_result` 註明前後各局由呼叫端寫操作紀錄）；改正「6.4 起加入檢舉」與「與前端一致」等過時註解。
- 補齊 A 與 D 列的測試缺口，每個新測試都要在拿掉對應程式時失敗（見 Tasks）。

**Never:**
- 不改 6.2 的 API 形狀與錯誤碼；不做 6.5 的任何事（含 #65 的建議）；不改 #69 的 PR 說明。

## Decisions

- 2026-11-09（使用者，D 在 #69 的中度建議）：重新比賽後，原申訴隊可以對重賽後的結果再申訴。`appeal` 的唯一鍵改成「同一隊對同一場只能有一筆未結案申訴」（`status='open'` 的部分唯一索引，新增一支遷移）；`file_appeal`／`get_appeal_state` 的「本隊已申訴」只看未結案的申訴；補測試；刪除 `deferred-work.md` 的對應延後項目。

</frozen-after-approval>

## Code Map

- `frontend/src/features/disputes/ResolveAppealDialogs.tsx`（約 132 錯誤顯示、246 理由必填、267 確認文字、514 `no_valid_time`）、`AppealsPage.tsx`（約 51、69 附件失敗路徑；141 `StatusCell`；156 `Actions` 卸載對話框）、`organizer-queries.ts`（約 37 註解、86 `useRefetchAppeals`）、`decision-label.ts`。
- `backend/app/modules/competition/appeals.py`（約 31 `_REPLAYABLE`、192 `TOURNAMENT_NOT_RESCHEDULABLE`）、`service.py`（約 1893 `get_replay_window` 的可重賽判斷）。
- `backend/app/modules/disputes/models.py`（約 50、248 註解；66 `UniqueConstraint`）、`service.py`（約 617 理由清理、863 公開結果取最後一次）、`router.py`（`read_open_disputes` docstring）。
- 測試：`backend/tests/disputes/test_resolve_appeals.py`、`test_appeal_concurrency.py`（`committed`、`_run_in_thread` 寫法）、`backend/tests/competition/test_appeal_resolution.py`；`frontend/tests/unit/organizer-appeals.test.tsx`（約 219 按鈕可見性）。
- 文件：`_bmad-output/implementation-artifacts/deferred-work.md`、`contracts/disputes.md`、`contracts/competition.md`（約 229-239 公開函式表）。

## Tasks & Acceptance

**Execution:**
- [x] 前端修正：409 錯誤 Toast、`StatusCell` 取最新決定、雙方棄權確認文字、`useRefetchAppeals` 多 invalidate 兩個 key
- [x] 後端修正：可重賽 outcome 共用一份；過時註解
- [x] 文件：deferred-work、兩份約定
- [x] 後端測試：處理與申訴雙向併發；更正翻盤時 `before`／`after` 的 `winner_id`、重賽 `before.scheduled_at` 與 `MatchRescheduled.scheduled_at`；公開結果取最後一次（兩筆 `handled_at`）；`replay_match` 的 `TOURNAMENT_NOT_RESCHEDULABLE`；理由只含控制／雙向字元回 422、夾帶時被移除；準決賽更正翻盤新敗隊進季軍賽；決賽更正後賽事結束且名次為新勝隊；同場重複送出第二次 `NO_OPEN_APPEALS` 且只有一筆 `appeal.resolved`；雙方棄權經 API 走完重賽
- [x] 前端測試：雙方棄權有「重新比賽」沒有「更正結果」；`no_valid_time` 提示與「前往場次管理」；更正、重賽填理由前確認鈕停用；附件 `window.open` 回 null 時顯示提示且不下載、下載失敗時關閉分頁並顯示錯誤；409 錯誤 Toast；兩輪處理時 S32 顯示最新決定
- [x] 重賽後再申訴：遷移（部分唯一索引）、`file_appeal`／`get_appeal_state` 只看未結案申訴、測試（重賽後原申訴隊可再申訴；同一輪仍不能重複）、刪除延後項目
- [x] `sprint-status.yaml` 6-2 註解補「審查後續 PR #71」

**Acceptance Criteria:**
- Given 主辦方在兩個分頁開同一場的處理對話框，when 第二個分頁送出，then 看到「已經處理」的錯誤 Toast，對話框可以關閉、列表顯示最新狀態。
- Given 先判重新比賽、重賽後另一隊申訴並判維持的場次，when 檢視 S32 與 S4，then 兩者都顯示「維持原結果」。

## Implementation Notes

- 前端：`useResolve` 遇到 409 `NO_OPEN_APPEALS` 時以 `notifyError` 顯示伺服器訊息（其他錯誤照舊只在對話框內顯示），重抓後這一列沒有操作、對話框跟著卸載。S32 狀態改用 `organizer-queries.ts` 新增的 `latestDecision`（`handled_at` 最新的一筆；缺 `handled_at` 的排最前）。維持原結果的確認文字由 `upholdConsequenceText` 依 `outcome` 決定：雙方棄權寫「雙方都不晉級」。`useRefetchAppeals` 另外 invalidate `myTournamentQueryOptions(tid)`（`["tournaments","organizer","detail",tid]`）與 `managedMatchesQueryOptions(tid)`（`["competition","managed-matches",tid]`）。
- 後端：可重賽的 outcome 定義為 competition `service.py` 的 `REPLAYABLE_OUTCOMES`（放在 6.x 前置區段，`get_replay_window` 與 `appeals.replay_match` 共用；`appeals.py` 本來就引用 `service` 的 `_RESCHEDULABLE_TOURNAMENT`，放在 `appeals.py` 會讓 `service.py` 需要函式內 import）。過時註解：`OpenDisputeItem`、`read_open_disputes`、前端 `openDisputesQueryOptions` 改為「檢舉由 6.5 接上」；`APPEAL_*_MAX_LENGTH` 改寫為「前端以 UTF-16 計，兩邊算法不同」。client 重新產生只有這兩段 docstring 改變。
- 重賽後再申訴：遷移 `f2b6d8a1c3e5`（接在 `a9d4f2c6e8b1` 後）刪除 `uq_appeal_match_team`，建立部分唯一索引 `uq_appeal_open_match_team`（`status = 'open'`）與 `ix_appeal_match_id`（原唯一鍵兼作依場次查詢的索引）；downgrade 在已有同隊同場多筆申訴時會失敗。repository `find_team_appeal` 改名為 `find_open_team_appeal` 並只看未結案，6.1 的 `test_unique_key_is_the_last_line_of_defence` 跟著改 monkeypatch 目標。
- 測試：每個新測試都以暫時改壞程式驗證過會失敗（前端：拿掉 409 Toast、`latestDecision` 換回 `find`、雙方棄權文字、賽事詳情 invalidate；後端：`find_open_team_appeal` 不看狀態、公開結果取最後提出的一筆、理由不清理控制字元、處理在鎖之前讀未結案申訴、`replay_match` 不檢查賽事狀態），檢查後已還原。
- `deferred-work.md` 刪除的「賽事已取消時仍可申訴」項目：6.1 在 #63 已處理（`file_appeal`／`get_appeal_state` 的 `_ENDED_TOURNAMENT` 檢查，`test_file_appeal.py` 的參數化測試 `test_ended_tournament_rejects_appeal`），是 #69 合併時誤加回來的，A 在審查中指出。
- 審查後續第 2 輪：重新比賽後再申訴時，S32 同一列會混入上一輪已結案的申訴；`list_tournament_appeals` 改依最早一筆未結案申訴排序（已結案的場次維持原排序），S32 有未結案申訴時「提出隊伍」「提出時間」只列未結案的（`listedAppeals`，說明對話框仍列全部）。遷移的 downgrade 在有同隊同場多筆申訴時先拋 `RuntimeError` 說明需人工處理，不刪資料；另以 `pg_indexes.indexdef` 檢查部分唯一索引的條件（`compare_metadata` 不比對 `postgresql_where`）。
- 實作時發現：重賽後再申訴的測試一開始失敗，因為凍結時鐘下兩輪處理的 `handled_at` 相同，`max` 取到第一筆（重新比賽）。實際上兩輪不會同時處理，改為在測試中把時鐘推到重賽後；程式不變。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap 三位並行；無高嚴重度）：

| # | 來源 | 發現 | 判定與證據 | 處理 |
|---|------|------|-----------|------|
| 1 | VG | 沒有測試確認非 `NO_OPEN_APPEALS` 的錯誤不會跳 Toast | low：放寬條件會重複提示、測試仍過 | patch |
| 2 | BH | 重賽後再申訴時 S32 同一列混兩輪申訴，且依舊輪的提出時間排序 | medium：本 Story 新開的流程，主辦方看不出哪筆待處理 | patch：依最早未結案申訴排序、列只顯示未結案申訴 |
| 3 | BH | 約定 `resolve_appeals` 列仍寫「另一隊不能再申訴」 | low：與 Decisions 矛盾 | patch |
| 4 | BH | 遷移一致性測試不比對 `postgresql_where`，部分索引條件可能悄悄分岔 | low | patch：讀 `pg_indexes.indexdef` 斷言 |
| 5 | BH＋ECH | downgrade 在已有重複申訴時中途失敗 | low：只影響降版 | patch：先檢查並拋清楚的錯誤 |
| 6 | BH | 再申訴測試沒斷言第二次的 `appeal.filed`、`AppealFiled` | low | patch |
| 7 | BH | 索引測試沒走「結案（UPDATE）再新增」的路徑、沒有兩次再申訴的併發測試 | low：`add_appeal` 撞唯一鍵已有測試 | 不處理 |
| 8 | BH | `TOURNAMENT_NOT_RESCHEDULABLE` 測試沒斷言不寫紀錄與事件 | low | patch |
| 9 | BH＋ECH | 重抓失敗時 `NO_OPEN_APPEALS` 同時出現在 Toast 與對話框 | low：要重抓也失敗才會發生 | 不處理 |
| 10 | BH | 前端 UTF-16 與後端 code point 的長度差異只寫在註解 | low | defer：`deferred-work.md` |
| 11 | BH | 測試 helper `_appeal_played` 的勝隊不隨 `sides` | low | patch |
| 12 | BH | 刪除「賽事已取消時仍可申訴」延後項目沒說明 | false：6.1（#63）已處理，#69 合併時誤加回、A 指出 | patch：Implementation Notes 補說明 |
| 13 | BH | `organizer-queries.ts` 匯入 competition、tournaments 的查詢；S30 invalidate 沒測 | low：前端 disputes 依賴這兩個模組是允許的方向 | 不處理 |
| 14 | ECH | 兩輪處理的 `handled_at` 相同時 S32 與 S4 可能不一致 | low：只在凍結時鐘下發生 | 不處理 |
| 15 | ECH | `handled_at` 無法解析時 `latestAt` 為 NaN | false：伺服器一律回 ISO 時間 | 不處理 |
| 16 | ECH | 結案後 `already_filed` 變 false | false：Decisions 定義「已申訴」只看未結案 | 不處理 |

## Verification

**Commands:**
- 後端：`bash scripts/lint.sh`、`bash scripts/test.sh`（容器內掛載原始碼）-- 全過
- 前端：`bunx biome check src tests`、`bun run typecheck`、`bun run test:unit`（容器內，掛上 `vitest.config.ts`）-- 全過
