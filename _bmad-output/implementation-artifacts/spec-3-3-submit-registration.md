---
title: 'Story 3.3 送出報名與鎖定名單'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '8d9183de77b7f404c55826a41b2916b0ceef67f9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-2-player-registration-info-2.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 隊伍組好、資料填完後，隊長還沒辦法送出報名；名單也不會鎖定，已送出的隊伍仍可經邀請連結加人（deferred-work 留給 3.3 的項目）。3.4～3.6 的名額分配要用送出時凍結的學校、平均段位積分與送出時間，這些快照也還不存在。

**Approach:** 隊長在 S17 按「送出報名」，AlertDialog 確認後送出：報名從 `forming` 轉為 `pending`，凍結三個快照；名單鎖定（不能加入、不能改參賽資料、邀請連結失效）。不符合條件時按鈕停用並逐項列出原因，伺服器以同一份檢查拒絕。

## Decisions（2026-11-03，邱芯彤）

- 先搶期（優先期結束後）送出：3.3 一律轉為 `pending`，不做當下分配。優先期內送出的顯示「已送出・待分配」＋「優先期結束後分配名額」倒數；優先期結束後送出的只顯示「已送出・待分配」，不顯示倒數，等 3.5 改為當下分配。
- 非隊長的隊員在 S17：不顯示「送出報名」，改顯示一行「由隊長送出報名」，下方同樣逐項列出送出條件還缺什麼。
- spec 篇幅約 4,000 tokens，超過 1600，保留完整 spec，不拆分。
- spec 審查後（同日）：
  - 報名截止時間由 registration 自己比對，套用到送出、建隊、加入、修改參賽資料四個操作（3.6 之前賽事不會自動變成 `closed`）；`profile_editable` 也要在截止前。
  - 平均段位積分欄位為 `numeric(12,2)`（段位積分上限是 PostgreSQL integer 上限，`numeric(6,2)` 會溢位）。
  - 加入已鎖定隊伍的訊息為「名單已鎖定，無法加入。」。
  - 學校不一致只比較已設學校的隊員，可與「尚未設定學校」同時列出。
  - 隊長檢查在 `core/authz.py` 新增 `ensure_captain`（以 Protocol 描述隊伍，比照 `ensure_tournament_owner`），competition、disputes 之後沿用。
- 程式審查後（同日）：
  - 報名截止後仍在組隊中的隊伍，邀請狀態為 `closed`，S17 與 S19 顯示「連結已失效：報名已截止」；優先順序為已鎖定 > 已截止 > 已滿 > 有效。
  - `ensure_captain` 預設訊息「只有隊長可以使用這個功能。」，呼叫端可傳入訊息；送出報名傳入「只有隊長可以送出報名」。

## Boundaries & Constraints

**Always:**
- 送出的檢查順序：查隊伍（404 `TEAM_NOT_FOUND`）→ `lock_tournament()` → 是隊員（403 `TEAM_MEMBER_REQUIRED`）→ 是隊長（`core.authz.ensure_captain`，403 `TEAM_CAPTAIN_REQUIRED`「只有隊長可以送出報名」）→ 在報名期間（賽事 `open` 且現在早於 `registration_end`，否則 409 `REGISTRATION_CLOSED`）→ 報名仍是 `forming`（否則 409 `REGISTRATION_ALREADY_SUBMITTED`「這支隊伍已送出報名」）→ 送出條件。
- 建隊、加入、修改參賽資料同樣要在報名期間（現在早於 `registration_end`），否則 409 `REGISTRATION_CLOSED`。
- 送出條件（依序，全部列出，不只第一項）：人數達先發人數；每位隊員參賽資料完整（沿用 3.2 的 `missing_fields`）；每位隊員都設定了學校；已設學校的隊員學校相同。不符合時 409 `REGISTRATION_REQUIREMENTS_UNMET`，`message` 為各項原因以「；」串接。
- 送出成功：`mark_status(forming → pending)`，同一交易寫入 `school_id`、`avg_rank_score`（全隊含替補的平均，`numeric(12,2)`，ROUND_HALF_UP）、`submitted_at`（`clock.now()`）；操作紀錄 `registration.submitted`（`after` 含三個快照）。
- 名單鎖定（報名不是 `forming`）時：`join_team` 回 409 `ROSTER_LOCKED`「名單已鎖定，無法加入。」；邀請預覽與 S17 的邀請狀態為 `locked`，顯示「連結已失效：名單已鎖定」；`profile_editable` 為 false。
- `TeamDetail` 由後端算出 `submit_blockers`（代碼與介面文字），前端停用原因與伺服器拒絕原因出自同一份規則。
- 學校從 identity 讀取：只在 identity 新增公開函式，不改既有函式；`core/authz.py` 只新增 `ensure_captain`；PR 說明列出（CONTRIBUTING 6.6）。

