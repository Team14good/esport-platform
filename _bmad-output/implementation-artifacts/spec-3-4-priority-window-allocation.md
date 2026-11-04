---
title: 'Story 3.4（第二階段）：優先期結束自動分配'
type: 'feature'
created: '2026-11-04'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
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

## Boundaries & Constraints

**Always:**
- 結算對象：狀態為 `open`、模式 `campus`、`priority_end <= clock.now()`、尚未結算的賽事。只有 `pending` 且 `submitted_at <= priority_end` 的報名參加結算；優先期後送出的 `pending`（3.5 尚未接上）維持原狀。
- 結算在同一個 `lock_tournament()` 鎖與交易內完成：鎖內重新檢查條件 → 呼叫 `allocate_priority_window` → 逐筆 `mark_status` → 寫結算紀錄（保存優先期有報名的學校＝參加結算報名的學校集合，可為空）。已有結算紀錄就不再處理，所以重複執行結果不變。沒有任何報名的賽事也要寫結算紀錄。
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
| 沒有報名 | 優先期結束時沒有待分配報名 | 寫空的結算紀錄，不發事件 | N/A |
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
- [ ] `backend/app/modules/registration/models.py`、新遷移檔 -- 結算表；`TeamDetail`、`MyTeamCard` 加 `waitlist_position`、`waitlist_reason`、`representative_backfill`；事件類別 `RegistrationAllocated`
- [ ] `backend/app/modules/registration/repository.py`、`service.py` -- `allocate_due_priority_window(session) -> bool`（worker 用，每次處理一個賽事）、`settle_priority_window(session, *, tournament_id)`（鎖內結算，3.6 會沿用）；讀取時計算候補順位
- [ ] `backend/app/worker/jobs.py` -- 註冊工作
- [ ] `backend/tests/` -- worker 整合測試（I/O 矩陣每一列、`frozen_clock` 推進、重複執行不變、`job in JOBS`）；S17、S12 API 回傳順位與原因
- [ ] `frontend/src/client` -- 以 `scripts/generate-client.sh` 重新產生
- [ ] `frontend/src/features/registration/*` -- 候補徽章文字、原因與補充、階段遞補規則說明、正取時的報名截止倒數；單元測試
- [ ] `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:199-205` -- 〈固定介面字串〉新增兩則階段遞補規則說明（字串見 Decisions），並在第 297 行指向它們；`epic-3-context.md`〈UX〉的狀態呈現同步提一句。兩個檔案放在同一個 commit，context 才不會被判定過期
- [ ] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除 source_spec 為 `spec-3-4-allocation-policy.md` 的「Story 3.4～3.6 第二階段」項目：3.4 的部分由本 Story 完成，3.5、3.6 已另有新項目。刪除前確認項目裡的「抽籤後狀態名稱與 `drawn` 一致」這項檢查，已寫進 3.6 項目；沒寫到就在檔尾新增一項補上

**Acceptance Criteria:**
- Given 優先期已結束的賽事，when 以 `frozen_clock` 推進時間並執行 worker，then 結果符合 `allocate_priority_window`，再跑一次狀態、操作紀錄、事件都不變。
- Given 結算後，when 隊伍成員打開 S17 或 S12，then 顯示的文字與 EXPERIENCE.md 的固定字串完全相同。
- Given 後端，when 執行 `scripts/test.sh`、`lint.sh` 與前端 typecheck、biome、單元測試，then 全部通過；`test_migrations.py` 通過。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

為什麼不新增 tournaments 的查詢：registration 不能直接查賽事表（`tests/test_architecture.py:22-34`）。結算表本身就是「已結算」標記，worker 從「有 `pending`、尚未結算」的賽事裡，用 `get_tournament` 檢查哪些已經到期。目前期中規模，每分鐘多幾次查詢可以接受，而且不用動 B 的模組。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose run --rm --no-deps -T backend bash -c "bash scripts/test.sh"` -- 全綠
- `docker compose run --rm --no-deps -T backend bash scripts/lint.sh` -- 通過
- 前端容器內 `bun run typecheck`、`bunx biome check`、`bun run test:unit` -- 通過
