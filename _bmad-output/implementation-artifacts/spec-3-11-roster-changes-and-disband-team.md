---
title: 'Story 3.11：隊員異動與解散隊伍'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: 'd12defe8c9e57c66048e435af7d381f50f43d8ed'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-8-review-and-reject-registration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 名單鎖定前，隊長無法移除隊員、轉讓隊長或解散隊伍，隊員也不能自行退出；加錯隊伍或隊員異動時只能卡住，無法完成報名（FR-41）。

**Approach:** registration 新增四個操作：移除隊員、轉讓隊長、退出隊伍、解散隊伍，只在名單未鎖定（沿用 3.8 的 `_roster_unlocked`：`forming` 或 `rejected`）時可用，先鎖賽事再檢查，寫操作紀錄。移除、轉讓、解散發事件，由 notifications 寄站內通知與 Email（FR-37；退出不通知）。前端在 S17 的 Roster list 加 `⋯` 選單與「解散隊伍」（UX-DR34），名單鎖定時不顯示（UX-DR20）。

## Decisions（2026-11-22，邱芯彤；依原規劃，見下方各條出處）

- 解散後保留為「撤回」唯讀（EXPERIENCE.md 狀態表：撤回「組隊中被隊長解散（FR-41）｜唯讀」，S12／S17 看得到）。`TeamMember` 列仍要刪除（FR-41「原隊員可以加入同賽事的其他隊伍」，唯一鍵只看隊員列），另存解散當下的原隊員（帳號與角色）到新資料表，供 S12 卡片與 S17 唯讀頁使用；需要一支遷移。FR-41「所有隊員離開隊伍」與 UX「唯讀可見」的取捨採 UX 的做法，PR 說明寫出。
- 異動的前提只有「名單未鎖定」（FR-41、EXPERIENCE.md〈動作停用條件〉S17 列），不另加報名期間限制；報名截止後仍是 `forming`／`rejected` 的隊伍也能移除、轉讓、退出、解散。
- 3.7 撤回的隊伍（隊員仍佔同賽事一隊）本 Story 不處理，記 deferred-work（FR-41 只規範名單鎖定前）。
- 介面文字採提案（UX-DR15：標題寫動作、內文寫後果、確認鈕重複動作名）：
  - 確認框：移除「{名稱}會離開隊伍，參賽資料一併刪除；之後仍可經邀請連結重新加入。」（destructive）；轉讓「轉讓後{名稱}成為隊長，你會成為一般隊員，不能再送出報名或管理隊員。」；退出「退出後你的參賽資料會一併刪除，之後可以加入這場賽事的其他隊伍。」（destructive）；解散「解散後所有隊員都會離開隊伍、報名改為撤回，邀請連結失效，無法復原。」（destructive）。標題與確認鈕都是動作名稱「移除隊員」「轉讓隊長」「退出隊伍」「解散隊伍」。
  - 成功 Toast「已移除隊員」「已轉讓隊長」「已退出隊伍」「已解散隊伍」；退出與解散成功後導向 S12（`/me/teams`）。
  - 通知（站內＋Email）：被移除「已被移出隊伍」／「你已被隊長移出「{隊名}」（{賽事}）。」，連結賽事頁；轉讓「你成為隊長」／「「{隊名}」（{賽事}）的隊長已轉讓給你。」，連結 `/teams/{id}`；解散「隊伍已解散」／「「{隊名}」（{賽事}）已被隊長解散，報名已撤回。」，收件人為所有原隊員（含隊長本人，FR-37「解散時為所有隊員」），連結 `/teams/{id}`（原隊員看得到唯讀頁）。
