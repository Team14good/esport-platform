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

## Deferred from: spec-3-2-player-registration-info.md 第一段 (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-player-registration-info.md`
  summary: 上傳 API 沒有請求大小上限，5 MB 在 multipart 整個收完後才由 `core.storage` 檢查。
  evidence: 2026-10-30 Story 3.2 第一段 Code Review（Blind Hunter）。Starlette 會先把整個 body spool 到暫存檔，超大請求仍會被完整接收；第二段建 multipart API 時要決定請求大小上限（例如檢查 `Content-Length`）（medium）。

## Deferred from: spec-5-2-forfeit-rules.md (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-forfeit-rules.md`
  summary: Story 5.2 第二階段尚未實作：第一階段只有 `competition/forfeit.py` 的純函式（`judge_forfeit`、`appeal_deadline`），還沒有 worker 工作、資料寫入、事件與畫面，所以逾時後實際上不會判棄權。
  evidence: 依賴 D 的 4.1（Match 資料表、`lock_match`、`transition_match`）與 5.1（`list_forfeit_due`、`list_check_ins`），兩者尚未合併。合併後在 competition 新增檔案完成以下範圍（不修改 D 的 `service.py` 既有函式）：
    - worker 工作：用 `list_forfeit_due` 選場次，`lock_match` 後以 `list_check_ins` 與賽事狀態重新呼叫 `judge_forfeit`；有結果時寫入 outcome、勝隊、wins 與 `appeal_deadline(decided_at=現在, appeal_minutes=賽事申訴時限)`，`submitted_by` 留空，再用 `transition_match` 轉為申訴期。重複執行沒有副作用。
    - 操作紀錄以 `app.core.audit.record()` 記 actor 為 system；發出判棄權事件（期中只發不通知）。
    - S4 顯示哪一隊棄權（雙方棄權時兩隊都標示）與申訴期倒數。
    - 確認 D 的場次狀態轉換表允許「待開打 → 申訴期」；若不允許，請 D 在轉換表新增，不由 5.2 修改。

