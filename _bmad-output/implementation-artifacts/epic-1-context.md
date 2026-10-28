# Epic 1 Context: 平台基礎、帳號與通知中心

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

用官方全端範本建立可以 `docker compose up` 一鍵啟動的系統骨架、core 共用元件與 FLOW 前端外框，讓之後每個 Epic 都沿用同一套模組結構、交易／事件／操作紀錄／權限／時鐘介面與共用 UI 元件。同時完成整個帳號生命週期：註冊、Email 驗證（可重寄）、登入、登出、重設密碼、身分切換器、主辦方申請與平台管理員審核，並以 outbox 驅動站內通知與 Email。這個 Epic 是整個平台的地基，這裡定下的慣例，後續 Epic 直接繼承、不再重新決定。1.1～1.5 已完成；期中（11/18）前還要做 1.7、1.8，通知中心 1.6 擱置到期中後。

## Stories

- Story 1.1: 以官方範本建立可一鍵啟動的專案骨架（已完成）
- Story 1.2: FLOW 前端外框與主題（已完成）
- Story 1.3: 以 Email 註冊並完成驗證（已完成）
- Story 1.4: 登入、登出、帳號資料與身分切換器（已完成）
- Story 1.5: 忘記與重設密碼（已完成）
- Story 1.6: 通知中心（期中擱置）
- Story 1.7: 申請成為主辦方
- Story 1.8: 平台管理員審核主辦方申請

## Requirements & Constraints

- **帳號**：同一個 Email 不能重複註冊（`EMAIL_ALREADY_REGISTERED`）；密碼至少 8 個字元、只存雜湊；學校為選填，只能從學校清單選擇（存 `school_id`）。登入失敗時不透露帳號是否存在。
- **Email 驗證閘門**：未驗證的帳號不能申請主辦方或報名，API 回 403 `EMAIL_NOT_VERIFIED`；未登入呼叫任何寫入 API 一律回 401。權限一律在伺服器端檢查，前端隱藏按鈕不算權限檢查。
- **一次性連結**：驗證連結 24 小時、重設連結 1 小時，用一次就失效；同一帳號、同一用途重新產生時，舊 token 全部作廢。重寄驗證信與申請重設密碼，不論 Email 是否存在，回應都相同。
- **主辦方申請**：同一帳號同時只能有一筆待審核（`APPLICATION_PENDING`）；退回必須填原因，申請人可以修改後重送、次數不限；核准後 `is_organizer` 立即生效。申請與審核都要寫操作紀錄。第一個平台管理員依 `.env` 在啟動時建立。
- **期中範圍**：通知中心（1.6）擱置。1.7、1.8 原本「收到站內通知與 Email」的地方，只在同一個交易裡用 `core.events.publish` 發出事件，不在 notifications 登錄收件規則（worker 會略過沒有登錄的事件並標為已處理）。1.8 核准後，申請人重新整理頁面或重新登入才會出現「主辦方」身分；S15 的唯讀摘要顯示目前的申請狀態（待審核、核准，或退回與原因）。
- **非功能**：375 px 寬沒有橫向捲軸，介面全部繁體中文；compose 一個指令就能啟動全部服務。

## Technical Decisions