- 解散後隊名仍被佔用（`Team` 列保留，與 3.7 撤回一致）。
- 解散後的 S17 唯讀頁：標頭（賽事、隊名、「撤回」徽章）＋「這支隊伍已由隊長解散。」＋原隊員名單（只有名稱與「隊長」徽章，不顯示參賽資料）；邀請連結、送出報名、`⋯` 選單與「解散隊伍」都不顯示。只有解散保留唯讀，被移除或自行退出的帳號看不到原隊伍（403）。
- spec 審查後（2026-11-23，邱芯彤，全部照建議）：
  - `TeamDisbanded` 只帶 `team_id`、`tournament_id`（AD-8：事件不帶收件人清單）；通知規則經 registration 新公開函式查解散名單決定收件人。
  - S29：解散的隊伍在「撤回」組列出原隊員名稱，不顯示「段位截圖」按鈕。被退回的隊伍移除隊員後，S29 平均段位積分仍是上次送出的快照，重送時才更新，接受並在 PR 說明寫出。
  - 賽事狀態：四個操作只在賽事為 `open` 或 `closed` 時可用（同 3.7 撤回）；其他狀態 409 `ROSTER_LOCKED`，S17 不顯示選單與「解散隊伍」。
  - S19 邀請預覽：已解散的隊伍新增邀請狀態 `disbanded`，顯示「隊伍已解散」。
  - 錯誤訊息：非隊員 403 `TEAM_MEMBER_REQUIRED`「你不是這支隊伍的隊員。」；非隊長 403 `TEAM_CAPTAIN_REQUIRED`「只有隊長可以管理隊員或解散隊伍。」；名單已鎖定 409 `ROSTER_LOCKED`「名單已鎖定，無法異動隊員。」；409 `CAPTAIN_CANNOT_REMOVE_SELF`「隊長不能移除自己。」；409 `ALREADY_CAPTAIN`「你已經是隊長。」；409 `CAPTAIN_MUST_TRANSFER`「先轉讓隊長才能退出。」。檢查順序：隊伍存在（404 `TEAM_NOT_FOUND`）→ 鎖賽事 → 賽事狀態 → 隊員 → 隊長 → 名單未鎖定 → 對象。
  - 只有隊長一人的隊伍：隊長自己那列顯示「隊伍只有你一人，要離開請解散隊伍」，取代「先轉讓隊長才能退出」。
  - 維持「解散後保留為撤回唯讀」；EXPERIENCE.md「撤回｜唯讀」也可讀成「沒有可做的動作」，這個解讀的取捨（新資料表與遷移）在 PR 說明寫出。
- 程式審查後（2026-11-23，邱芯彤）：
  - Always 段「解散」的邀請狀態由 `locked` 改為 `disbanded`，與上方 S19 的決定和程式一致（審查 R8）。
  - 非隊員的 403 訊息維持兩種：四個異動操作用「你不是這支隊伍的隊員。」，既有的 `GET /teams/{id}` 沿用「只有隊員可以查看這支隊伍。」，代碼都是 `TEAM_MEMBER_REQUIRED`。
  - 接受建置的替代做法：這台電腦 `docker compose up --build` 會停在 buildx 的檔案讀取權限提示，改用 `docker build` 建映像後 `docker compose up -d --no-build --wait`。

## Boundaries & Constraints

**Always:**
- 四個操作都：`_lock_tournament` 之後依 Decisions 的順序檢查賽事狀態、身分、名單狀態與對象；名單已鎖定或賽事不是 `open`／`closed` 時 409 `ROSTER_LOCKED`，不改任何資料；不檢查報名期間。呼叫者不是隊員 403 `TEAM_MEMBER_REQUIRED`；需要隊長而不是時 403 `TEAM_CAPTAIN_REQUIRED`（`authz.ensure_captain`）；對象帳號不在本隊 404 `TEAM_MEMBER_NOT_FOUND`。
- 移除：隊長移除自己 409 `CAPTAIN_CANNOT_REMOVE_SELF`。刪除該 `TeamMember` 列（參賽資料一併刪除）；段位截圖檔在交易提交後才刪（比照 `update_player_profile` 換截圖的寫法）。人數低於上限後邀請連結恢復有效；不重新產生 `invite_token`，被移除者可再經原連結加入。
- 轉讓：對象是自己 409 `ALREADY_CAPTAIN`。同一交易互換兩人的 `role`；原隊長立即失去隊長權限。
- 退出：隊長退出 409 `CAPTAIN_MUST_TRANSFER`。刪除自己的 `TeamMember` 列與截圖檔；之後可以加入同賽事的其他隊伍。
- 解散：報名轉為 `withdrawn`（`rejected` 時同一交易內先 `mark_status` 到 `forming` 再到 `withdrawn`，不改 `_TRANSITIONS`）；刪除所有 `TeamMember` 列與截圖檔，同一交易把原隊員（帳號、角色）寫入新資料表；保留 `Team` 與 `Registration` 列；原隊員在 S12 看到「撤回」卡片、可開 S17 唯讀頁（不能做任何操作）；邀請連結失效（邀請狀態為 `disbanded`，S19 與 S17 都回這個值；加入仍得 409 `ROSTER_LOCKED`）。`forming`／`rejected` 不佔名額，不呼叫遞補。
- 事件只帶 id（AD-8），但收件人在 worker 處理時已離隊，所以事件帶帳號 id：`TeamMemberRemoved`（team_id、tournament_id、account_id）、`CaptainTransferred`（team_id、tournament_id、from_account_id、to_account_id）、`TeamDisbanded`（team_id、tournament_id；收件人由通知規則查解散名單）。
- 操作紀錄動作：`team.member_removed`、`team.captain_transferred`、`team.member_left`、`team.disbanded`；同步 `LABELED_ACTIONS` 與前端 `AUDIT_ACTION_LABELS`。
- 前端：隊長端每列（自己除外）`⋯` 選單「轉讓隊長」「移除隊員」（後者 destructive）；非隊長在自己那列 `⋯` 選單「退出隊伍」；隊長自己那列 `⋯` 選單只有停用的「先轉讓隊長才能退出」；隊長在名單下方有 destructive outline「解散隊伍」。四個都經 `ConfirmDialog`。

