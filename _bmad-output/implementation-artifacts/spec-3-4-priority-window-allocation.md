---
title: 'Story 3.4（第二階段）：優先期結束自動分配'
type: 'feature'
created: '2026-11-04'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '3326ce378f52bc37ba9815bef5a051f4f97aba2b'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-3-submit-registration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3.3 送出後報名一律停在「已送出・待分配」。`allocation.py` 已經有優先期結算的純函式（第一階段），但還沒有任何東西在優先期結束時呼叫它，S17、S12 也看不到正取、候補順位與原因。

**Approach:** 新增 worker 工作：優先期結束後 1 分鐘內鎖住賽事，對優先期內送出的待分配報名呼叫 `allocate_priority_window`，再用 `mark_status` 改狀態，並保存「優先期有報名的學校」，重複執行結果不變。S17、S12 的回應加上候補順位與原因，前端照 EXPERIENCE.md 顯示。

## Decisions（2026-11-04，邱芯彤）

- 3.4～3.6 第二階段拆成三個 Story，依 3.4 → 3.6 → 3.5 的順序做；3.5、3.6 已記入 deferred-work。本 Story 從 main 開 `story/3-4-phase2`，並帶入 #28 審查修正的 `backfill_vacancies`（commit `df2243d`）。
- 候補狀態的「當下階段遞補規則說明」（EXPERIENCE.md:297）選 (乙)：新增兩則固定字串，顯示在候補徽章與原因下方，依階段切換；同步加入 EXPERIENCE.md〈固定介面字串〉。
  - 先搶期：「先搶期由優先期沒有報名、目前也沒有正取的學校，依送出先後遞補。」
  - 報名截止後：「報名截止後依平均段位積分由高到低遞補，每校最多 2 隊正取。」
- spec 約 2,500 tokens，保留完整 spec，前端顯示不另拆 Story。
- 完全沒有送出報名的賽事，worker 不寫結算紀錄（選 (甲)，維持實作），避免 worker 每一輪讀取全部賽事。原本 Boundaries 寫「沒有任何報名的賽事也要寫結算紀錄」，與 Design Notes 的候選來源矛盾，已改寫 Boundaries 與 I/O 矩陣。確認過沒有影響：只有 registration 自己讀結算表；3.6 的截止補位用 `fill_from_waitlist`（`priority_schools=()`），不需要結算紀錄；3.5 的先搶期判定在沒有紀錄時以空集合計算，結果與空紀錄相同；4.1 抽籤只經 registration 的公開函式（`competition/registration_port.py`：`finalize_for_draw`、`list_accepted_teams`、`mark_drawn`，registration 目前都還沒提供，抽籤回 503）。後續規則：3.5、3.6、`fill_at_deadline`／`finalize_for_draw` 需要「優先期已結算」時，在鎖內呼叫 `settle_priority_window`（重複呼叫結果不變，必要時會寫空紀錄），不要用「有沒有結算紀錄」判斷。
- 保留 API 欄位 `waitlist_phase`（`first_come`／`after_deadline`，只在候補時有值）：S12 的 `MyTeamCard` 沒有報名截止時間，畫面依它切換兩則遞補規則說明，階段由後端依 `clock.now()` 判斷。`waitlist_reason` 只回原因代碼，介面文字由前端常數負責顯示，前端測試逐字比對 EXPERIENCE.md。（實作時提出，2026-11-04 邱芯彤正式確認）
- S12 卡片的候補說明改放在「賽事名＋隊名＋右側徽章」那一列的下方、用卡片全寬（桌機與手機相同）。瀏覽器實測發現 375 px 時長徽章「候補・目前不在遞補順序中」占約 170 px，說明欄只剩約 100 px、卡片被拉長到約 350 px；另兩個選項（手機上徽章換到隊名下、維持現狀）未採用。（2026-11-04 邱芯彤決定）

## Boundaries & Constraints

