---
title: 'Story 6.3：申訴逾期提醒與受影響場次暫停'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'beb855f'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 主辦方沒處理申訴時沒有任何提醒；等待申訴結果的下一場雖然後端已暫停報到與棄權計時（5.1、5.2、5.5），但 S4 看不出是「暫停」，S27、S32 也沒有處理期限的倒數（FR-31、FR-24、FR-25）。

**Approach:** disputes 新增 worker 工作，對快到處理期限、尚未提醒的申訴發出 `AppealReminded` 事件並在同一交易寫入 `Appeal.reminded_at`；notifications 登錄收件規則（主辦方）。前端加上 S4 的暫停提示、S27 與 S32 的處理期限倒數。

## Boundaries & Constraints

**Always:**
- 處理期限沿用 `disputes/service.py` 的 `_handling_deadline`：有下一場（含季軍賽）時為最早那場的預定開始時間；決賽、季軍賽為申訴提出後 1 小時。
- 提醒時間：有下一場時為處理期限前 1 小時；決賽、季軍賽為處理期限（提出後 1 小時）。已過提醒時間才提出的申訴，下一輪 worker 立即提醒。
- worker 工作一次處理一筆、不 commit；只挑未結案、`reminded_at` 為空的申訴；先鎖賽事、在鎖內重新檢查（仍未結案、仍未提醒、賽事不是已結束或已取消），事件與 `reminded_at` 同一交易；同一筆申訴只提醒一次（AD-8）。
- `AppealReminded` 只帶實體 id（`appeal_id`、`match_id`、`tournament_id`）；收件人是該賽事主辦方，連結到 S32（照 `_appeal_filed` 的規則寫法）。
- 倒數：處理期限剩餘超過 1 小時為 `muted`，最後 1 小時為 `destructive`；過了處理期限顯示「已超過處理期限」（`destructive`），不顯示「系統處理中」也不重抓。
- S4：場次在等申訴結果時，頁頂 Page banner「前一場申訴處理中，報到與棄權計時暫停」、Check-in panel 停用、倒數位置顯示「計時暫停」、狀態徽章「棄權計時暫停」；申訴處理完成後（伺服器資料更新）提示消失、倒數依新的棄權期限。同一輪其他場次不顯示。
- 介面文字繁體中文；跨模組只呼叫對方 `service.py` 公開函式；不直接呼叫 notifications（只發事件）。

**Never:**
- 不改報到、判棄權、晉級與棄權期限的既有後端行為（5.1、5.2、5.5 已涵蓋，只補測試確認）。
- 不新增資料表或欄位（`reminded_at` 已存在）。
- 不做重新比賽（rematch）場次的暫停提示（重賽是同一場重新計時，不是等前一場）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 下一場 1 小時內開始 | 準決賽申訴中，決賽 14:00，現在 13:00 | 提醒一次：outbox 一筆 `AppealReminded`、`reminded_at`＝現在 | N/A |
| 還沒到提醒時間 | 同上，現在 12:59 | 不提醒 | N/A |
| 決賽申訴 | 決賽申訴 10:00 提出，現在 11:00 | 提醒一次 | N/A |
| 已提醒過 | `reminded_at` 已有值 | 不再提醒 | N/A |
| 已結案 | 申訴已處理 | 不提醒 | N/A |
| 賽事已取消／已結束 | 未結案申訴、已到提醒時間 | 略過，不寫 `reminded_at` | N/A |
| 同場兩筆申訴 | 兩隊各提一筆 | 各提醒一次 | N/A |
| 等待申訴的下一場 | 準決賽申訴中，到了決賽與季軍賽的報到開放時間 | 不開放報到（`MATCH_TEAMS_PENDING`）、`forfeit_deadline` 為空、不判棄權；同輪其他場照常 | 409 `MATCH_TEAMS_PENDING` |
| 申訴處理完成 | 處理時間晚於下一場預定開始 | 棄權期限＝處理時間＋棄權時限，已過報到開放時間立即可報到 | N/A |
| S4 暫停提示 | 公開單場 API 標示在等申訴 | banner、Check-in panel 停用、「計時暫停」、徽章「棄權計時暫停」 | N/A |

## Decisions