**Never:**
- 不做名額分配（正取、候補，3.4～3.6；#28 未合併），送出一律轉為 `pending`。
- 不發 outbox 事件（FR-37 只通知報名結果，不通知送出）。
- 不做撤回、退回、隊員異動（期中擱置）；不改 tournaments 模組，不做賽事 open → closed（3.6）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 送出成功 | 隊長、報名期間、條件全符合 | 200 `TeamDetail`，`registration_status=pending`，三個快照寫入，`invite_status=locked` | N/A |
| 人數不足 | 4 人、先發 5 | 不送出；S17 停用並列「還差 1 人才達先發人數（5 人）」 | 409 `REGISTRATION_REQUIREMENTS_UNMET` |
| 資料未填完 | 有人缺參賽資料 | 不送出；列「尚未填完參賽資料：小芸、阿凱」 | 同上 |
| 有人沒設學校 | 隊員 `school_id` 為 null | 不送出；列「尚未設定學校：阿凱」 | 同上 |
| 學校不一致 | 已設學校的隊員學校不同 | 不送出；列「隊員的學校不一致」 | 同上 |
| 沒設學校＋其餘同校 | A、B 同校，C 沒設 | 只列「尚未設定學校：C」 | 同上 |
| 多項不符 | 人數不足且有人沒填 | 每項都列出，順序固定 | 同上，message 含全部原因 |
| 非隊長 | 隊員送出 | 拒絕；S17 不顯示「送出報名」 | 403 `TEAM_CAPTAIN_REQUIRED` |
| 非隊員 | 他隊帳號 | 拒絕 | 403 `TEAM_MEMBER_REQUIRED` |
| 重複送出 | 已是 `pending`；或兩個請求同時送出 | 只有一次成功 | 409 `REGISTRATION_ALREADY_SUBMITTED` |
| 截止前 1 秒 | 現在 = `registration_end` − 1 秒 | 可送出 | N/A |
| 剛好截止 | 現在 = `registration_end` | 不送出；S17 停用並寫「已截止」 | 409 `REGISTRATION_CLOSED` |
| 賽事非開放 | 賽事不是 `open` | 不送出 | 409 `REGISTRATION_CLOSED` |
| 截止後的其他操作 | 現在 ≥ `registration_end`，建隊、加入、改參賽資料 | 拒絕；S18 唯讀 | 409 `REGISTRATION_CLOSED` |
| 鎖定後加入 | 以邀請連結加入已送出的隊伍 | S19 顯示「連結已失效：名單已鎖定。」 | 409 `ROSTER_LOCKED`「名單已鎖定，無法加入。」 |
| 隊伍不存在 | 未知 team_id | 拒絕 | 404 `TEAM_NOT_FOUND` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/models.py` -- `Registration`（108-120）只有 id、team_id、tournament_id、status、created_at；`InviteStatus`（148）註解寫「名單鎖定由 3.3 加入」；`TeamDetail`（176-200）、`TeamInvitePreview`（203-213）、`RegistrationRead`（241-248）
- `backend/app/modules/registration/service.py` -- 錯誤 helper（61-113）：`_team_member_required` 訊息是「只有隊員可以查看這支隊伍。」（送出沿用，非隊員看不到 S17）、`_roster_locked` 訊息是「名單已鎖定，資料無法修改。」（加入另寫訊息、同代碼）；`_TRANSITIONS`（122-164，forming → pending 已允許）；`mark_status`（171-202）；`_invite_status`（212）；`_ensure_can_join`（222，`_ensure_accepting_registrations`）；`_missing_fields`（233-242）；`_profile_editable`（245-249）；`_build_detail`（252-299）；`preview_invite`（359-376）；`join_team`（379-412）；`update_player_profile`（466 附近）；`is_captain`（572-574）
- `backend/app/core/authz.py` -- `ensure_tournament_owner` 以 Protocol 描述賽事；`ensure_captain` 照同樣寫法，Protocol 描述「有 `members`、每位有 `account_id` 與 `role`」（`TeamRead` 符合）
- `backend/app/modules/registration/player_profile.py` -- `average_rank_score`（回 float）；快照要 `Decimal`
- `backend/app/modules/identity/service.py` -- `AccountContact`（56-61，沒有 school_id）；`Account.school_id`（identity/models.py:80）。新增 `get_account_school_ids(session, account_ids) -> dict[UUID, UUID | None]`
- `backend/app/modules/tournaments/service.py:486` -- `ensure_accepting_registrations` 只看狀態；open → closed 由 3.6 做（contracts/tournaments.md:98）
- `backend/app/core/audit.py:72-73` -- `after` 以 `to_jsonable_python` 存，`Decimal` 會變成字串
- `backend/app/alembic/versions/a3f6b9d2c8e1_story_3_2_player_profile.py` -- 目前 head
- 測試：`tests/registration/test_teams.py` 的 `lock_spy`、`_set_status`；`tests/registration/test_player_profile_api.py` 準備隊伍與填資料；`tests/registration/test_team_concurrency.py` 多連線＋執行緒的併發寫法（含清理與取消管理員身分）；`tests/helpers.make_tournament` 用 `priority_hours`（`priority_end` 由 `registration_start` 算出，不能直接傳）；`frozen_clock` 固定在 2026-10-18 11:00 UTC，`registration_start`／`registration_end` 以它為基準設定
- `frontend/src/features/registration/TeamPage.tsx` -- 邀請欄位（75-86，`TEAM_FULL_REASON`）、RosterList、S18；`my_role` 已在 `TeamDetail`
- `frontend/src/components/common/ConfirmDialog.tsx` -- 送出中轉圈且不能關閉，`onConfirm` reject 時在對話框內顯示 `detail.message`；用法見 `features/identity/AdminApplicationsPage.tsx:56-66`
- `frontend/src/components/common/Countdown.tsx` -- `label`、`deadline`、`variant`（可為函式）、`expiredText`、`onExpire`；預設到期文字「已截止 · 系統處理中」並每 5 秒重抓、2 分鐘後顯示逾時（19-21）；用法見 `features/tournaments/TournamentOverview.tsx:58-66`
- `frontend/src/features/registration/{InviteLinkField,JoinTeamPage,registration-status}.tsx` -- `invalid={reason}`；S19 的 `Rejected`（94-100）；`pending` 標籤「已送出・待分配」、色調 `status-appeal`；成功後失效 `myTeamsQueryOptions` 的寫法見 `JoinTeamPage.tsx:86`
- `frontend/tests/unit/team-pages.test.tsx` -- `member()`、`filled()`、`TEAM`、`mockReadTeam`、`mockPreview`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py` -- `Registration` 加 `school_id`（FK school，可為 null）、`avg_rank_score`（`numeric(12,2)`，可為 null）、`submitted_at`（timestamptz，可為 null）；`InviteStatus` 加 `"locked"`；`TeamDetail` 加 `submit_blockers: list[SubmitBlocker]`、`priority_end`、`registration_end`、`submitted_at`；`RegistrationRead` 加 `school_id: UUID | None`、`avg_rank_score: Decimal | None`、`submitted_at: datetime | None`（`pending` 之後三者必有值；3.4 的 `allocation.Candidate` 要 `UUID`、`Decimal`、aware datetime）
- [x] `backend/app/alembic/versions/<hex>_story_3_3_submit_registration.py` -- 三欄，`down_revision = "a3f6b9d2c8e1"`
- [x] `backend/app/core/authz.py` -- 新增 `ensure_captain(team, account_id)`，403 `TEAM_CAPTAIN_REQUIRED`「只有隊長可以送出報名」
- [x] `backend/app/modules/identity/service.py` -- 新增 `get_account_school_ids`（只新增）
- [x] `backend/app/modules/registration/player_profile.py` -- 送出條件純函式：輸入人數、先發數、每位隊員（顯示名稱、缺漏欄位、學校），依加入順序輸出 `SubmitBlocker`。代碼與文字：`STARTERS_NOT_MET`「還差 N 人才達先發人數（S 人）」、`PROFILE_INCOMPLETE`「尚未填完參賽資料：A、B」、`SCHOOL_MISSING`「尚未設定學校：A」、`SCHOOL_MISMATCH`「隊員的學校不一致」；另加回傳 `Decimal` 的平均值
- [x] `backend/app/modules/registration/service.py` -- `submit_registration(session, *, team_id, account_id) -> TeamDetail`；報名期間檢查（`_ensure_accepting_registrations` 之外比對 `registration_end`）套用到建隊、加入、修改參賽資料與 `_profile_editable`；`_invite_status` 鎖定優先於額滿（`locked` > `full` > `active`）；`join_team` 在鎖之後檢查 `forming`；`_build_detail`：`submit_blockers` 只在 `forming` 時計算（其他狀態為 `[]`），截止後加一筆 `REGISTRATION_CLOSED`「已截止」（只供畫面，伺服器送出時仍回獨立的 409）
- [x] `backend/app/modules/registration/router.py` -- `POST /teams/{team_id}/submission`（`VerifiedAccount`，200 回 `TeamDetail`）
- [x] `backend/tests/registration/test_submit_registration.py` -- I/O 矩陣每一列、先查再鎖（`lock_spy`）、快照值（含替補平均、四捨五入、大積分不溢位）、操作紀錄、併發（照 `test_team_concurrency.py`）、鎖定後加入與預覽、截止邊界（`frozen_clock`）、截止後建隊／加入／改資料；`ensure_captain` 與 identity 新函式的測試
- [x] `frontend/src/client` -- 重新產生
- [x] `frontend/src/features/registration/` -- 見下方「前端」
- [x] `frontend/tests/unit/` -- 停用與原因、確認後呼叫 API、伺服器錯誤顯示在對話框、送出後狀態與倒數、倒數到期、鎖定的邀請欄位與 S19、非隊長畫面
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 3.1 留給 3.3 的項目（`join_team`／`_invite_status` 檢查 `forming`）

