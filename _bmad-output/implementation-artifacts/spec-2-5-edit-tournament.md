---
title: 'Story 2.5：抽籤前修改賽事'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '19f9b6be9c0ef9ec721209a36da27ac39c5fea51'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 主辦方建立賽事後無法調整設定；報名不如預期（例如報名截止時正取不足 2 隊、自動抽籤略過）時，只能取消賽事（FR-9）。

**Approach:** tournaments 新增 `update_tournament` 與 `PATCH /organizer/tournaments/{tournament_id}`，依賽事狀態限制可改的欄位，只記變動欄位的操作紀錄；新增 S28 賽事設定頁（側欄「設定」）。名額在開放報名後的提高沿用 3.7 的 `POST /tournaments/{id}/capacity`（registration 主導遞補）。

## Boundaries & Constraints

**Always:**
- 權限：`Organizer` ＋ `core.authz.ensure_tournament_owner`；先 `lock_tournament`；router commit（AD-5、AD-10）。
- **尚未開放**：名稱、遊戲、名額、報名開始／截止、優先期、開賽時間、每輪間隔、棄權時限、申訴期、先發／替補、BO、分輪 BO、直播連結都能改；改完仍須通過建立時的全部檢查（FR-7，含每輪間隔下限與分輪 BO 輪次範圍）。換遊戲時重建 `game_snapshot`（未另填的人數與 BO 帶新遊戲的值）。
- **開放報名、報名截止（抽籤前）**：只能延長報名截止、延長棄權時限／申訴期／每輪間隔、修改分輪 BO、修改直播連結；其他欄位與縮短、降低一律 422 指向該欄位並說明原因。延長棄權時限或申訴期後，每輪間隔仍須符合 FR-7 下限（以賽事 BO 計算）。
- 報名截止的賽事把報名截止延到現在之後時，經 `transition_tournament` 轉回開放報名（自動抽籤略過紀錄以報名截止時間為鍵，新截止時會重新嘗試）。
- **賽程已公布、進行中**：只能改直播連結；其他欄位 409 `TOURNAMENT_SETTINGS_LOCKED`「抽籤後只能修改場次時間。」。
- **已結束、已取消**：任何修改 409 `TOURNAMENT_NOT_EDITABLE`「已結束或已取消的賽事不能修改。」。
- 直播連結須為 http／https；空白代表移除。
- 操作紀錄 `tournament.updated`，before／after 只含變動欄位（分輪 BO 整份比較）；沒有任何變動時不寫紀錄、回 200。
- S28：遊戲欄位在開放報名後唯讀；數字欄位的輸入下限為目前值；賽程已公布或之後整頁唯讀（直播連結除外），頂部 Page banner「抽籤後只能修改場次時間」；已結束、已取消整頁唯讀。

**Never:**
- tournaments 不呼叫 registration（AD-3）；提高名額後的遞補由 3.7 處理。
- 不做賽事模式的修改：自訂模式屬 3.10（C，尚未做），目前只有校園賽，API 不接受 `mode`。
- 不做抽籤後修改場次時間（4.3 已有）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 尚未開放改任何設定 | upcoming，改遊戲、名額（降低）、時間 | 200；快照換成新遊戲；操作紀錄只含變動欄位 | N/A |
| 尚未開放改成不合法 | upcoming，每輪間隔低於下限 | 不變 | 422 `ROUND_INTERVAL_TOO_SHORT` 指向欄位 |
| 開放報名放寬 | open，延長截止、棄權時限、申訴期、間隔、改分輪 BO | 200；操作紀錄前後值 | N/A |
| 開放報名收緊或改鎖定欄位 | open，縮短申訴期／換遊戲／改開賽時間 | 不變 | 422 指向該欄位 |
| 延長棄權後間隔不足 | open，棄權時限加長、間隔未改 | 不變 | 422 `ROUND_INTERVAL_TOO_SHORT` |
| 報名截止後延長 | closed，報名截止延到現在之後 | 200；狀態回開放報名；操作紀錄含狀態變更 | N/A |
| 抽籤後改直播連結 | published／ongoing，只改直播連結 | 200 | N/A |
| 抽籤後改其他欄位 | published，改分輪 BO | 不變 | 409 `TOURNAMENT_SETTINGS_LOCKED` |
| 已結束／已取消 | 任何修改 | 不變 | 409 `TOURNAMENT_NOT_EDITABLE` |
| 直播連結不合法 | `ftp://…` | 不變 | 422 指向 `livestream_url` |
| 別的主辦方 | 非擁有者 | 不變 | 403 `TOURNAMENT_OWNER_REQUIRED` |
| 沒有變動 | 送出與目前相同的值 | 200，不寫操作紀錄 | N/A |

