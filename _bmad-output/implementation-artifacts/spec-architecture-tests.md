---
title: '後端架構測試：把 AD-2、AD-3、AD-5、AD-13 寫成測試'
type: 'chore'
created: '2026-11-04'
status: 'done'
baseline_commit: '8c0d45d7dc6ecf6f5ff8ebea6e9626953949aeb4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-se-final-project-2026-10-14/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 架構規則 AD-2、AD-3、AD-5、AD-13 目前只靠 CLAUDE.md 的文字約定，唯一的測試 `test_core_does_not_import_modules` 只比對字串 `"app.modules"`，換個 import 寫法就繞得過去。AI 產生程式時常為了方便直接越界，沒有測試就要靠人在審查時發現。

**Approach:** 新增一支只做靜態分析的測試檔，用 `ast` 解析 `backend/app` 的每個 `.py`，把四條規則寫成會紅燈的檢查；違規時訊息要列出「檔案:行號」和違反哪一條 AD。

## Boundaries & Constraints

**Always:**
- 只用標準函式庫（`ast`、`pathlib`），不新增套件；不連資料庫，單獨跑也能過。
- 規則與允許清單集中寫在測試檔開頭，一眼看得出例外有哪些、為什麼。
- 對目前 `main` 的程式全部綠燈；若掃到真的違規，先列給人決定，不要為了過測試而放寬規則。
- 每條規則至少一個「故意違規的程式片段會被抓到」的測試，證明檢查本身有效。

**Never:**
- 不改任何產品程式碼、不改既有測試（`test_module_structure.py` 保留原樣）。
- 不檢查 `alembic/versions/`（遷移檔是歷史快照）與 `tests/`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| AD-2 越界 | registration 的檔案 `from app.modules.tournaments import repository` | 測試失敗 | 訊息含檔案:行號與 AD-2 |
| AD-2 允許 | 呼叫對方 `service`；router 用 `identity.deps` | 通過 | N/A |
| AD-3 反方向 | tournaments 的檔案 import `app.modules.registration.service` | 測試失敗 | 訊息含 AD-3 |
| AD-3 通知 | 任何業務模組 import `app.modules.notifications` | 測試失敗 | 訊息含 AD-3 |
| AD-3 core | `core/` 用 `import app.modules.x` 或 `from app import modules` | 測試失敗 | 訊息含 AD-3 |
| AD-5 | `service.py`、`repository.py` 或其他非 router 的模組檔呼叫 `.commit()`／`.rollback()` | 測試失敗 | 訊息含 AD-5 |
| AD-13 | `core/clock.py` 以外呼叫 `datetime.now()`、`utcnow()`、`date.today()`、`time.time()` | 測試失敗 | 訊息含 AD-13 |
| AD-2 資料表 | competition 的檔案 `from app.modules.tournaments.models import Tournament` | 測試失敗 | 訊息含 AD-2 |
| AD-2 型別 | `from app.modules.tournaments.models import TournamentStatus, RankTierRead` | 通過 | N/A |

## Decisions

- **AD-3 方向（2026-11-04 使用者決定）：** 依序往下即可跳級。順序為 disputes → competition → registration → tournaments → identity，排在前面的模組可以呼叫排在後面的任一模組；反方向禁止。notifications 不在這條鏈上：它可以呼叫任何模組的 service，但沒有模組可以 import 它。
- **跨模組 models（2026-11-04 使用者決定）：** 允許 import 別的模組 `models.py` 裡的型別（StrEnum、`*Read` schema、事件 payload），但禁止 import `table=True` 的資料表類別。
- **不做逐項 code review（2026-11-04）：** 本項不做 code review，留待最後統一審查。

</frozen-after-approval>

## Code Map

- `backend/tests/test_module_structure.py` -- 既有的模組結構測試；`APP_DIR`、`MODULES` 的寫法可以照抄，不修改。
- `backend/app/modules/*/` -- 掃描對象。除了四層檔案，還有 `competition/{bracket,checkin,forfeit,forfeit_adapter,forfeit_job,progression,registration_port,schedule,scoring}.py`、`registration/player_profile.py`、`notifications/email.py`、`identity/deps.py`，同屬該模組。
- 合法的跨模組依賴（目前存在）：各 router → `identity.deps`；`competition/registration_port.py`、`forfeit_adapter.py` → 他模組 `service`；`notifications/service.py` → `identity.service`、`identity.models` 的事件 payload。
- 不屬於任何模組、可以 import 任何模組的進入點：`app/api/main.py`（掛 router）、`app/modules/__init__.py`（註冊資料表）、`app/worker/`、`app/main.py`、`app/initial_data.py`、`app/demo_data/`。
- AD-5 允許 commit／rollback：各模組 `router.py`、`app/worker/__init__.py`、`app/initial_data.py`；`app/core/db.py` 只在 docstring 出現，AST 不會抓到。
- AD-13：只有 `app/core/clock.py` 可以呼叫 `datetime.now`。`tests/competition/test_checkin.py:391`、`test_forfeit.py:311` 已有針對單一檔案的同類檢查，可參考寫法。

## Tasks & Acceptance

**Execution:**
- [x] `backend/tests/test_architecture.py` -- 新增：共用的 import 收集函式（處理 `import a.b`、`from a.b import c`、`from a import modules`）、四條規則各一個掃全專案的測試、每條規則一個餵入違規原始碼字串的負面測試 -- 規則與例外集中可讀。

**Acceptance Criteria:**
- Given 目前 `main` 的程式，when 跑 `pytest tests/test_architecture.py`，then 全部通過。
- Given 在任一模組檔加入違反四條規則之一的程式，when 跑同一個測試，then 失敗訊息列出該檔案:行號與 AD 編號。

## Implementation Notes

- 只新增 `backend/tests/test_architecture.py`，共 53 個測試：3 個掃全 `app/`、2 個自我檢查（掃描涵蓋六個模組、資料表類別辨識正確），其餘是負面與允許的案例。
- 資料表類別的判斷也用 AST：讀對方 `models.py` 裡 class 定義的 `table=True` 關鍵字，不匯入模組。
- AD-13 會追蹤別名（`import datetime as dt`、`from datetime import datetime as DT`、`from time import time`），也會抓沒呼叫的參照（`default_factory=datetime.now`）。
- AD-2 的 `identity.deps` 只允許 `router.py` import；`from app.modules.x import models` 整包匯入看不出用了哪些類別，一律判違規（目前只有 `modules/__init__.py` 這樣寫，它是進入點，不掃）。
- 驗證：Docker Desktop 當時是暫停狀態，改用本機 `uv run --frozen pytest tests/test_architecture.py --noconftest` 跑，53 passed；ruff check、ruff format --check、mypy 都沒有問題。另在 `registration/service.py` 暫時加入三種違規，三條規則各自紅燈，行號正確，之後已還原。
- 完整測試（2026-11-04，Docker 恢復後）：在 worktree 用獨立的 compose 專案 `flow-archtest` 啟動 db、backend，跑 `scripts/test.sh`。第一次只有 `test_smtp_sender_delivers_to_mailpit_from_flow` 失敗，原因是沒有啟動 mailpit；補啟動後重跑，1698 passed，覆蓋率門檻通過。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose run --rm --no-deps -T -v "<worktree>/backend:/app/backend" backend pytest tests/test_architecture.py -q` -- expected: 全部通過
- `ruff check` 與 `ruff format --check` 對新檔 -- expected: 無錯誤
