---
title: 'Story 1.1：以官方範本建立可一鍵啟動的專案骨架'
type: 'feature'
created: '2026-10-23'
status: 'done'
baseline_commit: 'NO_VCS'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 專案目前只有文件、沒有程式碼；組員需要一個符合架構骨幹（AD-1、5、9、11、13、16、17）的共同起點，之後每個 Story 都在上面開發。

**Approach:** 以 `fastapi/full-stack-fastapi-template` master 為來源，移除部署與範本示範功能，重組成模組化單體骨架：五個 compose 服務、core 共用介面、六個業務模組空殼、空的 worker 迴圈、第一個平台管理員，以及連真 PostgreSQL 18 的測試。

**Decisions（2026-10-23 使用者決定）：**
- 版本控制：在專案根目錄 `git init` 並設好 `.gitignore`，**不建立任何 commit**；第一個 commit 由使用者自己做。
- 範本既有的登入、註冊、使用者管理、Items 的 API 與頁面**全部移除**，只留健康檢查 API 與顯示後端狀態的首頁；登入與註冊由 1.3、1.4 重做。
- spec 超過 1,600 tokens，使用者選擇保留完整 spec、不拆分。

## Boundaries & Constraints

**Always:**
- `compose.yml` 是唯一的 compose 檔，只有 `db`（`postgres:18`）、`backend`、`worker`、`frontend`、`mailpit`；`docker compose up` 自動跑遷移並建立第一個平台管理員。
- Bun 固定 1.4（image tag 與根 `package.json` 的 `packageManager`），只有根目錄 `bun.lock`；後端只有根目錄 `uv.lock`。兩個鎖定檔都依實際安裝的版本重新產生。
- service／repository 不 commit；session 依賴不自動 commit，由 router 明確 `session.commit()`。
- 後端取得時間只經 `core.clock.now()`（UTC aware）；列舉一律英文 `StrEnum`，放在擁有它的模組的 `models.py`。
- 保留範本 `LICENSE`（MIT 授權要求保留原著作權聲明）與 `.gitattributes`（`*.sh` 必須是 LF，Windows 主機才不會壞掉）。
- 介面文字、README、程式註解用繁體中文；程式碼、資料庫值、錯誤代碼用英文。

**Never:**
- 不保留 Traefik、adminer、`compose.override.yml`、`compose.deploy.yml`、FastAPI Cloud 設定、`.github/`、Sentry、playwright 服務、`packages/react-email`。
- 不建 School、AccountToken、OutboxEvent、Notification、OrganizerApplication 表，也不寫 `events.publish`、`authz`、`storage`（屬 1.3 之後的 Story）。
- 不用 SQLite，也不讓測試寫入開發用資料庫。
- 不提交 `.env`；不產生 `package-lock.json`；不修改 `_bmad/`、`_bmad-output/`（本 spec 除外）、`.claude/`、`docs/`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 健康檢查 | `GET /api/v1/utils/health-check`（無結尾斜線） | 200，body `true` | N/A |
| 業務錯誤 | 端點拋 `BusinessError("SAMPLE_CODE", "繁中訊息", status_code=409)` | 409，`{"detail":{"code":"SAMPLE_CODE","message":"繁中訊息"}}` | 未指定 status_code 時為 400 |
| 首位管理員不存在 | `FIRST_ADMIN_EMAIL` 不在 account 表 | 建立帳號：`is_platform_admin=true`、`email_verified=true`、`display_name="平台管理員"`、密碼存雜湊 | N/A |
| 首位管理員已存在 | 同 Email 已存在（含被改過密碼） | 略過，不覆寫任何欄位 | N/A |
| 操作紀錄不可改 | 對 `audit_log` 執行 UPDATE 或 DELETE | 資料庫拒絕並拋錯 | trigger 拋例外 |
| 未提交的寫入 | 端點寫入資料但 router 未 commit | 請求結束後資料不存在 | session 關閉即回滾 |
| worker 單筆失敗 | 兩個工作，第一個拋例外 | 第一個回滾並記錄日誌，第二個照常提交，迴圈繼續 | 例外不中斷迴圈 |
| 時鐘凍結 | 測試把時鐘設為 T | `clock.now() == T` 且帶 UTC 時區 | N/A |

