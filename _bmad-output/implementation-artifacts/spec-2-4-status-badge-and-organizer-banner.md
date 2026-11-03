---
title: 'Story 2.4（第二階段）：賽事狀態徽章與申請主辦方橫幅'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: 'a8580ea371df2c106c9f844399329f33bafdccf2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 2.4 第一階段的 S1、S2 只用文字顯示賽事狀態，也沒有「申請成為主辦方」的入口；當時 1.7 的 `StatusBadge` 與申請 API、1.8 的主辦方身分都還沒合併，現在已合併。

**Approach:** S1、S2 的賽事狀態改用 `StatusBadge`；S1 頂部加一則可關閉的 default Page banner，引導已登入、非主辦方、沒有待審核申請的帳號到 `/organizer/apply`。

## Boundaries & Constraints

**Always:**
- 狀態色調（DESIGN.md〈Status badge〉）：開放報名 `live`；進行中 `live`＋脈動點；賽程已公布 `brand`；已取消 `destructive`；尚未開放、報名截止、已結束 `muted`。徽章文字沿用 `TOURNAMENT_STATUS_LABEL`。對照表以 `TournamentStatus` 為鍵，新增狀態忘了補會編譯失敗。
- 套用位置：S1 每張賽事卡的狀態、S2 標題列的狀態、S2 總覽的「狀態」欄。S1 分組標題維持文字。
- Page banner（S1 頂部）：default 變體，文字「想辦賽事？」、outline 按鈕「申請成為主辦方」；按鈕前往 `/organizer/apply`。
  - 顯示條件：已登入、`account.is_organizer` 為否、最新申請不是 `pending`、使用者沒有關閉過。帳號或申請資料還在載入或載入失敗時不顯示。
  - 關閉狀態存 `localStorage`，以帳號 id 區分（同一台電腦換帳號登入時各自記錄）；讀寫都包 try/catch，讀不到時視為沒關閉，寫不進去時只在本次畫面隱藏。
- 介面文字繁體中文；375 px 寬沒有橫向捲軸。

**Never:**
- 不做 2.4 第二階段第 3 項「S1 空狀態對主辦方顯示建立賽事」：要連到 2.2 第二階段的 S26，S26 在 PR #31，尚未合併。
- 不做分頁、已正取隊數、建立隊伍按鈕等其他 2.4 延後項目。
- 不修改 `StatusBadge`、`PageBanner`、`organizer-application.ts`、`auth.ts`（A 的檔案），只 import。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 徽章色調 | 七種狀態 | 各自的 tone；只有進行中有脈動點 | N/A |
| 未登入 | S1 | 不顯示 banner，不送帳號與申請請求 | N/A |
| 一般帳號 | 已登入、非主辦方、沒申請過 | 顯示 banner；點按鈕到 `/organizer/apply` | N/A |
| 被退回 | 最新申請 `rejected` | 顯示 banner | N/A |
| 待審核 | 最新申請 `pending` | 不顯示 | N/A |
| 主辦方 | `is_organizer` 為真 | 不顯示 | N/A |
| 關閉 | 點「關閉提示」 | 立即消失；重新整理後仍不顯示；換另一個帳號登入仍會顯示 | `localStorage` 丟例外：本次隱藏，不報錯 |
| 載入中／失敗 | 帳號或申請查詢未完成或失敗 | 不顯示 | 不另顯示錯誤 |

## Decisions

- 2026-11-03（使用者）：2.4 第二階段只先做狀態徽章與申請主辦方 banner；第 3 項「S1 空狀態對主辦方顯示建立賽事」等 PR #31 合併後再做，另記一筆延後項目。
- 2026-11-03（使用者）：banner 文字「想辦賽事？」，outline 按鈕「申請成為主辦方」（整句與 UX 字串表一致，按鈕為動詞＋名詞）。
- 2026-11-03（使用者）：banner 的關閉狀態依帳號 id 分開記錄；S2 總覽的「狀態」欄也換成徽章；S1 分組標題維持文字。

</frozen-after-approval>

## Code Map

