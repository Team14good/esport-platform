---
title: 'S30 場次管理頁：修改時間與指派裁判（4.3、4.4 前端）'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '72fdb9cf3772b252800147e75b0041a09ba38710'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.3 改時間與 4.4 指派裁判的後端都完成了，但主辦方後台沒有 S30「場次管理」頁，主辦方無法實際操作。

**Approach:** 在主辦方賽事後台新增 `/organizer/tournaments/$tournamentId/matches`：側欄加「場次管理」，用 `DataTable` 列出場次，每列可「修改時間」（Dialog）與選擇裁判；全部呼叫已產生的 client。

## Boundaries & Constraints

**Always:**
- 列表來自 `CompetitionService.listManagedMatches`，裁判名稱來自 `TournamentsService.listTournamentReferees`，以 `account_id` 對應。
- 依輪次排序、季軍賽在決賽之後；欄位：場次（`matchLabel`）、輪次、對戰（隊名或待定說明 `source_a/b`）、時間（`formatMatchDateTime`）、狀態（`MATCH_STATUS_BADGES`）、裁判、操作。每頁 20 筆，`< md` 為卡片（`DataTable` 內建）。
- 修改時間：`reschedule.can_reschedule` 為假時按鈕停用並在下方寫原因；為真時開 Dialog，`datetime-local` 的 `min`／`max` 為 earliest／latest（台北時間，`latest` 為 null 時不設上限），送出 `taipeiLocalToIso`。
- 裁判：`can_assign_referee` 為假時唯讀顯示目前裁判；為真時 `Select` 列出「不指派（主辦方登錄比分）」＋`assignable_referee_ids` 對應的裁判，目前裁判即使不在名單內也顯示為已選。選定即送出（`assignReferee`／`unassignReferee`），不另外確認。
- 任何成功或失敗（含所有 409）都重抓列表；失敗用 `notifyError` 顯示後端訊息，成功用 `notifySuccess`。
- 每列有「查看場次」連到 S4（代登比分入口）。

**Never:**
- 不改後端與 `src/client/`；不做狀態篩選、S13、裁判邀請頁（S31 是 B 的 2.7）。
- 不改 B 的既有元件；`organizer-nav.ts` 只在「總覽」後新增一項。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 列表 | 已抽籤賽事 | 依輪次列出全部場次，輪次名「32 強…決賽」、季軍賽寫「季軍賽」 | 載入失敗顯示錯誤與重試 |
| 未抽籤 | 404 `BRACKET_NOT_FOUND` | 空狀態「還沒有對戰表，抽籤後就能在這裡管理場次。」 | — |
| 已報到 | `reason=already_checked_in` | 「修改時間」停用，寫「已有隊伍報到，無法修改時間」 | — |
| 改時間 | 範圍內送出 | 列表顯示新時間，提示「已修改場次時間」 | 409 顯示後端訊息（含允許範圍）並重抓 |
| 指派 | 選一位裁判 | 列表裁判欄更新，提示「已指派裁判」 | 409 顯示訊息並重抓 |
| 收回 | 選「不指派」 | 裁判欄為「主辦方登錄比分」，提示「已收回裁判」 | 同上 |
| 不能指派 | `can_assign_referee=false` | 只顯示目前裁判文字，沒有選單 | — |
| 沒有裁判 | 賽事裁判清單為空 | 選單只有「不指派」，下方寫「還沒有裁判接受邀請。」 | — |
| 非主辦方 | 403 | 沿用後台既有的無權限畫面 | — |

## Decisions

- 2026-11-04（使用者）：核准 Design Notes 的做法（裁判選定即送出不另外確認、停用原因文字、不做狀態篩選）。

</frozen-after-approval>

## Code Map