</frozen-after-approval>

## Code Map

來源範本（master，取回時記錄完整 commit SHA）的重點與處置：
- `compose.yml`、`compose.override.yml`、`compose.deploy.yml` -- 合併成單一 `compose.yml`；範本沒有 frontend、worker 服務，prestart 已不是服務（`backend/scripts/prestart.sh`：`alembic upgrade head` → `python app/initial_data.py`）。
- `backend/Dockerfile` -- 第一階段用 `oven/bun:1` 建前端並複製進後端，要移除；保留 `python:3.14` + uv `sync --frozen`（含 dev 依賴，供容器內跑 pytest）。
- 根 `pyproject.toml`（uv workspace，members=["backend"]）、根 `uv.lock`、根 `package.json`（workspaces `frontend`、`packages/*`）、根 `bun.lock` -- 保留 workspace 結構，移除 `packages/*`。
- `backend/app/core/config.py` -- 讀 `../.env`；`DATABASE_URL` 驗證器改寫成 `postgresql+psycopg://`；`FIRST_SUPERUSER*` 改名為 `FIRST_ADMIN_EMAIL`／`FIRST_ADMIN_PASSWORD`；刪 `SENTRY_DSN`；新增 `WORKER_POLL_SECONDS`（預設 20，限 15～30）。
- `backend/app/core/db.py` -- `init_db` 改為建立首位管理員；`backend/app/api/deps.py` 的 `get_db`（只 yield、不 commit）移到 `core/db.py` 成為 `get_session`／`SessionDep`。
- `backend/app/core/security.py` -- 保留（pwdlib argon2 雜湊；JWT 留給 1.4）。
- `backend/app/main.py` -- 移除 `app.frontend(...)`、Sentry、`private` router；註冊 `BusinessError` handler；CORS 只允許 `FRONTEND_HOST`。
- `backend/app/api/routes/utils.py` -- health-check 改為無結尾斜線（有斜線時 FastAPI 會回 307）。
- 刪除：`backend/app/{models,crud,utils}.py`、`email-templates/`、`api/routes/{items,login,private,users}.py`、`alembic/versions/` 五支範本遷移、對應測試與 `tests/utils/`。
- `backend/app/alembic/env.py` -- `target_metadata` 改為匯入 core 與六個模組的 models。
- `backend/tests/conftest.py` -- 範本直接用開發資料庫並在結束時刪資料，要改寫。
- `frontend/vite.config.ts` -- `outDir` 改回預設 `dist`；`frontend/openapi-ts.config.ts`（輸入 `./openapi.json`、輸出 `src/client`、axios client、sdk byTags）保留。
- `frontend/src/main.tsx` -- 移除 localStorage token 與 401→`/login`；保留 QueryClient 與 router。`components/ui/`、`lib/utils.ts`（shadcn）保留，其他 `components/*`、`hooks/`、路由與 playwright 規格刪除。
- `scripts/generate-client.sh` -- 範本版需要本機 uv 與 bun；本機沒有 bun，要改成只需 Docker。
- 規劃依據：`ARCHITECTURE-SPINE.md` AD-5:88、AD-9:114、AD-11:129、AD-13:141、AD-16:162、AD-17:168、慣例表:198-212、骨架:291-308；列舉值 `docs/midterm/D-物件設計文件.md:725-742`；AUDIT_LOG／ACCOUNT 欄位 `docs/midterm/B-軟體需求分析文件.md:716-728、1032-1046`。

## Tasks & Acceptance

