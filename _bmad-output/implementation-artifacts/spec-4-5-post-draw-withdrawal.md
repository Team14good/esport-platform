---
title: 'Story 4.5：抽籤後退賽與候補遞補'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: '0493512d6804e7f6661c5dd1a3ac1e3cd101d22c'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-7-withdraw-registration.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-5-disqualify.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 抽籤後隊伍無法出賽時沒有退出的方法，只能不出席等棄權；空出的對戰表位置也無法讓候補頂上（FR-17）。6.5 抽籤後取消「還沒比過」的隊伍時，期中版只判對手獲勝、不遞補，與 epics 6.5「比照 Story 4.5」不符。

**Approach:** competition 新增抽籤後退賽：隊長在 S17 按「退賽」，competition 依 AD-6 先鎖賽事、再依 id 遞增鎖對戰表全部場次，確認隊伍第一場仍待開打後，請 registration 把報名轉「退賽」並取出候補第 1 位（截止後順位：平均段位積分、送出時間、id，每校正取＋已參賽不超過 2 隊），由遞補隊伍接手同一個位置、報名直接轉「已參賽」；兩隊確定時重設棄權期限（AD-7）。沒有候補時該場以 `walkover` 確認、對手晉級。6.5 的同類情況接上同一套遞補（改法見 Decisions 第 3 項）。

## Decisions

2026-11-22 黃鉅燊核准：待決定 1～8 全部採建議選項，spec 整份保留（約 9 千 tokens，超過 1,600；保留完整 spec）。

1. 輪空隊伍退賽、第二輪對手未定、又沒有候補（選 A）：拒絕，409 `TEAM_NOT_RETIRABLE`，訊息「對手確定後才能退賽。」；S17 退賽按鈕停用並顯示這個原因。不改 progression、不加遷移。有候補時照常遞補（對手未定不影響換位）。
2. 自訂模式（選 A）：本份不做。`backfill_drawn_from_waitlist` 對非 `campus` 回 `None`（等同沒有候補 → walkover）；deferred-work 新增一項交給 C 的 3.10，在同一個函式內補「最早送出的候補、不限每校 2 隊」。
3. 6.5 接上遞補（選 A，含全部子項）：遞補流程寫在 competition 新檔 `retirement.py`；只改 `service.disqualify` 本體那一行轉呼叫：該隊「沒有已確認場次、唯一未結束的場次為 `scheduled`」時走 `retirement.py` 的取消資格遞補，其他情況照舊呼叫 `disqualification.disqualify`。B 的 `disqualification.py` 一行都不動；PR 說明列出並請 B（@sususu0804）審查。子項：
   - (a) 沒有候補時 outcome 維持 `disqualified`（判對手勝並晉級，與 6.5 現狀相同，對戰樹顯示「取消資格」）。
   - (b) 第一場已開打（`live`／`appeal_window`／`appealed`）才被取消資格：維持 6.5 現狀（判對手勝、不遞補），即不進新分流。
   - (c) 第一場待開打但已有報到：仍遞補，刪除被取消隊伍的報到；報到限制只約束隊長退賽。
   - (d) 對手未定且有候補：遞補（原本 409）；對手未定且沒有候補：維持 409 `DISQUALIFY_OPPONENT_PENDING`。
   - 新分流沿用 6.5 的前置檢查與錯誤碼（賽事已結束／已取消 409、隊伍不屬於該賽事 404、已取消資格 409），操作者為主辦方；回傳 `DisqualifyResult`（`affected_match_ids`＝該場、`replacement_team_id`＝遞補隊或 None）。
