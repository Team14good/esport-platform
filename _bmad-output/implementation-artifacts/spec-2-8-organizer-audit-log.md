---
title: 'Story 2.8：主辦方查閱操作紀錄'
type: 'feature'
created: '2026-11-21'
status: 'ready-for-dev'
baseline_commit: 'da3d619b73f6202b627e52f1a6978c95d809fa9d'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** 每個 Story 都透過 `core.audit.record()` 寫了操作紀錄，但主辦方沒有任何畫面或 API 可以查閱；發生爭議時拿不出證據，7.2 端對端演練也只能直接查資料表代替（epics.md 7.2 期中版調整）。

**Approach:** tournaments 新增主辦方專用的唯讀分頁 API：確認主辦方身分後以 `core.audit.list_for_tournament()` 取得該賽事紀錄，附上操作者顯示名稱；前端新增 S34 `/organizer/tournaments/$tournamentId/audit-log`（側欄「操作紀錄」），以 Data table 列出操作者、時間、動作、變更前後內容。

## Boundaries & Constraints

**Always:**
- API `GET /organizer/tournaments/{tournament_id}/audit-log?page=`：`Organizer` 依賴＋`authz.ensure_tournament_owner`；不存在 404 `TOURNAMENT_NOT_FOUND`，別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`，不是主辦方身分 403（`Organizer` 既有行為）。
- 查詢只走 `core.audit.list_for_tournament()`，操作者名稱用 `identity_service.get_display_names` 一次查齊；不跨模組查各實體表（AD-9）。
- 回應沿用全專案分頁格式 `{items, total, page, page_size}`，每頁 20 筆，由新到舊（同時間依寫入順序倒序）；`page` 超過總頁數時 `items` 為空、`total` 照實。
- `actor_id` 為 null（worker）時畫面顯示「系統自動」。
- S34 唯讀：沒有任何新增、修改、刪除按鈕；頁碼寫在網址（第 1 頁不寫），超出範圍時以 `replace` 導回最後一頁。
- 介面文字繁中；375 px 沒有橫向捲軸（Data table `< md` 自動變卡片）。

**Never:**
- 不改 `core/audit.py` 既有函式與 `audit_log` 資料表；不新增遷移。
- 不改其他模組寫紀錄的內容或動作名稱。
- 不做篩選、搜尋、匯出、即時輪詢；不翻譯變更內容裡的欄位名稱與 id（Decisions）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 主辦方查閱 | 自己的賽事有 25 筆紀錄 | 第 1 頁 20 筆（最新在前），第 2 頁 5 筆；`total` 25 | — |
| system 操作 | `actor_id` null（例：`tournament.status_changed` 轉開放報名） | API `actor_id`、`actor_display_name` 皆 null；畫面「系統自動」 | — |
| 帳號操作 | `actor_id` 有值 | `actor_display_name` 為該帳號顯示名稱 | — |
| 別人的賽事 | 另一位主辦方 | 403 `TOURNAMENT_OWNER_REQUIRED` | 畫面由賽事後台版面顯示 403 |
| 非主辦方帳號 | 已登入、無主辦方身分 | 403 | 同上 |
| 未登入 | 無 token | 401 | 版面導向登入 |
| 賽事不存在 | 亂數 id | 404 `TOURNAMENT_NOT_FOUND` | 版面顯示 404 |
| 頁碼超出 | `page=99`，只有 1 頁 | API `items` 空、`total` 照實；畫面導回最後一頁 | — |
| 沒有紀錄 | `total` 0（理論上建立賽事就有一筆） | 空狀態「這場賽事還沒有操作紀錄。」 | — |
| 新增類紀錄 | `before` null、`after` 有值 | 變更內容列出 `after` 的每個欄位 | — |
| 修改類紀錄 | `before`、`after` 都有值 | 只列出值不同的欄位：「欄位：前 → 後」 | — |
| 未知動作 | 動作代碼不在對照表 | 顯示原始代碼 | — |
| 讀取失敗 | API 500 | 錯誤訊息＋「重新載入」 | — |

</intent-contract>

## Decisions（2026-11-21，flow-bot 依推薦做法選定，可在 PR 提出異議）

- **由新到舊排列**：AC 只寫「依時間」；發生爭議時要找的通常是最近的操作，第 1 頁放最新的紀錄，與 S14 通知中心一致。`list_for_tournament()` 回傳由舊到新，service 反轉後分頁。
- **伺服器端分頁、沿用 `OrganizerApplicationPage` 格式**：一場 64 隊賽事的紀錄可達上千筆，全部送到前端太重。分頁在 service 對 `list_for_tournament()` 的結果切片（AC 指定用這個函式；資料庫層分頁列為延後項目）。
- **操作者回傳 `actor_display_name`，system 為 null**：「系統自動」是介面文字，由前端顯示，API 不放中文字串。
- **時間顯示到秒**（`2026/11/21 14:05:09`，台北時間）：紀錄是證據，同一分鐘內常有多筆（報到、登錄各局）。
- **動作以繁中對照表顯示**，未知代碼顯示原文；對照表放前端 `features/tournaments/audit-log.ts`，涵蓋目前所有帶 `tournament_id` 的動作。帳號類動作（`account.*`、`school.*`、`game.*`、`organizer_application.*`）不屬於任何賽事，不列入。
- **變更內容顯示欄位差異**：新增類（`before` null）列出 `after` 全部欄位；刪除類（`after` null）列出 `before` 全部欄位；兩邊都有時只列值不同的欄位。欄位名稱與 id 照原始資料顯示（等寬字），物件與陣列以 JSON 呈現；翻譯欄位名稱與把 id 換成名稱需要各模組提供對照，列入延後項目。
- **不顯示「對象」欄**：AC 只列操作者、時間、動作、變更前後；`entity_id` 是 UUID，對主辦方沒有意義。
- **側欄位置**：照 UX-DR7 順序放在「檢舉」之後，圖示用 lucide `ScrollTextIcon`。

## Code Map

- `backend/app/core/audit.py` -- `AuditLogRead`（`actor_id`、`tournament_id`、`action`、`entity_type`、`entity_id`、`before`、`after`、`at`、`id`）、`list_for_tournament(session, tournament_id)` 由舊到新。唯讀使用。
- `backend/app/modules/tournaments/router.py:112-161` -- 主辦方端點寫法：`Organizer` 依賴、`service.get_tournament`＋`authz.ensure_tournament_owner`。新端點接在裁判之後。
- `backend/app/modules/tournaments/service.py:771` `list_referees` -- 用 `identity_service.get_display_names` 補顯示名稱的寫法（不存在的帳號不會出現在結果裡，要用 `.get`）。
- `backend/app/modules/tournaments/models.py:485` `RefereeRead` -- API schema 放這裡；分頁格式照 `identity/models.py:453` `OrganizerApplicationPage`、`PAGE_SIZE`／`MAX_PAGE`（`identity/models.py:41-43`）。
- `backend/app/modules/notifications/router.py:29` -- `page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1` 的寫法。
- `backend/tests/tournaments/test_referees.py`、`test_tournaments.py` -- 主辦方 API 測試的 fixture 與建立賽事的寫法。
- `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- 補新端點。
- `frontend/src/features/tournaments/organizer-nav.ts` `tournamentNav` -- 新增「操作紀錄」。`frontend/tests/unit/organizer-tournaments.test.tsx` 有側欄項目的預期清單，要補。
- `frontend/src/routes/organizer/tournaments/$tournamentId/matches.tsx` -- 子頁＋網址頁碼的寫法（`parsePage` 來自 `features/identity/admin-applications`）；`features/competition/OrganizerMatchesPage.tsx:177` 頁碼超出時 `replace` 修正。
- `frontend/src/components/common/DataTable.tsx` -- `DataTable`（`columns`、`rows`、`page`、`pageSize`、`total`、`onPageChange`、`empty`、`label`）。
- `frontend/src/features/notifications/queries.ts:97` -- 分頁查詢 `placeholderData: keepPreviousData`。
- `frontend/src/features/disputes/ReportsPage.tsx` -- 主辦方 Data table 頁的錯誤處理（`getErrorMessage(parseApiError())`＋「重新載入」）。
- `frontend/tests/unit/organizer-reports.test.tsx`、`auth-fixtures.ts`、`helpers.ts` -- 主辦方後台頁的單元測試寫法。
- `frontend/tests/e2e/support/organizer.ts` `createOrganizer`、`tournament.spec.ts` 的 `createTournament` -- e2e 建立主辦方與賽事。
- `frontend/src/routeTree.gen.ts`、`frontend/src/client/` -- 不手改，用腳本產生。

