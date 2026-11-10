---
title: 'Story 7.2（第三階段）：端對端演練跑完報名到頒獎'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'ee836afb6d124243c54c58e1b2b19acd40f627d2'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill-2.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 上游 Story 都已合併，但 `tournament.spec.ts` 從送出報名到頒獎的步驟仍是 `test.fixme`，7.2 的驗收條件還沒有被真的跑過。

**Approach:** 把 fixme 換成真的測試：兩款示範遊戲各跑一場 32 隊完整賽事到頒獎，第三款遊戲跑 8 隊到確認一場結果。關鍵步驟走畫面，大量重複的準備與場次走公開 API，受真實時間限制的期限由測試改資料庫。

## Boundaries & Constraints

**Always:** 只靠 `games.ts` 切換遊戲；tag 標 Story 與 FR；同一資料庫可重複執行；desktop 與 mobile-375 都跑；瀏覽器發出的 API 超過 1 秒就失敗（沿用 fixtures）。

**Never:** 不改 `frontend/src`、`backend/app`；不加任何只給測試用的後端 API；不把 e2e 加進 CI；不寫通知、隊伍搜尋、晉級路徑（期中版調整）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 裁判 | S31 產生連結，新帳號在 S23 接受，S30 指派 | S13 看得到被指派的場次 | N/A |
| 報名與分配 | 一隊在 S17 送出，其餘走 API；優先期改為已過 | 名單鎖定；worker 分配後 S17 顯示「正取」 | 等 worker 最多 90 秒 |
| 抽籤 | S27 按「抽籤」 | 對戰表公開，含 32 隊與季軍賽（賽事狀態為賽程已公布） | N/A |
| 報到與比分 | 兩隊長在 S4 報到，裁判逐局登錄並送出 | 依比分型態完成，場次進入申訴期 | N/A |
| 10 秒更新 | 觀眾開著 S3，申訴期滿自動確認 | 場次確認後 10 秒內顯示新結果，不重新整理 | N/A |
| 申訴更正 | 敗隊長在 S4 申訴，主辦方在 S32 更正 | 勝隊改變並晉級 | N/A |
| 取消資格頂替 | 隊長在 S2 檢舉一支等待第二輪的勝隊，主辦方在 S33 取消資格 | 最近輸給它的隊伍頂替它在第二輪的位置 | N/A |
| 頒獎 | 季軍賽與決賽定案 | 賽事已結束，S3 頒獎台有冠亞季軍 | N/A |
| 操作紀錄 | 演練結束直接查 `audit_log` | 申訴更正與取消資格都有操作者與前後內容，送出系列結果有操作者 | N/A |

## Decisions（2026-11-10，使用者授權「遇到問題選最推薦的」）

- 32 隊每隊走畫面約要 1 小時，因此每場賽事只有一隊送出報名走畫面，其餘組隊、報名走公開 API；第二階段已涵蓋整隊走畫面的流程（第二階段「不直接呼叫 API 準備資料」的限制只適用於該階段）。
- 大量帳號的 Email 驗證由測試改資料庫，角色帳號（主辦方、裁判、走畫面的隊長）照常從 Mailpit 取信。
- 申訴期至少 30 分鐘、每輪間隔更長，演練不可能等真實時間：測試直接把 `match.scheduled_at`、`match.appeal_deadline`、`tournament.priority_end` 改到需要的時間，再由真的 worker 處理；不新增測試用後端 API，後端程式完全不動。
- 每輪只有代表性的場次走畫面（首場、申訴場、決賽），其餘走公開 API。
- 3.9「公開正取名單」期中擱置：「觀眾看到正取隊伍」改為抽籤後在公開對戰表看到隊伍。
- 3.5 先搶期、3.6 截止補位由既有整合測試涵蓋，演練只走優先期分配。

</frozen-after-approval>

## Code Map