4. 報到限制（選 A）：第一場任一隊已報到 → 409 `TEAM_NOT_RETIRABLE`「已有隊伍報到，無法退賽」，S17 不顯示退賽；補「退賽與報到同時」兩種順序的併發測試。
5. 確認對話框（選 A）：標題「退賽」；內文「退賽後無法恢復。有候補隊伍時，由候補第 1 位接手你們在對戰表上的位置；沒有候補時，對手以輪空晉級。」；確認鈕「退賽」（destructive）；成功 Toast「已退賽」。
6. 通知（選 A）：新增事件 `BracketBackfilled`（`match_id`、`team_id`、`replaced_team_id`，退賽與 6.5 遞補共用）→ 遞補隊全員，標題「已遞補進入對戰表」，內文「「隊名」已由候補遞補，接手「賽事」M3 的位置。」（M3 為場次代碼），連結沿用既有 `_match_link`。對手：兩隊確定時沿用既有 `MatchOpponentsDecided`，不另發。沒有候補時（退賽）新增事件 `OpponentRetired`（`match_id`、`winner_id`）→ 對手隊長，標題「對手退賽」，內文「M3 的對手已退賽，你們以輪空晉級。」。退賽隊不另通知。
7. 重賽中的第一場（選 A）：只看狀態 `scheduled`，重賽中的第一場也可退賽。
8. 4.2 後續（選 A）：不做；deferred-work 新增一項（修法：`auto_draw` 鎖內若現在正取 ≥2 且大於 `skip.accepted_teams` 就照常抽籤）。

Design Notes 的兩項由實作者決定並保留：操作紀錄沿用既有動作（不新增 audit 動作代碼、不改 `AUDIT_ACTION_LABELS`）；不需要 Alembic 遷移。

## Boundaries & Constraints

**Always:**
- 可退賽的條件（鎖內以最新值檢查）：檢視者是該隊隊長；報名為 `drawn`；賽事為 `published` 或 `ongoing`；該隊在對戰表上沒有任何已確認的場次，且它唯一未結束的場次為 `scheduled`（輪空隊伍的第一場是第二輪那一場）。
- 鎖的順序：`lock_tournament` → `lock_bracket_matches`（id 遞增）→ 判斷 → 寫入；全部判斷完成才寫入，任何拒絕都不改資料、紀錄與事件。router commit（AD-5）。
- 先把退賽隊報名轉 `retired`（操作者為隊長），再取候補，讓退賽隊的學校名額先釋出。順位與 S17 顯示的候補順位一致：沿用 registration `_waitlist_order`（抽籤後 `_current_phase` 必為截止後，`departed_schools` 不參與）。候補第 1 位轉 `drawn`（`waitlisted` → `drawn` 是既有合法轉換）並寫 `backfilled_at`，操作者為系統。遞補不看名額（一對一換位）。
- 遞補：`set_match_team` 換成遞補隊、寫 `match.teams_changed`（操作者為隊長，`after` 帶 `retired_team_id`）、`unassign_referee_if_member`；兩隊都在時 `start_forfeit_clock` 並發 `MatchOpponentsDecided`。
- 沒有候補：`clear_match_team` 移出退賽隊、寫 `match.teams_changed`，再 `confirm_walkover`（對手晉級，後續操作者為系統）。
- registration 只新增公開函式，不改 C 的既有函式與 `_TRANSITIONS`；competition 經 `registration_port` 呼叫。
- 錯誤碼：非隊員或非隊長 403（`TEAM_MEMBER_REQUIRED`／`TEAM_CAPTAIN_REQUIRED`，比照 3.7）；隊伍不存在 404 `TEAM_NOT_FOUND`；不符合可退賽條件 409 `TEAM_NOT_RETIRABLE`（訊息依原因）。
- 介面文字繁體中文、按鈕動詞＋名詞；S17 的退賽按鈕只在後端回報可退賽時出現。

**Never:**
- 不改 3.7 抽籤前撤回（`withdraw_registration`）與它的按鈕；兩者在 S17 不會同時出現（`withdrawable` 只在抽籤前為真）。
- 不改 B 的 `disqualification.py` 既有函式、不改 C 的 registration 既有函式、不改 A 的 notifications 既有規則（只在檔尾新增）。
- 不做第一場開打後的退賽、抽籤後退回報名、自訂模式遞補的分配規則（3.10）。

## I/O & Edge-Case Matrix

