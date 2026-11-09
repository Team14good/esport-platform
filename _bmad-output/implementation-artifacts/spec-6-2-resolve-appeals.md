---
title: 'Story 6.2：主辦方處理申訴'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
baseline_commit: 'a4fbdf6d6209022a441e81267b2946e5261f71db'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-1-file-appeal.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 6.1 讓隊長能申訴，但主辦方還不能處理：申訴中的場次停在「申訴中」，下一場也因此無法開始。

**Approach:** competition 新增 `uphold_result`、`correct_result`、`replay_match`（新檔 `competition/appeals.py`，`service.py` 只新增公開函式）；disputes 新增列表、處理、待處理計數與公開結果查詢；前端新增 S32 申訴頁與側欄「申訴」、S27 待處理清單、S4 顯示處理結果。

## Boundaries & Constraints

**Always:**
- 照 `contracts/disputes.md` 的函式、路由與錯誤碼；鎖順序 `lock_tournament` → `lock_match` → 狀態（只接受 `appealed`）→ outcome → 其他（AD-6）。主辦方權限一律 `ensure_tournament_owner`（403）。
- `uphold_result`：沿用已寫入的 outcome、勝隊呼叫 `confirm_match`（內含晉級）。
- `correct_result`：只接受 `outcome=played`；整組新的各局以 5.3 的 `scoring` 規則驗證，另加 `SERIES_NOT_DECIDED`、`REDUNDANT_GAMES`；通過後整份替換 `match_game`（repository 新增「刪除該場全部局」）、寫入勝局數與勝隊，再 `confirm_match`；回傳 `CorrectionResult{before_games, after_games, winner_id}`。
- `replay_match`：只接受 `outcome` 為 `forfeit`、`double_forfeit`；`check_replay_time` → `clear_for_replay` → `transition_match(→ scheduled)` → 寫入新時間 → `start_forfeit_clock` → 操作紀錄 `match.replay_scheduled` → 發 `MatchRescheduled`；裁判保留。其他 outcome 回 409 `REPLAY_ONLY_FOR_FORFEIT`。
- `resolve_appeals`：理由去頭尾空白後 1～1000 字（422）；沒有未結案申訴回 409 `NO_OPEN_APPEALS`；同一場所有未結案申訴以相同決定與理由結案，寫 `handled_by`、`handled_at`，不改 `submitted_by`；寫 `appeal.resolved`（更正時含前後各局），發 `AppealResolved{match_id, decision}`。另一隊申訴期限未到也可以處理。
- `count_open_disputes`：未結案申訴數、檢舉數（6.4 合併前回 0）、每筆的處理期限與最早期限；處理期限＝等待結果的下一場預定時間，決賽與季軍賽為申訴提出後 1 小時。
- 公開申訴結果 API 不需登入，只回 `upheld`／`corrected`／null，不含申訴內容（AD-19）。
- S32（`/organizer/tournaments/$tournamentId/appeals`，側欄「申訴」）：Data table 列出申訴（場次、提出隊伍、提出時間、狀態與決定），可查看說明與附件；沒有未結案申訴時顯示「目前沒有待處理的申訴。」。未結案的場次提供「維持原結果」「更正結果」「重新比賽」（只有棄權的場次才出現）；三者都走確認對話框、理由必填，確認鈕重複動作名。更正依比分型態輸入整組各局；重新比賽以 `datetime-local` 選時間（範圍來自 `get_replay_window`），`RESCHEDULE_NO_VALID_TIME` 時顯示後端訊息與「前往場次管理」。
- S27 待處理清單：顯示待處理申訴數與每筆（類型「申訴」、場次、提出時間、處理期限），依期限由近到遠，點選進 S32。
- S4：經申訴處理的已確認場次顯示「維持原結果」或「更正結果」。
- 只新增 D 的 competition、A 的 S4／S27／側欄檔案中的函式或掛載點，不改既有行為；PR 說明列出並請對方審查。

