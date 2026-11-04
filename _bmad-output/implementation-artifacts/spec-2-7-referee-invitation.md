---
title: 'Story 2.7（第一階段）：邀請裁判的後端'
type: 'feature'
created: '2026-11-02'
status: 'done'
baseline_commit: '0a31e2f5d3c1bbb4f19b05374117bba04061d0f0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 主辦方還沒辦法邀請裁判，D 的 4.4 指派裁判（11/6）需要 `is_referee`、`list_referees` 與 TournamentReferee 資料表。

**Approach:** 第一階段只做後端：tournaments 新增 RefereeInvitation、TournamentReferee 兩張表與一支遷移；主辦方產生／查看邀請連結與已接受的裁判名單，受邀者預覽並接受邀請；提供合約上的 `is_referee`、`list_referees`。S31、S23 畫面在第二階段（3.1 的 Invite link field 合併後）完成。

## Boundaries & Constraints

**Always:**
- 邀請 7 天有效；`expires_at <= clock.now()` 即過期。產生新邀請時，先 `lock_tournament`，再把同賽事尚未過期的邀請 `expires_at` 設為現在（不刪除）。
- token 用 `secrets.token_urlsafe(32)`，明文存放並唯一（S31 需要再次顯示目前的連結，比照 3.1 的隊伍邀請）。
- 接受邀請要已登入且 Email 已驗證（`VerifiedAccount`）；已是裁判再接受一次回成功、不重複建立（冪等）。
- 裁判身分只在該賽事有效：`core.authz` 新增只比對已載入資料的判斷函式，`is_referee` 經由它判斷；單元測試證明 A 賽事的裁判在 B 賽事為否。
- 預覽 API 不需登入，只回 `Public*` schema（賽事名稱、到期時間、是否過期），不含主辦方或任何帳號資料（AD-19）。
- 產生邀請與接受邀請各寫一筆 `audit.record()`（不記 token）。
- 跨模組只呼叫 identity `service.py` 的公開函式；對 identity 只新增函式，不改既有函式。

**Never:**
- 不做前端畫面（第二階段）；`frontend/src/client` 只以 `bash scripts/generate-client.sh` 重新產生，不手改。
- 不做撤銷裁判、身分切換器的「裁判」身分、通知事件。
- 不檢查受邀者是否為參賽隊員（tournaments 不能呼叫 registration；由 4.4 指派時檢查）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 產生邀請 | 主辦方對自己的賽事 POST | 201，回 token、`expires_at`＝現在＋7 天；舊的未過期邀請 `expires_at`＝現在 | 別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`；不存在 404 |
| 查看目前邀請 | 主辦方 GET | 最新一筆邀請（含 `expired`）；從未產生回 `null` | 同上 |
| 預覽 | 任何人 GET 有效／過期 token | 200，`expired` 為 false／true | 不存在 404 `REFEREE_INVITATION_NOT_FOUND` |
| 接受 | 已驗證帳號、有效 token | 建立 TournamentReferee，回 `RefereeRead` | 過期或已作廢 409 `REFEREE_INVITATION_EXPIRED`；不存在 404；未登入 401；未驗證 403 `EMAIL_NOT_VERIFIED` |
| 重複接受 | 已是該賽事裁判 | 200，回原本的 `RefereeRead`，資料不重複 | — |
| 與重新產生同時 | 接受與重新產生並行 | 不會接受已作廢的邀請 | 以列鎖保證 |
| 主辦方接受 | 賽事主辦方本人用有效 token 接受 | 拒絕，不建立 TournamentReferee | 409 `ORGANIZER_CANNOT_BE_REFEREE` |
| 已結束／已取消 | 賽事狀態為 `finished` 或 `cancelled` 時產生或接受邀請 | 拒絕，資料不變 | 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES` |

## Decisions

