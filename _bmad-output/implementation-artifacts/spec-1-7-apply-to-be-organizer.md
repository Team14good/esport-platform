---
title: 'Story 1.7：申請成為主辦方'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: '338742d67f024a2a07e68a992b9f011d16c419b0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 想辦賽事的人目前沒有任何管道取得主辦方資格；沒有主辦方申請的資料表、API，也沒有 S15。

**Approach:** 在 identity 新增 OrganizerApplication：已驗證的帳號從身分切換器進入 S15，填社團名稱、從學校清單選擇學校送出，建立「待審核」申請並寫操作紀錄、發出事件；S15 改為以 Status badge 呈現的唯讀摘要。同時建立之後全站共用的 Status badge 元件。

## Boundaries & Constraints

**Always:**
- 送出申請要 `VerifiedAccount`（未驗證 403 `EMAIL_NOT_VERIFIED`）；學校存 `school_id`，不存在回 422 `SCHOOL_NOT_FOUND`（欄位錯誤，比照註冊）。
- 同一帳號同時只能有一筆 `pending`：服務層先鎖帳號再檢查，資料庫再以部分唯一索引（`account_id`，`status = 'pending'`）保底；違反時 409 `APPLICATION_PENDING`。
- 申請、操作紀錄 `organizer_application.submitted`、事件 `OrganizerApplicationSubmitted` 在同一個交易寫入；事件只帶 `application_id`。
- Status badge：藥丸形、永遠帶文字、tone 依 DESIGN.md 對照表、可選脈動點；主辦方申請的對照為待審核 `status-appeal`、核准 `status-confirmed`、退回 `destructive`。
- 時間以 Asia/Taipei 顯示；schema 變更一支 Alembic 遷移檔。

**Never:**
- 不在 notifications 登錄收件規則、不建站內通知或 Email（期中規則 2，worker 會略過）。
- 不做審核、退回原因顯示、重送表單、核准後的「前往主辦方後台」（Story 1.8）。
- 不修改 `docs/`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 送出申請 | 已驗證、非主辦方、沒有待審核；社團名稱＋學校 | 201 回傳申請（`pending`）；S15 換成唯讀摘要；Toast「已送出主辦方申請。」 | N/A |
| 重複送出 | 已有 `pending` | 不新增任何資料 | 409 `APPLICATION_PENDING`「你已有一筆待審核的主辦方申請。」，表單頂部 Alert |
| 已是主辦方 | `is_organizer = true` | 不新增任何資料 | 409 `ALREADY_ORGANIZER`「你已經是主辦方。」 |
| 未驗證 Email | 開啟 S15 | 表單整個停用＋「完成 Email 驗證後才能申請成為主辦方。」＋「前往 Email 驗證」（→ S7） | API 403 `EMAIL_NOT_VERIFIED` |
| 欄位不合格 | 社團名稱空白或超過 50 字、沒選學校、學校不存在 | 422，錯誤顯示在欄位下方 | 前端先擋前三種 |
| 已有申請時開啟 S15 | 最新一筆申請存在 | 直接顯示唯讀摘要（社團名稱、學校、送出時間、Status badge） | N/A |
| 未登入 | 開啟 S15 或呼叫 API | 導向 S6 帶 `redirect`；API 401 | N/A |

## Decisions（2026-10-29 定案；使用者授權「有問題直接選最推薦那個」）

- **身分切換器入口**：選單在「帳號資料」上方加「申請成為主辦方」（→ S15）；非主辦方帳號一律顯示（含未驗證、已有待審核的帳號），主辦方不顯示。
- **S1 的 Page banner 延後**：S1 目前仍是佔位頁（賽事列表在 Epic 2），banner 記入 deferred-work。
- **社團名稱**：去除前後空白後 1～50 字（以字元計，同顯示名稱）。
- **學校預填**：表單的學校預設帶入帳號的學校，可以改。
- **未驗證時的連結**：S15 用「前往 Email 驗證」連到 S7（S7 已有重寄驗證信），不在 S15 放重寄按鈕。
- **待審核摘要文案**：「平台管理員審核後，結果會顯示在這裡。」
- **主辦方開啟 S15 且沒有任何申請**（例如手動設定的主辦方）：只顯示「你已經是主辦方。」。
- **保留完整 spec**（超過 1600 tokens，不拆分；Status badge 是本 Story 的 AC）。
- **不做 code review**（使用者決定）：之後不再每個 Story 各自 review，改在最後統一審查一次；本 Story 驗證通過即收尾，sprint-status 停在 `review` 等統一審查。

