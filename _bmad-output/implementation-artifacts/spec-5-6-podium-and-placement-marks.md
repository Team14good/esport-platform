---
title: 'Story 5.6 第二階段：S2／S3 頒獎台與名次標記'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 後端在賽事結束後已經回傳 `PublicBracket.podium`，但前端完全沒有用到：S2、S3 看不到冠亞季軍，決賽與季軍賽卡也沒有名次標記（epics 5.6 最後一組 AC、UX-DR26）。

**Approach:** 新增 Podium 元件，賽事結束時顯示在 S3 對戰樹上方與 S2 頁面最上方；冠軍一列 `heading-md`＋`brand` 標記，亞軍、季軍各一列，手機直排、桌機三欄，點隊名到該隊最後一場的 S4。決賽與季軍賽卡的隊伍列加名次標記（冠軍 `brand`，亞軍、季軍 `muted-foreground`）。只動前端，沒有 API 或 schema 變更。

## Decisions（2026-11-09；使用者指示有問題時選最推薦的做法）

- **S2 的位置**：S2 是 B 的 `TournamentPage`，依 CONTRIBUTING 不改對方既有函式，所以由路由 `routes/tournaments/$tournamentId/index.tsx` 把新元件放在 `TournamentPage` 上方（EXPERIENCE.md 狀態表寫「Podium 置頂」），不把它插進分頁內。
- **該隊最後一場**：該隊出現過、沒有取消（`voided`）的場次中輪次最大的一場。準決賽雙方棄權時，季軍賽已取消，不算最後一場。
- **從缺**：名次為 `null` 就不列該列；三個都是 `null` 時不顯示 Podium。
- **S4**：公開單場 API 沒有名次資料，S4 與同輪其他場次卡不顯示名次標記，只有 S3 對戰樹的卡片顯示。

</frozen-after-approval>

## Implementation Notes

- 「S27 改為唯讀」不用改：`DrawButton` 只在 `open`／`closed` 顯示，`OrganizerStatusCountdowns` 在其他狀態回傳 null，S27 沒有其他寫入動作（讀 `OrganizerTournamentOverview.tsx`、`DrawButton.tsx` 確認）。
- 沒有季軍賽時不顯示季軍賽卡、準決賽雙方棄權時決賽卡「—」＋「輪空」、季軍賽「已取消」灰色兩列，都是 4.6／5.8 既有行為，本次只加測試確認名次標記與它們並存。
- 新增的檔案：`features/competition/TournamentPodium.tsx`、`tests/unit/tournament-podium.test.tsx`（15 個案例）、`tests/e2e/podium.spec.ts`。本機沒有已結束的賽事，e2e 用 `page.route` 回傳假資料，沒有走真的後端 API；後端的 `podium` 欄位由 5.5／5.6 的後端測試涵蓋。
- 驗證（2026-11-09）：Vitest 全部 916 通過、typecheck、biome、前端 build 通過；Playwright 在 desktop 與 mobile-375 都通過，並看過 S3 桌機與 S2 手機的截圖；S2、S3 除對戰樹外沒有橫向捲動。
- 依使用者「每個 Story 不各自 review、最後統一做一次」的決定，略過這個流程內的 Blind Hunter 審查。