## Deferred from: Story 5.2（S4 申訴期區塊，2026-10-30）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-game-settings-and-school-list.md`
  summary: （低）Pydantic 內建的 422 訊息是英文：缺欄位、列舉值不合法（例如 `score_type`）、型別不是 list／object 時，`detail[].msg` 不是繁中，前端直接顯示會出現英文。
  evidence: 2026-10-29 Story 2.1 第一階段審查（Edge Case Hunter）。既有問題，identity 的 API 也一樣（`core/errors.py` 沒有翻譯 `RequestValidationError`）。處理時在 core 加一個 `RequestValidationError` handler，依 `type`（missing、enum、list_type 等）換成繁中訊息，並補測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-create-tournament.md`
  summary: （中）目前沒有任何工作把賽事從 `open` 轉成 `closed`，`ensure_accepting_registrations` 也只看狀態；在 C 的 3.6 完成前，報名截止時間過後仍可報名。
  evidence: 2026-10-30 Story 2.2 第一階段審查（Blind Hunter）。依 `contracts/tournaments.md`〈三〉，`open` → `closed` 由 3.6 在截止補位之後呼叫 `transition_tournament`。3.6 實作時要確認截止工作會轉換狀態；若 3.6 延後，改由 `ensure_accepting_registrations` 另外比對 `registration_end` 與 `clock.now()`，並同步修改約定。

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: （低）competition 純函式（schedule.py；4.1 合併後的 bracket.py、5.5 的 progression.py 也適用）要求的 90% 分支覆蓋率只靠 spec 的手動指令驗證，CI 沒有強制。
  evidence: CI 在 backend 容器內執行 `scripts/test.sh`，其中 `coverage run` 沒有 `--branch`，全域門檻是 `fail_under = 85`。CI 要另加一步 `coverage run --branch -m pytest tests/competition` 再 `coverage report --include=... --fail-under=90`；若改成全域開 branch，要先確認整體覆蓋率仍高於 85%。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: `confirm_walkover` 不檢查空缺方是否真的確定不會有隊伍，6.5 呼叫前要自己確認（未驗證，若為真屬 medium）。
  evidence: Edge Case Hunter：空缺方的來源場次還沒定案時就以輪空確認，來源的勝隊之後會發現下一場已定案而被丟掉。要確認 6.5 的呼叫時機，或在 `confirm_walkover` 用 progression 的來源推導擋下。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: 6.2 更正已結束賽事或季軍賽已開打後的準決賽時，`VoidMatch`、名次與賽事狀態怎麼處理還沒定（未驗證，若為真屬 medium）。
  evidence: `_void` 只能從待開打轉 voided；`_finish` 對已結束的賽事不再動作，但名次從場次重算，會和 `tournament.podium` 操作紀錄不一致。6.2 實作時要決定規則並補測試。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-8-public-match-api.md`
  summary: （低）賽事取消後，停在申訴期或申訴中的場次，公開單場 API 仍會回傳 `appeal_deadline`，但 worker 已不再自動確認（未驗證，若為真屬 low）。
  evidence: 2026-10-31 公開單場 API 審查（Edge Case Hunter、Blind Hunter）。期中不能取消賽事（2.6 擱置），已結束的賽事也不會有停在申訴期的場次，所以目前不會發生。2.6 實作取消時，要決定公開頁對這類場次顯示什麼，並在 `get_public_match` 加上賽事狀態判斷。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （低）報到只鎖場次、讀賽事狀態不加鎖；2.6 做取消賽事時，取消與報到同時發生可能寫入一筆已取消賽事的報到紀錄。
  evidence: 2026-11-01 5.1 第二階段審查（Blind Hunter、Edge Case Hunter）。期中不能取消賽事（2.6 擱置），所以目前不會發生。2.6 實作時改成先 `lock_tournament` 再 `lock_match`（AD-6 順序），或由取消流程鎖住所有場次。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （低）兩隊同時報到只以先後兩次請求與唯一鍵測試，沒有在兩條真實資料庫連線上測併發。
  evidence: 測試環境所有 session 共用同一條連線與交易，無法製造真正的併發。若之後測試架構支援多連線，補一個兩隊同時 POST 的測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: 4.3 第二階段的改時間 service 呼叫 `reschedule_window`／`check_reschedule` 時，準決賽的 `next_match_at` 要傳決賽與季軍賽中較早的那一場。
  evidence: A 在 #5 的審查：8 強 10:00、準決賽 12:00、決賽 16:00、最小間隔 85 分，先把季軍賽改到 14:00、再把準決賽改到 13:00 都會被允許，但準決賽最早 14:25 才結束。`schedule.py` 只收一個 `next_match_at`，規則（不晚於兩隊要去的下一場）要由呼叫端選對場次；docstring 已註明。

- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md`
  summary: `allocation.py` 沒有「優先期代表隊退出時，由同校平均段位積分次高的隊伍遞補」的對象函式（FR-17）。
  evidence: 2026-11-01 Story 3.4 第一階段 Code Review（Blind Hunter）。只在代表隊撤回或被退回時觸發（3.7、3.8 期中擱置），期中不會發生；做 3.7 或 3.8 時在本模組新增，並讓先搶期名額釋出時的遞補先處理這個情況（medium）。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md`
  summary: epic-3-context 要求 `AllocationPolicy` 分支覆蓋率 ≥ 90%，但 `scripts/test.sh` 沒有 `--branch`，只靠 spec 的手動指令檢查。
  evidence: 2026-11-01 Story 3.4 第一階段 Code Review（Verification Gap）。目前實測 100%；之後修改 `allocation.py` 時若漏測分支，一般測試仍會通過。要自動檢查時，在 CI 加一步對 `app/modules/registration/allocation.py` 以 `--branch` 量測並設 `--fail-under=90`（low）。