**Never:**
- 不改 3.7 撤回、3.8 退回的語意；不改 `_TRANSITIONS`。
- 不做重設邀請連結、主辦方移除隊員、名單鎖定後的異動（3.11 範圍外）。
- 不讓 service 或 repository commit；不在交易提交前刪除截圖檔。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 移除隊員 | `forming`，隊長移除隊員 B | B 離隊、資料與截圖刪除；`TeamMemberRemoved`；隊伍原本已滿時邀請連結恢復 `active` | N/A |
| 被移除者再加入 | 報名期間內，B 被移除後用原連結加入 | 加入成功，參賽資料為空（報名截止後邀請狀態為 `closed`，無法加入） | N/A |
| 被退回的隊伍異動 | `rejected`，隊長移除、轉讓、解散；隊員退出 | 都成功；解散後報名 `withdrawn`（經 `forming`） | N/A |
| 轉讓隊長 | 隊長 A 轉給 B | A 變 `player`、B 變 `captain`；A 送出報名得 403；B 可以送出；`CaptainTransferred` | N/A |
| 隊員退出 | B 退出 | B 離隊、資料與截圖刪除；可加入同賽事其他隊伍；不發通知 | N/A |
| 解散隊伍 | 隊長解散 | 所有人離隊；報名 `withdrawn`；原隊員可加入同賽事其他隊伍；S12 仍有「撤回」卡片、S17 唯讀；`TeamDisbanded` 的通知寄給全部原隊員（含隊長）；S29 撤回組列出原隊員、無截圖按鈕；S19 預覽「隊伍已解散」 | N/A |
| 截止後異動 | 賽事 `closed`，隊伍仍 `forming`／`rejected` | 四個操作照常可用 | N/A |
| 抽籤後或取消、結束 | 賽事 `published` 以後或 `cancelled`，隊伍 `forming` | 拒絕；S17 不顯示選單與解散 | 409 `ROSTER_LOCKED` |
| 重複解散 | 已解散的隊伍再按解散（原隊員） | 拒絕 | 403 `TEAM_MEMBER_REQUIRED` |
| 隊伍不存在 | 不存在的 team_id | 拒絕 | 404 `TEAM_NOT_FOUND` |
| 只剩隊長一人 | 隊長自己那列 | 顯示「隊伍只有你一人，要離開請解散隊伍」 | N/A |
| 被移除或退出者 | 被移除或自行退出的帳號開 S17 | 不再是隊員，看不到（只有解散保留唯讀） | 403 `TEAM_MEMBER_REQUIRED` |
| 隊長移除或退出自己 | 隊長對自己移除／退出 | 拒絕，不改資料 | 409 `CAPTAIN_CANNOT_REMOVE_SELF`／`CAPTAIN_MUST_TRANSFER` |
| 轉讓給自己或非本隊帳號 | 對象是自己／別隊或不存在的帳號 | 拒絕 | 409 `ALREADY_CAPTAIN`／404 `TEAM_MEMBER_NOT_FOUND` |
| 非隊長操作 | 隊員呼叫移除、轉讓、解散 | 拒絕 | 403 `TEAM_CAPTAIN_REQUIRED` |
| 非隊員操作 | 其他帳號呼叫任一操作 | 拒絕 | 403 `TEAM_MEMBER_REQUIRED` |
| 名單已鎖定 | `pending`／`accepted`／`waitlisted`／`withdrawn`／`drawn` 等 | 拒絕，不改資料；S17 不顯示選單與解散 | 409 `ROSTER_LOCKED` |
| 移除與送出同時 | 隊長送出與移除 B 並行 | 依鎖序：先送出則移除得 409；先移除則送出以移除後的名單判斷 | 409 |
| 解散與加入同時 | 解散與新隊員加入並行 | 先解散則加入得 409 `ROSTER_LOCKED`；先加入則新隊員也被解散並收到通知 | 409 |

</frozen-after-approval>

## Code Map

