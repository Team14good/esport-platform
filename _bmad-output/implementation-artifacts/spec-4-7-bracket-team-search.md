---
title: 'Story 4.7：對戰樹隊伍搜尋與晉級路徑'
type: 'feature'
created: '2026-11-21'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-6-bracket-page.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** S3 對戰表（4.6）只能整張瀏覽；32 隊的對戰樹在 375 px 手機上要左右上下捲很久才找得到自己關心的隊伍，也看不出它一路怎麼晉級、下一場在哪裡。

**Approach:** 在 S3 對戰樹上方加隊伍搜尋框（只比對隊名、輸入即篩選），命中時把該隊在每一輪的列、連接線標成 `search-highlight` 晉級路徑，下一輪等它的待定列加虛線框，並自動橫向捲到它目前最遠的一輪。純前端，資料沿用 `PublicBracket`。

## Boundaries & Constraints

**Always:**
- 依 epics.md Story 4.7 原版驗收條件（期中已結束，〈期中範圍〉不限制本 Story）；UX 依 EXPERIENCE.md〈對戰樹〉隊伍搜尋、DESIGN.md `bracket-team-row-search-hit`／`bracket-team-row-tbd`、Team search、示意稿 `key-s3-bracket.html`。
- 比對：去掉前後空白後不分大小寫、部分符合；只比對 `PublicTeamRef.name`。空字串（或只有空白）視為沒有搜尋，對戰樹完整顯示、不顯示命中數。
- 命中隊伍依它在對戰樹第一次出現的位置排序（輪次、同輪由上到下，季軍賽在決賽之後），一次只高亮一隊，預設第一隊；上一隊／下一隊循環切換。
- 搜尋內容只存在元件 state，不寫入網址；每 5 秒輪詢更新後，輸入、目前高亮的隊伍（依隊伍 id）與捲動位置都保留，只有高亮隊伍改變時才自動捲動。
- 搜尋框在 `[data-slot=bracket-tree]` 橫向捲動容器之外；輪次欄頭也移出容器、隨容器橫向捲動同步位移；垂直捲動時搜尋列與輪次欄頭疊成一條固定在視窗頂端。
- 尚未抽籤（沒有對戰表）時不顯示搜尋框。

**Never:**
- 不改後端與 API；不新增搜尋 API（隊伍資料都在 `PublicBracket` 裡）。
- 不搜尋、不顯示學校（NFR-6）。
- 不修改 B 的 `features/tournaments/*` 與共用的 `TopBar`、`AppShell`。
- 不做垂直自動捲動、不做縮放。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 命中一隊、進行中 | 輸入「hydra」，清大 Hydra 第一輪已確認勝、第二輪待開打 | 兩輪的列加 `search-highlight`；第一輪到第二輪的連接線實線同色；第三輪「M… 勝者」列加虛線框、第二輪到第三輪的連接線虛線同色；「找到 1 隊」；捲到第二輪 | N/A |
| 命中多隊 | 輸入「大」命中 N 隊 | 「找到 N 隊」、出現「上一隊」「下一隊」；只高亮目前那隊，切換時捲到該隊最遠的一輪；最後一隊按下一隊回到第一隊 | N/A |
| 零結果 | 輸入不存在的隊名 | 「找到 0 隊」（`muted-foreground`）、沒有任何高亮、搜尋列下方顯示「對戰表上沒有符合的隊伍。候補、已撤回或被退回的隊伍不會出現在對戰表上。」、輸入保留、不捲動 | N/A |
| 已淘汰 | 該隊最後一場已確認且落敗 | 出現過的列都高亮，沒有虛線列 | N/A |
| 冠軍 | 決賽已確認且獲勝 | 每一輪的列與連接線高亮，沒有虛線列 | N/A |
| 第一輪輪空 | 該隊由輪空直接進第二輪 | 從第二輪開始高亮，沒有第一輪的連接線 | N/A |
| 打季軍賽 | 該隊準決賽落敗、在季軍賽 | 季軍賽卡的列也高亮；季軍賽不畫連接線 | N/A |
| 清除 | 按 ✕ | 輸入清空、回到完整對戰樹、焦點回到輸入框 | N/A |
| 輪詢更新 | 搜尋中，對戰表晉級一場 | 高亮跟著新資料重算（例如虛線列變實線命中列），輸入與捲動位置不變 | N/A |
| 高亮的隊伍消失 | 輪詢後原本高亮的隊不在命中結果 | 改高亮第一隊；沒有命中時照零結果 | N/A |

</intent-contract>

## Decisions（2026-11-21，flow-bot 依推薦做法選定，可在 PR 提出異議）

