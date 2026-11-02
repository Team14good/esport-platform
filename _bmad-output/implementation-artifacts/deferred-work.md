# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-official-template-project-skeleton.md`
  summary: 首頁「後端狀態：正常」沒有自動化的端對端測試，`bun run test` 因為沒有任何 Playwright 規格而回報「No tests found」並以非零代碼結束。
  evidence: `frontend/tests/` 只有 `.gitkeep`；Story 1.1 的 Never 移除了 playwright 服務，目前沒有可執行的 e2e 環境。等 e2e 環境建立後（最晚 Story 7.2），新增 `frontend/tests/home.spec.ts`，以 `PLAYWRIGHT_BASE_URL` 對 compose 執行，斷言 `role="status"` 顯示「後端狀態：正常」。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-official-template-project-skeleton.md`
  summary: worker 可能在 job 失敗後的 rollback 或 session close 拋錯時結束程序，而 compose 沒有替它設定 restart 政策（未證實；若成立為 medium）。
  evidence: `Worker.run_forever` 外層沒有例外保護，`compose.yml` 的 worker 沒有 `restart`。要確認是否成立：在 worker 執行工作時重啟 db 容器，觀察 `session.rollback()`／close 是否拋錯、worker 是否結束。若成立，補上 `restart: unless-stopped` 並在 `run_once` 保護 rollback；Story 1.3 加入第一個 outbox 工作時一併處理。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-flow-frontend-shell-and-theme.md`
  summary: DESIGN.md 的部分色票對比不足：淺色 primary #0891B2 搭配白字約 3.7:1，未達 WCAG AA 一般文字 4.5:1；深色 `status-eliminated` #4B5370 在背景 #070A14 上約 2.6:1，連非文字元素的 3:1 都不到。
  evidence: Story 1.2 照 DESIGN.md frontmatter 原樣寫入 `frontend/src/index.css`，數值與設計稿一致，所以問題出在設計稿本身。需要由 UX（bmad-ux）調整色票，例如加深淺色 primary，或讓 primary 按鈕在淺色時改用深色字，再同步更新 `index.css`。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-email-signup-and-verification.md`
  summary: worker 的事件分派與寄信遇到「每次都失敗」的項目時（不是 payload 格式錯誤，而是持續性的資料庫錯誤或外鍵錯誤），同一筆會一直排在最前面，擋住後面所有事件或信件（未證實；若成立為 medium）。
  evidence: `dispatch_outbox` 與 `send_next_email` 每次都取最舊的一筆，失敗時交易回滾、項目不變；`outbox_event` 沒有 attempts 或 dead-letter 欄位，`_compose` 的資料庫錯誤也可能讓 `attempts` 無法寫入。Story 1.3 的事件只有 `VerificationEmailRequested`，payload 一定合法、帳號不可刪除，所以沒能證明實際會發生。要確認是否成立：用 Story 1.6 的新事件類型，或刻意製造持續性的資料庫錯誤來觀察。若成立，在 1.6 建立事件類型登錄機制時，加上分派次數上限與 dead-letter 標記。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-official-template-project-skeleton.md`
  summary: `audit_log` 的「只增不改」只靠資料庫 trigger；應用程式、worker、alembic 都以資料表擁有者（預設 postgres 超級使用者）連線，可以停用或刪除 trigger，AD-9 沒有真正的強制力。
  evidence: 2026-10-24 Story 1.1 Code Review（Blind Hunter）。要強制，需另建非擁有者的應用程式角色，對 `audit_log` 只給 INSERT／SELECT，並撤銷 UPDATE／DELETE／TRUNCATE；遷移仍以擁有者身分執行。牽涉 compose、`.env` 與連線設定，適合在部署或安全強化時一併處理。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-login-logout-account-identity-switcher.md`
  summary: `POST /api/v1/access-tokens` 沒有頻率限制或連續失敗鎖定；每次請求都會跑一次 argon2，可被用來暴力猜密碼或耗用 CPU（規劃文件沒有相關規則，嚴重度未證實；若部署到公開網路，為 medium）。
  evidence: 2026-10-27 Story 1.4 Code Review（Blind Hunter）。Story 1.4 調查時確認 PRD、架構、epics 都沒有鎖定或頻率限制的規則。要處理時，先由 PM／架構決定規則（例如同一 Email 或 IP 每分鐘上限），再在登入端點實作，並決定是否要以 429 回應。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-apply-to-be-organizer.md`
  summary: S1 的 Page banner「想辦賽事？申請成為主辦方」（→ S15）延後；目前進入 S15 只有身分切換器的「申請成為主辦方」。
  evidence: Story 1.7 Decisions：S1 目前仍是佔位頁（賽事列表在 Epic 2），banner 沒有地方放。做 S1 賽事列表時（Epic 2）在頂欄下方、內容區最上方加上 Page banner，對已登入的非主辦方帳號顯示，連到 `/organizer/apply`；樣式見 DESIGN.md〈頁頂橫幅〉。

