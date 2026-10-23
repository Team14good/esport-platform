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
