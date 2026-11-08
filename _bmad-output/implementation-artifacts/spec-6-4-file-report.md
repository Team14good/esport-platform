---
title: 'Story 6.4：提出檢舉'
type: 'feature'
created: '2026-11-08'
status: 'done'
baseline_commit: '7e32d9fdb7ada015e174842ad2c23626b2000544'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 隊長懷疑同賽事的他隊資格不符（例如隊員不同校）時，目前沒有正式管道通知主辦方；disputes 模組只有列舉，沒有檢舉資料表與 API（FR-32）。

**Approach:** 依 #55 的 `contracts/disputes.md` 建立 `report` 資料表與遷移、disputes 的檢舉公開函式與 API；registration 新增兩個公開函式供資格判斷；前端在 S2 總覽加「檢舉隊伍」入口，開 S20 對話框選對象、填說明、選擇性附截圖送出。主辦方的通知期中只發 `ReportFiled` 事件（期中規則 2）；S33 處理畫面屬 6.5（B）。

## Decisions（2026-11-08，邱芯彤）

- 重複檢舉：同一檢舉人隊伍對同一對象已有「處理中」（`open`）的檢舉時拒絕（409 `REPORT_ALREADY_FILED`，「已檢舉這支隊伍，主辦方處理中。」）；結案（駁回或屬實）後可以再檢舉。S20 的對象清單把這些隊伍標為「已檢舉・處理中」並停用。
- 沒有可檢舉的隊伍（清單為空）時不顯示「檢舉隊伍」；清單有隊伍、但全部已檢舉處理中時仍顯示，S20 內全部停用。
- spec 約 4,200 tokens，超過 1,600；後端、S20、S2 入口是同一個使用者目標，且 6.5（11/13）要接著用後端，保留完整 spec，不拆。
- 主流程提出、使用者核准的：賽事 `cancelled` 視同已結束；「檢舉隊伍」放在 S2 總覽的倒數／建隊區塊下方、賽事資訊上方；非隊長一律 403 `TEAM_CAPTAIN_REQUIRED`（2026-11-09 改為 `CAPTAIN_REQUIRED`，見本節最後一則）；成功 Toast「已送出檢舉」。
- spec 審查（2026-11-08）後補定：S20 介面文字（見 Boundaries〈S20 介面〉）；說明不符的錯誤 `REPORT_DESCRIPTION_INVALID`「說明須為 1～1000 字。」；主辦方列表排序為處理中在前、各組依 `filed_at` 由舊到新、再依 id；附件下載檔名 `report-<檢舉 id>.<jpg|png>`；送出不經 AlertDialog（EXPERIENCE.md:111 不在 Dialog 上再開 Dialog）。與 contracts 不同的地方（錯誤碼、新增欄位、`find_team_of_account`、`file_report` 回傳）先整理成清單請 B 確認，取得共識後才回寫 `contracts/disputes.md`。
- 2026-11-08 使用者核准 spec 審查的 20 項修正，以及 S20 的畫面文字、欄位配置、錯誤訊息與主辦方列表排序；保留完整 spec（約 6,600 tokens），不拆、不做第二輪審查；核准後停在 ready-for-dev，實作在新的 session 進行。
- 對外約定（#55 `contracts/disputes.md`）的差異要先請 B 確認；未取得共識前，不自行改變既有的對外約定。
- 2026-11-09，B 在 #63 回覆後由使用者決定：
  - 非隊長（含沒有隊伍）改為 403 `CAPTAIN_REQUIRED`「只有隊長可以提出檢舉。」，與 6.1 申訴、competition 報到一致；disputes 自己比對成員角色，不用 `ensure_captain`。先前「程式中沒有 `CAPTAIN_REQUIRED`」的判斷有誤，competition 5.1 報到已在用。
  - `report.reason` 改用 `Text`，與申訴的 `reason` 相同；長度上限由 6.5 的 service 驗證。
  - 其他 7 處差異 B 沒有異議，回寫 `contracts/disputes.md`。

## Boundaries & Constraints

