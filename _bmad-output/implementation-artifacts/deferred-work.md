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

## Deferred from: spec-3-1-tournament-integration.md (2026-11-02)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-tournament-integration.md`
  summary: A 的 `frontend/tests/unit/admin-applications.test.tsx`（「不是平台管理員：顯示 S38 的 403，不呼叫審核 API」）偶發失敗，CI 可能因此偶爾失敗；請 A 確認原因並修正（medium，未證實）。
  evidence: 2026-11-02 3.1 收尾時前端全部單元測試連跑 3 次，失敗 1 次，其他 2 次全過。同次在 `team-pages.test.tsx` 量到的原因是路由以 `autoCodeSplitting` 延遲載入，路由第一次渲染要 930～1006 ms，超過 `findBy` 預設的 1000 ms；以 `beforeAll` 呼叫 `router.loadRouteChunk` 先載入路由後連跑 10 次全過。A 的檔案是否同因未查證：在該檔加同樣的預先載入後連跑 10 次即可確認。不是本 Story 造成。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-tournament-integration.md`
  summary: A 的 `frontend/tests/unit/login.test.tsx`（「有 redirect：登入後回到原頁（包含查詢參數）」，找不到標題「帳號資料」）與 B 的 `frontend/tests/unit/tournament-pages.test.tsx`（「標題列、總覽分頁與賽事資訊；未登入也能看」）也會偶發失敗；可能和上一項同一個原因，要請 A、B 各自確認（medium，未證實）。
  evidence: 2026-11-02 story/3-1 合併 origin/main（含 #29、#13、#12）後，前端全部單元測試跑 1 次，這兩個測試各失敗 1 次；只重跑這兩個檔 3 次，`login.test.tsx` 失敗 1 次、其他全過，`main` 最近 4 次 CI 都通過。兩個測試失敗的都是「進入另一個路由後第一次 `findBy`」。不是本 Story 造成；確認方法同上一項。

## Deferred from: spec-5-2-forfeit-rules.md (2026-10-30)

- source_spec: `_bmad-output/implementation-artifacts/spec-5-2-forfeit-rules.md`
  summary: Story 5.2 第二階段尚未實作：第一階段只有 `competition/forfeit.py` 的純函式（`judge_forfeit`、`appeal_deadline`），還沒有 worker 工作、資料寫入、事件與畫面，所以逾時後實際上不會判棄權。
  evidence: 依賴 D 的 4.1（Match 資料表、`lock_match`、`transition_match`）與 5.1（`list_forfeit_due`、`list_check_ins`），兩者尚未合併。合併後在 competition 新增檔案完成以下範圍（不修改 D 的 `service.py` 既有函式）：
    - worker 工作：用 `list_forfeit_due` 選場次，`lock_match` 後以 `list_check_ins` 與賽事狀態重新呼叫 `judge_forfeit`；有結果時寫入 outcome、勝隊、wins 與 `appeal_deadline(decided_at=現在, appeal_minutes=賽事申訴時限)`，`submitted_by` 留空，再用 `transition_match` 轉為申訴期。重複執行沒有副作用。
    - 操作紀錄以 `app.core.audit.record()` 記 actor 為 system；發出判棄權事件（期中只發不通知）。
    - S4 顯示哪一隊棄權（雙方棄權時兩隊都標示）與申訴期倒數。
    - 確認 D 的場次狀態轉換表允許「待開打 → 申訴期」；若不允許，請 D 在轉換表新增，不由 5.2 修改。

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

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: `confirm_walkover` 不檢查空缺方是否真的確定不會有隊伍，6.5 呼叫前要自己確認（未驗證，若為真屬 medium）。
  evidence: Edge Case Hunter：空缺方的來源場次還沒定案時就以輪空確認，來源的勝隊之後會發現下一場已定案而被丟掉。要確認 6.5 的呼叫時機，或在 `confirm_walkover` 用 progression 的來源推導擋下。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-5-confirm-advance.md`
  summary: 6.2 更正已結束賽事或季軍賽已開打後的準決賽時，`VoidMatch`、名次與賽事狀態怎麼處理還沒定（未驗證，若為真屬 medium）。
  evidence: `_void` 只能從待開打轉 voided；`_finish` 對已結束的賽事不再動作，但名次從場次重算，會和 `tournament.podium` 操作紀錄不一致。6.2 實作時要決定規則並補測試。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-8-public-match-api.md`
  summary: （低）賽事取消後，停在申訴期或申訴中的場次，公開單場 API 仍會回傳 `appeal_deadline`，但 worker 已不再自動確認（未驗證，若為真屬 low）。
  evidence: 2026-10-31 公開單場 API 審查（Edge Case Hunter、Blind Hunter）。期中不能取消賽事（2.6 擱置），已結束的賽事也不會有停在申訴期的場次，所以目前不會發生。2.6 實作取消時，要決定公開頁對這類場次顯示什麼，並在 `get_public_match` 加上賽事狀態判斷。
- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-panel.md`
  summary: （中）前端單元測試在容器冷啟動時不穩定：`login`、`signup`、`account`、`auth`、`forgot-password` 等走路由的舊測試，在 frontend 容器裡第一次執行會有 4～32 個因等不到元素（預設 1 秒）失敗，同一個容器第二次執行全部通過。CI 若遇到機器忙碌也可能偶發失敗。
  evidence: 2026-10-29 在沒有任何前端改動的分支（story/5-5）上重現：第一次 14 failed／162，第二次 162 passed；與本 Story 的新測試無關。可能的修法：路由測試的 `findBy*` 加長 timeout，或在 `vitest.config.ts` 設 `testTimeout`／預先載入路由，修好後以冷啟動連跑多次確認。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （中）6.2「重新比賽」把場次從申訴中轉回待開打時，舊的報到紀錄還在，會讓重賽回 `ALREADY_CHECKED_IN`，且兩隊都有紀錄時 `list_forfeit_due` 永遠不會選到它（未驗證，若為真屬 medium）。
  evidence: 2026-11-01 5.1 第二階段審查（Edge Case Hunter）。FR-31 規定重新比賽要清除報到紀錄、依新時間重新起算棄權期限。6.2 實作時需要 competition 提供清除報到紀錄的公開函式（由 D 新增），並在轉回待開打後呼叫 `start_forfeit_clock`。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （低）報到只鎖場次、讀賽事狀態不加鎖；2.6 做取消賽事時，取消與報到同時發生可能寫入一筆已取消賽事的報到紀錄。
  evidence: 2026-11-01 5.1 第二階段審查（Blind Hunter、Edge Case Hunter）。期中不能取消賽事（2.6 擱置），所以目前不會發生。2.6 實作時改成先 `lock_tournament` 再 `lock_match`（AD-6 順序），或由取消流程鎖住所有場次。

