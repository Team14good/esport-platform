---
title: 'Story 5.5、5.6（第二階段）：確認結果、晉級推進、申訴期滿自動確認與賽事結束'
type: 'feature'
created: '2026-10-31'
status: 'in-progress'
baseline_commit: 'f83895594672f0eb43600e9e80de23fdb5f83f93'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-5-5-progression-rules.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-1-draw-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 5.5 第一階段的 `progression.py` 只算出「確認一場後要做哪些變更」，沒有寫進資料庫；申訴期滿也沒有 worker 自動確認，賽事走不到「已結束」。A 的 5.2（判棄權，#16）與 B 的 6.x（申訴更正）都要呼叫 competition 的 `confirm_match`／`advance`。

**Approach:** 在 competition service 實作 `confirm_match`、`advance`、`confirm_walkover`、`auto_confirm_expired` 與 `get_podium`：從資料表組出 `MatchState` 交給 `progression.advance`，在同一交易內依序套用回傳的變更（填位、輪空確認、季軍賽取消、起算棄權期限、賽事結束）。新增申訴期滿自動確認的 worker 工作。分支疊在 4.1 第二階段（#19）上，範圍由使用者 2026-10-31 同意（「繼續」，依建議順序先做 5.5）。

## Boundaries & Constraints

**Always:**
- 晉級規則（誰進哪場、輪空、季軍賽取消、名次）全部取自 `progression.advance`／`podium`，service 不重寫規則；一次呼叫回傳的變更必須在同一交易內全部套用。
- `confirm_match(session, *, match, outcome, winner_id, actor_id)`：寫入 `outcome`、`winner_id`、`confirmed_at`，經 `transition_match` 轉為已確認，接著呼叫 `advance`。`actor_id=None` 表示系統。
- `advance`：鎖的順序依 AD-6——先 `lock_tournament`，再依 id 遞增鎖住這個對戰表的全部場次，用鎖住後的資料組 `MatchState`。
- 變更的套用：`FillSlot` 填入隊伍；`ConfirmWalkover` 以 `walkover` 確認（經 `transition_match`），並在同一次推進中繼續處理；`VoidMatch` 轉為 `voided`；`StartForfeitClock` 呼叫 `start_forfeit_clock`；`TournamentFinished` 讓賽事轉為 `finished`——賽事還是 `published` 時先轉 `ongoing` 再轉 `finished`，已經是 `finished` 時不再轉（progression 對決賽重複呼叫會再回傳一次）。
- 申訴期滿自動確認：worker 工作每次處理一場「申訴期、`appeal_deadline <= now`」的場次；鎖住後重新檢查狀態與期限，沿用場次上已寫的 `outcome`、`winner_id` 呼叫 `confirm_match`（操作者為系統）。賽事已取消或已結束時略過（AD-7）。重複執行沒有副作用。
- 操作紀錄：每場確認 `match.confirmed`（含 outcome、勝隊）；賽事結束另記 `tournament.podium`（冠、亞、季）。事件：每場確認發 `MatchResultConfirmed`（`match_id`、`winner_id`）；填位後下一場兩隊都確定時發 `MatchOpponentsDecided`（`match_id`），讓 notifications 通知兩隊隊長（期中只發不通知）。
- 公開對戰樹 `PublicBracket` 加 `podium`（冠、亞、季，各為 `PublicTeamRef | None`；賽事未結束時整個為 null）。
- 時間一律 `clock.now()`；測試用 `frozen_clock` 推進，不等待真實時間（AD-13）。

**Ask First:**
- 要改 tournaments、registration 或 5.2（`forfeit*.py`）的既有程式。
- 要新增這份 spec 以外的公開函式或 API。