學校以大寫字母表示；括號內是學校與平均段位積分。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一輪退賽、有候補 | T1（X）在 M1 對 T2，M1 待開打、無報到；候補 W1（Y，80）、W2（Z，90） | T1 `retired`；W2 `drawn`＋`backfilled_at`，接手 M1 的 T1 位置；棄權期限＝max(預定時間, 現在)＋棄權時限；通知、紀錄 | N/A |
| 每校上限 | 退賽隊 X 校；X 校另有 2 隊已參賽；候補 W1（X，95）、W2（Y，70） | W1 略過（`SCHOOL_LIMIT_REACHED`），W2 遞補 | N/A |
| 退賽隊同校候補 | 退賽隊 X 校（X 校共 2 隊已參賽）；候補 W1（X，95）、W2（Y，70） | 退賽後 X 校剩 1 隊，W1 遞補 | N/A |
| 沒有候補 | M1 待開打、沒有 `waitlisted` | T1 `retired`、移出 M1；M1 `walkover` 確認，T2 進下一場（下一場兩隊湊齊時開始計時） | N/A |
| 輪空隊伍退賽、對手已定 | T5 輪空入座 M9，M9 對手已由 M2 勝出 | 同第一輪規則（有候補遞補；沒有則 M9 `walkover`） | N/A |
| 輪空隊伍退賽、對手未定 | T5 在 M9，M2 尚未確認 | 有候補：W 接手 T5 位置，M9 仍等 M2；沒有候補：拒絕，不改資料（Decisions 1） | 沒有候補時 409 `TEAM_NOT_RETIRABLE`「對手確定後才能退賽。」 |
| 兩支輪空隊伍相遇 | M9 兩方都是輪空入座、已開始計時；其中一隊退賽並遞補 | 遞補後重設棄權期限 | N/A |
| 已有人報到 | 第一場任一隊已報到 | 拒絕，不改資料（Decisions 4） | 409 `TEAM_NOT_RETIRABLE`「已有隊伍報到，無法退賽」 |
| 第一場已開打 | 第一場 `live`／`appeal_window`／`appealed`／`confirmed` | 拒絕，不改資料 | 409 `TEAM_NOT_RETIRABLE` |
| 已贏過一場 | 第一場已確認（含輪空 walkover）、在下一場等待 | 拒絕 | 409 `TEAM_NOT_RETIRABLE` |
| 非隊長 | 選手或非隊員呼叫 | 拒絕 | 403 |
| 報名不是已參賽 | `waitlisted`／`retired`／`disqualified` | 拒絕 | 409 `TEAM_NOT_RETIRABLE` |
| 退賽與報到同時 | 兩者並行 | 先退賽：退賽隊的報到被拒（不在該場）；先報到：退賽被拒。不會出現已報到的場次被退賽 | 409 |
| 退賽與取消資格同一隊同時 | 兩者並行 | 由賽事鎖序列化；後到者被拒 | 409 |
| 裁判衝突 | 指派的裁判是遞補隊隊員 | 清空裁判、寫 `match.referee_unassigned`、發 `RefereeUnassigned` | N/A |
| 6.5 取消還沒比過的隊伍 | 第一場待開打；有／沒有候補 | 有候補：被取消隊伍 `disqualified`、候補第 1 位遞補（同退賽換位，含刪除被取消隊伍的報到）；沒有候補：以 `disqualified` 判對手勝並晉級（Decisions 3） | 對手未定且沒有候補 409 `DISQUALIFY_OPPONENT_PENDING` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/disqualification.py`（B 的檔案，只讀）-- 結構範本：`_plan` 只讀、全部判斷完才寫；`_replace`(:252) 的換位、`_record_teams`(:201)、`_award`(:225) 待開打改走 `service._confirm`＋`advance`。
- `backend/app/modules/competition/service.py` -- `disqualify`(:2534，Decisions 第 3 項：只改它本體那一行轉呼叫)、`confirm_walkover`(:934，要求一方為空)、`start_forfeit_clock`(:806)、`unassign_referee_if_member`(:2192)、`list_team_matches`(:767)、`check_in`(:1269，只鎖場次)；新增公開函式 `retire_team`、`get_retirement_status`（委派給新檔）。
- `backend/app/modules/competition/repository.py` -- `get_bracket_by_tournament`(:36)、`lock_bracket_matches`(:194)、`set_match_team`(:248)、`clear_match_team`(:264)、`list_check_ins`(:307)。
- `backend/app/modules/competition/progression.py` -- `advance`(:204)；walkover 只允許一方在場（`_check_consistent` :149-153），所以沒有候補時要先 `clear_match_team` 再 `confirm_walkover`。
- `backend/app/modules/competition/registration_port.py` -- 新增 `retire_registration`、`backfill_drawn_from_waitlist` 兩個轉接（`_lookup` 模式）。
- `backend/app/modules/competition/models.py` -- `DisqualifyResult`(:431)、`MatchOpponentsDecided`(:229) 旁新增 `RetirementStatus` 回應、`BracketBackfilled`／`OpponentRetired` 事件（依 Decisions 第 6 項）。
- `backend/app/modules/competition/router.py` -- 新增 `GET`／`POST /teams/{team_id}/retirement`（VerifiedAccount，登入才能用，不加 `PUBLIC_WRITE_ROUTES`）。
- `backend/app/modules/registration/service.py`（C 的檔案，只新增）-- 可沿用 `_lock_tournament`(:67)、`mark_status`(:268)、`_waitlist_order`(:483)、`_registrations_in`(:1115)、`_ORDER_STATUSES`(:443)；`disqualify_registration`(:1801) 是新函式的範本（鎖後 `session.refresh`）。新增：
  - `retire_registration(session, *, team_id, actor_id)`（服務回 `RegistrationRead`，port 轉接回 `None`）：鎖賽事、refresh，`drawn` → `retired`；其他狀態 409 `REGISTRATION_INVALID_TRANSITION`。
  - `backfill_drawn_from_waitlist(session, *, tournament_id) -> uuid.UUID | None`：鎖賽事；非 `campus` 回 None（Decisions 第 2 項）；`_waitlist_order` 第 1 位寫 `backfilled_at`、`mark_status(→DRAWN, actor_id=None)`，回傳隊伍 id；不發 `RegistrationBackfilled`（它的文字是「遞補為正取」）。
- `backend/app/modules/registration/allocation.py` -- `_after_deadline_order`(:285) 已含每校 2 隊上限，不需改。
- `backend/app/modules/notifications/rules.py`（A 的檔案）-- 檔尾新增規則；沿用 `_member_ids`(:88)、`_match_link`(:98)、`_match_label`(:102)。
- `backend/app/modules/disputes/service.py`（B）-- `resolve_report`(:1060) 讀 `affected_match_ids`、`replacement_team_id`，不需改。
- 前端
  - `frontend/src/routes/teams.$teamId.tsx` -- 已用 `renderStatusExtra` 放 disputes 的取消資格理由；改為 `drawn` 時同時渲染新的退賽區塊。
  - 新增 `frontend/src/features/competition/RetireTeamSection.tsx`、`retirement-queries.ts`、`useRetireTeam.ts`；確認框用 `components/common/ConfirmDialog.tsx`；範本 3.7 的 `features/registration/SubmitRegistrationSection.tsx`（確認框開著時保持掛載，避免錯誤訊息閃掉）。
  - `features/registration/registration-status.tsx` 已有 `retired: "退賽"`，不需改。
- 遷移：不需要（Decisions 第 1 項選 A）。
- 測試範本：`backend/tests/competition/test_disqualify.py`、`test_check_in.py`、`test_registration_port.py`（自建 `MyTeamCard` 替身）、`tests/registration/test_withdraw_registration.py`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/service.py` -- 新增 `retire_registration`、`backfill_drawn_from_waitlist` -- C 模組只新增公開函式（PR 說明列出）。
- [x] `backend/app/modules/competition/registration_port.py` -- 兩個轉接。
- [x] `backend/app/modules/competition/models.py` -- `RetirementStatus`（`retirable`、`reason`）、新事件。
- [x] `backend/app/modules/competition/retirement.py`（新檔）-- `_plan`／寫入兩段：可退賽判斷、遞補換位或 walkover；6.5 共用的遞補函式（依 Decisions 第 3 項）。
- [x] `backend/app/modules/competition/service.py` -- 新增 `retire_team`、`get_retirement_status`；依 Decisions 第 3 項調整 `disqualify` 的分流。
- [x] `backend/app/modules/competition/router.py` -- 兩個端點，router commit。
- [x] `backend/app/modules/notifications/rules.py`＋`backend/tests/notifications/` -- 新事件規則與測試。
- [x] `backend/tests/competition/test_retire_team.py`、`test_retire_concurrency.py` -- I/O 矩陣每列一個測試；併發：退賽對報到、退賽對取消資格，兩種順序。
- [x] `backend/tests/registration/test_post_draw_backfill.py` -- 兩個新函式：每校上限、退賽隊同校候補、沒有候補、自訂模式回 None。
- [x] `backend/tests/competition/test_disqualify.py` -- 依 Decisions 第 3 項新增遞補案例；既有案例只在行為改變處調整並列入 Implementation Notes。
- [x] `scripts/generate-client.sh` -- 重新產生 `frontend/src/client`。
- [x] 前端 `features/competition/RetireTeamSection.tsx` 等三檔、`routes/teams.$teamId.tsx`、`frontend/tests/unit/` -- 可退賽才顯示按鈕；確認、成功後讓隊伍與 S12 查詢失效；被拒時錯誤訊息留在對話框。
- [x] `frontend/tests/e2e/`（`@story-4.5`）-- 隊長退賽、候補遞補後在 S3 對戰樹看到新隊名。
- [x] `_bmad-output/implementation-artifacts/contracts/competition.md` -- 新增公開函式、端點、錯誤碼；`sprint-status.yaml` 4-5 改 `in-progress`；`deferred-work.md` 依決定新增或刪除項目。