- source_spec: `_bmad-output/implementation-artifacts/spec-5-1-check-in-backend.md`
  summary: （低）兩隊同時報到只以先後兩次請求與唯一鍵測試，沒有在兩條真實資料庫連線上測併發。
  evidence: 測試環境所有 session 共用同一條連線與交易，無法製造真正的併發。若之後測試架構支援多連線，補一個兩隊同時 POST 的測試。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-schedule-rules.md`
  summary: 4.3 第二階段的改時間 service 呼叫 `reschedule_window`／`check_reschedule` 時，準決賽的 `next_match_at` 要傳決賽與季軍賽中較早的那一場。
  evidence: A 在 #5 的審查：8 強 10:00、準決賽 12:00、決賽 16:00、最小間隔 85 分，先把季軍賽改到 14:00、再把準決賽改到 13:00 都會被允許，但準決賽最早 14:25 才結束。`schedule.py` 只收一個 `next_match_at`，規則（不晚於兩隊要去的下一場）要由呼叫端選對場次；docstring 已註明。
- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-public-tournament-pages.md`
  summary: Story 2.4 第二階段：S1、S2 的狀態改用 1.7 的 `StatusBadge`（開放報名、進行中 live＋進行中脈動、賽程已公布 brand、已取消 destructive、其餘 muted-foreground）；S1 頂部「想辦賽事？申請成為主辦方」Page banner（已登入、非主辦方、沒有待審核申請；可關閉，存 `localStorage`，連到 `/organizer/apply`）；S1 空狀態對主辦方另顯示「建立賽事」（連到 2.2 第二階段的 S26）。
  evidence: 2026-11-02 使用者決定 2.4 拆兩階段：`StatusBadge`、申請 API 在 A 的 1.7（PR #10），主辦方身分在 1.8（PR #11），兩者都未合併。
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
- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-create-team-entry.md`
  summary: 前端單元測試的偶發逾時擴及更多檔案：D 的 `match-route.test.tsx`（第一個測試最常失敗，單獨跑該檔也會失敗）、A 的 `identity-switcher.test.tsx`、`organizer-apply.test.tsx`；全部一起跑時一次最多 9 個失敗，CI 可能因此失敗（medium）。
  evidence: 2026-11-03 story/3-1 合併 #19 後在本機容器跑前端全部單元測試：第一次 9 個失敗、第二次 1 個；只跑這 5 個檔仍有 `match-route` 1 個失敗。失敗的都是路由第一次渲染時的 `findBy`。可能和上面兩項同一個原因（路由以 `autoCodeSplitting` 延遲載入，第一次轉譯超過 1000 ms），本機只在 `team-pages.test.tsx` 證實過；比較根本的修法是在共用的測試設定預先載入所有路由，或調高 `asyncUtilTimeout`，但那是共用設定，要組員一起決定。
- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-create-team-and-invite-members.md`
  summary: 3.3 送出報名時，`join_team`（service.py:328）與 `_invite_status`（service.py:196）要補檢查報名狀態仍是 `forming`；否則已送出的隊伍仍可透過邀請連結加入，S19 預覽也會顯示連結有效（medium）。
  evidence: 2026-11-02 A 在 PR #23 的審查。3.1 只有 `forming` 狀態，目前不會出錯；epic-3-context 規定「送出報名後名單鎖定、邀請連結失效」。
- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-bracket-page.md`
  summary: S2 在「賽程已公布」「進行中」時應以「對戰表」為預設分頁（epics 4.6 AC、EXPERIENCE.md 狀態表），4.6 第二階段沒有做；目前 `/tournaments/$tournamentId` 固定顯示總覽，觀眾要自己點「對戰表」。
  evidence: 2026-11-03 使用者決定（spec Decisions 1A）交給 B 決定做法。「總覽」分頁本身連到 `/tournaments/$tournamentId`，直接導向會讓總覽點不回去。可行做法：總覽改用新網址（例如 `/overview`），`/tournaments/$tournamentId` 依狀態導向 `/bracket` 或總覽；或 S1 列表在這兩個狀態直接連到 `/bracket`（外部分享連結仍落在總覽）。兩者都要改 B 的 `TournamentPage`／`TournamentTabs`／`TournamentList`。