**前端（S17、S19）：**
- 隊長、`forming`：「送出報名」（primary，同頁唯一的 primary）；`submit_blockers` 非空時停用，下方逐項列出 `message`。`ConfirmDialog` 標題「送出報名」、內文「送出後名單會鎖定，只有被主辦方退回才能修改。」、確認鈕「送出報名」（非 destructive）。成功後以回應 `setQueryData`、失效 `myTeamsQueryOptions`、Toast「已送出報名」。
- 非隊長、`forming`：「由隊長送出報名」＋同樣的缺漏清單。
- `forming` 時顯示報名截止 `Countdown`（剩餘超過 24 小時 `muted`，最後 24 小時 `appeal`）；到期時不輪詢，`expiredText`「已截止」，並停用「送出報名」（以 `onExpire` 重抓隊伍，後端會回 `REGISTRATION_CLOSED` blocker）。
- `pending` 且現在早於 `priority_end`：`Countdown`（`muted`）標籤「優先期結束後分配名額」；到期時不輪詢、不顯示逾時，改顯示「已送出・待分配」即可（分配在 3.4 第二階段）。`pending` 且優先期已過：不顯示倒數。
- 邀請欄位：`locked` 時 `invalid={reason: "名單已鎖定"}`；S19：`locked` 時「連結已失效：名單已鎖定。」＋回賽事頁。