## Deferred from: code review of spec-1-4-login-logout-account-identity-switcher.md (2026-10-28)

- 正式啟動程式 `frontend/src/main.tsx` 呼叫 `createQueryClient()` 與 `configureApiClient(...)`（接上 Bearer 標頭與 401 攔截器）沒有任何測試；刪掉這行，所有單元測試照樣通過，但正式環境的已登入請求會不帶 token、401 也不會導向 S6。要等第一個 Playwright e2e 規格（登入後開 `/account`）才能涵蓋；`configureApiClient` 本身已有單元測試。

## Deferred from: code review of spec-1-5-forgot-reset-password.md (2026-10-28)

- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: 同一個重設連結同時送出兩次（兩個分頁、連點）時只能成功一次的保護（`reset_password` 先鎖帳號再鎖 token 重查、`get_token_by_hash` 的 `populate_existing`）沒有並行測試；拿掉任一環，現有測試都照樣通過（未證實會出錯；若退步，為 medium：一次性連結可被用兩次、`credentials_version` 加 2）。
  evidence: 2026-10-28 Story 1.5 Code Review（Verification Gap、Blind Hunter）。測試的 `client` 與 `session` fixture 共用同一條連線與外層交易，兩個交易不可能互搶 `FOR UPDATE` 鎖。要補需要另一套測試架構：自行建立並提交資料、兩條連線、兩個執行緒以 barrier 同時送出，斷言恰好一個 204、一個 `RESET_LINK_INVALID`、版本只加 1。`verify_email` 的鎖定重查也一併適用。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: `POST /api/v1/password-reset-emails` 沒有頻率限制：可以對同一個 Email 大量寄信灌爆收件匣，而且每次申請都會作廢對方手上的重設連結，讓本人無法完成重設。
  evidence: 2026-10-28 Story 1.5 Code Review（Edge Case Hunter）。Story 1.5 的 Never 明定不做頻率限制（與登入相同）。處理時與登入的頻率限制一起由 PM／架構決定規則（例如同一 Email 每小時上限、同一 IP 上限），並決定超過時是否仍回相同的 202 以免透露帳號是否存在。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: 「重設信只寄 Email、不建立站內通知」目前沒有任何斷言（1.5 第一輪審查移除了 `"notification" not in metadata.tables`）；Story 1.6 加入站內通知後，若 `dispatch_event` 誤替 `PasswordResetRequested`（或 `VerificationEmailRequested`）建立站內通知，現有測試照樣通過。
  evidence: 2026-10-28 Story 1.5 第二輪 Code Review（Blind Hunter、Acceptance Auditor）。目前還沒有 notification 表，無從斷言。Story 1.6 建立站內通知時，在 `tests/notifications/test_email_delivery.py` 的重設信與驗證信測試補上「站內通知筆數不變」的斷言。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-5-forgot-reset-password.md`
  summary: `tests/test_migrations.py` 只開 `compare_type`，沒有比對 server default；遷移檔與模型的 `server_default` 不一致（例如 `account.credentials_version` 的 `"0"` 被刪掉或改值）時測試照樣通過。測試資料庫每次從空表升級，也測不到「既有帳號升級後拿到 0」（低；若遷移檔被改錯，為 medium：有資料的資料庫升級失敗，或舊登入全部失效）。
  evidence: 2026-10-28 Story 1.5 第二輪 Code Review（Verification Gap）。比對設定自 Story 1.1 起就是如此，不是本 Story 造成。處理時在 `MigrationContext.configure` 加 `"compare_server_default": True`，先跑一次確認其他既有欄位沒有誤報；要完整守住資料升級，另寫一支「升到上一版、插入帳號、再升到 head」的測試。

## Deferred from: spec-5-2-forfeit-rules.md (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-forfeit-rules.md`
  summary: Story 5.2 第二階段尚未實作：第一階段只有 `competition/forfeit.py` 的純函式（`judge_forfeit`、`appeal_deadline`），還沒有 worker 工作、資料寫入、事件與畫面，所以逾時後實際上不會判棄權。
  evidence: 依賴 D 的 4.1（Match 資料表、`lock_match`、`transition_match`）與 5.1（`list_forfeit_due`、`list_check_ins`），兩者尚未合併。合併後在 competition 新增檔案完成以下範圍（不修改 D 的 `service.py` 既有函式）：
    - worker 工作：用 `list_forfeit_due` 選場次，`lock_match` 後以 `list_check_ins` 與賽事狀態重新呼叫 `judge_forfeit`；有結果時寫入 outcome、勝隊、wins 與 `appeal_deadline(decided_at=現在, appeal_minutes=賽事申訴時限)`，`submitted_by` 留空，再用 `transition_match` 轉為申訴期。重複執行沒有副作用。
    - 操作紀錄以 `app.core.audit.record()` 記 actor 為 system；發出判棄權事件（期中只發不通知）。
    - S4 顯示哪一隊棄權（雙方棄權時兩隊都標示）與申訴期倒數。
    - 確認 D 的場次狀態轉換表允許「待開打 → 申訴期」；若不允許，請 D 在轉換表新增，不由 5.2 修改。