- 後端 `backend/app/modules/registration/`
  - `service.py`：`_TRANSITIONS`(:219-261，`REJECTED→{FORMING}`、`FORMING→WITHDRAWN` 合法)、`mark_status`(:268)、`_roster_unlocked`(:306-312)、`_max_members`(:315)、`_invite_status`(:319，每次讀取計算，人數降下自動恢復)、`_registration_of`(:344)、`_ensure_can_join`(:350，`ALREADY_IN_TOURNAMENT` 只看 `TeamMember` 列)、`join_team`(:696)、`update_player_profile`(:763，回傳 `ProfileUpdate` 讓 router 提交後刪舊截圖)、`submit_registration`(:891-900，`rejected→forming→pending` 範本)、範本 `withdraw_registration`(:1333：get_team → lock → list_members → 隊員檢查 → `ensure_captain` → refresh → `mark_status` → `_build_detail`)。錯誤 helper：`_team_member_required`(:142)、`_roster_locked`(:148)、`_team_member_not_found`(:206)、`_ensure_registration_period`(:89)。
  - `repository.py`：`get_team`(:40)、`get_membership`(:60)、`get_team_member`(:72)、`list_members`(:83)、`count_members`(:93)、`add_member`(:153)；新增 `delete_member`。
  - `models.py`：`TeamMember`(:86-120，參賽資料在同一列，唯一鍵 (tournament_id, account_id))、事件類別放在 `RegistrationRejected`(:176-206) 旁；新資料表存解散時的原隊員（team_id、tournament_id、account_id、role、created_at），一支 Alembic 遷移。
  - `list_my_teams`(service.py:934，目前只走 `TeamMember`)與 `get_team_detail`(:736，目前要求隊員身分) 要納入解散隊伍的原隊員：S12 卡片「撤回」、`withdrawable` 為 false；S17 唯讀（不回邀請連結、不可操作）。
  - `router.py`：比照 `POST /teams/{team_id}/withdrawal`(:125，`VerifiedAccount`、router commit)、截圖提交後刪除(:98-105)。新路徑：`POST /teams/{team_id}/members/{account_id}/removal`、`POST /teams/{team_id}/captain-transfer`（body `{account_id}`）、`POST /teams/{team_id}/departure`、`POST /teams/{team_id}/disbandment`。移除、轉讓回 `TeamDetail`；退出、解散回 204。不加 `PUBLIC_WRITE_ROUTES`。
- `core/authz.py:34` `ensure_captain`；`core/storage.py:107` `delete_file`（不拋例外）；`core/audit.py:53` `record`。
- registration 新公開函式 `list_disbanded_member_ids(session, *, team_id)`（供解散通知規則查收件人）；S29 `_organizer_items` 對解散隊伍改用解散名單（只回名稱與角色、`has_rank_screenshot=false`），前端 S29 在解散隊伍不顯示「段位截圖」按鈕（`OrganizerRegistration` 加 `disbanded: bool`）。`InviteStatus` 加 `disbanded`，前端 `inviteInvalidReason` 對應「隊伍已解散」。
- `notifications/rules.py`：檔尾新增三條規則（範本 :404-456、`_drafts`(:79)、單一收件人 `_referee_assigned`(:285)）；所有規則都同時發站內與 Email（`notifications/service.py:94-108`）。
- 其他模組（competition、disputes）只在送出或抽籤後讀隊員，名單未鎖定時的異動不影響；轉讓只改 `role`，沒有別處快取隊長。
- 前端 `frontend/src/features/registration/`
  - `RosterList.tsx`：列 :102-142，右欄 :121-142 放「填寫我的資料」，`⋯` 放其後；props 要加 `myRole`、`rosterUnlocked` 與四個 callback。
  - `TeamPage.tsx`：名單區 :137-153；mutation hook 範本 `useWithdrawRegistration.ts:14-40`（`setQueryData` 團隊、invalidate `myTeamsQueryOptions`、`notifySuccess`）；退出與解散成功後 `removeQueries` 團隊 key 並 `navigate` 到 `/me/teams`（否則重抓會顯示 403 頁）。
  - `ConfirmDialog`（`components/common/ConfirmDialog.tsx:22-42`，受控 `open` 不帶 `trigger`；拒絕時對話框內顯示伺服器訊息）；範本 `SubmitRegistrationSection.tsx:279-350`（「退賽」）。
  - 下拉選單 `components/ui/dropdown-menu.tsx`（`DropdownMenuItem variant="destructive"`）；寫法比照 `components/layout/IdentitySwitcher.tsx:46-71`（`aria-label`、`h-touch-target`、內容寬 `w-[min(16rem,calc(100vw-2rem))]`）。專案內還沒有 `⋯` 列選單。
