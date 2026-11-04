---
title: 'S4 申訴期倒數接上 Countdown、PageBanner 連結型 action'
type: 'feature'
created: '2026-11-04'
status: 'done'
route: 'oneshot'
baseline_commit: '0a31e2f5d3c1bbb4f19b05374117bba04061d0f0'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-2-appeal-window-display.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** B 的 `Countdown`（#29）已合併，但 S4 申訴期區塊的倒數插槽仍是空的（deferred-work 的 5.2 S4 項目第 (2)(3) 點）。A 的 `PageBanner` 的 action 只支援 `onClick`，S1「申請成為主辦方」不能中鍵開新分頁（deferred-work 的 2.4 第二階段項目）。另外 `sprint-status` 的 4.6 在 #33 合併後仍是 `review`。

**Approach:** S4 路由把 `Countdown`（`appeal` 變體，歸零時重抓場次）傳給 `MatchSpectatorView` 的 `appealCountdown`；`PageBanner` 的 action 新增 `to`（TanStack `Link`）的寫法；4.6 改 `done`。

**Decisions（使用者 2026-11-04 定案）:**
- 有倒數時，申訴期區塊不再顯示自己的「{絕對時間} 截止」，只留 Countdown 下方那一行，避免重複；沒有倒數時照舊。這一點取代 `spec-5-2-appeal-window-display.md` I/O 矩陣「插槽在標題與截止時間之間」。
- 進度條起點先用 Countdown 預設的截止前 24 小時（場次資料沒有申訴開始時間）；請 D 的單場 API 帶申訴開始時間，記進 `deferred-work.md`。
- `PageBanner` 只新增連結型 action，不改 B 的 `OrganizerApplyBanner.tsx`；S1 改用 `to` 交給 B，記進 `deferred-work.md`。

</frozen-after-approval>

## Implementation Notes

- S4 路由（`routes/tournaments/$tournamentId/matches/$matchId.tsx`）有 `appeal_deadline` 時建立 `Countdown`（label「剩餘時間」、`variant="appeal"`），`onExpire` 讓場次查詢失效重抓；傳給既有的 `MatchSpectatorView` 的 `appealCountdown`，沒有改 `MatchSpectatorView`。
- `MatchAppealWindow`：有倒數時不再渲染 `[data-slot=appeal-deadline]`；`match-appeal-window.test.tsx` 的預期跟著改，`match-route.test.tsx` 新增 M18（假資料的申訴期場次）的測試。
- `PageBanner` 的 `BannerAction` 改成 `onClick` 或 `to`（`LinkProps["to"]`）二選一；`to` 時以 `Button asChild` 包 TanStack `Link`。既有呼叫端（B 的 `OrganizerApplyBanner`）不用改也能編譯。
- `sprint-status`：4.6 改 `done`。`deferred-work.md`：刪除 2.4 第二階段「`PageBanner` 只支援 `onClick`」那項（A 的部分已完成），新增給 B 的 S1 改用 `to`、給 D 的申訴開始時間兩項。5.2 S4 申訴期那項的第 (1) 點（單場 API 的 `appeal_deadline`）還沒完成，整項保留。
- `spec-5-2-appeal-window-display.md` 凍結區的 I/O 矩陣「有倒數插槽」列與 Decisions 依使用者 2026-11-04 的決定更新。
- 依使用者要求省 token，跳過 Blind Hunter 審查。
- 驗證：前端容器內 typecheck、biome（216 個檔案）、build 通過；單元測試全部 700 個，`--maxWorkers=4` 一次 4 個、一次 8 個失敗，都在 B 的 `admin-games`、`organizer-tournaments` 與 A 的 `signup`，約 1 秒逾時。`organizer-tournaments` 單獨跑，在 main 上 2 次、加上本次修改 3 次都全過，屬於 `deferred-work.md` 已記的偶發逾時。這次改到的 4 個測試檔（36 個）全過。
