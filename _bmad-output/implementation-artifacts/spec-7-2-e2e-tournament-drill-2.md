---
title: 'Story 7.2（第二階段）：端對端演練接上新增遊戲、建立賽事與組隊'
type: 'feature'
created: '2026-11-04'
status: 'done'
route: 'dispatch'
baseline_commit: '17cc63b5d24238c6f7b9d717f955f76eb3b57f02'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一階段把完整賽事流程寫成 `test.fixme`。2.1（S36）、2.2（S26／S27）、2.4（S1／S2）、3.1（建隊與邀請）、3.2（參賽資料）已合併，這幾步現在可以真的跑，但仍列為待辦。

**Approach:** 在 `tournament.spec.ts` 為三款遊戲各加一個真的測試，從平台管理員新增遊戲一路走到一隊滿編、全員填完參賽資料；後續要等 3.3 以後的步驟維持 `test.fixme`。共用步驟抽到 `support/`。

## Boundaries & Constraints

**Always:**
- 沿用第一階段的規則：只靠 `games.ts` 的設定切換遊戲、tag 標 Story 與 FR、每次執行不重複、選取元素優先用 role 與可見文字、桌機與 375 px 各跑一次、API 超過 1 秒失敗。
- 遊戲名稱與賽事名稱加上本次執行的後綴（後端遊戲名稱不分大小寫唯一），同一個資料庫可以重複執行。
- 主辦方以第一階段的流程產生（註冊→申請→平台管理員核准），不依賴示範資料。

**Never:**
- 不修改產品程式（`frontend/src`、`backend/app`），也不直接呼叫 API 準備資料（全部經由畫面）。
- 不把 e2e 加進 CI；不寫通知、隊伍搜尋、晉級路徑。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新增遊戲 | 平台管理員在 `/admin/games/new` 依 `GameConfig` 填寫 | Toast「已新增遊戲」，列表出現該遊戲 | N/A |
| 建立賽事 | 主辦方選該遊戲；報名開始＝現在前 1 小時 | 先發、替補、BO 自動帶入遊戲預設；S27 狀態「開放報名」 | N/A |
| 觀眾瀏覽 | 未登入開 S1 | 「開放報名」分組裡有該賽事，點進 S2 看到賽事名稱 | N/A |
| 組隊 | 隊長在 S2 建隊，其餘隊員開邀請連結加入 | S17 名單人數＝先發＋替補 | N/A |
| 名單已滿 | 再多一個帳號開邀請連結 | 「連結已失效：隊伍已滿。」 | N/A |
| 參賽資料 | 每人填遊戲 ID、段位、上傳 PNG 截圖 | 平均段位積分＝各人段位積分的平均（全員已填） | N/A |

## Decisions（2026-11-04 使用者定案）

- 每款遊戲一隊滿編（特戰英豪 7、英雄聯盟 6、星砂競技場 3 人），全員填參賽資料；完整執行約多 3～5 分鐘。

</frozen-after-approval>

## Code Map

- `frontend/tests/e2e/tournament.spec.ts` -- `fullTournamentSteps`／`newGameSteps` 產生 `test.fixme`；本次把 2.1、2.2、2.4、3.1、3.2 的步驟換成一個真的測試，其餘保留。
- `frontend/tests/e2e/identity.spec.ts:20` -- `approveApplication`（看 API 回應換頁）；抽到 `support/` 供建立主辦方重用。
- `frontend/tests/e2e/support/accounts.ts` -- `newTestAccount`、`registerVerifiedAccount`、`logIn`、`platformAdmin`、`uniqueSuffix`。
- `frontend/tests/e2e/support/games.ts` -- 三款 `GameConfig`、`rosterLimit`。
- S36 `features/tournaments/GameForm.tsx`：欄位「遊戲名稱」「先發人數」「替補人數」「每局預估時間（分鐘）」，combobox「預設 BO 數」（BO1…）、「比分型態」（只記勝負／記回合比分）；段位每列 label「第 N 筆段位名稱」「第 N 筆積分」，按「新增段位」加列；送出「新增遊戲」。
- S26 `features/tournaments/CreateTournamentForm.tsx`：「賽事名稱」、combobox「遊戲」、「名額」、`datetime-local` 的「報名開始」「報名截止」「開賽時間」（台北時間，`fill("YYYY-MM-DDTHH:mm")`）、「優先期（小時）」、「每輪間隔（分鐘）」（下方提示最小間隔）、送出「建立賽事」→ `/organizer/tournaments/{id}`，h1 為賽事名稱。
- S1 `/`：`section[aria-label=開放報名]`，卡片是 `link`（名稱含賽事名稱）。S2：按鈕「建立隊伍」→ 對話框「隊名」→「建立隊伍」→ S17 `/teams/{id}`。
- S17 `features/registration/`：`getByLabel("隊伍邀請連結")` 取 `/join/{token}`；`ul[aria-label=隊伍名單]`；自己那列「填寫我的資料」→「遊戲 ID」、combobox「段位」、`getByLabel("段位截圖").setInputFiles()`、「儲存資料」；名單下方「平均段位積分 N.NN」。
- `/join/{token}`：h1「加入隊伍」，已登入按「加入隊伍」；滿員顯示「連結已失效：隊伍已滿。」。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/tests/e2e/support/organizer.ts` -- `approveApplication` 移出 identity spec；新增 `createOrganizer()`（註冊、申請、管理員核准）。
- [x] `frontend/tests/e2e/support/drill.ts` -- `addGame`、`createTournament`（回傳 id）、`createTeam`（回傳邀請連結）、`joinTeam`、`fillPlayerProfile`（產生小 PNG）、`expectedAveragePoints`。
- [x] `frontend/tests/e2e/identity.spec.ts` -- 改 import `support/organizer.ts`，行為不變。
- [x] `frontend/tests/e2e/tournament.spec.ts` -- 每款遊戲一個真的測試（tag 含 2.1、2.2、2.4、3.1、3.2 與 FR），以 `test.step` 分段；`fullTournamentSteps`、`newGameSteps` 移除已實作的步驟。
- [x] `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill.md`、`deferred-work.md` -- 只新增：第二階段做了哪些、還剩哪些等上游。

**Acceptance Criteria:**
- Given compose 已啟動，when `docker compose --profile e2e run --rm e2e`，then 三款遊戲的新測試在 desktop 與 mobile-375 都通過，其餘仍為 skipped；再跑一次仍通過。
- Given 前端檢查，when typecheck 與 `bunx biome check`，then 無錯誤。

## Implementation Notes

- 第一次完整執行卡住超過 20 分鐘：`fullyParallel: true` 且本機沒設 worker 上限，16 核開 8 個 worker，6 個演練同時開 5～9 個頁面、註冊多個帳號，後端與 Chromium 搶滿 CPU。2 個 worker 時 e2e 容器仍吃約 5 核，所以 `playwright.config.ts` 改成本機與 CI 都 `workers: 1`（不屬產品程式）。
- 單跑星砂競技場×桌機 2.1 分鐘通過；完整執行（1 個 worker、e2e 容器限 1.5 核）10 passed、62 skipped，22.4 分鐘。使用者決定只跑一次，未照 Verification 跑第二次。
- 前端容器內 `bun run typecheck`、`bunx biome check src tests playwright.config.ts` 無錯誤。

## Verification

**Commands:**
- `docker compose -p flow-e2e up -d --build --wait` 後 `docker compose -p flow-e2e --profile e2e run --rm e2e`（跑兩次）-- expected: 失敗 0
- 前端容器內 `bun run typecheck`、`bunx biome check src tests playwright.config.ts` -- expected: 無錯誤
