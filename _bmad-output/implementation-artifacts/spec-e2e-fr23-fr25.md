---
title: '補 FR-23 排程與順延、FR-25 判棄權的端對端測試'
type: 'chore'
created: '2026-11-25'
status: 'done'
baseline_commit: 'fa2e7c2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/README.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 41 條 FR 之中，有 6 條沒有 Playwright 端對端測試。其中 FR-23（抽籤後自動排程、順延提示、主辦方改時間並通知）和 FR-25（過期未報到判棄權、進入申訴期）是 D 負責的 competition 模組。這兩條目前只有後端單元與整合測試，沒有驗證「瀏覽器加上真的 worker」的完整流程；F 測試報告與驗收對照表會顯示這兩條沒有端對端測試。

**Approach:** 新增一支 e2e spec，用既有的 support 輔助函式準備資料，關鍵步驟走畫面：
- FR-23：主辦方抽籤後，在 S27 看到順延提示；在 S30 看到排定的時間、修改一場的時間；隊長在通知中心看到改時間的通知。
- FR-25：一場只有一隊報到，讓棄權期限過期後，由真的 worker 判棄權。單場頁顯示棄權結果並進入申訴期，對戰表顯示勝隊。

## Boundaries & Constraints

**Always:**
- 新增 `frontend/tests/e2e/schedule-forfeit.spec.ts`（或相近的名稱），tag 標上 `@story-4.3`、`@FR-23`、`@story-5.2`、`@FR-25`，以及實際測到的其他 Story 或 FR。
- 重用 `support/` 的既有函式，例如 `bulk.ts` 的 `createRegisteredTeams`、`apiCheckIn`、`waitForMatchStatus`，`db.ts` 的 `openCheckIn`，以及 `organizer.ts`。
  - 需要新的資料庫快轉時，只在 `support/db.ts` 新增函式（例如 `expireForfeitDeadlines(matchIds)`），不改既有函式。
  - 新函式要檢查實際改到的筆數，比照 `expireAppealWindows`。
- 期限只改資料庫，判定交給真的 worker，不直接呼叫判定 API。
- 每個斷言都要看得到的畫面文字或狀態，用 `getByRole` 或可見文字，不用內部 test id，除非既有測試已經這樣用。
- 介面文字照實際畫面；讀元件原始碼取得，例如 `DelayedRoundsNotice`、`RescheduleDialog`、單場頁的棄權結果文字。
- 桌機與 375px 兩個 project 都要通過，沿用既有 fixture 的「API 超過 1 秒就失敗」檢查。

**Never:**
- 不改產品程式。若發現產品 bug，記進 `deferred-work.md` 並在回報說明，不在這裡修。
- 不改其他 e2e spec 或既有 support 函式。
- 不用 `waitForTimeout` 這類固定時間的等待，改等狀態。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 排程與順延（FR-23） | 每輪間隔設得比「棄權時限＋BO×每局時間＋申訴期」短的賽事（例如 4 隊、第 1 輪 BO3），報名後由主辦方在畫面抽籤 | S27 出現順延提示並列出被順延的輪次；S30 列出每場的時間，第 2 輪的時間晚於「第 1 輪時間＋每輪間隔」 | N/A |
| 改時間並通知（FR-23） | 主辦方在 S30 改第 1 輪一場的時間 | 列表顯示新時間；兩隊隊長之一登入後，在通知中心看到改時間的通知 | N/A |
| 判棄權（FR-25） | 一場兩隊都確定，只有 A 隊報到，把棄權期限改成已過 | worker 處理後，單場頁顯示 A 隊因對手未報到而勝（棄權），狀態為申訴期；公開對戰表顯示 A 隊勝 | 等狀態時有逾時訊息，說明卡在哪個狀態 |

</frozen-after-approval>

## Code Map

- `frontend/tests/e2e/tournament.spec.ts`：完整賽事演練，示範 support 函式與 tag 的用法。
- `frontend/tests/e2e/support/`：`bulk.ts`（API 準備）、`db.ts`（資料庫快轉）、`organizer.ts`、`accounts.ts`、`fixtures.ts`（1 秒檢查）、`games.ts`。
- `frontend/src/features/competition/`：
  - `DelayedRoundsNotice.tsx`、`DrawButton.tsx`：S27。
  - `OrganizerMatchesPage.tsx`、`RescheduleDialog.tsx`：S30。
  - `MatchHeader.tsx`、`MatchAppealWindow.tsx`、`match-status.ts`：單場頁的棄權與申訴期文字。
