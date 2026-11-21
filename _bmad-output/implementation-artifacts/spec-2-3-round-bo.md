---
title: 'Story 2.3：分輪設定 BO 數'
type: 'feature'
created: '2026-11-21'
status: 'done'
baseline_commit: '7b70c649b176cbac802977a1938ec77ab1d182b0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/tournaments.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 期中每一輪都用建立賽事時的 BO，主辦方無法讓前幾輪快速（BO1）、四強與決賽更慎重（BO3／BO5）；`bo_for_round` 一律回賽事 BO（FR-8）。

**Approach:** S26 建立賽事表單加可展開的「分輪 BO」，以「距決賽的輪數」（決賽＝0、4 強＝1、8 強＝2…）儲存在新資料表 `round_setting`；`bo_for_round` 依實際對戰表的總輪數換算後查設定，沒有設定的輪次回快照中的預設 BO，季軍賽沿用四強的設定。

## Boundaries & Constraints

**Always:**
- 分輪 BO 只接受 1、3、5、7；其他值、重複的輪次、超出名額可能輪數的輪次，都回 422 並指向 `round_bo`。
- 可設定的輪次依名額計算：名額 N 的總輪數＝⌈log₂N⌉，可設距決賽 0～總輪數−1。
- 實際正取隊數較少、輪數變少時，仍以距決賽的輪數對應（決賽與四強套用各自的設定）。
- 勝局門檻沿用 `scoring.wins_needed`（BO1 先 1、BO3 先 2、BO5 先 3、BO7 先 4）。
- 建立賽事的操作紀錄 `tournament.created` 要包含分輪 BO。
- 程式不依遊戲名稱或 id 分支（AD-12）。

**Never:**
- 不做賽事建立後修改分輪 BO（屬 2.5 的 S28）、不做公開頁 S2 的分輪 BO 顯示。
- 不在 tournaments 呼叫 competition（呼叫方向 competition → tournaments）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 設定四強與決賽 | 名額 16、預設 BO1、四強 BO3、決賽 BO5 | 第 1、2 輪 BO1，第 3 輪 BO3，第 4 輪（決賽）BO5，季軍賽 BO3 | N/A |
| 隊數變少 | 同上，實際 6 隊（3 輪） | 第 1 輪 BO1、第 2 輪 BO3、決賽 BO5、季軍賽 BO3 | N/A |
| 沒有設定 | `round_bo` 空 | 每一輪都是快照的 BO | N/A |
| 只設決賽 | 決賽 BO5 | 季軍賽用預設 BO（四強未設定） | N/A |
| 不合法的 BO | 決賽 BO2 | 不建立賽事 | 422，`round_bo` |
| 超出輪數 | 名額 8，設距決賽 3 | 不建立賽事 | 422，`round_bo` |
| 重複輪次 | 決賽設兩次 | 不建立賽事 | 422，`round_bo` |
| 輪次超出實際 | `bo_for_round` 的 `round_no` 不在 1～`rounds` | 拋 `ValueError`（程式錯誤） | N/A |

## Decisions