- 名單是否未鎖定：`TeamDetail` 新增 `roster_editable: bool`（後端以 `_roster_unlocked` 等條件計算，與 `withdrawable` 一樣），前端只看這個欄位決定是否顯示 `⋯` 選單與「解散隊伍」。
- 解散的唯讀資料（審查 #1、#11）：
  - 新資料表 `disbanded_team_member`：`id` PK、`team_id`（FK team）、`tournament_id`、`account_id`（索引）、`role`、`joined_at`（原 `TeamMember.created_at`）、`created_at`；唯一鍵 (team_id, account_id)。
  - `TeamDetail` 新增 `disbanded: bool`；`invite_token` 改為 `str | None`（解散時 null，前端 `teamInviteUrl` 處理 null）。解散時 `my_role` 取自新資料表，`members` 取自新資料表（參賽欄位 null、`missing_fields=[]`），`roster_editable`、`withdrawable` 為 false，`submit_blockers=[]`。
  - service 另寫 `_build_disbanded_detail`；`get_team_detail` 的判斷順序：現任隊員 → 解散名單 → 403 `TEAM_MEMBER_REQUIRED`。
  - `list_my_teams`：現任隊伍與解散隊伍合併，依加入時間（解散隊伍用 `joined_at`）新到舊排序；解散隊伍的卡片 `registration_status` 為 `withdrawn`。
  - 前端：`RosterList` 加 `readOnly`（隱藏 caption、完成度、人數與平均段位）；`TeamPage` 在 `disbanded` 時隱藏「邀請隊友」與 `SubmitRegistrationSection`，標頭下顯示「這支隊伍已由隊長解散。」。
- 轉讓的 request body：`CaptainTransfer { account_id: UUID }`；格式錯誤 422。退出、解散回 204；前端四個 hook 成功與失敗時都讓隊伍與 S12 查詢重新取得（範本 `useWithdrawRegistration.ts:31-38` 的 onError），退出與解散成功後先 `removeQueries` 隊伍 key 再導向 S12。
- 操作紀錄 payload（審查 #8，entity 都是 team）：`team.member_removed`／`team.member_left` before `{account_id, role}`、after null；`team.captain_transferred` before `{captain_id: 原隊長}`、after `{captain_id: 新隊長}`；`team.disbanded` before `{member_ids}`、after null。被退回的隊伍解散時，S34 會多出兩筆 `registration.status_changed`（rejected→forming→withdrawn），屬預期。
- 測試：後端 helper `tests/registration/test_teams.py`（`_create_ok`、`_join`、`_auth`、`LockSpy`、`_audit`）、`test_withdraw_registration.py`（`_events`、`_status`、`_card`）、`test_reject_registration.py`（`_reject_ok`）、併發 `test_settlement_concurrency.py:540 _race`、`test_team_concurrency.py:43`；新測試檔加進 `tests/traceability.yaml`。前端 `tests/unit/team-pages.test.tsx`（`TEAM`、`member()`、`mockReadTeam`、3.7 describe :1394-1596）；E2E 範本 `tests/e2e/registration-withdraw.spec.ts`，`support/bulk.ts` 的 `BulkTeam` 不含隊員（新增回傳隊員的函式，不改既有函式）。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py`、`repository.py`、`backend/app/alembic/versions/<新檔>.py` -- 三個事件類別、`delete_member`、原隊員資料表與查詢、`TeamDetail` 的解散唯讀欄位、（若採用）`roster_editable`。
- [x] `backend/app/modules/registration/service.py` -- `remove_member`、`transfer_captain`、`leave_team`、`disband_team`（回傳待刪截圖鍵值給 router）。
- [x] `backend/app/modules/registration/router.py` -- 四個端點，提交後刪截圖檔。
- [x] `backend/app/modules/notifications/rules.py`、`backend/tests/notifications/test_rules.py` -- 三條規則。
- [x] `backend/tests/tournaments/test_audit_action_labels.py`、`frontend/src/features/tournaments/audit-log.ts` -- 四個動作名稱。
- [x] `backend/tests/registration/test_roster_changes.py` -- I/O 矩陣每一列（含加鎖先於檢查、截圖檔刪除）；併發列放 `test_settlement_concurrency.py` 或 `test_team_concurrency.py`。
- [x] `backend/tests/traceability.yaml`（新測試檔，以及有修改的既有測試檔 stories 加 "3.11"）；`scripts/generate-client.sh` 重新產生 client（沒有新路由，不動 routeTree）。
- [x] 前端 `RosterList.tsx`、`TeamPage.tsx`、新 hooks（`features/registration/`）-- `⋯` 選單、解散按鈕、四個確認框、成功後的更新與導頁。
- [x] `frontend/tests/unit/team-pages.test.tsx` -- 選單顯示規則（隊長／隊員／自己那列／鎖定時隱藏／被退回時恢復）、四個操作成功與 409。
- [x] `frontend/tests/e2e/roster-changes.spec.ts`、`support/` 新增函式 -- 隊長移除隊員、轉讓隊長、隊員退出、解散，桌機與 375 px。
- [x] `sprint-status.yaml` 3-11 改 `in-progress`；`deferred-work.md` 新增：3.7 撤回的隊伍隊員仍佔同賽事一隊、無法加入他隊；既有通知規則在 worker 處理時才查隊員，名單異動後收件人可能少於事件發生時。
- [x] `docs/ai-usage/C-邱芯彤.md` -- 依 CLAUDE.md 記錄本 Story 的 AI 使用。

**Acceptance Criteria:**
- Given 名單未鎖定的隊伍，when 隊長在 S17 檢視名單，then 其他隊員那列有 `⋯` 選單「轉讓隊長」「移除隊員」，自己那列只有停用的「先轉讓隊長才能退出」，名單下方有「解散隊伍」；非隊長只在自己那列看到「退出隊伍」。
- Given 名單已鎖定，when 報名被主辦方退回，then 選單與「解散隊伍」恢復顯示。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh`、前端測試與 `@story-3.11` E2E，then 全部通過。