## Deferred from: spec-5-2-forfeit-job.md (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-forfeit-job.md`
  summary: 逾時判棄權的 worker 工作（`competition/forfeit_job.py` 的 `make_forfeit_job`）已依約定介面寫好並以假的 `ForfeitPorts` 測過，但還沒接上真的 D、B 函式，也沒有加進 `app/worker/jobs.py` 的 `JOBS`，所以 worker 目前實際上不會判棄權。
  evidence: D 的 4.1、5.1（Match 資料表、`get_match`、`lock_match`、`transition_match`、`list_forfeit_due`、`list_check_ins`）與 B 的 `lock_tournament` 尚未合併。合併後：
    - 在 competition 新增轉接層檔案，實作 `ForfeitPorts`：`list_forfeit_due` → `service.list_forfeit_due(now=)`；`get_tournament_id` → `service.get_match(match_id=).tournament_id`；`lock_tournament` → tournaments `service.lock_tournament(tournament_id=)`，轉成 `TournamentForfeitInfo(cancelled=狀態是否為已取消, appeal_minutes=)`；`lock_match` → `service.lock_match(match_id=)`，直接回傳 Match 資料列；`list_checked_in_team_ids` → `service.list_check_ins(match_id=)` 的 `team_id`；`transition_to_appeal_window` → `service.transition_match(match=, to=MatchStatus.APPEAL_WINDOW)`。
    - 把 `make_forfeit_job(轉接層)` 加進 `JOBS`，並補一個用真資料表跑 `run_once` 的整合測試。
    - 確認 D 的轉換表允許「待開打 → 申訴期」；若不允許，請 D 新增，不由 5.2 修改。
    - 請 D 評估 `list_forfeit_due` 是否排除「兩隊都已報到」的場次：目前的約定只排除非待開打，兩隊都報到但還沒登錄第一局的場次，每輪都會被重新鎖住再略過；這段期間它們的賽事列與場次列的鎖會留到該交易結束。
## Deferred from: Story 5.8 第一階段（2026-10-30）