**Execution:**
- [x] 範本取回 -- `git clone --depth 1` 到 scratchpad，記錄完整 SHA，排除 Never 清單、`.git`、`.agents/`、範本 `.claude/`、`.vscode/`、`img/`、`hooks/`、`.pre-commit-config.yaml`、`.env`、`frontend/.env`、`Dockerfile.playwright`、發版腳本、`development.md`、`deployment*.md`、`release-notes.md`、`CONTRIBUTING.md` 後複製到專案根目錄 -- 只帶進需要的部分。
- [x] `compose.yml` -- 五個服務；db 健康檢查 + `app-db-data`；backend 先跑 prestart 再 `fastapi dev`、healthcheck 打無斜線路徑、掛 `uploads` volume；worker 用同一個 image 跑 `python -m app.worker`，依賴 backend healthy；frontend 跑 Vite dev server；mailpit 固定 tag；埠號 5432、8000、5173、8025；backend 與 frontend 設 `develop.watch` -- AD-17。
- [x] `backend/Dockerfile`、`frontend/Dockerfile`（新）、`.dockerignore` -- 前端用 `oven/bun:1.4`，以根目錄為 build context、`bun install --frozen-lockfile`。
- [x] 根 `package.json`、`bun.lock`、`pyproject.toml`、`backend/pyproject.toml`、`uv.lock` -- 移除 sentry-sdk、react-email 與發版工具依賴，在 Bun 1.4／uv 容器或本機 uv 重新產生鎖定檔。
- [x] `backend/app/core/{config,db,clock,errors,audit}.py` -- 依 Code Map 與 Design Notes。
- [x] `backend/app/modules/{identity,tournaments,registration,competition,disputes,notifications}/` -- 各有 `__init__`、`router`（空的 `APIRouter`）、`service`、`repository`、`models`；identity 的 `Account`（id、email unique、hashed_password、email_verified、display_name、is_platform_admin、is_organizer、created_at；`school_id` 留給 1.3）；全部列舉依 Design Notes。
- [x] `backend/app/{main,initial_data}.py`、`api/`、`scripts/prestart.sh` -- 匯入各模組 router、移除範本功能、首位管理員冪等建立。
- [x] `backend/app/alembic/` -- 刪範本遷移，新增一支遷移：`account`、`audit_log`、索引 `(tournament_id, at)`、拒絕 UPDATE／DELETE 的 trigger。
- [x] `backend/app/worker/` -- `__main__.py` 進入點；`run_once(jobs)` 每個工作一個 session／交易；收到 SIGTERM 後跑完本輪再結束；1.1 的工作清單為空。
- [x] `backend/tests/` -- 改寫 conftest，新增 `tests/core/`、`tests/identity/`、`tests/worker/`，涵蓋 I/O 矩陣每一列，以及「六個模組各有四個檔案」的結構測試。
- [x] `frontend/src/` -- `routes/__root.tsx`、`routes/index.tsx`（FLOW 字樣 + 透過產生的 client 與 TanStack Query 顯示後端狀態）、`features/<六個模組>/.gitkeep`；重新產生 `src/client`。
- [x] `scripts/generate-client.sh` -- 從 backend 容器匯出 `openapi.json`，再於 Bun 1.4 容器執行 `generate-client` 與 Biome 格式化。
- [x] `.env.example`、`.gitignore`、`README.md` -- 列出所有變數與預設值；忽略 `.env`、`node_modules`、`dist`、coverage；README 寫啟動、測試、重新產生 client 的指令與範本來源 SHA。
- [x] 專案根目錄 -- `git init`（不 commit），確認 `git status` 中 `.env` 被忽略、`bun.lock`、`uv.lock`、`.env.example` 可被追蹤。

**Acceptance Criteria:**
- Given 只複製了 `.env.example` 為 `.env`，when 執行 `docker compose up -d --wait`，then 五個服務都在執行，且 `curl -i http://localhost:8000/api/v1/utils/health-check` 回 200。
- Given 專案根目錄，when 執行 `docker compose config --services`，then 恰好列出五個服務；全專案找不到 `traefik`、`adminer`、`package-lock.json`。
- Given backend 重啟兩次，when 查 account 表，then 只有一個平台管理員。
- Given 服務已啟動，when 瀏覽 `http://localhost:5173`，then 首頁顯示 FLOW 與「後端狀態：正常」，畫面沒有範本的 Items 或使用者管理。
- Given 已產生的 client，when 再執行一次重新產生指令，then `frontend/src/client` 沒有差異。

## Implementation Notes