**Always:**
- 可檢舉的報名狀態＝`pending`、`accepted`、`waitlisted`、`drawn`（下稱「四種狀態」）。檢舉人必須是四種狀態隊伍的隊長；對象必須是同賽事、四種狀態、不是自己的隊伍；賽事狀態為 `finished` 或 `cancelled` 時拒絕。
- 檢查順序與錯誤碼：賽事不存在 404 `TOURNAMENT_NOT_FOUND` → 賽事已結束或已取消 409 `REPORT_NOT_ALLOWED` → 登入者在該賽事沒有隊伍（`find_team_of_account` 回 None）或不是隊長（比對 `team.members` 的角色）403 `CAPTAIN_REQUIRED`「只有隊長可以提出檢舉。」 → 檢舉人報名不是四種狀態 409 `REPORT_NOT_ALLOWED` → 對象是自己 422 `REPORT_SELF`（`BusinessError(..., status_code=422)`，不是 `FieldError`）→ 對象不存在或不在此賽事 404 `TEAM_NOT_FOUND` → 對象不是四種狀態 409 `REPORT_NOT_ALLOWED` → 已有對同一對象處理中的檢舉 409 `REPORT_ALREADY_FILED` → 說明與附件驗證。`file_report` 先以 tournaments 的 `lock_tournament` 鎖住賽事再檢查，同時送出兩筆相同的檢舉只會成功一筆。`REPORT_NOT_ALLOWED` 的 message 寫出具體原因（例如「賽事已結束，不能提出檢舉。」）。
- 說明去除頭尾空白後 1～1000 字（以 code point 計），存入去頭尾空白後的值；不符時 `FieldError("REPORT_DESCRIPTION_INVALID", "說明須為 1～1000 字。", loc=("body", "description"))`。POST 為 multipart：`reported_team_id: Annotated[uuid.UUID, Form()]`、`description: Annotated[str, Form()] = ""`（預設空字串，空白才會走到 service 的 `FieldError`，不是 FastAPI 的英文 missing 錯誤）、`attachment: Annotated[UploadFile | None, File()] = None`（瀏覽器送出的空檔視為沒附）；附件最多一張，沿用 `core.storage.save_image`（JPG／PNG、5 MB，415／413）。
- 建立檢舉、`audit.record`（`report.filed`，操作者為檢舉人，after 含 `reporter_team_id`、`reported_team_id`、`description`、`has_attachment`，**不含**檔案鍵值）與 `events.publish(ReportFiled(report_id, tournament_id, reported_team_id))` 在同一交易。附件在所有檢查通過後才存；`file_report` 回傳內部結果 `FiledReport{report: ReportRead, attachment_key: str | None}`（只給 router 用，與 contracts 回傳 `ReportRead` 不同），存檔後 service 內任何步驟失敗先刪新檔再往外拋，router commit 失敗也刪新檔（照 `registration/service.py:712-716`、`router.py:84-89`）。被檢舉的隊伍狀態不變。
- 附件下載：檢舉不存在 404 `REPORT_NOT_FOUND` → 非該賽事主辦方 403 `TOURNAMENT_OWNER_REQUIRED`（`Organizer` dep ＋ `ensure_tournament_owner`）→ 沒有附件 404 `FILE_NOT_FOUND`。`open_report_attachment` 回 `(檔案, media type)`，media type 依鍵值副檔名（`.jpg`→`image/jpeg`、`.png`→`image/png`）；router 以 `StreamingResponse` 分塊讀、在 generator 的 `finally` 關檔，`Content-Disposition: attachment; filename="report-<id>.<ext>"`，並宣告 `response_class=StreamingResponse` 與 `responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}}`，讓產生的 client 不把圖檔當 JSON。任何回應都不暴露 `attachment_key`，只給 `has_attachment`。
- 主辦方列表 `list_tournament_reports`：`Organizer` ＋ `ensure_tournament_owner`；處理中在前，各組依 `filed_at` 由舊到新、再依 id。
- `reportable-teams` 每一項為 `{id, name, has_open_report}`（`has_open_report`＝本隊對它已有處理中的檢舉），依 `(name, id)` 在 Python 排序；檢舉人資格不符時回與 `file_report` 相同的錯誤。
- 前端：「檢舉隊伍」只對「在此賽事有四種狀態隊伍、且是隊長」、且 `reportable-teams` 不為空的登入者顯示，賽事 `finished`／`cancelled` 時不顯示；其他人（含隊員、主辦方、觀眾）看不到。判斷順序：登入 → `myTeamsQueryOptions()` 有此賽事、四種狀態的隊伍 → 既有 `teamQueryOptions(teamId)` 的 `my_role === "captain"` → 才呼叫 `reportable-teams`（`retry: false`）且結果不為空；隊員不會打 `reportable-teams`。
- S20 介面：手機底部 Sheet、桌機 Dialog（把 `PlayerProfileDialog.tsx:267` 私有的 `ResponsiveShell` 抽到 `components/common/ResponsiveDialog.tsx`，testid 由參數傳入，S18 改用它、testid 維持 `player-profile-sheet`）。入口為 outline Button「檢舉隊伍」。標題「提出檢舉」，說明「主辦方會查證，查證前被檢舉的隊伍不受影響。截圖只有主辦方看得到。」。欄位：「檢舉對象」Select（placeholder「選擇隊伍」，`has_open_report` 的項目停用並加「・已檢舉・處理中」）、「說明」Textarea（字數 `n／1000`，以 code point 計 `[...text].length`；空白時前端顯示「請輸入說明。」）、「截圖（選填）」`ScreenshotUploader`（上傳中顯示進度）。按鈕只有「送出檢舉」（沒有「取消」，關閉用右上角，與 S18 相同）；全部對象都停用時顯示「這些隊伍都已檢舉，主辦方處理中。」並停用「送出檢舉」。送出中不能關閉（照 `PlayerProfileDialog.tsx:253-256`）。成功關閉並 Toast「已送出檢舉」；伺服器錯誤顯示在對話框內。送出成功或失敗都 invalidate `reportable-teams`；`REPORT_NOT_ALLOWED` 時另 invalidate my-teams 與賽事資料。送出不經 AlertDialog。

