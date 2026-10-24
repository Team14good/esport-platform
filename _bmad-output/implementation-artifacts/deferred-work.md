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
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-official-template-project-skeleton.md`
  summary: `core/security.py` 的 `create_access_token` 與 `verify_password` 沒有任何測試，coverage 也沒有設 `fail_under` 門檻。
  evidence: 2026-10-24 Story 1.1 Code Review（Blind Hunter）。JWT 到 Story 1.4 才會使用；1.4 實作登入時一併補上這兩個函式的測試（`exp` 以 `clock.now()` 計算），並決定是否在 `[tool.coverage.report]` 設門檻。
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-flow-frontend-shell-and-theme.md`
  summary: 頂欄與手機選單的「登入」仍是一般 `<a href="/login">`，每次點擊會整頁重新載入，清掉 React Query 快取與頁面狀態。
  evidence: 2026-10-24 Story 1.2 Code Review（Blind Hunter）。`/login` 路由要到 Story 1.4 才存在；1.4 建立登入頁後，把 `frontend/src/components/layout/TopBar.tsx` 的「登入」改成 `<Link to="/login">`（「註冊」已在 1.3 改好）。