</frozen-after-approval>

## Code Map

- `backend/app/modules/identity/models.py` -- `ApplicationStatus` 已存在；新增 `OrganizerApplication` 表（比照 `AccountToken`：`status` 用 `sa_type=String(32)`、時間 `DateTime(timezone=True)`、`created_at` default `clock.now`）、事件比照 `PasswordResetRequested`、欄位驗證比照 `DisplayNameField`（`_require_str` + `PydanticCustomError`）。`IdentityKey` 不動（申請不是身分）。
- `backend/app/modules/identity/service.py` -- `_school_not_found()`（FieldError）直接沿用；`repository.get_account(..., for_update=True)` 鎖帳號；`audit.record`、`events.publish` 寫法同 `register`。
- `backend/app/modules/identity/repository.py` -- `add_account` 的 `begin_nested` + `IntegrityError` 判斷索引名稱，新增申請照抄。
- `backend/app/modules/identity/router.py`、`deps.py` -- `VerifiedAccount`、`CurrentAccount`；router commit。`tests/test_auth_required.py` 會自動檢查新的寫入端點要登入。
- `backend/app/alembic/versions/9e5b3f1a7c42_story_1_5_password_reset.py` -- 目前 head，新遷移 `down_revision` 指向它；`tests/test_migrations.py` 檢查遷移與模型一致。
- `backend/app/modules/notifications/service.py:46` `dispatch_event` -- 沒登錄的事件會記 log 後略過；不要改。
- `backend/tests/identity/test_signup.py`、`test_login.py` -- 建帳號、登入取 token、檢查 audit 與 outbox 的寫法。
- `frontend/src/features/identity/AccountProfilePage.tsx` -- S15 表單照抄（`Form`、`SchoolPicker`＋`useSchools`、`applyFieldErrors`、`FormErrorAlert`、`LoadingButton`、Skeleton／錯誤重載）；`codePointLength` 在 `SignupForm.tsx`。
- `frontend/src/features/identity/VerificationRequired.tsx` -- 未驗證停用的包裝；加一個改成「前往 Email 驗證」連結的選項。
- `frontend/src/components/layout/IdentitySwitcher.tsx` -- 加入口；`tests/unit/identity-switcher.test.tsx` 有既有測試。
- `frontend/src/routes/account.tsx` -- 路由寫法（`requireSignedIn`、`head` 標題）。
- `frontend/src/index.css:119-123` -- `status-*`、`brand` 色已有 Tailwind token。
- UX：S15 `ux-designs/.../EXPERIENCE.md:57,305-312,362`；Status badge `DESIGN.md:427-436`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/identity/models.py`、`backend/app/alembic/versions/` -- `OrganizerApplication`（id、account_id FK＋index、club_name、school_id FK、status、reject_reason 可空、created_at）與部分唯一索引；事件 `OrganizerApplicationSubmitted(application_id)`；schema `OrganizerApplicationCreate{club_name, school_id}`、`OrganizerApplicationRead`（見 Design Notes）；遷移檔 `story_1_7`。
- [x] `backend/app/modules/identity/repository.py`、`service.py` -- `submit_organizer_application`、`get_my_organizer_application`（最新一筆或 None）。
- [x] `backend/app/modules/identity/router.py` -- 兩支端點（見 Design Notes）。
- [x] `backend/tests/identity/test_organizer_application.py` -- I/O 矩陣後端各列、操作紀錄內容、outbox 事件、部分唯一索引擋下第二筆 pending、被退回後可再送（直接把舊申請設為 rejected 模擬）。
- [x] `scripts/generate-client.sh` -- 重新產生 `frontend/src/client`。
- [x] `frontend/src/components/common/StatusBadge.tsx` -- 共用元件：`tone`（live、appeal、confirmed、waitlist、eliminated、brand、destructive、muted）、`pulse`、文字 children。
- [x] `frontend/src/lib/datetime.ts` -- `formatDateTime`（Asia/Taipei，`2026/10/29 14:05`）。
- [x] `frontend/src/features/identity/organizer-application.ts`、`OrganizerApplyPage.tsx`、`frontend/src/routes/organizer/apply.tsx` -- S15：查詢、表單、摘要、狀態對照（label＋tone）。
- [x] `frontend/src/features/identity/VerificationRequired.tsx`、`frontend/src/components/layout/IdentitySwitcher.tsx` -- 前往 S7 的選項、切換器入口。
- [x] `frontend/tests/unit/{status-badge,organizer-apply}.test.tsx`、`identity-switcher.test.tsx` -- I/O 矩陣前端各列、徽章文字與 tone、脈動點、切換器入口顯示條件。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 新增 S1「想辦賽事？申請成為主辦方」Page banner 延後一項。

**Acceptance Criteria:**
- Given 已驗證的帳號，when 從身分切換器「申請成為主辦方」進入 S15 送出，then 資料庫有一筆 `pending` 申請、一筆 `organizer_application.submitted` 操作紀錄與一則 `OrganizerApplicationSubmitted` 事件，worker 處理後事件標為已處理、沒有寄任何信。
- Given 送出後重新整理 S15，then 仍顯示唯讀摘要與「待審核」徽章。
- Given 375 px 寬，when 瀏覽 S15 的表單、摘要與未驗證狀態，then 沒有橫向捲軸，介面文字全部為繁體中文。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- 產生的 client（`client.gen.ts` 的 `data: data ?? {}`）會把後端的 `null` 回應換成 `{}`；`organizerApplicationQueryOptions` 以有沒有 `id` 判斷，沒有就視為 null。單元測試照實以 `{ data: {} }` 模擬「沒有申請」，否則測不到（手動檢查時才發現 S15 會當成有申請而崩潰）。
- `school_id` 用 `RequiredSchoolField`：null／空字串回「請選擇學校」、不是 UUID 回「找不到這間學校」，都在 `school_id` 欄位下方；完全沒送這個鍵仍是 pydantic 預設的英文訊息（與其他必填欄位相同，前端一定會送）。
- 「前往 Email 驗證」連到 `/verify-email?redirect=<目前頁面>`，在 S7 重寄的驗證信驗證完會回到 S15。
- 遷移 `c7e2a4d9b8f1_story_1_7_organizer_application.py`；`club_name` 欄位長度 255（與 `display_name` 相同），1～50 字由 schema 驗證。

## Spec Change Log

## Review Triage Log

## Design Notes

**API**：
- `POST /api/v1/organizer-applications` `{club_name, school_id}`（`VerifiedAccount`）→ 201 `OrganizerApplicationRead`。檢查順序：鎖帳號 → 已是主辦方 → 已有 pending → 學校存在 → 新增（撞部分唯一索引也轉成 `APPLICATION_PENDING`）。
- `GET /api/v1/accounts/me/organizer-application`（`CurrentAccount`）→ 200 `OrganizerApplicationRead | null`，取 `created_at` 最新一筆；未驗證帳號也能讀。

`OrganizerApplicationRead`：`id`、`club_name`、`school_id`、`school_name`、`status`、`reject_reason`、`created_at`。帶 `school_name` 讓 S15 與 1.8 的審核表不必再對照學校清單；1.8 預填重送表單時用 `school_id`。

**操作紀錄**：`actor_id` 申請人、`entity_type="organizer_application"`、`after={club_name, school_id, status}`、`before=None`。

**S15**：載入中 Skeleton；查詢失敗顯示錯誤＋「重新載入」。有申請 → 摘要 `Card`：標題列「主辦方申請」＋Status badge、`dl` 列出社團名稱／學校／送出時間、下方 muted 說明。沒有申請 → 表單（標題「申請成為主辦方」，說明「平台管理員會依社團名稱與學校審核。」，按鈕「送出申請」）。送出成功以回傳值 `setQueryData`，不另外重抓。徽章對照放在 `organizer-application.ts`，以產生的 `ApplicationStatus` 為鍵（漏了會編譯失敗，比照 `identity-icons.ts`）。

**Status badge**：`rounded-full border px-2.5 py-0.5 text-label`，文字 `text-status-*`、底 `bg-status-*/15`、框 `border-status-*/38`；`pulse` 時文字前加 6px 圓點（`animate-pulse`，`motion-reduce` 時不動），圓點 `aria-hidden`。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy，新遷移套用成功。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過，coverage 達 `fail_under`。
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bun run --filter frontend typecheck` -- expected: 無錯誤。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。

**Manual checks (if no CLI):**
- 以已驗證帳號從身分切換器進入 S15 送出、再送一次被拒；未驗證帳號看停用狀態；375 px 寬各看一次。
