---
title: 'Story 5.2（S4 部分）：場次頁的申訴期區塊'
type: 'feature'
created: '2026-10-30'
status: 'done'
baseline_commit: 'bd1bf7fb537f1681de773c4aac514b809b27600e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-8-match-page-results.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 5.2 的驗收條件要求判棄權之後，S4 要顯示哪一隊棄權，並顯示申訴期倒數。哪一隊棄權的部分，5.8 已經用 Score display 的「棄權」標記做到了。但 S4 目前沒有申訴期資訊，觀眾看不出結果為什麼還沒確認。另外，Countdown 元件是 B 在 2.4 的範圍，還沒做。

**Approach:** 照使用者的決定，在 S4 新增「申訴期」區塊，顯示「{絕對時間} 截止」，再留一個倒數插槽。B 的 Countdown 做好之後，由呼叫端放進插槽，不在這裡重做倒數。資料型別 `PublicMatchDetail` 補上 `appeal_deadline`。

## Boundaries & Constraints

**Always:**
- 什麼時候顯示：場次狀態是申訴期（`appeal_window`）或申訴中（`appealed`），而且 `appeal_deadline` 有值。不符合時，整個區塊不顯示。
  - 申訴中也要顯示，因為另一隊在期限內仍可以申訴（FR-30）。
- 區塊放在一張 Card 裡，內容依序是：
  1. 標題「申訴期」，`label` 字級、`status-appeal`。
  2. 倒數插槽（`countdown?: ReactNode`）。呼叫端沒有傳入時，什麼都不顯示，也不留空白。
  3. 一行「{formatMatchDateTime(appeal_deadline)} 截止」，`caption`、`muted-foreground`。
- 不讀裝置時鐘，也不判斷是否已經到期。到期之後怎麼呈現，屬於 Countdown 的範圍。
- 版面依 EXPERIENCE.md〈場次頁（S4）〉：
  - `≥ lg` 放在右欄最上方，「同輪其他場次」之上。
  - `< lg` 放在 Score display 之後、各局列表之前，也就是頁首、Score display、申訴期、各局、同輪其他場次。
  - 375px 寬時頁面沒有橫向捲軸。
- `PublicMatchDetail` 新增 `appeal_deadline: string | null`（ISO）。假資料中，申訴期與申訴中的場次都要有值。

**Never:**
- 不做 Countdown 元件、進度條、「提出申訴」按鈕與申訴對話框（B 的 2.4、Epic 6）。
- 不改 `match-time.ts`，也不改後端。