**Never:**
- 不做 S33 主辦方處理畫面、`resolve_report`、取消資格（6.5，B）；不做 S2「正取隊伍」分頁每列的「檢舉」（3.9 擱置）。
- 不登錄通知收件規則、不寄 Email（期中規則 2）。
- 不改其他組員的既有函式：tournaments 的 `TournamentOverview.tsx` 只新增一個掛載點；registration 只新增公開函式與 repository 查詢，不改既有函式（`PlayerProfileDialog.tsx` 改用抽出的 `ResponsiveDialog`，是 C 自己的檔案）。
- disputes 不直接讀 registration、tournaments 的資料表，只呼叫對方 `service.py`。

## I/O & Edge-Case Matrix

狀態 A 隊為檢舉人的隊伍，B 隊為對象；未特別說明時兩隊都是 `accepted`、賽事 `open`。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 送出成功（含附件） | A 隊長；說明 20 字＋PNG | 201 `ReportRead`（`status == "open"`、`has_attachment == true`）；1 筆 `report.filed`、1 則 `ReportFiled`；B 報名狀態不變 | N/A |
| 送出成功（無附件） | 同上，不附檔 | 201、`has_attachment == false` | N/A |
| 各種檢舉人／對象狀態 | 兩隊分別為 `pending`、`waitlisted`、`drawn`；賽事 `closed`、`published`、`ongoing` | 都可送出 | N/A |
| 賽事已結束 | 賽事 `finished`（或 `cancelled`） | 拒絕 | 409 `REPORT_NOT_ALLOWED` |
| 檢舉自己 | 對象＝A | 拒絕 | 422 `REPORT_SELF` |
| 對象狀態不符 | B 為 `forming`、`rejected`、`withdrawn`、`retired`、`disqualified` | 拒絕 | 409 `REPORT_NOT_ALLOWED` |
| 重複檢舉 | A 對 B 已有 `open` 的檢舉 | 拒絕；同一對象的檢舉駁回或屬實後再送則成功 | 409 `REPORT_ALREADY_FILED` |
| 同時送出相同檢舉 | A 隊長平行送出兩筆對 B 的檢舉 | 只有一筆成功 | 另一筆 409 `REPORT_ALREADY_FILED` |
| 對象在其他賽事或不存在 | 隨機 id 或他賽事隊伍 | 拒絕 | 404 `TEAM_NOT_FOUND` |
| 檢舉人狀態不符 | A 為 `forming` 或 `withdrawn` | 拒絕；`reportable-teams` 同樣拒絕 | 409 `REPORT_NOT_ALLOWED` |
| 非隊長 | A 的隊員、沒有隊伍的帳號、他賽事的隊長 | 拒絕 | 403 `CAPTAIN_REQUIRED` |
| 未登入／未驗證 | 無 token／未驗證 Email | 拒絕 | 401／403 `EMAIL_NOT_VERIFIED` |
| 說明不符 | 空白、只有空白、1001 字 | 拒絕，不留附件 | 422 `REPORT_DESCRIPTION_INVALID`（loc `body.description`） |
| 存檔後失敗 | 附件已存，之後寫入或 commit 失敗 | 不留檢舉也不留檔案 | 原錯誤 |
| 附件不符 | GIF、超過 5 MB | 拒絕，不建立檢舉 | 415／413 |
| 可檢舉隊伍清單 | 賽事有 A、B（accepted）、C（forming）、D（waitlisted） | `reportable-teams` 回 B、D（id、隊名、`has_open_report`，依隊名排序），不含 A、C；A 對 B 有處理中的檢舉時 B 的 `has_open_report == true` | N/A |
| 主辦方列表與下載 | 該賽事主辦方；他賽事主辦方；檢舉人；檢舉不存在；沒有附件 | 主辦方取得列表（排序見 Boundaries）與附件（正確 media type 與檔名）；他賽事主辦方 403 `TOURNAMENT_OWNER_REQUIRED`、檢舉人 403 `ORGANIZER_REQUIRED`；404 `REPORT_NOT_FOUND`／`FILE_NOT_FOUND` | 403／404 |
| S2 入口顯示 | 隊長（四種狀態）／隊員／組隊中的隊長／觀眾／賽事已結束／隊長但清單為空 | 只有第一種看到「檢舉隊伍」 | N/A |
| S20 已檢舉的對象 | 清單中 B 的 `has_open_report == true` | B 顯示「已檢舉・處理中」且不能選 | N/A |
| S20 送出 | 選 B、填說明、附 PNG、按「送出檢舉」 | 關閉對話框，Toast「已送出檢舉」 | 伺服器錯誤在對話框內顯示 |