- **（使用者 2026-11-21）本 PR 一併修改 D 的 competition 呼叫點。** 季軍賽與決賽的 `round_no` 相同、`bo_for_round` 不知道實際總輪數，所以 `competition/service.py` 的 `_round_starts`、公開單場詳情、`_bo`、改時間的 `min_gap` 改為多傳 `rounds` 與 `is_third_place`；PR 說明列出並請 D 審查（前例：6.2 例外修改 D 的 `get_replay_window`）。
- **（使用者 2026-11-21）建立時每輪間隔的下限照 FR-7 用預設 BO。** 某一輪 BO 較大時，由抽籤排程（`plan_round_starts`）自動順延下一輪；S26 分輪 BO 區塊提示「BO 較大的輪次，下一輪會自動順延」。
- **（使用者 2026-11-21）spec 約 3,000 tokens，超過 1,600 仍不拆**：只有分輪 BO 一個目標，後端、前端與呼叫點分開都無法單獨上線。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/service.py:513` `bo_for_round` -- 改簽名為 `bo_for_round(session, *, tournament_id, round_no, rounds, is_third_place)`；`create_tournament:330-390` 驗證並寫入設定；`_tournament_to_read`、`get_tournament`、`lock_tournament`、`list_organizer_tournaments` 都要帶出 `round_bo`
- `backend/app/modules/tournaments/models.py:116,385,409` -- 新增 `RoundSetting` 表（PK `tournament_id`＋`rounds_from_final`，`bo`）、`RoundBo`（`rounds_from_final`、`bo`）；`TournamentCreate.round_bo: list[RoundBo] = []`、`TournamentRead.round_bo`；沿用 `BoField`
- `backend/app/modules/tournaments/repository.py` -- 新增讀寫 `round_setting`
- `backend/app/modules/competition/service.py:142,699,1520,1925` -- 四個呼叫點（`_bo` 被 1563、1584、1667、1700、1746 使用）；取總輪數用 `repository.get_bracket_by_tournament`；`_round_starts` 的 `best_of` 清單對季軍賽不需另算（同輪共用開始時間，決賽是最後一輪）
- `backend/app/modules/competition/bracket.py:92` `round_name` -- 輪次名稱（決賽、4 強、8 強）與前端標籤一致
- `backend/app/alembic/versions/` -- 新遷移，`down_revision = "c4f8a2e6d1b7"`（目前唯一 head；合併 1.6 後改接 `d1f3a5c7e9b2`）
- `frontend/src/features/tournaments/CreateTournamentForm.tsx:53,90,190,266,550-575` -- `ALLOWED_BO`、zod schema、`superRefine`、`toTournamentCreate`、BO 欄位；BO 說明「每一輪都用這個 BO 數。」要改
- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx` -- S27 總覽顯示分輪 BO
- `contracts/tournaments.md:108`、`contracts/competition.md:281` -- 更新 `bo_for_round` 說明
- 不改：`competition/schedule.py`（已支援依輪 BO）、`competition/scoring.py`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/{models,repository,service}.py`、`backend/app/alembic/versions/<rev>_story_2_3_round_setting.py` -- 資料表、建立時驗證與儲存、`TournamentRead.round_bo`、新 `bo_for_round`；換算抽成純函式方便單元測試
- [x] `backend/app/modules/competition/service.py` -- 依 Decisions 修改四個呼叫點（D 的模組，PR 說明列出）
- [x] `backend/tests/tournaments/test_round_bo.py` -- I/O Matrix 每列至少一個測試；`backend/tests/competition/` 加一個整合測試：四強 BO3 的賽事，四強場次需拿 2 局才能送出結果
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh`
- [x] `frontend/src/features/tournaments/{CreateTournamentForm,OrganizerTournamentOverview}.tsx` -- 「分輪 BO」區塊：預設收合，展開後依名額列出輪次（決賽在最上），每列選單「沿用預設（BO{n}）」或 BO1／3／5／7；送出時只送有設定的輪次；S27 列出有設定的輪次
- [x] `frontend/tests/unit/organizer-tournaments.test.tsx` -- 展開、依名額列輪次、送出 payload、422 寫回
- [x] `contracts/tournaments.md`、`contracts/competition.md` -- 更新函式說明