**Never:**
- 不做 HTTP API（確認由 worker 與其他模組的 service 呼叫）；不做 S4、S2 畫面。
- 不做晉級後的裁判衝突檢查（4.4 指派裁判還沒有，`referee_account_id` 目前一律為空；留給 4.4）。
- 不做取消資格的頂替（6.6）、退賽遞補（4.5 擱置）。
- 不在 service 或 repository commit；不讀其他模組的資料表。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 一般晉級 | 8 隊，M1 申訴期、期限已過、勝隊 A | worker 確認 M1，`confirmed_at`＝現在；A 填入 M5 對應位置；M5 另一方未定時沒有棄權期限 | N/A |
| 下一場湊齊 | M1、M2 都確認 | M5 兩隊確定，棄權期限＝max(預定時間, 現在)＋棄權時限；發 `MatchOpponentsDecided` | N/A |
| 申訴期未滿 | `appeal_deadline > now` | 不處理，勝隊不出現在下一輪 | N/A |
| 準決賽 | 8 隊，M5 確認 | 勝隊進決賽，敗隊進季軍賽 | N/A |
| 雙方棄權 | M1 `double_forfeit` 期滿 | M1 確認、無勝隊；M5 的對手以 `walkover` 確認並繼續推進 | N/A |
| 準決賽雙方棄權 | M5 `double_forfeit` 期滿 | 另一場準決賽勝隊以輪空贏得決賽、成為冠軍；季軍賽 `voided`；另一場準決賽敗隊為亞軍、季軍從缺；賽事 `finished` | N/A |
| 賽事結束 | 決賽與季軍賽都已確認 | 賽事 `ongoing` → `finished`；操作紀錄 `tournament.podium`；公開對戰樹顯示名次 | N/A |
| 賽事仍為已公布 | 決賽確定時賽事是 `published` | 依序轉 `ongoing`、`finished` | N/A |
| 決賽取消資格 | 決賽以 `disqualified` 確認 | 亞軍從缺（沿用 5.5 第一階段的決定） | N/A |
| 重複執行 | 同一場被 worker 處理兩次 | 第二次看到已確認，不做任何事 | N/A |
| 賽事已取消或已結束 | 申訴期場次所屬賽事 `cancelled`／`finished` | worker 略過，不確認 | N/A |
| 非法確認 | 對已確認或待開打的場次呼叫 `confirm_match` | 不改任何資料 | 409 `MATCH_INVALID_TRANSITION` |
| 2 隊賽事 | 只有決賽 | 決賽確認後直接結束，季軍從缺 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/progression.py` -- `MatchState`、`advance(plan, states, code) -> list[Change]`、`podium(plan, states)`、五種 Change
- `backend/app/modules/competition/service.py` -- #19 的 `lock_match`、`transition_match`、`start_forfeit_clock`、`get_public_bracket`、`_MATCH_TRANSITIONS`
- `backend/app/modules/competition/models.py` -- `Bracket`（有 `team_count`）、`Match`（沒有 `confirmed_at`，本 Story 新增）、`PublicBracket`
- `backend/app/modules/competition/repository.py` -- 新增「依 id 遞增鎖住整個對戰表的場次」「找一場申訴期滿的場次」
- `backend/app/modules/tournaments/service.py` -- `lock_tournament`、`transition_tournament`、`get_tournament`
- `backend/app/worker/jobs.py` -- `JOBS` 清單，新增自動確認工作（只新增一行與一個函式）；`open_registrations` 是「找候選 → 鎖 → 重新檢查」的寫法參考
- `backend/app/alembic/versions/f7a3c9e1b5d2_story_4_1_bracket_and_match.py` -- 新遷移的 `down_revision`
- `backend/tests/competition/conftest.py`、`test_draw.py` -- 抽籤替身與建資料的方式
- `backend/tests/worker/` -- worker 工作測試寫法
- `_bmad-output/implementation-artifacts/contracts/competition.md` -- `confirm_match`、`advance`、`confirm_walkover` 的簽名；事件表

## Tasks & Acceptance

**Execution:**
- [ ] `competition/models.py` 與新遷移 -- `Match.confirmed_at`（可為空）；`PublicPodium`（`champion`、`runner_up`、`third_place`）與 `PublicBracket.podium`；事件 `MatchResultConfirmed`、`MatchOpponentsDecided`
- [ ] `competition/repository.py` -- 依 id 遞增鎖住對戰表全部場次；找下一場申訴期滿的場次 id
- [ ] `competition/service.py` -- `confirm_match`、`advance`、`confirm_walkover`、`auto_confirm_expired`、`get_podium`；`get_public_bracket` 帶入名次
- [ ] `backend/app/worker/jobs.py` -- 新增 `confirm_expired_appeals` 並加進 `JOBS`
- [ ] `backend/tests/competition/test_confirm_advance.py`、`backend/tests/worker/` 對應測試 -- I/O 矩陣每一列；2、3、8、13 隊從抽籤一路確認到賽事結束的整合測試
- [ ] `contracts/competition.md` -- 補 `auto_confirm_expired`、`get_podium`、`PublicBracket.podium`、兩個事件

**Acceptance Criteria:**
- Given 抽籤後的 2、3、8、13 隊賽事，when 依序讓每場以正常完賽進入申訴期並讓 worker 在期滿後處理，then 每一場都在期滿後才確認，勝隊只在確認後出現在下一場，最後賽事為 `finished`，名次與 `progression.podium` 一致。
- Given 任一場確認造成下一場兩隊湊齊，when 交易提交，then 該場有棄權期限且 outbox 有一筆 `MatchOpponentsDecided`；只湊齊一方時兩者都沒有。
- Given 同一場申訴期滿的場次，when worker 連續處理兩次，then 第二次不改任何資料、不再寫操作紀錄或事件。
- Given 雙方棄權的準決賽期滿，when worker 處理，then 決賽以 walkover 確認、季軍賽為 `voided`、賽事 `finished`、名次符合 I/O 矩陣。

## Verification

- 從主 repo 目錄：`MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "<worktree>/backend/app:/app/backend/app" -v "<worktree>/backend/tests:/app/backend/tests" backend bash scripts/test.sh` -- 全部通過
- `bash scripts/lint.sh`（同樣掛載）-- 通過
- competition `service.py` 分支覆蓋率 ≥ 90%（`coverage run --branch`，映像沒有 pytest-cov）

## Implementation Notes

## Spec Change Log

## Review Triage Log