- **（使用者 2026-11-24）在 `PublicMatchDetail` 新增 `awaiting_appeal: bool`**，由 competition 依「空著的一方，其來源場次狀態為申訴中」計算；要改 D 的 `get_public_match`，PR 說明列出、請 D 審查（前例：2.3）。
- **（使用者 2026-11-24）spec 約 3,500 tokens，超過 1,600 仍不拆**：提醒與暫停提示是同一個使用者目標（避免因申訴未處理而被誤判棄權）。
- **（使用者 2026-11-24）提醒通知文字**：標題「申訴待處理」，內文「「賽事」場次 X 的申訴已接近或超過處理期限，請盡快處理。」決賽、季軍賽在處理期限當下才提醒，不能寫「快到期限」。

</frozen-after-approval>

## Code Map

- `backend/app/modules/disputes/models.py:65-102` `Appeal`（`reminded_at` 已存在，遷移 `a9d4f2c6e8b1` 已建欄位）、`:146-158` 既有事件、`:226` `AppealGroup`（S32，新增 `deadline`）、`:272` `OpenDisputeItem`（已有 `deadline`）
- `backend/app/modules/disputes/service.py:805-823` `_handling_deadline`、`:337` `_FINAL_HANDLING_TIME`、`:503` `file_appeal`（鎖順序：賽事 → 場次）、`:744` `list_tournament_appeals`、`:861` `count_open_disputes`；新增 worker 用的 `remind_due_appeal(session) -> bool`
- `backend/app/modules/disputes/repository.py` -- 新增「未結案且 `reminded_at` 為空」的查詢
- `backend/app/worker/jobs.py:81-91` `JOBS` -- 新工作排在 `confirm_expired_appeals` 之後、`dispatch_outbox` 之前；`backend/tests/worker/test_email_pipeline.py` 的工作順序清單一起更新
- 範本：`competition/service.py:1119-1176` `auto_confirm_expired`（找候選、排除已結束與已取消、鎖、重新檢查）
- `backend/app/modules/notifications/rules.py:327` `_appeal_filed`（範本）、`:404-405` 登錄 -- 新增 `AppealReminded` 規則（A 的模組，只新增）；同名事件類別可在 rules.py 重新宣告（`:54` 的寫法）
- 暫停的既有後端行為（不改，補測試確認）：`competition/checkin.py:32` `teams_pending`、`forfeit.py:35-75`、`service.py:824` `start_forfeit_clock`、`schedule.py:119` `forfeit_deadline`；季軍賽已有 `tests/competition/test_appeal_resolution.py:311`
- `competition/models.py:489` `PublicMatchDetail`、`service.py:~710` `get_public_match` -- 新增 `awaiting_appeal`（依 Decisions）
- 前端：`frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx:80-87`（S4 `PageBannerSlot`）、`features/competition/CheckInPanel.tsx`（`teams_pending` 已停用）、`MatchCheckIn.tsx:42` `checkInCountdownPhase`（新增暫停）、`match-status.ts:23` `MATCH_STATUS_BADGES`、`features/disputes/OpenDisputesPanel.tsx:65-69`（S27 靜態期限改倒數）、`AppealsPage.tsx`（S32 加倒數）、`components/common/Countdown.tsx`（`variant` 可傳函式、`expiredText`）
- 測試範本：`backend/tests/disputes/test_resolve_appeals.py`（期限 `:1063`、`:1083`）、`backend/tests/worker/test_confirm_expired_appeals.py`、`backend/tests/notifications/test_rules.py`、`backend/tests/competition/test_check_in.py:237`；前端 `match-route.test.tsx`、`match-check-in.test.tsx`、`organizer-appeals.test.tsx`、`organizer-tournaments.test.tsx`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/disputes/{models,repository,service}.py` -- `AppealReminded` 事件、`remind_due_appeal`、`AppealGroup.deadline`
- [x] `backend/app/worker/jobs.py`、`backend/tests/worker/test_email_pipeline.py` -- 新工作 `remind_due_appeals`
- [x] `backend/app/modules/notifications/rules.py` -- `AppealReminded` 收件規則（主辦方、連結 S32）
- [x] `backend/app/modules/competition/{models,service}.py` -- `PublicMatchDetail.awaiting_appeal`（D 的模組，PR 說明列出）
- [x] `backend/tests/disputes/test_appeal_reminder.py`、`backend/tests/worker/test_remind_due_appeals.py`、`backend/tests/notifications/test_rules.py` -- I/O Matrix 提醒相關各列
- [x] `backend/tests/competition/` -- I/O Matrix「等待申訴的下一場」「申訴處理完成」各一個測試（確認既有行為；已有的測試涵蓋時引用即可）
- [x] `frontend/src/client/` -- `bash scripts/generate-client.sh`
- [x] `frontend/src/...` -- S4 暫停提示（banner、徽章、「計時暫停」）、S27 與 S32 處理期限倒數
- [x] `frontend/tests/unit/` -- S4 暫停與恢復、S27／S32 倒數變體（超過 1 小時、最後 1 小時、已超過處理期限）
- [x] `contracts/disputes.md`（若有）與 `contracts/competition.md` -- 新事件、新欄位

**Acceptance Criteria:**
- Given 準決賽申訴中且決賽 1 小時內開始，when worker 輪詢兩次，then 主辦方只收到一則提醒（站內與 Email）
- Given 決賽在等準決賽申訴，when 開啟決賽的 S4，then 看到暫停提示；申訴處理完成並重新整理後提示消失、顯示棄權期限倒數
- Given 375 px 寬的手機，when 開啟 S4 暫停狀態、S32，then 沒有橫向捲軸
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- 動到其他組員的模組（PR 說明列出）：notifications `rules.py` 新增 `_appeal_reminded` 與登錄（A）；competition `PublicMatchDetail.awaiting_appeal`、新增私有 `_awaiting_appeal`、`get_public_match` 多帶一個欄位（D）；`tests/competition/test_match_api.py` 的 `DETAIL_KEYS` 加新欄位（D）；共用元件 `Countdown.tsx` 新增選填 `expiredVariant` 與 `PausedCountdown`。
- 賽事已取消時 `awaiting_appeal` 一律為 false（AI 決定，取消橫幅優先）。
- 處理期限略過已取消（VOIDED）的下一場，S27 的期限也跟著改（審查修正）。
- AI 寫的介面文字：S4 暫停倒數的說明「報到與棄權倒數」、S32 倒數的說明「剩餘時間」。
- 驗證（2026-11-23，單獨執行）：後端 2843 passed、覆蓋率 97%；lint、typecheck、biome、build 通過；前端 81 檔 1222 tests 通過（第一次全套有 2 個既有 `match-route` 測試在冷啟動時 5 秒逾時，單獨與重跑全套都通過）。
- 手動檢查（2026-11-23）：開發資料庫造一筆 M1 申訴、M17 在 30 分鐘後。worker 寫入 `reminded_at` 並送出站內通知「申訴待處理」；S4 顯示 banner、徽章、「計時暫停」、報到停用；S27、S32 最後 1 小時紅色倒數，改成 3 小時後為灰色；375 px 的 S4、S32 沒有橫向捲軸；1280 px 的 S32 表格放得下（800 px 時表格內出現橫向捲軸）。檢查後資料已還原。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap）：
- intent_gap：提醒通知寫「快到處理期限」，但決賽、季軍賽在期限當下才提醒 → 使用者決定改文字（見 Decisions）。
- patch：鎖後重新讀場次實際讀到 identity map 的舊物件（`get_match` 是 `session.get`），改期後仍照舊時間提醒；處理期限把已取消（VOIDED）的季軍賽算進去；補測試：鎖內各分支與不 commit、`awaiting_appeal` 負向情境、S32 決賽期限、季軍賽 59 分邊界、`expiredVariant` 不呼叫 `onExpire`、S4 同頁暫停到恢復、隊長登入時報到停用、S27 測試改用固定時間。
- defer：派送時沒有再確認申訴仍未結案（A 的模組）；已取消／已結束賽事的未結案申訴每輪都被掃描；決賽兩筆申訴時 S27 與 S32 期限不同。
- reject：重新比賽場次沒有暫停提示（Never 已排除）；改期延後後不再提醒、同場兩筆各提醒一次（Always 已寫明）；決賽另一邊來源未定時仍顯示暫停（文字沒有錯）。

## Design Notes

AI 依現有程式決定：
- 通知規則登錄在 notifications（A 的模組，只新增）：`rules.py` 註解列出由各 Story 自己登錄的事件；沒有規則時事件會被消耗掉（2.6 審查確認），所以 6.3 必須自己登錄才有提醒。PR 說明列出。
- 「已超過處理期限」：Countdown 預設的過期文字是「已截止 · 系統處理中」並會重抓，但申訴期限到了系統不會自動處理，所以改用自訂文字、不重抓。

## Verification

**Commands:**
- `docker compose up -d --build --wait && docker compose exec backend bash scripts/test.sh` -- expected: 後端全部通過
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過
- 前端 `bun run build`、`bun run typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過

**Manual checks:**
- 瀏覽器開啟等待申訴的決賽 S4、S27 待處理清單、S32；375 px 檢查 S4 與 S32。
