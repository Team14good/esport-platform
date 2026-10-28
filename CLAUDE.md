# FLOW 電競賽事管理平台：給 Claude 的專案規則

這個專案以 BMAD 工作流程逐一實作 Story。組員的協作流程見 `CONTRIBUTING.md`，啟動與測試指令見 `README.md`。

## 溝通

- 回覆使用者一律用繁體中文；寫進專案的文件（spec、說明、程式註解）也用繁體中文。
- 介面文字全部繁體中文；按鈕用動詞＋名詞，不用「確定」「Submit」，不用驚嘆號與表情符號。

## 做 Story

- 實作 Story、修 bug 或有意義的變更時，用 `bmad-build`；看變更用 `bmad-walkthrough`；審查用 `bmad-code-review`。
- 需求來源依序是：
  1. `_bmad-output/implementation-artifacts/epic-<N>-context.md`
  2. 前一個已完成 Story 的 `spec-*.md`
  3. `_bmad-output/planning-artifacts/`（epics、PRD、架構、UX）
- spec 的 `<frozen-after-approval>` 區塊只有人能改。需求沒講清楚而會被使用者察覺的地方，要問人，不要自己假設。
- `deferred-work.md` 只新增項目，不修改既有項目；項目在本 Story 處理完時才刪除。
- 除非使用者要求，不要 commit 或 push。commit 時不要包含 `.env`；除非使用者要求，也不要包含 `docs/`。
- 使用者表達過的偏好與決定，要記錄在 spec 的 Decisions，不要只留在對話裡。

## 架構規則（細節見 `_bmad-output/planning-artifacts/architecture/` 與 README）

- 模組化單體：`backend/app/modules/{identity,tournaments,registration,competition,disputes,notifications}`＋`core`。
  - `core` 不能 import 任何模組（AD-3）。
  - 跨模組只呼叫對方 `service.py` 的公開函式。
  - 呼叫方向固定為 disputes → competition → registration → tournaments → identity。
  - 其他模組不能直接呼叫 notifications，只能發 outbox 事件。
- 帳號層級權限用 router 的 `Depends`：`identity/deps.py` 的 `CurrentAccount`、`VerifiedAccount`、`PlatformAdmin`。未登入也能呼叫的寫入 API，要加進 `identity/router.py` 的 `PUBLIC_WRITE_ROUTES`（有測試檢查）。
- 只有 router（或 worker 的每個工作）能 `session.commit()`；service、repository 不得 commit 或 rollback（AD-5）。
- 目前時間一律 `app.core.clock.now()`；跟期限有關的測試用 `frozen_clock` fixture。
- 業務錯誤：`BusinessError("UPPER_SNAKE", "繁中訊息", status_code=4xx)`，回應為 `{"detail":{"code","message"}}`；欄位錯誤是 422。
- 操作紀錄只能用 `app.core.audit.record()`，資料表只增不改（AD-9）。
- 每個 Story 的 schema 變更各自一支 Alembic 遷移檔；`tests/test_migrations.py` 會檢查遷移與模型一致。
- 前端只能呼叫 `frontend/src/client`（由 `scripts/generate-client.sh` 產生），不手寫 fetch 或 axios。
  - 頁面放 `src/routes/`，元件與 hooks 放 `src/features/<模組>/`。
  - 登入狀態與 401 處理在 `features/identity/auth.ts`。
- 測試連 compose 裡的 PostgreSQL 18，禁止 SQLite。

## 環境上的坑

- backend、frontend 容器是 build 時複製原始碼，沒有掛載。改完程式要 `docker compose up -d --build --wait` 才會測到新版。
- 只在容器裡格式化或產生檔案時，可以用 `docker compose run --rm --no-deps -T -v "<本機路徑>:/app/<服務目錄>" <服務> ...`。
  - Windows 的 Git Bash 要加 `MSYS_NO_PATHCONV=1`，路徑用 `$(pwd -W)`。
  - 產生 `routeTree.gen.ts` 要掛整個 `frontend/` 再跑 `bunx vite build`；只掛 `src/` 會出現 `EXDEV`。
- 換行一律 LF。
  - 在 Windows 用 Python 改檔要用 `open(p, "rb")`／`open(p, "wb")`，文字模式會寫成 CRLF，弄壞 `.sh` 腳本。
  - 檢查換行時用 Python 讀二進位；Git Bash 的 `grep -c $'\r'` 看不出來。
- Git Bash 的 `/tmp` 和 Windows 的 Python 看到的不是同一個資料夾；暫存檔要給兩邊共用時，用專案外的完整 Windows 路徑。
- 前端套件一律用 Bun，不用 npm。
