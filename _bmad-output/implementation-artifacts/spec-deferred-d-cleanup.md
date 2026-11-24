---
title: 'competition 延後項目整理：裁判名單查詢共用、場次裁判欄索引'
type: 'chore'
created: '2026-11-25'
status: 'done'
baseline_commit: '116ed0bd13962bd2d47c0bacdf058850079929e5'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** deferred-work 有兩項屬於 D（competition）的待辦：(1)（中）S30 的 `tournamentRefereesQueryOptions` 與 S31 的 `refereesQueryOptions` 用同一個 query key 各寫一份 `queryFn`、`retry`，誰先掛載就用誰的設定，之後只改一邊會互相污染快取；(2) `Match.referee_account_id` 沒有索引，`GET /me/referee/matches` 會掃整張場次表。

**Approach:** (1) competition 改為匯入 tournaments 的 `refereesQueryOptions`，刪掉自己的定義（依賴方向 competition → tournaments，不改 tournaments 的檔案）；(2) 模型加 `index=True`，另開一支 Alembic 遷移建立索引。完成後刪除這兩個 deferred 項目。擁有者 2026-11-24 指示「做我們的事情就好」，並授權自動採建議。

**Decisions:**
- 第三項「賽事取消後 S30–S33 仍可操作」（spec-2-6）查證 competition 部分：改時間（`_RESCHEDULABLE_TOURNAMENT`）與指派裁判（`_ASSIGNABLE_TOURNAMENT`）只接受賽程已公布、進行中，已取消回 409，既有測試 `test_tournament_not_reschedulable`、`test_tournament_not_assignable` 都參數化涵蓋 CANCELLED；S30 依 `reschedule.can_reschedule`、`can_assign_referee` 停用動作。competition 不需改。該項仍含 S31–S33（他人模組），不刪除、不修改，只在 PR 說明回報。
- 兩項合在同一個 PR：都屬 D、改動很小、彼此不耦合（擁有者授權自動採建議）。

## Boundaries & Constraints

**Always:** 只改 competition 模組（前端 `features/competition/`、後端 `competition/models.py`）與新增遷移；遷移 `down_revision` 接目前唯一的 head `a7d3e9b2c6f4`，downgrade 刪除索引；`tests/test_migrations.py` 必須通過（模型與遷移一致）。