- **固定列蓋在頂欄上，不改 `TopBar`**：專案的 `TopBar` 是全站 `sticky top-0 z-40`。AC 要求「頂欄與賽事分頁照常捲走」，若改 `TopBar` 會影響所有頁面。改成搜尋列 `sticky top-0`、`z-[45]`、不透明底色，捲上去時從頂欄上方滑過、把它蓋住（搜尋列＋欄頭高度 ≥ 頂欄 56px），視覺上等同頂欄捲走；對話框、Sheet（z-50）仍在最上層。
- **桌機也固定**：AC 只寫 375 px，桌機同樣固定可以省一套版型、32 隊往下捲時也看得到欄頭，不會被察覺為錯誤。
- **零結果說明不固定**：照 EXPERIENCE.md「找不到說明文字不固定」，搜尋列與輪次欄頭是兩個 sticky 元素（欄頭 `top` 等於搜尋列高度），說明文字夾在中間、照常捲走。
- **一次只高亮一隊**：AC「可以用上一隊／下一隊切換高亮的隊伍」，多隊同時高亮時路徑會互相重疊、看不出是哪隊。只有一隊命中時不顯示切換鈕。
- **連接線**：照示意稿，命中隊伍相鄰兩輪之間的那半段連接線改為 `search-highlight`；通往虛線待定列的那段用虛線。
- **「目前最遠的一輪」**：該隊出現過的最大輪次（季軍賽算最後一輪）；虛線待定列不算。捲動目標讓該欄完整露出並帶出下一段連接線，與示意稿相同；只在高亮的隊伍改變時捲動（含清除後重新搜尋），輪詢不捲。
- **待定虛線列的判定**：取該隊最後一場非季軍賽場次；狀態為待開打、進行中、申訴期或申訴中，且不是決賽時，下一輪對應位置（`slot` 奇數為 A 方、偶數為 B 方）還沒有隊伍才加虛線。已取消（voided）的場次不算未確認。
- **命中列字重**：照示意稿 `.row.hit .tn` 隊名加粗。
- **元件切法**：純函式 `bracket-search.ts`（比對、路徑）可單元測試；`BracketTree` 只多接「高亮資料」與「固定列內容」兩個選用 prop，沒傳時畫面與 4.6 相同。

## Code Map

- `frontend/src/features/competition/BracketTree.tsx` -- 4.6 對戰樹；欄頭 `[data-slot=bracket-round-heads]` 目前在捲動容器 `[data-slot=bracket-tree]` 內，要移出並以 `onScroll` 同步 `transform`（用 ref，不觸發 re-render）。連接線是單一 `<path data-slot=bracket-connectors>`。
- `frontend/src/features/competition/bracket-layout.ts` -- `layoutBracket` 回傳 `cards`（含 `x`、`y`）、`columns`、`connectors`；常數 `BRACKET_COLUMN_WIDTH`、`BRACKET_CONNECTOR_WIDTH`、`BRACKET_CARD_HEIGHT`。父場次＝下一輪 `slot ceil(slot/2)`；單邊連接線寫法 `M{from} {childY} H{mid} V{parentY} H{to}` 已在第 132 行。
- `frontend/src/features/competition/BracketMatchCard.tsx` -- `TeamRow` 有 `data-slot=bracket-team-row`、`data-side`、`data-pending`；新增命中與虛線樣式加在這裡。
- `frontend/src/features/competition/TournamentBracketPage.tsx:139` -- S3 把 `BracketTree` 放在 `TournamentPodium` 下方；改用新的搜尋外殼。
- `frontend/src/features/competition/match-status.ts` -- `BracketSide`；`disqualifiedLastMatches` 的排序寫法（輪次、季軍賽在後、slot）可沿用。
- `frontend/src/features/competition/bracket-fixtures.ts` -- `createBracketFixture({ teamCount, scenario })`，隊名表 `TEAM_NAMES`（中興 Titan、清大 Hydra…），scenario `scheduled`／`in_progress`／`finished`／`third_place_voided`。
- `frontend/src/index.css:124` -- `--color-search-highlight` 已註冊，可用 `text-search-highlight`、`outline-search-highlight`。
- `frontend/src/components/ui/input.tsx`、`button.tsx`；icon 用 `lucide-react`（`Search`、`X`、`ChevronUp`、`ChevronDown`）。
- `frontend/tests/unit/bracket-tree.test.tsx`、`tournament-bracket-page.test.tsx` -- 既有對戰樹與 S3 頁面測試寫法；`tests/e2e/spectator.spec.ts` 以 `mockFixtureTournament`（32 隊 `in_progress`）測 S3，`support/layout.ts` 的 `BRACKET_TREE_SELECTOR`、`expectNoHorizontalScroll`。

## Tasks & Acceptance