- **堆疊**：`fastapi/full-stack-fastapi-template` 起始；Python 3.14、FastAPI、SQLModel、Alembic、PostgreSQL 18、React 19.3、TS 6.0、Vite 8.3、TanStack Router／Query、Tailwind 4.2＋shadcn/ui、Bun。版本由 `uv.lock`、`bun.lock` 固定；不得產生 `package-lock.json`。compose 只有 `db`、`backend`、`worker`、`frontend`、`mailpit` 五個服務。
- **模組化單體**：identity 擁有 Account、School、AccountToken、OrganizerApplication；notifications 擁有 Notification、EmailDelivery；core 擁有 AuditLog、OutboxEvent。跨模組只呼叫對方 `service.py` 的公開函式並回傳 Pydantic schema；呼叫方向固定為 disputes → competition → registration → tournaments → identity；沒有模組可以直接呼叫 notifications（只能發事件）；core 不 import 任何模組。
- **分層與交易**：router 用 `Depends` 做帳號層級權限並提交交易；service 做業務規則、資源層級權限（`core.authz`，只比對已載入的物件）、寫操作紀錄、發事件；service 與 repository 不得 commit 或 rollback。worker 每處理一筆就是一個獨立交易，重複執行沒有副作用；API 程序裡不得有排程器。
- **core 介面**：`clock.now()` 是唯一取得目前時間的方式；`BusinessError` 回應 `{"detail":{"code","message"}}`，422 沿用預設；`events.publish(session, event)` 與業務資料同一交易；`audit.record(...)` 只增不改（資料庫 trigger 拒絕 UPDATE、DELETE），以（tournament_id, at, seq）建索引，worker 的操作者記為 `system`。
- **事件**：名稱用過去式 PascalCase；只帶實體 id 與事件特有資料，不帶收件人；收件人由 notifications 依事件類型登錄的規則決定，以（事件 id、收件人）去重。`VerificationEmailRequested`、`PasswordResetRequested` 只建立 EmailDelivery。
- **登入憑證**：JWT 7 天、不做 refresh token；已登入狀態下任何 API 回 401 時清除 token、顯示「登入已過期，請重新登入。」並導向 S6 帶 `redirect`，不保留表單；登入 API 本身的 401 不觸發。Account 帶 `credentials_version`，token 帶 `ver` claim，重設密碼成功時＋1，舊 token 全部失效；重設成功也把未驗證帳號標為已驗證。
- **慣例**：UUID v4；`timestamptz` 存 UTC，前端顯示 Asia/Taipei；API `/api/v1/<複數資源>`、kebab-case；狀態用英文 `StrEnum`、只能經唯一的轉換函式修改；每個 Story 的 schema 變更各自一支 Alembic 遷移檔。
- **前端**：頁面放 `src/routes/`，元件與 hooks 放 `src/features/<模組>/`；只能呼叫產生的 client。身分清單由一支後端 API 依帳號資料產生。期中沒有任何輪詢（未讀數輪詢屬於 1.6）。
- **測試**：pytest 連 compose 的 PostgreSQL 18，禁止 SQLite；與到期時間有關的測試以替換 `core.clock` 推進時間。

## UX & Interaction Patterns

- **主題與外框**：T1 深空霓虹 token 以 DESIGN.md 為準，預設深色、主題存 `localStorage`；卡片不加陰影。後台頁用 shadcn `Sidebar`（寬 240px，`< lg` 收進 `Sheet`，選擇後自動關閉）。
- **身分切換器**：目前身分以 2px `brand` 左條標示，底部「帳號資料」「登出」；切換身分只改導覽與首頁，不改權限。
- **路由**：S15 `/organizer/apply`、S35 `/admin/applications`；S38 為 403／404 錯誤頁。
- **通用行為**：422 欄位錯誤在欄位下方；業務錯誤照實顯示 `detail.message`；成功 Toast 一句話、3 秒消失；首次載入用 `Skeleton`；送出中按鈕顯示 spinner 並停用；不做 optimistic update；每個畫面最多一個主要按鈕。Email 未驗證時 S15 表單整個停用並連到 S7。
- **本 Epic 建立、後續重用的元件**：Status badge（1.7：藥丸形、永遠帶文字、tone 依 DESIGN.md 對照表，「進行中」「申訴中」帶脈動點）；後台 Sidebar 版面、Data table（每頁 20 筆、狀態欄可篩選、分頁與篩選寫入 URL、`< md` 改卡片清單）、AlertDialog 包裝（標題寫動作、內文寫後果、確認鈕重複動作名、可設定必填理由欄）（1.8）。School picker 已在 1.3 建立。
- **文案**：按鈕用動詞＋名詞（「核准」「退回申請」），不用「確定」；不用驚嘆號與表情符號。

## Cross-Story Dependencies

- 1.7 重用 1.3 的 School picker 與 1.4 的身分切換器、`VerifiedAccount`；1.8 依賴 1.7 的申請資料。
- **跨人交接**：1.8 的後台版面、Data table、AlertDialog 要在 11/1 前完成，B 的 2.1、2.2 畫面會用到。
- 跨 Epic：學校清單維護畫面在 2.1；操作紀錄查閱頁面（2.8）期中擱置；新身分（主辦方後台、我的隊伍、裁判）都加進同一份身分清單。期末做 1.6 時，為期中各 Story 已發出的事件登錄收件規則。
