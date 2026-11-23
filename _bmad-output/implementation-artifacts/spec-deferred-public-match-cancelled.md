---
title: '賽事取消後的公開場次頁'
type: 'bugfix'
created: '2026-11-23'
status: 'done'
baseline_commit: '2679e45298cc87007a1fc35177199b0738cd858e'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 2.6 取消賽事後，場次狀態不變、worker 也不再判棄權或確認申訴，但公開單場 API `get_public_match` 仍回傳 `appeal_deadline`、`forfeit_deadline`，S4 場次頁照樣顯示申訴期與報到倒數；倒數歸零後每 5 秒重抓一次、永遠等不到新狀態。場次頁也看不出賽事已取消（對戰樹、正取名單頁已有「此賽事已取消」橫幅）。

**Approach:** `get_public_match` 在賽事已取消時兩個期限一律回 `None`，並在回應帶出賽事狀態；S4 場次頁依此顯示與對戰樹相同的取消橫幅。

## Boundaries & Constraints

**Always:** 期限判斷放在後端，前端只依回應有沒有值決定倒數（沿用現有寫法）；橫幅文字共用 `CANCELLED_BANNER_TEXT`。新增欄位後重新產生 `frontend/src/client`。

**Never:** 不改場次狀態、不改 worker、不改 2.6 的取消流程；不改其他組員的既有函式；不動 `PublicTournamentRef`（裁判頁也在用）；不做遷移。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 取消後申訴期 | 賽事 cancelled、場次 `appeal_window` 或 `appealed` | `appeal_deadline`、`appeal_started_at` 為 null；`tournament_status` = `cancelled` | N/A |
| 取消後待開打 | 賽事 cancelled、場次 `scheduled` 且兩隊確定 | `forfeit_deadline` 為 null | N/A |
| 未取消 | 賽事 in_progress、場次 `appeal_window` | 期限照舊回傳，`tournament_status` = `in_progress` | N/A |
| 場次頁 | 回應 `tournament_status` = `cancelled` | 頁首顯示 destructive 橫幅「此賽事已取消」，沒有申訴倒數與報到倒數 | N/A |
| 場次頁未取消 | 其他狀態 | 不顯示取消橫幅 | N/A |

## Decisions

- （擁有者 2026-11-23，照建議）取消後申訴期與報到兩種倒數都不顯示：後端回 null，停止歸零後的無止盡重抓。
- （擁有者 2026-11-23，照建議）場次頁加上與對戰樹、正取名單頁相同的 destructive 橫幅「此賽事已取消」。
- （擁有者 2026-11-23，照建議）場次狀態標籤維持原狀態（例如「申訴期」「待開打」），由橫幅說明賽事已取消，與 2.6「場次狀態不變」一致。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/service.py:659` `get_public_match` -- 已取得 `tournament`；`appeal_deadline` 依 `_APPEAL_STATUSES`、`forfeit_deadline` 依 `SCHEDULED` 判斷，在這兩處加賽事已取消的條件，並填 `tournament_status`。
- `backend/app/modules/competition/models.py:486` `PublicMatchDetail` -- 新增 `tournament_status: TournamentStatus`（`PublicTournamentRef` 不動）。
- `backend/tests/competition/test_match_api.py` -- 公開單場 API 測試範本；取消賽事的寫法參考 `backend/tests/worker/test_cancelled_tournament_skipped.py`。
- `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx` -- `MatchPage` 目前只有連線中斷橫幅；仿 `TournamentBracketPage.tsx:123` 用 `PageBannerSlot` 加取消橫幅。
- `frontend/src/features/tournaments/TournamentPage.tsx:16` `CANCELLED_BANNER_TEXT` -- 共用文字。
- `frontend/src/features/competition/match-fixtures.ts` -- 測試 fixture 要補新欄位。
- `frontend/tests/unit/match-route.test.tsx` -- 場次頁單元測試。
- 已確認不需改：`list_my_next_matches` 已略過取消賽事；申訴提出（disputes `_ENDED_TOURNAMENT`）、比分（`ensure_accepting_scores`）、報到後端已拒絕取消賽事。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/models.py` -- `PublicMatchDetail` 加 `tournament_status` -- 前端判斷橫幅
- [x] `backend/app/modules/competition/service.py` -- `get_public_match` 取消時期限回 None、填狀態 -- 停止無效倒數
- [x] `backend/tests/competition/test_match_api.py` -- I/O 前三列各一個測試
- [x] `scripts/generate-client.sh` -- 重新產生 client
- [x] `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx` -- 取消橫幅
- [x] `frontend/src/features/competition/match-fixtures.ts`、`frontend/tests/unit/match-route.test.tsx` -- 補欄位與 I/O 後兩列測試
- [x] `backend/tests/traceability.yaml`、`_bmad-output/implementation-artifacts/deferred-work.md` -- 登錄測試；刪除第 47–48 行項目

