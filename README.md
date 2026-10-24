# FLOW 電競賽事管理平台

模組化單體（modular monolith）：一個 FastAPI 後端（六個業務模組＋共用核心＋worker）與一個 React 前端，全部由 `docker compose` 在本機一鍵啟動。

## 範本來源

以 [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) 的 master 分支為起點：

- commit：`b1125d8839482cb7bbae603ddc6d0081bf87532e`（2026-10-15）
- 已移除：反向代理與資料庫管理介面兩個服務、覆寫與部署用的 compose 檔、雲端部署設定、GitHub Actions、錯誤監控、端對端測試服務、Email 範本套件，以及範本的登入、註冊、使用者管理與 Items 示範功能；只剩一個 `compose.yml`。
- 範本以 MIT 授權釋出，原著作權聲明保留在 [`LICENSE`](./LICENSE)。

## 需要的工具

只需要 Docker（含 Docker Compose v2.23 以上）。本機不必安裝 Python、uv 或 Bun；所有指令都在容器裡執行。

## 啟動

```bash
cp .env.example .env          # 第一次啟動前複製設定檔，依需要修改
docker compose up -d --build --wait
```

啟動時 backend 會先執行資料庫遷移（`alembic upgrade head`），再依 `.env` 的 `FIRST_ADMIN_EMAIL`／`FIRST_ADMIN_PASSWORD` 建立第一個平台管理員；同一個 Email 已存在時直接略過、不覆寫。

| 服務 | 說明 | 網址／埠號 |
| --- | --- | --- |
| `frontend` | React SPA（Vite dev server） | http://localhost:5173 |
| `backend` | FastAPI，API 文件在 `/docs` | http://localhost:8000 |
| `worker` | 輪詢到期工作與 outbox（與 backend 共用 image） | — |
| `db` | PostgreSQL 18（只綁 127.0.0.1） | 127.0.0.1:5432 |
| `mailpit` | 本機收信（只綁 127.0.0.1） | http://127.0.0.1:8025 |

健康檢查：

```bash
curl -i http://localhost:8000/api/v1/utils/health-check   # 200，內容為 true
```

開發時想讓修改自動同步進容器，改用：

```bash
docker compose up --build --watch
```

backend 與 frontend 會即時同步程式碼；worker 同步後自動重啟；`pyproject.toml`、`uv.lock`、`package.json`、`bun.lock` 變動時重建 image。

停止：`docker compose down`（加上 `-v` 會一併刪除資料庫與上傳檔案的 volume）。

## 註冊與寄信

在 http://localhost:5173/signup 註冊後，worker 會在下一輪輪詢（`WORKER_POLL_SECONDS`，預設 20 秒）把驗證信寄到 Mailpit，在 http://127.0.0.1:8025 打開信、點「驗證 Email」即可完成驗證。寄信失敗會記錄在 `email_delivery`（`attempts`、`last_error`），之後的輪詢再試，第 5 次仍失敗就標為 `failed`。

學校清單的初始資料來自政府資料開放平臺的教育部「[大專校院名錄](https://data.gov.tw/dataset/6091)」（CSV：`https://stats.moe.gov.tw/files/opendata/u1_new.csv`），於 2026-10-24 下載，取最新的 115 學年度、只取校名，共 139 所，由 Story 1.3 的遷移檔載入。

## 測試與檢查

```bash
# 後端測試：連線 compose 裡的 PostgreSQL 18，使用獨立的 <POSTGRES_DB>_test 資料庫
docker compose exec backend bash scripts/test.sh
# 額外參數會傳給 pytest，例如只跑操作紀錄的測試
docker compose exec backend bash scripts/test.sh -k audit

# 後端靜態檢查：mypy、ty、ruff check、ruff format --check
docker compose exec backend bash scripts/lint.sh

# 前端型別檢查與建置
docker compose exec frontend bun run --filter frontend build

# 前端 lint／格式檢查
docker compose exec frontend bunx biome check

# 前端單元測試（Vitest＋jsdom，tests/unit/）
docker compose exec frontend bun run test:unit
```

測試不會寫入開發用資料庫：每個測試包在一個外層交易裡並在結束時回滾；`<POSTGRES_DB>_test` 在每次測試開始時刪除重建並跑完遷移。

## 重新產生前端 API client

後端 API 有變動時，重新產生 `frontend/src/client`（前端只能透過這份 client 呼叫 API）：

```bash
bash scripts/generate-client.sh
```

這支腳本只需要 Docker：先在 backend image 裡用目前的 `backend/app` 匯出 OpenAPI 規格，再到 frontend image（Bun 1.4）裡執行 `openapi-ts` 與 Biome 格式化，最後把結果寫回 `frontend/src/client`。在 Windows 請用 Git Bash 執行。

## 專案結構

```text
backend/app/
  core/            # config、db（session）、clock、errors、audit、security
  modules/         # identity、tournaments、registration、competition、disputes、notifications
                   # 每個模組都有 router.py、service.py、repository.py、models.py
  worker/          # python -m app.worker：每 WORKER_POLL_SECONDS 秒執行一輪工作
  alembic/         # 資料庫遷移（每個 Story 一支）
backend/tests/     # core/、identity/、worker/ ……鏡射後端模組
frontend/src/
  routes/          # TanStack Router 檔案路由（頁面）
  features/<模組>/  # 元件與 hooks，名稱與後端模組一致
  client/          # 由 scripts/generate-client.sh 產生，不要手改
compose.yml · .env.example
```

架構約束見 `_bmad-output/planning-artifacts/architecture/` 的架構骨幹文件，重點如下：

- 一個使用案例一個交易：只有 router（或 worker 的每個工作）能 `session.commit()`；service 與 repository 不得 commit 或 rollback，session 依賴也不會自動 commit。
- 後端取得目前時間一律呼叫 `app.core.clock.now()`（UTC）；測試以 `frozen_clock` fixture 凍結或推進時間。
- 業務錯誤拋 `BusinessError("UPPER_SNAKE", "繁中訊息", status_code=4xx)`，回應為 `{"detail": {"code": ..., "message": ...}}`。
- 操作紀錄只能用 `app.core.audit.record()` 新增；資料庫 trigger 拒絕 UPDATE、DELETE 與 TRUNCATE。
- 狀態與類型一律用英文 `StrEnum`，放在擁有它的模組的 `models.py`。

## 版本鎖定

- 後端：根目錄 `uv.lock`（uv workspace，成員為 `backend`）。
- 前端：根目錄 `bun.lock`（Bun 1.4，`package.json` 的 `packageManager` 固定版本）；一律用 Bun 安裝套件，不要用 npm，也不要產生 npm 的鎖定檔。
- 兩個鎖定檔都進版本控制；`.env` 不進版本控制，只提交 `.env.example`。