- 2026-11-04（使用者）：主辦方不能接受自己賽事的裁判邀請。場次沒有裁判時由主辦方代為登錄比分（FR-26），主辦方不需要另外當裁判。planning 文件沒有規定這一點，由使用者決定。
- 2026-11-04（使用者）：賽事已結束或已取消時，產生邀請與接受邀請都拒絕；其餘狀態（含尚未開放）都可以。
- 2026-11-04（使用者）：已是該賽事裁判的人用過期或已作廢的連結再接受，維持回 409 `REFEREE_INVITATION_EXPIRED`（先檢查到期，再看是否已是裁判）；裁判身分不受影響。
- 2026-11-04（使用者）：第一階段就重新產生 `frontend/src/client`。原本 Never 寫「不重新產生」，但 CI 的「API client 與後端一致」會因新增的 5 支 API 失敗；2.1、2.2 第一階段也都有重新產生。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/models.py` -- 新增資料表 `RefereeInvitation`（`referee_invitation`：id、tournament_id FK、token 唯一、created_by、created_at、expires_at；索引 tournament_id）與 `TournamentReferee`（`tournament_referee`：主鍵 (tournament_id, account_id)、invitation_id、accepted_at）；schema `RefereeInvitationRead`、`PublicRefereeInvitation`、`RefereeRead`（合約欄位＋`accepted_at`）。
- `backend/app/modules/tournaments/repository.py` -- 邀請與裁判的查詢、`FOR UPDATE`／`FOR SHARE`；用 `ON CONFLICT DO NOTHING` 新增裁判。
- `backend/app/modules/tournaments/service.py` -- `invite_referee`、`get_current_invitation`、`preview_invitation`、`accept_invitation`、`is_referee`、`list_referees`；沿用 `lock_tournament`、`get_tournament`、`_tournament_not_found`、`audit`、`clock`。
- `backend/app/modules/tournaments/router.py` -- 主辦方路由沿用 `read_my_tournament` 的 `Organizer`＋`authz.ensure_tournament_owner` 寫法；只有 router commit。
- `backend/app/core/authz.py` -- 新增裁判判斷函式，比照 `ensure_tournament_owner` 以 Protocol 描述欄位。
- `backend/app/modules/identity/service.py` -- 只新增 `get_display_names(session, *, account_ids) -> dict[UUID, str]`（一次查多個，避免 N+1）；`hash_token`、`get_account_contact` 不動。
- `backend/app/alembic/versions/` -- 新增一支遷移，`down_revision = "a3d5e7f9b1c4"`（5.5，2026-11-04 main 的唯一 head；鏈為 2.2 → 4.1 → 3.1 → 3.2 → 5.5）。之後別人的遷移先合併時，依 CONTRIBUTING 第 4 節由後合併者調整。
- `backend/app/modules/tournaments/models.py:32` `TournamentStatus`（`FINISHED`、`CANCELLED`）、`:129` `Tournament.organizer_id` -- 兩個決定的判斷依據；比照 `service.py:486` `ensure_accepting_registrations` 寫一個不碰資料庫的 `ensure_accepting_referees(tournament)`。
- `backend/tests/helpers.py` -- 沿用既有建立帳號、主辦方、賽事的 helper。
- `backend/tests/tournaments/` -- 新增 `test_referees.py`；`frozen_clock` 測到期。
- `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- 補 `RefereeRead.accepted_at` 與 2.7 的 API。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/models.py` -- 新增兩張表與三個 schema -- TournamentReferee 是 D 的 4.4 依賴
- [x] `backend/app/alembic/versions/<rev>_story_2_7_referee.py` -- 建立兩張表、唯一索引 -- `test_migrations.py` 檢查與模型一致
- [x] `backend/app/core/authz.py` -- 新增 `is_tournament_referee(referee_tournament_ids, tournament_id) -> bool` 與 `ensure_tournament_referee(...)`（403 `TOURNAMENT_REFEREE_REQUIRED`） -- AC 指定由 core.authz 判斷
- [x] `backend/app/modules/identity/service.py` -- 新增 `get_display_names` -- `list_referees` 用
- [x] `backend/app/modules/tournaments/repository.py`、`service.py` -- 實作上列函式；接受時以 `FOR SHARE` 讀邀請，再檢查到期、賽事狀態與「不是主辦方本人」 -- 與重新產生互斥
- [x] `backend/app/modules/tournaments/router.py` -- `POST`／`GET /organizer/tournaments/{tournament_id}/referee-invitation`、`GET /organizer/tournaments/{tournament_id}/referees`、`GET /referee-invites/{token}`、`POST /referee-invites/{token}/accept`
- [x] `backend/tests/tournaments/test_referees.py`、`backend/tests/core/test_authz.py` -- 覆蓋 I/O 矩陣、7 天邊界、跨賽事為否、`list_referees` 依接受時間排序
- [x] `contracts/tournaments.md`、`deferred-work.md`、`sprint-status.yaml` -- 補合約；新增「2.7 第二階段：S31、S23 畫面」延後項目；2-7 改 `in-progress`
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh` 重新產生（CI 檢查與後端一致；Decisions 2026-11-04）