**Acceptance Criteria:**
- Given 已取消賽事中停在申訴期的場次，when 觀眾開 S4 場次頁，then 看到「此賽事已取消」橫幅、看不到申訴倒數，且頁面不會每 5 秒重抓期限。

## Implementation Notes

- I/O 第三列寫的 `in_progress` 不是實際的 enum 值；`TournamentStatus` 進行中為 `ongoing`，測試只斷言「不是 cancelled」，fixture 用 `ongoing`。
- 場次頁的連線中斷橫幅改經 `PageBannerSlot`（`connectionLostText`），與對戰樹頁相同；`ConnectionLostBanner` 元件之後只剩單元測試使用。
- 前端單元測試 fixture 有兩份（`features/competition/match-fixtures.ts`、`tests/unit/match-detail-fixture.ts`），都補上 `tournament_status`。
- 審查後修正：`MatchCheckIn.tsx` 在賽事已取消時把 `isScheduled` 視為 false，不顯示「報到開放」「距預定開始」倒數與報到按鈕（這兩段倒數由 `opens_at`、`scheduled_at` 計算，後端把 `forfeit_deadline` 設為 null 擋不到）。這偏離 Boundaries「前端只依回應有沒有值決定倒數」的字面，但為了符合 Decisions 第 1 項「兩種倒數都不顯示」；frozen 區塊未改，由擁有者決定是否修訂。拿掉此修正時新測試失敗（1 failed），放回後通過。
- 驗證：`pytest tests/competition/test_match_api.py tests/test_traceability.py` 21 passed；vitest 全套 1187 passed；tsc、biome、ruff、mypy 通過。

## Spec Change Log

## Review Triage Log

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Edge、Gap、Blind | 已取消賽事的待開打場次仍顯示「報到開放」「距預定開始」倒數與停用的報到按鈕（`MatchCheckIn.tsx` 由 `opens_at`、`scheduled_at` 計算，不看 `forfeit_deadline`） | medium：讀碼確認，拿掉修正後新測試失敗 | patch |
| 2 | Edge、Gap | 前端缺「取消＋待開打」測試 | medium：與 1 同源 | patch（新增測試） |
| 3 | Edge | 隊長看到「目前無法報到，請重新整理頁面」 | medium：與 1 同源，按鈕隱藏後不再顯示 | patch（併入 1） |
| 4 | Blind | 前端取消測試自己把期限設為 null，證明不了前端行為 | low：期限由後端決定是 spec 設計，後端測試涵蓋；改測試名稱說明 | patch |
| 5 | Blind | `test_uncancelled_tournament_keeps_deadlines` 只斷言「不是 cancelled」 | low | patch（改斷言 `published`） |
| 6 | Edge、Blind | 取消橫幅會蓋掉連線中斷橫幅 | false：`PageBannerSlot` 只顯示最重要的一則，對戰樹頁相同 | reject |
| 7 | Blind | 已取消賽事仍每 5 秒輪詢 | low：要加分支，日常影響小 | reject |
| 8 | Edge、Blind | `ConnectionLostBanner` 元件只剩測試使用 | low：對戰樹頁早已改用 `connectionLostText`，非本次造成 | reject |
| 9 | Blind | 對戰樹 API 仍回傳原始期限 | false：對戰樹卡片不顯示倒數 | reject |
| 10 | Blind | 從頁面模組 import `CANCELLED_BANNER_TEXT` | low：沿用既有寫法 | reject |
| 11 | Blind | 後端取消測試沒有交叉斷言其他欄位 | low：I/O 每列各有斷言 | reject |
| 12 | Blind | 缺 AI 使用紀錄 | 開 PR 前補 | 流程 |

## Verification

**Commands:**
- `docker compose exec -T backend pytest tests/competition/test_match_api.py -q` -- expected: 全部通過
- `cd frontend && bun run test -- match-route` -- expected: 全部通過
- CI（後端全套、前端全套、client 一致性檢查）-- expected: 綠