## Implementation Notes

實作（2026-11-23，子代理，待人確認）：

- 後端
  - `models.py`：`DisbandedTeamMember`（`disbanded_team_member`，唯一鍵 (team_id, account_id)、`account_id` 索引）；事件 `TeamMemberRemoved`、`CaptainTransferred`、`TeamDisbanded`；`TeamDetail` 加 `roster_editable`、`disbanded`（有預設值），`invite_token` 改 `str | None`；`InviteStatus` 加 `disbanded`；`OrganizerRegistration` 加 `disbanded`；`CaptainTransfer` body。遷移 `c3e7a9d1f5b2`（`down_revision = "b8d4f2a6c9e1"`）。
  - `service.py`：共同檢查 `_lock_roster_change`（順序同 Decisions）；`remove_member`（回 `RosterChange(detail, deleted_keys)`）、`transfer_captain`、`leave_team`、`disband_team`（後兩者回待刪截圖鍵值）；`_roster_editable`（名單未鎖定且賽事 `open`／`closed`）；`_build_disbanded_detail`；`get_team_detail` 依序現任隊員 → 解散名單 → 403；`list_my_teams` 合併解散隊伍；`preview_invite` 已解散時回 `disbanded`；S29 `_organizer_items` 對解散隊伍列原隊員；公開函式 `list_disbanded_member_ids`。
  - `router.py`：四個端點，`_commit_then_delete` 提交後才刪截圖檔；退出、解散回 204。
  - `notifications/rules.py`：檔尾三條規則；隊名用 `get_team_names` 查（解散後隊伍沒有隊員），隊伍不存在時 `RecipientsNotFound`。
- 實作時自行決定（spec 沒寫）：
  - 非隊員的錯誤訊息只在四個異動操作用「你不是這支隊伍的隊員。」；`GET /teams/{id}` 沿用原本的「只有隊員可以查看這支隊伍。」（同一個代碼 `TEAM_MEMBER_REQUIRED`）。
  - 已解散隊伍的 `TeamDetail.invite_status` 也回 `disbanded`（Always 段寫 `locked`，審查後 Decisions 新增 `disbanded` 狀態；前端唯讀頁不顯示邀請區塊，兩者畫面相同）。
  - S12 合併排序：依加入時間新到舊，同時間時維持各自原本的順序（Python 穩定排序）。
  - S29 解散隊伍：隊名下方顯示「已解散・原隊員：阿哲（隊長）、小芸」，不顯示「段位截圖」。
  - 每列選單按鈕的 aria-label「{名稱}的操作」；「解散隊伍」用 outline＋destructive 文字與框線；轉讓確認鈕不是 destructive（Decisions 只把移除、退出、解散標為 destructive）。
  - 只剩隊長一人時，選單仍顯示（只有一個停用項目「隊伍只有你一人，要離開請解散隊伍」）。
- 跨模組只新增（PR 說明要列）：notifications `rules.py` 的 import 與檔尾三條規則；2.8 的 `AUDIT_ACTION_LABELS`、`test_audit_action_labels.py` 加四個動作；`app/demo_data/registration.py`（`invite_token` 改為可為 null，建隊後取 token 加一個 None 檢查，mypy 要求）；E2E `support/bulk.ts` 新增 `createFormingTeamWithMembers`（不改既有函式）。
- 既有測試：沒有修改既有測試案例；`test_rules.py`、`test_team_concurrency.py`、`team-pages.test.tsx`、`organizer-registrations.test.tsx` 只在檔尾新增案例（另補 import）。
- 新測試：後端 `test_roster_changes.py` 34 個、`test_rules.py` 4 個、`test_team_concurrency.py` 2 個（移除對送出、解散對加入，連跑 3 次都通過）；前端 `team-pages.test.tsx` 12 個、`organizer-registrations.test.tsx` 1 個；E2E `roster-changes.spec.ts` 1 個（desktop、mobile-375）。
- 環境：`docker compose up --build` 在這台機器卡在 buildx bake 的檔案權限提示（`--allow=fs.read=...`），改用 `docker build -f backend/Dockerfile -t flow-backend:latest .`、`docker build -f frontend/Dockerfile -t espory-platform-frontend:latest .` 建映像，再 `docker compose up -d --no-build --wait`。
- 驗證（2026-11-23）：
  - 後端 `scripts/lint.sh` 通過；`scripts/test.sh` 2712 passed（覆蓋率 97%）。
  - 前端 `bunx biome check src tests`、`bunx tsc --noEmit -p tsconfig.json` 通過；`bunx vitest run` 78 檔 1166 passed。
  - E2E `--grep @story-3.11` desktop、mobile-375 共 2 passed；迴歸 `@story-3.7|@story-3.8|@story-3.1 ` 14 passed。