- source_spec: `_bmad-output/implementation-artifacts/spec-5-3-referee-score-backend.md`
  summary: （未驗證，若為真屬 medium）比分寫入只 `lock_match`、讀賽事狀態不加鎖；2.6 取消賽事若不鎖場次，取消與登錄同時發生時，比分可能寫進已取消的賽事。
  evidence: 2026-11-01 5.3 第二階段審查（Edge Case Hunter）。2.6 尚未實作無法重現；2.6 實作時取消流程要依 AD-6 鎖賽事再鎖場次，或比分寫入改為先 `lock_tournament`。

- source_spec: `_bmad-output/implementation-artifacts/spec-6-2-replay-clear-helper.md`
  summary: 6.2 `replay_match`（B）要呼叫 `clear_for_replay` 並串完整重賽流程，目前尚未實作。
  evidence: 呼叫順序：`lock_tournament` → `clear_for_replay` → `transition_match` 回待開打 → 寫入新 `scheduled_at` → `start_forfeit_clock` → 操作紀錄 → 事件；全部在同一個交易內。操作紀錄的變更前內容用 `ReplayCleared`（報到、各局、結果、勝隊、勝局數與各期限）。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: （低）公開賽事列表 `GET /tournaments` 沒有分頁或上限，未登入的請求一次取回所有賽事（含已結束、已取消）。
  evidence: 2026-11-02 Story 2.4 第一輪審查（Blind Hunter、Edge Case Hunter）。期中賽事數量少；賽事累積後在 S1 改為分頁（沿用 1.8 的分頁格式）或只回最近的已結束賽事。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: S2 總覽「開放報名」時要顯示「已正取隊數／名額」（EXPERIENCE.md 狀態表），2.4 只顯示名額；需要 registration 提供正取隊數的公開函式。
  evidence: 2026-11-02 Story 2.4 第二輪審查（Blind Hunter）。spec 的 Never 明定不做；由 C 的 3.x 提供計數後，在 S2 總覽補上。

## Deferred from: spec-3-1-create-team-entry.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-create-team-entry.md`
  summary: A 的 identity：註冊時 email 的 @ 前面含中文（例如 `主辦方@example.com`）會被接受，但驗證信寄不出去，帳號無法完成驗證（low，未確認是否要擋）。
  evidence: 2026-11-02 3.1 瀏覽器實測準備資料時發現，worker 記錄 `Email delivery ... failed (attempt 1): UnicodeEncodeError: 'ascii' codec can't encode characters`；改用英文 email 後正常。不是本 Story 造成。處理方式二擇一：註冊時以 422 擋下非 ASCII 的本地部分，或寄信時啟用 SMTPUTF8。

## Deferred from: spec-2-4-status-badge-and-organizer-banner.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-status-badge-and-organizer-banner.md`
  summary: Story 2.4 第二階段第 3 項：S1 空狀態「目前沒有公開的賽事。」對主辦方另顯示「建立賽事」，連到 2.2 第二階段的 S26（`/organizer/tournaments/new`）（low）。等 PR #31 合併後再做。
  evidence: 2026-11-03 使用者決定 2.4 第二階段先只做狀態徽章與申請主辦方 banner；S26 在 PR #31，尚未合併。上方 source_spec 為 `spec-2-4-public-tournament-pages.md` 的「Story 2.4 第二階段」那筆列了三項，其中狀態徽章、申請主辦方 banner 兩項已由 `spec-2-4-status-badge-and-organizer-banner.md` 完成，只剩本項；那筆依使用者指示保留不刪。
  summary: （低）`PageBanner` 的 `action` 只支援 `onClick`，S1「申請成為主辦方」按鈕以程式導向，不能中鍵開新分頁或複製連結；需要 A 為 `PageBanner` 新增連結型的 action。
  evidence: 2026-11-03 Story 2.4 第二階段審查（Blind Hunter）。`PageBanner.tsx` 是 A 的元件，本 Story 只 import 不修改。