- 範本來源：`fastapi/full-stack-fastapi-template` master，commit `b1125d8839482cb7bbae603ddc6d0081bf87532e`（2026-10-15）；已寫入 README。
- 與 Code Map 不同之處：
  - 首位管理員不放在 `core/db.py` 的 `init_db`：AD-3 規定 core 不得 import 模組。改為 `identity.service.ensure_first_admin()`（只 add/flush），由 `app/initial_data.py` 開交易並 commit；`prestart.sh` 改用 `python -m app.initial_data`。
  - `fastapi[standard]` 改為 `fastapi[standard-no-fastapi-cloud-cli]`：sentry-sdk 會經由 fastapi-cloud-cli 間接進入 `uv.lock`，換 extra 後 lock 中已沒有 sentry-sdk 與 fastapi-cloud-cli。
  - 保留 `frontend/src/components/theme-provider.tsx` 與 `hooks/useMobile.ts`：保留的 `ui/sonner.tsx`、`ui/sidebar.tsx` 依賴它們，刪除會讓 tsc 失敗。
  - `frontend/biome.json`：`src/client` 不再排除在 `files.includes` 外，改用 override 停用 linter 與 assist，Biome 才會格式化產生的 client；另排除 `openapi.json`。
  - `app/modules/__init__.py` 匯入六個模組的 models：`audit_log.actor_id → account.id` 是字串外鍵，實測在沒有載入 identity models 的程序（例如 worker）flush AuditLog 會拋 `NoReferencedTableError`；worker、alembic env.py 都改為匯入 `app.modules`。
- 補強：audit trigger 為 statement-level，並一併拒絕 TRUNCATE；`BusinessError` 檢查 code 為 UPPER_SNAKE、status 為 4xx；`audit.record()` 先把 before/after 轉成 JSON 可序列化值；`backend/Dockerfile` 複製 `backend/tests`，不開 watch 也能在容器跑 pytest。
- 一併移除（未列在 Never，但只服務範本 CI 或已刪功能）：根目錄 `scripts/test.sh`、`scripts/test-local.sh`（會 `down -v`）、`backend/scripts/tests-start.sh`、backend 與 frontend 各自的 README 與 `.dockerignore`（build context 是根目錄，用不到）、`frontend/src/utils.ts`、`frontend/public/` 的範本圖示。保留 `@playwright/test` 依賴與精簡後的 `playwright.config.ts`，供之後 `frontend/tests/` 使用。
- 鎖定檔：`uv.lock` 在 `python:3.14` 容器以 uv 0.9.26（與 Dockerfile 同版）產生；`bun.lock` 在 `oven/bun:1.4`（1.4.4）容器產生。Bun 不會更新 lock 裡根 workspace 的名稱，已手動由範本的 `fastapi-cloud` 改為 `flow`，並確認 `bun install --frozen-lockfile` 通過、再次 install 後 lock 不變。
- 範本在 Windows checkout 後為 CRLF，已全部轉為 LF（Biome 會把 CRLF 判為格式錯誤）。
- 驗證環境：主機的 5432、8000 被另一個專案（codefest2026）的容器占用，本次以 scratchpad 裡的暫時 override（`ports: !override`，對應 15432、18000，`VITE_API_URL=http://localhost:18000`）驗證；`compose.yml` 仍是規格的 5432、8000。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter = BH、Edge Case Hunter = EC、Verification Gap = VG）。

