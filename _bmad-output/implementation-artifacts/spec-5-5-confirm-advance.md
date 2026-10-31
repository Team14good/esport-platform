---
title: 'Story 5.5、5.6（第二階段）：確認結果、晉級推進、申訴期滿自動確認與賽事結束'
type: 'feature'
created: '2026-10-31'
status: 'done'
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
- [x] `competition/models.py` 與新遷移 -- `Match.confirmed_at`（可為空）；`PublicPodium`（`champion`、`runner_up`、`third_place`）與 `PublicBracket.podium`；事件 `MatchResultConfirmed`、`MatchOpponentsDecided`
- [x] `competition/repository.py` -- 依 id 遞增鎖住對戰表全部場次；找下一場申訴期滿的場次 id
- [x] `competition/service.py` -- `confirm_match`、`advance`、`confirm_walkover`、`auto_confirm_expired`、`get_podium`；`get_public_bracket` 帶入名次
- [x] `backend/app/worker/jobs.py` -- 新增 `confirm_expired_appeals` 並加進 `JOBS`
- [x] `backend/tests/competition/test_confirm_advance.py`、`backend/tests/worker/` 對應測試 -- I/O 矩陣每一列；2、3、8、13 隊從抽籤一路確認到賽事結束的整合測試
- [x] `contracts/competition.md` -- 補 `auto_confirm_expired`、`get_podium`、`PublicBracket.podium`、兩個事件

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

### spec 沒寫、實作時的決定

- `advance` 的鎖：先 `lock_tournament`，再以一條 `SELECT … ORDER BY id FOR UPDATE`（`populate_existing`）鎖住整個對戰表的場次。worker 的 `auto_confirm_expired` 先鎖賽事、再 `lock_match` 鎖候選場次重新檢查，之後 `confirm_match` → `advance` 依 id 鎖其餘場次；持有的候選列不照 id 順序，但任何遵守 AD-6 的交易都要先拿賽事鎖，所以不會互鎖。
- 呼叫 `advance` 前對場次的修改必須已 flush（`populate_existing` 會以資料庫值覆蓋 identity map）；repository 的寫入都會 flush，6.5 換隊時也要經 repository 寫入。
- `confirm_match` 先呼叫 `transition_match` 檢查轉換，再寫 outcome、勝隊、`confirmed_at`，非法時不改任何資料。
- 連鎖的輪空確認同樣寫 `confirmed_at`、`match.confirmed` 操作紀錄與 `MatchResultConfirmed` 事件（「每場確認」），但不再呼叫 `advance`（`progression.advance` 已在同一次呼叫內推完）。
- 季軍賽取消另記一筆 `match.voided` 操作紀錄（before/after 狀態）；spec 只列了 `match.confirmed`、`tournament.podium`，取消也是狀態變更，所以補上。
- 操作者：觸發的那場用呼叫端給的 `actor_id`；連鎖的輪空確認、季軍賽取消、賽事狀態轉換與 `tournament.podium` 一律為系統（`None`），因為 `advance(session, *, match)` 沒有操作者參數。
- `match.confirmed` 的內容：before `{"status": 原狀態}`，after `{"status": "confirmed", "outcome", "winner_id"}`；`tournament.podium` 的 after 為 `{"champion", "runner_up", "third_place"}`（隊伍 id，從缺為 null）。
- `MatchResultConfirmed.winner_id` 可為 null（雙方棄權、兩方都沒有隊伍的輪空）。
- `MatchOpponentsDecided` 依 `progression` 的 `StartForfeitClock` 發出（兩者條件相同：本次填位後兩隊湊齊）。
- `confirm_walkover(session, *, match)` 照 contract 不帶操作者（系統）；勝隊為場上唯一的隊伍，兩方都沒有時無勝隊；兩隊都在時拋 409 `MATCH_INVALID_TRANSITION`（沿用既有錯誤碼，不新增）。
- `advance` 對尚未確認的場次讓 `progression` 的 `ValueError` 直接拋出（呼叫端程式錯誤，不是使用者能觸發的情境）。
- `get_podium(session, *, tournament_id) -> PublicPodium | None`：spec 沒定簽名，回傳與 `PublicBracket.podium` 相同的公開 schema；名次直接取 `progression.podium`（未結束為 None），不另外看賽事狀態。
- `auto_confirm_expired` 找候選時跳過已取消／已結束賽事的場次（記下賽事 id、以 `NOT IN` 重查），避免同一場永遠被選中而擋住其他場；鎖住後若賽事已結束、場次不在申訴期、期限未到或沒有 outcome，就不做任何事並回 True。repository 不讀 tournament 資料表，賽事狀態經 `tournaments_service.get_tournament` 取得。
- worker 工作 `confirm_expired_appeals` 排在 `open_registrations` 之後、`dispatch_outbox` 之前，同一輪就能分派確認產生的事件；`tests/worker/test_email_pipeline.py` 的工作順序測試隨之更新。
- `MatchRead` 沒有加 `confirmed_at`（spec 沒要求，避免改動 API）；`PublicBracket.podium` 是 spec 要求的 API 變更，已重新產生 `frontend/src/client`（CI 會檢查一致）。