**Acceptance Criteria:**
- Given 隊長在 S17 且條件全符合，when 按「送出報名」並在 AlertDialog 確認，then 徽章變「已送出・待分配」、Toast「已送出報名」、邀請欄位顯示「連結已失效：名單已鎖定」、S18 為唯讀。
- Given 優先期內已送出，when 檢視 S17，then 顯示「優先期結束後分配名額」倒數。
- Given 條件不符，when 隊長檢視 S17，then「送出報名」停用，下方逐項列出原因，文字與伺服器拒絕時相同。
- Given 報名截止倒數歸零，when 隊長還在 S17，then「送出報名」停用並寫「已截止」，S18 唯讀。
- Given 已送出的隊伍，when 有人開啟邀請連結，then S19 顯示「連結已失效：名單已鎖定。」並提供回賽事頁的連結。

## Implementation Notes

- 遷移檔 `d7e2a5c9b4f1_story_3_3_submit_registration.py`（`down_revision = "a3f6b9d2c8e1"`），外鍵名 `registration_school_id_fkey`。
- 截止時間比對的 409 `REGISTRATION_CLOSED` 訊息為「這場賽事的報名已截止。」（賽事狀態不是 `open` 時仍是 tournaments 的「這場賽事目前不開放報名。」）；spec 沒有指定這句文字。
- `submit_blockers` 的 `REGISTRATION_CLOSED`「已截止」排在最前面，其餘原因照常列出；賽事不是 `open` 時也會加這一筆（截止或非開放，畫面上都不能送出）。
- identity 只新增：`service.get_account_school_ids` 與 `repository.list_account_school_ids`。`core/authz.py` 只新增 `ensure_captain`（角色以字串 `"captain"` 比對，core 不能 import registration 的 `MemberRole`）。
- `join_team` 的 `forming` 檢查放在 `_ensure_can_join`（報名期間、主辦方、已在賽事）之後、人數之前，所以鎖定且額滿時回 `ROSTER_LOCKED`，與 `locked` > `full` 一致。
- `player_profile.average_rank_score_decimal` 回 `Decimal`；原本的 `average_rank_score`（float）改為呼叫它。
- 前端倒數不改共用的 `Countdown`（B 的元件）：`SubmitRegistrationSection.tsx` 的 `useDeadlinePassed` 在到期時把 `Countdown` 換成靜態的「已截止」／「已送出・待分配」，所以不會觸發 `Countdown` 的 5 秒輪詢與 2 分鐘逾時文字；報名截止歸零時只重新取得隊伍一次，在重新取得前先在本地補上「已截止」並停用按鈕。
- 優先期倒數歸零後在「名額分配」區塊顯示「已送出・待分配」；開啟頁面時優先期已過則整個區塊不顯示。
- 程式審查後：`useDeadlinePassed` 除了到期的 setTimeout，另在分頁重新顯示時與 `Countdown` 的 `onExpire` 再檢查一次（裝置休眠時計時器可能延後）；S19 加入時被拒 `ROSTER_LOCKED` 與預覽 `locked` 顯示同一句「連結已失效：名單已鎖定。」。
- 瀏覽器手動檢查（含 375 px）尚未執行。
- 2026-11-03 補做瀏覽器實測：Playwright 以隊長（375 px）、隊員（桌機）、未加入者實測 32 項全部通過，含實際等一場賽事截止、倒數歸零後沒有轉圈與逾時文字；資料庫的報名快照與操作紀錄正確。
- 2026-11-03 合併 main 時，D 的 5.5（#20）遷移 `a3d5e7f9b1c4` 也接在 `a3f6b9d2c8e1` 之後，依 CONTRIBUTING 第 4 節把本 Story 的 `down_revision` 改接 `a3d5e7f9b1c4`；開發資料庫先 downgrade 回 `a3f6b9d2c8e1` 再升級，避免 5.5 的遷移被跳過。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-03；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V1、B2 | `join_team` 先鎖再讀報名狀態的順序沒有測試；也沒有送出與加入同時發生的測試 | medium | `_record_checks`（test_teams.py:731-740）沒包 `get_registration_by_team`；現有鎖定測試都是先送出完成再加入，檢查移到鎖之前也會全過 | patch |
| V2 | 預覽時連結有效、加入前隊伍剛送出：S19 顯示伺服器訊息「名單已鎖定，無法加入。」，與預覽已鎖定時的「連結已失效：名單已鎖定。」不同 | low | `JoinTeamPage.tsx` 的 `join.isError` 走通用 `Rejected`；I/O 矩陣「鎖定後加入」要求顯示後者 | patch |
| E3 | 截止後仍在組隊中的隊伍，S17 與 S19 顯示連結有效，但加入一定失敗 | medium | `_invite_status` 只看報名狀態與人數；本次讓截止後的加入回 409，連結狀態卻沒跟上。使用者決定新增 `closed` | patch（使用者決定） |
| B1 | `ensure_captain` 的訊息寫死為送出報名，competition、disputes 沿用時文字不對 | medium | core/authz.py 只有一段訊息；Decisions 寫明之後沿用。使用者決定預設通用訊息、呼叫端可傳入 | patch（使用者決定） |
| E1、E2 | 裝置休眠或計時器延遲時，`Countdown` 先歸零：顯示轉圈、2 分鐘後顯示逾時文字，「送出報名」仍可按、也不會重抓 | medium | `Countdown` 每秒依 `Date.now()` 判斷歸零，沒有 `onExpire` 時仍顯示轉圈與逾時（Countdown.tsx:166、201-205）；`useDeadlinePassed` 只靠一次長時間 `setTimeout`，休眠時不計時 | patch |
| E4～E7、B4 | 「`pending` 之後三個快照必有值」與「組隊中 `submitted_at` 為 null」的說明過度承諾：`mark_status` 可直接 forming → withdrawn，rejected → forming 不清快照 | low | 只有 `submit_registration` 寫快照；撤回、退回是期中擱置的功能，目前沒有路徑會走到。修正是改寫 docstring 與註解 | patch |
| B3 | 有段位但積分為 null 的隊員被排除在平均之外 | false | 段位與積分只由 `update_player_profile` 一起寫入（3.2），不會只有其中一個 | reject |
| B5 | 賽事取消時 S17 也寫「已截止」 | low | 取消賽事是期中擱置的功能，目前沒有路徑；其他非 open 狀態都在截止之後 | reject |
| B6 | 已在別的分頁送出時，重抓後確認對話框連同錯誤一起消失 | low | 重抓後畫面已顯示「已送出・待分配」，使用者看得到結果 | reject |
| B7 | `PassedDeadline` 複製 B 的 `Countdown` 版面 | low | 沒有修改 B 的元件；在 PR 說明列出 | reject |
| B8 | 從 D 的 `features/competition` 借用 `formatMatchDateTime` | low | 只 import 公開的格式化函式；在 PR 說明列出 | reject |
| B9 | 每次讀 S17 都逐一查隊員名稱與學校 | low | 隊伍最多約 10 人；改成批次查詢要新增 identity 公開函式 | reject |
| B10 | sprint-status 仍是 `in-progress`、瀏覽器實測未做 | low | step-05 改為 `review`；瀏覽器實測在 commit 前做 | reject |
| B11 | 「只有隊長可以送出報名」「這支隊伍已送出報名」沒有句號 | low | 文字來自凍結的 spec；不影響功能 | reject |
| B12 | 停用的按鈕無法取得焦點，鍵盤使用者聽不到原因 | low | 原因清單在畫面上可見；改用 `aria-disabled` 要另寫點擊阻擋 | reject |
| B13 | 併發測試留下已提交的學校、帳號、賽事 | low | 沿用 `test_team_concurrency.py` 的做法；操作紀錄只增不改，賽事無法刪除；全套測試通過 | reject |
| B14 | 24 小時邊界、超過 24.8 天的分段等待沒測試；裝置時間偏差；S17 沒顯示送出時間 | low | 伺服器仍會依自己的時間拒絕；送出時間 UX 沒有要求顯示 | reject |

