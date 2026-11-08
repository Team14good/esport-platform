---
title: 'Story 6.1：提出申訴'
type: 'feature'
created: '2026-11-08'
status: 'done'
baseline_commit: '5b5284627854391034a85651557659f04e38a580'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 隊長目前無法對申訴期內的場次結果提出申訴（FR-30）；disputes 模組只有列舉，沒有資料表、API 與畫面，6.2 處理申訴也因此無法開工。

**Approach:** 依 `contracts/disputes.md` 建立 `appeal` 資料表、`file_appeal`／`get_appeal_state`／`open_appeal_attachment` 與 API；competition 新增 `mark_appealed`（新增檔案＋`service.py` 只新增公開函式）；S4 申訴期區塊下方加「提出申訴」與 S21 `Dialog`（文字＋截圖），申訴中時區塊顯示「申訴處理中」。

## Boundaries & Constraints

**Always:**
- 資料表 `appeal` 照約定〈一〉欄位；`(match_id, team_id)` 唯一；一支 Alembic 遷移。說明 1～1000 字；附件最多一張，用 `core.storage.save_image`（JPG／PNG、5 MB）。
- `file_appeal` 依序：`lock_tournament` → `lock_match` → 場次屬於該賽事（否則 404 `MATCH_NOT_FOUND`）→ 登入者是兩隊之一的隊長（經 `registration_port.is_captain`，否則 403 `CAPTAIN_REQUIRED`）→ 狀態為 `appeal_window`／`appealed`（否則 409 `APPEAL_NOT_ALLOWED`）→ `now < appeal_deadline`（否則 409 `APPEAL_DEADLINE_PASSED`）→ 該隊未申訴過（否則 409 `APPEAL_ALREADY_FILED`；唯一鍵是最後防線）→ 建立申訴；場次仍是 `appeal_window` 時呼叫 `mark_appealed`。寫操作紀錄 `appeal.filed`、發 `AppealFiled{appeal_id, match_id, team_id}`。任何拒絕都不寫資料、紀錄、事件，也不留下已存的附件。
- 與 worker 期滿確認互斥：鎖順序與 `auto_confirm_expired` 相同（賽事 → 場次），鎖住後才判斷狀態與期限。
- `mark_appealed(session, *, match_id) -> MatchRead`：`appeal_window` → `appealed`；已是 `appealed` 不動；其他 409 `MATCH_INVALID_TRANSITION`；不改 `appeal_deadline`。寫在 competition 新增的檔案，`service.py` 只新增這個公開函式（CONTRIBUTING 6.6）。
- `get_appeal_state`：只回登入者本隊的狀態 `{can_file, already_filed, deadline, reason}`；不是兩隊隊長時 `can_file=false`、原因 `not_captain`；不透露另一隊是否申訴。
- `open_appeal_attachment`：只有該賽事主辦方能下載（AD-15）；6.1 只做 API，S32 的下載入口屬於 6.2。
- API 照約定：`GET …/matches/{mid}/appeal-state`（`CurrentAccount`）、`POST …/matches/{mid}/appeals`（`VerifiedAccount`，multipart，201 `AppealRead`）、`GET /organizer/appeals/{appeal_id}/attachment`（`Organizer`）。不加進 `PUBLIC_WRITE_ROUTES`。
- S4：申訴期區塊（`MatchAppealWindow`）下方滿版 outline「提出申訴」，只有兩隊隊長看得到；本隊已申訴時停用並寫「本隊已對此場次提出申訴」；期限已過時停用並寫「已截止」。點擊開 S21 `Dialog`：說明（必填）＋沿用 3.2 的 `ScreenshotUploader`；送出鈕「送出申訴」；成功 Toast、關閉並重抓 S4；失敗以 `notifyError` 顯示後端訊息。場次為「申訴中」時區塊另寫「申訴處理中」，倒數照常顯示（另一隊在期限內仍可申訴）。
- 申訴內容不出現在任何公開 API 或觀眾畫面。

