# Epic 1 Context: 平台基礎、帳號與通知中心

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

用官方全端範本建立可以 `docker compose up` 一鍵啟動的系統骨架、core 共用元件與 FLOW 前端外框，讓之後每個 Epic 都沿用同一套模組結構、交易／事件／操作紀錄／權限／時鐘介面與共用 UI 元件。同時完成整個帳號生命週期：註冊、Email 驗證（可重寄）、登入、登出、重設密碼、身分切換器、主辦方申請與平台管理員審核，並以 outbox 驅動站內通知與 Email。這個 Epic 是整個平台的地基，這裡定下的慣例，後續 Epic 直接繼承、不再重新決定。

## Stories

- Story 1.1: 以官方範本建立可一鍵啟動的專案骨架
- Story 1.2: FLOW 前端外框與主題
- Story 1.3: 以 Email 註冊並完成驗證
- Story 1.4: 登入、登出、帳號資料與身分切換器
- Story 1.5: 忘記與重設密碼
- Story 1.6: 通知中心
- Story 1.7: 申請成為主辦方
- Story 1.8: 平台管理員審核主辦方申請

## Requirements & Constraints

- **帳號**：同一個 Email 不能重複註冊（`EMAIL_ALREADY_REGISTERED`）；密碼只存雜湊；學校為選填，只能從學校清單選擇（存 `school_id`，清單外的 id 會被拒絕）。登入失敗時不透露帳號是否存在。
- **Email 驗證閘門**：未驗證的帳號不能申請主辦方或報名，API 回 403 `EMAIL_NOT_VERIFIED`；未登入呼叫任何寫入 API 一律回 401。權限一律在伺服器端檢查，前端隱藏按鈕不算權限檢查。
- **一次性連結**：驗證連結 24 小時、重設連結 1 小時，用一次就失效；同一帳號、同一用途重新產生時，舊 token 全部作廢；設定新密碼後舊密碼不能再登入。申請重設密碼時，不論 Email 是否已註冊，回應的狀態碼與內容都相同（未註冊時不產生事件）。
- **主辦方申請**：同一帳號同時只能有一筆待審核（`APPLICATION_PENDING`）；退回必須填原因，申請人可以修改後重送、次數不限；核准後 `is_organizer` 立即生效。新申請通知所有平台管理員，核准或退回通知申請人（站內通知＋Email）；申請與審核都要寫操作紀錄。第一個平台管理員依 `.env` 在啟動時建立，已存在則略過。
- **通知**：每個事件對每位收件人只通知一次；Email 寄送失敗會記錄並重試，不影響主流程；驗證信與重設密碼信只寄 Email、不進通知中心。只能讀取或標記自己的通知。
- **非功能**：375 px 寬沒有橫向捲軸，介面全部繁體中文；compose 一個指令就能啟動全部服務。

## Technical Decisions

