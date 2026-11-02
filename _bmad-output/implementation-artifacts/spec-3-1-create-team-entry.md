---
title: 'Story 3.1 收尾之二：S2 賽事頁的「建立隊伍」入口'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: 'cf96cdeeb89dd61d9a434062f1249d64188d2da6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-1-create-team-and-invite-members.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3.1 只做了 `CreateTeamDialog` 元件，畫面上沒有任何建隊入口，一般使用者無法建隊。B 的 2.4（#29，已合併）在 S2 總覽 `StatusPanel` 的 `case "open"` 留了註解，spec 寫明「開放報名時的啟用按鈕由 C 的 3.1 接上」。

**Approach:** 在該位置掛上 `CreateTeamDialog`，依登入狀態、Email 驗證、主辦方身分與是否已在本賽事有隊伍決定顯示什麼；建隊成功導向 S17（元件既有行為）。

## Boundaries & Constraints

**Always:**
- 只在 `TournamentOverview.tsx` 的 `case "open"` 加入入口；其餘 2.4 的函式不改。PR 說明列出動到 B 的檔案。
- 未登入不顯示「建立隊伍」（UX-DR38「登入者另見」）；未驗證 Email 時按鈕停用並說明原因（3.1 AC，`VerificationRequired` 既有行為）。
- 前端只呼叫 `frontend/src/client`；不改後端與 tournaments 的 API。

**Never:**
- 不做「已正取隊數」、檢舉入口、自訂模式的入口（2.4 Never、3.9、6.4、3.10）。
- 不手改 `frontend/src/client`、`routeTree.gen.ts`。

## Decisions（2026-11-02，邱芯彤）