## Deferred from: spec-3-2-player-registration-info-2.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-player-registration-info-2.md`
  summary: 上傳 API（`PUT /teams/{team_id}/members/me/profile`）仍沒有請求大小上限；上面第一段留下的同一項再次延後（medium）。
  evidence: 第二段 spec 的 Never 明定「不做請求大小上限」：`save_image` 邊讀邊擋 5 MB，超過的檔案不會存下，但 Starlette 仍會先把整個 multipart body spool 到暫存檔。只靠 `Content-Length` 擋不住 chunked 傳輸，要在 ASGI middleware 或反向代理（例如 `client_max_body_size`）處理，屬部署層的決定，不在本 Story 範圍。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-bracket-page.md`
  summary: S2 在「賽程已公布」「進行中」時應以「對戰表」為預設分頁（epics 4.6 AC、EXPERIENCE.md 狀態表），4.6 第二階段沒有做；目前 `/tournaments/$tournamentId` 固定顯示總覽，觀眾要自己點「對戰表」。
  evidence: 2026-11-03 使用者決定（spec Decisions 1A）交給 B 決定做法。「總覽」分頁本身連到 `/tournaments/$tournamentId`，直接導向會讓總覽點不回去。可行做法：總覽改用新網址（例如 `/overview`），`/tournaments/$tournamentId` 依狀態導向 `/bracket` 或總覽；或 S1 列表在這兩個狀態直接連到 `/bracket`（外部分享連結仍落在總覽）。兩者都要改 B 的 `TournamentPage`／`TournamentTabs`／`TournamentList`。

## Deferred from: spec-7-2-e2e-tournament-drill.md (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill.md`
  summary: 觀眾 e2e 從 S3 對戰表點場次卡進 S4、再回到 S3 的步驟（`spectator.spec.ts` 的 `test.fixme`）還沒接上；目前場次頁直接開開發模式的假資料 `tournament-fixture`。
  evidence: 2026-11-03 合併 main 後，4.6 第二階段已刪除 `/dev/bracket`。真的 S3 需要已抽籤的賽事（7.1 示範資料或測試內建立），S4 要等 D 的 #21 與 5.8 第二階段接上單場 API；使用者決定先 fixme。接上時要檢查 375 px 只有對戰樹容器橫向捲動。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill.md`
  summary: `tournament.spec.ts`「觀眾未登入瀏覽公開賽事列表與賽事頁的正取隊伍」仍是 `test.fixme`；2.4（#29）已合併，但正取隊伍要有 3.x 的報名資料。
  evidence: 2026-11-03 D 在 7.2 第一階段審查中提出可以接上；使用者決定留到第二階段，跟報名步驟一起做。