## Design Notes

- 停用原因由後端算（`submit_blockers`），送出時再用同一個函式檢查一次，避免前後端規則分歧（EXPERIENCE.md:235 要求兩者一致）。
- `mark_status` 只管狀態與 `registration.status_changed`；快照與 `registration.submitted` 在 `submit_registration` 內同一交易寫入。
- 截止比對放在 registration：tournaments 的 `ensure_accepting_registrations` 只看狀態，open → closed 要到 3.6 才有；兩者都檢查，3.6 之後時間檢查仍是正確的防線。
- 平行送出：`lock_tournament` 讓同一賽事的送出排隊，第二個請求在鎖後讀到 `pending` 而回 409。
- API 路徑與架構文件不同：架構寫 `POST /tournaments/{tournament_id}/registrations` → 201（c-d-design-groundwork.md:119-133）。報名在建隊時就已存在（3.1），送出只是轉換狀態，所以改為 `POST /teams/{team_id}/submission` → 200，回傳與其他隊伍操作相同的 `TeamDetail`。
- 送出後隊員改了帳號的學校：快照不變（分配只看快照，AD-12）；S17 不顯示學校，不受影響。
- 非隊員送出沿用「只有隊員可以查看這支隊伍。」：非隊員看不到 S17，只有直接呼叫 API 才會遇到。

## Verification

**Commands:**
- `docker compose up -d --build --wait && docker compose exec -T backend bash scripts/test.sh` -- 全綠，`test_migrations.py` 通過
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- `docker compose exec -T frontend bun run --filter frontend typecheck`、`bunx biome check`、`bun run test:unit` -- 通過

**Manual checks:**
- 瀏覽器（含 375 px）：隊長看到停用原因 → 補齊後送出 → 狀態與倒數；隊員的畫面；已送出隊伍的邀請連結