**Always:**
- 結算對象：狀態為 `open`、模式 `campus`、`priority_end <= clock.now()`、尚未結算的賽事。只有 `pending` 且 `submitted_at <= priority_end` 的報名參加結算；優先期後送出的 `pending`（3.5 尚未接上）維持原狀。
- 結算在同一個 `lock_tournament()` 鎖與交易內完成：鎖內重新檢查條件 → 呼叫 `allocate_priority_window` → 逐筆 `mark_status` → 寫結算紀錄（保存優先期有報名的學校＝參加結算報名的學校集合，可為空）。已有結算紀錄就不再處理，所以重複執行結果不變。worker 只處理有 `pending` 報名的賽事：優先期內沒有待分配報名、但有優先期後送出的 `pending` 時，寫空的結算紀錄；完全沒有送出報名的賽事 worker 不處理，直接呼叫 `settle_priority_window` 時才寫空紀錄。沒有結算紀錄時「優先期有報名的學校」視為空集合。
- 操作紀錄：每筆狀態變更由 `mark_status` 記錄（actor 為 system＝`None`），另外寫一筆結算摘要（名額、正取與候補 id）。
- 每筆被分配的報名發一個 outbox 事件（帶報名 id、隊伍 id、賽事 id、結果狀態），3.5、3.6 會沿用。
- S17（`TeamDetail`）、S12（`MyTeamCard`）回應新增候補順位、無順位原因、代表隊補充旗標，只在 `waitlisted` 時有值。階段依當下時間判斷：報名截止前為先搶期，之後為截止後；`priority_schools` 取自結算紀錄。順位只由 `waitlist_order` 計算。
- 前端只用重新產生的 client；介面字串與 `REASON_MESSAGES`、`REPRESENTATIVE_BACKFILL_MESSAGE`、EXPERIENCE.md:199-205 逐字相同。