**Acceptance Criteria:**
- Given 主辦方產生過兩次邀請，when 用第一次的 token 接受，then 409 `REFEREE_INVITATION_EXPIRED`，第二次的 token 可以接受。
- Given 帳號接受 A 賽事邀請，when 呼叫 `is_referee` 查 A、B 賽事，then 分別為 true、false。
- Given 三個帳號先後接受，when `list_referees`，then 依接受時間排序且帶顯示名稱。

## Implementation Notes

- 遷移 `3274615001c8_story_2_7_referee.py`，原本 `down_revision = "a3d5e7f9b1c4"`。2026-11-04 D 的 5.1 第二階段（PR #22）先合併，它的 `b5c7e9a1d3f2` 也接在 `a3d5e7f9b1c4` 之後；緊接著 D 的 5.3、5.4 第二階段（PR #25）也合併，`d8e2f4a6b1c3` 接在 `b5c7e9a1d3f2` 之後；依 CONTRIBUTING 第 4 節由後合併的本 PR 改為 `down_revision = "d8e2f4a6b1c3"`。
- `accept_invitation` 的檢查順序：邀請不存在 404 → 過期或已作廢 409 → 賽事已結束／已取消 409 → 主辦方本人 409 → 已是裁判回原資料（冪等）。所以已是裁判的人用過期連結再接受一次會得到 409，而不是 200；只有第一次接受寫 `referee.accepted`。
- 併發：重新產生是「`lock_tournament`（FOR UPDATE）→ UPDATE 舊邀請」，接受是「以 token 查出賽事 → `lock_tournament` → FOR SHARE 重新讀邀請 → 檢查」；兩邊都先鎖賽事再碰邀請列，不會死結，賽事狀態也是在鎖內檢查。（最初版本接受時只以 FOR SHARE 讀邀請、不鎖賽事，審查指出新增 tournament_referee／audit_log 的外鍵檢查會對賽事列取 FOR KEY SHARE，與重新產生持有的 FOR UPDATE 交叉等待而死結，且賽事狀態在鎖外檢查；已改正。）兩種先後順序各有一個以兩條真的連線、輪詢 `pg_stat_activity` 確認對方卡在鎖上的測試。
- 「最新一筆邀請」以 `expires_at DESC, created_at DESC` 排序：最新的邀請到期時間一定最大，凍結時鐘下兩次產生在同一時間點也不會選到已作廢的那筆。
- `add_referee` 用 `INSERT … ON CONFLICT DO NOTHING RETURNING` 判斷是否真的新增；最初用 `rowcount > 0`，在測試裡實際新增了卻判斷為沒有新增（接受邀請的操作紀錄沒寫入），所以改用 RETURNING。
- `core.authz` 依 Tasks 的簽章以「已載入的賽事 id 集合」判斷（`Collection[UUID]`），沒有另外定義 Protocol。
- identity 只新增 `service.get_display_names` 與 `repository.list_accounts`，既有函式未修改。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-04）：Blind Hunter 13 筆、Edge Case Hunter 6 筆、Verification Gap 2 筆（另 2 筆 Other）。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Edge、Gap | 接受先以 FOR SHARE 鎖邀請，INSERT `tournament_referee`／`audit_log` 的外鍵檢查要對賽事列取 FOR KEY SHARE；重新產生先 `lock_tournament`（FOR UPDATE）再 UPDATE 邀請，兩邊交叉等待會死結 | high：`lock_tournament` 確為 FOR UPDATE（`repository.get_tournament`），兩個外鍵都指向 `tournament.id`；Implementation Notes「不鎖賽事就不會死結」不成立 | patch：接受時先 `lock_tournament` 再讀邀請，兩邊鎖的順序一致 |
| 2 | Blind、Edge | 接受時賽事狀態沒有鎖，和取消／結束賽事同時發生時可能接受成功 | medium：違反 I/O 矩陣「已結束／已取消時拒絕」；與 #1 同一修法 | patch（併入 #1） |
| 3 | Gap、Blind | Decisions「已是裁判用過期連結回 409」沒有測試，調換檢查順序不會有測試失敗 | medium | patch |
| 4 | Gap | 併發測試只涵蓋「重新產生先拿到鎖」，沒有「接受先拿到鎖」的交錯 | medium：正是 #1 的死結路徑 | patch（隨 #1 補測試）。補上的 `test_regeneration_waits_for_concurrent_accept_without_deadlock` 讓接受取得全部鎖後才暫停，驗證的是新的上鎖順序（重新產生要等接受結束）；死結發生在「接受鎖住邀請之後、INSERT 之前」，重現要在 service 中間插入停點，這個測試沒有直接證明舊程式會死結 |
| 5 | Blind、Edge | 併發測試用 `sleep(0.5)`＋`is_alive()` 判斷阻塞，CI 慢時沒有驗證到阻塞也會通過 | medium | patch：輪詢 `pg_stat_activity` 確認對方在等鎖 |
| 6 | Blind | `GET …/referee-invitation` 非主辦方 403、`GET …/referees` 不存在 404 沒有測試 | low：直接補測試 | patch |
| 7 | Blind | `tournament_referee` 沒有 `account_id` 索引，`is_referee` 依帳號查詢 | low：遷移加一個索引即可 | patch |
| 8 | Blind | 接受端看到的錯誤訊息是「不能再邀請裁判」，受眾不對 | low：分成產生與接受兩則訊息 | patch |
| 9 | Blind | 合約把 `ensure_accepting_referees` 標成內部，說明仍寫「兩個 `ensure_*`」 | low | patch |
| 10 | Blind | 預覽與接受的 `token` 路徑參數沒有長度上限 | low：`Path(max_length=64)` 直接擋 | patch |
| 11 | Blind | diff 裡沒有 `frontend/src/client` | false：審查 diff 刻意排除產生檔；client 已以 `generate-client.sh` 重新產生（382 行新增），typecheck 通過 | 不處理 |
| 12 | Blind | `is_referee` 先載入帳號所有裁判賽事 id 再比對 | low：凍結區塊要求經 `core.authz` 判斷；資料量小 | 不處理 |
| 13 | Blind | `invitation_id` 外鍵沒有索引 | low：沒有依 invitation_id 的查詢 | 不處理 |
| 14 | Blind | 重新產生時作廢舊邀請沒有寫操作紀錄 | low：凍結區塊只要求產生與接受各一筆；新邀請的紀錄已能推知舊邀請作廢 | 不處理 |
| 15 | Blind | `get_latest_invitation` 依賴「最新邀請到期最晚」的不變式 | low：效期是常數，期中不做自訂效期 | 不處理 |
| 16 | Blind | Verification 寫死本機路徑 | low：修正方式是改本 spec | 不處理 |
| 17 | Edge | 預覽在賽事已結束／已取消時仍回 `expired: false`，接受才 409 | medium：要新增 schema 欄位，凍結區塊的預覽欄位沒有包含；第二階段 S23 需要 | defer |
| 18 | Edge | 主辦方查看目前邀請，賽事已結束／已取消時看起來仍有效 | medium：與 #17 同，第二階段 S31 需要 | defer（併入 #17） |
| 19 | Edge | （主張）接受不鎖賽事可避免死結 | 同 #1 | patch |

## Verification

所有檔案與指令都在 `C:\Users\grace\espory-platform`（分支 `story/2-7`）；不要改到其他 worktree。

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過、覆蓋率門檻通過
- `docker compose exec backend bash scripts/lint.sh` -- expected: mypy、ty、ruff 通過
- `docker compose exec backend alembic heads` -- expected: 只有一個 head
