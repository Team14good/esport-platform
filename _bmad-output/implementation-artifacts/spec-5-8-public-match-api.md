---
title: '公開單場 API（5.8 後端，competition 提供）'
type: 'feature'
created: '2026-10-31'
status: 'in-progress'
baseline_commit: 'e0fe27ee168dfa265aa27ac9de0cf8eb2df48cfc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-draw-backend.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A 的 5.8 S4 場次頁（#12）目前只能在開發模式用假資料，正式 build 一律 404。A 在 5.8 的 deferred-work 請 D 在 competition 提供公開的單場 API，形狀照 `frontend/src/features/competition/match-types.ts` 的 `PublicMatchDetail`。

**Approach:** 新增 `GET /api/v1/tournaments/{tournament_id}/matches/{match_id}`（未登入可看），回傳 `PublicMatchDetail`：`PublicMatch` 的欄位，加上賽事 id 與名稱、遊戲名、本輪 BO、比分型態、輪次名稱、已登錄的局、同輪其他場次、申訴期截止時間、`updated_at`。逐局資料表屬於 5.3 第二階段，還沒建，`games` 先一律回空陣列，5.3 建表後填入、欄位形狀不變。分支疊在 5.5 第二階段（#20）上。使用者 2026-10-31 指示「先做能做的」。

## Boundaries & Constraints

**Always:**
- 回傳形狀照 A 的 `PublicMatchDetail`（欄位名稱一字不差）：`PublicMatch` 全部欄位＋`tournament {id, name}`、`game_name`、`best_of`、`score_type`、`round_name`、`games: list[PublicGame]`、`same_round: list[PublicMatch]`、`appeal_deadline`、`updated_at`。`PublicGame` 為 `{game_no, winner_side: "a"|"b", score_a, score_b}`。
- `PublicMatch` 的組法（隊名、待定字串、輪空、空缺方 null）和公開對戰樹完全相同，共用同一段程式，不另寫一份。
- `best_of` 用 `tournaments_service.bo_for_round`；`game_name`、`score_type` 取自 `TournamentRead`；`round_name` 用 `bracket.round_name`，季軍賽寫「季軍賽」。
- `same_round`：同一 `round_no` 的其他場次（不含自己），依 `slot_no`、季軍賽排在最後；季軍賽與決賽同輪，會互相列出。
- `appeal_deadline` 只在申訴期、申訴中有值，其他狀態一律 null。
- `updated_at`＝這場與同輪其他場次 `updated_at` 的最大值（同輪場次變動也要讓 S4 重抓後 flash）。
- 場次不屬於網址上的賽事、賽事不存在、場次不存在、尚未抽籤，一律 404 `MATCH_NOT_FOUND`（不透露哪一種）。
- AD-19：公開 schema 不含 Email、學校、裁判帳號、段位截圖鍵值。

**Ask First:**
- 要改 tournaments、registration 的既有程式，或改 `PublicMatch`／`PublicBracket` 既有欄位。

**Never:**
- 不建 MatchGame 表（5.3 第二階段）；不做登錄比分、報到的 API。
- 不改 A 的前端檔案（換成產生的 client 是 A 的工作）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一輪場次 | 8 隊抽籤後 GET M1 | 200；兩隊隊名、`round_name`「8 強」、`best_of` 為賽事 BO、`games` 為 `[]`、`same_round` 為 M2～M4、`appeal_deadline` null | N/A |
| 待定場次 | GET M5 | 兩方 `team_*` null、`source_*` 為「M1 勝者」「M2 勝者」 | N/A |
| 季軍賽 | 8 隊 GET 季軍賽 | `round_name`「季軍賽」；`same_round` 只有決賽 | N/A |
| 決賽 | 8 隊 GET 決賽 | `round_name`「決賽」；`same_round` 只有季軍賽 | N/A |
| 2 隊賽事 | 只有決賽 | `same_round` 為 `[]` | N/A |
| 申訴期 | 場次在申訴期 | `appeal_deadline` 為場次上的值 | N/A |
| 已確認 | 場次已確認 | `appeal_deadline` null | N/A |
| 同輪有變動 | M2 確認後 GET M1 | `updated_at` 跟著前進 | N/A |
| 場次不屬於這個賽事 | 別的賽事 id | — | 404 `MATCH_NOT_FOUND` |
| 不存在 | 隨機 id、賽事未抽籤 | — | 404 `MATCH_NOT_FOUND` |
| 未登入 | 無 token | 200 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/features/competition/match-types.ts`（在 A 的 `story/5-8`，commit `24a8fce`）-- 回傳形狀的來源
- `backend/app/modules/competition/service.py` -- `get_public_bracket` 裡組 `PublicMatch` 的程式（抽出共用）、`get_match`
- `backend/app/modules/competition/models.py` -- `PublicMatch`、`PublicBracket`
- `backend/app/modules/competition/router.py` -- 公開 GET 的寫法（`/tournaments/{id}/bracket`）
- `backend/app/modules/competition/bracket.py` -- `round_name`
- `backend/app/modules/tournaments/service.py` -- `get_tournament`、`bo_for_round`
- `backend/tests/competition/test_bracket_api.py`、`conftest.py` -- 抽籤替身與公開 API 測試寫法

## Tasks & Acceptance

**Execution:**
- [ ] `competition/models.py` -- `PublicGame`、`PublicTournamentRef`、`PublicMatchDetail`
- [ ] `competition/service.py` -- 抽出組 `PublicMatch` 的共用函式；新增 `get_public_match(session, *, tournament_id, match_id) -> PublicMatchDetail`
- [ ] `competition/router.py` -- `GET /tournaments/{tournament_id}/matches/{match_id}`
- [ ] `backend/tests/competition/test_match_api.py` -- I/O 矩陣每一列；回傳的 JSON 鍵集合與 `PublicMatchDetail` 完全相同
- [ ] 重新產生 `frontend/src/client`
- [ ] `contracts/competition.md` -- HTTP API 表與 schema 補上這支 API

**Acceptance Criteria:**
- Given 8 隊抽籤後，when 未登入 GET 每一場，then 都回 200，`PublicMatch` 部分與公開對戰樹裡同一場完全相同，`same_round` 與 `round_name` 符合 I/O 矩陣。
- Given 回傳的 JSON，when 比對 A 的 `PublicMatchDetail` 欄位，then 鍵集合完全相同，沒有 Email、學校、裁判或截圖欄位。
- Given 場次與網址上的賽事不符或不存在，when GET，then 404 `MATCH_NOT_FOUND`。

## Verification

- 從主 repo 目錄：`MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "<worktree>/backend/app:/app/backend/app" -v "<worktree>/backend/tests:/app/backend/tests" backend bash scripts/test.sh` -- 全部通過
- `bash scripts/lint.sh` -- 通過

## Implementation Notes

## Spec Change Log

## Review Triage Log