## Deferred from: Story 7.1 第二階段 competition 步驟（2026-11-03）

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-organizer-tournament-ui.md`
  summary: （低）主辦方賽事清單的查詢在兩處各定義一次：`features/tournaments/organizer-queries.ts` 的 `myTournamentsQueryOptions` 與 C 的 `features/registration/CreateTeamEntry.tsx` 的 `organizerTournamentsQueryOptions`，都用查詢鍵 `["tournaments","organizer","list"]`；之後只改其中一邊（例如 `queryFn` 或回傳型別），兩邊的快取會互相污染。
  evidence: 2026-11-03 A（@max930000）在 PR #31 的審查。處理時請 C 把 `CreateTeamEntry.tsx` 改成 import `myTournamentsQueryOptions`，刪掉自己的定義（registration 模組只新增 import，不改 tournaments 的檔案）。

## Deferred from: spec-5-2-appeal-countdown-and-banner-link.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-appeal-countdown-and-banner-link.md`
  summary: B 的 `OrganizerApplyBanner.tsx`：S1「申請成為主辦方」改用 `PageBanner` 新增的連結型 action（`action: { label, to: "/organizer/apply" }`），就能中鍵開新分頁、複製連結（low）。
  evidence: 2026-11-04 A 已為 `PageBanner` 新增 `to`；使用者決定不改 B 的既有函式，交給 B。改完後 S1 的測試要從按鈕改成連結。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-s36-game-settings-and-school-list-ui.md`
  summary: （低）`GameForm` 與 `SchoolDialog` 把 `form.formState.isSubmitting` 納入送出鈕停用，防止連點重複送出，但沒有測試：拿掉 `isSubmitting` 後現有測試仍會通過。
  evidence: 2026-11-03 A（@max930000）在 PR #30 的審查。下次動到這兩個表單時補測試：讓 `createGame`／`createSchool` 回傳一個未完成的 Promise，連按兩次送出，斷言只呼叫一次，且送出中按鈕停用。

## Deferred from: spec-7-2-e2e-tournament-drill-2.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill-2.md`
  summary: 完整賽事演練目前每款遊戲只組一隊（使用者 2026-11-04 決定）；抽籤以後的步驟需要 `teamCount` 隊（特戰英豪、英雄聯盟 32 隊，星砂競技場 8 隊）各自滿編、填完參賽資料並送出報名，要等 3.3～3.6 合併後再補。
  evidence: 每位選手都經畫面註冊並等驗證信，一隊 3～7 人就要 1～2.5 分鐘；32 隊×7 人照同樣做法太慢，補的時候要另外決定建立大量隊伍的方式（例如改用 7.1 示範資料的隊伍，或只讓少數隊伍走畫面）。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-2-e2e-tournament-drill-2.md`
  summary: e2e 一次只跑 1 個測試（`playwright.config.ts` 的 `workers: 1`，`tournament.spec.ts` 另有 `describe.configure({ mode: "default" })`），完整跑一次約 22 分鐘；演練同時跑會互相拖慢，一般 API 超過 1 秒（NFR-2），甚至整個卡住。
  evidence: 2026-11-04 實測：本機沒設 worker 上限時，16 核預設開 8 個 worker，6 個演練同時開瀏覽器、註冊帳號，`POST /accounts` 6～7 秒、`GET /accounts/me` 約 2.4 秒，之後停住超過 20 分鐘；2 個 worker 時 e2e 容器約吃 5 核；1 個 worker 時 10 passed、62 skipped（22.4 分鐘）。7.3 彙整回應時間時要知道這些數字是在什麼並行度下量的；之後要縮短時間，`WORKER_POLL_SECONDS` 最小只能設 15 秒（`core/config.py`），省不多，要另找方法（例如共用已驗證的選手帳號）。
## Deferred from: spec-2-7-referee-invitation.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-referee-invitation.md`
  summary: 2.7 第二階段：S31（`/organizer/tournaments/$tournamentId/referees`，邀請連結＋已接受的裁判名單、空狀態「還沒有裁判接受邀請。複製邀請連結傳給裁判。」）與 S23（`/referee-invite/$inviteToken`，預覽＋接受、過期文案「此裁判邀請已過期，請向主辦方索取新連結。」）畫面，並重新產生 `frontend/src/client`。
  evidence: 第一階段 spec 的 Never 明定不做前端；S31 要沿用 3.1 的 Invite link field，等它合併後再做。後端 API 已在第一階段完成。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-referee-invitation.md`
  summary: （中）裁判邀請的預覽（`PublicRefereeInvitation`）與主辦方查看目前邀請（`RefereeInvitationRead`），在賽事已結束或已取消時仍回 `expired: false`，要等按下接受才得到 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
  evidence: 2026-11-04 Story 2.7 第一階段審查（Edge Case Hunter）。凍結區塊的預覽欄位只有賽事名稱、到期時間、是否過期，加欄位屬於改需求；第二階段做 S23、S31 時一起決定：加一個 `closed` 欄位或把 `expired` 改為「無法接受」，並讓畫面顯示原因。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-7-referee-invitation.md`
  summary: （低）裁判邀請的 token 放在網址路徑（`GET /referee-invites/{token}`、`POST /referee-invites/{token}/accept`），uvicorn 與反向代理的 access log 會記下完整路徑，token 會留在 log 裡；與 3.1 的隊伍邀請連結做法相同。
  evidence: 2026-11-04 D（@OG-Matcha）在 PR #40 的審查，期中可以接受。之後要收緊時，accept 改用 body 帶 token，或在 log 遮蔽這段路徑；隊伍邀請一併處理。