**Acceptance Criteria:**
- Given 隊長在 S17 且隊伍可退賽，when 按「退賽」並確認，then 報名徽章變「退賽」、按鈕消失；遞補隊的 S17 顯示「已參賽」，S3 對戰樹在下一次輪詢顯示遞補隊名。
- Given 不能退賽的隊伍（含非隊長），when 開 S17，then 看不到退賽按鈕；直接呼叫 API 得到上表的錯誤碼且資料不變。
- Given 退賽或遞補完成，when 主辦方開 S34，then 看得到報名狀態變更（退賽、已參賽）、場次隊伍變更與（沒有候補時）確認比賽結果的紀錄。
- Given 後端與前端，when 執行 `scripts/test.sh`、`scripts/lint.sh`、前端 `bun run lint` 與 vitest，then 全部通過。

## Implementation Notes

- 新增三個 registration 公開函式（spec 列兩個）：`has_backfill_candidate(tournament_id, leaving_team_id)`，只讀，供「輪空隊伍對手未定又沒有候補」與 6.5「對手未定」在寫入前判斷能否遞補（Decisions 1、3(d) 要求拒絕時不改資料；先寫再回滾會讓替身與紀錄不一致）。預估時把退賽隊排除在名單外，與實際「先轉 `retired` 再取候補」的順位一致。
- `registration_port` 另加 `get_team_tournament_id`（經 `get_team`，隊伍不存在 404 `TEAM_NOT_FOUND`）；`RegistrationState` 新增 `status`（預設 `"drawn"`，替身不必改），退賽要求報名為 `drawn`。
- `competition.check_in`、`_locked_for_scoring`（比分寫入）、`upload_result_screenshot`（結算截圖）改為先 `lock_tournament` 再 `lock_match`（AD-6）。原本只鎖場次：併發測試實際抓到死結（報到持有場次鎖後寫操作紀錄，對賽事列取共享鎖；退賽持有賽事鎖後等場次鎖）。刪除 deferred-work 第 5.1 的「報到只鎖場次」與第 5.3 的「比分寫入只 `lock_match`」項目（修法與該項相同）。代價：同一賽事的報到彼此序列化（鎖很短）。
- 新增檔案 `competition/retirement.py`；`service.disqualify` 本體只改成轉呼叫 `retirement.disqualify`，B 的 `disqualification.py` 沒動。轉呼叫條件之外的情況（含賽事已結束／已取消、隊伍不屬於賽事、已取消資格）全部交給 `disqualification.disqualify` 產生原本的錯誤。
- 既有測試沒有調整行為；只擴充 `tests/competition/conftest.py` 的 `FakeRegistration`（候補、隊長、退賽、遞補、`status`），`disqualify_registration` 替身改為與真實一樣拒絕非 `drawn` 的隊伍。
- 6.5 遞補的審計紀錄 `match.teams_changed` 的 `after` 帶 `disqualified_team_id`（沿用 6.5），退賽帶 `retired_team_id`。
- 6.5 沒有候補的路徑在 `retirement.py` 內重做「判對手獲勝＋`advance`」（呼叫 `service._confirm`，與 `disqualification._award` 的待開打分支相同），沒有呼叫 B 的私有函式。
- 前端：S17 的退賽區塊只在隊長且報名為 `drawn` 時查詢 `GET /teams/{id}/retirement`；`reason` 有值（對手未定又沒有候補）顯示停用按鈕與原因，沒有 `reason` 且不可退賽則不顯示。確認後使隊伍、我的隊伍、下一場（S12）與退賽狀態查詢失效。
- 併發測試（真實 PostgreSQL，`test_retire_concurrency.py`）會在測試資料庫留下報到的操作紀錄；`test_check_in.py` 以全域筆數斷言「沒有新紀錄」，依檔名順序先於本檔執行，所以單獨先跑併發測試再跑 `test_check_in.py` 會失敗。
- e2e `frontend/tests/e2e/retire-team.spec.ts`（`@story-4.5`）已寫、已通過 lint 與型別檢查，但這次環境沒有執行（需要完整 compose 與 worker）。