**Decisions（使用者 2026-10-30 定案）:**
- 先顯示截止時間，加一個倒數插槽；B 的 Countdown 做好後再放進去。
- 不做 code review（沿用使用者的決定）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 申訴期 | `appeal_window`、截止 2026-10-18T06:22:00Z | 顯示「申訴期」與「10/18（日）14:22 截止」 | N/A |
| 申訴中 | `appealed`、有截止時間 | 同上 | N/A |
| 有倒數插槽 | 傳入 `countdown` | 插槽在標題與截止時間之間 | N/A |
| 其他狀態 | 待開打、進行中、已確認、已取消 | 不顯示區塊 | N/A |
| 缺截止時間 | `appeal_window`、`appeal_deadline` 為 null | 不顯示區塊 | N/A |
| 手機順序 | `< lg`、申訴期 | 頁首 → Score display → 申訴期 → 各局 → 同輪 | N/A |
| 桌機位置 | `≥ lg`、申訴期 | 右欄：申訴期在上，同輪其他場次在下 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/match-types.ts`：`PublicMatchDetail` 補上 `appeal_deadline`。
- `frontend/src/features/competition/match-fixtures.ts`：`matchDetailFromBracket`。申訴期與申訴中的場次，`appeal_deadline` 設為預定時間加 2 小時，其他狀態設為 null。`simulateMatchChange` 不用改。
- `frontend/src/features/competition/MatchSpectatorView.tsx`：目前是兩欄 grid，左欄 `match-main`（Score display、各局），右欄 `aside`（同輪）。`< lg` 時申訴期要插在 Score display 與各局之間，`≥ lg` 時要在右欄最上方，所以要調整結構，例如改用 grid 的區域或 `order`。不能為了版面把同一個區塊渲染兩次。新增 prop `appealCountdown?: ReactNode`，往下傳給申訴期區塊。
- `frontend/src/features/competition/match-time.ts`：`formatMatchDateTime`，直接用。
- `frontend/src/components/ui/card.tsx`、`frontend/src/index.css`：`text-label`、`text-status-appeal` 這些 token。
- `frontend/tests/unit/match-detail-fixture.ts`：測試用的 `makeDetail`，要補上 `appeal_deadline` 的預設值 null。
- `frontend/src/routes/dev/match.tsx`：預覽頁不傳倒數也可以；如果要示範插槽，可以傳一段示意文字，但只放在預覽頁。
- 5.8 既有的版面測試（`match-route.test.tsx` 等）必須全部通過。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/MatchAppealWindow.tsx`：新增申訴期區塊。
- [x] `frontend/src/features/competition/match-types.ts`、`match-fixtures.ts`、`frontend/tests/unit/match-detail-fixture.ts`：加上 `appeal_deadline`。
- [x] `frontend/src/features/competition/MatchSpectatorView.tsx`：放入申訴期區塊，調整 `< lg` 與 `≥ lg` 的順序，並把 `appealCountdown` 傳下去。
- [x] `frontend/tests/unit/match-appeal-window.test.tsx`：涵蓋 I/O 矩陣每一列。版面順序用 DOM 順序與 class 驗證，例如 `order` 或 grid area。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`：新增一項，內容是：
  - 公開單場 API 的提議形狀要多一個 `appeal_deadline`
  - B 的 Countdown（`appeal` 變體，帶進度條）做好後，要由 S4 路由傳入 `appealCountdown`
  - 到期後要顯示「已截止 · 系統處理中」

**Acceptance Criteria:**
- Given `/dev/match` 選一場申訴期的場次，when 寬度是 1280px，then 右欄上方顯示申訴期區塊；when 寬度是 375px，then 申訴期區塊在比分之後、各局之前，而且沒有橫向捲軸。
- Given 前端，when 執行 Verification 的指令，then 全部通過，5.8 的既有測試也全部通過。

## Implementation Notes

- **版面只渲染一次**：DOM 維持兩個容器，`match-main`（Score display、各局）與 `match-aside`（申訴期、同輪）。`< lg` 時兩個容器是 `display: contents`，四個區塊直接成為外層單欄 grid（`grid-cols-1`）的項目，再用 `max-lg:order-1～4` 排成 Score display、申訴期、各局、同輪；`≥ lg` 時容器恢復成 flex 欄，`order` 只在 `< lg` 生效。沒有改用 grid area，因為兩欄共用列高時，申訴期一長就會在 Score display 與各局之間撐出空白。
- **閱讀順序**：`< lg` 的視覺順序（申訴期在各局之前）與 DOM 順序（各局在前）不同。目前申訴期區塊沒有可聚焦元素，不影響 Tab 順序；Epic 6 在區塊內加「提出申訴」按鈕時要再確認焦點順序。
- **申訴期區塊**：`MatchAppealWindow` 是 `role="region"`，以標題「申訴期」命名；倒數插槽只有傳入非空值（不是 `undefined`／`null`／`false`）時才渲染 `data-slot="appeal-countdown"` 的容器。截止時間用 `formatMatchDateTime`，它只拿目前時間決定要不要加年份，不判斷是否到期。
- **假資料**：`appeal_deadline` 是 `scheduled_at` 加 2 小時；`/dev/match` 的「申訴期」M18 顯示「10/18（日）18:00 截止」。預覽頁沒有示範倒數插槽。
- **驗證（2026-10-30）**：frontend 重建後 healthy；build、typecheck、biome（156 個檔案）都通過；單元測試 38 個檔案、367 個通過（新增 13 個，5.8 的既有測試全部通過）。在 `/dev/match` 選 M18 實測：1280px 時申訴期在右欄最上方（x=852、寬 400），同輪其他場次在其下；375px 時由上而下為頁首、Score display、申訴期、各局、同輪，`scrollWidth` 等於 375，沒有橫向捲軸。改動的檔案都是 LF。依使用者的決定，沒有跑 code review。

- **主對話驗收（2026-10-30，重建 frontend 後重跑）**：
  - build、typecheck、biome（156 個檔案）都通過。
  - 單元測試 38 個檔案、367 個通過，新增 13 個，5.8 的既有測試全部通過。
  - 改動的檔案都是 LF。
  - 依使用者的決定，沒有跑 code review。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose up -d --build --wait frontend`：frontend healthy。
- `docker compose exec frontend bun run --filter frontend build`：成功。
- `docker compose exec frontend bun run --filter frontend typecheck`：沒有錯誤。
- `docker compose exec frontend bunx biome check`：沒有錯誤。
- `docker compose exec frontend bun run test:unit`：全部通過。
