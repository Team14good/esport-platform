---
title: 'Story 4.6：視覺化對戰樹'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '1578024cbed0390f57752af071e6c2be63f5d202'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 觀眾沒有地方看賽事進行到哪裡。公開對戰樹 API（`GET /tournaments/{id}/bracket` → `PublicBracket`）由 D 在 4.1 提供、S2 賽事頁由 B 在 2.4 提供，兩者都還沒合併。

**Approach:** 照 CONTRIBUTING 6.5「純邏輯先寫」與 D 的 5.1、5.3 做法分兩階段。本 Story 是**第一階段**：在 `features/competition` 做出對戰樹的版面計算、元件與輪詢 hook，資料型別照 `contracts/competition.md` 的 `PublicBracket` 先自己寫，以假資料測試；接上產生的 client、S3 路由與分頁留到第二階段（4.1 的 API 與 S2 合併後）。

## Boundaries & Constraints

**Always:**
- 版型依 UX-DR24：每輪一欄由左到右，欄頭用 `round_names`；欄寬 200px、連接線 28px、場次間距 18px、列高 32px（`index.css` 的 `--spacing-bracket-*`）；季軍賽卡在決賽卡下方、不與決賽相連、標頭「季軍賽」；不顯示種子或籤位。32 隊總寬 1112px，1280px 桌機不出現橫向捲軸；只有對戰樹容器可以橫向捲動，不縮放。
- 場次卡依 DESIGN.md〈Bracket match card〉：待開打的標頭「M3 · 10/18（日）13:00」、比分欄留空；其他狀態標頭改接 Status badge；待定列顯示 `source_a/b`（`muted-foreground`）；輪空、棄權、取消資格以 Bracket mark tag 標示；勝隊與淘汰列樣式只在「已確認」套用。
- 輪詢每 5 秒；分頁在背景時暫停、回到前景立即重抓；重抓時保留舊資料與捲動位置、不顯示 loading；有變動的場次卡 `update-flash` 一次（`muted` 底、1.5 秒，`prefers-reduced-motion` 時不做）；連續 3 次失敗顯示「連線中斷，正在重試 · 最後更新 HH:mm:ss」，恢復後自動消失。
- 375 px 寬時頁面本身沒有橫向捲軸；介面全部繁體中文。

**Never:**
- 不寫後端、不修改 competition 的 `service.py`、`router.py`、`models.py`（D 的範圍）；不手寫 fetch，第一階段的元件與 hook 都不呼叫 API。
- 不做隊伍搜尋、晉級路徑高亮與固定的搜尋列（4.7 擱置）、Podium 與冠亞季標記（Epic 5）、「退賽」標記（4.5 擱置，期中不會出現）。
- 不修改 `docs/`（`docs/ai-usage/` 除外）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 32 隊 | 5 輪、31 場＋季軍賽 | 五欄、欄頭 32 強～決賽；M1～M31；季軍賽卡在決賽下方 | N/A |
| 13 隊 | 4 輪、3 輪空、13 場 | 第一輪只畫實際存在的場次；輪空隊伍直接出現在第二輪並帶「輪空」 | N/A |
| 2～3 隊 | 正取少於 4 隊 | 沒有季軍賽卡 | N/A |
| 待開打 | `scheduled`，隊伍未定 | 標頭「M5 · 10/18（日）13:00」；待定列「M1 勝者」 | N/A |
| 進行中、申訴期 | `live`／`appeal_window`／`appealed` | 標頭換成徽章；顯示比分，兩列都不套勝隊／淘汰樣式；`live` 卡加 live 外框與光環 | N/A |
| 已確認 | `confirmed` | 勝隊粗體、比分 `primary`；淘汰列 `status-eliminated`＋刪除線 | N/A |
| 棄權 | `forfeit`／`double_forfeit` | 沒有比分；棄權的一方（雙方棄權時兩方）帶「棄權」 | N/A |
| 取消資格 | `disqualified` | 被取消資格的一方帶「取消資格」（`destructive`） | N/A |
| 季軍賽取消 | 季軍賽 `voided` | 徽章「已取消」（`muted-foreground`），兩列灰色、沒有比分 | N/A |
| 輪詢有變動 | 新資料與上一次不同 | 只有變動的場次卡 flash 一次；第一次載入不 flash | N/A |
| 輪詢失敗 | 連續 3 次失敗 | 保留舊對戰樹，頁頂顯示連線中斷 banner | 第 1、2 次失敗不顯示；成功一次就消失 |
| 尚未抽籤 | 沒有對戰表 | 「報名截止後抽籤，對戰表會出現在這裡。」＋倒數插槽 | N/A |