## Tasks & Acceptance

**Execution:**
- [ ] `backend/app/modules/tournaments/{models,service,router}.py` -- `AuditLogEntry`（`id`、`at`、`actor_id`、`actor_display_name`、`action`、`entity_type`、`entity_id`、`before`、`after`）、`AuditLogPage`；`list_audit_log(session, *, tournament_id, page)`；`GET /organizer/tournaments/{tournament_id}/audit-log` -- I/O 矩陣的後端列
- [ ] `backend/tests/tournaments/test_audit_log.py` -- 排序（含同一時間依寫入順序）、分頁與超出頁碼、system 與帳號操作者、403（別人的賽事、非主辦方）、401、404、不含其他賽事與帳號類紀錄
- [ ] `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- 新端點；`bash scripts/generate-client.sh` 重新產生 client
- [ ] `frontend/src/features/tournaments/audit-log.ts` -- 查詢、動作對照表、時間格式（到秒）、變更內容差異計算
- [ ] `frontend/src/features/tournaments/AuditLogPage.tsx`、`routes/organizer/tournaments/$tournamentId/audit-log.tsx`、`organizer-nav.ts` -- S34
- [ ] `frontend/tests/unit/audit-log.test.tsx` -- I/O 矩陣的畫面列與差異計算；補 `organizer-tournaments.test.tsx` 側欄斷言
- [ ] `frontend/tests/e2e/audit-log.spec.ts` -- 主辦方建立賽事後開 S34 看到「建立賽事」那一筆（desktop、mobile-375 截圖）
- [ ] `_bmad-output/implementation-artifacts/deferred-work.md` -- 新增：資料庫層分頁；欄位名稱與 id 的翻譯

**Acceptance Criteria:**
- Given 主辦方建立賽事並讓 worker 轉為開放報名，when 在側欄點「操作紀錄」，then S34 依新到舊列出「賽事狀態變更」（操作者「系統自動」）與「建立賽事」（操作者為主辦方顯示名稱），且沒有任何編輯操作
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose exec -T backend bash scripts/test.sh`、`bash scripts/lint.sh` -- 全部通過
- `bash scripts/generate-client.sh` 後 `git diff --exit-code frontend/src/client` -- 一致
- 前端 build、typecheck、`bunx biome check`、`bunx vitest run tests/unit` -- 全部通過
- `docker compose --profile e2e` 跑 `audit-log.spec.ts`（desktop、mobile-375） -- 通過並存截圖