## Spec Change Log

## Review Triage Log

程式審查（2026-11-22，Blind Hunter（BH）、Edge Case Hunter（ECH）、Verification Gap（VG）三層獨立子代理；另加完整 `scripts/test.sh` 第一輪結果）：

| # | 來源 | 發現 | 判定與依據 | 去向 |
|---|------|------|-----------|------|
| R1 | test.sh | `test_traceability.py::test_every_test_file_is_listed` 失敗：新的 4 個測試檔沒寫進 `tests/traceability.yaml` | high：CI 必失敗（第一輪 1 failed、2717 passed） | patch |
| R2 | BH、ECH | 退賽先鎖賽事再鎖全部場次，比分寫入（`_locked_for_scoring`）與結算截圖只 `lock_match` 後寫操作紀錄（對賽事列取共享鎖），兩者同時會死結回 500 | medium：與本份已修的 `check_in` 同一機制（service.py:1547、:1813 只 `lock_match`）；6.5 既有路徑也有，但退賽讓它更常發生 | patch：比照 `check_in` 先 `lock_tournament`；一併處理 deferred 5.3 項 |
| R3 | ECH（claim） | 契約與 Implementation Notes 暗示改了 `check_in` 就不會死結 | medium：只改報到時不成立（同 R2） | patch：與 R2 一起改說法 |
| R4 | VG | `check_in` 的鎖序只有機率性併發測試保護，拿掉 `lock_tournament` 多數執行順序仍綠 | medium（VG 已驗證） | patch：確定性鎖序測試 |
| R5 | BH、ECH | 沒有候補分支用 `assert target.opponent is not None`，預估與實際遞補不一致時在寫入後變 500 | low：兩者都用 `_waitlist_order` 且排除離開的隊伍，正常不會不一致；修正只是把 assert 換成業務錯誤 | patch |
| R6 | VG | 「先讓離開的隊伍出局、再取候補」的順序沒有測試；替身不看學校，對調兩個呼叫仍全綠 | medium（VG 已驗證）：真實資料下同校候補會被跳過 | patch：真 registration 的 competition 端測試 |
| R7 | BH | `RegistrationState.status` 正式程式預設 `"drawn"` | low：漏傳時會誤判可退賽；修正是刪除預設值 | patch |
| R8 | ECH | 退賽被拒（409）後重新取得隊伍、報名已非 `drawn`，退賽區塊卸載，錯誤訊息一閃即逝 | medium：3.7 E2E 抓過同一個 bug（PR #105） | patch |
| R9 | BH | POST 非隊員訊息寫「查看」；`_OPPONENT_PENDING_MESSAGE` 缺句號 | low：直接修正文字 | patch |
| R10 | BH、VG、ECH | `test_retire_concurrency.py` docstring 仍寫「報到只鎖場次」 | low：直接修正 | patch |
| R11 | BH | 契約漏列兩種 `TEAM_NOT_RETIRABLE` 訊息、`retire_registration` 回傳型別不一致 | low：直接修正文件 | patch |
| R12 | BH | 棄權期限已過、worker 尚未處理的空檔仍可退賽，遞補會重設棄權期限 | low：worker 每 15～30 秒輪詢，空檔極短；修正要加新的判斷分支 | 駁回 |
| R13 | BH | 併發測試沒有「兩隊同時退賽搶同一候補」 | low：兩者都先 `lock_tournament`，由同一把鎖序列化；R6 已補真實遞補測試 | 駁回 |
| R14 | BH | 通知少了退賽隊其他隊員、主辦方；對手不知道換人原因 | false：Decisions 第 6 項由人定案（退賽隊不另通知、對手沿用 `MatchOpponentsDecided`） | 駁回 |
| R15 | BH | `_opponent_retired` 逐人呼叫 `is_captain` | low：與既有 `_opponents_decided` 相同寫法，每隊最多 5～7 人 | 駁回 |
| R16 | BH | 6.5 遞補刪除報到沒有獨立紀錄 | low：與 B 既有 `_replace` 相同行為；`match.teams_changed` 已記換隊 | 駁回 |
| R17 | BH | `retirement.py` 用 `service._confirm`、與 `service.py` 互相 import | low：與 B 的 `disqualification.py` 相同既有模式，載入順序已由既有測試涵蓋 | 駁回 |
| R18 | BH | 前端失效範圍只含隊伍、我的隊伍、下一場、退賽狀態；單元測試未檢查隊伍查詢的失效 | low：S3／S13 本來就輪詢或進頁重抓；徽章更新另有 R8 的測試涵蓋 | 駁回 |
| R19 | BH | 未驗證 Email 的隊長 GET 拿 403、畫面不顯示 | false：建立／加入隊伍都要 `VerifiedAccount`，未驗證帳號不會是隊長 | 駁回 |
| R20 | BH | e2e 只走有候補一條路 | low：其他路徑由後端 API 與前端單元測試涵蓋；CI 不跑 e2e | 駁回 |
| R21 | BH | diff 不含 `docs/ai-usage/` 與 spec | false：spec 刻意不給這層；AI 使用紀錄在 commit 前新增 | 駁回 |

