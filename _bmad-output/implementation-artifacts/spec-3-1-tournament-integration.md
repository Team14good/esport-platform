---
title: 'Story 3.1 收尾：接上 2.2 的真實賽事'
type: 'chore'
created: '2026-11-02'
status: 'done'
baseline_commit: '1494bc2810404023e06d30defe542553038e0417'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-1-create-team-and-invite-members.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3.1 先照約定呼叫 tournaments、測試用替身。2.2（#15）合併後，本分支已 merge `origin/main`（1494bc2），遷移改接 `e4b8c1d2a6f7`，但 `audit_log.tournament_id` 有了外鍵，替身賽事寫不進操作紀錄：`test_teams.py` 101 個失敗、mypy 4 個錯誤、A 的 1.8 測試 2 個斷言沒算到「我的隊伍」，前端 `team-pages.test.tsx` 偶發失敗。PR #23 因此無法轉成 Ready。

**Approach:** 依 deferred-work 中 3.1 的四個項目收尾：`tournament_id` 外鍵、移除型別忽略與 `_Tournament`、測試改用真實賽事、真實 PostgreSQL 平行加入測試；並修好上述失敗。不新增功能，3.1 的 I/O 矩陣與驗收條件不變。

## Boundaries & Constraints

**Always:**
- `team`、`team_member`、`registration` 的 `tournament_id` 外鍵到 `tournament.id`，直接改 3.1 的同一支遷移 `c5d2e8a4f913`（尚未合併，維持每 Story 一支）。
- registration 只透過 `tournaments.service` 公開函式取賽事，型別用 `TournamentRead`。
- 3.1 原有的測試情境全部保留（I/O 矩陣、唯一鍵防線、先鎖再檢查、使用鎖定回傳值、轉換表、公開函式、操作紀錄）。
- 平行加入測試在真實 PostgreSQL 以多條連線、多執行緒同時加入；名額剩 k 人時成功數恰為 k，其餘為 `TEAM_FULL`。

**Never:**
- 不改 tournaments 模組與 `tests/helpers.py`；A 的 1.8 測試只改身分清單斷言。
- 不改 3.1 的 API、畫面行為與錯誤碼；不手改 `frontend/src/client`、`routeTree.gen.ts`。
- 不為了讓測試通過而刪除或跳過測試；不改全域測試設定。

## Decisions（2026-11-02，邱芯彤）