- `frontend/src/components/common/StatusBadge.tsx` -- `StatusBadge`、`StatusTone`；只 import
- `frontend/src/components/common/PageBanner.tsx` -- `PageBannerSlot`、`PageBannerProps`（`action.onClick`、`onDismiss`）；只 import
- `frontend/src/features/identity/auth.ts` -- `useIsSignedIn`、`useCurrentAccount`（`data.is_organizer`、`data.id`）；只 import
- `frontend/src/features/identity/organizer-application.ts` -- `useMyOrganizerApplication`（未登入不送請求；沒申請過為 `null`）；只 import
- `frontend/src/features/identity/OrganizerApplyPage.tsx` -- `/organizer/apply` 已存在（1.7）
- `frontend/src/features/tournaments/status.ts` -- `TOURNAMENT_STATUS_LABEL`；新增狀態徽章對照
- `frontend/src/features/tournaments/TournamentList.tsx` -- S1；卡片狀態（`cancelled` 時 `text-destructive`）換成徽章，頂部加 banner
- `frontend/src/features/tournaments/TournamentPage.tsx` -- `TournamentHeader` 狀態換成徽章
- `frontend/src/features/tournaments/TournamentOverview.tsx:115` -- 「狀態」欄換成徽章
- `frontend/tests/unit/tournament-pages.test.tsx`、`auth-fixtures.ts` -- 既有 S1、S2 測試與 `renderApp`；徽章仍帶文字，既有斷言應不受影響

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/tournaments/status.ts` -- `TOURNAMENT_STATUS_BADGES: Record<TournamentStatus, {tone, pulse?}>` 與 `TournamentStatusBadge` 元件（可放 `TournamentStatusBadge.tsx`） -- S1、S2 共用
- [x] `frontend/src/features/tournaments/{TournamentList,TournamentPage,TournamentOverview}.tsx` -- 換上徽章
- [x] `frontend/src/features/tournaments/OrganizerApplyBanner.tsx` -- 顯示條件、`localStorage` 關閉狀態（try/catch）、導向 `/organizer/apply`；放進 S1 頂部的 `PageBannerSlot`
- [x] `frontend/tests/unit/` -- 七種狀態的 tone 與脈動點；S1、S2 顯示徽章；banner 的 I/O 矩陣各列（含 `localStorage` 丟例外）

**Acceptance Criteria:**
- Given 375 px 寬的手機，when 已登入一般帳號瀏覽 S1，then banner 與賽事卡都沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- 徽章：`status.ts` 新增 `TOURNAMENT_STATUS_BADGES`（`Record<TournamentStatus, {tone, pulse?}>`），`TournamentStatusBadge.tsx` 包 `StatusBadge`；S1 卡片原本 `cancelled` 的 `text-destructive` 文字、S2 標題列的狀態文字、S2 總覽「狀態」欄都換成這個元件（總覽 `Field` 的 `children` 改為 `ReactNode`）。
- Banner：`OrganizerApplyBanner.tsx` 的 `useOrganizerApplyBanner()` 回傳 `PageBannerProps | null`，由 `TournamentList` 放進 S1 自己的 `PageBannerSlot`（同 S2 的 cancelled banner，同頁最多一則、destructive 優先由 S1 的 slot 決定）。依 `useIsSignedIn`、`useCurrentAccount`、`useMyOrganizerApplication` 判斷，兩個查詢都 `status === "success"` 才可能顯示，所以載入中與失敗（含重抓失敗）都不顯示。關閉狀態的鍵是 `flow-organizer-apply-banner-dismissed:<帳號 id>`，值為 `"1"`；另以 state 記錄本次畫面已關閉的帳號 id，`localStorage` 寫入丟例外時仍立即隱藏。
- 測試：`tests/unit/tournament-status-badge.test.tsx`（七種狀態的 tone 與脈動點、S1 卡片與分組標題、S2 標題列與總覽）、`tests/unit/organizer-apply-banner.test.tsx`（I/O 矩陣各列，另加帳號載入失敗）。以突變檢查確認不顯示的測試不是空過：拿掉條件後 6 個對應測試失敗。
- 延後：`deferred-work.md` 原本涵蓋整個 2.4 第二階段的項目依使用者指示保留（實作代理一度刪除，已還原）；另記一筆「S1 空狀態對主辦方顯示建立賽事」，等 PR #31 合併後再做。
- 瀏覽器實測：本機 espory-platform 的資料庫缺 `organizer_application` 資料表（申請 API 回 500），正好驗證「載入失敗不顯示」；顯示、關閉、重新整理後不顯示、按鈕導向改接另一套已遷移的後端驗證。375 px 下 S1（卡片＋徽章、banner）與 S2 的 `scrollWidth` 都是 375。主辦方帳號只由單元測試涵蓋，沒有在瀏覽器實測。
- 審查修正後主代理驗證：`tournament-status-badge.test.tsx` 的 S2 測試單獨跑時固定失敗（路由延遲載入，冷啟動超過 `findBy` 的 1 秒），全部一起跑時剛好通過；比照 `tournament-pages.test.tsx` 加上 `beforeAll` 預先載入頁面模組後，單獨跑兩次、全部跑一次都通過（49 個檔、562 個測試）。
- 2026-11-03 依 D 在 PR #32 的審查（使用者同意處理第 1、2 點，第 3 點「申請已核准但帳號快取未更新時短暫顯示」不處理）：`organizer-apply-banner.test.tsx` 的 `settle()` 改為等 QueryClient 裡帳號與申請查詢的 `status` 落定（success／error，載入中那則等 pending）再斷言；並在 `beforeAll` 預先載入 S1。突變檢查：`application.status !== "success"` 改成 `!== "pending"` 時 6 個測試失敗，改成 `=== "pending"`（失敗時會顯示）時「申請資料載入失敗」失敗，`account.status` 改成 `=== "pending"` 時「帳號載入失敗」失敗；還原後 11 個全過。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-03）：Blind Hunter 13 筆、Edge Case Hunter 3 筆、Verification Gap 0 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind | banner 元件自己包 `PageBannerSlot`，S1 頁面沒有擁有 slot，「同頁最多一則」對 S1 失效 | low：目前 S1 只有這一則，但與 spec「放進 S1 頂部的 `PageBannerSlot`」不符 | patch：改成 hook，由 `TournamentList` 擁有 slot |
| 2 | Blind | 顯示條件沒檢查 Email 是否驗證，未驗證帳號進 S15 表單停用 | false：S15 對未驗證帳號停用表單並連到 S7 驗證，是 1.7 設計的流程；UX 只要求已登入、非主辦方、無待審核 | 不處理 |
| 3 | Blind | 新的延後項目沒有標嚴重度 | low：直接修正 | patch |
| 4 | Blind | 新的延後項目沒寫清楚舊項目哪些已完成 | low：直接修正 | patch |
| 5 | Blind | Manual checks 列了主辦方帳號，但瀏覽器沒有實測主辦方與被退回 | low：主辦方、被退回只由單元測試涵蓋，記在此處 | 不處理（已記錄） |
| 6 | Blind | 375 px 只有手動檢查，沒有自動化 | low：期中沒有視覺測試框架，實作代理已量 `scrollWidth` | 不處理 |
| 7 | Blind | 沒測「送出申請後回 S1 banner 消失」 | low：靠 A 的 `OrganizerApplyPage` 更新快取，屬 1.7 既有行為 | 不處理 |
| 8 | Blind | 關閉後被退回也不再顯示 | false：凍結區塊明定「使用者沒有關閉過」才顯示 | 不處理 |
| 9 | Blind、Edge | 每次 render 讀 `localStorage`；其他分頁關閉後本分頁不同步 | low：讀取成本小；同步要加訂閱，日常少見 | 不處理 |
| 10 | Blind | 測試寫死 `"flow-access-token"` | low：直接修正 | patch |
| 11 | Blind | `TournamentStatusBadge` 的 `className` 沒人用 | low：直接刪除 | patch |
| 12 | Blind | 沒有 AI 使用紀錄 | false：在完成步驟處理 | 不處理 |
| 13 | Blind | banner 按鈕以 `onClick` 導向，不能開新分頁 | low：`PageBanner` 的 API 限制，屬 A 的元件 | defer |
| 14 | Edge | API 回傳對照表沒有的狀態時解構 `undefined` 會壞 | low：`Record<TournamentStatus>` 型別保證，CI 會擋 client 未重新產生；加後備屬新增防護 | 不處理 |
| 15 | Edge | 申請已核准但快取的 `is_organizer` 仍為否時顯示 banner | false：兩個查詢同時抓取，核准後 `is_organizer` 即為真；不會出現核准而非主辦方的組合 | 不處理 |

## Verification

**Commands:**
- `cd frontend && bun run build`、`bun run typecheck`、`bunx biome check`、`bunx vitest run --maxWorkers=4` -- 全部通過

**Manual checks:**
- 在瀏覽器以未登入、一般帳號、主辦方三種情況開 S1；開 S2 確認徽章；375 px 寬檢查 `scrollWidth`