- 未做：`docs/ai-usage/C-邱芯彤.md` 的實作紀錄留給主流程在審查後一併記錄（避免與審查結果重複）。
- 瀏覽器人工檢視後（2026-11-23，使用者要求修正）：375 px 時 `⋯` 選單貼齊螢幕左緣、隊長那列的 `⋯` 被擠到下一行。修法：`RosterList` 每列改為「可換行的名稱與資料區＋固定在右側的 `⋯`」，選單加 `collisionPadding={16}`。重拍截圖確認，前端 vitest 1169 passed、`@story-3.11` E2E 2 passed。

## Spec Change Log

## Review Triage Log

spec 審查（2026-11-23，獨立子代理）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| 1 | 解散唯讀頁的 API 形狀未定義（`invite_token`、`my_role` 必填，`_build_detail` 需要 TeamMember） | high | 已修正：Code Map 定義 `disbanded`、`_build_disbanded_detail`、前端 readOnly |
| 2 | `TeamDisbanded(member_ids)` 違反 AD-8 | high | 使用者決定：只帶 id，規則查解散名單 |
| 3 | 既有通知規則在 worker 時才查隊員，名單異動後收件人變少 | medium | 已寫 Design Notes，記 deferred |
| 4 | S29 解散隊伍空名單、截圖已刪；移除後平均段位是舊快照 | medium | 使用者決定：列原隊員、隱藏截圖按鈕；快照接受 |
| 5 | 抽籤、取消、結束後的 forming 隊伍仍可異動；重新加入只在報名期間成立 | medium | 使用者決定：限 `open`／`closed`；矩陣補前提 |
| 6 | S19 對解散隊伍顯示「名單已鎖定」 | medium | 使用者決定：新增 `disbanded` 狀態 |
| 7 | 錯誤檢查順序與訊息未定義 | medium | 使用者決定：訊息與順序寫入 Decisions，矩陣補列 |
| 8 | 操作紀錄 before/after 未定義 | medium | 已修正：Code Map |
| 9 | 前端失敗處理與解散回傳型別 | medium | 已修正：onError 重抓、退出解散回 204 |
| 10 | `roster_editable` 二選一留給實作者 | low | 已定為後端欄位 |
| 11 | 新資料表、排序、request body 未定義 | low | 已修正 |
| 12 | 解散後隊伍無隊員，與 D-3、ER 圖不一致 | low | Design Notes 與 PR 說明 |
| 13 | 只剩隊長一人時的文字 | low | 使用者決定：「隊伍只有你一人，要離開請解散隊伍」 |
| 14 | traceability 既有檔、AI 紀錄任務缺漏 | low | 已補 Tasks |
| 15 | 行號小誤 | low | 已修正 |
| 16 | 「撤回｜唯讀」的解讀成本 | low | 使用者決定維持；PR 說明寫取捨 |

程式審查（2026-11-23，三個獨立子代理：Blind Hunter、Edge Case Hunter、Verification Gap）：