- 測試的真實賽事用 2.2 的共用工具 `tests/helpers.make_tournament`（必要時搭配 `make_game`），不在 `test_teams.py` 自己 insert 賽事；帳號仍用本檔的 `_make_account`。
- spec 約 3,000 tokens，保留完整 spec，不拆分。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 平行加入 | 6 人隊伍已有 4 人，5 人同時加入 | 恰 2 人成功，隊伍 6 人 | 其餘 409 `TEAM_FULL` |
| 不存在的賽事 | 建隊時 `tournament_id` 不存在 | 拒絕 | 404 `TOURNAMENT_NOT_FOUND`（tournaments 拋出） |
| 孤兒資料 | 直接 insert `team` 帶不存在的 `tournament_id` | 資料庫拒絕 | `IntegrityError` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/service.py:1-80` -- 模組 docstring、`_Tournament` Protocol、`_get_tournament`／`_lock_tournament`／`_ensure_accepting_registrations` 的三處 `type: ignore`；`_max_members`、`_ensure_can_join`、`_build_detail` 的參數型別改 `TournamentRead`
- `backend/app/modules/registration/models.py:42,59,85,99` -- 移除「暫不加外鍵」註解；三個 `tournament_id` 加 `foreign_key="tournament.id"`
- `backend/app/alembic/versions/c5d2e8a4f913_story_3_1_team_and_registration.py` -- docstring 第 5 行說明改寫；三張表加 `ForeignKeyConstraint(["tournament_id"], ["tournament.id"])`；`tests/test_migrations.py` 檢查一致
- `backend/app/modules/tournaments/service.py:384-457` -- `get_tournament`、`lock_tournament`（`FOR UPDATE`）、`ensure_accepting_registrations`（訊息「這場賽事目前不開放報名。」，與替身不同）；只讀不改
- `backend/app/modules/tournaments/models.py:112` `Tournament`、`TournamentStatus` -- 要讓賽事非 open 時，直接改列的 `status`
- `backend/tests/helpers.py:84-130` -- `make_game`、`make_tournament`（預設 open、先發 5、替補 2）、`make_account`
- `backend/tests/registration/test_teams.py:36-105` -- `FakeTournament`／`FakeTournaments`／`tournaments` fixture；`:696` `_record_checks` 以替身的 `events` 驗證先鎖再檢查，改為包裝真實 `lock_tournament`
- `backend/tests/identity/test_organizer_application_review.py:380,604-615` -- 身分清單斷言，比照 `tests/identity/test_login.py:253-285` 在 `browse` 後加 `my_teams`
- `backend/tests/identity/test_organizer_application_review.py:653-751` -- 真實交易併發測試的寫法（`Session(engine)`、`threading`、`finally` 清理）；操作紀錄只增不改，參照它的列留在測試資料庫（每次測試重建）
- `frontend/tests/unit/team-pages.test.tsx:97,162` -- 偶發失敗的兩處都是該路由第一次渲染的 `findBy`（預設 1000 ms），疑為路由首次載入較慢
- `_bmad-output/implementation-artifacts/deferred-work.md:46-57` -- 3.1 的四個 2.2 相關項目，處理完刪除

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py`、遷移 `c5d2e8a4f913` -- 補三個外鍵、更新說明 -- deferred 項目一
- [x] `backend/app/modules/registration/service.py` -- 移除 `_Tournament`、型別忽略與 docstring 的過渡說明，改用 `TournamentRead` -- mypy／ty 通過
- [x] `backend/tests/registration/test_teams.py` -- 移除替身，改用真實賽事（見 Decisions）；「先鎖再檢查」「使用鎖定回傳值」改以包裝真實函式驗證；新增 I/O 矩陣的孤兒資料與不存在賽事測試 -- deferred 項目一、四
- [x] `backend/tests/registration/test_team_concurrency.py`（新） -- 平行加入測試 -- deferred 項目二
- [x] `backend/tests/identity/test_organizer_application_review.py` -- 只改身分清單斷言 -- 合併 1.8 後的預期變化
- [x] `frontend/tests/unit/team-pages.test.tsx` -- 找出偶發失敗的原因並在本檔修正，連跑 10 次全部通過 -- 不改全域設定
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除已處理的 3.1 項目（46-51、55-57 行）；S2 入口項目（52-54 行）保留
- [x] `_bmad-output/implementation-artifacts/spec-3-1-create-team-and-invite-members.md` -- 不改（status done）

**Acceptance Criteria:**
- Given 本分支，when 執行後端測試與 lint，then 全部通過，`registration/` 不再有 `type: ignore`／`ty: ignore`、`raising=False`。
- Given 遷移鏈，when `alembic heads`，then 只有一個 head 且為 `c5d2e8a4f913`。
- Given 前端，when typecheck、biome、單元測試，then 通過，且 `team-pages.test.tsx` 連跑 10 次無失敗。

## Implementation Notes