## Decisions

- **（使用者 2026-11-23）S28 的「提高名額」另設區塊與按鈕。** 開放報名、報名截止時經 3.7 的 `POST /tournaments/{id}/capacity` 送出，確認對話框說明「候補會依順位立即遞補，無法復原。」；「儲存設定」只送 `PATCH` 的其他欄位。尚未開放時名額（含降低）照一般欄位由 `PATCH` 修改。每次送出都是單一交易。
- **（使用者 2026-11-23）開放報名後開賽時間不能改**，照 FR-9；報名截止最多延到開賽時間之前。
- **（AI 依現況，使用者核准）不做賽事模式的修改**：偏離原 AC「尚未開放時可改賽事模式」，因為自訂模式屬 3.10（C，尚未做）、目前只有校園賽；3.10 完成時再補。
- **（使用者 2026-11-23）spec 約 3,500 tokens，超過 1,600 仍不拆**：只有修改賽事設定一個目標，後端與 S28 分開無法單獨上線。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/service.py:335` `_validate_schedule`、`:328` `min_round_interval`、`:380` `_validate_round_bo`、`:395` `create_tournament`（`:437-445` 建 `game_snapshot`、`:405` 以 FOR SHARE 鎖遊戲）、`:545` `transition_tournament`、`:614` `raise_tournament_capacity`、`:150` `update_game`（只記變動欄位的範本）
- `backend/app/modules/tournaments/models.py:399-427` 欄位型別（下限、網址）、`:430` `TournamentCreate`、`:353` 分輪 BO 的 schema 檢查 -- 新增 `TournamentUpdate`（全部選填）
- `backend/app/modules/tournaments/repository.py:145,153` 分輪 BO 讀寫（沒有刪除，要新增取代整份的函式）、`:244` `set_tournament_capacity`、`:107` `update_game`
- `priority_end` 是唯一的衍生欄位（＝報名開始＋優先期），改報名開始或優先期時重算；優先期目前值＝`priority_end - registration_start`
- 報名截止轉回開放報名的影響：`registration/service.py:1319` `close_due_registration`（只處理 open 且截止已到）、`priority_window_settlement` 已結算不會重跑、`competition/models.py:66` `auto_draw_skip` 以報名截止為鍵
- 提高名額：`registration/router.py:153`、`registration/service.py:1373`；前端 client `RegistrationService.raiseCapacity`（尚無呼叫端）
- `frontend/src/features/tournaments/CreateTournamentForm.tsx`（`:93` zod、`:173` superRefine、`:268` `toTournamentCreate`、`:317` `RoundBoField`、`:444` `TextField`、`:478` `FormSection`）-- 抽出可共用的欄位元件給 S28，不改 S26 行為
- `frontend/src/features/tournaments/organizer-nav.ts` `tournamentNav` -- 加「設定」；`frontend/src/routes/organizer/tournaments/$tournamentId/referees.tsx` 路由範本；`organizer-queries.ts:80` mutation 範本
- `frontend/src/components/common/PageBanner.tsx`、`TournamentPage.tsx:96` banner 用法；`frontend/src/features/tournaments/audit-log.ts:24` 操作紀錄標籤（新增 `tournament.updated`）
- 測試範本：`backend/tests/tournaments/test_tournaments.py`、`test_round_bo.py`、`backend/tests/registration/test_raise_capacity.py`、`backend/tests/worker/test_registration_deadline.py`、`backend/tests/competition/test_auto_draw.py`；前端 `organizer-tournaments.test.tsx`（`fillValidForm` 等）
- 不需要遷移（沒有 schema 變更）

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/{models,repository,service,router}.py` -- `TournamentUpdate`、`update_tournament`、`PATCH /organizer/tournaments/{tournament_id}`
- [x] `backend/tests/tournaments/test_update_tournament.py` -- I/O Matrix 每一列；另含「報名截止延長後，worker 在新截止時重新截止並重新嘗試自動抽籤」
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh`
- [x] `frontend/src/features/tournaments/{TournamentSettingsPage.tsx,organizer-queries.ts,organizer-nav.ts,audit-log.ts}`、`frontend/src/routes/organizer/tournaments/$tournamentId/settings.tsx` -- S28；依 Open Question 1 處理提高名額；重新產生 `routeTree.gen.ts`
- [x] `frontend/tests/unit/tournament-settings.test.tsx` -- 各狀態的可編輯欄位與下限、送出內容、422 寫回欄位、409 顯示、抽籤後 banner 與唯讀、已結束唯讀
- [x] `contracts/tournaments.md` -- `update_tournament`、PATCH API；移除「期中不提供 `update_tournament`」

**Acceptance Criteria:**
- Given 開放報名的賽事，when 主辦方在 S28 延長報名截止並儲存，then 成功 Toast，S27 顯示新的報名截止
- Given 報名截止、正取不足而自動抽籤略過的賽事，when 主辦方延長報名截止，then 狀態回到開放報名，之後在新截止時重新嘗試自動抽籤
- Given 375 px 寬的手機，when 開啟 S28，then 沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- 開放報名後的錯誤代碼：鎖定欄位 422 `TOURNAMENT_FIELD_LOCKED`、縮短 422 `TOURNAMENT_SETTING_TIGHTENED`（訊息依欄位說明原因）；名額在開放報名後一律 422，訊息指向「提高名額」。
- 報名截止的賽事延長到仍早於現在的時間：只更新截止時間、維持報名截止（只有延到現在之後才轉回開放報名）。
- 已結束、已取消的賽事連空的 PATCH 也回 409 `TOURNAMENT_NOT_EDITABLE`。
- `tournament.updated` 以修改前後的 `TournamentRead` 比較（不含狀態），所以換遊戲時快照欄位（遊戲名稱、每局時間、段位表等）與衍生的 `priority_end` 也會列出；狀態變更另由 `tournament.status_changed` 記錄。
- S28 已結束、已取消時頂部顯示 Page banner「已結束或已取消的賽事不能修改。」；抽籤後的 banner 附「前往場次管理」連結。
- S28 的表單只在儲存或提高名額成功、或賽事狀態改變時以新值重新建立；背景重抓不會清掉未儲存的修改（`TournamentRead` 沒有 `updated_at`，以頁面內的版本計數加狀態當 key）。
- 開放報名後報名截止必須早於開賽時間（等於時 422 `REGISTRATION_END_AFTER_START`），S28 的上限為開賽前一分鐘。
- 手動檢查（2026-11-23，瀏覽器、375 px，主代理）：開放報名的賽事（本機新建「設定頁測試盃」）在 S28 只開放報名截止、時限、間隔、分輪 BO、直播連結，下限為目前值，「提高名額」獨立區塊、新名額下限 9；延長報名截止後 Toast「已儲存設定。」，操作紀錄 `tournament.updated` 只含 `registration_end`。賽程已公布的賽事頂部顯示「抽籤後只能修改場次時間」，只剩直播連結可改。兩頁都沒有橫向捲軸（scrollWidth＝clientWidth＝375）。
- 完整驗證（審查修補後，單獨執行）：後端 `scripts/test.sh` 2854 passed、覆蓋率 97%，`lint.sh` 通過；前端 build、typecheck、biome、`test:unit`（81 檔、1208 passed）通過。
- 共用元件：`CreateTournamentForm.tsx` 匯出 `TextField`（新增 `disabled`、`max`）、`FormSection`、`RoundBoField`（新增 `disabled`）、`livestreamUrlError`；`createTournamentSchema` 新增選填的 `currentGame`（S28 以快照的每局時間計算下限），S26 不傳，行為不變。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-23）：Verification Gap 3 筆＋1 筆其他、Blind Hunter 13 筆、Edge Case Hunter 5 筆，主代理手動檢查 1 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind、Edge | 開放報名後可把報名截止設成「等於」開賽時間；該賽事會在開賽時截止，自動抽籤只挑 `start_at > now`（`repository.list_closed_before_start_ids`），永遠不會抽籤、卡在報名截止；凍結區 Decisions 寫「延到開賽時間之前」 | high：已對照程式確認；偏離凍結區決定 | patch（改為嚴格早於開賽時間，前端上限與提示同步） |
| 2 | Gap、Blind | 「整份替換分輪 BO」的刪除步驟沒有測試（所有測試都從空清單開始） | medium：拿掉刪除或 flush 測試照過，實際會殘留舊設定或主鍵衝突 | patch（補測試：替換、同輪改 BO、清空） |
| 3 | Gap | 尚未開放時，不換遊戲只改先發／替補／BO 的路徑沒有測試 | medium：刪掉該分支會靜默丟掉修改並顯示成功 | patch（補測試，含只提高 BO 使間隔不足的 422） |
| 4 | Gap | S28 切換遊戲帶入新遊戲預設值（`selectGame`）沒有 DOM 測試 | medium：刪掉 `setValue` 會沿用舊遊戲的人數與 BO | patch（補測試） |
| 5 | Blind | S28 表單以 `key={JSON.stringify(data)}` 重建，視窗回到焦點的背景重抓也會清掉沒儲存的修改 | medium：日常會遇到（切換分頁再回來） | patch（改以 `updated_at`、`status` 當 key） |
| 6 | Blind、Edge | 提高名額失敗（例如期間已抽籤，409 `CAPACITY_NOT_EDITABLE`）不重抓賽事，頁面停在過時的狀態 | low：直接比照 `useUpdateTournament` 在業務錯誤時重抓 | patch |
| 7 | Edge | 儲存失敗後再成功提高名額，頂部仍留著舊的儲存錯誤 | low：直接在提高名額成功時清除 | patch |
| 8 | Blind | 這條路由缺 401 與 403 `ORGANIZER_REQUIRED` 的測試 | low：直接補兩個測試 | patch |
| 9 | Gap、Blind | `round_bo` 比較受順序影響 | false：`TournamentUpdate.round_bo` 經 `_validate_round_bo` 排序，與讀出的順序一致 | 不處理 |
| 10 | Blind | 報名截止轉回開放報名時，沒有處理截止時已發的事件、已結算的狀態，也沒有通知隊伍 | maybe-false（若為真屬 medium）：AC 沒有要求通知；`priority_window_settlement` 已結算不重跑是預期行為；要查 `close_registration` 有沒有發出會變成錯誤的事件 | defer |
| 11 | Blind、Edge | 尚未開放時降低名額，超出輪數的分輪 BO 被前端靜默丟棄（API 直接送則 422 指向 `round_bo`） | low：名額變小後那幾輪本來就不存在；與 S26 相同（2.3 審查第 16 點） | 不處理 |
| 12 | Blind | 同一個請求鎖了三次賽事列，`assert` 在 `-O` 時會被略過 | low：同一交易內重複鎖不會等待；與 2.6 的寫法一致 | 不處理 |
| 13 | Blind | 換遊戲時操作紀錄帶整份段位表，S34 只顯示原始欄位名稱 | false：2.8 的操作紀錄頁依設計照原始資料顯示（`AuditLogEntry` docstring） | 不處理 |
| 14 | Edge | 「重新截止並重新嘗試自動抽籤」的測試直接呼叫 `close_registration`，不是 worker | low：worker 以 `find_due_registration_end_id`（open 且截止已到）挑賽事，轉回開放報名後條件成立，3.6 已有測試 | 不處理 |
| 15 | Blind | Tasks 寫「依 Open Question 1」，但該節已改為 Decisions | 修正方式是改 spec，依規則不處理 | 不處理 |
| 16 | Blind | spec 是 `in-review`、sprint-status 是 `in-progress` | false：由 bmad-build 最後一步更新 | 不處理 |
| 17 | Blind | 沒有 AI 使用紀錄與手動檢查證據 | false：手動檢查已做（見 Implementation Notes）；AI 紀錄在完成時新增 | 不處理 |
| 18 | 主代理 | 沒有變更時按「儲存設定」似乎沒有反應 | false：程式送出空的 PATCH 並顯示成功 Toast；手動檢查時請求清單已被截斷、Toast 已消失，是主代理誤判 | 不處理 |

## Design Notes

AI 依現有程式決定（使用者不易察覺）：
- 尚未開放的賽事把報名開始改到現在或更早時，與建立時相同，立即經 `transition_tournament` 轉為開放報名。
- 開放報名後不能改名稱、優先期、先發／替補、賽事 BO（FR-9 未列）；分輪 BO 可改，輪次範圍依目前名額。
- PATCH 只帶要改的欄位；未帶的欄位不變。前端只送有變動的欄位。

## Verification

**Commands:**
- `docker compose up -d --build --wait && docker compose exec backend bash scripts/test.sh` -- expected: 後端全部通過
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過
- 前端 `bun run build`、`bun run typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過

**Manual checks:**
- 瀏覽器在 S28 修改開放報名中賽事的報名截止、抽籤後只改直播連結；375 px 檢查 S28。
