---
title: 'Story 1.6：通知中心'
type: 'feature'
created: '2026-11-21'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** worker 目前只認得驗證信與重設密碼信兩種事件，其餘 18 種業務事件都被略過；使用者收不到任何站內通知，頂欄沒有鈴鐺，也沒有通知中心（FR-37、FR-38）。

**Approach:** 在 notifications 建立「事件類型 → 收件規則」的登錄機制：worker 處理登錄過的事件時，依規則查出收件人，為每人建立 Notification 與 EmailDelivery（以事件 id＋收件人去重），Email 用同一版型寄出。為期中已發出、在 FR-37 對照表內的事件登錄規則。前端加上鈴鐺（30 秒輪詢未讀數、Popover 最新 8 則）與 S14 `/notifications`（每頁 20 則、點擊標為已讀並導向 `link`）。

## Boundaries & Constraints

**Always:**
- 事件不帶收件人（AD-8）；收件規則在 notifications 內登錄，規則只呼叫各模組 `service.py` 的公開函式查詢。其他模組不 import notifications。
- 只寄 Email 的事件（`VerificationEmailRequested`、`PasswordResetRequested`）維持原行為，不建立 Notification。
- Notification 以（`event_id`, `account_id`）唯一；同一事件重複處理、或規則回傳同一人兩次，都只產生一則通知與一封信。
- 收件規則查不到實體（`BusinessError`、`LookupError`）或 payload 格式錯誤時，記錄後略過該事件並照常標為已處理，不卡住後面的事件；其他例外照常往外拋（交易回滾，下一輪重試）。
- 通知 API 一律要登入（`CurrentAccount`，未驗證 Email 也可以看）；只能讀取、標記自己的通知。
- 未讀數 30 秒輪詢（AD-14），這是唯一新增的輪詢；不做 optimistic update。
- 時間顯示 Asia/Taipei；介面全部繁中，375 px 寬沒有橫向捲軸。

**Never:**
- 不做「全部標為已讀」、通知偏好設定、刪除通知（UX-DR9）。
- 不補發期中已處理的事件（outbox 已標為 processed 的不重跑）。
- 不修改其他組員模組的既有函式；需要的查詢只新增公開函式（CONTRIBUTING 6.6）。
- 不為 `MatchResultSubmitted`、`MatchResultConfirmed`、`TeamCheckedIn` 登錄規則（不在 FR-37 對照表）。
- 不做 2.6 取消賽事、3.7～3.11 的事件（那些 Story 自己登錄）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 登錄過的事件 | 測試事件類型，規則回傳 2 位收件人 | 2 則 Notification（`title`、`body`、`link`、`created_at`）＋2 筆 EmailDelivery | N/A |
| 重複處理 | 同一事件 dispatch 兩次 | 仍只有 2 則通知、2 筆寄送 | N/A |
| 規則回傳重複收件人 | 同一 account 出現兩次 | 1 則通知 | N/A |
| 實體不存在 | 規則查詢拋 `BusinessError` | 不建立任何資料，事件標為已處理 | log 後略過 |
| 未登錄的事件 | 例如 `TeamCheckedIn` | 不建立任何資料 | log info 後略過 |
| 一般通知的 Email | 該收件人的 Notification 存在 | 主旨＝`title`，內文＝`body`，按鈕「前往 FLOW 查看」連到 `FRONTEND_HOST + link` | 寄送失敗沿用重試規則 |
| 列表 | `GET /api/v1/notifications?page=1` | `{items,total,page,page_size=20}`，依 `created_at` 由新到舊（同時間依 id） | `page < 1` 422 |
| 未讀數 | `GET /api/v1/notifications/unread-count` | `{count}`，只算自己的 `read_at IS NULL` | 未登入 401 |
| 標為已讀 | `POST /api/v1/notifications/{id}/read` | 200 回傳該通知；`read_at` 寫入目前時間；已讀過的保持原 `read_at` | 別人的或不存在：404 `NOTIFICATION_NOT_FOUND`「找不到這則通知。」 |
| 鈴鐺徽章 | 未讀 0／5／120 | 不顯示／「5」／「99+」 | 輪詢失敗時不顯示徽章、不跳錯 |
| Popover | 點鈴鐺 | 最新 8 則：`title`、相對時間（「3 分鐘前」）、一行絕對時間（`10/18（六）19:00`），未讀左側 8px 圓點；底部「查看全部」→ `/notifications` | 沒有通知：「還沒有通知。」 |
| S14 | 開啟 `/notifications?page=N` | 每頁 20 則、分頁寫入 URL；沒有通知時 Empty state「還沒有通知。」 | 未登入導向 S6 帶 `redirect` |
| 點擊通知 | 未讀通知 | 呼叫標為已讀 → 重新取得未讀數與列表 → 導向 `link` | 標記失敗仍導向 `link` |