**Never:**
- 不做 6.3（逾期提醒、處理期限變色）、通知（只發事件）、檢舉處理與 S33。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 維持 | 申訴中、兩筆未結案 | 兩筆結案（同決定、理由）；場次已確認並晉級；S4 顯示「維持原結果」 | — |
| 更正改變勝隊 | 申訴中、played、新各局翻盤 | 各局替換、勝隊改變、已確認並晉級新勝隊；紀錄含前後各局；S4 顯示「更正結果」 | 未分勝負 409 `SERIES_NOT_DECIDED`、多餘局 409 `REDUNDANT_GAMES`，資料不變 |
| 重新比賽 | 申訴中、forfeit／double_forfeit、合法新時間 | 回到待開打、清除結果與報到、新時間、棄權重新起算 | 非棄權 409 `REPLAY_ONLY_FOR_FORFEIT`；時間不合法沿用 `RESCHEDULE_*` 409 |
| 期限未到先處理 | 另一隊仍在申訴期限內 | 可以處理；之後另一隊無法再申訴 | — |
| 沒有未結案申訴 | 已處理過 | — | 409 `NO_OPEN_APPEALS` |
| 非主辦方 | 其他帳號 | — | 403 `TOURNAMENT_OWNER_REQUIRED`；S32 顯示 S38 |
| 理由空白 | `"  "` | 前端無法送出 | API 422 |
| 公開結果 | 已維持／已更正／未處理 | `upheld`／`corrected`／null | 場次不屬於該賽事 404 |

## Decisions