| # | 來源 | 發現 | 判定 | 依據 | 去向 |
|---|------|------|------|------|------|
| 1 | VG | `initial_data.init()`（唯一 commit 首位管理員的地方）沒有測試 | medium | 測試只呼叫 service；刪掉 `initial_data.py` 的 `session.commit()` 不會有測試失敗 | patch P1 |
| 2 | BH | 同上（init 寫死 `Session(engine)` 無法測） | medium | 同 #1 | patch P1 |
| 3 | VG | worker 進入點沒有測到 `install_signal_handlers()` | medium | 測試自己呼叫該方法；Python 為 PID 1 時沒有 handler，SIGTERM 不會送達，變成被 SIGKILL | patch P2 |
| 4 | VG | 睡眠中收到停止要求的行為沒有測試 | low | 現有測試在本輪內送 SIGTERM 或 `poll_seconds=0`，`_sleep` 改成整段睡也不會失敗；補測試不增加程式複雜度 | patch P3 |
| 5 | VG | 非開發環境拒絕 `changethis` 的檢查沒有測試 | medium | `test_config.py` 只測 `WORKER_POLL_SECONDS`；`raise` 改成 `warn` 無測試失敗 | patch P4 |
| 6 | BH | `_enforce_non_default_secrets` 與 `_use_psycopg_driver` 沒有測試 | medium（secret 部分）／false（driver 部分） | secret 部分同 #5；driver 改寫若失效，所有連 DB 的測試都會失敗（lock 中沒有 psycopg2），已間接驗證 | patch P4 |
| 7 | VG | 首頁「後端狀態：正常」只靠手動瀏覽驗證 | medium | `frontend/tests/` 沒有規格；Never 移除了 playwright 服務，目前沒有可執行的 e2e 環境 | defer D1 |
| 8 | BH | 前端沒有自動化測試，`bun run test` 回「No tests found」 | low | 同 #7 的根因（尚無 e2e 規格） | defer D1 |
| 9 | VG | `list_for_tournament` 只依 `at` 排序，同時間多筆順序不定 | medium | `frozen_clock` 下所有紀錄 `at` 相同；uuid4 不能當次序；AD-9 查閱依賴順序 | patch P5 |
| 10 | BH | 同上 | medium | 同 #9 | patch P5 |
| 11 | EC | 同上 | medium | 同 #9 | patch P5 |
| 12 | BH | `.gitattributes` 的 `* text=auto` 在 `core.autocrlf=true` 下 checkout 成 CRLF，Biome 檢查失敗 | medium | 本機 git 已出現「LF will be replaced by CRLF」警告；Implementation Notes 記錄 Biome 會把 CRLF 判為錯誤；組員都在 Windows | patch P6 |
| 13 | BH | compose 強制 `FASTAPI_ENV=development`，`.env.example` 卻寫「正式環境必須更換」 | low | `${FASTAPI_ENV:-development}` 加上 `Literal["development"] \| None`，compose 下無法宣告非開發環境；AD-17 也沒有正式環境，註解誤導 | patch P7 |
| 14 | BH | db（5432，預設密碼）與 mailpit（8025）綁在 0.0.0.0，整個區網都能連 | medium | Docker 發布埠預設綁所有介面；1.3 起 mailpit 會收到重設密碼連結 | patch P8 |
| 15 | BH | `.dockerignore` 的 `.env` 只比對根目錄，`frontend/.env` 會被打包進 image | low | Docker 的比對以 context 根目錄為準；組員為 Vite 建立 `frontend/.env` 很常見；直接改規則即可 | patch P9 |
| 16 | BH | 同 Email 的非管理員帳號已存在時，log 仍寫「已存在」 | low | 1.1 沒有註冊功能，碰不到；要修需要多一個分支 | reject |
| 17 | EC | 同上 | low | 同 #16 | reject |
| 18 | BH | `test_template_features_are_removed`（路徑恰好只有健康檢查）與 `test_story_1_1_has_no_jobs` 鎖死 1.1 現況 | low | 1.3 加第一個端點或工作時一定失敗，每個 Story 都會碰到；改成斷言範本路徑不存在、刪掉 JOBS 測試 | patch P10 |
| 19 | BH | `lint.sh` 不檢查 `tests/` | low | 確實只跑 `app`；平常不會造成錯誤，加入後 mypy strict 可能要連帶修測試，不是直接修正 | reject |
| 20 | BH | 修改已套用的遷移檔後，測試資料庫不會重建 | low | conftest 只在資料庫不存在時建立；同一 Story 內修改遷移（P5 就會）會跑在舊 schema 上 | patch P11 |
| 21 | EC | 同上 | low | 同 #20 | patch P11 |
| 22 | BH | 遷移的 `downgrade()` 沒有測試 | low | 依序刪除 trigger、function、index、table，檢查無誤；往返測試會和 session 層級的測試資料庫 fixture 衝突，不是直接修正 | reject |
| 23 | BH | worker 沒有 `develop.watch`，`--watch` 時跑舊程式 | low | backend 會同步，worker 不會；加設定就好 | patch P12 |
| 24 | EC | 同上 | low | 同 #23 | patch P12 |
| 25 | BH | worker 沒有 restart 政策；`run_once` 的 rollback 再拋錯時程序會結束 | maybe-false（若成立為 medium） | 沒能證明 rollback 或 close 在斷線時會拋錯；要確認需在 job 執行中重啟 db 觀察 | defer D2 |
| 26 | EC | worker 結束後沒有重啟 | maybe-false（若成立為 medium） | 同 #25 | defer D2 |
| 27 | EC | rollback／close 拋錯會讓 worker 崩潰 | maybe-false（若成立為 medium） | 同 #25 | defer D2 |
| 28 | BH | `.env.example` 沒有列出所有變數（缺 `ACCESS_TOKEN_EXPIRE_MINUTES`；SMTP 寫死在 compose） | low | `ACCESS_TOKEN_EXPIRE_MINUTES` 確實沒傳進容器；SMTP 依 AD 固定使用 mailpit，`.env.example` 已註明，那部分不算缺漏 | patch P13 |
| 29 | BH | 前端留著未使用的範本依賴 | low | grep 確認未匯入；但 zod、react-hook-form、react-table 等 Epic 1 的表單與 Data table 會用到，現在刪掉之後又要加回來；不影響使用者 | reject |
| 30 | BH | 後端掛掉時首頁停在「檢查中」約 7 秒 | low | TanStack Query 預設重試 3 次並指數退避；加 `retry: false` 一行就好 | patch P14 |
| 31 | EC | 同上 | low | 同 #30 | patch P14 |
| 32 | BH | `account.email` 區分大小寫 | low | 1.1 只有首位管理員，要大小寫不同的 `FIRST_ADMIN_EMAIL` 才會碰到；正規化與函數索引屬於 1.3 註冊（`EMAIL_ALREADY_REGISTERED`）的範圍，1.3 會有自己的遷移 | reject |
| 33 | EC | 同上（大小寫不同時建立第二個管理員） | low | 同 #32 | reject |
| 34 | BH | `actor_id` 外鍵沒有 `ON DELETE`，帳號刪除會失敗 | false | 需求沒有硬刪除帳號；保留操作紀錄的操作者時，擋下刪除是正確的行為 | reject |
| 35 | EC | 同上 | false | 同 #34 | reject |
| 36 | EC | 兩次 prestart 同時跑，檢查與 insert 之間有競態 | false | 只有一個 backend 容器會跑 prestart，worker 不會；碰不到 | reject |
| 37 | EC | JSONB 的 `None` 存成 JSON `null` 而不是 SQL NULL | low | SQLAlchemy JSON 預設 `none_as_null=False`；讀回時仍是 None，所以測試照樣通過，但 `IS NULL` 查詢會漏掉；改成 `JSONB(none_as_null=True)` 即可 | patch P15 |
| 38 | EC | 無法辨識的雜湊格式在登入時變成 500 | false | 1.1 沒有登入端點，`verify_password` 只有測試呼叫 | reject |
| 39 | EC | 沒有 tags 的路由會讓 `route.tags[0]` IndexError | false | 所有 router 都有 tags；就算缺了也會在啟動時直接報錯 | reject |
| 40 | EC | tag 含連字號時 `methodName` 的 regex 會切錯 | false | 所有 tag 都是單一英文字，沒有連字號 | reject |
| 41 | EC | `FRONTEND_HOST` 結尾帶斜線，或用 127.0.0.1 開頁面時 CORS 失敗 | low | 屬於使用者設定錯誤，README 寫的是 localhost；要修得改成多來源清單 | reject |
| 42 | EC | `env_file="../.env"` 依 CWD 決定，不在 backend/ 執行時找不到 | low | 容器內 cwd 固定且由 compose 帶入環境變數；README 說明只需要 Docker，主機上直接跑不是支援的方式 | reject |
| 43 | EC | `POSTGRES_PASSWORD` 含 `@:/#%` 時 `DATABASE_URL` 解析錯誤 | low | compose 直接把密碼插進 URL；在 `.env.example` 加一行說明即可 | patch P16 |
| 44 | EC | 一輪超過 10 秒時，Docker 會在本輪中途 SIGKILL | false | 1.1 的 JOBS 是空的，一輪不可能超過 10 秒 | reject |
| 45 | EC | `DATABASE_URL` 沒有資料庫名稱時會建立 `None_test` | low | 設定錯誤，很少見；要修得加防護 | reject |
| 46 | EC | `test_worker_poll_seconds_must_be_between_15_and_30` 可能因其他欄位的 ValidationError 而通過 | low | 環境缺必要變數時測試會空轉通過；改成斷言錯誤位置是直接修正 | patch P17 |
| 47 | EC | `test_core_does_not_import_modules` 抓不到 `from app import modules`、相對匯入與子目錄 | low | 確實只用字串比對 `*.py`；要可靠得改用 AST 解析，組員也不太可能這樣寫 | reject |
| 48 | EC | `scripts/test.sh` 的參數被傳給 `coverage html --title`，不是 pytest | low | `-k` 之類的參數會被忽略，組員常會這樣用；改成傳給 pytest 即可 | patch P18 |
| 49 | EC | 沒設 `VITE_API_URL`（主機上直接 `bun run dev`）時請求打到 Vite | low | compose 有設；主機直接跑前端不是 README 支援的方式 | reject |
| 50 | EC | theme-provider 在 localStorage 值無效或被封鎖時出錯 | low | 原封不動沿用範本，主題由 1.2 重做；很少見，修正要加防護 | reject |
| 51 | EC | `useTheme` 的 context 防護永遠不會觸發 | low | 範本原有程式；沒有實際損害 | reject |

