---
title: 'Story 4.4 指派裁判到場次（後端）'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'a469f952ba7647b9a64d1e41486594f8980003f4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `Match.referee_account_id` 沒有任何流程會寫入，所以記分者一律是主辦方；主辦方無法把 2.7 已接受邀請的裁判派到場次，晉級後裁判變成參賽隊員的衝突也沒人處理（5.5 留給 4.4）。

**Approach:** competition 新增指派／收回 API 與 service，S30 場次列表附上每場可選的裁判；`advance` 填位後檢查衝突並自動收回。只發事件、寫操作紀錄，通知由之後的 notifications 處理。

## Boundaries & Constraints

**Always:**
- AD-6：先 `lock_tournament`，再 `lock_match`；主辦方檢查用 `authz.ensure_tournament_owner`。
- 只能指派 `tournaments_service.is_referee` 為真的帳號；場次兩隊中已確定的隊伍，`registration_port.is_member` 為真就拒絕（待定的一方不檢查，晉級後由 `advance` 處理）。
- 可以指派／收回：賽事為 `published`、`ongoing`，且場次為 `scheduled`、`live`（送出系列結果前）；一位裁判可派多場、含同時段。
- 指派給目前的同一人、或收回沒有裁判的場次：直接回傳，不寫紀錄、不發事件。
- 指派與改派寫 `match.referee_assigned`（before／after 為帳號 id），收回寫 `match.referee_unassigned`；改派發 `RefereeUnassigned`（原裁判）＋`RefereeAssigned`（新裁判），指派只發後者，收回只發前者。
- 收回後由主辦方代登（`_is_scorer` 不改），已登錄的局保留。
- `advance` 填位後，若該場指派的裁判是新填入隊伍的隊員：清空 `referee_account_id`、寫 `match.referee_unassigned`（操作者為系統 `None`）、發 `RefereeUnassigned`。
- 任何拒絕都不改資料、不寫紀錄、不發事件。

**Never:**
- 不改 tournaments、registration 的既有函式；`is_member` 經 `registration_port` 呼叫。
- 不做 S30、S13 畫面與通知寄送；不新增資料表或遷移。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 指派 | 主辦方、賽事裁判、待開打場次 | 200 `MatchRead`，`referee_account_id` 為該帳號 | — |
| 改派 | 已有裁判，換另一位 | 新裁判寫入，兩個事件 | — |
| 收回 | 已有裁判 | `referee_account_id` 為 null，主辦方成為記分者 | — |
| 非裁判 | 帳號沒接受此賽事邀請（含主辦方本人） | 拒絕 | 409 `NOT_TOURNAMENT_REFEREE` |
| 隊員 | 裁判是該場已確定隊伍的隊員 | 拒絕 | 409 `REFEREE_IS_TEAM_MEMBER` |
| 已送出 | 場次 `appeal_window`、`appealed`、`confirmed`、`voided` | 拒絕 | 409 `MATCH_REFEREE_LOCKED` |
| 賽事狀態 | 賽事 `finished`、`cancelled` | 拒絕 | 409 `TOURNAMENT_NOT_ASSIGNABLE` |
| 非主辦方 | 已登入的其他主辦方 | 拒絕 | 403 `TOURNAMENT_OWNER_REQUIRED`（沿用 authz） |
| 不存在 | 賽事或場次不存在、場次不屬於此賽事 | 拒絕 | 404 `TOURNAMENT_NOT_FOUND`／`MATCH_NOT_FOUND`（沿用 4.3） |
| 晉級衝突 | 確認後填入的隊伍含下一場裁判 | 下一場自動收回 | — |

## Decisions

- 2026-11-04（使用者）：這支 PR 只做後端（A）。S30 頁面（改時間＋指派裁判）另開一支，S13 我執法的場次之後再做。
- 2026-11-04（使用者）：主辦方不能兼任裁判，場次沒有裁判時由主辦方代登比分（沿用 2.7 的決定）；選手自行登錄比分期中不做。

</frozen-after-approval>

## Code Map