**Never:**
- 不改 tournaments、competition 既有函式，也不新增 tournaments 的函式（registration 只呼叫既有的 `get_tournament`、`lock_tournament`）。
- 不做先搶期送出判定（3.5）、截止補位與 `fill_at_deadline`（3.6）、退賽、撤回、通知規則。
- 不做自訂模式。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 40 校搶 32 名 | 優先期結束，40 校各 1 隊待分配 | 正取 32、候補 8；8 隊候補沒有順位，原因 `SCHOOL_NOT_ELIGIBLE` | N/A |
| 同校 3 隊 | 同校 3 隊待分配、名額足夠 | 1 隊正取、2 隊候補；候補附代表隊補充旗標 | N/A |
| 重複執行 | 已結算後 worker 再跑 | 狀態、操作紀錄、事件都不增加 | N/A |
| 優先期未到 | `priority_end > now` | 不處理 | N/A |
| 優先期後送出 | 優先期後送出、狀態仍為 `pending` | 不參加結算，維持 `pending` | N/A |
| 優先期內沒有報名 | 優先期結束時，優先期內沒有待分配報名，只有優先期後送出的 `pending` | 寫空的結算紀錄，不發事件 | N/A |
| 完全沒有報名 | 優先期結束時沒有任何送出的報名 | worker 不處理、不寫結算紀錄；直接呼叫 `settle_priority_window` 則寫空紀錄，不發事件 | N/A |
| 賽事已取消 | 狀態不是 `open` | 不處理 | N/A |
| 顯示正取 | `accepted` | S17、S12 顯示「正取」；S17 顯示報名截止倒數 | N/A |
| 顯示候補 | `waitlisted` 有順位／無順位 | 「候補第 N 位」，或「候補・目前不在遞補順序中」＋原因（＋補充） | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/worker/jobs.py:56` -- `JOBS` 有順序，新工作放在 `dispatch_outbox` 之前；job 不能 commit（`tests/test_architecture.py:36`）
- `backend/app/worker/__init__.py:23-52` -- `Job = Callable[[Session], bool]`；`run_once` 會重複呼叫，直到回傳 False，所以找不到到期的賽事時要回傳 False
- `backend/app/modules/tournaments/service.py:520` `open_due_registration` -- 範本：先不加鎖找候選 → `lock_tournament` → 鎖內重新檢查 → 處理；`:394` `get_tournament`、`:402` `lock_tournament`
- `backend/app/modules/registration/service.py:215` `mark_status`（參數是 row，會寫 `registration.status_changed`）；`:166-208` 轉換表（pending→accepted／waitlisted 合法）；`:638` `submit_registration`（3.3，不改行為）；`:728` 起是公開函式
- `backend/app/modules/registration/repository.py` -- 新增：列出「有 pending、尚未結算」的賽事 id，以及依賽事列出報名
- `backend/app/modules/registration/models.py:109` `Registration`（`school_id`、`avg_rank_score`、`submitted_at` 是送出時的快照）；`:199` `TeamDetail`、`:246` `MyTeamCard` 要加欄位
- `backend/app/modules/registration/allocation.py` -- `Candidate`、`allocate_priority_window`、`waitlist_order`、`REASON_MESSAGES`；不改規則
- `backend/app/core/audit.py:53` `record(actor_id=None …)`；`backend/app/core/events.py:58` `publish`，事件類別用 PascalCase 過去式（例如 `RegistrationAllocated`），registration 目前沒有事件類別
- `backend/app/alembic/versions/` -- head 是 `d7e2a5c9b4f1`；新增一支遷移建結算表（`tournament_id` 為主鍵、`settled_at`、優先期學校 id 陣列）
- `backend/tests/worker/test_open_registration.py`、`test_judge_forfeits.py` -- worker 測試範本（`session_factory`、`frozen_clock`、`run_once`、查 `OutboxEvent`、`audit.list_for_tournament`、`job in JOBS`）；`tests/helpers.py` 的 `make_tournament`
- `frontend/src/features/registration/registration-status.tsx:5-37` -- `RegistrationStatusBadge` 只能依 status 顯示文字，要能顯示「候補第 N 位」
- `frontend/src/features/registration/SubmitRegistrationSection.tsx:241-252` -- 依狀態分派；`accepted` 要加報名截止倒數（沿用 `Countdown`、`deadlineVariant`）
- `frontend/src/features/registration/TeamPage.tsx:81-89`（標頭徽章下方加原因）、`RegistrationStatusCard.tsx:9-11`（S12 卡片）
- `frontend/tests/unit/team-pages.test.tsx`（`mockReadTeam`、S12 的 `listMyTeams`）、`registration-components.test.tsx`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py`、新遷移檔 -- 結算表；`TeamDetail`、`MyTeamCard` 加 `waitlist_position`、`waitlist_reason`、`representative_backfill`；事件類別 `RegistrationAllocated`
- [x] `backend/app/modules/registration/repository.py`、`service.py` -- `allocate_due_priority_window(session) -> bool`（worker 用，每次處理一個賽事）、`settle_priority_window(session, *, tournament_id)`（鎖內結算，3.6 會沿用）；讀取時計算候補順位
- [x] `backend/app/worker/jobs.py` -- 註冊工作
- [x] `backend/tests/` -- worker 整合測試（I/O 矩陣每一列、`frozen_clock` 推進、重複執行不變、`job in JOBS`）；S17、S12 API 回傳順位與原因
- [x] `frontend/src/client` -- 以 `scripts/generate-client.sh` 重新產生
- [x] `frontend/src/features/registration/*` -- 候補徽章文字、原因與補充、階段遞補規則說明、正取時的報名截止倒數；單元測試
- [x] `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:199-205` -- 〈固定介面字串〉新增兩則階段遞補規則說明（字串見 Decisions），並在第 297 行指向它們；`epic-3-context.md`〈UX〉的狀態呈現同步提一句。兩個檔案放在同一個 commit，context 才不會被判定過期
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 source_spec 為 `spec-3-4-allocation-policy.md` 的「Story 3.4～3.6 第二階段」項目：3.4 的部分由本 Story 完成，3.5、3.6 已另有新項目。刪除前確認項目裡的「抽籤後狀態名稱與 `drawn` 一致」這項檢查，已寫進 3.6 項目；沒寫到就在檔尾新增一項補上

