---
title: 'Story 2.6：取消賽事'
type: 'feature'
created: '2026-11-21'
status: 'done'
baseline_commit: '3b41f171d8d7f1185683ef107cefa646c8a68f80'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 主辦方無法正式停止辦不成的賽事；狀態轉換表雖允許轉為「已取消」，但沒有取消的 API、事件與 S27 按鈕（FR-10）。

**Approach:** tournaments 新增 `cancel_tournament` 與 `POST /organizer/tournaments/{tournament_id}/cancel`：鎖住賽事、轉為 `cancelled`（沿用 `transition_tournament` 的操作紀錄）、發出 `TournamentCancelled` 事件。S27 加「取消賽事」按鈕與確認對話框，已取消後 S27 唯讀。

## Boundaries & Constraints

**Always:**
- 只有該賽事的主辦方能取消（`Organizer` ＋ `ensure_tournament_owner`）；router commit，service 不 commit（AD-5）。
- 先 `lock_tournament` 再轉換；已結束、已取消的賽事回 409，錯誤代碼 `TOURNAMENT_NOT_CANCELLABLE`、訊息「已結束或已取消的賽事不能取消。」，狀態與操作紀錄都不變。
- `TournamentCancelled` 只帶 `tournament_id`（事件只放實體 id），在同一個交易內經 `core.events.publish` 寫入 outbox。
- 確認對話框：標題與確認鈕「取消賽事」、內文「所有已報名隊伍的隊長與選手會收到通知；賽事資訊改為唯讀，無法復原。」，destructive。
- S27 的「取消賽事」只在狀態不是 `finished`、`cancelled` 時顯示；已取消時 S27 沒有任何動作（抽籤、待處理清單都不顯示）。
- 介面文字繁體中文、按鈕動詞＋名詞。

**Never:**
- 不改 D 的報到（5.1）與比分寫入（5.3）的加鎖順序、不改 `get_public_match` 對已取消賽事的處理：CONTRIBUTING 7.1 已派給 D，等本 Story 合併後做。
- 不做 S1 徽章與 S2 destructive banner（已存在，只補測試確認）。
- 不做 6.3 的申訴逾期提醒工作（尚不存在）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 取消進行中的賽事 | 主辦方本人，狀態 upcoming／open／closed／published／ongoing | 200 回 `TournamentRead`（`cancelled`）；操作紀錄 `tournament.status_changed`；outbox 一筆 `TournamentCancelled` | N/A |
| 已結束 | 狀態 finished | 不變 | 409 `TOURNAMENT_NOT_CANCELLABLE` |
| 已取消 | 狀態 cancelled | 不變、不重複發事件 | 409 `TOURNAMENT_NOT_CANCELLABLE` |
| 別的主辦方 | 非該賽事主辦方 | 不變 | 403 |
| 非主辦方帳號／未登入 | 一般帳號／無 token | 不變 | 403／401 |
| 不存在 | 亂數 id | — | 404 `TOURNAMENT_NOT_FOUND` |
| 取消後報名或登錄比分 | 已取消的賽事 | 拒絕 | 409（既有 `REGISTRATION_CLOSED`／`TOURNAMENT_NOT_ACCEPTING_SCORES`） |
| 取消後 worker | 已取消賽事的到期場次 | 判棄權、申訴期滿確認、賽事開始都略過，狀態不變 | N/A |

## Decisions