## Decisions（2026-10-29 定案）

- **只做第一階段**（使用者選 A）：元件、版面計算、輪詢 hook 與假資料測試；PR 標題「feat: Story 4.6 第一階段：對戰樹元件與輪詢」，sprint-status 維持 `in-progress`。第二階段在 D 的 4.1 API 與 B 的 S2 合併後做：接產生的 client、S3 路由與「對戰表」分頁、尚未抽籤時的報名截止倒數、點卡片到 S4。
- **開發模式預覽頁 `/dev/bracket`**（使用者選 A）：只在 `import.meta.env.DEV` 時顯示，正式 build 顯示 404；第二階段完成後刪除。
- **保留完整 spec**（使用者決定）：粗估約 3,900 tokens，不拆分。
- **不做 code review**（使用者決定，沿用 1.7、1.8）：驗證通過即收尾，等最後統一審查。
- **分支從 `story/1-8` 開出**：要用 1.7 的 `StatusBadge` 與 1.8 的 `EmptyState`；PR 依賴 #10、#11。
- **`match-time.ts` 照抄 D 的版本**：內容與 `origin/story/5-1` 完全相同，合併時不衝突。
- **輪空隊伍的標示**：`bye_a／bye_b` 那一方的隊伍列帶「輪空」；隊伍確定不會出現（沒有隊伍也沒有 `source_*`）時顯示「—」＋「輪空」。
- **手機的固定欄頭**（搜尋框與輪次欄頭合成固定列）隨 4.7 隊伍搜尋延後。

</frozen-after-approval>

## Code Map

