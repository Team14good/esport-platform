---
title: '清理 deferred-work：可獨立完成的 8 項'
type: 'chore'
created: '2026-11-19'
status: 'in-review'
baseline_commit: '177f22d0d2dd1c9f3813e399c0e602e4b4fc114f'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `deferred-work.md` 累積了數筆不需他人決定、不綁在擱置 Story 上的小問題：422 訊息是英文、遷移的 server default 沒被比對、一次性連結缺並行測試、`main.tsx` 的接線沒有測試、非 ASCII 的 email 會讓驗證信寄不出去、worker 沒有 restart 政策、觀眾 e2e 只有假資料版、表單連點保護沒有測試。

**Approach:** 單一 PR 一次處理 8 項，每項各自有測試或斷言；處理完的 deferred 項目才刪除。頻率限制、色票、請求大小上限、`audit_log` 角色、屬於 B／C／D 模組的項目與綁在 2.6、3.7、3.8、6.x 的項目不在本次範圍，維持登記。

## Boundaries & Constraints

**Always:**
- 業務錯誤與 422 的回應格式不變：422 的 `detail` 仍是 `[{"type","loc","msg"}]`，只替換 `msg`；`PydanticCustomError` 自訂的繁中 `msg` 原樣保留。
- 不改其他組員模組的既有函式；只新增檔案或公開函式。
- 測試連 compose 的 PostgreSQL，不用 SQLite；時間用 `app.core.clock.now()`。
- 改完後端、前端要 `docker compose up -d --build --wait` 才會測到新版。

**Never:**
- 不做頻率限制、色票調整、請求大小上限、`audit_log` 角色。
- 不為了讓 CI 通過而跳過或刪除既有測試。
- 不新增 home e2e；該 deferred 的元件已不存在，只刪除該筆（見 Decisions）。
- 不改 worker 的 rollback 保護（`_run_item` 已有外層 `try/except`），只補 compose 的 restart。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 422 缺欄位 | 請求缺必填欄位 | 422，`msg` 為繁中，`type`、`loc` 不變 | N/A |
| 422 列舉不合法 | 列舉欄位給未知值 | 422，`msg` 為繁中 | N/A |
| 422 自訂錯誤 | 觸發 `PydanticCustomError` | 422，`msg` 維持原自訂繁中訊息 | N/A |
| 非 ASCII email | `主辦方@example.com` 註冊 | 422，`loc` 指向 email，繁中訊息 | 不建立帳號、不寄信 |
| 並行重設 | 同一重設連結兩條連線同時送出 | 恰好一個 204、一個 `RESET_LINK_INVALID`，`credentials_version` 只加 1 | N/A |
| 並行驗證 | 同一驗證連結同時送出 | 恰好一個成功、一個 `VERIFY_LINK_INVALID` 類錯誤（以現有代碼為準） | N/A |
| 表單連點 | 送出中再按一次送出 | `createGame`／`createSchool` 只呼叫一次，送出鈕停用 | N/A |

## Decisions

- email 非 ASCII 本地部分：註冊時回 422 擋下（使用者 2026-11-19 決定）；實作放在 `_validate_email`，註冊、重寄驗證信、忘記密碼共用。
- worker：只補 `restart: unless-stopped`，並刪除該筆 deferred（使用者 2026-11-19）。
- home e2e：不做，並刪除過時的 deferred；原因是首頁已無「後端狀態：正常」元件（使用者 2026-11-19）。
- 觀眾 e2e：補走真 API 的版本（`setUpDrawnTournament`），保留既有假資料版（使用者 2026-11-19）。
- 範圍：原 9 項中 8 項實作（home e2e 不做）、放同一個 PR；分支 `story/deferred-cleanup`（使用者 2026-11-19）。

</frozen-after-approval>

## Code Map