</intent-contract>

## Decisions（2026-11-21，flow-bot 依推薦做法選定，可在 PR 提出異議）

- **範圍包含登錄期中事件的收件規則**：epics.md Story 1.6 的期中擱置註記要求「期末做本 Story 時，為期中各 Story 已發出的事件登錄收件規則」。本 Story 為下表 14 種事件登錄規則；登錄機制本身的測試仍用測試專用事件類型（AC 3）。
- **Notification 加 `body` 欄位**：D-6 類別圖只有 `title`、`link`；UX-DR10 的 Email 需要「一段說明」，所以存一句 `body`。介面只顯示 `title`。
- **收件規則以每位收件人一份草稿表示**（`account_id`, `title`, `body`, `link`）：檢舉處理完成時，檢舉方與被檢舉方要導向各自的隊伍頁，`link` 因人而異。
- **別人的通知回 404**（不是 403）：不透露通知 id 是否存在，與 AC「被拒絕」相容。
- **Popover 重用列表 API 第 1 頁、只顯示前 8 則**：不另開 API；只在打開時抓取。
- **身分清單刷新**：UX-DR8 要求「主辦方申請核准後在下次輪詢到核准通知時刷新」。前端在輪詢到未讀數增加時，重新取得帳號與身分清單（`ME_QUERY_KEY`）。這取代 1.8 期中版「重新整理才出現主辦方身分」的規則。
- **「隊長與選手」＝隊伍所有成員**（`TeamRead.members` 全部帳號）。
- **`RefereeUnassigned` 只通知被取消的裁判**：事件沒有區分「晉級衝突」與「主辦方收回」，FR-37「晉級衝突時另通知主辦方」需要 competition 在事件加欄位，列入 deferred-work。
- **BracketDrawn 的收件人取自對戰表**：抽籤後報名狀態已改為 `drawn`，從 `competition.get_bracket` 的場次隊伍取隊員，不用 `list_accepted_teams`。

### 收件規則表

| 事件 | 收件人 | link |
|---|---|---|
| OrganizerApplicationSubmitted | 所有平台管理員 | `/admin/applications` |
| OrganizerApplicationApproved | 申請人 | `/organizer` |
| OrganizerApplicationRejected | 申請人 | `/organizer/apply` |
| RegistrationAllocated | 該隊所有成員 | `/teams/{team_id}` |
| BracketDrawn | 對戰表上所有隊伍的成員 | `/tournaments/{id}/bracket` |
| AutoDrawSkipped | 賽事主辦方 | `/organizer/tournaments/{id}` |
| MatchRescheduled | 兩隊成員＋指派的裁判 | `/tournaments/{tid}/matches/{mid}` |
| MatchOpponentsDecided | 兩隊隊長 | 同上 |
| MatchForfeited | 兩隊成員＋指派的裁判 | 同上 |
| RefereeAssigned／RefereeUnassigned | 事件裡的裁判 | `/me/referee` |
| AppealFiled | 賽事主辦方 | `/organizer/tournaments/{tid}/appeals` |
| AppealResolved | 兩隊成員 | `/tournaments/{tid}/matches/{mid}` |
| ReportFiled | 賽事主辦方 | `/organizer/tournaments/{tid}/reports` |
| ReportResolved | 檢舉方與被檢舉方成員 | 各自的 `/teams/{team_id}` |