</frozen-after-approval>

## Code Map

- `backend/app/modules/disputes/models.py` -- 已有 `ReportStatus`（OPEN／DISMISSED／SUBSTANTIATED）。新增 `Report` table（欄位照 contracts〈一〉，含 6.5 用的 `reason`、`handled_by`、`handled_at`，6.5 不再改表；型別：`description` varchar(1000)、`attachment_key` varchar(64)、`status` String(32)（照 `registration/models.py:130`）、`reason` `Text`（與申訴相同，2026-11-09 B 確認）、時間欄位 `DateTime(timezone=True)`；index：`tournament_id`、(`reporter_team_id`, `reported_team_id`)）、`ReportRead`（不含 `attachment_key`，改 `has_attachment`；含 `reporter_team_name`、`reported_team_name` 供 S33）、`ReportableTeam{id, name, has_open_report}`、`ReportFiled(Event)`（事件寫法照 `registration/models.py:159` `RegistrationAllocated`）。
- `backend/app/modules/disputes/{repository,service,router}.py` -- 目前幾乎是空檔；router 已掛在 `api/main.py:26`。service 只呼叫 registration、tournaments 的 `service.py`；不 commit。
- `backend/app/modules/registration/service.py` -- 已有 `get_team`（:1086，`TeamRead.members` 含 role）、`get_registration`（:1094）、`get_team_names`（:1192）。新增公開函式：`find_team_of_account(session, *, tournament_id, account_id) -> TeamRead | None`（不限角色，用 `repository.get_membership`（repository.py:60）；同一帳號在一個賽事只會有一隊，`uq_team_member_tournament_id_account_id`；取代 contracts 的 `find_captain_team`，隊長判斷由 disputes 比對成員角色）、`list_teams_by_status(session, *, tournament_id, statuses) -> list[TeamSummary{id, name}]`（既有 repository 函式不合用：`list_teams_with_members_by_status`（:213）只收單一狀態且載入隊員、`list_registrations`（:150）沒有隊名；新增一個 join team 與 registration、`status IN (...)` 的 repository 查詢）。
- `backend/app/modules/tournaments/service.py:394` `get_tournament`、`:402` `lock_tournament` -- 取狀態與 `organizer_id`；`file_report` 用 `lock_tournament` 防止重複檢舉的競態。
- `backend/app/core/storage.py` -- `save_image`（鍵值帶 `.jpg`／`.png` 副檔名，下載的 media type 依副檔名）、`open_file`（呼叫端關閉）、`delete_file`。目前沒有任何下載 API，這是第一個：用 `StreamingResponse`，`Content-Disposition: attachment`。
- `backend/app/modules/registration/router.py:59-95` -- multipart 寫法範本（`Form()`、`UploadFile | None = File()`、空檔視為沒附、commit 失敗刪新檔）。
- `backend/app/core/{audit,events,authz}.py`、`identity/deps.py` -- `audit.record`（:53）、`events.publish`（:58）、`ensure_captain`（403 `TEAM_CAPTAIN_REQUIRED`）、`ensure_tournament_owner`（只需 `.organizer_id`）、`VerifiedAccount`、`Organizer`（:74）。寫入 API 都需登入，不加進 `PUBLIC_WRITE_ROUTES`。
- `backend/app/alembic/versions/` -- head `b5c8e2f4a1d7`；檔名 `<12hex>_story_6_4_report.py`；`tests/test_migrations.py` 要求遷移與模型完全一致（外鍵：`tournament_id`→tournament、兩個 team_id→team、`filed_by`／`handled_by`→account）。
- `frontend/src/features/tournaments/TournamentOverview.tsx` -- B 的檔案。`StatusPanel` 只在 `open` 掛 `CreateTeamEntry`（:79），其他狀態回 null；「檢舉隊伍」要在任何狀態都能出現，掛在 `TournamentOverview` 的 `StatusPanel` 之後、資訊 `dl` 之前（只加一行掛載）。
- `frontend/src/features/registration/CreateTeamEntry.tsx` -- 判斷登入、`myTeamsQueryOptions()`（`MyTeamCard` 有 `tournament_id`、`registration_status`，沒有角色）的範本；隊長身分用 `teamQueryOptions(teamId)` 的 `TeamDetail.my_role`（`registration/models.py:276`，S17 已用，`SubmitRegistrationSection.tsx:156`）。`frontend/src/lib/query-client.ts:8-14` 預設對 403／409 重試 3 次，所以 `reportable-teams` 要 `retry: false`。
- `frontend/src/features/registration/{ScreenshotUploader.tsx,screenshot-file.ts,useUpdatePlayerProfile.ts,PlayerProfileDialog.tsx}` -- 截圖上傳元件、前端檢查、`onUploadProgress` 進度、`ResponsiveShell`（:267，私有，要抽出）手機 Sheet／桌機 Dialog；`components/common/ConfirmDialog.tsx:118-131` 字數計數版面（它以 UTF-16 計，S20 改用 code point）。
- `backend/tests/helpers.py` -- `make_account`、`make_game`、`make_tournament`；上傳測試範本 `tests/registration/test_player_profile_api.py`（`upload_dir` fixture :45、`PNG`／`GIF` 常數 :37-41、audit 不含鍵值 :426、存檔後失敗不留檔 :465、commit 失敗刪檔 :485）；改賽事狀態照 `tests/registration/test_teams.py:64` `_set_status`；先鎖賽事再檢查可用 `test_teams.py` 的 `lock_spy`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/service.py`、`repository.py`、`models.py` -- 新增 `find_team_of_account`、`list_teams_by_status`、`TeamSummary` 與 repository 查詢；`backend/tests/registration/` 補對應測試
- [x] `backend/app/modules/disputes/models.py`、`repository.py`、`service.py` -- `Report` 等模型；`list_reportable_teams`、`file_report`、`list_tournament_reports`、`open_report_attachment`（簽名照 contracts〈二〉）
- [x] `backend/app/alembic/versions/<rev>_story_6_4_report.py` -- 建立 `report` 表
- [x] `backend/app/modules/disputes/router.py` -- 4 支 API（照 contracts〈二〉API 表的路徑與權限；POST 回 201）
- [x] `backend/tests/disputes/__init__.py`、`test_reports.py` -- I/O 矩陣後端各列（含重複檢舉、結案後可再檢舉（直接把檢舉列改為 `dismissed`）、主辦方列表排序、下載內容／media type／檔名、他人 403、驗證失敗不留附件、存檔後失敗與 commit 失敗不留檔、空檔視為沒附、先鎖賽事再檢查、audit 不含檔案鍵值、未驗證 Email 403）
- [x] `backend/tests/disputes/test_report_concurrency.py` -- 真實 PostgreSQL 平行送出兩筆相同檢舉只成功一筆（寫法照 `tests/registration/test_settlement_concurrency.py`：獨立 Session、提交資料；finally 依序刪 report、outbox、registration、team_member、team，並把賽事改為 `cancelled`，避免被 worker 測試撿到）
- [x] `frontend/src/client` -- `scripts/generate-client.sh` 重新產生
- [x] `frontend/src/components/common/ResponsiveDialog.tsx`、`frontend/src/features/registration/PlayerProfileDialog.tsx` -- 抽出 `ResponsiveShell`（testid 參數化），S18 行為與既有測試不變
- [x] `frontend/src/features/disputes/` -- `ReportTeamEntry`（入口與顯示條件）、`ReportTeamDialog`（S20，文字與行為照 Boundaries）、queries（`retry: false`）／mutation hook（invalidate 規則照 Boundaries）
- [x] `frontend/src/features/tournaments/TournamentOverview.tsx` -- 只新增 `<ReportTeamEntry>` 掛載點
- [x] `frontend/tests/unit/report-team.test.tsx` -- S2 入口顯示條件（含隊員不呼叫 `reportable-teams`、403 不重試、清單為空不顯示）、S20 送出成功與錯誤、全部已檢舉時停用、說明字數（含 emoji 以 code point 計）與附件檢查、送出後 invalidate
- [x] `backend/tests/traceability.yaml` -- 若 #61 已合併，新增的後端測試檔各加一列（layer `integration`、stories `["6.4"]`、frs `[FR-32]`，併發檔加 `NFR-1`）；若把 registration 新函式的測試加進既有測試檔，該列的 `stories` 補 `"6.4"`（#61 尚未合併，本 Story 不加）
- [x] `_bmad-output/implementation-artifacts/contracts/disputes.md` -- 先整理與約定不同處並請 B 確認（PR 說明或 #55 留言），取得共識後才回寫；差異：`TEAM_CAPTAIN_REQUIRED`、`REPORT_ALREADY_FILED`、`REPORT_DESCRIPTION_INVALID`、`ReportableTeam.has_open_report`、`ReportRead` 欄位、`file_report` 回傳 `FiledReport`、`find_team_of_account`、`reason` 長度、POST 表單欄位（2026-11-09 B 回覆後回寫）
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 6-4 改 `in-progress`，完成時 `done`；`epic-6` 改 `in-progress`
- [x] `docs/ai-usage/C-邱芯彤.md` -- 完成後由主流程在使用者確認後新增紀錄

**Acceptance Criteria:**
- Given 符合資格的隊長在 S2 總覽，when 按「檢舉隊伍」、選對象、填說明（可附截圖）並送出，then 建立檢舉、寫操作紀錄並發 `ReportFiled`，被檢舉隊伍的狀態不變，只有該賽事主辦方能下載附件。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh` 與前端 typecheck、biome、單元測試，then 全部通過。

