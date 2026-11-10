# FLOW 電競賽事管理平台

模組化單體（modular monolith）：一個 FastAPI 後端（六個業務模組＋共用核心＋worker）與一個 React 前端，全部由 `docker compose` 在本機一鍵啟動。

組員接手 Story 的流程（分支、BMAD、PR）見 [CONTRIBUTING.md](./CONTRIBUTING.md)；給 Claude 的專案規則見 [CLAUDE.md](./CLAUDE.md)。

## 範本來源

以 [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) 的 master 分支為起點：

- commit：`b1125d8839482cb7bbae603ddc6d0081bf87532e`（2026-10-15）
- 已移除：反向代理與資料庫管理介面兩個服務、覆寫與部署用的 compose 檔、雲端部署設定、GitHub Actions、錯誤監控、端對端測試服務、Email 範本套件，以及範本的登入、註冊、使用者管理與 Items 示範功能；只剩一個 `compose.yml`。
- 範本以 MIT 授權釋出，原著作權聲明保留在 [`LICENSE`](./LICENSE)。

## 需要的工具

啟動、測試與建置只需要 Docker（含 Docker Compose v2.23 以上）。本機不必安裝 Python 或 Bun，這些指令都在容器裡執行。

用 BMAD 做 Story 時，另外需要 [Claude Code](https://claude.com/claude-code) 與 [uv](https://docs.astral.sh/uv/)：BMAD 的腳本以 `uv run` 執行。

## 啟動

```bash
cp .env.example .env          # 第一次啟動前複製設定檔，依需要修改
docker compose up -d --build --wait
```

啟動時 backend 會先執行資料庫遷移（`alembic upgrade head`），再依 `.env` 的 `FIRST_ADMIN_EMAIL`／`FIRST_ADMIN_PASSWORD` 建立第一個平台管理員；同一個 Email 已存在時直接略過、不覆寫。

### 示範帳號

接著載入示範資料（`backend/app/demo_data/`），建立下列已驗證 Email 的帳號，都屬於「國立中央大學」。Email 網域來自 `.env` 的 `DEMO_EMAIL_DOMAIN`（預設 `example.com`），密碼共用 `DEMO_PASSWORD`（`.env.example` 為 `changethis`）。再次啟動不會重複建立，同一個 Email 已存在（包含已被真人註冊）時略過、不覆寫。

| 身分 | Email（預設網域） | 密碼 | 說明 |
| --- | --- | --- | --- |
| 平台管理員 | `admin@example.com` | `FIRST_ADMIN_PASSWORD` | 由 `FIRST_ADMIN_EMAIL` 設定 |
| 主辦方 | `organizer@example.com` | `DEMO_PASSWORD` | 已具主辦方身分（`is_organizer`），不必再申請 |
| 裁判 | `referee@example.com` | `DEMO_PASSWORD` | 目前只有帳號，指派到賽事待之後補上 |
| 隊長 | `captain@example.com` | `DEMO_PASSWORD` | 示範賽事「國立中央大學電競隊」的隊長 |
| 選手 | `player@example.com` | `DEMO_PASSWORD` | 「國立中央大學電競隊」的隊員 |

舊的 `.env` 沒有 `DEMO_PASSWORD` 時只建立第一個平台管理員，backend log 會提示補上設定；從 `.env.example` 補上 `DEMO_PASSWORD`、`DEMO_EMAIL_DOMAIN` 後重新啟動即可。

帳號之後接著建立《英雄聯盟》《特戰英豪》兩款遊戲（含段位對照表），以及一場 32 隊、已抽籤的校園賽「FLOW 校園盃 特戰英豪」（主辦方為上表的主辦方，開賽在啟動後 7 天）。32 隊來自 32 所學校，每隊 5 人；其他隊員的帳號是 `team02-m1@example.com` 這類格式（隊號 02～32、隊員 m1～m5，第一隊為 m3～m5），密碼同 `DEMO_PASSWORD`，方便用其他隊伍的身分操作。

**Demo 前請先清空資料庫再啟動**：`docker compose down -v && docker compose up -d --build --wait`。示範賽事的時間在第一次建立時固定；保留資料庫、超過 7 天後再啟動時會沿用已過開賽時間的賽事，抽籤會被拒絕。

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

# 前端建置（tsc 只檢查 src，加上 vite build）
docker compose exec frontend bun run --filter frontend build

# 前端型別檢查（包含 tests/ 與設定檔；build 不會檢查測試檔）
docker compose exec frontend bun run --filter frontend typecheck

# 前端 lint／格式檢查
docker compose exec frontend bunx biome check

# 前端單元測試（Vitest＋jsdom，tests/unit/）
docker compose exec frontend bun run test:unit

# 端對端測試（Playwright，tests/e2e/）：先 docker compose up -d --wait，再執行
docker compose --profile e2e run --rm e2e
# 額外參數取代預設指令，例如只跑手機版、只跑某個 Story 的測試
docker compose --profile e2e run --rm e2e bunx playwright test --project mobile-375
docker compose --profile e2e run --rm e2e bunx playwright test --grep @story-1.7
```

端對端測試在 profile `e2e` 的容器裡執行（Playwright 官方 image 加 Bun），平常的 `docker compose up` 不會啟動它，也不在 CI 裡執行：

- 每個測試以桌機（`desktop`）與 375 px 手機（`mobile-375`）各跑一次，並檢查頁面沒有橫向捲軸（只有對戰樹可以左右捲動）。
- 每次執行都註冊新的 Email，可以對同一個資料庫重複執行；驗證信從 Mailpit 取得，worker 每 `WORKER_POLL_SECONDS` 秒寄一次，身分流程約需 30～40 秒。
- 每個測試附上 `api-timings.json`（每個 API 請求的回應時間）；一般請求超過 1 秒就失敗，登入（密碼雜湊）只記錄不判定。
- 測試以 tag 標註 Story 與需求編號（例如 `@story-1.7`、`@FR-2`）。
- 完整賽事演練（`tests/e2e/tournament.spec.ts`）在關鍵步驟走畫面，32 隊的組隊報名與重複的場次走公開 API。申訴期等期限等不了真實時間，測試會直接改資料庫的期限，之後由真的 worker 處理，所以 e2e 服務需要 `E2E_DATABASE_URL`（compose 已設定）。
- HTML 報告寫到 `frontend/playwright-report/`（用瀏覽器打開 `index.html`），失敗時的截圖與 trace 在 `frontend/test-results/`。
- `tests/` 與 `playwright.config.ts` 是掛載進容器的，改測試不必重新 build；改了依賴或 `frontend/Dockerfile.e2e` 時加 `--build`。
- 測試會在資料庫留下 `e2e-*` 開頭的帳號與已核准的主辦方。不想弄髒開發用資料庫時，先停掉平常的服務，改用獨立的 compose 專案（另一組 volume）跑，跑完連同 volume 一起刪掉：

  ```bash
  docker compose down
  docker compose -p flow-e2e up -d --build --wait
  docker compose -p flow-e2e --profile e2e run --rm e2e
  docker compose -p flow-e2e down -v
  ```

每個 PR 與 `main` 的 push 都由 GitHub Actions（`.github/workflows/ci.yml`）跑上面全部項目，另外檢查 Alembic 只有一個 head、`frontend/src/client` 與後端 API 一致；範本原本的 Actions 已移除，這份是本專案自己的。

### 測試總指令與測試報告

```bash
# 依序跑單元（前端 Vitest、後端 pytest -m unit）、整合（後端 pytest -m integration）、端對端，最後產生報告
bash scripts/test-all.sh
# 略過端對端（報告註明「本次略過」）；--no-build 不重新 build 容器
bash scripts/test-all.sh --skip-e2e
```

- 預設先 `docker compose up -d --build --wait`，測到的是目前的原始碼；任何一層失敗都會跑完其餘層，最後以非 0 結束。
- 產出放在 `reports/`（已加進 `.gitignore`）：`test-report.md`（各層結果、後端覆蓋率、純函式分支覆蓋率、NFR-1 併發比對、NFR-2 回應時間、Story／FR 追溯）、`coverage/index.html`、`raw/`（JUnit、coverage.json、Playwright json、計時檔）。
- 後端每個測試檔的層級（unit／integration）與 Story、FR 寫在 `backend/tests/traceability.yaml`；新增測試檔要加一列，否則 `tests/test_traceability.py` 會失敗並列出檔名。
- `scripts/test.sh` 開啟分支覆蓋率，並要求 `allocation.py`、`bracket.py`、`schedule.py`、`progression.py` 逐檔達 90% 以上（CI 也會檢查）。

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