**Acceptance Criteria:**
- Given 優先期已結束的賽事，when 以 `frozen_clock` 推進時間並執行 worker，then 結果符合 `allocate_priority_window`，再跑一次狀態、操作紀錄、事件都不變。
- Given 結算後，when 隊伍成員打開 S17 或 S12，then 顯示的文字與 EXPERIENCE.md 的固定字串完全相同。
- Given 後端，when 執行 `scripts/test.sh`、`lint.sh` 與前端 typecheck、biome、單元測試，then 全部通過；`test_migrations.py` 通過。

## Implementation Notes

- 遷移 `b5c8e2f4a1d7_story_3_4_priority_window_settlement.py`（`down_revision = "d7e2a5c9b4f1"`）：`priority_window_settlement`（`tournament_id` 主鍵＋外鍵、`settled_at`、`priority_school_ids uuid[]`，學校 id 依大小排序存）。
- service：`settle_priority_window(session, *, tournament_id) -> bool`（回傳這次是否結算；已結算、賽事不是開放中的校園賽、優先期未結束時回 False，不拋錯）；`allocate_due_priority_window(session) -> bool`（worker 用）。worker 工作名稱 `allocate_priority_windows`，排在 `open_registrations` 之後、`start_due_tournaments` 之前。
- 操作紀錄：每筆 `registration.status_changed`（`mark_status`，actor `None`），另一筆 `registration.priority_window_settled`（entity 為賽事，`after` 含 `capacity`、`accepted`、`waitlisted`、`priority_school_ids`）。事件 `RegistrationAllocated`（`registration_id`、`team_id`、`tournament_id`、`status`），notifications 目前沒有處理者，分派時記錄後略過。
- 實作子代理自訂的解讀（spec 未寫明）：
  - API 除了 spec 列的三個欄位，另加 `waitlist_phase`（`first_come`／`after_deadline`，只在候補時有值）：S12 的 `MyTeamCard` 沒有報名截止時間，畫面要靠它切換兩則遞補規則說明；階段由後端依 `clock.now()` 判斷，不看裝置時間。
  - `waitlist_reason` 回原因代碼（`SCHOOL_NOT_ELIGIBLE` 等），介面字串放在前端 `registration-status.tsx`（`WAITLIST_REASON_MESSAGES`、`REPRESENTATIVE_BACKFILL_MESSAGE`、`WAITLIST_PHASE_RULES`），前端單元測試逐字比對 EXPERIENCE.md；models 用 `Literal`（allocation 會 import models，不能反向 import enum），後端測試檢查 `Literal` 與 enum 的值相同。
  - 「沒有任何報名的賽事也要寫結算紀錄」：worker 依 Design Notes 只從「有 `pending`、尚未結算」的賽事找候選，所以完全沒有送出報名的賽事 worker 不會處理（沒有 `pending` 就沒有要分配的報名）；只有優先期後送出的 `pending` 時，worker 會寫空的結算紀錄。直接呼叫 `settle_priority_window`（3.6 會用）時，沒有任何報名也會寫空紀錄。
  - 候補順位計算時，正取包含 `accepted`、`drawn`，候補為 `waitlisted`；其他狀態不算。結算前沒有結算紀錄時 `priority_schools` 視為空集合。
  - 正取的報名截止倒數放在 S17「名額分配」區塊，沿用 `Countdown`＋`deadlineVariant`；歸零後顯示靜態「已截止」不輪詢，開啟頁面時已截止則不顯示（與優先期倒數同一寫法）。
  - 候補說明在 S17 放在標頭徽章下方，在 S12 放在卡片隊名下方；S12 卡片整張是連結，說明用 `span`。