- `backend/app/core/errors.py:49-61` -- `register_error_handlers` 只註冊 `BusinessError`；新增 `RequestValidationError` handler，沿用 `FieldError` 的 `[{"type","loc","msg"}]` 格式。
- `backend/tests/core/test_errors.py`、`test_app.py:15` -- handler 測試與註冊斷言的風格。
- `backend/tests/test_migrations.py:14` -- `MigrationContext.configure(..., opts={"compare_type": True})`；加 `compare_server_default`，注意 `identity/models.py:70` 的 functional index 可能出現雜訊。
- `backend/app/modules/identity/service.py:435`（`reset_password`）、`:314-340`（`verify_email`） -- 並行測試對象。
- `backend/tests/registration/test_first_come_concurrency.py` -- 多連線 `Barrier`、`ThreadPoolExecutor`、自建資料並清理的先例；`conftest.py:117-140` 的 `client`／`session` 共用同一條連線，不能用。
- `backend/app/modules/identity/models.py:176-184`（`_validate_email`）、`:274`（`EmailField`）-- 非 ASCII 檢查放這裡；`PydanticCustomError` 沿用既有用法。
- `backend/tests/identity/test_signup.py` -- `_register`、`_email()` 風格。
- `frontend/src/main.tsx:15,24`、`frontend/src/features/identity/auth.ts:296` -- 接線；`frontend/tests/unit/auth.test.tsx` 有 `stubAdapter`、`jsonResponse` 可重用。
- `frontend/tests/e2e/spectator.spec.ts`、`support/match-api.ts`（假資料版）；`tournament.spec.ts:232` 的 `setUpDrawnTournament`、`support/matchday.ts:62` 的 `drawBracket`。
- `compose.yml:80-102` -- worker 服務；`backend/app/worker/__init__.py:34-49` 已有 cleanup 保護，不動。
- `frontend/src/features/tournaments/GameForm.tsx:446`、`frontend/src/features/identity/AdminSchoolsPage.tsx:70`；測試 `frontend/tests/unit/admin-games.test.tsx`、`admin-schools.test.tsx`。
- `_bmad-output/implementation-artifacts/deferred-work.md` -- 只刪除已處理的 9 筆（含 home、worker）；其餘不動。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/core/errors.py`、`backend/tests/core/test_errors.py` -- 新增 `RequestValidationError` handler，依 `type`（missing、enum、list_type、dict_type、型別錯誤等）換繁中，未知 type 用通用繁中訊息；測試涵蓋矩陣前三列 -- 英文 422 訊息會直接顯示給使用者
- [x] `backend/tests/test_migrations.py` -- 開 `compare_server_default`，先跑確認既有欄位沒有誤報，必要時只對確定雜訊的項目排除並註明原因 -- 遷移與模型 default 不一致時要失敗
- [x] `backend/tests/identity/test_reset_verify_concurrency.py`（新增） -- 兩條連線、兩個執行緒以 barrier 同時送出，涵蓋 `reset_password` 與 `verify_email`，自行建立並清理資料 -- 守住鎖定重查
- [x] `backend/app/modules/identity/models.py`、`backend/tests/identity/test_signup.py` -- `_validate_email` 擋非 ASCII 本地部分（繁中訊息）；測試註冊、重寄驗證信、忘記密碼 -- 驗證信寄不出去
- [x] `frontend/tests/unit/main-wiring.test.tsx`（新增） -- 驗證啟動接線：已登入請求帶 Bearer、401 導向 S6 -- 刪掉接線時測試要失敗
- [x] `frontend/tests/unit/admin-games.test.tsx`、`admin-schools.test.tsx` -- 補連點測試 -- 拿掉 `isSubmitting` 時測試要失敗
- [x] `frontend/tests/e2e/spectator.spec.ts` -- 新增走真 API 的 S3→S4→返回測試，檢查 375 px 只有對戰樹容器橫向捲動；更新檔頭註解 -- 與假資料版並存
- [x] `compose.yml` -- worker 加 `restart: unless-stopped` -- 程序結束後自動重啟
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除已處理的項目（422、migration default、並行、main.tsx、home、觀眾 e2e、email、worker、連點）

**Acceptance Criteria:**
- Given 缺欄位或列舉值不合法的請求，when 送出，then 422 的 `msg` 全是繁中，格式與 `loc` 不變，既有測試全過。
- Given 遷移與模型的 server default 不一致，when 跑 `test_migrations.py`，then 測試失敗。
- Given 同一重設或驗證連結同時送出，when 兩條連線競爭，then 恰好一個成功。
- Given 非 ASCII 本地部分的 email，when 註冊，then 422 且沒有帳號與信件。
- Given 完整後端、前端單元測試與 e2e（desktop、mobile-375）執行，then 全部通過，且 e2e 未新增 `fixme`／`skip`。

## Implementation Notes

- 後端 pytest 通過（總覆蓋率 97%；未抓到通過總數），lint 全過；前端單元 1025 項、typecheck、biome 通過。
- `tournament.spec.ts`（搬移 helper 到 `support/drawn.ts`）12 項通過（desktop、mobile-375 各 6，32.2 分鐘）；`spectator.spec.ts` 6 項僅有實作子任務自報，未獨立重跑；完整 e2e 因系統記憶體不足被停止，未跑完。
- deferred-work.md：刪除 10 筆（422、migration default、並行、main.tsx、home、worker、email、連點，加上觀眾 e2e 兩筆：spec-5-8-real-match-data 與 spec-7-2-e2e-tournament-drill）。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 全部服務 healthy
- `docker compose exec backend uv run pytest -q` -- expected: 全部通過
- `docker compose run --rm frontend bun run test` -- expected: 單元測試全過
- `docker compose run --rm e2e bunx playwright test tests/e2e/spectator.spec.ts` -- expected: 觀眾測試在 desktop 與 mobile-375 通過
- `git diff --check` -- expected: 無輸出