### 已確認的決定（協調者 2026-10-31 回覆）

- `confirm_match` 只接受 `live`、`appeal_window`、`appealed`；`scheduled`、`confirmed`、`voided` 在寫入前拋 409 `MATCH_INVALID_TRANSITION`，不改任何資料（照 I/O 矩陣）。轉換表保留 scheduled → confirmed，給輪空確認用：`confirm_walkover` 與 `advance` 內的 `ConfirmWalkover` 直接走內部的 `_confirm`，不經 `confirm_match`。5.2 判棄權是 scheduled → appeal_window，不經 `confirm_match`。
- 賽事已取消時，其他模組直接呼叫 `confirm_match` 不擋，維持現狀（取消賽事不在期中範圍）；若觸發賽事結束，`transition_tournament` 會拋 409 `TOURNAMENT_INVALID_TRANSITION`。

### 審查後修正（協調者 2026-10-31）

- `find_expired_appeal_id` 加上 `outcome IS NOT NULL`：沒有 outcome 的申訴期場次不再被一直選中而擋住後面的場次（以真正的 finder 測試）。
- `confirm_match`、`confirm_walkover` 開頭先 `lock_tournament`，避免呼叫端先鎖場次、`advance` 才鎖賽事的順序反轉；docstring 與 contract 寫明呼叫端要先 `lock_tournament` 再 `lock_match`。
- `_finish` 只處理 `published`、`ongoing` 的賽事（已取消不再拋 409）；`get_podium` 與 `PublicBracket.podium` 只在賽事為 `finished` 時回傳名次。
- `get_public_bracket` 計算名次遇到不自洽的場次（`ValueError`）時記錄日誌、名次為 null，公開頁面不 500。
- 遷移 a3d5e7f9b1c4 與模型加上 `match (status, appeal_deadline)` 索引 `ix_match_status_appeal_deadline`。
- `set_match_team` 的 `side` 型別改為 `Literal["a", "b"]`；季軍賽取消時一併清除 `forfeit_deadline`。
- 重跑 `tests/competition`、`tests/worker`、`tests/test_migrations.py`：460 passed；`service.py` 分支覆蓋率 99%（221 行、72 分支，只缺 617->597），`repository.py` 100%；lint 通過。

### 驗證

- 全部測試（`bash scripts/test.sh`，掛載 worktree 的 app、tests、scripts）：899 passed（本分支 HEAD 基準 861，`--collect-only`；新增 38 個），後端整體行覆蓋率 97%；`tests/test_migrations.py` 通過。加上 `confirm_match` 來源狀態檢查後重跑 `tests/competition`、`tests/worker`：455 passed。
- `bash scripts/lint.sh`（mypy、ty、ruff check、ruff format --check）：通過。
- 分支覆蓋率（`coverage run --branch --source=app/modules/competition -m pytest tests/competition`）：competition 全體 99%，`service.py` 99%（加上 `confirm_match` 來源狀態檢查後 208 行、70 分支，只缺 `auto_confirm_expired` 迴圈的一條分支 588->568），`repository.py` 100%。
- 突變測試（在 scratchpad 副本上修改，跑 `test_confirm_advance.py` 與 worker 測試）：
  - (a) `advance` 不套用 `StartForfeitClock`：6 個失敗（3、8、13 隊整合測試、兩個湊齊測試、重複推進測試）。
  - (b1) repository 拿掉 `appeal_deadline <= now`：6 個失敗（4 個整合測試、期限未到、沒有期限）。
  - (b2) 鎖住後的重新檢查拿掉 `appeal_deadline > now`：一開始沒有測試失敗（repository 已過濾，重新檢查沒被測到）；補上「候選期限其實未到」的測試後 1 個失敗。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-10-31）：Blind Hunter 10 項、Edge Case Hunter 10 項、Verification Gap 0 個缺口＋3 項其他發現。