## Design Notes

**交易邊界**（AD-5）：

```python
@router.post("/samples")
def create_sample(session: SessionDep, body: SampleIn) -> SampleOut:
    result = service.create_sample(session, body)  # service 只 add/flush
    session.commit()                               # 只有 router 提交
    return result
```

**測試資料庫**：conftest 在同一個 PG18 上使用 `<POSTGRES_DB>_test`（不存在就建立），跑 `alembic upgrade head`，每個測試包在外層交易內並以 savepoint 模式（`join_transaction_mode="create_savepoint"`）讓 router 的 commit 不會真的落地；凍結時鐘以 fixture 提供，不 monkeypatch `datetime`。

**`core.audit`**：`record(session, *, actor_id: UUID | None, tournament_id: UUID | None, action: str, entity_type: str, entity_id: UUID, before: dict | None, after: dict | None) -> None`，`actor_id=None` 代表 system；`list_for_tournament(session, tournament_id) -> list[AuditLogRead]` 依 `at` 由舊到新。`tournament_id` 先不加外鍵，由 Story 2.2 建 Tournament 表時補上。`at` 取自 `clock.now()`。

**列舉英文值**（D:727 授權由第一個 Story 訂定的部分以 * 標示）：TokenPurpose `verify_email/reset_password`；ApplicationStatus* `pending/approved/rejected`；ScoreType `win_loss/rounds`；TournamentMode `campus/custom`；TournamentStatus `upcoming/open/closed/published/ongoing/finished/cancelled`；MemberRole `captain/player`；RegistrationStatus `forming/pending/accepted/waitlisted/rejected/withdrawn/drawn/retired/disqualified`；MatchStatus `scheduled/live/appeal_window/appealed/confirmed/voided`；MatchOutcome `played/forfeit/double_forfeit/walkover/disqualified`；AppealStatus* `open/closed`；AppealDecision* `upheld/corrected/rematch`；ReportStatus* `open/dismissed/substantiated`；DeliveryStatus* `pending/sent/failed`。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 healthy／running。
- `curl -i http://localhost:8000/api/v1/utils/health-check` -- expected: `HTTP/1.1 200`，body `true`。
- `docker compose exec backend bash scripts/test.sh` -- expected: pytest 全數通過，連線的是 PG18 的 `_test` 資料庫。
- `docker compose exec backend bash scripts/lint.sh` -- expected: mypy、ruff check、ruff format --check 都通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: tsc 與 vite build 成功。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- 連續執行兩次 `bash scripts/generate-client.sh`，比較兩次之間 `frontend/src/client` 的檔案雜湊 -- expected: 完全相同。
- `git status --porcelain --ignored` -- expected: `.env` 列為忽略（`!!`），`bun.lock`、`uv.lock`、`.env.example` 列為未追蹤（`??`），沒有任何 commit。

**Manual checks (if no CLI):**
- 瀏覽 `http://localhost:5173` 首頁顯示後端狀態正常；`http://localhost:8025` 可開啟 Mailpit。