- `contracts/competition.md` -- `PublicBracket`、`PublicMatch`（`code`、`round_no`、`slot_no`、`is_third_place`、`team_a/b`、`source_a/b`、`bye_a/b`（原為 `bye_side`，見 Review Triage Log）、`status`、`outcome`、`winner_id`、`wins_a/b`、`scheduled_at`）、`updated_at`。D 的分支 `origin/story/5-5:backend/app/modules/competition/models.py`：`MatchStatus` = scheduled／live／appeal_window／appealed／confirmed／voided；`MatchOutcome` = played／forfeit／double_forfeit／walkover／disqualified。
- `origin/story/5-1:frontend/src/features/competition/match-time.ts` -- D 寫好的 `formatMatchDateTime`（「10/18（日）13:00」）與 `formatClock`（HH:mm）。本 Story 要用：**照抄成完全相同的檔案**（`git show origin/story/5-1:frontend/src/features/competition/match-time.ts`），兩邊合併時內容一致才不會衝突；不要修改它。D 的 `CheckInPanel.tsx` 是「第一階段元件用自己的型別、註明之後改用 client」的寫法參考。
- `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/` -- `DESIGN.md:142-146`（`bracket-row` 字級）、`:162-165`（尺寸）、`:190-227`（卡片、列、mark tag、update-flash token）、`:396-398`、`:427-440`（場次徽章 tone）、`:463-474`（場次卡各狀態）；`EXPERIENCE.md:266-279`（場次狀態）、`:405-442`（對戰樹）、`:24`（輪詢）。`mockups/key-s3-bracket.html` 的桌機 32 隊畫面：絕對定位的卡片＋一個 SVG 畫連接線（直角折線，前後各 14px，`muted-foreground` 55%、寬 1.5），欄的 x 為 0、228、456、684、912。文件與示意圖衝突時以文件為準。
- `frontend/src/index.css` -- `--spacing-bracket-*`（:73-76）、`--text-bracket-row*`（:56-58）、`--radius-xs`（:61）、`--text-overline*`、`status-*`（:119-124）；**沒有** `update-flash` 與任何 `@keyframes`，要新增。
- `frontend/src/components/common/StatusBadge.tsx`（1.7，`tone`、`pulse`）、`EmptyState.tsx`（1.8）、`components/ui/alert.tsx`。本分支從 `story/1-8` 開出，所以這些都在。
- `ARCHITECTURE-SPINE.md:147-154`（AD-14）-- 只用 TanStack Query 輪詢，公開對戰樹 5 秒。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/bracket-types.ts` -- 照約定寫 `PublicBracket`、`PublicMatch`、`MatchStatus`、`MatchOutcome` 型別，檔頭註明「第二階段改用產生的 client 型別後刪除」。
- [x] `frontend/src/features/competition/match-time.ts` -- 照抄 D 的檔案，內容完全相同。
- [x] `frontend/src/features/competition/bracket-layout.ts` -- 純函式：由 `PublicBracket` 算出欄、每張卡的座標、連接線路徑、畫布寬高；每輪的直排位置以 `slot_no` 決定，輪空不佔位置但後一輪的位置照完整的 2 的次方排；季軍賽放在決賽卡下方。
- [x] `frontend/src/features/competition/BracketMatchCard.tsx`、`BracketMarkTag.tsx` -- 場次卡與標記（見 Design Notes）。
- [x] `frontend/src/features/competition/BracketTree.tsx` -- 欄頭、卡片、SVG 連接線、橫向捲動容器；接收 `changedMatchIds` 做 flash。
- [x] `frontend/src/features/competition/use-bracket-polling.ts` -- 輪詢 hook（見 Design Notes）。
- [x] `frontend/src/features/competition/ConnectionLostBanner.tsx`、`BracketPending.tsx` -- 連線中斷 banner；尚未抽籤（`EmptyState`＋`countdown` 插槽）。
- [x] `frontend/src/index.css` -- `update-flash` keyframes 與 utility（`muted` 底、1.5 秒、`motion-reduce` 時不做）。
- [x] `frontend/src/features/competition/bracket-fixtures.ts` -- 假資料產生器（2、3、13、32 隊、各種狀態），給測試與預覽頁共用。
- [x] `frontend/src/routes/dev/bracket.tsx` -- 開發模式預覽頁；`import.meta.env.DEV` 為 false 時顯示 404。
- [x] `frontend/tests/unit/{bracket-layout,bracket-match-card,bracket-tree,use-bracket-polling}.test.ts(x)` -- I/O 矩陣各列、32 隊畫布寬 1112px、編號與待定列、輪詢間隔／背景暫停／3 次失敗／flash 只對變動的卡。

**Acceptance Criteria:**
- Given 32 隊的假資料，when 在 1280px 寬的預覽頁瀏覽，then 五欄完整排開、頁面與對戰樹容器都沒有橫向捲軸。
- Given 16 隊以上的假資料，when 在 375px 寬瀏覽，then 只有對戰樹容器能左右捲動、不縮放，其他元素不跟著捲動。
- Given 預覽頁模擬一次輪詢變動，then 只有變動的卡淡入淡出一次，捲動位置不變。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- **walkover 不顯示比分**：Design Notes 只列 forfeit／double_forfeit／disqualified 不顯示比分；walkover（一方確定沒有隊伍）沒有實際比賽，比照 EXPERIENCE.md〈場次狀態〉「S4 沒有比分」也不顯示。若要顯示 0 再調整 `BracketMatchCard.tsx` 的 `UNSCORED_OUTCOMES`。
- **版面常數**：卡高 67px（兩列 32＋分隔 1＋外框 2）、首張卡上方 19px 給標頭、季軍賽卡距決賽卡底 83px，三者沿用 `mockups/key-s3-bracket.html` 的數值（文件沒有規定）。對戰樹容器有 4px 內距，避免 live 光環被捲動容器裁掉，所以 32 隊容器總寬 1120px（畫布本身 1112px）。
- **`slot_no` 以 D 的 `bracket.py`（origin/story/4-1）為準**：第一輪輪空的位置留空號，所以直排位置直接用 `slot_no - 1` 放進完整的 2 的次方格；季軍賽 `slot_no` 為 2，版面另外放在決賽卡下方。假資料的抽籤結構照抄同一份規則。
- **`useBracketPolling` 多回傳 `isLoading`、`error`**：第二階段 S3 要區分「第一次載入」與「尚未抽籤（404）」；Design Notes 列的四個欄位不變。資料內容沒變時（TanStack structural sharing 保持同一個參照）`changedMatchIds` 沿用同一個 Set，卡片不會再 flash。
- **flash 重播**：同一張卡連續兩次輪詢都有變動時，`BracketTree` 以「id:序號」當 key 讓那張卡重新掛載，動畫才會再跑一次；沒變動的卡不重建，捲動位置不受影響。
- **場次卡用 `<article aria-label>`**：Biome 的 `useSemanticElements` 不接受 `role="group"` 的 div。
- **測試**：TanStack Query 預設以 `setTimeout(0)` 批次通知元件，在 vitest 假時鐘下結果會晚一輪才反映，`use-bracket-polling.test.tsx` 在測試期間把 `notifyManager` 的 scheduler 換成 `queueMicrotask`。
- **正式 build**：`/dev/bracket` 的 chunk 只剩 404 元件（約 0.6 KB），預覽頁與假資料不會進正式 bundle。

## Spec Change Log

## Review Triage Log

**2026-10-31 D 審查（`1578024..25b3eff`）**

D 確認欄位、列舉、`slot_no`、季軍賽的放法與 `bracket.py`、約定一致，3、6、7 隊的連接線與輪空對位正確。約定由 D 修改，前端跟著調整：

- [已修正] 兩方都輪空的場次：輪空多於 P÷4 時（5 隊、9～11 隊、17～23 隊），第二輪會有兩方都來自輪空的場次，`bye_side` 只能標一方。`bracket-types.ts` 改成 `bye_a: boolean`、`bye_b: boolean`（4.1 第二階段的 API 照這個出），假資料、`rowView`、`diffBracketMatches` 跟著改。
- [已修正] 確定沒有隊伍的一方：已確認的 walkover 空缺方原本會顯示「M14 勝者」灰字配「已確認」，看起來像待定；假資料把 source 清成 null，剛好遮住。約定會寫明「確定不會有隊伍時 `source_*` 為 null」；前端另加保險：`status === "confirmed" && outcome === "walkover" && team === null` 也顯示「—」＋「輪空」。
- [已修正，建議] 404 `BRACKET_NOT_FOUND` 原本會計入連續失敗，尚未抽籤的頁面 15 秒後跳「連線中斷」。新增 `BracketNotFoundError`（第二階段的 `queryFn` 收到 404 時拋出），不計失敗、照常輪詢，回傳 `notFound`；404 之後的失敗從 0 開始算。
- [已修正，建議] 補測試：5、9 隊的版面（兩方輪空、沒有連接線）、兩方輪空的卡片、walkover 空缺方仍帶來源的卡片。
- [不處理，記下] 9 隊時第一輪只有一張卡，上方空白約 600px：符合 spec，畫面是否調整留給之後討論。
- **Decisions 第 60 行（凍結區）**：原本寫 `bye_side`，使用者 2026-10-31 改成 `bye_a／bye_b`。
- 驗證（重建 frontend 後）：單元測試 29 個檔案、285 個通過（新增 7 個）；typecheck、biome（132 個檔案）、build 通過；改動的檔案都是 LF。

## Design Notes

**場次卡**：寬 200px，`background` 底、1px `border`、`rounded-md`；標頭在卡片上方一行 `overline`：`code` ＋「 · 」＋ `formatMatchDateTime(scheduled_at)`（只在 `scheduled`），其他狀態接 Status badge：`live` 進行中（live、脈動點）、`appeal_window` 申訴期（appeal）、`appealed` 申訴中（appeal、脈動點）、`confirmed` 已確認（confirmed）、`voided` 已取消（muted）。季軍賽標頭用「季軍賽」取代 `code`。兩列各高 32px、中間 1px 分隔、`bracket-row` 字級；右側等寬比分欄。隊伍為 null 時：有 `source_*` 就顯示它（muted），沒有就顯示「—」＋「輪空」；已確認的 `walkover` 空缺方即使還有 `source_*` 也顯示「—」＋「輪空」。`bye_a`／`bye_b` 為 true 的一方帶「輪空」，兩方可以同時為 true。`forfeit` 時非勝方帶「棄權」、`double_forfeit` 兩方都帶；`disqualified` 時非勝方帶「取消資格」（destructive）；這三種都不顯示比分。

**Bracket mark tag**：1px `currentColor` 外框、`rounded-xs`、`caption` 字級、`px-1`；預設 `muted-foreground`。

**輪詢 hook**：`useBracketPolling({ queryKey, queryFn })` 包 TanStack `useQuery`：`refetchInterval: 5000`、`refetchIntervalInBackground: false`、`refetchOnWindowFocus: true`、`placeholderData: keepPreviousData`、`retry: false`（失敗次數由 hook 自己算）。回傳 `{ bracket, changedMatchIds, connectionLost, lastUpdatedAt }`：與上一份資料逐場比較（`status`、`outcome`、隊伍、比分、`scheduled_at`、`source_*`）得到 `changedMatchIds`；連續失敗 3 次 `connectionLost = true`，成功一次歸零。第二階段只要傳入呼叫產生的 client 的 `queryFn`。

**預覽頁**：切換隊數與場次狀態的控制項，加「模擬變動」「模擬斷線」按鈕，驅動 `useBracketPolling` 的假 `queryFn`。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bun run --filter frontend typecheck` -- expected: 無錯誤。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過（本 Story 不改後端，確認沒有壞掉）。

**Manual checks (if no CLI):**
- 預覽頁 1280px 看 32 隊、375px 看 16 與 32 隊的橫向捲動；切換各種場次狀態；模擬變動看 flash；模擬斷線 3 次看 banner、恢復後消失。