## Deferred from: spec-7-1-tournaments-demo-step.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-tournaments-demo-step.md`
  summary: （低）示範賽事的時間在第一次建立時固定（開賽＝當時＋7 天）；保留資料庫、超過 7 天後再次啟動時，tournaments 步驟依「主辦方＋名稱」沿用這場已過開賽時間的賽事，competition 步驟的抽籤會因 `TOURNAMENT_START_PASSED` 一直略過。
  evidence: 2026-11-04 Story 7.1 tournaments 步驟第一輪審查（Blind Hunter、Edge Case Hunter）。凍結區塊規定已存在就沿用、不覆寫；Demo 前用 `docker compose down -v` 清掉資料庫即可。要自動處理時，需由人決定：過期就另建一場（會有兩場同名賽事）或改寫既有賽事的時間（違反「不覆寫」）。
- source_spec: `_bmad-output/implementation-artifacts/spec-7-1-tournaments-demo-step.md`
  summary: 示範資料的 tournaments 步驟已建立「FLOW 校園盃 特戰英豪」並寫入 `context.tournament_to_draw`（開放報名、開賽在啟動後 7 天），competition 步驟會嘗試抽籤；但目前沒有 registration 步驟建立 32 隊正取，registration 也還沒提供抽籤用的 `finalize_for_draw`、`list_accepted_teams` 等函式，實際啟動會記錄 `REGISTRATION_UNAVAILABLE` 並略過抽籤。
  evidence: 2026-11-04 Story 7.1 tournaments 步驟（B）完成後，以 compose 實際啟動確認的 log。剩下的是 C 的 registration 步驟（32 隊正取，放在 `STEPS` 的 tournaments 之後、competition 之前）與 contracts/competition.md〈二〉的四個函式；賽事維持 `open`，所以 `draw` 會先呼叫 `finalize_for_draw`（spec-7-1-tournaments-demo-step.md Decisions）。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-backfill.md`
  summary: （中）Story 3.4～3.6 第二階段：先搶期送出與截止補位時，在同一個 `lock_tournament()` 鎖與交易內先呼叫 `backfill_vacancies` 讓有順位的候補遞補（以 `mark_status` 改為正取、寫操作紀錄、發事件），再以更新後的報名呼叫 `decide_first_come` 判定新送出的報名。
  evidence: 2026-11-04 OG-Matcha 在 PR #28 的審查建議 1。期中抽籤前取消資格不立即遞補（epics.md 規則 6），先搶期會出現空位；不先遞補時新送出的隊伍會插到「候補第 1 位」前面（`test_backfill_without_backfill_new_submission_would_jump_queue`）。截止補位階段 `backfill_vacancies(phase=AFTER_DEADLINE)` 與 `fill_from_waitlist(remaining=空位)` 相同，擇一呼叫即可。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-allocation-backfill.md`
  summary: （中）先搶期釋出的是優先期代表隊（期中由 6.5 抽籤前取消資格觸發）時，`backfill_vacancies` 依先搶期順位把名額給別校，沒有依 FR-17「由同校平均段位積分次高的隊伍遞補」。
  evidence: 2026-11-04 PR #28 審查修正的 Code Review（Blind Hunter）。3.4 第一階段的 deferred 項目寫「代表隊退出只在撤回、退回時觸發，期中不會發生」，但期中 6.5 可在先搶期取消優先期代表隊的資格，之後分配時就會走到這條路；同校候補的 `representative_backfill` 也會因代表隊不再是正取而變成 False。修正需在本模組新增同校遞補規則（需確認 `priority_schools` 中哪一隊是代表隊），並讓 `backfill_vacancies` 先處理。