- 在 #23 接上 S2 的建隊入口（照 2.4 spec 的分工），不另開 PR、不交給 B。
- 本賽事的主辦方：前端判斷後不顯示「建立隊伍」。登入者 `is_organizer` 時，以既有的主辦方賽事列表 API 比對是不是自己的賽事；不改後端。
- 已在本賽事有隊伍：不顯示「建立隊伍」，改顯示該隊的 Registration status card（點擊到 S17），資料取自既有的「我的隊伍」API。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已驗證、可建隊 | 開放報名、登入、不是本賽事主辦方、本賽事沒有隊伍 | 顯示「建立隊伍」，開 S16，成功導向 S17 | 伺服器錯誤顯示在 Dialog |
| 未登入 | 開放報名 | 不顯示「建立隊伍」 | N/A |
| 未驗證 | 開放報名、登入 | 按鈕停用並說明原因 | N/A |
| 本賽事主辦方 | 開放報名、登入者主辦這場賽事 | 不顯示「建立隊伍」 | N/A |
| 其他主辦方 | 登入者是主辦方但不是這場的 | 照一般帳號顯示「建立隊伍」 | N/A |
| 已有隊伍 | 登入者在本賽事已有隊伍 | 不顯示「建立隊伍」，顯示該隊 Registration status card，點擊到 S17 | N/A |
| 資料載入中或失敗 | 我的隊伍或主辦方賽事查詢未完成／失敗 | 不顯示「建立隊伍」（不讓使用者按了才被拒） | 失敗時不另外報錯 |
| 非開放報名 | upcoming／closed 等 | 維持 2.4 既有行為 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/tournaments/TournamentOverview.tsx:70-80` -- `StatusPanel` 的 `case "open"`：目前只有報名截止 `Countdown`，註解「『建立隊伍』的啟用按鈕由 Story 3.1 接上」；`upcoming` 分支的 `CreateTeamNotYetOpen` 是登入者才顯示的寫法參考（`useIsSignedIn`）
- `frontend/src/features/registration/CreateTeamDialog.tsx` -- `CreateTeamDialog({ tournamentId })`：已含 `VerificationRequired`（未驗證停用＋說明）、送出成功導向 S17；docstring「入口（S2）由 Story 2.4 放上」要改成實際狀況
- `frontend/src/features/registration/{queries.ts,RegistrationStatusCard.tsx}` -- `myTeamsQueryOptions()`（`MyTeamCard` 含 `tournament_id`）、Registration status card
- `frontend/src/features/identity/auth.ts:107,130` -- `useIsSignedIn`、`useCurrentAccount`（`AccountRead.is_organizer`）
- `frontend/tests/unit/tournament-pages.test.tsx` -- B 的 S2 測試；本次新增案例放在新檔 `frontend/tests/unit/tournament-create-team.test.tsx`，不改 B 的既有案例
- `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除「Story 2.4 建立 S2 時，要把 `CreateTeamDialog` 放上 S2」一項

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/tournaments/TournamentOverview.tsx` -- `case "open"` 在倒數下方加入建隊入口（依 Decisions）；入口邏輯放在 `frontend/src/features/registration/` 的新元件，2.4 檔案只多一行引用
- [x] `frontend/src/features/registration/CreateTeamDialog.tsx` -- 更新 docstring
- [x] `frontend/tests/unit/tournament-create-team.test.tsx`（新） -- I/O 矩陣各列
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除已處理的 S2 入口項目

**Acceptance Criteria:**
- Given 開放報名中的賽事，when 已驗證且可建隊的帳號在 S2 按「建立隊伍」並送出隊名，then 導向新隊伍的 S17。
- Given 375 px 手機寬度，when 開啟 S2 總覽，then 「建立隊伍」完整顯示、沒有水平捲動。

## Implementation Notes

- 入口元件是 `features/registration/CreateTeamEntry.tsx`。`TournamentOverview.tsx` 除了一行 import 與 `<CreateTeamEntry>`，`case "open"` 還要把倒數和入口包進 `<div className="flex flex-col gap-4">`（寫法和 `upcoming` 分支相同），並刪掉「由 Story 3.1 接上」的註解，所以不只多一行；2.4 的其他函式沒有改。
- 判斷順序：未登入 → 不顯示；帳號或我的隊伍還沒載入或載入失敗 → 不顯示；本賽事已有隊伍 → 顯示 Registration status card；`is_organizer` 時，主辦方賽事列表（`TournamentsService.listMyTournaments`，`GET /organizer/tournaments`）還沒載入、載入失敗或含本賽事 → 不顯示；其餘情況顯示 `CreateTeamDialog`。一般帳號不會呼叫主辦方賽事 API。
- 主辦方賽事的 query options（`organizerTournamentsQueryOptions`，key `["tournaments","organizer","list"]`）定義在 `CreateTeamEntry.tsx`，沒有加進 B 的 `features/tournaments/queries.ts`。2.2 第二階段做 S25 時如果另定 key，可以改成共用。
- deferred-work 刪了兩項：3.1 的「S2 放上 `CreateTeamDialog`」，以及 2.4 的「『建立隊伍』按鈕尚未接上」，兩項說的是同一件事。3.1 那項另外提到「自訂賽事不顯示」，依本 spec 的 Never 交給 3.10，沒有另外追蹤。
- 新測試的 `beforeAll` 預先載入 S2 的方式和 `tournament-pages.test.tsx` 相同（`import TournamentPage`）。`routesByPath["/tournaments/$tournamentId/"]` 型別上存在，但執行時找不到。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-03；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V、B6、E5、E6 | 主辦方賽事查詢載入中、目前帳號載入中或失敗、「已有隊伍的卡片優先於主辦方判斷」都沒有測試 | low | 拿掉對應判斷時既有測試仍通過；補測試是直接新增（補後實作子代理逐一改壞程式確認新測試會失敗） | patch |
| B1 | 後端沒有擋主辦方在自己的賽事建隊 | false | `registration/service.py` `_ensure_can_join` 在 `tournament.organizer_id == account_id` 時拋 403 `ORGANIZER_CANNOT_JOIN`；瀏覽器實測主辦方加入被拒並顯示原因 | reject |
| B2、E9 | 刪掉 3.1 的 deferred 項目後，「自訂賽事不顯示」沒有人追蹤 | false | epics.md〈期中範圍〉第 4 項明訂 2.4、3.1 中自訂模式的驗收條件到期末做 3.10 時一起完成 | reject |
| B3 | 375 px 驗收條件沒有證據 | false | 主流程以 Playwright 在 375 px 實測 S2 的未登入、未驗證、主辦方、可建隊（含 Dialog）、已有隊伍，26 項全過，`scrollWidth` 皆為 375 | reject |
| B4、E7 | Tasks 寫「2.4 檔案只多一行引用」，實際還包了一層 `div` 並刪註解 | low | 修正對象是本 spec；Implementation Notes 已說明，PR 說明會照實列出 | reject |
| B5 | 否定斷言靠固定 50 ms 等待；失敗案例可能還在重試 | low | `tests/unit/render-router.tsx:20` 的 QueryClient 設 `retry: false`，失敗會立即進入錯誤狀態；mock 已 resolve／reject 後 50 ms 足以讓查詢結束 | reject |
| B7、E3 | 主辦方賽事的查詢鍵只在 registration 定義、沒有人讓它失效；主辦方剛建新賽事後，可能先看到舊快取而短暫出現按鈕 | low | 只發生在同一分頁先開過別場 S2、再建新賽事並開它的 S2 時，且按下送出會被伺服器以 `ORGANIZER_CANNOT_JOIN` 拒絕；修正要加新的判斷 | reject |
| B8 | S2 上的隊伍卡片沒有標題、重複顯示賽事名 | low | 卡片沿用 3.1 的 Registration status card，使用者決定顯示該卡片（Decisions） | reject |
| E1 | 報名倒數歸零、狀態變成截止時，開著的 Dialog 會消失、已輸入的隊名不見 | low | 只在截止前最後幾秒開著對話框時發生；修正要讓 Dialog 脫離狀態切換，複雜度高 | reject |
| E2 | 倒數歸零但狀態尚未更新的 5 秒內按鈕仍可按 | low | 送出後伺服器回 `REGISTRATION_CLOSED` 並顯示在 Dialog；修正要再傳入截止時間另做判斷 | reject |
| E4 | 帳號不是 `is_organizer` 卻是賽事主辦方 | false | 只有主辦方帳號能建立賽事（2.2），不會出現 | reject |
| E8 | 「非開放報名」只測了 closed，沒測 upcoming | low | upcoming 是 2.4 既有行為，B 的 `tournament-pages.test.tsx` 已涵蓋 | reject |
| B9、B10 | 沒有 AI 使用紀錄；Triage Log 為空 | false | AI 使用紀錄在 step-05 新增；Triage Log 即本表 | reject |
| V 其他 | B 的 `tournament-pages.test.tsx:305` 註解「建立隊伍的啟用按鈕由 3.1 接上」已過時 | low | 依 Boundaries 不改 B 的既有案例；PR 說明請 B 更新 | reject（PR 說明） |

## Verification

**Commands:**
- `MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps -T -v "$(pwd -W)/frontend:/app/frontend" frontend bash -c "cd /app/frontend && bun run typecheck && bunx biome check && bun run test:unit"` -- 通過