- source_spec: `_bmad-output/implementation-artifacts/spec-5-8-match-page-results.md`
  summary: S4 場次頁目前只在開發模式以假資料顯示，正式 build 一律 404；要換成真資料，需要公開的單場 API 與以下四件事。
  evidence: Story 5.8 Decisions（使用者 2026-10-30 定案）：相依的 D 5.1、5.5 與公開單場 API 尚未合併，所以 `features/competition/match-source.ts` 的 `fetchMatchDetail` 只在 `import.meta.env.DEV` 時回傳由對戰樹假資料推導的場次。換成真資料的範圍：
  (1) 請 D 在 `contracts/competition.md` 補上公開的單場 API（例如 `GET /api/v1/tournaments/{tournament_id}/matches/{match_id}`，公開、找不到回 404），回傳形狀見 `frontend/src/features/competition/match-types.ts` 的 `PublicMatchDetail`（`PublicMatch`＋賽事 id／名稱、遊戲名、本輪 BO、比分型態、輪次名稱、已登錄的局、同輪其他場次、`updated_at`）；
  (2) 後端測試確認段位截圖不出現在任何公開 API（AD-19）；
  (3) 把 `fetchMatchDetail` 換成呼叫產生的 client（404 時拋 `MatchNotFoundError`），刪除 `match-types.ts`、`routes/dev/match.tsx`，`match-fixtures.ts` 只留給測試；S4 路由的 loader 為了頁面標題會多抓一次，接上後可改為共用 TanStack Query 快取；
  (4) S3 路由（4.6 第二階段）完成後，`MatchHeader` 的返回連結（目前是一般的 `<a href="/tournaments/{id}/bracket">`）改為 TanStack `Link` 就能用。