- `competition/service.py` -- `reschedule_match`（1631，檢查順序與 AD-6 寫法照抄）、`list_managed_matches`（1698，加欄位）、`advance`（712，`FillSlot` 後檢查衝突）、`_is_scorer`（1175，不改）、`_match_in_tournament`、`lock_match`、`_match_to_read`
- `competition/registration_port.py` -- 新增 `is_member`（同 `is_captain` 的 `_lookup`，`action="指派裁判"`）；registration 已有 `is_member`
- `competition/repository.py` -- 新增寫入 `referee_account_id`（含 `updated_at`）的函式
- `competition/models.py` -- 新增 `RefereeAssigned`、`RefereeUnassigned` 事件（欄位見 contracts 212–213）、`RefereeAssignIn {account_id}`；`ManagedMatch` 加 `assignable_referee_ids: list[UUID]`（依 `list_referees` 順序、排除兩隊隊員）與 `can_assign_referee: bool`
- `competition/router.py` -- `PUT`、`DELETE /tournaments/{tournament_id}/matches/{match_id}/referee`，`Organizer` 依賴，與 4.3 的 PATCH 同樣寫法
- `tournaments/service.py` -- `is_referee`、`list_referees`；只呼叫
- 測試參考：`tests/competition/test_reschedule.py`、`test_score_entry.py`（直接寫 `referee_account_id` 的寫法）、`tests/competition/conftest.py` 的 `draw_with`；接受裁判邀請用 tournaments 的 `invite_referee`＋`accept_invitation`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/{models,repository,registration_port,service,router}.py` -- 事件、型別、寫入、`assign_referee`／`unassign_referee`、列表欄位、`advance` 衝突收回、兩個端點
- [x] `backend/tests/competition/test_assign_referee.py` -- I/O 矩陣每一列；拒絕時資料、紀錄、事件都不變；同一人／無裁判不寫入；列表的 `assignable_referee_ids` 與指派 API 一致；經指派 API 後 `get_score_entry` 的 `is_scorer` 隨之切換（收回後回到主辦方、已登錄的局保留）；晉級衝突自動收回
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- API 表、錯誤碼、`ManagedMatch` 新欄位
- [x] `frontend/src/client/` -- `scripts/generate-client.sh` 重新產生，不手改
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 5.3 的「4.4 指派裁判後，S4 的記分者判斷要接上」（本 Story 處理完）；只新增：S30 指派選單、S13 我執法的場次
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 4.4 改 in-progress；4.3、5.1、5.3、5.4 註記的「待合併」改成已合併（#26、#22、#25）

**Acceptance Criteria:**
- Given 列表某場 `assignable_referee_ids` 含某裁判，when 指派他到該場，then 成功；不含的裁判 then 失敗。
- Given 被指派的裁判，when 呼叫 `get_score_entry`，then `is_scorer` 為真，主辦方為假；收回後相反。

## Implementation Notes

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-04）：Blind Hunter 13 項、Edge Case Hunter 2 項、Verification Gap 2 個缺口。沒有 intent_gap、bad_spec，全部 patch 或駁回。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | VG | 賽事 `ongoing` 時能指派沒有測試（`draw_with` 只產生 published） | medium | 拿掉 ONGOING 測試不會失敗，開賽後就無法指派。patch：補 ongoing 的 PUT、DELETE、列表測試 |
| 2 | VG | 真正的 `registration_port.is_member` 轉接沒被測到（全被替身取代） | medium | 寫錯函式名或參數時測試全綠。patch：照 `_REAL_IS_CAPTAIN` 補轉接與 503 測試 |
| 3 | Blind、Edge | `MATCH_REFEREE_LOCKED` 對已取消（voided）的場次也說「已送出結果」 | low | 季軍賽取消後會遇到。patch：訊息改成涵蓋已取消 |
| 4 | Blind | models.py 註解仍寫「4.4 前為 None」；`RefereeAssignIn` 放在 4.3 區段 | low | patch：改註解、移到 4.4 區段 |
| 5 | Blind | contracts 錯誤碼沒寫 401、422、503 | low | patch：補上（503 目前不會發生，registration 已有 `is_member`） |
| 6 | Blind | 缺 401／422 測試、改派不寫 `referee_unassigned` 紀錄的斷言、賽事結束時列表為不可指派的測試 | low | 4.3 有同類測試。patch：補上；「主辦方不在可選名單」為 false（主辦方不能成為裁判，`list_referees` 不會有他） |
| 7 | Blind、Edge | 刪掉的 5.3 延後項目還有「S4 面板隨指派顯示／隱藏」沒做 | low | 後端端對端測試已補，前端檢查仍待 A。patch：新增延後項目保留前端檢查 |
| 8 | Blind | S30 選單沒有裁判名字、成功後回 `MatchRead` 不能更新列 | low | 與 4.3 同樣回 `MatchRead`。patch：S30 延後項目寫明名字取自 `GET /organizer/tournaments/{id}/referees`、成功後也重抓列表 |
| 9 | Blind | 已登錄的局在改派後是否保留、新裁判能否修改沒寫 | low | 行為是保留且新裁判可修改（記分者只看目前裁判）。patch：contracts 寫明 |
| 10 | Blind | 指派同一人直接回傳、略過隊員檢查 | false | 抽籤後名單已鎖（`_roster_locked_for_join`），指派後不會新增隊員 |
| 11 | Blind | 指派後裁判加入參賽隊伍不會被處理 | false | 同 #10；隊員異動（3.11）期中擱置 |
| 12 | Blind | 列表與 PUT 的隊員檢查寫兩次 | low | `test_list_assignable_matches_assign_api` 已驗證兩者一致；抽共用函式不是直接修正。reject |
| 13 | Blind | 列表每位裁判×每隊查一次 `is_member` | low | 期中規模數位裁判；4.3 同類 N+1 已駁回。reject |
| 14 | Blind | 沒有訂閱 `RefereeAssigned` 寄通知 | false | Intent 寫明只發事件，通知由之後的 notifications 處理 |

## Verification

**Commands:**
- 在主 repo 目錄執行（worktree 沒有 `.env`），`WT=I:/大學課程/軟工/espory-wt/s44`：`MSYS_NO_PATHCONV=1 docker compose run --rm -T -v "$WT/backend/app:/app/backend/app" -v "$WT/backend/tests:/app/backend/tests" -v "$WT/backend/scripts:/app/backend/scripts" backend bash -c "python -m pytest -q -p no:cacheprovider | tail -1; bash scripts/lint.sh"` -- expected: 全部通過（含 `test_architecture.py`）
- 重新產生 client 後 `bunx biome check src`、`bun run build` -- expected: 通過