## Implementation Notes

給後續 bmad-build 的提醒（2026-11-08，使用者核准 spec 時指定）：

1. spec 較長（約 6,600 tokens），實作與 step-03 核對時逐項對照 Tasks 與 I/O 矩陣每一列，不要只看摘要。
2. 確認附件上傳失敗（service 內存檔後失敗、router commit 失敗）時檔案都被清除；附件下載的權限（只有該賽事主辦方）與錯誤處理（`REPORT_NOT_FOUND`、`TOURNAMENT_OWNER_REQUIRED`、`ORGANIZER_REQUIRED`、`FILE_NOT_FOUND`）都有測試。
3. 重複檢舉的併發安全要在真實 PostgreSQL 上驗證（`test_report_concurrency.py`），不能只靠單一交易內的測試。
4. 抽出 S18 的 `ResponsiveShell` 不得改變原本的操作與顯示行為；既有 S18 測試要照常通過，並補回歸測試（手機 Sheet／桌機 Dialog、送出中不能關閉、testid 不變）。
5. 對照 #55 的 `contracts/disputes.md` 整理所有介面差異，先請 B 確認；未取得共識前不要自行改變既有的對外約定。
6. `report` 資料表要完整支援 6.5（處理欄位、型別、索引），避免 B 之後重做遷移。
7. 實作完成後逐項確認：測試結果、Git diff、審查結果與 AI 使用紀錄。