**Never:**
- 不做 6.2（處理申訴、S32、結案）、6.3、檢舉；不改 competition 既有函式；不讓 disputes 直接讀寫 `match` 表；不做站內通知或 Email（期中只發事件）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一隊申訴 | 申訴期、期限內、A 隊隊長 | 201；場次轉申訴中；一筆紀錄、一個事件 | — |
| 第二隊申訴 | 申訴中、期限內、B 隊隊長 | 201；場次維持申訴中 | — |
| 重複申訴 | A 隊已申訴 | — | 409 `APPEAL_ALREADY_FILED`；S4 停用寫「本隊已對此場次提出申訴」 |
| 期限已過 | `appeal_deadline <= now` | — | 409 `APPEAL_DEADLINE_PASSED`；S4 停用寫「已截止」 |
| 狀態不對 | 待開打、進行中、已確認 | — | 409 `APPEAL_NOT_ALLOWED`；S4 不顯示按鈕 |
| 非隊長 | 裁判、主辦方、一般隊員、觀眾 | 看不到按鈕 | API 403 `CAPTAIN_REQUIRED`（未登入 401） |
| 與 worker 同時 | 期限剛過、worker 確認中 | 只有一方成功 | 鎖順序相同、鎖後重查 |
| 附件不合格 | 非 JPG／PNG 或超過 5 MB | — | 沿用 `core.storage` 的錯誤；不建立申訴 |
| 下載附件 | 該賽事主辦方／其他人 | 主辦方取得檔案 | 其他人 403 |

## Decisions

- 2026-11-08（使用者與 D 協議）：Epic 6 改照模組分工。competition 端 6.2 的 `uphold_result`、`correct_result`、`replay_match` 與 6.5 的 `disqualify` 由 D 實作；B 負責 6.1 全部（含 competition 的 `mark_appealed`），以及 6.2、6.5 的 disputes 端（`resolve_appeals`、`resolve_report`、S32、S33）。約定〈一〉分工表隨本 Story 更新。
- 2026-11-08（使用者）：S4 的「提出申訴」與「申訴處理中」由 B 在 6.1 一併做。新元件（`AppealPanel`、`AppealDialog`）放 `features/disputes/`；S4 屬於 A 的 5.8，只加掛載點（`MatchAppealWindow` 多一個插槽並在申訴中顯示「申訴處理中」，S4 路由傳入），不改其他既有行為；PR 說明列出動到的 A／D 檔案並請 A 審查（CONTRIBUTING 6.6）。

</frozen-after-approval>

## Code Map