## Deferred from: Story 5.2（S4 申訴期區塊，2026-10-30）

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-appeal-window-display.md`
  summary: S4 的申訴期區塊目前只顯示「{絕對時間} 截止」，倒數插槽是空的；公開單場 API 與 B 的 Countdown 都還沒有，以下三件事要在上游完成後補上。
  evidence: Story 5.2 Decisions（使用者 2026-10-30 定案）：先顯示截止時間，加一個倒數插槽，B 的 Countdown 做好後再放進去。
  (1) 公開單場 API 的提議形狀（見上方 5.8 第一階段一項）要多一個 `appeal_deadline`（ISO，申訴期、申訴中才有值，其他狀態為 null），對應 `frontend/src/features/competition/match-types.ts` 的 `PublicMatchDetail.appeal_deadline`；
  (2) B 的 Countdown（2.4，`appeal` 變體，帶進度條）做好後，由 S4 路由 `frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx` 把它傳給 `MatchSpectatorView` 的 `appealCountdown`，`MatchAppealWindow` 不重做倒數；
  (3) 到期後要顯示「已截止 · 系統處理中」（EXPERIENCE.md〈倒數與時間〉到期行為），由 Countdown 負責；`MatchAppealWindow` 目前不讀裝置時鐘、不判斷是否到期。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-game-settings-and-school-list.md`
  summary: Story 2.1 第二階段：S36 遊戲設定（列表、新增／編輯頁、段位表）與學校清單分頁的前端畫面，含側欄入口、375 px 卡片版面，以及學校異動後讓 `["identity","schools"]` 查詢失效。
  evidence: 2026-10-29 使用者決定 2.1 拆兩階段：後台 Sidebar 版面、Data table 由 A 的 1.8 提供（11/1），第一階段只做後端以趕上 2.2 的 10/31 期限。1.8 合併後另寫 spec 實作，並驗收 epics.md Story 2.1 的 S36 相關 AC。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-game-settings-and-school-list.md`
  summary: （低）Pydantic 內建的 422 訊息是英文：缺欄位、列舉值不合法（例如 `score_type`）、型別不是 list／object 時，`detail[].msg` 不是繁中，前端直接顯示會出現英文。
  evidence: 2026-10-29 Story 2.1 第一階段審查（Edge Case Hunter）。既有問題，identity 的 API 也一樣（`core/errors.py` 沒有翻譯 `RequestValidationError`）。處理時在 core 加一個 `RequestValidationError` handler，依 `type`（missing、enum、list_type 等）換成繁中訊息，並補測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-create-tournament.md`
  summary: Story 2.2 第二階段：S25 我的賽事（列表、狀態徽章、空狀態「你還沒有建立賽事。」）、S26 建立賽事表單（選遊戲帶入預設值、每輪間隔不足時顯示最小間隔、欄位錯誤顯示）、S27 賽事總覽（主辦方賽事後台側欄「查看賽事頁」「總覽」、狀態徽章、模式、報名期間、優先期結束、開賽時間），以及接手 1.8 的 `routes/organizer/index.tsx`。
  evidence: 2026-10-30 使用者決定 2.2 拆兩階段：主辦方後台版面、`/organizer` 路由、Data table、狀態徽章由 A 的 1.8（PR #11）提供，第一階段只做後端以趕上 10/31 的交接期限。1.8 合併後另寫 spec，並驗收 epics.md Story 2.2 的畫面 AC；時間輸入需要新增以 Asia/Taipei 輸入、送出 UTC 的處理。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-create-tournament.md`
  summary: Story 2.2 第二階段的 S26 表單：名額超過 128 時，送出前彈出提醒「名額超過 128 隊，請確認沒有輸入錯誤」，主辦方確認後才送出（後端不限制 128）。
  evidence: 2026-10-30 使用者決定：128 是提醒門檻、不是上限，避免誤輸入極大值又不擋住真的需要的大型賽事。第一階段後端只擋 < 2 與超過資料庫整數上限。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-create-tournament.md`
  summary: （中）目前沒有任何工作把賽事從 `open` 轉成 `closed`，`ensure_accepting_registrations` 也只看狀態；在 C 的 3.6 完成前，報名截止時間過後仍可報名。
  evidence: 2026-10-30 Story 2.2 第一階段審查（Blind Hunter）。依 `contracts/tournaments.md`〈三〉，`open` → `closed` 由 3.6 在截止補位之後呼叫 `transition_tournament`。3.6 實作時要確認截止工作會轉換狀態；若 3.6 延後，改由 `ensure_accepting_registrations` 另外比對 `registration_end` 與 `clock.now()`，並同步修改約定。
- source_spec: `_bmad-output/implementation-artifacts/spec-5-3-score-rules.md`
  summary: （低）`rounds` 型態的回合數沒有上限，純函式 `scoring.make_game` 接受任意大的非負整數；寫入資料庫的整數欄位時可能溢位。
  evidence: 2026-10-29 Story 5.3 第一階段審查（Edge Case Hunter、Blind Hunter）。第二階段寫 `record_game` 的 API schema 時，以 `Field(ge=0, le=...)` 設定合理範圍（例如 999），回 422。
- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-panel.md`
  summary: （中）前端單元測試在容器冷啟動時不穩定：`login`、`signup`、`account`、`auth`、`forgot-password` 等走路由的舊測試，在 frontend 容器裡第一次執行會有 4～32 個因等不到元素（預設 1 秒）失敗，同一個容器第二次執行全部通過。CI 若遇到機器忙碌也可能偶發失敗。
  evidence: 2026-10-29 在沒有任何前端改動的分支（story/5-5）上重現：第一次 14 failed／162，第二次 162 passed；與本 Story 的新測試無關。可能的修法：路由測試的 `findBy*` 加長 timeout，或在 `vitest.config.ts` 設 `testTimeout`／預先載入路由，修好後以冷啟動連跑多次確認。

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: （低）competition 純函式（schedule.py；4.1 合併後的 bracket.py、5.5 的 progression.py 也適用）要求的 90% 分支覆蓋率只靠 spec 的手動指令驗證，CI 沒有強制。
  evidence: CI 在 backend 容器內執行 `scripts/test.sh`，其中 `coverage run` 沒有 `--branch`，全域門檻是 `fail_under = 85`。CI 要另加一步 `coverage run --branch -m pytest tests/competition` 再 `coverage report --include=... --fail-under=90`；若改成全域開 branch，要先確認整體覆蓋率仍高於 85%。

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: 4.3 第二階段的改時間 service 呼叫 `reschedule_window`／`check_reschedule` 時，準決賽的 `next_match_at` 要傳決賽與季軍賽中較早的那一場。
  evidence: A 在 #5 的審查：8 強 10:00、準決賽 12:00、決賽 16:00、最小間隔 85 分，先把季軍賽改到 14:00、再把準決賽改到 13:00 都會被允許，但準決賽最早 14:25 才結束。`schedule.py` 只收一個 `next_match_at`，規則（不晚於兩隊要去的下一場）要由呼叫端選對場次；docstring 已註明。

- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md`
  summary: Story 3.4～3.6 第二階段：把純函式 `registration/allocation.py`（`allocate_priority_window`、`decide_first_come`、`waitlist_order`、`fill_from_waitlist`）接上資料庫、worker、事件與畫面。
  evidence: 第一階段只寫純函式，因 Registration 資料表（3.1）與賽事、`lock_tournament`（2.2）尚未合併。第二階段要做：worker 工作在優先期結束與報名截止後 1 分鐘內執行，先 `lock_tournament()`、取報名快照、呼叫本模組、以 `mark_status` 改狀態、寫操作紀錄（操作者 `system`）、發 outbox 事件，重複執行結果不變（以 `frozen_clock` 推進時間測試）；優先期結算時保存「優先期有報名的學校」（結算輸入的學校集合）供先搶期的 `priority_schools` 使用；先搶期送出在鎖內呼叫 `decide_first_come`，並補 200 筆平行送出的併發測試；S17／S12 顯示「正取」「候補第 N 位」或「候補・目前不在遞補順序中」＋原因（`REASON_MESSAGES`、`REPRESENTATIVE_BACKFILL_MESSAGE`）。本模組把 `drawn` 也算進每校正取數，第二階段確認抽籤後的狀態名稱與此一致。跨人交接：registration 要提供公開函式 `fill_at_deadline`（epic-3-context；D 的 4.1 在開放報名中抽籤時呼叫，交接期限 11/12）；截止工作必須確保優先期結算已先執行，不能有 `pending` 報名被 `fill_from_waitlist` 漏掉。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md`
  summary: `allocation.py` 沒有「優先期代表隊退出時，由同校平均段位積分次高的隊伍遞補」的對象函式（FR-17）。
  evidence: 2026-11-01 Story 3.4 第一階段 Code Review（Blind Hunter）。只在代表隊撤回或被退回時觸發（3.7、3.8 期中擱置），期中不會發生；做 3.7 或 3.8 時在本模組新增，並讓先搶期名額釋出時的遞補先處理這個情況（medium）。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md`
  summary: epic-3-context 要求 `AllocationPolicy` 分支覆蓋率 ≥ 90%，但 `scripts/test.sh` 沒有 `--branch`，只靠 spec 的手動指令檢查。
  evidence: 2026-11-01 Story 3.4 第一階段 Code Review（Verification Gap）。目前實測 100%；之後修改 `allocation.py` 時若漏測分支，一般測試仍會通過。要自動檢查時，在 CI 加一步對 `app/modules/registration/allocation.py` 以 `--branch` 量測並設 `--fail-under=90`（low）。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: Story 2.4 第二階段：S1、S2 的狀態改用 1.7 的 `StatusBadge`（開放報名、進行中 live＋進行中脈動、賽程已公布 brand、已取消 destructive、其餘 muted-foreground）；S1 頂部「想辦賽事？申請成為主辦方」Page banner（已登入、非主辦方、沒有待審核申請；可關閉，存 `localStorage`，連到 `/organizer/apply`）；S1 空狀態對主辦方另顯示「建立賽事」（連到 2.2 第二階段的 S26）。
  evidence: 2026-11-02 使用者決定 2.4 拆兩階段：`StatusBadge`、申請 API 在 A 的 1.7（PR #10），主辦方身分在 1.8（PR #11），兩者都未合併。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: （低）公開賽事列表 `GET /tournaments` 沒有分頁或上限，未登入的請求一次取回所有賽事（含已結束、已取消）。
  evidence: 2026-11-02 Story 2.4 第一輪審查（Blind Hunter、Edge Case Hunter）。期中賽事數量少；賽事累積後在 S1 改為分頁（沿用 1.8 的分頁格式）或只回最近的已結束賽事。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: S2 總覽「開放報名」時要顯示「已正取隊數／名額」（EXPERIENCE.md 狀態表），2.4 只顯示名額；需要 registration 提供正取隊數的公開函式。
  evidence: 2026-11-02 Story 2.4 第二輪審查（Blind Hunter）。spec 的 Never 明定不做；由 C 的 3.x 提供計數後，在 S2 總覽補上。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: S2「開放報名」時啟用的「建立隊伍」按鈕與 3.1 的 `CreateTeamDialog` 尚未接上；2.4 只做「尚未開放」時停用的按鈕。
  evidence: 2026-11-02 Story 2.4 第二輪審查（Blind Hunter）。spec 的 Never 明定由 C 的 3.1 在 S2 總覽掛上對話框（3.1 spec 第 39 行同樣記載）。