## Code Map

- `backend/app/modules/notifications/service.py` -- `dispatch_event`（只處理 token 事件，其餘 log 略過）、`_compose`、`send_next_email`。要擴充分派與一般通知的信件組成。
- `backend/app/modules/notifications/models.py` -- `EmailDelivery`、`DeliveryStatus`；新增 `Notification` 與 API schema。
- `backend/app/modules/notifications/repository.py` -- `add_delivery_if_absent` 用 `on_conflict_do_nothing`，通知照同樣寫法。
- `backend/app/modules/notifications/router.py` -- 目前空的 router，已掛在 `app/api/main.py`。
- `backend/app/modules/notifications/email.py` -- `render_email(to,title,body,button_label,button_url)` 直接重用。
- `backend/app/worker/jobs.py:20` -- `dispatch_outbox` 呼叫 `dispatch_event` 後 `mark_processed`；不需修改。
- `backend/app/core/events.py` -- `Event`、`OutboxEvent`、`publish`。測試事件類別在測試檔內定義。
- `backend/app/modules/identity/models.py:154` -- 三種主辦方申請事件（只帶 `application_id`）；`Account.is_platform_admin`、`OrganizerApplication.account_id`。
- 查詢用的既有公開函式：`tournaments.service.get_tournament`（`organizer_id`、`name`）、`registration.service.get_team`（`members`、`name`）、`registration.service.is_captain`、`competition.service.get_match`（`team_a_id`、`team_b_id`、`referee_account_id`、`tournament_id`、`code`）、`competition.service.get_bracket`（`matches`）。
- 事件定義：`competition/models.py:208-268`、`competition/forfeit_job.py:54`（`MatchForfeited`）、`registration/models.py:159`、`disputes/models.py:146-175`。
- `backend/app/modules/identity/models.py:453` -- `OrganizerApplicationPage` 是分頁格式 `{items,total,page,page_size}` 的範例。
- `backend/tests/notifications/test_email_delivery.py`、`backend/tests/worker/test_email_pipeline.py` -- 既有寄信測試寫法。
- `backend/tests/traceability.yaml` -- 新測試檔要加一列。
- `frontend/src/components/layout/TopBar.tsx` -- 鈴鐺放在 `IdentitySwitcher` 前（只在登入時）。
- `frontend/src/components/common/EmptyState.tsx` -- 1.8 已建立，直接重用（AC 的 Empty state 元件已存在）。
- `frontend/src/components/ui/popover.tsx`、`pagination.tsx` -- shadcn 元件。
- `frontend/src/lib/datetime.ts` -- 台北時間格式化；新增相對時間與 `10/18（六）19:00` 格式。
- `frontend/src/features/identity/auth.ts:119-125` -- `ME_QUERY_KEY`（帳號、身分清單）。
- `frontend/src/features/identity/admin-applications.ts` -- 分頁查詢與 URL search 寫法範例。

## Tasks & Acceptance