| # | 來源 | 發現 | 判定 | 證據 | 處置 |
|---|------|------|------|------|------|
| 1 | BH、EC | 申訴期滿但 `outcome` 為空的場次永遠是最早的候選，worker 每輪都卡在它 | high | 查詢沒過濾 `outcome`；鎖住後重新檢查失敗仍回 True，下次又選到同一場；現有測試用 monkeypatch 只回一次，遮住問題 | patch：查詢加 `outcome IS NOT NULL`，補「壞場次後面還有一場」的真查詢測試 |
| 2 | BH、EC、VG | 呼叫端照約定先 `lock_match` 再 `confirm_match`，`advance` 才鎖賽事，和 worker 的「先賽事後場次」順序相反，可能死結 | medium | AD-6 要求先鎖賽事；`confirm_match` docstring 與約定只寫 `lock_match`；測試輔助函式也沒鎖賽事 | patch：`confirm_match`／`confirm_walkover` 一開始先 `lock_tournament`，約定與 docstring 寫明呼叫端要先鎖賽事再鎖場次 |
| 3 | BH、EC、VG | 賽事已取消時決賽確定，`_finish` 轉 `finished` 拋 409；名次也不看賽事狀態 | low | `_finish` 只略過 `finished`；`get_podium` 只看場次 | patch：`_finish` 只處理 `published`／`ongoing`；名次只在賽事 `finished` 時回傳 |
| 4 | EC、VG | 公開對戰樹現在會跑 `progression.podium` 的一致性檢查，資料不一致時整頁 500 | low | 改動前公開對戰樹不做這個檢查 | patch：名次計算失敗時記錄日誌、名次為 null，對戰樹照常回傳 |
| 5 | BH | worker 查詢沒有索引 | low | 每輪都查 `status`＋`appeal_deadline`；加索引是直接修正 | patch：`(status, appeal_deadline)` 索引 |
| 6 | BH | `set_match_team(side: str)` 非 `"a"` 一律寫 b 方 | low | 型別可以直接收窄 | patch：`Literal["a","b"]` |
| 7 | BH | 季軍賽取消時沒清 `forfeit_deadline` | low | 目前靠 `list_forfeit_due` 只查待開打才沒出事 | patch：取消時一併清除 |
| 8 | EC | 某一場每次都拋錯時，worker 那一輪就停在它 | low | 只有資料不一致才會發生，會大聲失敗並記錄日誌；逐場吞錯要加 savepoint | 駁回 |
| 9 | BH、EC | `confirm_match` 不檢查 outcome 與勝隊是否一致 | low | 呼叫端是 5.2、6.2 的 service，錯了 progression 會拋 ValueError、整筆回滾 | 駁回（大聲失敗） |
| 10 | EC | 已取消賽事上直接呼叫 `confirm_match` 仍會填位 | low | 期中不能取消賽事；使用者同意維持現狀（見 Implementation Notes） | 駁回 |
| 11 | EC | `confirm_walkover` 不檢查空缺方是否真的確定不會有隊伍 | maybe-false | 約定由 6.5 在確定時才呼叫；若為真屬 medium | defer |
| 12 | EC、BH | 6.2 更正已結束或季軍賽已開打的場次時，`VoidMatch`、名次、賽事狀態的處理未定 | maybe-false | 6.2 尚未實作；若為真屬 medium | defer |
| 13 | EC | 填位後沒檢查裁判衝突 | false | spec 的 Never 明列留給 4.4 | 駁回 |
| 14 | BH | 賽事結束沒有事件 | low | spec 沒要求；`transition_tournament` 已寫操作紀錄 | 駁回 |
| 15 | BH | 沒有非空名次的 HTTP 測試、遷移沒測、docstring 寫 5.6 | false | VG 確認 `test_confirm_advance.py` 有公開 `podium` JSON 測試；`test_migrations.py` 比對遷移；spec 標題就是 5.5、5.6 | 駁回 |