**Acceptance Criteria:**
- Given S26，when 主辦方展開「分輪 BO」把四強設 BO3、決賽設 BO5 並送出，then S27 顯示這兩輪的設定，其他輪次沿用預設 BO
- Given 有分輪設定且已抽籤的賽事，when 裁判在四強場次登錄比分，then 勝局門檻是 2 局
- Given 375 px 寬的手機，when 開啟 S26 展開分輪 BO，then 沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- `RoundBo` 的 BO 沒有直接用 `BoField`：前端 `applyFieldErrors` 以 loc 的最後一段對應欄位，巢狀錯誤的 loc 是 `["body","round_bo",0,"bo"]`，會被寫進預設 BO 欄位。改在 `round_bo` 清單的驗證器一起檢查 BO（1／3／5／7）、輪次 ≥ 0、不重複，loc 停在 `["body","round_bo"]`；超出名額輪數由 `service._validate_round_bo` 以 `FieldError` 指向同一欄位。
- 換算抽成純函式 `total_rounds`、`rounds_from_final`、`resolve_round_bo`（`tournaments/service.py`）；`bo_for_round` 先驗證 `round_no` 再查資料庫。
- competition 新增私有函式 `_bracket_rounds`（`get_bracket_by_tournament` 取總輪數）給 `_bo` 與 `_reschedule_window` 用；`_reschedule_window` 的 `min_gap` 改收 `Match`（要知道 `is_third_place`）。
- 前端表單值 `round_bo` 是字串陣列（索引＝距決賽的輪數，值為 `default` 或 BO 數）；送出時只送 `< totalRounds(名額)` 且有設定的輪次，`round_bo` 一律帶上（沒有設定時是空陣列）。伺服器 `round_bo` 錯誤會自動展開區塊。
- 既有前端測試的 `TournamentRead` 假資料（`draw-button`、`organizer-appeals`、`organizer-reports`）補上 `round_bo: []`。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-21）：Verification Gap 4 筆、Edge Case Hunter 4 筆、Blind Hunter 16 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Gap、Blind | 抽籤排程（`_round_starts`）沒有用分輪 BO 的測試：每輪改回 `tournament.bo` 或輪次對反，測試都不會失敗 | medium：使用者決定的「BO 較大的輪次下一輪自動順延」沒有測試守住 | patch（補測試：`scheduled_at`、`delayed_rounds`、`get_bracket`） |
| 2 | Gap、Blind | 改時間範圍（`_reschedule_window` 的 `min_gap`）沒有用分輪 BO 的測試 | medium：D 的模組裡改了邏輯卻沒有測試；所有輪 BO 相同時任何錯誤都測不出 | patch（補測試） |
| 3 | Gap | 季軍賽經 `_bo` 登錄比分沒有測試；`_bo` 改成永遠 `is_third_place=False` 也不會失敗 | medium：季軍賽會誤用決賽的勝局門檻 | patch（補測試：季軍賽 `wins_needed == 2`） |
| 4 | Gap | S27 每一輪都有設定時不顯示「其他輪次」的分支沒有測試 | low：只是顯示文字，但補一個測試就能守住 | patch（補測試） |
| 5 | Edge、Blind、Edge | 伺服器 `round_bo` 錯誤讓區塊展開後，改選單會清掉錯誤、區塊突然收起；有錯誤時按收合沒有反應（`expanded = open \|\| error`） | low：介面幾乎送不出會被伺服器拒絕的 `round_bo`，但修正是直接改展開狀態的來源 | patch（`expanded` 只看 `open`，有錯誤時設為展開） |
| 6 | Blind | 收合時 `aria-controls` 指向不存在的 id | low：直接改成一律渲染區塊、收合時加 `hidden` | patch |
| 7 | Blind | `round_bo` 的 `FormMessage` 沒有接到各個選單的 `aria-describedby`／`aria-invalid` | low：要改 shadcn `FormControl` 的結構；介面幾乎不會出現此錯誤 | 不處理 |
| 8 | Edge（2 筆同根因） | `round_bo` 項目型別錯誤（`bo` 是字串、`null`、缺欄位）時 loc 是巢狀的 `["body","round_bo",0,"bo"]`，前端會寫進預設 BO 欄位；與 contracts 的說法不符 | low：只有繞過介面直接呼叫 API 才會發生，改 schema 要放寬型別再手動轉換；contracts 改寫說明是直接修正 | patch（只改 contracts 說明：型別錯誤沿用欄位層級的 loc） |
| 9 | Blind | 錯誤訊息沒有指出是哪一輪 | low：介面已過濾超出的輪次，BO 只能從選單選，使用者遇不到 | 不處理 |
| 10 | Blind | 實際隊數較少時，S27 仍列出用不到的輪次設定；「其他輪次」依名額判斷 | false：S27 顯示主辦方的設定本身；依距決賽的輪數對應、用不到的輪次自然不套用，正是凍結區的規則 | 不處理 |
| 11 | Blind | `bo_for_round` 每次呼叫都查賽事與設定，`_bo` 另查對戰表 | low：每次請求只有數筆查詢；修正要重構 D 的呼叫點 | 不處理 |
| 12 | Blind | `round_setting` 沒有 CHECK（BO 值、輪次 ≥ 0） | low：只有繞過 service 的寫入會遇到；與 2.1、2.2 的判斷一致 | 不處理 |
| 13 | Blind | Never 清單的項目（2.5 修改、S2 顯示）沒有寫進 deferred-work | false：2.5 是 sprint-status 裡已排定的 Story；S2 顯示不在任何驗收條件裡 | 不處理 |
| 14 | Blind | spec 是 `in-review`、sprint-status 仍是 `in-progress` | false：sprint-status 由 bmad-build 的最後一步更新 | 不處理 |
| 15 | Blind | 沒有 AI 使用紀錄 | false：在 bmad-build 完成時新增 | 不處理 |
| 16 | Blind | 名額改小後，超出輪次的設定仍留在表單；名額改回時會再出現 | low：送出時已過濾（有測試）；保留使用者的選擇是合理行為 | 不處理 |
| 17 | Blind | `round-bo.ts` 沒有直接的單元測試；`totalRounds` 對名額 ≤ 1 回 0，後端則拋錯 | low：表單在名額 ≥ 2 時才呼叫，已由表單測試間接覆蓋 | 不處理 |
| 18 | Blind | 日程錯誤與分輪 BO 錯誤分兩次回傳 | low：與 2.2 審查第 9 點相同的取捨 | 不處理 |
| 19 | Blind | contracts 寫「存在 `round_setting` 表」，容易讀成「存在」 | low：直接改字 | patch（改為「存於」） |
| 20 | Blind | `test_bo_for_round_returns_tournament_bo_for_every_round` 對名額 16 的賽事傳 `rounds=7` | low：直接改成實際可能的輪數 | patch |

## Verification

**Commands:**
- `docker compose up -d --build --wait && bash scripts/test.sh` -- expected: 後端全部通過（含 `test_migrations.py`、`test_architecture.py`）
- `docker compose run --rm frontend bun run build`、`bun run typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過

**Manual checks:**
- 瀏覽器走一次 S26 建立含分輪 BO 的賽事 → S27，並在 375 px 檢查 S26。