- `backend/app/modules/competition/forfeit_job.py`：worker 判棄權的條件（`list_forfeit_due`、`forfeit_deadline`）。
- `backend/app/modules/notifications/rules.py`：改時間的通知規則與文字。
- `README.md` 的 e2e 章節：用獨立的 compose 專案執行。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/tests/e2e/support/db.ts`：只在需要時新增棄權期限快轉函式。
- [x] `frontend/tests/e2e/schedule-forfeit.spec.ts`：涵蓋矩陣三列。
- [x] 實際在 compose 中執行新 spec（兩個 project），全部通過。
- [x] 突變檢查：暫時讓斷言的期望值錯一次（例如順延輪次），確認測試會失敗後再還原，證明斷言真的有作用。

**Acceptance Criteria:**
- Given 獨立的 compose e2e 專案，when 只跑新 spec，then desktop 與 mobile-375 都通過，且可以對同一個資料庫重複執行。

## Implementation Notes

- 執行指令：`docker compose -p flow-e2e --profile e2e run --rm e2e bunx playwright test tests/e2e/schedule-forfeit.spec.ts --project=<desktop|mobile-375>`；`E2E_DATABASE_URL` 由 compose 的 e2e 服務提供。
- 單場頁在申訴期內不顯示勝方，所以判棄權用三種方式交叉確認：B 隊旁的「棄權」標記、API 回傳的 `outcome=forfeit`／`winner_id`、申訴期滿後決賽卡含 A 隊。
- 通知列表只顯示標題，內文改由隊長的 token 讀通知 API 比對；新時間依 `_format_time` 的格式自行計算。
- 第一次執行時，測試自己寫錯兩處：用場次編號找季軍賽（畫面寫「季軍賽」）、以為敗隊只出現在一張卡（實際會進季軍賽）。兩處都已修正。
- 審查後的版本：desktop 2 passed（3.4m）、mobile-375 2 passed（4.0m）；突變（通知時間加 1 小時）1 failed，還原後通過；biome、tsc 結束碼 0。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter＝BH、Edge Case Hunter＝ECH、Verification Gap＝VG）：

| # | 來源 | 判定 | 證據／處理 |
|---|------|------|-----------|
| 1 | BH | medium → patch | `STORY_TAGS` 兩個測試共用：排程測試被標了 5.2（判棄權），判棄權測試被標了 4.3，追溯報告會高估。改成各自標實際測到的 Story。 |
| 2 | BH | low → patch | 標了 `@FR-35`，但沒有任何斷言驗證 10 秒內更新；拿掉這個 tag。 |
| 3 | BH、VG | medium → patch | 通知只比對標題，內文時間錯了也會通過；後端 `test_rules.py` 也沒驗內文。e2e 補上內文含新時間與場次的斷言，並加驗 B 隊隊長。 |
| 4 | BH、ECH | medium → patch | `ROUND_ONE_MIN_GAP_MINUTES * MINUTE_MS > intervalMs` 是兩個常數互比，永遠不會失敗；第 2 輪時間用 API 比 API。改成由第 1 輪的時間加最小間隔（用 `minRoundIntervalMinutes` 算，不寫死 15、30）獨立算出預期值，再斷言 S30 那一列顯示的時間。 |
| 5 | ECH | medium → patch | 第 1、2 輪清單為空時迴圈不會執行，測試會空轉通過；補上「至少一場」的斷言，基準改用第 1 輪最晚的開始時間。 |
| 6 | ECH、VG | low → patch | 申訴期滿後只數卡片數（2 張），分不出 A 進的是決賽還是季軍賽；先等場次狀態變成已確認（等不到時寫出卡在哪個狀態），再斷言決賽卡含 A 隊。 |
| 7 | BH | low → patch | 逾時訊息「棄權期限已過 90 秒」不正確，改成「等了 90 秒仍是 X」。 |
| 8 | ECH、BH | low → patch | `expireForfeitDeadlines` 遇到重複的 id 會誤報；改用去重後的數量。另在註解說明快轉後 `scheduled_at` 晚於棄權期限的取捨。 |
| 9 | ECH | low → reject | `[data-slot=score-team]` 屬於內部屬性：其他 9 支 e2e 也都用 `data-slot`，屬於既有慣例。 |
| 10 | BH | low → reject | 沒驗改時間後的操作紀錄與棄權期限：後端 `test_reschedule.py` 已涵蓋。 |
| 11 | BH | low → reject | 沒測雙方棄權、兩隊都報到的情況：後端 `test_forfeit.py` 與 `test_forfeit_job.py` 已涵蓋，e2e 只走主流程。 |
| 12 | VG | defer（既有決定） | e2e 不在 CI 執行是專案既有的決定；PR 說明與 F 報告註明這兩條的端對端測試需要手動執行。 |
| 13 | BH | low → 主代理處理 | spec 的 Tasks、Implementation Notes、驗證指令沒有更新：由主代理收尾。 |

## Verification

**Commands:**
- 從 `I:\大學課程\軟工\espory-platform\.env` 複製 `.env` 進 worktree，再執行：
  - `docker compose -p flow-e2e up -d --build --wait`
  - `docker compose -p flow-e2e --profile e2e run --rm e2e npx playwright test tests/e2e/schedule-forfeit.spec.ts`（照 e2e 服務實際的指令格式調整）

  預期 desktop 與 mobile-375 全部通過，結束碼 0。
- 再跑一次同一個指令，確認可以重複執行。
- 前端 lint：`biome check tests/e2e`（照 package.json），結束碼 0；`tsc` 若涵蓋 tests 也要通過。
- 收尾：`docker compose -p flow-e2e down -v`，並刪除 worktree 的 `.env`。