| # | 來源 | 發現 | 判定 | 證據 | 去向 |
|---|------|------|------|------|------|
| R1 | Edge | 被移除者在 worker 處理前經原連結重新加入，仍收到「已被移出隊伍」 | low | 時間窗極短，且通知描述的移除確實發生過；修法要在規則加守衛 | 駁回 |
| R2 | Edge | 轉讓後在 worker 處理前又轉回或解散，新隊長仍收到「你成為隊長」 | low | 同 R1，通知描述的是已發生的事件 | 駁回 |
| R3 | Edge | 退出／解散成功時先 `removeQueries` 再 `navigate`（未 await）；ConfirmDialog 關閉觸發 `setRosterAction(null)` 重繪 TeamPage，觀察者重建查詢並再送一次 `GET /teams/{id}`（退出後 403），可能閃出骨架或錯誤頁 | medium | ConfirmDialog.tsx `confirm()` 在 `onConfirm` resolve 後才 `setOpen(false)`；導頁是非同步。Code Map 指定的順序達不到它寫的目的（避免 403 頁） | patch：先導頁、完成後才移除快取 |
| R4 | Edge | demo_data 註解誤稱解散會清掉資料庫的 token | false | 註解指的是 `create_team` 回傳的 `TeamDetail.invite_token`（型別可為 null），沒有提到資料庫 | 駁回 |
| R5 | VerifGap | 前端四個操作紀錄名稱沒有測試 | medium | 後端測試只比對自己的副本；`audit-log.test.tsx` 沒有 `team.*` | patch |
| R6 | VerifGap | 退出、解散、轉讓的 409 失敗路徑沒有測試 | medium | 唯一的 409 案例只測 `removeTeamMember` | patch |
| R7 | Blind | 解散後用舊預覽按加入，得到「名單已鎖定」而非「隊伍已解散」 | false | 凍結矩陣「解散與加入同時」明定 409 `ROSTER_LOCKED` | 駁回 |
| R8 | Blind | 凍結區 Always 寫 `_invite_status` 為 `locked`，與 Decisions 的 `disbanded` 矛盾 | low | 屬實，但修法是改 spec 凍結區，只有人能改 | 使用者決定：Always 改為 `disbanded`（見 Decisions） |
| R9 | Blind | sprint-status 仍是 in-progress，spec 已 in-review | false | 工作流程在完成步驟才同步 sprint-status | 駁回 |
| R10 | Blind | AI 使用紀錄任務未勾 | false | 依計畫在審查後撰寫，避免記兩筆 | 駁回 |
| R11 | Blind | E2E 標了 `@FR-37` 卻沒有檢查通知 | low | 屬實；identity.spec.ts 與 test_rules.py 已涵蓋 FR-37，移除標籤即可 | patch |
| R12 | Blind | 沒有測試先離隊者不在解散名單 | false | `disband_team` 只寫入 `locked.members`（當下隊員），先離隊者不可能被寫入 | 駁回 |
| R13 | Blind | 原隊員加入他隊後 S12 兩張卡片與排序沒有測試 | low | `test_my_teams_merges_disbanded_teams_by_join_time` 已測合併排序；剩下的組合不會走到新程式路徑 | 駁回 |
| R14 | Blind | 未知隊伍的通知測試只測一種事件 | low | 三條規則都經 `_team_label` 拋 `RecipientsNotFound`，同一條路徑 | 駁回 |
| R15 | Blind | 「已解散」由解散名單推得，沒有旗標；`MyTeamCard` 無 `disbanded`；`tournament_id` 沒被讀 | false | 資料表欄位與 S12 卡片顯示「撤回」都是 Code Map 指定 | 駁回 |
| R16 | Blind | service 回傳型別不一致（`RosterChange` 與 `list[str]`） | low | 只影響可讀性，router 呼叫端各自正確 | 駁回 |
| R17 | Blind | `team.disbanded` 的 before 沒有角色 | low | Code Map 指定 `{member_ids}`；修法是改 spec | 駁回 |
| R18 | Blind | `RosterActionDialog` 一次建立四個 mutation hook | low | 只是多建幾個閒置的 hook，沒有可見影響 | 駁回 |
| R19 | Blind | E2E 註解「4 人裝不下」把賽事名額（capacity）誤寫成人數 | low | `createOpenTournamentByApi` 第三個參數是 `capacity`；改註解即可 | patch |
| R20 | Blind | 退出或解散後在導頁前可能重抓隊伍頁（與 R3 同一根因：removeQueries 與導頁的順序） | medium | 同 R3 | patch（併入 R3） |

## Design Notes

- 解散與退出必須刪除 `TeamMember` 列：`ALREADY_IN_TOURNAMENT` 與資料庫唯一鍵只看隊員列，保留列就無法加入他隊。
- 通知 resolver 在 worker 處理時查資料庫，那時被移除或解散的隊員已不在隊上，所以收件人帳號 id 放在事件 payload，不用 `_member_ids`。
- 截圖檔在交易提交後才刪：提交失敗時不會留下指向已刪檔案的資料列（比照 `update_player_profile`）。
- 既有通知規則在 worker 處理時才以 `_member_ids` 查隊員（rules.py:86-89）：主辦方退回後、worker 處理前隊長就移除隊員或解散，`RegistrationRejected`、`RegistrationAllocated` 等只會寄給處理當下仍在隊上的人（解散則沒人收到）。本 Story 不改既有規則，記 deferred-work（審查 #3）。
- 解散後隊伍沒有任何 `TeamMember`，與 D-3「每隊恰好一位 captain」、期中 ER 圖 `TEAM ||--|{ TEAM_MEMBER` 不一致，新資料表也不在期中 25 張表內；PR 說明寫出，`docs/` 依規定不在本 PR 修改（審查 #12）。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- frontend 容器內 `bunx vitest run`、`bunx biome check`、`bunx tsc --noEmit -p tsconfig.json` -- 通過
- `docker compose --profile e2e run --rm e2e bunx playwright test --grep @story-3.11` -- 通過