- source_spec: none
  summary: Story 3.6 第二階段：報名截止 worker 工作（賽事轉為「報名截止」並以 `backfill_vacancies(AFTER_DEADLINE)`／`fill_from_waitlist` 補位、操作紀錄、事件）、公開函式 `fill_at_deadline` 給 D 的 4.1 呼叫、S2「抽籤準備中」。
  evidence: 2026-11-04 bmad-build 單一目標檢查，邱芯彤選擇把 3.4～3.6 第二階段拆開，依序 3.4 → 3.6 → 3.5。3.6 可獨立合併；跨人交接期限 11/12（D 的 4.1、B 的 6.5 在等），排在 3.4 之後第一個做；截止工作須確保優先期結算已執行。
- source_spec: none
  summary: Story 3.5 第二階段：先搶期送出時，在 3.3 `submit_registration` 的 `lock_tournament()` 鎖內先呼叫 `backfill_vacancies(FIRST_COME)` 遞補，再以 `decide_first_come` 判定正取或候補，回應直接帶結果與候補順位；補 200 筆平行送出的併發整合測試。
  evidence: 2026-11-04 bmad-build 單一目標檢查，邱芯彤選擇把 3.4～3.6 第二階段拆開。3.5 只改送出流程與併發測試，可獨立合併，排在 3.6 之後；沿用 3.4 第二階段建立的「優先期有報名的學校」與 S17／S12 狀態顯示。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-4-assign-referee-backend.md`
  summary: S4 要隨 `is_scorer` 顯示或隱藏比分登錄面板：指派、改派、收回後（含晉級衝突自動收回），`ScoreEntryState.is_scorer` 會改變，S4 需重抓 `GET .../score-entry`（A 的 S4 工作）。
  evidence: 2026-11-04 承接已刪除的 5.3 項目；後端端對端測試已在 `test_assign_referee.py`（指派／收回後 `is_scorer` 切換、晉級衝突收回），前端尚未接上。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-s30-matches-page.md`
  summary: 主辦方賽事後台側欄在子頁（例如 S30 `/organizer/tournaments/{id}/matches`）時，「總覽」（`/organizer/tournaments/{id}`）也顯示為目前位置：`BackofficeLayout` 的 `Link` 沒設 `activeOptions`，以前綴比對；「我的賽事」（`/organizer`）在所有賽事頁也同樣亮起。
  evidence: 2026-11-04 S30 實作時發現；B 的 S31 裁判頁也會遇到。修法需要改 B 的 `components/layout/BackofficeLayout.tsx`（例如 `BackofficeNavItem` 加選填的 `exact`，傳給 `activeOptions`），S30 spec 禁止改 B 的元件，交給 B 決定。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-s30-matches-page.md`
  summary: S30 的 Manual checks 還沒做：在瀏覽器（含 375 px）走一次列表、修改時間、指派、收回。
  evidence: 2026-11-04 A 在 #48 審查提醒。本機沒有已抽籤的賽事（抽籤要等 C 的 registration 函式，或 7.1 示範資料有已抽籤的賽事），目前只有單元測試；任一條件完成後補做。

## Deferred from: spec-5-8-real-match-data.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-8-real-match-data.md`
  summary: 觀眾 e2e（`frontend/tests/e2e/spectator.spec.ts`）的 S3、S4 目前以 `page.route` 回傳假對戰樹（`support/match-api.ts`），沒有走真的後端；7.1 示範資料有已抽籤的賽事後，要補一份從真賽事 S2「對戰表」分頁進入、走真 API 的版本。
  evidence: 2026-11-04 使用者依 D 在 PR #47 審查的建議，決定先改用 `page.route`，不等 7.1。假資料只驗證前端流程與版面（含 375 px），測不到公開 API 的實際回應與 NFR-2 回應時間。