## Spec Change Log

- 2026-11-09：B 在 #63 回覆約定差異。使用者決定非隊長錯誤碼改為 `CAPTAIN_REQUIRED`、`report.reason` 改為 `Text`（見 Decisions 最後一則），連帶更新 Boundaries 的檢查順序、I/O 矩陣〈非隊長〉、Code Map 與 Design Notes。遷移檔尚未合併進 main，直接修改 `e9a4c2f7b6d1`，不另加遷移。
- 2026-11-09：B 在 #64 核准並提出 4 點不擋合併的建議，使用者決定合併前處理其中 3 點：`report` 加 `(reported_team_id, status)` 索引（6.5 結案同一隊的未結案檢舉）與 CHECK `reporter_team_id <> reported_team_id`（同樣直接改 `e9a4c2f7b6d1`）；補 S2 掛載點的頁面層測試，以及附件鍵值存在但檔案已不在時下載回 404 `FILE_NOT_FOUND` 的測試。約定檔裡殘留的 `ensure_captain` 寫法，由 B 合併 #63 時一併修改。

## Review Triage Log

第 1 輪（2026-11-08，Blind Hunter、Edge Case Hunter、Verification Gap）：

| # | 來源 | 發現 | 判定 | 處理 | 依據 |
|---|------|------|------|------|------|
| 1 | VG | `reportable-teams` 依隊名排序的測試只有兩隊、id 隨機，拿掉排序約一半會通過 | medium | patch | 驗證缺口，已讀測試確認 |
| 2 | VG | 入口層級沒有測試 `onUploadProgress` 接到對話框的進度 | medium | patch | `report-team.test.tsx` 沒有 `onUploadProgress` |
| 3 | VG | S20「關閉再開啟從空白開始」沒有測試 | medium | patch | S18 有同類測試，S20 沒有 |
| 4 | EC | `REPORT_NOT_ALLOWED` 後重取我的隊伍／賽事，入口條件不成立時 `ReportTeamEntry` 回 null，對話框連同錯誤一起消失 | medium | patch | `ReportTeamEntry.tsx` 先判斷條件再渲染對話框；spec 要求錯誤顯示在對話框內 |
| 5 | EC | 對話框開著時 `reportable-teams` 重取為空，對話框消失、輸入遺失；空清單時 `allReported` 為真會誤顯示「都已檢舉」 | medium | patch | 與 #4 同一根因（開啟中仍依入口條件卸載）；`[].every` 為 true |
| 6 | EC | 說明含 NUL 字元時 PostgreSQL 拒絕，回 500 | low | 拒絕 | 只有手工構造的請求會遇到；修正要加防護分支 |
| 7 | EC | 串流未開始就斷線時 generator 的 finally 不執行 | low | 拒絕 | CPython 參照計數會在回應物件釋放時關檔；修正要改結構 |
| 8 | EC | 隊伍沒有報名列時 `get_registration` 拋未列出的錯誤 | false | 拒絕 | 建隊時同時建立報名列（3.1），不會有沒有報名列的隊伍 |
| 9 | BH | 存附件時賽事列一直鎖著 | low | 拒絕 | FastAPI 已先收完上傳，存檔只是本機複製；改法要換鎖的設計 |
| 10 | BH | 資料庫沒有約束重複檢舉 | false | 拒絕 | Design Notes 已記錄以 `lock_tournament` 序列化、不用部分唯一索引 |
| 11 | BH | 送出失敗後選單仍選著已停用的對象 | low | 拒絕 | 再送會得到同樣清楚的錯誤；修正要加 effect |
| 12 | BH | 字數計數用原文、驗證用去頭尾空白後的文字 | low | 拒絕 | spec 指定 `[...text].length`；只在頭尾有空白時差幾個字 |
| 13 | BH | 刪掉既有測試「不查我的隊伍」的斷言，且隊員也會打 `readTeam` | false | 拒絕 | Design Notes 已預期多查一次；`readTeam` 只在找到此賽事的隊伍時才呼叫 |
| 14 | BH | 檢舉人的 `rejected`／`retired`／`disqualified` 沒測，對象狀態不符沒驗訊息 | low | patch | 只要補 parametrize 值與訊息斷言 |
| 15 | BH | 回滾測試只驗檔案不見，沒驗檢舉列／紀錄／事件 | low | 拒絕 | 測試用外層交易，例外後的回滾無法在此 fixture 觀察；實際由交易保證 |
| 16 | BH | 主辦方兩支 API 未測 401、`reportable-teams` 未測 404、未測 worker 接受 `ReportFiled` | false／low | 拒絕 | `dispatch_event` 對沒有 handler 的事件記錄後略過；401 與 404 由既有 dep 與 `get_tournament` 負責，各模組已測 |
| 17 | BH | 附件下載沒有 `X-Content-Type-Options: nosniff`、`Cache-Control: private, no-store` | low | patch | 檢舉截圖是敏感資料，加兩個標頭即可 |
| 18 | BH | 操作紀錄保存完整說明 | false | 拒絕 | spec 規定 after 含 `description` |
| 19 | BH | 404／409 可推測他隊報名狀態 | false | 拒絕 | 錯誤順序是 frozen 規則，改法要改 spec |
| 20 | BH | 隊名依 code point 排序，不是筆畫／注音 | false | 拒絕 | spec 規定依 `(name, id)` 在 Python 排序 |
| 21 | BH | 測試匯入其他測試檔的私有 helper | low | 拒絕 | 沿用 registration 測試的寫法；修正要搬動多個 helper |
| 22 | BH | `_file_not_found` 與 `core.storage` 重複 | low | 拒絕 | 共用要在 core 新增公開函式 |
| 23 | BH | S33 前端未做、路由未宣告 4xx 回應 | false | 拒絕 | S33 屬 6.5（frozen Never）；各模組路由都未宣告 4xx，既有慣例 |

## Design Notes

- 隊長身分：`MyTeamCard` 沒有角色欄位，不改 S12 的回應；改用 S17 已有快取的 `TeamDetail.my_role`，只有隊長才呼叫 `reportable-teams`。非 `open` 狀態時 `CreateTeamEntry` 不掛載，`ReportTeamEntry` 會讓登入者多取一次 `/accounts/me/teams`（與 S12 共用快取）。
- 重複檢舉以 `lock_tournament` 序列化，不用部分唯一索引：遷移與模型比對較單純，且與 registration 的併發做法一致。
- 非隊長的錯誤碼用 `CAPTAIN_REQUIRED`，與 6.1 申訴、competition 報到一致（2026-11-09 改；原本誤以為程式中沒有這個碼而用 `TEAM_CAPTAIN_REQUIRED`）。
- 附件先存檔再寫資料庫；驗證失敗在存檔前擋下，commit 失敗由 router 刪檔（與 S18 相同）。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- `docker compose exec -T frontend bun run --filter frontend typecheck`、`bunx biome check`、`bun run test:unit` -- 通過
