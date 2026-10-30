---
title: 'Story 7.1 第一階段：示範資料腳本骨架與示範帳號'
type: 'feature'
created: '2026-10-30'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '7414d3b9abd2be5aa8c64c187615a11448ad9f0b'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 全新資料庫啟動後只有第一個平台管理員，評審與組員都要手動註冊、驗證、申請主辦方才能操作；CONTRIBUTING 6.5 也要求 A 先建立共用的種子腳本，讓各模組負責人把自己的資料加進去。

**Approach:** 這是 Story 7.1 的第一階段（使用者 2026-10-30 決定）。在 backend 啟動流程（`prestart.sh` → `app.initial_data`）加入可重複執行的示範資料腳本：先建立主辦方、裁判、隊長、選手四個已驗證 Email 的示範帳號，並為 tournaments、registration、competition 留好擴充點。遊戲與段位表、32 隊、已抽籤賽事等上游 service 合併後再補（第二階段）。

## Boundaries & Constraints

**Always:**
- 示範資料只透過各模組 `service.py` 的公開函式建立；示範腳本與 `initial_data` 一樣扮演 router 角色，負責開交易與 commit。
- 每一筆示範資料先檢查是否已存在，再次啟動不重複建立、不覆寫既有欄位。
- 示範帳號的登入資訊來自 `.env`（`.env.example` 與 README 記載），程式裡不寫密碼。
- 時間一律 `core.clock.now()`。

**Never:**
- 不直接寫資料表，不新增遷移檔。
- 不建立自訂模式的賽事（期中版規則）；本階段不建立遊戲、隊伍、賽事。
- 不修改其他組員模組的既有函式。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 全新資料庫 | `.env` 有 `DEMO_PASSWORD` | 建立四個示範帳號：Email 已驗證、主辦方帳號 `is_organizer=true`、都屬示範學校 | N/A |
| 再次啟動 | 示範帳號已存在 | 略過、不改任何欄位，log 記錄略過 | N/A |
| 未設定密碼 | `.env` 沒有 `DEMO_PASSWORD`（舊的 `.env`） | 只建立第一個平台管理員，示範資料整段略過，log 提示要補設定 | 不中斷啟動 |
| 同 Email 已被真人註冊 | 示範 Email 已存在但是一般帳號 | 視為已存在、略過，不改成主辦方 | N/A |

## Decisions（2026-10-30 使用者決定）

- 範圍：先做第一階段（腳本骨架＋示範帳號），分支從 `origin/main` 開 `story/7-1`。
- Email：`.env` 只設一個網域變數 `DEMO_EMAIL_DOMAIN`（預設 `example.com`），帳號固定為 `organizer@`、`referee@`、`captain@`、`player@`；第二階段的隊伍帳號沿用同一規則（例如 `captain01@`）。密碼共用 `DEMO_PASSWORD`。
- 學校：示範帳號都屬於「國立中央大學」。
- spec 約 2,100 tokens，超過建議上限，使用者選擇保留完整 spec。

</frozen-after-approval>

## Code Map