- **（使用者 2026-11-21）不改既有的 worker 工作。** 判棄權（`judge_forfeit` 的 `tournament_cancelled`）、申訴期滿確認（`auto_confirm_expired` 的 `_ENDED`）、賽事開始（`_start_bracket` 只處理 `published`）都已在鎖內各自略過已取消賽事；本 Story 補測試證明。「接受報名／比分的檢查函式」就是既有的 `ensure_accepting_registrations`、`ensure_accepting_scores`。偏離原 AC 字面「worker 先用同一個函式檢查」：行為相同，不動 D、A 的程式。
- **（使用者 2026-11-21）通知規則照 epics.md 由 A 的 Story 3.9 登錄。** 本 Story 只發 `TournamentCancelled` 事件；合併後到 3.9 完成前，取消賽事不會發通知。`notifications/rules.py` 註解「2.6 自己登錄」與 epics.md 不符，PR 說明告知 A。
- **（使用者 2026-11-22，審查第一輪）接受 3.9 前取消的賽事通知會遺失。** `notifications/service.py` 對沒有規則的事件只記 log 就標為已處理，3.9 上線後也不會補發。3.9 合併前只有本機與示範環境會取消賽事，所以不改程式；PR 說明告知 A，deferred-work 新增一項請 3.9 第 2 部分處理已取消賽事的補發（A 在 PR #106 已寫明第 2 部分等 2.6）。
- **（使用者 2026-11-22，審查第一輪）確認對話框的關閉鈕改為「保留賽事」。** `ConfirmDialog`（`components/common/`）新增選填的關閉鈕文字屬性，預設仍為「取消」，其他對話框不受影響；PR 說明列出。
- **（使用者 2026-11-21）spec 約 2,800 tokens，超過 1,600 仍不拆**：只有取消賽事一個目標，後端與 S27 分開無法單獨上線。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/service.py:206-231` `_TRANSITIONS` -- 已允許非結束狀態 → `cancelled`；`:402` `lock_tournament`；`:459` `transition_tournament`（寫操作紀錄、不發事件）；新增 `cancel_tournament(session, *, tournament_id, actor_id) -> TournamentRead`
- `backend/app/modules/tournaments/models.py` -- 新增事件 `TournamentCancelled(Event)`（欄位 `tournament_id`；寫法照 `competition/models.py:208` 起的事件）
- `backend/app/modules/tournaments/router.py:112` -- 照 GET 單筆的權限寫法（`Organizer`、`authz.ensure_tournament_owner`）；router commit
- `backend/app/core/events.py:58` `publish(session, event)` -- flush、不 commit
- worker 現有檢查（不改，只補測試）：`competition/forfeit_job.py:197`、`competition/service.py:1101` `auto_confirm_expired`、`:1364` `start_due_tournament`
- 測試範本：`backend/tests/tournaments/test_transitions.py`、`test_tournaments.py`；`backend/tests/worker/test_judge_forfeits.py`、`test_confirm_expired_appeals.py`
- `frontend/src/features/tournaments/organizer-queries.ts:55` `useCreateTournament` -- 照寫 `useCancelTournament`，成功後更新 S27 單筆並使主辦方清單與公開查詢（`PUBLIC_TOURNAMENTS_KEY`）失效
- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx:226-250` -- S27 動作區（`DrawButton`、`OpenDisputesPanel`）；新增取消按鈕
- `frontend/src/components/common/ConfirmDialog.tsx:22` -- `destructive`、`onConfirm` 回 Promise
- 已存在、不改：`features/tournaments/status.ts`（「已取消」徽章）、`TournamentPage.tsx:16,96-101`（S2 banner）
- 前端測試：`frontend/tests/unit/organizer-tournaments.test.tsx`、`tournament-pages.test.tsx`
- `backend/app/alembic/` -- 本 Story 沒有 schema 變更，不需要遷移

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/{models,service,router}.py` -- 事件、`cancel_tournament`、取消 API
- [x] `backend/tests/tournaments/test_cancel_tournament.py` -- I/O Matrix 前 7 列；含 outbox 有一筆 `TournamentCancelled`、操作紀錄
- [x] `backend/tests/worker/test_cancelled_tournament_skipped.py` -- I/O Matrix 最後一列：判棄權、申訴期滿確認、賽事開始各一個測試
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh`
- [x] `frontend/src/features/tournaments/{organizer-queries.ts,CancelTournamentButton.tsx,OrganizerTournamentOverview.tsx}` -- mutation、按鈕與確認對話框、S27 唯讀；成功 Toast「已取消賽事。」，409 以 Toast 顯示伺服器訊息
- [x] `frontend/tests/unit/organizer-tournaments.test.tsx` -- 按鈕顯示條件（各狀態）、確認後呼叫 API 並顯示已取消、409、已取消時沒有任何動作；`tournament-pages.test.tsx` 確認 S1 徽章與 S2 banner 已有測試（沒有就補）
- [x] `contracts/tournaments.md` -- 新增 `cancel_tournament`、取消 API、`TournamentCancelled`；移除「期中不提供 `cancel_tournament`」

**Acceptance Criteria:**
- Given S27 狀態為開放報名，when 主辦方按「取消賽事」並在對話框確認，then 狀態徽章變「已取消」、「取消賽事」與其他動作消失，S2 頁頂出現「此賽事已取消」
- Given 已結束的賽事，when 主辦方開啟 S27，then 不顯示「取消賽事」
- Given 375 px 寬的手機，when 開啟 S27 的確認對話框，then 沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- `CancelTournamentButton` 的對話框改成受控開關：取消成功後狀態先變 `cancelled`，等對話框關閉才移除按鈕，避免對話框開著時被卸載。409 時以錯誤 Toast 顯示伺服器訊息並關閉對話框（與 `DrawButton` 相同），再重抓 S27。
- `PUBLIC_TOURNAMENTS_KEY`（`queries.ts`）改為 export，讓取消後能使公開查詢失效。
- 本機開發資料庫原本停在 2.3 的遷移 `a7d3e9b2c6f4`（本分支沒有這支遷移），backend 起不來。使用者同意後，以 2.3 合併前的遷移檔把開發資料庫降回 `d1f3a5c7e9b2`（只刪 `round_setting` 表）。
- 手動檢查（2026-11-22，瀏覽器、375 px）：確認對話框沒有橫向捲軸（scrollWidth＝clientWidth＝375）、關閉鈕是「保留賽事」；確認後 Toast「已取消賽事。」，S27 徽章變「已取消」且沒有任何動作；S2 頁頂顯示「此賽事已取消」。取消的是本機的測試賽事「分輪 BO 測試盃」。
- 完整驗證（審查修補後）：後端 `scripts/test.sh` 2550 passed、`lint.sh` 通過；前端 build、typecheck、biome、`test:unit`（74 檔、1072 passed）通過。