- 動到其他組員的測試（只為了新欄位與新工作，不改行為）：`backend/tests/worker/test_email_pipeline.py` 的 `test_jobs_are_registered_in_order` 加入 `allocate_priority_windows`；`frontend/tests/unit/tournament-create-team.test.tsx` 的 `TEAM`、`MY_TEAM` fixture 補四個 null 欄位。PR 說明要列出。
- 驗證（2026-11-04）：後端全套 1879 passed（含 `test_migrations.py`、`test_architecture.py`），`scripts/lint.sh`（mypy、ty、ruff）通過；前端 `typecheck`、`biome check` 通過，`test:unit` 全跑 732 個中 729～730 個通過，失敗的是 `organizer-tournaments`、`admin-games`（每次不同、單獨重跑全過，屬全量平行時的路由載入逾時，與本 Story 無關），本 Story 動到的三個測試檔單獨跑 96 個全過。`docker compose up -d --build --wait` 後開發資料庫已升到 `b5c8e2f4a1d7`，worker 以 7 個工作啟動、沒有錯誤。瀏覽器手動檢查尚未執行。
- 前端不穩定的原因（2026-11-04 複查）：`main`（`1d73956`，#47）全量 761 個全過；本分支開在 #47 之前，少了 `tests/unit/setup.ts` 的 `asyncUtilTimeout: 5000`（預設 1 秒，路由延遲載入第一次渲染就要約 3.7 秒）與 `vitest.config.ts` 的 `testTimeout: 15000`。本分支沒有這兩處時，全量跑三次分別失敗 8～15 個（全是路由載入的 `Unable to find`，每次不同，沒有本 Story 的測試檔）；在複製版本套上 `main` 的這兩個檔後，732 個全過。合併 `origin/main` 後就會帶入。
- 補測試 `test_worker_skips_tournament_without_any_submission`（I/O 矩陣「完全沒有報名」）；後端全套 1880 passed。
- 審查修正後合併 `origin/main`（`cd0cce8`，#46～#48，`--no-commit`，無衝突；重新產生的 client 與合併結果相同）：後端 1913 passed、覆蓋率 97%，lint 通過；前端 typecheck、biome 通過，單元測試 798 個全過。
- 瀏覽器實測（2026-11-04，Playwright，桌機與 375 px，8 個情境全過）：在開發資料庫建兩場名額 3 的校園賽（先搶期、截止後），4 校 6 隊直接寫成「已送出・待分配」，由實際的 worker 在 20 秒內結算（各 1 筆摘要、6 筆狀態變更、合計 12 個事件）。以 4 個帳號登入檢查 S12 卡片與 S17：正取、「候補第 1／2 位」、「候補・目前不在遞補順序中」＋ `SCHOOL_NOT_ELIGIBLE`／`SCHOOL_LIMIT_REACHED` 原因、代表隊補充、兩則階段規則說明逐字相同；正取在報名截止前顯示「名額分配」倒數、截止後不顯示；沒有橫向捲軸。另一場既有賽事的報名沒有送出快照，worker 在優先期結束後 14 秒寫入空的結算紀錄，該報名維持 `pending`，worker 沒有錯誤。看截圖發現 S12 在 375 px 的版面問題，依 Decisions 修正後重跑全過。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-04，Blind Hunter＝B、Edge Case Hunter＝E、Verification Gap＝V）：