## Deferred from: spec-4-4-s13-referee-matches.md (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-4-s13-referee-matches.md`
  summary: `Match.referee_account_id` 沒有索引，`GET /me/referee/matches` 會掃整張場次表；資料變多時要加索引，並另開一支 Alembic 遷移。
  evidence: 2026-11-04 S13 實作與審查第 1 輪；期中規模可接受，且 `tests/test_migrations.py` 要求遷移與模型一致，所以這個 Story 沒動 schema。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md`
  summary: Story 3.6 第二階段：確認抽籤後的報名狀態名稱與 `allocation.py` 一致——`allocation.py` 把 `drawn`（已參賽）也算進每校正取數（FR-17「含抽籤後」），3.4 第二階段的 S17／S12 候補順位也把 `drawn` 當正取。
  evidence: 2026-11-04 Story 3.4 第二階段刪除第一階段的「Story 3.4～3.6 第二階段」項目時，該項目裡的這項檢查沒寫進 3.6 的新項目，依 spec 補上。3.6 接上 D 的 4.1（抽籤時把報名標為已參賽）時，確認 4.1 呼叫的 registration 函式寫入的狀態就是 `drawn`。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md`
  summary: Story 3.6 第二階段：截止補位與 4.1 的 `finalize_for_draw`（開放報名中提前抽籤）都要先在鎖內呼叫 `settle_priority_window`，並處理優先期後送出、仍為 `pending` 的報名，不能讓它們被 `fill_from_waitlist` 漏掉或在抽籤後留在 `pending`。
  evidence: 2026-11-04 Story 3.4 第二階段審查（Blind Hunter、Edge Case Hunter）。刪除第一階段的「Story 3.4～3.6 第二階段」項目時，「不能有 `pending` 報名被 `fill_from_waitlist` 漏掉」沒寫進 3.6 的新項目；而開發順序是 3.4 → 3.6 → 3.5，3.6 做的時候優先期後送出的報名仍會維持 `pending`（本 Story 刻意不處理）。另外 `competition/service.py` 的抽籤可以把賽事由 `open` 直接轉成 `published`，`registration_port.finalize_for_draw` 是 D 呼叫的入口；若優先期剛結束、worker 還沒結算就抽籤，優先期內的 `pending` 會留下。目前 registration 還沒提供 `finalize_for_draw`，抽籤回 503，所以現在不會發生。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md`
  summary: 補 API 層測試：同校已有 2 隊 `drawn` 時，同校候補在 S17／S12 回 `waitlist_reason == "SCHOOL_LIMIT_REACHED"`、`waitlist_phase == "after_deadline"`（驗證 `_ORDER_STATUSES` 把 `drawn` 當正取）。
  evidence: 2026-11-04 Story 3.4 第二階段審查（Verification Gap）。`allocation.py` 的純函式測試有測 `drawn`，但沒有測試讓 `drawn` 報名經過 `service._waitlist_fields` 的狀態篩選；從 `_ORDER_STATUSES` 拿掉 `DRAWN`，現有測試仍全過。目前沒有正式程式會把報名設成 `drawn`（`mark_drawn` 尚未提供），在 3.6 提供 `mark_drawn` 時補。
- source_spec: none
  summary: Story 3.6 第二階段之二：報名截止 worker 工作——截止後 1 分鐘內鎖住賽事、轉為「報名截止」，呼叫「給抽籤用的函式」那份 spec 建立的截止補位（先 `settle_priority_window`、處理優先期後送出的 `pending`、再 `fill_from_waitlist`），操作者為 system，重複執行結果不變；自訂模式只轉狀態不補位。
  evidence: 2026-11-04 bmad-build 單一目標檢查，邱芯彤選擇把 3.6 第二階段拆成兩份：先做給 D 抽籤用的四個函式（`finalize_for_draw`、`list_accepted_teams`、`mark_drawn`、`get_team_names`，目前抽籤回 503，期限 11/12），截止 worker 沿用同一段補位邏輯，排在之後。S2「抽籤準備中」B 已在 `TournamentOverview.tsx` 做好，不在範圍內。