**Execution:**
- [ ] `frontend/src/features/competition/bracket-search.ts` -- `searchBracketTeams(bracket, query)`：依第一次出現位置排序的命中隊伍；`bracketTeamPath(bracket, teamId)`：命中列（場次 id＋方）、相鄰輪連接線（子場次、父場次、是否虛線）、虛線待定列、最遠輪次。
- [ ] `frontend/tests/unit/bracket-search.test.ts` -- I/O 矩陣中比對與路徑的各列（大小寫、空白、部分符合、排序、淘汰、冠軍、輪空、季軍賽、申訴期仍有虛線、決賽沒有虛線）。
- [ ] `frontend/src/features/competition/bracket-layout.ts` -- 匯出單邊連接線 `d` 的產生函式，`layoutBracket` 改用它（輸出不變）。
- [ ] `frontend/src/features/competition/BracketMatchCard.tsx` -- 選用 prop：命中的方、虛線待定的方；命中列 14% 底、左側 3px 實色條、1.5px 外框、隊名加粗，`data-search-hit`；虛線列 1.5px 虛線外框，`data-search-pending`。
- [ ] `frontend/src/features/competition/BracketTree.tsx` -- 選用 prop `highlightTeamId`、`toolbar`（固定在頂端的搜尋列）、`toolbarNote`（搜尋列下方、不固定）；欄頭移出捲動容器並同步位移、垂直 sticky；畫高亮連接線；高亮隊伍改變時把容器 `scrollLeft` 設到最遠一輪。
- [ ] `frontend/src/features/competition/BracketTeamSearch.tsx` -- 搜尋框（放大鏡、placeholder「搜尋隊名」、✕「清除搜尋」）、命中數「找到 N 隊」（`role=status`）、「上一隊」「下一隊」；`BracketExplorer`：持有搜尋 state、算命中、把結果交給 `BracketTree`。
- [ ] `frontend/src/features/competition/TournamentBracketPage.tsx` -- S3 改用 `BracketExplorer`。
- [ ] `frontend/tests/unit/bracket-team-search.test.tsx` -- 輸入即篩選、清除、多隊切換與循環、零結果文字、高亮列與虛線列屬性、rerender 新資料後輸入與高亮保留、自動捲動只在換隊時發生、未傳 prop 時 `BracketTree` 與 4.6 相同。
- [ ] `frontend/tests/e2e/bracket-search.spec.ts` -- 32 隊假資料：搜尋一隊看到高亮與「找到 1 隊」、零結果文字、375 px 下搜尋框不在橫向捲動容器內、捲動後搜尋列固定在頂端、頁面沒有橫向捲軸。

**Acceptance Criteria:**
- Given 已抽籤的 S3，when 觀眾在「搜尋隊名」輸入部分隊名（大小寫不同），then 不按 Enter 就出現「找到 N 隊」並高亮第一隊的晉級路徑，網址不變。
- Given 375 px 手機搜尋中，when 往下捲動，then 搜尋列與輪次欄頭固定在視窗頂端，頂欄與分頁列不再可見；左右捲動對戰樹時搜尋框不動、欄頭跟著對戰樹移動。
- Given 搜尋中，when 輪詢帶來新資料，then 輸入、高亮的隊伍與捲動位置不變。
- Given 前端，when 執行 Verification 的指令，then 全部通過。

## Spec Change Log

## Review Triage Log

## Design Notes

固定列的結構（兩個 sticky 兄弟元素共用同一個父容器，所以只在對戰樹範圍內固定）：

```tsx
<div data-slot="bracket-explorer">
  <div className="sticky top-0 z-[45] h-13 bg-background">{toolbar}</div>
  {toolbarNote /* 零結果說明，不固定 */}
  <div className="sticky top-13 z-[45] overflow-hidden bg-background">
    <div ref={headsRef} data-slot="bracket-round-heads" style={{ transform: `translateX(-${scrollLeft}px)` }} />
  </div>
  <div data-slot="bracket-tree" className="overflow-x-auto" onScroll={syncHeads}>…</div>
</div>
```

沒有 `toolbar` 時（例如其他頁面重用 `BracketTree`）不加 sticky，維持 4.6 行為。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 服務 healthy。
- `docker compose exec frontend` 內 `bun run build`、`bun run typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過（實際指令照 `.github/workflows/ci.yml`）。
- `docker compose --profile e2e run --rm e2e bunx playwright test tests/e2e/bracket-search.spec.ts tests/e2e/spectator.spec.ts` -- expected: desktop 與 mobile-375 通過。

**Manual checks (if no CLI):**
- 375 px 開 S3 搜尋「Hydra」，截圖確認路徑、虛線列與固定列。