## Design Notes

- 操作紀錄沿用既有動作，不新增動作代碼：報名由 `mark_status` 自動寫 `registration.status_changed`（退賽、已參賽），場次寫 `match.teams_changed`（`after.retired_team_id`），沒有候補時 `confirm_walkover` 寫 `match.confirmed`。因此 `frontend/src/features/tournaments/audit-log.ts` 的 `AUDIT_ACTION_LABELS` 與 `backend/tests/tournaments/test_audit_action_labels.py` 不需改；若核准時要求 S34 有獨立的「退賽」動作，再新增 `match.team_retired` 並同步兩處。
- 為什麼先轉 `retired` 再取候補：截止後順位計算每校上限時把 `drawn` 算進去，退賽隊不先離開，同校候補會被誤判為 `SCHOOL_LIMIT_REACHED`。兩步在同一個鎖與交易內，外部看不到中間狀態。
- 為什麼不沿用 `backfill_vacancies`：它以「名額 − 正取數」算空位，抽籤後正取數可能本來就小於名額（截止補位後仍有空位），會一次遞補多隊；抽籤後必須一對一換位。
- 跨模組方向：competition → registration（AD-4、呼叫方向固定）；registration 不知道對戰表。S17 的「可不可以退賽」由 competition 的 `GET /teams/{id}/retirement` 提供，不加進 registration 的 `TeamDetail`。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠，`retirement.py` 分支覆蓋率 90% 以上
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- `docker compose exec -T backend alembic heads` -- 只有一個 head
- 前端 `bun run lint`、`bun run test:unit`-- 通過；`bun run test -- --grep @story-4.5` -- 通過