| # | 發現 | 判定 | 處理 | 證據 |
|---|------|------|------|------|
| V1 | 多場賽事測試的 id 隨機，未到期候選只有約 1/3 機率排在前面 | medium | patch | 候選依 `tournament_id`（uuid4）排序；「遇到未到期就停」的回歸約 2/3 次仍會通過 |
| B6 | 沒有測試「非校園賽不結算」 | low | patch | `_priority_window_due` 有檢查 `mode`，測試只 parametrize 狀態；補一個直接的測試 |
| B15 | 刪舊 deferred 項目時，「`pending` 不能被 `fill_from_waitlist` 漏掉」沒轉移到 3.6 | medium | patch | 新 3.6 項目沒有這句；順序是 3.4 → 3.6 → 3.5，3.6 時優先期後送出的仍為 `pending`；已在 deferred-work 檔尾新增 |
| E3 | 賽事在 worker 結算前離開 `open`，優先期內 `pending` 永遠不分配 | medium（目前不會發生） | defer | 離開 `open` 的路徑是取消（不需分配）與抽籤；抽籤需要的 `finalize_for_draw` 尚未提供（回 503）。與 B15 合為同一則 deferred |
| V2 | `drawn` 當正取沒有從 API 層測試 | medium | defer | 純函式層有測；目前沒有正式程式會產生 `drawn` |
| E1 | `submitted_at == priority_end` 且結算剛好在同一刻先執行時漏掉 | low | reject | 兩者都在同一個賽事鎖內，要同一微秒才會發生；邊界 `<=` 是凍結規則 |
| E2／B5 | 已取消或非校園賽留有 `pending` 時，worker 每輪都重查 | low | reject | 每場一次 `get_tournament`，Design Notes 已接受期中規模的額外查詢；修正要新增 tournaments 函式或標記 |
| E4／B7 | 讀取路徑遇到缺快照的報名會 500 | false | reject | 只有 `pending` 經 `submit_registration`（必寫快照）才會進入 accepted／waitlisted／drawn，沒有路徑會產生缺快照的這些狀態 |
| E5／B7／B14 | 已取消或自訂模式賽事的候補仍顯示校園賽順位與規則 | low | reject | 自訂模式目前不會有候補（不做自訂模式）；取消後仍有候補不常見，修正要新增分支，spec 也沒定義 |
| E6／B8 | `list_my_teams` 的 N+1 查詢 | low | reject | 同一帳號在同一賽事只能有一支隊伍（`uq_team_member_tournament_id_account_id`），不會重複計算；每張候補卡多兩次查詢 |
| E7 | 3.6 還沒接上時，截止後就依時鐘顯示截止後規則 | false | reject | 凍結規則明定「階段依當下時間判斷」 |
| V-o | 某場結算拋錯會擋住後面的賽事 | false | reject | 只有缺快照的壞資料會拋錯，同 E4 不會發生 |
| B1 | 改了凍結區塊，Spec Change Log 卻是空的 | reject | reject | 修正要改本 spec；變更由使用者核准並記在 Decisions，Change Log 只記錄審查回圈 |
| B2 | Implementation Notes 有過時、重複的內容 | reject | reject | 修正要改本 spec |
| B3 | 還沒做瀏覽器手動檢查 | low | reject | 不是程式缺陷，在 step-05 告知使用者 |
| B4 | 審查用的 diff 沒有收錄 `types.gen.ts` | false | reject | 產生檔刻意排除；合併 main 後會重新產生並跑 typecheck |
| B9 | 沒有驗證沒有處理者的事件會被略過 | false | reject | `notifications/service.py:62` 記錄後略過，`test_email_delivery.py:213` 有測 |
| B10 | 原因字串有三份，沒有交叉檢查 | low | reject | 後端與前端各自有逐字測試；跨專案比對要新增讀取 planning 文件的測試基礎設施 |
| B11 | 原因與先搶期規則兩句話幾乎重複 | false | reject | EXPERIENCE.md 與 Decisions 規定兩種候補都附規則說明，原因字串是固定介面字串 |
| B12 | 沒有測正取倒數在畫面中歸零 | low | reject | 與既有的優先期倒數同一寫法；補假計時器測試的成本高於風險 |
| B13 | 優先期後送出的隊伍只看到「待分配」，沒有說明 | low | reject | 本 Story 依凍結規則維持 `pending`，由 3.5 的 deferred 項目處理 |

## Design Notes

為什麼不新增 tournaments 的查詢：registration 不能直接查賽事表（`tests/test_architecture.py:22-34`）。結算表本身就是「已結算」標記，worker 從「有 `pending`、尚未結算」的賽事裡，用 `get_tournament` 檢查哪些已經到期。目前期中規模，每分鐘多幾次查詢可以接受，而且不用動 B 的模組。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose run --rm --no-deps -T backend bash -c "bash scripts/test.sh"` -- 全綠
- `docker compose run --rm --no-deps -T backend bash scripts/lint.sh` -- 通過
- 前端容器內 `bun run typecheck`、`bunx biome check`、`bun run test:unit` -- 通過