- 併發測試提交的操作紀錄會留在測試資料庫，`test_teams.py` 的 `_audit` 因此改為限定賽事查詢（否則 `team.created`、`team.member_joined` 會多算到併發測試的列）。
- `make_game` 會新建平台管理員；併發測試在提交前取消他的管理員身分，避免留下第二個管理員影響以管理員人數為前提的測試。
- 前端偶發失敗的原因：路由以 `autoCodeSplitting` 延遲載入，該路由第一次渲染時 Vite 才轉譯元件，冷啟動量到 930～1006 ms。`team-pages.test.tsx` 加 `beforeAll` 以 `router.loadRouteChunk` 先載入三個路由；之後 S19 第一個測試 46～121 ms、S17 第一個測試 271～560 ms，連跑 10 次全過。
- 全部前端單元測試連跑 3 次時，A 的 `admin-applications.test.tsx`（「不是平台管理員：顯示 S38 的 403」）失敗 1 次，疑為同一原因；不在本 Story 範圍，未修改。
- 遷移的 `down_revision` 最後接到 `f7a3c9e1b5d2`，不是 Problem 寫的 `e4b8c1d2a6f7`：#19（4.1）合併後 head 改變，本分支 merge `origin/main` 時再改接一次。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-02；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V、B1 | 併發測試說留下的列「每次測試重建」 | low | `tests/conftest.py:61` `_test_database` 是 `scope="session"`，每次執行 pytest 只重建一次，同一輪之後的測試都看得到；目前後續測試都以 `in` 或依賽事篩選，沒有失敗 | patch（改正說明） |
| B2、E1 | `setup.commit()` 後的斷言與 barrier 在 `try` 外，失敗時不清理 | low | 程式順序如所述，斷言失敗會留下已提交的隊伍、隊員與報名 | patch |
| B3、E3 | `start.wait` 在 `_join` 的 `try` 外，`BrokenBarrierError` 不記錄原因 | low | 執行緒內的例外不會傳到主執行緒，斷言只看到 outcomes 少一筆 | patch |
| B4 | 併發測試沒有確認失敗的加入不留操作紀錄 | low | 只核對人數與名單；補斷言是直接新增。主流程給的指示「該隊恰好 2 筆」寫錯（併發前已有 3 名隊員加入，該隊共 5 筆），由實作子代理改為只算 5 名同時加入者，恰 2 筆且為成功者 | patch |
| B5 | 只測平行加入，沒測平行建隊、建隊與加入同時發生 | low | Intent 與 deferred 項目只要求平行加入；建隊同帳號重複由唯一鍵防線測試涵蓋 | reject |
| B6、E8 | 併發測試自寫 `_account`，與 `helpers.make_account` 重複 | low | 該檔沒有斷言顯示名稱，可直接改用共用工具 | patch |
| B7、E6 | 孤兒資料測試只斷言 `IntegrityError`，沒確認是外鍵擋下 | low | 目前其他約束不會觸發，但之後改唯一鍵時測試可能誤通過；改為斷言 `<表名>_tournament_id_fkey` 是直接修正 | patch |
| B8、E4、E5 | 非開放狀態只測了部分（建隊 3 種、加入 1 種） | low | 改用真實 `ensure_accepting_registrations` 後，參數化到所有非 `OPEN` 狀態不增加程式 | patch |
| E2 | 執行緒卡住持有鎖時，清理的 DELETE 會一直等 | low | 只在加入本身卡死時發生，屆時測試本來就逾時；修正要加 `lock_timeout` 等新分支 | reject |
| B9 | 錯誤訊息從替身的「目前不在報名期間。」變成「這場賽事目前不開放報名。」 | false | 舊訊息只存在於測試替身，正式程式一直由 tournaments 拋出；錯誤碼 `REGISTRATION_CLOSED` 不變，前端顯示伺服器訊息 | reject |
| B10 | A 的 `admin-applications.test.tsx` 偶發失敗只寫在 Implementation Notes | medium（未證實） | 不是本 Story 造成；原因是否與本檔相同未查證 | defer |
| B11、E7 | A 的測試函式名稱沒包含 `my_teams` | low | 改名會改動 A 的既有函式，違反 CLAUDE.md「不改對方既有函式」；PR 說明列出 | reject |
| B12 | 直接改遷移 `c5d2e8a4f913`，跑過舊版的本機資料庫不會有外鍵 | low | 只影響切過 story/3-1 的本機開發資料庫（含使用者自己的）；CI 從空資料庫升級不受影響，在 PR 說明提醒 downgrade 後重新 upgrade | reject（PR 說明） |
| B13 | Verification 沒寫「連跑 10 次」的指令、`--no-deps` 需先啟動 db | low | 修正對象是本 spec | reject |
| B14 | diff 裡沒有 AI 使用紀錄、Triage Log 為空 | false | AI 使用紀錄在 step-05 新增；Triage Log 在審查後填寫（即本表） | reject |

## Design Notes

併發測試要提交資料，另一條連線才看得到；`lock_tournament` 讓加入依序執行，人數上限沒有資料庫約束，所以這是唯一能驗證「不超收」的測試。被操作紀錄參照的賽事、帳號、隊伍刪不掉，留在測試資料庫，比照 1.8 的併發測試。

## Verification

**Commands:**
- `docker compose build backend && docker compose run --rm --no-deps -T backend bash -c "bash scripts/test.sh; bash scripts/lint.sh"` -- 全綠
- `docker compose run --rm --no-deps -T backend alembic heads` -- 只有 `c5d2e8a4f913 (head)`
- `MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps -T -v "$(pwd -W)/frontend:/app/frontend" frontend bash -c "cd /app/frontend && bun run typecheck && bunx biome check && bun run test:unit"` -- 通過