- `backend/app/initial_data.py` -- 啟動時的初始資料入口，`init(session_factory)` 建立第一個管理員後 commit；`main()` 由 prestart 呼叫。在這裡接上示範資料。
- `backend/scripts/prestart.sh` -- `alembic upgrade head` → `python -m app.initial_data`，不需改。
- `backend/app/modules/identity/service.py:58` -- `ensure_first_admin` 是示範帳號函式的範本（同 Email 已存在就略過、直接建立已驗證帳號、不 commit）。`register()` 不適用：驗證 token 明文只在 outbox 事件裡，示範腳本拿不到。
- `backend/app/modules/identity/repository.py` -- `get_account_by_email`、`add_account`、`list_schools` 可直接重用。
- `backend/app/modules/identity/models.py:59` -- `Account` 有 `email_verified`、`school_id`、`is_organizer`。
- `backend/app/core/config.py:64` -- `FIRST_ADMIN_*` 的設定與 `_check_default_secret` 寫法。
- `compose.yml:38` -- backend 環境變數；worker 共用 `*backend-env`。
- `backend/tests/identity/test_initial_data.py` -- 以 `session_factory` 呼叫 `init` 兩次的冪等測試範本。
- `backend/app/alembic/versions/4c1d9a7e2f30_*.py:31` -- 學校清單初始資料。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/identity/service.py` -- 新增 `ensure_demo_account(session, *, email, password, display_name, school_name, is_organizer=False) -> bool`：Email 已存在就回傳 False；找不到學校拋錯；建立已驗證帳號 -- 讓示範資料走 identity 的 service（A 負責 identity）。
- [x] `backend/app/core/config.py` -- 新增選填的 `DEMO_PASSWORD: str | None` 與 `DEMO_EMAIL_DOMAIN`（預設 `example.com`），`DEMO_PASSWORD` 納入 `_check_default_secret` -- 登入資訊不寫死在程式。
- [x] `backend/app/demo_data/__init__.py` -- `load(session)` 依呼叫方向的反序執行各模組的種子步驟（identity → tournaments → registration → competition），未設定 `DEMO_PASSWORD` 時整段略過；模組說明寫明其他組員如何新增自己的步驟檔 -- 共用擴充點。
- [x] `backend/app/demo_data/accounts.py` -- 建立四個示範帳號並回傳之後步驟要用的帳號 id -- 第一階段的資料。
- [x] `backend/app/initial_data.py` -- 建立管理員後，另開交易載入示範資料並 commit -- 啟動時自動載入。
- [x] `compose.yml`、`.env.example`、`README.md` -- 傳入、記載示範帳號設定與登入資訊表 -- 評審照 README 登入。
- [x] `backend/tests/identity/test_demo_data.py` -- 涵蓋 I/O 表四種情境與 `ensure_demo_account` 找不到學校 -- 冪等與略過行為。

**Acceptance Criteria:**
- Given 全新資料庫與 `.env.example` 複製的設定，when `docker compose up -d --build --wait`，then 用 README 列出的主辦方帳號 `POST /api/v1/access-tokens` 登入成功，`GET /api/v1/accounts/me` 取得的帳號 `email_verified` 與 `is_organizer` 皆為 true。
- Given 已啟動過，when 重新啟動 backend，then `account` 表的示範帳號數量不變。

## Design Notes

- 主辦方身分直接設 `is_organizer=true`，不經 1.7 申請、1.8 核准（1.8 尚未合併）；第二階段可改成呼叫 1.8 的核准函式，留下 `OrganizerApplication` 與操作紀錄。示範帳號與第一個管理員一樣不寫操作紀錄（系統初始資料，不是使用者操作）。
- 裁判、隊長是賽事與隊伍層級的身分（2.7、3.1），本階段只建立帳號，第二階段由各模組步驟把它們放進賽事與隊伍。
- 擴充方式：每個模組一個步驟檔，接收前面步驟回傳的 context（例如帳號 id），各自檢查是否已存在；新增檔案即可，減少合併衝突。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: backend healthy，log 出現示範帳號建立或略過的訊息
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過
- `docker compose exec backend bash scripts/lint.sh` -- expected: 無錯誤

## Implementation Notes

- `identity/service.py` 另外新增公開函式 `find_account_id_by_email`：示範帳號已存在而略過時，`accounts.py` 仍要把帳號 id 寫進 context 給第二階段的步驟用，`ensure_demo_account` 依 spec 只回傳 bool。
- 同 Email 已被真人註冊時，`context.accounts` 拿到的是那個真人帳號的 id；第二階段把帳號放進賽事、隊伍前要留意。
- `DemoContext` 與步驟型別放在 `demo_data/context.py`，避免步驟檔從套件 `__init__` 匯入造成循環匯入。
- `ensure_demo_account` 找不到學校時拋 `LookupError`（設定錯誤，不是使用者操作的業務錯誤），會讓 prestart 中斷。
- `prestart.sh` 只改了註解（說明也會建立示範資料）。
- 驗證：另開 compose 專案 `flow-verify`（全新 volume）啟動，以 `organizer@example.com` 登入成功，`/accounts/me` 的 `email_verified`、`is_organizer` 皆為 true；重啟 backend 前後 `account` 表都是 5 筆，log 出現 5 筆略過訊息；`scripts/test.sh` 259 passed（`demo_data` 覆蓋率 100%），`scripts/lint.sh` 無錯誤；驗證後 `down -v` 刪除該專案。

## Spec Change Log

## Review Triage Log