## Spec Change Log

- 2026-11-22 審查第一輪：Review Triage Log #1、#2 屬 intent_gap，使用者決定後寫入凍結區 Decisions（接受通知遺失、關閉鈕改「保留賽事」）。#1 不改程式，#2 只新增 `ConfirmDialog` 的選填屬性，既有程式碼不需重新推導，改以修補處理（連同 #3～#5）；#6 寫入 deferred-work。KEEP：取消 API、事件、worker 測試、S27 按鈕與 mutation 的既有實作都保留。

## Review Triage Log

第一輪（2026-11-21）：Verification Gap 1 筆、Edge Case Hunter 1 筆、Blind Hunter 13 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Edge、Blind | 3.9 登錄規則前發出的 `TournamentCancelled` 會被消耗掉：`notifications/service.py:73-76` 找不到規則只記 log 就返回，事件標為已處理，3.9 上線後也不會補發；確認對話框卻寫「會收到通知」 | high：已對照程式確認；Decisions 只同意「這段期間不發通知」，沒有涵蓋永久遺失與對話框文字不實 | intent_gap（問使用者） |
| 2 | Blind | 確認對話框的關閉鈕是「取消」，和「取消賽事」並列容易混淆，也不是動詞＋名詞 | medium：每次取消都會看到；`ConfirmDialog` 共用 `CANCEL_TEXT`，改字要新增屬性 | intent_gap（問使用者） |
| 3 | Gap | 取消後讓公開查詢（S1、S2）與 S25 清單失效沒有測試；刪掉 `onSettled` 測試照過 | medium：驗收條件要的「S2 出現 banner」靠這段 | patch（補測試，比照 `draw-button.test.tsx:156-176`） |
| 4 | Blind | 「不可取消的狀態」在 `_NOT_CANCELLABLE_STATUSES` 又寫一次，與 `_TRANSITIONS` 重複 | low：之後改轉換表會兩邊不一致；直接改成由 `_TRANSITIONS` 判斷 | patch |
| 5 | Blind | `test_confirm_expired_appeals_skips_cancelled_tournament` 依賴 fixture 的預設時間 | low：直接改成明確 `frozen_clock.set` | patch |
| 6 | Blind | 取消後側欄的場次管理、裁判、申訴、檢舉頁仍顯示動作；對話框寫「賽事資訊改為唯讀」 | maybe-false（若為真屬 medium）：裁判邀請（`ensure_accepting_referees`）與申訴處理（`disputes/service.py:106`）後端已拒絕已取消，改場次時間未確認；驗收條件只要求 S27 | defer |
| 7 | Blind | 報到與比分寫入的加鎖競態、`get_public_match` 對已取消賽事的處理，合併後成真但沒有追蹤 | false：deferred-work 既有項目仍在，CONTRIBUTING 7.1 已派給 D | 不處理 |
| 8 | Blind | 比分被拒只測 service，沒有打 API | low：比分與報到 API 的狀態檢查屬 D，既有測試已覆蓋 `_CHECKABLE_TOURNAMENT`；補 API 測試要抽籤、報到整套前置 | 不處理 |
| 9 | Blind | 產生的 client 只有 422 錯誤型別 | low：與既有路由相同寫法（2.2 審查第 7 點） | 不處理 |
| 10 | Blind | spec 是 `in-review`、sprint-status 是 `in-progress` | false：sprint-status 由 bmad-build 最後一步更新 | 不處理 |
| 11 | Blind | spec 沒有手動檢查與 375 px 的紀錄 | false：手動檢查尚未進行（本機開發資料庫停在 2.3 的遷移版本），完成後記錄 | 不處理 |
| 12 | Blind | 沒有 AI 使用紀錄 | false：bmad-build 完成時新增 | 不處理 |

## Verification

**Commands:**
- `docker compose up -d --build --wait && docker compose exec backend bash scripts/test.sh` -- expected: 後端全部通過
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過
- 前端 `bun run build`、`bun run typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過

**Manual checks:**
- 瀏覽器在 S27 取消一場開放報名的賽事 → S2 顯示 banner；375 px 檢查對話框。