- **起始與堆疊**：`fastapi/full-stack-fastapi-template`（2026-10 master）；Python 3.14、FastAPI、SQLModel、Alembic、psycopg 3.3、PostgreSQL 18、React 19.3、TS 6.0、Vite 8.3、TanStack Router／Query、Tailwind 4.2＋shadcn/ui、Bun 1.4。後端版本由 `uv.lock`、前端由 `bun.lock` 固定，兩者都進版本控制；不得產生 `package-lock.json`。
- **compose**：只有 `db`（`postgres:18`）、`backend`、`worker`、`frontend`、`mailpit` 五個服務；移除 Traefik、adminer 與雲端部署設定；frontend 用自寫的 Dockerfile；設定從 `.env` 讀取，只提交 `.env.example`。
- **模組化單體**：`backend/app/modules/{identity,tournaments,registration,competition,disputes,notifications}`＋`core`＋`worker`，每個模組有 router、service、repository、models。本 Epic 的實體歸屬：identity 擁有 Account、School、AccountToken、OrganizerApplication；notifications 擁有 Notification、EmailDelivery；core 擁有 AuditLog、OutboxEvent。跨模組只能呼叫對方 `service.py` 的公開函式，回傳 Pydantic schema；呼叫方向固定為 disputes → competition → registration → tournaments → identity；沒有模組可以直接呼叫 notifications（只能發事件）；core 不 import 任何模組。
- **分層與交易**：router 負責帳號層級權限（`Depends`：已登入、`require_verified`、平台管理員、主辦方），並開啟、提交交易；service 負責業務規則、資源層級權限（`core.authz`，只比對已載入的物件，不查資料庫）、寫操作紀錄、發事件。service 與 repository 不得 commit 或 rollback。worker 每處理一則事件就是一個獨立交易，重複執行沒有副作用，每 15～30 秒輪詢；API 程序裡不得有排程器。
- **core 介面**：`clock.now()` 是後端唯一取得目前時間的方式，測試時可替換；`BusinessError` 的回應格式為 `{"detail":{"code":"UPPER_SNAKE","message":"繁中訊息"}}`，422 沿用 FastAPI 預設；`events.publish(session, event)` 在同一交易寫入 OutboxEvent（交易回滾時事件不存在）；`audit.record(操作者, tournament_id, 動作, 對象, 變更前, 變更後)` 與 `list_for_tournament()`，AuditLog 帶 `tournament_id`（帳號類操作為空），以（tournament_id, at）建索引，由資料庫 trigger 拒絕 UPDATE 與 DELETE，worker 的操作者記為 `system`。
- **事件**：名稱用過去式 PascalCase；內容只帶實體 id 與事件特有的資料，不帶收件人；收件人由 notifications 依事件類型登錄的規則查詢，以（事件 id、收件人）唯一約束去重。`VerificationEmailRequested`、`PasswordResetRequested` 帶 token 明文，只建立 EmailDelivery。
- **資料**：AccountToken 欄位為 `purpose`（`verify_email`／`reset_password`）、`token_hash`、`expires_at`、`used_at`。Account 帶 `email_verified`、`is_platform_admin`、`is_organizer`。School 的初始資料（教育部大專校院名錄）由遷移檔載入，並提供公開的學校清單 API。
- **慣例**：ID 用 UUID v4；時間以 `timestamptz` 存 UTC，API 回傳 ISO 8601，前端顯示 Asia/Taipei；API 路徑 `/api/v1/<複數資源>`、kebab-case、巢狀不超過兩層；資料表 snake_case 單數；每個 Story 的 schema 變更各自一支 Alembic 遷移檔。
- **狀態列舉**：一律用英文 `StrEnum`，只能經唯一的轉換函式修改。賽事、報名、場次沿用期中文件的代號：Tournament `upcoming/open/closed/published/ongoing/finished/cancelled`；Registration `forming/pending/accepted/waitlisted/rejected/withdrawn/drawn/retired/disqualified`；Match `scheduled/live/appeal_window/appealed/confirmed/voided`。ApplicationStatus（待審核／核准／退回）、DeliveryStatus（待寄／已寄出／失敗）的英文值由 Story 1.1 依同一慣例訂定。
- **前端**：頁面放 `src/routes/`（TanStack Router 檔案路由），元件與 hooks 放 `src/features/<模組>/`；只能呼叫 `@hey-api/openapi-ts` 產生的 client（要有重新產生 client 的指令），不手寫 fetch 或 axios。只用 TanStack Query 輪詢，本 Epic 只有一種：未讀通知數每 30 秒。身分清單由一支後端 API 依帳號資料產生。
- **測試**：pytest 連線 compose 裡的 PostgreSQL 18，禁止 SQLite；測試放 `backend/tests/<模組>/` 與 `frontend/tests/`；與到期時間有關的測試以替換 `core.clock` 推進時間，不等待真實時間。
- **待決**：登入憑證過期的處理方式（憑證時效、是否保留正在填寫的表單、導向 S6 並帶 `redirect`）在 Story 1.4 開工時定案，結果寫回 epics 的〈待決事項〉第 7 項。

## UX & Interaction Patterns