**Execution:**
- `backend/app/modules/notifications/models.py` -- 新增 `Notification` 表（id、account_id FK、event_id FK、type、title、body、link、created_at、read_at；唯一（event_id, account_id）、索引（account_id, created_at））、`NotificationRead`、`NotificationPage`、`UnreadCount`。
- `backend/app/alembic/versions/<新檔>.py` -- 建 `notification` 表的遷移，down_revision 為目前 head。
- `backend/app/modules/notifications/registry.py`（新）-- `NotificationDraft`、`register(event_class, resolver)`、`get_rule(event_type)`；測試可以登錄並移除測試事件。
- `backend/app/modules/notifications/rules.py`（新）-- 依上方收件規則表登錄 14 種事件的 resolver（含標題與一句說明）。
- `backend/app/modules/identity/service.py` -- 新增 `list_platform_admin_ids`、`get_organizer_applicant_id(application_id)`（identity 是 A 的模組）。
- `backend/app/modules/disputes/service.py` -- 只新增 `get_report_parties(report_id) -> ReportParties`（tournament_id、reporter_team_id、reported_team_id）；`ReportParties` schema 加在 `disputes/models.py`。
- `backend/app/modules/notifications/repository.py` -- `add_notification_if_absent`、`list_for_account`（分頁＋total）、`count_unread`、`get_for_account`、`get_by_event_and_account`。
- `backend/app/modules/notifications/service.py` -- `dispatch_event` 加上登錄規則分支（去重、例外處理）；`_compose` 支援一般通知；新增 `list_notifications`、`unread_count`、`mark_read`。
- `backend/app/modules/notifications/router.py` -- `GET /notifications`、`GET /notifications/unread-count`、`POST /notifications/{id}/read`。
- `backend/tests/notifications/test_dispatch.py`（新）-- 測試事件類型的分派、去重、略過、Email 組成。
- `backend/tests/notifications/test_rules.py`（新）-- 以真實流程建資料，驗證主要規則的收件人與 link（申請三事件、報名、抽籤、改時間、裁判、申訴、檢舉）。
- `backend/tests/notifications/test_notification_api.py`（新）-- 列表排序與分頁、未讀數、標為已讀、別人的通知 404、未登入 401。
- `backend/tests/traceability.yaml` -- 新增三列（1.6、FR-37／FR-38／NFR-5）。
- `frontend/src/client/` -- 重新產生。
- `frontend/src/lib/datetime.ts` -- `formatRelativeTime(value, now)`、`formatShortDateTime(value)`（`10/18（六）19:00`）。
- `frontend/src/features/notifications/queries.ts`（新）-- 未讀數輪詢（30 秒，增加時 invalidate `ME_QUERY_KEY`）、列表、標為已讀 mutation。
- `frontend/src/features/notifications/NotificationBell.tsx`、`NotificationList.tsx`、`NotificationsPage.tsx`（新）-- 鈴鐺＋Popover、共用列表項目、S14。
- `frontend/src/routes/notifications.tsx`（新）-- S14 路由（要登入，`page` 寫入 URL）。
- `frontend/src/components/layout/TopBar.tsx` -- 登入時加入鈴鐺。
- `frontend/tests/unit/notifications.test.tsx`、`datetime.test.ts` -- 徽章 99+、Popover 8 則與圓點、點擊標為已讀並導向、Empty state、時間格式。

**Acceptance Criteria:**
- Given 測試專用事件類型登錄了收件規則，when worker 處理該事件，then 每位收件人有一則 Notification 與一筆 EmailDelivery，重複處理不會增加。
- Given 只寄 Email 的事件，when worker 處理，then 不建立 Notification。
- Given 已登入，when 停在任何頁面，then 鈴鐺每 30 秒更新未讀數，超過 99 顯示「99+」。
- Given 一則未讀通知，when 在 Popover 或 S14 點擊，then 標為已讀、未讀數減一並導向 `link`。
- Given 其他帳號的通知 id，when 呼叫標為已讀，then 404，且該通知的 `read_at` 不變。
- Given 平台管理員核准申請，when worker 處理事件，then 申請人收到「主辦方申請已核准」通知，下一次輪詢後身分切換器出現「主辦方後台」。

## Spec Change Log

## Review Triage Log

## Design Notes

分派流程（worker 交易內）：

```python
rule = registry.get_rule(event.type)
payload = rule.event_class.model_validate(event.payload)   # ValidationError → 略過
drafts = rule.resolver(session, payload)                   # BusinessError/LookupError → 略過
for draft in dedupe_by_account(drafts):
    repository.add_notification_if_absent(...)
    repository.add_delivery_if_absent(...)
```

`_compose` 對非 token 事件，以（event_id, account_id）找回 Notification 組信；找不到時 `LookupError`（走重試）。

## Verification

**Commands:**
- `docker compose exec backend bash scripts/test.sh` -- 全部通過
- `docker compose exec backend bash scripts/lint.sh` -- 無錯誤
- `cd frontend && bun run build && bunx tsc --noEmit && bunx biome check && bun run test` -- 全部通過
- `scripts/generate-client.sh` 後 `git diff --exit-code frontend/src/client` -- 無差異
