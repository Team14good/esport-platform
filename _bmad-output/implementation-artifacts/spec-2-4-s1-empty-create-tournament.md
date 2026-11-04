---
title: 'Story 2.4（第二階段第 3 項）：S1 空狀態對主辦方顯示建立賽事'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '0a31e2f5d3c1bbb4f19b05374117bba04061d0f0'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** S1 沒有公開賽事時只顯示「目前沒有公開的賽事。」；主辦方沒有從這裡開始建立賽事的入口（EXPERIENCE.md〈通用狀態〉、epics.md Story 2.4：「主辦方另見『建立賽事』」）。這項原本等 2.2 的 S26（PR #31）合併，現已合併。

**Approach:** S1 空狀態在帳號為主辦方（`useCurrentAccount` 的 `is_organizer`，與申請主辦方 banner 同一個查詢）時，文字下方另顯示 S25 同一顆「建立賽事」按鈕，連到 S26 `/organizer/tournaments/new`；一般帳號、未登入、帳號資料載入中或失敗時不顯示。有賽事時不顯示。

</frozen-after-approval>

## Implementation Notes

- 「建立賽事」按鈕從 `OrganizerTournamentsPage.tsx`（2.2）抽成 `CreateTournamentButton.tsx`，S25 與 S1 共用；避免 S1 為了按鈕 import 整個 S25（含 DataTable）。
- `TournamentList.tsx`：以 `useCurrentAccount().data?.is_organizer === true` 判斷；未登入時查詢停用（data 為 undefined），載入中、失敗都不顯示。審查後 S1 空狀態改用共用的 `EmptyState`（UX-DR17 明列 S1；與 S25 一致），所有人看到的空狀態多了置中的標誌、文字改為 `heading-md`。
- 測試 `tests/unit/tournament-list-create-entry.test.tsx` 5 則：主辦方（連結到 `/organizer/tournaments/new`）、主辦方有賽事、一般帳號、帳號載入失敗、未登入。突變檢查：按鈕改為一律顯示時「一般帳號」「未登入」失敗。
- 驗證：typecheck、biome、build 通過；`vitest run --maxWorkers=4 tests/unit` 703 個中 701 個通過，失敗的 `admin-games`（2.1）與 `organizer-tournaments`（2.2）第一個測試是本機負載下的冷啟動逾時，合併 PR #31 時在 main 的程式上已出現；與本檔、`tournament-pages` 一起單獨跑 82 個全過。

## Review Triage Log

Blind Hunter 9 筆（2026-11-04）：

- patch（low）：`OrganizerTournamentsPage.tsx` 多餘的 `CREATE_TOURNAMENT_TEXT` re-export，沒有人用 → 刪除。
- patch（low）：S1 空狀態手刻，未用共用 `EmptyState`，與 S25 及 UX-DR17 不一致 → 改用 `EmptyState`。
- patch（low）：沒有「帳號載入失敗」的測試 → 補上。
- reject（low）：S25 測試寫死「建立賽事」字串；2.2 既有測試，文字改動時會直接失敗，不會空過。
- reject（low）：「主辦方、有賽事」只等請求送出；按鈕只在空狀態分支渲染，有賽事時不可能出現，帳號是否落定不影響結論。
- reject（low）：沒有點擊後到 S26 的測試；`href` 已驗證，S26 的渲染由 2.2 的測試涵蓋。
- reject（low）：`is_organizer` 判斷在 `CreateTeamEntry` 也有一份，建議在 `auth.ts` 加 hook；`auth.ts` 是 A 的檔案，一行判斷不值得跨人改動。
- reject（false）：JSDoc 列出使用處會過時；專案既有元件（如 `TournamentStatusBadge`）都這樣寫。
- reject（false）：缺 AI 使用紀錄；在完成步驟新增。