- 2026-11-09（使用者）：Epic 6 分工改回 #55 最早的約定：competition 端 6.2 的 `uphold_result`、`correct_result`、`replay_match` 與 6.5 的 `disqualify` 由 B 寫在 competition 新檔，`service.py` 只新增公開函式，D 審查；取代 6.1 spec 記錄的 2026-11-08 協議。`contracts/disputes.md` 分工表隨本 Story 更新。
- 2026-11-09（使用者）：另一隊申訴期限未到時，主辦方也可以處理；處理後場次已確認，另一隊不能再申訴。
- 2026-11-09（使用者）：不拆階段，前後端同一個 PR；spec 超過 1,600 tokens 仍維持完整。
- 2026-11-09（AC「一方或雙方」）：重新比賽也適用 `double_forfeit`，約定只寫 `forfeit` 的地方隨本 Story 更新。
- 2026-11-09（使用者，審查第 0 項）：為支援雙方棄權重賽，例外修改 D 的既有函式 `get_replay_window`（也接受 `double_forfeit`）與 D 的測試參數；這是本 Story 唯一改到 D 既有行為的地方，不受上方「不改既有行為」限制，PR 說明列出並請 D 審查。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/appeals.py` -- 6.1 的 `mark_appealed`；新增三個函式。`service.py:1912` 以延遲 import 包裝，新函式照做。
- `backend/app/modules/competition/service.py` -- 沿用 `lock_match`:626、`transition_match`:637、`start_forfeit_clock`:652、`clear_for_replay`:675、`confirm_match`:752（含 `advance`）、`check_replay_time`:1844、`get_replay_window`:1872；比分 helper `_score_rejection`:1301、`_series`:1372、`_sync_wins`:1407、`submit_result`:1532（勝隊對應）。`_confirm` 不寫勝局數。
- `backend/app/modules/competition/repository.py` -- `list_games`:319、`add_game`:329、`set_match_wins`:358；新增刪除全部局。`scoring.py` 的 `make_game`:92、`series`:130、`check_record`:154；`models.py` 的 `GameScoreIn`:417、`ReplayCleared`:362、`RescheduleInfo`:491。
- `backend/app/modules/disputes/` -- 6.1 的 `Appeal`、`AppealRead`、`_to_read`:70、`_match_in_tournament`:118、附件下載路由；新增列表回傳以場次分組（含場次編號、outcome、比分型態、BO、目前各局、隊名），以及重賽時間範圍路由（呼叫 `get_replay_window`）。
- 前端：`features/tournaments/organizer-nav.ts`（`tournamentNav()` 加「申訴」）、`OrganizerTournamentOverview.tsx:225`（加待處理清單區塊）、`routes/organizer/tournaments/$tournamentId/`（新增 `appeals.tsx`）、`components/common/{DataTable,ConfirmDialog}.tsx`（ConfirmDialog 已有必填理由）、`features/competition/RescheduleDialog.tsx:46-83`（時間範圍寫法，抽共用或照抄，不改它）、`ScoreEntryPanel.tsx:83` 的 `REASON_TEXT`；S4 在 `routes/tournaments/$tournamentId/matches/$matchId.tsx`（6.1 的插槽寫法）與 `MatchHeader.tsx:24`。新元件放 `features/disputes/`。

## Tasks & Acceptance

**Execution:**
- [x] `competition/{repository,appeals,service,models}.py` -- 三個函式與 `CorrectionResult`
- [x] `disputes/{models,repository,service,router}.py` -- 列表、處理、待處理計數、公開結果、重賽時間範圍
- [x] `tests/competition/test_appeal_resolution.py`、`tests/disputes/test_resolve_appeals.py` -- 覆蓋 I/O 矩陣、晉級、紀錄、事件、處理期限
- [x] `frontend/src/client/` -- 重新產生
- [x] `features/disputes/` 新元件、`appeals.tsx` 路由、側欄、S27 區塊、S4 標示、`routeTree.gen.ts` -- 前端
- [x] `frontend/tests/unit/` -- S32 三種處理、理由必填、重新比賽只出現在棄權場次、S27 排序、S4 標示
- [x] `contracts/disputes.md`、`sprint-status.yaml` -- 分工表與新增 schema、路由；6-2 改 `in-progress`

**Acceptance Criteria:**
- Given 兩隊都申訴的場次，when 主辦方在 S32 更正結果，then 兩筆同時結案、`submitted_by` 不變、下一場出現新勝隊。
- Given 兩場申訴中（一場有下一場、一場是決賽），when 開啟 S27，then 待處理數為 2，依處理期限由近到遠排序。

## Implementation Notes

- competition：`appeals.py` 新增 `uphold_result`、`correct_result`、`replay_match`，`service.py` 只新增三個以函式內 import 包裝的公開函式；repository 新增 `delete_games`；models 新增 `CorrectionResult`。三者共用 `_locked_appealed`（`lock_match` → 只接受 `appealed` 且有 outcome）。`correct_result` 用 service 的 `_bo`、`_score_rejection`、`_public_game`（同模組內的私有函式），錯誤碼與 5.3、5.4 完全相同；非 `played` 時回新的 409 `CORRECTION_ONLY_FOR_PLAYED`（約定原本沒寫錯誤碼）。前後各局記在 disputes 的 `appeal.resolved`，competition 端只有 `confirm_match` 寫的 `match.confirmed`。
- `replay_match` 另外檢查賽事是 `published`／`ongoing`（否則 409 `TOURNAMENT_NOT_RESCHEDULABLE`），與 `get_replay_window` 的判斷一致；操作紀錄 `match.replay_scheduled` 的 `before` 為 `ReplayCleared` 全部欄位加原狀態與原時間。
- 依 Decisions（AC「一方或雙方」），D 的 `get_replay_window` 由只接受 `forfeit` 改為也接受 `double_forfeit`，D 的 `test_replay_hooks.py::test_window_appealed_but_not_forfeit` 參數的 `double_forfeit` 換成 `walkover`。這是本 Story 唯一改到 D 既有函式與測試的地方，PR 說明要列出。
- disputes：`resolve_appeals` 在 `lock_match` 後先確認有未結案申訴（409 `NO_OPEN_APPEALS`），再交給 competition 判斷狀態與 outcome；理由用與申訴說明相同的清理（去控制字元與雙向控制字元）。決定需要的欄位缺漏時回 422（`APPEAL_GAMES_REQUIRED`、`APPEAL_REPLAY_AT_REQUIRED`）。`count_open_disputes` 多收 `actor_id` 檢查主辦方，並回每筆 `items`（S27 要列每筆）；處理期限取勝隊、敗隊去的場次中較早者（準決賽同時等決賽與季軍賽）。待處理數以申訴筆數計（兩隊都申訴算 2）。
- 新 API：`GET /organizer/tournaments/{tid}/appeals`、`POST …/matches/{mid}/appeal-resolution`、`GET …/matches/{mid}/replay-window`、`GET /organizer/tournaments/{tid}/open-disputes`（皆 `Organizer`）、`GET /tournaments/{tid}/matches/{mid}/appeal-result`（公開 GET，不需加 `PUBLIC_WRITE_ROUTES`）。公開結果只在場次已確認時，以最後一次處理的決定為準；重新比賽為 null。
- 前端：`features/disputes/` 新增 `AppealsPage`（S32）、`ResolveAppealDialogs`（維持用共用 `ConfirmDialog`；更正、重賽用同樣寫法的 AlertDialog，多放各局或時間欄位，未改 `ConfirmDialog`）、`OpenDisputesPanel`（S27）、`AppealResultBadge`（S4）、`organizer-queries`。重賽時間欄照 `RescheduleDialog` 的寫法另寫，沒有改它；任一 `RESCHEDULE_*` 409 後重抓時間範圍（competition.md 的要求）。附件以 client 下載 blob 後在新分頁開啟。
- 動到 A 的檔案（只加掛載點）：`organizer-nav.ts`（側欄「申訴」）、`OrganizerTournamentOverview.tsx`（賽程已公布、進行中、已結束時顯示待處理清單）、`MatchHeader.tsx`（`extra` 插槽）、`MatchSpectatorView.tsx`（`headerExtra` 轉傳）、S4 路由（傳入 `AppealResultBadge`）；A 的 `organizer-tournaments.test.tsx` 側欄項目清單加上「申訴」。
- 發現但不在範圍內：重新比賽後，上一輪申訴過的隊伍不能再對同一場申訴（唯一鍵不分輪次），已記入 `deferred-work.md`。
- 審查第 1 輪 patch（#1、2、3、4、7、9、11、13、14、16、17、23）：
  - 後端：`AppealResolveIn.games` 加 `max_length=7`（OpenAPI 多 `maxItems`，產生的 client 型別不變）；S32 列表的隊名改為以 registration `get_team_names` 依 `appeal.team_id` 一次查齊，6.5 頂替後原申訴隊仍顯示隊名（測試以假的 registration 取代 `get_team_names`）。
  - 後端測試補上：處理與重賽時間範圍路由對其他賽事的場次回 404、`open-disputes` 排除已結案、準決賽取決賽與季軍賽較早者、季軍賽為提出後 1 小時、`games` 超過 7 局 422、`APPEAL_REASON_TOO_LONG`、`APPEAL_REPLAY_AT_REQUIRED`、無時區 `replay_at` 422、重賽後再確認公開結果仍為 null；`submitted_by` 不變的測試改用裁判帳號當送出者。
  - 前端：決定文字共用 `features/disputes/decision-label.ts`；三個處理對話框的說明先列「目前結果」（比分與勝隊、棄權方或雙方棄權）；重賽時間範圍查詢移到 `RematchAppealDialog`（`enabled: open`），`match_not_reschedulable`／`tournament_not_reschedulable` 時顯示說明、不顯示時間欄、確認鈕停用；查看附件在點擊當下先 `window.open("")` 開空白分頁（設 `opener = null`），下載完成後再導到 blob 網址，失敗時關閉分頁，被瀏覽器擋下時以錯誤 Toast 提示。
  - 前端測試補上：S4 路由層級的處理結果徽章（`match-route.test.tsx`）、對話框的目前結果、重賽被擋的說明、附件分頁在下載完成前就開啟。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-09，Blind Hunter、Edge Case Hunter、Verification Gap）：

| # | 來源 | 發現 | 判定 | 處置 |
|---|---|---|---|---|
| 0 | 主持人核對 diff | `get_replay_window` 原本只接受 `forfeit`，實作改了 D 的既有函式與 D 的測試參數以接受 `double_forfeit`；違反 Always「不改既有行為」，但 Decisions 要求雙方棄權也能重賽，兩條在凍結區內互相衝突 | medium：D 的函式行為改變，需 D 審查 | intent_gap → 使用者決定保留修改並請 D 審查（見 Decisions） |
| 1 | VG | 處理、重賽時間範圍路由沒有測「場次不屬於該賽事」回 404 | medium：授權邊界，刪掉檢查測試仍全過 | 已完成（patch） |
| 2 | VG | `open-disputes` 沒測已結案申訴被排除 | medium：拿掉 `open_only` 測試仍過 | 已完成（patch） |
| 3 | VG、BH | 準決賽（`loser_next_match_id`）與季軍賽的處理期限沒有測試 | medium：spec 明文規則，改壞測試仍過 | 已完成（patch） |
| 4 | VG | S4 路由層級沒測處理結果徽章 | medium：拿掉掛載點測試仍過 | 已完成（patch） |
| 5 | VG 其他 | 既有 S4 路由測試沒 mock `readAppealResult` | low：`retry:false`、失敗不顯示 | 不處理 |
| 6 | ECH | 已取消／已結束賽事仍可維持、更正 | false：取消賽事（2.6）期中未實作；賽事在決賽與季軍賽都確認後才結束，不會留下申訴中的場次 | 不處理 |
| 7 | ECH | `games` 沒有長度上限 | low：直接加 `max_length=7` | 已完成（patch） |
| 8 | ECH | 決定不需要的欄位（games、replay_at）被靜默忽略 | low：多加分支，日常不會遇到 | 不處理 |
| 9 | ECH、BH | 重賽時間範圍 `match_not_reschedulable`／`tournament_not_reschedulable` 時前端無說明、仍可送出 | medium：另一分頁已處理時會遇到 | 已完成（patch） |
| 10 | ECH | 已取消賽事 S27 不顯示待處理 | false：取消賽事期中未實作 | 不處理 |
| 11 | BH | `submitted_by` 不變的測試用主辦方當送出者，改壞也會過 | low：程式沒改 `submitted_by`，但測試無效 | patch（改用隊長或裁判）→ 已完成（改用裁判帳號） |
| 12 | BH | spec、約定、程式對 `submitted_by`／`filed_by` 用詞不一 | low：修法是改 spec | 不處理 |
| 13 | BH | 隊名只從場次目前兩隊找，6.5 頂替後原申訴隊顯示「未知隊伍」 | medium：6.5 合併後必然發生 | patch（以 registration `get_team_names` 依 `appeal.team_id` 查）→ 已完成 |
| 14 | BH | S32 處理前看不到目前結果（比分、勝隊、棄權方） | medium：主辦方確認「維持原結果」卻看不到結果 | patch（對話框說明列出目前結果；資料已在 `AppealGroup`）→ 已完成 |
| 15 | BH | 更正內容與原結果相同仍可送出 | low：日常少見，修法要加比較邏輯 | 不處理 |
| 16 | BH | 附件在 `await` 後才 `window.open`，Firefox／Safari 會擋彈出視窗 | medium：主辦方看不到附件 | 已完成（patch） |
| 17 | BH | 缺 `APPEAL_REASON_TOO_LONG`、`APPEAL_REPLAY_AT_REQUIRED`、無時區 `replay_at`、重賽後公開結果為 null 的測試 | low：行為已實作，補測試 | 已完成（patch） |
| 18 | BH | S27 與 S32 排序不同、季軍賽標籤 | low：多加連結參數與欄位 | 不處理 |
| 19 | BH | 前端以 UTF-16 計理由長度、後端以 code point；註解寫「與前端一致」 | low：只影響 emoji 等字元 | 不處理 |
| 20 | BH | `appeals.py` 依賴 D `service.py` 的私有 helper | low：寫進 PR 說明請 D 審查，不改程式 | 不處理（PR 說明列出） |
| 21 | BH | `AppealResolved` 沒有 `appeal_ids` | low：約定的 payload，操作紀錄已有 | 不處理 |
| 22 | BH | `list_tournament_appeals`、`count_open_disputes` 逐場查詢 | low：申訴場次很少 | 不處理 |
| 23 | BH | 決定文字在 `AppealResultBadge`、`AppealsPage` 各定義一次 | low：直接共用一份 | 已完成（patch） |
| 24 | BH | spec 狀態、AI 使用紀錄未補 | false：in-review 是流程狀態；紀錄在 step-05 補 | 不處理 |
| 25 | BH | 側欄「申訴」在所有賽事狀態都顯示 | low：只是空狀態 | 不處理 |

## Verification

本工作樹與其他工作樹的容器同時在跑，compose 指令都加 `-p espory-6-2 -f compose.yml -f "C:/Users/grace/AppData/Local/Temp/claude/41f60a345d7607b4/1fabc1f3-312d-4d81-a1f5-4b734a9929d3/scratchpad/ports-6-2.yml"`（以下簡寫 `dc`）；不要停止或重建其他專案的容器。

**Commands:**
- `dc up -d --build --wait db backend mailpit` 後 `dc exec backend bash scripts/test.sh` -- expected: 全部通過、覆蓋率門檻通過
- `dc exec backend bash scripts/lint.sh` -- expected: mypy、ty、ruff 通過
- `bash scripts/generate-client.sh` -- expected: client 只多出新 API
- 前端 build、typecheck、biome、單元測試（README〈測試與檢查〉）-- expected: 全部通過