- `backend/app/modules/disputes/{models,repository,service,router}.py` -- 目前只有 `AppealStatus`、`AppealDecision`、`ReportStatus` 列舉，其餘空殼；`router` 已由 `app/api/main.py` include，不用另外註冊。
- `backend/app/modules/competition/service.py` -- `lock_match`（約 626，先 `lock_tournament`）、`transition_match`（約 637，`APPEAL_WINDOW → APPEALED` 已允許）、`_match_in_tournament`（約 1105）、`auto_confirm_expired`（約 947，鎖順序與鎖後重查的範本）、`_evaluate_check_in`（約 1052，判斷登入者是哪一方隊長的寫法）。只新增 `mark_appealed`，實作放新檔 `competition/appeals.py`。
- `backend/app/modules/competition/registration_port.py:83` -- `is_captain`（缺函式回 503）。
- `backend/app/core/storage.py` -- `save_image`、`open_file`、`delete_file`；`registration/router.py:67-94` 是 multipart 上傳與失敗時刪檔的範本（3.2 沒有下載端點，下載要新做）。
- `backend/app/core/events.py` -- `Event`、`publish`；`core/audit.py:53` -- `record`。
- `backend/app/modules/identity/deps.py` -- `CurrentAccount`、`VerifiedAccount`、`Organizer`；`core/authz.py` -- `ensure_tournament_owner`。
- 前端：`features/competition/MatchAppealWindow.tsx`（申訴期區塊，`appealed` 也顯示）、`MatchSpectatorView.tsx`（aside 約 96）、`routes/tournaments/$tournamentId/matches/$matchId.tsx`（`MatchContent` 建立倒數與插槽）、`MatchCheckIn.tsx:103`（依 `matchVersion(detail)` 重抓的 query 寫法）、`features/registration/ScreenshotUploader.tsx`、`PlayerProfileDialog.tsx`（上傳範本）。`match-status.ts` 已有 `appealed → 申訴中`（脈動），不用改。
- 約定：`contracts/disputes.md` 〈一〉分工表改為「6.2、6.5 的 competition 函式由 D 新增」，〈四〉`unassign_referee_if_member` 列補「只對 scheduled／live 呼叫，其他狀態拋 `ValueError`；6.5 要在 `confirm_walkover`／`confirm_match` 之前呼叫」；`contracts/competition.md` 〈公開函式〉加 `mark_appealed`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/disputes/models.py` -- `Appeal` 表、`AppealRead`、`AppealState`、`AppealFiled` 事件 -- 約定〈一〉〈二〉
- [x] `backend/app/alembic/versions/` -- 新增 `appeal` 遷移（接在目前唯一的 head 後） -- 一個 Story 一支遷移
- [x] `backend/app/modules/competition/appeals.py`、`service.py` -- `mark_appealed` -- 6.1 的 competition 前置
- [x] `backend/app/modules/disputes/{repository,service,router}.py` -- `file_appeal`、`get_appeal_state`、`open_appeal_attachment` 與三個 API -- I/O 矩陣
- [x] `backend/tests/disputes/`、`backend/tests/competition/` -- I/O 矩陣每列、`mark_appealed`、不留痕跡、併發互斥
- [x] `scripts/generate-client.sh` -- 重新產生 client
- [x] `frontend/src/features/disputes/` -- `AppealPanel`、`AppealDialog`、queries；S4 只加掛載點（見 Decisions）
- [x] `frontend/tests/unit/` -- 按鈕顯示條件、三種停用文字、送出成功與失敗、申訴處理中
- [x] `contracts/disputes.md`、`contracts/competition.md`、`sprint-status.yaml` -- 見 Code Map

**Acceptance Criteria:**
- Given 申訴期的場次，when 兩隊之一的隊長在 S4 送出申訴，then 場次轉為申訴中、S4 顯示「申訴處理中」與「申訴中」徽章，該隊再看 S4 時按鈕停用並寫「本隊已對此場次提出申訴」。
- Given 申訴中的場次，when 觀眾呼叫公開單場 API，then 回應不含任何申訴內容。

## Implementation Notes

- 隊長判斷：disputes 直接呼叫 `registration.service.is_captain`（呼叫方向 disputes → registration 允許）。`registration_port` 是 competition 內部的轉接檔，跨模組只能 import `service`，所以沒有經它；registration 的 `is_captain` 已合併，不需要 503 的退路。
- `file_appeal` 在 `lock_tournament` 之前先做一次不鎖定的讀取，確認場次屬於網址上的賽事（404 `MATCH_NOT_FOUND`，與 competition 的場次 API 一致，賽事不存在也回這個碼，不必排隊等鎖）；鎖住後再取最新的場次判斷狀態與期限，互斥性不變。說明欄位（422）最先檢查。
- `file_appeal` 回傳 `FiledAppeal {appeal, attachment_key}` 而不是約定原本的 `AppealRead`：router 在 `session.commit()` 失敗時要刪掉剛存的附件（比照 3.2 `update_player_profile` 的 `ProfileUpdate`）。附件在全部檢查通過後才存；之後任何例外（含唯一鍵衝突）都在 service 內刪檔。`get_appeal_state` 多收 `tournament_id` 以檢查場次歸屬。兩者已更新到 `contracts/disputes.md`。
- `AppealRead` 只回 `has_attachment`，不回 `attachment_key`（AD-15）。說明以 code point 計算字數；去掉控制字元（保留換行與 tab）與雙向控制字元（U+202A–U+202E、U+2066–U+2069），其他格式字元（例如組合 emoji 的 U+200D）保留，再去頭尾空白。附件下載回應加 `X-Content-Type-Options: nosniff`。
- `AppealState.reason` 的順序與 API 相同（隊長 → 狀態 → 期限 → 已申訴）；`already_filed` 不論其他原因都照實回傳，S4 據此讓「本隊已對此場次提出申訴」優先於「已截止」。
- `appeal.filed` 的 `before` 為 `{match_status}`、`after` 含場次、隊伍、說明、`has_attachment` 與新的 `match_status`，記下第一筆申訴造成的場次狀態變更（`mark_appealed` 本身不寫紀錄）。
- `mark_appealed` 經 `transition_match` 更新 `updated_at`，S4 的 `matchVersion` 因此改變、申訴狀態會重抓。`service.mark_appealed` 以函式內 import 呼叫 `appeals.py`，避免循環 import。
- 附件下載以 `StreamingResponse` 分段讀出，結束後關閉檔案；加 `Cache-Control: private, no-store`。
- 前端：`MatchAppealWindow` 新增 `action` 插槽與「申訴處理中」，`MatchSpectatorView` 新增 `appealAction` 轉傳，S4 路由傳入 `AppealPanel`；其他既有行為未改。對話框送出失敗時保留內容並重抓 S4（例如已截止時按鈕狀態跟上）。未驗證 Email 的隊長按下送出時由後端回 403 `EMAIL_NOT_VERIFIED`，以錯誤 Toast 顯示（沒有包 `VerificationRequired`，它需要 router context）。
- 併發測試（`tests/disputes/test_appeal_concurrency.py`）用兩條真實連線：一方持鎖未提交時，另一方必須等鎖並在鎖後放棄。把 `file_appeal` 的兩個鎖拿掉時，第一個測試會失敗（已實測：申訴在場次確認後仍進到 `mark_appealed`）。測試結束時刪除申訴、場次、對戰表與相關事件。
- 併發測試提交的 `appeal.filed` 操作紀錄只增不改、刪不掉，第一次跑全套時讓 `test_file_appeal.py` 的計數多 1 而失敗（單獨跑該檔不會發生）；計數改為只算該場次／賽事後全套通過。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap 三位並行；中途因用量上限中斷後續跑；無高嚴重度）：

| # | 來源 | 發現 | 判定與證據 | 處理 |
|---|------|------|-----------|------|
| 1 | Verification Gap＋Blind | router 在 commit 失敗時刪附件沒有測試 | low：拿掉 try/except 現有測試都會過 | patch：補測試 |
| 2 | Blind | 存檔不見時的 404 `FILE_NOT_FOUND` 沒有測試 | low：約定寫了、測試沒有 | patch：補測試 |
| 3 | Blind＋Verification Gap＋Edge | `_clean_description` 去掉所有 Cc／Cf：丟掉 tab、拆散 ZWJ 表情，且完全沒有測試；前端只 trim，兩邊不一致 | medium：申訴是證據，存下的文字與隊長輸入不同且無提示 | patch：只去 Cc（保留 `\n`、`\t`）與 bidi 控制字元，補測試 |
| 4 | Verification Gap | S4 路由是否真的掛上申訴入口沒有測試 | low：拿掉插槽轉傳所有測試仍過 | patch：補路由層測試 |
| 5 | Blind＋Edge | 第一隊送出後版本改變，`placeholderData` 讓舊的可按按鈕閃回 | low：按下只會得到 409 | patch：placeholder 期間不顯示可按的入口 |
| 6 | Blind | 附件下載沒有 `X-Content-Type-Options: nosniff` | low：使用者上傳的檔案 | patch：加 header |
| 7 | Blind | `disputes.md`〈三〉的新檔與不改既有函式規則與 D 負責四個函式矛盾；`competition.md` 刪除線加新規則讀起來像兩條規則 | low：之後 D 照約定會誤讀 | patch：寫清楚只適用 `mark_appealed` |
| 8 | Blind | `sprint-status.yaml` 的 6.2、6.5 仍只寫負責 B | low | patch：註解改為 B（disputes 端）、D（competition 端） |
| 9 | Edge | 賽事已取消時仍可對申訴期場次申訴 | maybe-false（medium）：期中 2.6 擱置、已結束時所有場次已確認，目前走不到 | defer：`deferred-work.md` |
| 10 | Blind | 第二隊送出後沒有重抓觸發 | false：S4 的 `refresh` 會 invalidate `matchQueryKey` 前綴，申訴狀態的 key 也以它開頭 | 不處理 |
| 11 | Edge | 期限在用戶端到了但版本沒變，按鈕仍可按 | false：申訴期倒數的 `onExpire` 會呼叫 `refresh`，申訴狀態隨之重抓成「已截止」 | 不處理 |
| 12 | Blind | 產生的 API 型別只列 422 | false：全專案慣例，業務錯誤統一由 `parseApiError` 處理 | 不處理 |
| 13 | Blind | `AppealFiled` 沒有 `tournament_id` | low：約定定義的 payload，通知（1.6）擱置 | 不處理 |
| 14 | Blind | `file_appeal` 與 `mark_appealed` 鎖了兩次場次 | low：PostgreSQL 重入無害，約定寫明函式內再 `lock_match` | 不處理 |
| 15 | Blind | `test_mark_appealed` 沒列舉所有狀態、沒有一方待定的案例、確認後測試多斷言賽事結束 | low：轉換表由 `transition_match` 統一擋 | 不處理 |
| 16 | Blind | 伺服器 422 沒有寫回表單欄位 | low：只在說明全是控制字元時發生，第 3 點後更少 | 不處理 |
| 17 | Edge | `can_file=false`、`reason=null` 時按鈕無聲隱藏 | false：後端 `can_file` 由 `reason is None` 推得，不會出現 | 不處理 |
| 18 | Edge | Tasks 寫「三種停用文字」，實際兩種 | low：修法是改 spec 文字 | 不處理 |
| 19 | Blind | diff 少了 spec 與 AI 使用紀錄 | false：spec 依流程只給 Edge Case Hunter，紀錄在流程結束時寫 | 不處理 |

## Verification

**Commands:**
- `bash scripts/test.sh` -- 後端全過（含 `test_migrations.py`、`test_architecture.py`）
- `bash scripts/lint.sh` -- 通過
- `cd frontend && bunx biome check src tests && bun run typecheck && bun run test:unit` -- 容器內全過（掛上 `vitest.config.ts`，見 CLAUDE.md〈環境上的坑〉）

**Manual checks (if no CLI):**
- 以示範隊長在申訴期場次的 S4 送出申訴（含截圖）；375 px 寬沒有橫向捲軸。