- `frontend/src/routes/organizer/tournaments/$tournamentId/index.tsx` -- 照抄成 `matches.tsx`（`head` 標題「場次管理 · FLOW」）
- `frontend/src/features/tournaments/organizer-nav.ts` -- `tournamentNav` 在「總覽」後加「場次管理」（lucide 圖示，例如 `CalendarClockIcon`）
- `frontend/src/features/tournaments/organizer-queries.ts`、`useCreateTournament` -- query／mutation 寫法；`myTournamentQueryOptions` 的 retry 規則
- `frontend/src/components/common/` -- `DataTable`（必須傳 `page`、`pageSize`、`total`、`onPageChange`）、`EmptyState`、`StatusBadge`；`components/ui/` 的 `dialog`、`select`、`loading-button`、`input`
- `frontend/src/lib/` -- `api-error.ts` 的 `parseApiError`、`feedback.ts` 的 `notifyError`／`notifySuccess`、`datetime.ts` 的 `taipeiLocalToIso`（需新增反向的 `isoToTaipeiLocal`，同檔、附單元測試）
- `frontend/src/features/competition/match-time.ts` 的 `formatMatchDateTime`；`match-status.ts` 的 `matchLabel`、`MATCH_STATUS_BADGES`
- `frontend/src/features/competition/bracket-fixtures.ts:100` 的 `roundName` -- 移到 `features/competition/round-name.ts`（與後端 `bracket.round_name` 相同規則），fixtures 改 import；總輪數取列表最大 `round_no`
- `frontend/src/client/sdk.gen.ts` -- `CompetitionService.listManagedMatches`、`rescheduleMatch`、`assignReferee`、`unassignReferee`；`TournamentsService.listTournamentReferees`
- 測試：`frontend/tests/unit/organizer-tournaments.test.tsx` 的寫法（`signInAs`、`renderApp`、`vi.spyOn(Service, fn)`、`httpError`）

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/round-name.ts`、`bracket-fixtures.ts` -- 移出 `roundName`
- [x] `frontend/src/lib/datetime.ts` -- 新增 `isoToTaipeiLocal`
- [x] `frontend/src/features/competition/organizer-matches-queries.ts` -- 列表、裁判清單的 queryOptions 與改時間、指派、收回的 mutation hooks（完成後 invalidate 列表）
- [x] `frontend/src/features/competition/OrganizerMatchesPage.tsx`（＋ `RescheduleDialog.tsx`、`RefereeSelect.tsx`） -- 頁面
- [x] `frontend/src/routes/organizer/tournaments/$tournamentId/matches.tsx`、`organizer-nav.ts` -- 路由與側欄；重新產生 `routeTree.gen.ts`
- [x] `frontend/tests/unit/organizer-matches.test.tsx`、`datetime` 與 `round-name` 的單元測試 -- I/O 矩陣每一列
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 4.3、4.4 兩項 S30 延後項目（本頁處理完）
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 4.3、4.4 註記改為 S30 完成待合併

**Acceptance Criteria:**
- Given Dialog 的時間選擇器，when 開啟，then `min`／`max` 等於列表的 earliest／latest 轉成台北時間。
- Given 任一 mutation 結束（成功或失敗），when 檢查 query，then 列表重抓一次。

## Implementation Notes

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-04）：Blind Hunter 13 項、Edge Case Hunter 6 項、Verification Gap 2 個缺口＋1 項；另含實作者回報的側欄高亮。沒有 intent_gap、bad_spec。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Blind、Edge、VG | 裁判清單載入失敗時當成「沒有裁判」：裁判顯示「未知的裁判」、每列寫「還沒有裁判接受邀請」；403 也照預設重試 | medium | patch：失敗時顯示錯誤＋重試、`retry` 照列表規則，補測試 |
| 2 | Blind | Dialog 沒寫可選範圍，原生時間選擇器在部分瀏覽器看不出 min／max | medium | patch：說明寫「可選 {earliest}～{latest}」（無上限寫「{earliest} 以後」） |
| 3 | Blind、Edge | `open && can` 只遮住 Dialog，`can` 變回真時自己再開 | low | patch：`can` 變假時 `setOpen(false)` |
| 4 | Edge | 預定時間已早於 earliest 時，預填值低於 min | low | patch：預填取 max(scheduled_at, earliest) |
| 5 | Blind | 時間沒改也送出、顯示「已修改場次時間」 | low | 後端不寫入，但提示誤導。patch：沒改時「儲存時間」停用 |
| 6 | VG、Blind | 頁碼超出時改回最後一頁沒有測試 | low | patch：補 `?page=9` 測試 |
| 7 | Blind | 收回的測試用後端不會回的 `can_assign_referee: false` | low | patch：保持 true，斷言選單回到「不指派」 |
| 8 | Blind | `isoToTaipeiLocal` 測試放在 `round-name.test.ts` | low | patch：移到 datetime 的測試檔 |
| 9 | Blind、Edge | min 只取到分，比 earliest 早，最早那一分鐘會被拒絕 | false | contracts：最早＝現在進位到整分＋30 分鐘；前一輪時間也是整分，earliest 不帶秒 |
| 10 | Blind | Dialog 開著時範圍過期 | low | 送出遇 409 會重抓並顯示後端帶範圍的訊息（4.3 的約定）。reject |
| 11 | Blind | 裁判清單的 query key 沒和裁判相關功能共用 | low | S31（B 的 2.7）還沒做，目前沒有其他地方會改裁判。reject |
| 12 | Blind | route 從 identity 功能 import `parsePage` | low | 搬到共用模組要改 A 的檔案。reject |
| 13 | Blind | 儲存中選單仍顯示舊裁判 | low | 選單停用到重抓完成，數百毫秒。reject |
| 14 | Blind | 延後項目直接刪除而非標記完成 | false | CLAUDE.md：項目在本 Story 處理完時刪除 |
| 15 | 實作者 | 在 `/matches` 時「總覽」也亮起（`BackofficeLayout` 的 `Link` 用前綴比對） | medium | 既有問題，B 的 S31 也會遇到；Never 禁止改 B 的元件。defer：記入 deferred-work 並在 PR 請 B 決定（例如 `BackofficeNavItem` 加 `exact`） |

## Design Notes

UX 文件（EXPERIENCE.md 89、242、337–339、578 行）只定了停用條件與資料表規則；其餘由 AI 依現有元件決定，使用者可在核准前改：
- 裁判用 `Select` 選定即送出，不加確認：指派、收回都可以再改，AlertDialog 依 UX 只用在不可逆動作。
- 停用原因文字：`already_checked_in`「已有隊伍報到，無法修改時間」（UX 原文）；`match_not_reschedulable`「只有待開打的場次可以修改時間」；`forfeit_due`「棄權期限已過，等待系統判定」；`no_valid_time`「目前沒有可選的時間」；`tournament_not_reschedulable`「賽事目前的狀態不能修改時間」（與後端訊息一致）。
- 不做 UX 標為 [ASSUMPTION] 的狀態篩選。

## Verification

**Commands:**
- 在主 repo 執行、掛 worktree 的 `frontend/src`、`frontend/tests`：`bunx biome check src tests`、`bunx vitest run tests/unit/organizer-matches.test.tsx tests/unit/<新的單元測試>` -- expected: 通過（ConfirmDialog／alert-dialog 的型別錯誤是本機映像過舊，以 CI 為準）
- `routeTree.gen.ts` 要掛整個 `frontend/` 跑 `bunx vite build` 產生（見 CLAUDE.md〈環境上的坑〉）

**Manual checks:**
- 瀏覽器（含 375 px）走一次：列表、改時間、指派、收回