**Never:** 不改 tournaments 的 `referee-queries.ts`（它的註解提到 `tournamentRefereesQueryOptions`，過時的部分在 PR 說明提給負責人）；不改 S31–S33；不改其他 deferred 項目的內容。

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/organizer-matches-queries.ts:46-57` -- 刪除 `tournamentRefereesQueryOptions`；`TournamentsService` import 若不再使用一併移除。
- `frontend/src/features/competition/OrganizerMatchesPage.tsx:21,145` -- 改從 `@/features/tournaments/referee-queries` 匯入 `refereesQueryOptions`。
- `frontend/src/features/tournaments/referee-queries.ts:62-76` -- 只讀：`refereesQueryOptions`，`shouldRetry` 與 competition 版本相同（403、業務錯誤不重試）。
- `backend/app/modules/competition/models.py:121` -- `referee_account_id` 加 `index=True`。
- `backend/app/alembic/versions/` -- 新增 `<rev>_deferred_match_referee_index.py`，`op.create_index(op.f("ix_match_referee_account_id"), "match", ["referee_account_id"])`；索引名稱依 SQLModel 命名慣例，參考同檔 `bracket_id` 的既有索引遷移（`f7a3c9e1b5d2_story_4_1_bracket_and_match.py`）。
- `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 spec-2-7（裁判名單查詢）與 spec-4-4（`referee_account_id` 索引）兩項。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/competition/organizer-matches-queries.ts`、`OrganizerMatchesPage.tsx` -- 改用 `refereesQueryOptions`、刪除重複定義 -- 單一定義來源
- [x] `backend/app/modules/competition/models.py` 與新遷移 -- 加索引 -- 查詢裁判場次不掃全表
- [x] `deferred-work.md` -- 刪除兩項 -- 已處理

**Acceptance Criteria:**
- Given 主辦方開 S30，when 裁判名單載入，then 顯示與改前相同，且 `grep tournamentRefereesQueryOptions frontend/src` 只剩 tournaments 檔案的註解。
- Given 從空資料庫升級到 head，when 檢查 `match` 資料表，then 有 `ix_match_referee_account_id` 索引，`tests/test_migrations.py` 通過，且 downgrade 一版後索引消失。

## Implementation Notes

- 前端：`organizer-matches-queries.ts` 刪除 `tournamentRefereesQueryOptions` 與不再用的 `TournamentsService` import；`OrganizerMatchesPage.tsx` 改匯入 tournaments 的 `refereesQueryOptions`（`queryFn`、`retry` 規則相同）。
- 後端：`Match.referee_account_id` 加 `index=True`；遷移 `d4b8f2a6c1e9_deferred_match_referee_index.py`（接 `a7d3e9b2c6f4`）。
- 刪除 deferred 兩項時，第一版連同章節標題 `## Deferred from: spec-4-4-s13-referee-matches.md` 一起刪掉，讓底下 S27、3.6 兩個別人的項目變成歸在 spec-7-1 底下；審查發現後補回標題。
- 新增兩個 deferred 項目：tournaments 註解過時（交給負責人）、spec-2-6 的 S30 部分查證結果。
- 驗證（實際輸出）：
  - `pytest -q tests/test_migrations.py tests/competition/test_referee_matches.py` → 26 passed。
  - 遷移來回：head 時 `pg_indexes` 有 `ix_match_referee_account_id`；`alembic downgrade -1` 後查無；`upgrade head` 後又出現。
  - frontend 容器 `bunx vitest run tests/unit/referee-pages.test.tsx tests/unit/organizer-matches` → 2 files、49 passed；`bunx tsc --noEmit`、`bunx biome check src` 通過。
  - spec 列的 `tests/unit/referees*.test.tsx` 不存在，實際 S31 測試是 `referee-pages.test.tsx`，已改跑它。
  - 沒跑 `EXPLAIN`：本機資料量小，planner 選擇不代表正式環境；索引存在已由 `pg_indexes` 確認。

## Spec Change Log

## Review Triage Log

- ECH／Blind：刪 deferred 項目時連章節標題一起刪，別人的兩項出處被改錯 — medium，patch（補回標題）。
- ECH：`CREATE INDEX` 沒用 `CONCURRENTLY`，大表時會擋寫入 — low，reject：`match` 每場賽事最多數十列，其他遷移也都是一般建立索引。
- VG／Blind：downgrade 沒有自動化測試 — low，reject：repo 所有遷移都沒有降級測試（既有慣例），本次已手動來回驗證並記錄於 Implementation Notes。
- Blind：Verification 的 `referees*` 路徑對不到檔案 — reject（修法是改本 spec）；已改跑 `referee-pages.test.tsx`。
- Blind：沒有測試防止重複定義再出現 — low，reject：要多一個跨頁共用快取的測試，日常不會遇到。
- Blind：Verification 沒附實際輸出 — reject（修法是改本 spec）；已補在 Implementation Notes。
- Blind：tournaments 註解指向已刪除的函式 — low，defer（新增 deferred 項目交給負責人，competition 不改對方檔案）。
- Blind：spec-2-6 的 S30 查證結果沒留在 deferred-work — low，patch（新增一項，不改舊項目）。
- Blind：缺 AI 使用紀錄 — patch（step-05 收尾時新增）。
- Blind：沒寫為什麼不用 `(referee_account_id, scheduled_at)` 複合索引 — low，reject：每位裁判的場次很少，排序成本可忽略。
- Blind：spec `context` 為空 — reject（修法是改本 spec）。

## Verification

**Commands:**
- `docker compose exec -T backend python -m pytest -q tests/test_migrations.py tests/competition/test_referee_matches.py` -- expected: 全部 passed
- frontend 容器 `bunx vitest run tests/unit/organizer-matches*.test.tsx tests/unit/referees*.test.tsx`、`bunx tsc --noEmit`、`bunx biome check src` -- expected: 通過
- `EXPLAIN` 查 `select * from match where referee_account_id = ...` -- expected: 使用 `ix_match_referee_account_id`（資料少時 planner 可能仍選 seq scan，可 `set enable_seqscan=off` 確認索引可用）