- **主題**：T1 深空霓虹的色票、字級、圓角與具名間距一律以 DESIGN.md frontmatter 為準。無後綴的值寫在 `:root`（淺色），`-dark` 的值寫在 `.dark`，別名槽位依〈Colors〉別名表；FLOW 色（`brand`、`status-*`、`search-highlight`）在 `@theme inline` 註冊。`<html>` 預設帶 `class="dark"`；主題切換存在 `localStorage`，不跟隨作業系統偏好。不載入 webfont；卡片不加陰影。
- **外框**：頂欄有 L2 lockup（`< sm` 只顯示標誌本體）、主題切換，登入後另有鈴鐺與身分切換器。後台頁（S35）用 shadcn `Sidebar`，寬 240px，`< lg` 收進 `Sheet`。
- **身分切換器**：目前身分以 2px `brand` 左條標示，底部為「帳號資料」「登出」；切換身分只改變導覽與首頁，不改變權限。登入後：有 `redirect` 參數時回原頁；只有 1 種身分時到 S1；擁有 2 種以上身分時，第一次到 S11，之後到上次使用的身分首頁（存於 `localStorage`）。登出不需確認。
- **路由**（[ASSUMPTION]）：S5 `/signup`、S6 `/login`、S7 `/verify-email`、S8 `/forgot-password`、S9 `/reset-password`、S10 `/account`、S11 `/me`、S14 `/notifications`、S15 `/organizer/apply`、S35 `/admin/applications`；S38 為 403／404 錯誤頁。
- **通用行為**：422 欄位錯誤顯示在欄位下方；業務錯誤照實顯示 `detail.message`（表單送出時在表單頂部 `Alert`，其他動作以 Toast 顯示並保留到使用者關閉）；成功的 Toast 一句話、3 秒消失。首次載入用 `Skeleton`；主要按鈕送出中顯示 spinner 並停用；不做 optimistic update；每個畫面最多一個主要按鈕。未登入時嘗試寫入，導向 S6 並帶 `redirect`；Email 未驗證時動作停用，並寫「完成 Email 驗證後才能…」＋「重寄驗證信」。
- **本 Epic 建立、後續重用的元件**：Empty state、Status badge（藥丸形、永遠帶文字、tone 依 DESIGN.md 對照表）、Data table（每頁 20 筆、狀態欄可篩選、分頁與篩選寫入 URL 查詢參數、`< md` 改為卡片清單）、AlertDialog 包裝（標題寫動作、內文寫後果、確認鈕重複動作名、可設定必填的理由欄）、School picker（`Popover`＋`Command` 可搜尋下拉，不分大小寫、部分符合，沒有符合時顯示「找不到這間學校」，不能自由輸入）。
- **時間與通知**：絕對時間一律用 `10/18（六）19:00` 格式（Asia/Taipei，跨年才加年份）。Email 共用一個版型：主旨＝通知 `title`，內文一段說明＋一個按鈕，寄件者名稱「FLOW」，驗證信與重設密碼信也用這個版型。不做「全部標為已讀」，也不提供通知偏好設定。
- **文案**：按鈕用動詞＋名詞，不用「確定」「Submit」；不用驚嘆號與表情符號。

## Cross-Story Dependencies

- 1.1 是所有 Story 的前提（模組骨架、core 介面、compose、第一個平台管理員）；1.2 提供所有頁面共用的外框、主題、錯誤與 Toast 處理。
- 1.3 建立 School 表與學校清單 API、AccountToken、outbox → worker → EmailDelivery 的寄信管線與 School picker；1.5 重用 token 與寄信管線，1.4、1.7 重用 School picker。
- 1.4 的 `require_verified`、身分清單 API 與身分切換器，在 1.7、1.8 加上「申請成為主辦方」入口與「主辦方」身分（核准後，在下次輪詢到核准通知時刷新）。
- 1.6 建立 Notification、事件類型登錄機制與 Empty state，1.7、1.8 的通知依賴它；1.7 建立 Status badge；1.8 建立後台 Sidebar 版面、Data table 與 AlertDialog 包裝。
- 跨 Epic：平台管理員維護學校清單的畫面在 Story 2.1；操作紀錄的查閱介面在 Story 2.8；後續 Epic 只要登錄新的事件類型就能發通知，新身分（主辦方後台、我的隊伍、裁判）也加進同一份身分清單。