- `frontend/tests/e2e/tournament.spec.ts` -- 移除 `fullTournamentSteps`、`newGameSteps` 與 fixme 產生器，`registrationDrill` 保留。
- `frontend/tests/e2e/support/drill.ts`、`organizer.ts`、`accounts.ts`、`fixtures.ts` -- 沿用 `addGame`、`createTournament`、`createOrganizer`、`registerVerifiedAccount`、`logIn`、`newRoleContext`。
- `frontend/Dockerfile.e2e`、`compose.yml` e2e 服務 -- 加 `postgresql-client` 與 `E2E_DATABASE_URL`（不新增 npm 依賴，不動 `bun.lock`）。
- 公開 API：`POST /accounts`、`POST /access-tokens`、`GET /schools`、`POST /tournaments/{id}/teams`、`POST /team-invites/{token}/members`、`PUT /teams/{id}/members/me/profile`（multipart：`game_account_id`、`rank_tier`、`rank_screenshot`）、`POST /teams/{id}/submission`、`GET /tournaments/{id}/bracket`、`POST …/matches/{m}/check-in`、`PUT …/games/{n}`（`GameScoreIn`）、`POST …/submit`。
- 資料表：`account.email_verified`、`tournament.priority_end`、`match.scheduled_at／appeal_deadline`（狀態值看 `MatchStatus`）、`audit_log`（`match.result_submitted`、`match.teams_changed` 等）。
- 畫面：S27 `section[aria-label=抽籤]`；S4「報到」、「新增一局」、`第 N 局 {隊名} 分數`、「登錄」、「送出系列結果」、「提出申訴」→「申訴說明」→「送出申訴」；S30 `{場次}的裁判` combobox；S31「產生邀請連結」、`裁判邀請連結`；S23「接受邀請」；S32「更正結果」（`第 N 局 {隊名} 回合數`／`第 N 局 {隊名} 勝`、「處理理由」）；S2「檢舉隊伍」→「檢舉對象」、「說明」、「送出檢舉」；S33「取消資格」＋「處理理由」；S3 `[data-slot=podium]`。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/Dockerfile.e2e`、`compose.yml` -- 加 psql 與 `E2E_DATABASE_URL` -- 測試要改期限、查 AuditLog。
- [x] `frontend/tests/e2e/support/db.ts`（新增）-- 以 psql 查詢與改期限的函式。
- [x] `frontend/tests/e2e/support/bulk.ts`（新增）-- 走 API 建帳號、組隊、報名、報到、登錄、送出。
- [x] `frontend/tests/e2e/support/matchday.ts`（新增）-- 裁判邀請、抽籤、指派、S4 報到與登錄、申訴、更正、檢舉、取消資格、觀眾與頒獎台。
- [x] `frontend/tests/e2e/tournament.spec.ts` -- 完整賽事與第三款遊戲的真測試，換掉 fixme。
- [x] `README.md`、`deferred-work.md`、`sprint-status.yaml` -- 更新跑法與時間、新增還沒做的項目、狀態改 review。

**Acceptance Criteria:**
- Given compose 已啟動，when `docker compose --profile e2e run --rm e2e`，then 兩款遊戲的完整賽事與第三款遊戲在 desktop 與 mobile-375 都通過，`tournament.spec.ts` 沒有 fixme。
- Given 前端檢查，when typecheck 與 `bunx biome check`，then 無錯誤。

## Implementation Notes

- 驗證結果（2026-11-10，獨立 compose 專案 `flow-e2e`）：完整執行 17 passed、3 failed，28.6 分鐘。桌機全部通過；3 個失敗都是 mobile-375 的新測試，原因相同（見下一點）。單跑桌機：《特戰英豪》32 隊 3.9 分鐘、第三款遊戲 1.9 分鐘。typecheck、`bunx biome check src tests playwright.config.ts` 無錯誤。
- **未達成的 AC：** 375 px 時 S4 比分登錄表（`features/competition/ScoreEntryPanel.tsx`）的 `[data-slot=table-container]` 有內部橫向捲動，違反「只有對戰樹可以橫向捲動」。元件註解寫明這是刻意的設計，元件屬 D；spec 的 Never 不改產品程式，CLAUDE.md 也不改別人既有的函式，所以保留嚴格檢查、不放寬，記進 `deferred-work.md`，由 D 或使用者決定修法。
- 為了確認手機版其他步驟沒有問題，暫時拿掉 `scoreMatchOnPage` 裡那一個檢查跑過一次（沒有提交，跑完還原）：mobile-375 的 3 個新測試都通過，9.7 分鐘。
- 第一次跑時把 `priority_end` 設成 `now() - 1 秒`，第一隊的送出時間晚於它，結算時被排除，等 worker 逾時。原因在測試，不是產品；已改成 `now()`。
- 手機與桌機的 S17 送出後「填寫我的資料」仍在（改為唯讀），鎖定改看「連結已失效：名單已鎖定」。
- 依使用者的記憶設定，未執行 step-04 的 code review，統一於最後做。

## Spec Change Log

## Review Triage Log

## Verification

**結果（2026-11-10）：** D 以 #78、#79 修正 S4 比分登錄表的版面（窄螢幕縮小欄距、隊名任意字元換行、動作鈕直排），上面「未達成的 AC」已解決，`deferred-work.md` 那一條已移除。A 在 #80 以 1769c09 加上審查修正跑完整 e2e（desktop＋mobile-375）：20 passed、0 failed。D 統一 code review 逐條對照 epics 的 7.2 AC（含期中版調整）都有對應的測試步驟。

**Commands:**
- `docker compose --profile e2e run --rm e2e` -- expected: 失敗 0
- 前端容器內 `bun run typecheck`、`bunx biome check src tests playwright.config.ts` -- expected: 無錯誤
