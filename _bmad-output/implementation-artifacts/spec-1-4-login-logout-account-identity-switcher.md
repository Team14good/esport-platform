---
title: 'Story 1.4：登入、登出、帳號資料與身分切換器'
type: 'feature'
created: '2026-10-27'
status: 'done'
baseline_commit: '9d8985e6f8df5b9ace2d72f948499ee1a7c6fe2f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 帳號能註冊與驗證，但還不能登入；後端沒有「已登入」「Email 已驗證」「平台管理員」的權限依賴，前端也沒有身分切換器、帳號資料頁與身分首頁的導向規則，之後所有需要登入的功能都無從開始。

**Approach:** 後端以 JWT（`Authorization: Bearer`）建立登入 API、目前帳號、帳號資料修改與身分清單 API，並在 core 提供 `CurrentAccount`、`require_verified`、`require_platform_admin` 依賴；前端做 S6 登入、S10 帳號資料、S11 身分選擇與頂欄身分切換器，處理登入後導向、未登入導向 S6，以及登入過期。

## Boundaries & Constraints

**Always:**
- 權限一律在伺服器端檢查（AD-10）：帳號層級的檢查用 router 的 `Depends`；前端隱藏或停用按鈕不算權限檢查。
- 登入失敗不論 Email 不存在、密碼錯誤或格式不符，回應的狀態碼與訊息都完全相同，不透露帳號是否存在。未驗證 Email 的帳號可以登入，只有套用 `require_verified` 的 API 回 403 `EMAIL_NOT_VERIFIED`。
- 未登入呼叫任何寫入 API 一律回 401；只有明確列在公開清單的端點例外（註冊、驗證 Email、重寄驗證信、登入，以及之後 1.5 的忘記／重設密碼），並以測試逐一檢查所有寫入路由。
- 身分清單只由後端依帳號資料產生，前端不自行判斷身分；切換身分只改變導覽與首頁，不改變權限。
- Email 一律正規化後比對（沿用 1.3 的 `normalize_email`）；顯示名稱與學校沿用 1.3 的驗證規則與 School picker。
- 時間經 `core.clock.now()`；介面文字繁體中文；錯誤呈現沿用 Story 1.2 的錯誤工具。

**Never:**
- 不做忘記／重設密碼（1.5）、通知中心與鈴鐺（1.6）、主辦方申請與「主辦方後台」身分（1.7）、S35 平台管理頁面（1.8）。
- S10 不提供修改 Email 與密碼。
- 不修改既有的遷移檔；本 Story 若有 schema 變更，新增一支遷移。
- 不修改 `_bmad/`、`docs/`、`.claude/`；規劃文件只改 `epics.md` 的〈待決事項〉第 7 項與 `epic-1-context.md` 的對應待決行；不建立 commit。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 登入成功 | 正確的 Email（大小寫、前後空白不拘）與密碼 | 200，回傳 access token；之後帶 `Authorization: Bearer` 可呼叫需要登入的 API | N/A |
| 登入失敗 | Email 不存在，或密碼錯誤 | 兩者都是 401 `INVALID_CREDENTIALS`「Email 或密碼錯誤。」，回應完全相同 | 前端顯示在表單頂部 Alert |
| 未驗證帳號登入 | 帳號 `email_verified=false` | 可以登入 | N/A |
| 需要驗證的 API | 未驗證帳號呼叫套用 `require_verified` 的 API | 403 `EMAIL_NOT_VERIFIED` | 前端對應動作停用，顯示「完成 Email 驗證後才能…」＋「重寄驗證信」 |
| 未登入寫入 | 沒帶 token 呼叫任何非公開的寫入 API | 401 `AUTHENTICATION_REQUIRED` | 前端導向 S6 並帶 `redirect` 回原頁 |
| token 無效或過期 | 帶過期、簽章錯誤或帳號不存在的 token | 401 `AUTHENTICATION_REQUIRED` | 依 Decisions 的「登入過期」處理 |
| 身分清單 | 一般帳號／平台管理員 | 一般帳號只有「瀏覽賽事」；平台管理員另有「平台管理」 | N/A |
| 平台管理員 API | 非平台管理員呼叫套用 `require_platform_admin` 的 API | 403 `PLATFORM_ADMIN_REQUIRED` | N/A |
| 登入後導向 | 有 `redirect` | 回到 `redirect`（只接受站內路徑，沿用 1.3 的檢查） | 不合格的 `redirect` 視為沒有 |
| 登入後導向 | 沒有 `redirect`，只有 1 種身分 | 到 S1 `/` | N/A |
| 登入後導向 | 沒有 `redirect`，2 種以上身分 | 第一次到 S11 `/me`；之後到 `localStorage` 記住的上次身分首頁 | 記住的身分已不在清單內時視同第一次 |
| 修改帳號資料 | 在 S10 改顯示名稱與學校（可清除學校） | 200；Email 唯讀不可改 | 學校不在清單回 422 `SCHOOL_NOT_FOUND`；顯示名稱規則同 1.3 |
| 登出 | 在切換器按「登出」 | 清除登入狀態並回到 S1，不需確認 | N/A |

## Decisions（2026-10-27 定案）

- **登入時效 7 天**：`ACCESS_TOKEN_EXPIRE_MINUTES` 預設改為 `60 * 24 * 7`；不做 refresh token。
- **登入過期時不保留表單內容**（〈待決事項〉第 7 項）：已登入狀態下任何 API 回 401 時，清除 token、顯示「登入已過期，請重新登入。」，導向 S6 並帶 `redirect` 回原頁；登入後回到原頁，表單是空的。登入 API 本身的 401（`INVALID_CREDENTIALS`）不觸發這個流程。
- **「平台管理」直接連到未來路徑 `/admin/applications`**：Story 1.8 做好之前會顯示 S38 404，和 Story 1.2「登入／註冊連到未來路徑」的做法一致。

</frozen-after-approval>

## Code Map

- `backend/app/core/security.py` -- 已有 `create_access_token(subject, expires_delta)`（HS256、`exp` 用 `clock.now()`）與 `verify_password`；本 Story 補上解碼與測試（deferred-work：JWT 函式沒有測試）。
- `backend/app/core/config.py` -- `ACCESS_TOKEN_EXPIRE_MINUTES`（預設 8 天）、`SECRET_KEY`。
- `backend/app/core/errors.py` -- `BusinessError`／`FieldError`。
- `backend/app/core/db.py` -- `SessionDep`；新增的權限依賴可放在 `core/deps.py`，但 core 不能 import 模組（AD-3），帳號查詢要透過 identity 提供的函式（見 Design Notes）。
- `backend/app/modules/identity/{models,repository,service,router}.py` -- 1.3 的 Account、School、`normalize_email`、`DisplayNameField`、`_validate_redirect`、`get_school`、操作紀錄寫法；`router.py` 目前只有公開端點。
- `backend/app/api/main.py` -- 掛載各模組 router；`tests/core/test_app.py` 檢查 OpenAPI 路徑。
- `frontend/src/main.tsx` -- `client.setConfig({ baseURL })`，尚未帶憑證；需加上 Authorization 與 401 處理。
- `frontend/src/components/layout/{TopBar,MobileMenu,Logo}.tsx` -- 「登入」仍是 `<a href="/login">`（deferred-work，本 Story 改成 `<Link>`）；登入後要換成身分切換器；Logo 登入後回到目前身分的首頁。
- `frontend/src/features/identity/{SignupForm,SchoolPicker,schools,redirect,ResendVerificationForm}.tsx|ts` -- 表單、School picker、`safeRedirect`、重寄驗證信可直接沿用。
- `frontend/src/lib/api-error.ts` -- 403 已歸為 `forbidden` 並保留 `code`（例如 `EMAIL_NOT_VERIFIED`）；本 Story 要能分辨 401。
- `frontend/src/components/ui/dropdown-menu.tsx` -- 身分切換器用。
- UX：S6／S10／S11 `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:48、52、53`；身分切換器 `:490-511`、`DESIGN.md:257-261、447`；未驗證 `EXPERIENCE.md:362`；頂欄 `< sm` `EXPERIENCE.md:393`。
- 〈待決事項〉第 7 項：`_bmad-output/planning-artifacts/epics.md:195`（格式比照 `:189-194` 已定案的項目）；`epic-1-context.md:42`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/core/security.py` -- 新增 `decode_access_token`；過期、簽章錯誤、格式錯誤都回傳 None。
- [x] `backend/app/core/config.py`、`.env.example`（若有對應設定）-- `ACCESS_TOKEN_EXPIRE_MINUTES` 預設改為 7 天。
- [x] `backend/app/modules/identity/` -- `authenticate`、`get_current_account`（給依賴用）、`list_identities`、`update_profile` service；schema `AccessToken`、`AccountRead`、`Identity`、`ProfileUpdate`；API `POST /access-tokens`、`GET /accounts/me`、`PATCH /accounts/me`、`GET /accounts/me/identities`。
- [x] `backend/app/core/deps.py`（或依 Design Notes 的位置）-- `CurrentAccount`、`VerifiedAccount`（`require_verified`）、`PlatformAdmin`（`require_platform_admin`）。
- [x] `backend/tests/` -- 涵蓋 I/O 矩陣後端各列；一支測試列舉所有寫入路由，未帶 token 時除公開清單外都回 401；`create_access_token`／`decode_access_token`／`verify_password` 的測試。
- [x] `frontend/src/features/identity/auth.ts`（或同等位置）-- token 存取、目前帳號與身分清單的 query、登出、上次身分。
- [x] `frontend/src/main.tsx` -- client 帶 `Authorization`；401 依定案處理。
- [x] `frontend/src/routes/{login,account,me}.tsx` 與 `features/identity/` -- S6、S10、S11；`/account`、`/me` 未登入時導向 S6 並帶 `redirect`。
- [x] `frontend/src/components/layout/` -- 身分切換器（`DropdownMenu`；目前身分 2px `brand` 左條；底部「帳號資料」「登出」；另有「全部身分」連到 S11）、登入後的頂欄（`< sm` 時切換器縮成圖示）、Logo 回到目前身分首頁、「登入」改成 `<Link>`。
- [x] `frontend/src/features/identity/VerificationRequired.tsx` -- 未驗證時停用動作並顯示「完成 Email 驗證後才能…」＋「重寄驗證信」的共用元件（1.7 起套用到實際動作）。
- [x] `frontend/tests/unit/` -- 登入、導向規則、身分切換器、S10、登出、401 處理、未驗證元件。
- [x] `_bmad-output/planning-artifacts/epics.md`、`_bmad-output/implementation-artifacts/epic-1-context.md` -- 〈待決事項〉第 7 項改為「已定案（2026-10-27）」並寫入定案內容。
- [x] `backend/pyproject.toml` -- `[tool.coverage.report]` 設 `fail_under = 85`（deferred-work：coverage 沒有門檻）。

**Acceptance Criteria:**
- Given 服務已啟動，when 以已驗證的帳號在 S6 登入，then 頂欄出現身分切換器、「登入」「註冊」消失；重新整理後仍是登入狀態。
- Given 首位平台管理員登入，when 開啟身分切換器，then 看到「瀏覽賽事」與「平台管理」，目前身分有 brand 左條，底部有「帳號資料」「登出」。
- Given 未登入，when 開啟 `/account?x=1`，then 導向 `/login?redirect=…`，登入後回到 `/account?x=1`。
- Given 1280 與 375 px 寬，when 瀏覽 S6、S10、S11 與開啟身分切換器，then 沒有橫向捲軸，介面文字全部為繁體中文。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

### Review Findings

2026-10-28 Code Review（Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）。

- [x] [Review][Decision] 登入、登出只清 `ME_QUERY_KEY` 底下的快取 — `signIn`、`signOut` 只移除 `["identity","me",…]`。之後的 Story 若新增與帳號有關、卻不在這個前綴底下的 query（我的隊伍、報名、裁判指派），同一分頁換帳號時會看到前一個帳號的資料。要選：改用 `queryClient.clear()`，或在 `auth.ts` 寫明「與帳號有關的 query 一律放在 `ME_QUERY_KEY` 底下」的約定。→ 定案：換帳號時清掉所有 query（`removeQueries()`，不清 mutation，避免影響進行中的登入），轉為 patch 並已套用。
- [x] [Review][Patch] 重新登入後「登入已過期」Toast 不會消失（Toast 設成永久顯示，`signIn` 沒有關閉它） [frontend/src/features/identity/auth.ts:191]
- [x] [Review][Patch] 其他分頁直接改登另一個帳號時，本分頁仍顯示前一個帳號的資料，但請求已改用新帳號的 token（storage 事件沒有清除目前帳號的快取） [frontend/src/features/identity/auth.ts:271]
- [x] [Review][Patch] 登入後取得身分清單沿用預設重試，5xx 時登入按鈕約轉 7 秒才導向（`fetchQuery` 要加 `retry: false`） [frontend/src/features/identity/LoginForm.tsx:58]
- [x] [Review][Patch] `scripts/test.sh -k audit` 這類篩選執行會因 `fail_under = 85` 一定失敗，`coverage html` 也不會執行 [backend/scripts/test.sh:8]
- [x] [Review][Patch] 身分圖示對照表宣告成 `Record<string, LucideIcon>`，之後新增身分忘了補圖示時編譯器不會報錯（改用產生的 `IdentityKey`） [frontend/src/features/identity/identity-icons.ts:8]
- [x] [Review][Patch] 測試缺口：超過 128 字元的密碼（正確密碼後面多加字元）被拒絕的檢查沒有測試 [backend/app/modules/identity/service.py:274]
- [x] [Review][Patch] 測試缺口：`signIn` 清掉前一個帳號快取的行為沒有測試 [frontend/src/features/identity/auth.ts:192]
- [x] [Review][Patch] 測試缺口：`HrefLink` 把修飾鍵、非左鍵點擊交給瀏覽器的行為沒有測試 [frontend/src/components/common/HrefLink.tsx:20]
- [x] [Review][Patch] 測試缺口：其他分頁登入、登出時頂欄同步的 storage 事件處理沒有測試 [frontend/src/features/identity/auth.ts:65]
- [x] [Review][Patch] deferred-work 中「JWT 函式沒有測試／coverage 沒有門檻」與「『登入』仍是 `<a href="/login">`」兩筆已在本 Story 完成，仍列為未處理 [_bmad-output/implementation-artifacts/deferred-work.md:22]
- [x] [Review][Defer] 正式啟動程式（`main.tsx`）接上 Bearer 與 401 攔截器的設定沒有測試 [frontend/src/main.tsx:24] — deferred: 要有第一個 Playwright e2e 規格才能涵蓋（登入後開 `/account`），超出本 Story 範圍；`configureApiClient` 本身已有單元測試。

**Rejected：**
- `FIRST_ADMIN_PASSWORD` 超過 128 字元時首位管理員無法登入 — low：要把環境變數設得極長才會發生，修正要加設定驗證。
- 登入 body 的 email／password 不是字串時回 422 而非 401 — low：前端一律送字串，docstring 的「格式不符」指 Email／密碼格式；修正要加分支。
- 回傳的 `expires_at` 比 token 實際到期晚最多 1 秒 — low：前端沒有使用 `expires_at`，修正要改 `create_access_token` 的參數。
- 登入前送出、登入後才回來的舊 401 會把剛登入的人登出 — low：要在登入的同時有請求進行中，修正要加判斷。
- localStorage 無法寫入時，記憶體中的值會蓋過其他分頁的變更 — low：只在 localStorage 丟例外時發生，此時其他分頁通常也無法寫入。
- 身分清單、目前帳號查詢持續失敗（非 401）時，切換器一直顯示 Skeleton、`VerificationRequired` 一直停用且沒有說明 — low：只在後端持續故障時發生，修正要在三個元件各加錯誤分支。
- `redirect=/login` 時登入後回到登入頁 — low：只有手動拼出的網址會發生，修正要加判斷。
- 只有一種身分時應前往該身分首頁而非 `/` — false：Design Notes 規定只有 1 種身分時到 S1，而唯一的身分「瀏覽賽事」首頁就是 `/`。
- `LoginForm` 吞掉取得身分清單的 401 後仍導向 `/` — low：要新簽發的 token 立刻失效（帳號被刪、多台後端金鑰不同）才會發生，修正要加判斷。
- `VerificationRequired` 說明文字沒有 `aria-describedby`、`<fieldset disabled>` 擋不住連結 — low：本 Story 還沒有任何實際套用的動作（1.7 起才套用），屆時再依實際的動作類型處理。
- access token 沒有 `typ`／`aud` — false：目前用 `SECRET_KEY` 簽出的 JWT 只有 access token，驗證信 token 是隨機字串的雜湊。
- `test_auth_required.py` 只測沒帶 token 的情況 — low：所有權限依賴都經過 `get_current_account`，過期與簽章錯誤已在 `test_login.py` 測過。
- 登入失敗沒有寫應用程式 log — low：規劃文件沒有這項要求，屬於新功能；與頻率限制一起由 PM／架構決定。
- Ctrl／Cmd＋點擊 S11 的身分卡片開新分頁時也會改掉上次身分 — low：很少見，修正要改 `HrefLink` 的介面。
- Logo 在身分清單載入中退回 `/` 沒有測試 — low：只是退回預設值。
- `docs/midterm/docx` 的四份 Word 檔被修改 — false：不在 diff 內，修改時間早於本 Story 開工。
- Intent 寫「在 core 提供依賴」但實作在 identity — 修正要改 spec 本身，不在審查範圍內。
- 登入過期時被擋下的表單短暫顯示「請先登入。」 — low：攔截器同時導向 S6，頁面隨即卸載。

## Implementation Notes

- 沒有 schema 變更，所以沒有新增遷移。
- FastAPI 0.141 起 `app.routes` 不再展開 include 的 router，`test_auth_required.py` 改從 OpenAPI 規格列舉寫入路由；另有一支測試禁止在 `app/` 使用 `include_in_schema`，避免路由被漏掉。之後 Story 1.5 的忘記／重設密碼端點要加進 `PUBLIC_WRITE_ROUTES`。
- API client 的設定（`baseURL`、Bearer、401 攔截器）在 `features/identity/auth.ts` 的 `configureApiClient`；QueryClient 在 `lib/query-client.ts`，401 不重試。
- 「目前身分」是記住的上次身分，不從網址推算：在「平台管理」身分下點「賽事」，目前身分仍是「平台管理」。
- 手動檢查（實作子代理以首位平台管理員執行）：未登入開 `/account?x=1` 導向 S6 並在登入後回到原頁；切換器內容與 brand 左條正確；重新整理仍登入；S10 改名成功；帳密錯誤、假 token 導回 S6 並顯示「登入已過期」；登出回到 S1；1280 與 375 px 寬都沒有橫向捲軸。
- 本機未進版控的 `.env` 的 `ACCESS_TOKEN_EXPIRE_MINUTES` 也從 11520 改成 10080，讓執行中的服務與新預設一致。

## Spec Change Log

## Review Triage Log

| # | 來源 | 位置 | 發現 | 判定 | 去向 | 依據 |
|---|------|------|------|------|------|------|
| 1 | verification-gap | `frontend/src/main.tsx` | 沒有測試確認 client 會帶 `Authorization: Bearer`、401 攔截器有註冊 | medium | patch | 所有 auth 測試都 mock `IdentityService`，請求不經過 axios；刪掉 `auth:` 那行測試仍全過，正式環境卻會一登入就被登出。 |
| 2 | verification-gap | `LoginForm.tsx` | 登入後身分清單失敗時退回 `/` 的分支沒有測試 | low | patch | 沒有測試讓 `listCurrentIdentities` reject；補一個測試即可。 |
| 3 | verification-gap | `tests/identity/test_login.py` | 7 天預設值的測試讀到的是 `.env`／compose 注入的值，不是程式預設 | low | patch | compose 一定注入 10080；把 `config.py` 改回 8 天，測試仍會通過。 |
| 4 | blind＋edge | `auth.ts` `writeStorage` | localStorage 被封鎖時登入後 token 沒存住，使用者被導回 S6，註解卻寫「只在這個分頁有效」 | low | patch | `getAccessToken` 只讀 localStorage，沒有記憶體備援；補一個模組變數讓行為符合註解。 |
| 5 | blind＋edge | `auth.ts` 401 handler | 舊 token 的請求在重新登入後才回 401，會清掉新 token | low | reject | 要在使用者輸入帳密的幾秒內仍有舊請求未回應才會發生，日常不會遇到；修正要多一個比對分支。 |
| 6 | blind＋edge | `auth.ts` `subscribe` | 其他分頁換帳號／登出時，這個分頁的帳號快取沒清 | low | reject | React Query 預設切回分頁時重新取資料，畫面會自行更新；修正要多一個監聽器。 |
| 7 | blind | 前端 | 沒使用 `expires_at`，過期 token 會先顯示已登入的畫面再被導回 | low | reject | 第一個 API 回 401 就導向，只是短暫閃動；修正要多存一個值與判斷。 |
| 8 | blind＋edge | `service.authenticate` | `expires_at` 與 JWT `exp` 取了兩次時間且 `exp` 截到秒，最多差 1 秒 | low | reject | 前端沒有使用 `expires_at`；修正要改 `create_access_token` 的介面。 |
| 9 | blind | JWT 格式 | 沒有 `iat`／token 版本，重設密碼後舊 token 仍有效 7 天 | medium（未證實是否為需求） | defer | Story 1.5 的需求範圍，交給 1.5 決定。 |
| 10 | blind | `POST /access-tokens` | 沒有頻率限制或失敗鎖定 | medium（規劃文件未規定） | defer | 規劃文件沒有這項規則（見 Story 1.4 調查），不是本 Story 造成的缺口。 |
| 11 | blind＋edge | `_dummy_password_hash` | 第一次「Email 不存在」的請求多算一次雜湊 | low | reject | 每個程序只發生一次，不足以推測帳號是否存在。 |
| 12 | blind | `ProfileUpdate` | 送 `email` 欄位會被默默忽略並回 200 | low | reject | 前端不會送；改成禁止多餘欄位會出現英文錯誤訊息，要另外處理。 |
| 13 | blind＋edge | `VerificationRequired` | 帳號資料載入中或載入失敗時，被保護的動作仍可使用 | low | patch | `!account.data` 時直接原樣顯示；已登入但還不知道驗證狀態時應先停用。 |
| 14 | blind | `IdentitySwitcher` | 身分清單 API 非 401 失敗時，trigger 一直顯示 Skeleton | low | reject | 選單仍有「帳號資料」「登出」可用，且 React Query 會重試；只有後端故障時才會遇到。 |
| 15 | blind | S10 | 已登入但未驗證的帳號在任何畫面都找不到「重寄驗證信」 | low | patch | 已確認登入後的介面沒有連到 S7；在 S10 的 Email 說明旁加上按鈕，沿用重寄的 API。 |
| 16 | blind | `PUBLIC_WRITE_ROUTES` | 公開寫入清單放在 identity，其他模組之後要公開寫入得改 identity | low | reject | 目前所有公開寫入端點都在 identity；未來的需求只是推測。 |
| 17 | blind | `test_auth_required.py` | 用字串比對 `include_in_schema` 太脆弱 | low | reject | 誤判時測試會明確失敗，不會默默漏掉。 |
| 18 | blind | spec／sprint-status | 狀態不一致、Code Map 寫 8 天、Implementation Notes 空白 | false | reject | sprint-status 依流程在完成時才改為 done；Code Map 描述的是改動前的程式；Notes 會在 Step 5 補上。 |
| 19 | blind | `LoginForm` | 導向規則有兩份，`postLoginDestination` 的 redirect 分支正式程式沒用到 | low | patch | 直接把 `redirect` 交給 `postLoginDestination`，有 redirect 時不取身分清單。 |
| 20 | blind | `service.get_current_account` | `raise` 沒加 `from None` | low | patch | 一行修正。 |
| 21 | blind | S10 | 沒有改動時按儲存仍顯示「已更新」 | false | reject | PATCH 成功、資料確實是最新，訊息正確。 |
| 22 | blind | `/login` | 已登入的使用者開啟 `/login` 仍看到表單 | low | reject | 不影響安全，重新登入也會正常運作；修正要多一個導向分支。 |
| 23 | edge | `main.tsx` QueryClient | 401 時預設重試 3 次，每次都觸發 401 處理 | low | patch | 正式環境的 QueryClient 沒設 retry；401 重試沒有意義，改成不重試 401。 |
| 24 | edge | `LoginForm` | redirect 指向 `/login` 或 `/signup` 時，登入後又回到那頁 | low | reject | 要手動輸入這種網址才會發生，且只是回到該頁。 |
| 25 | edge | `requireSignedIn` | 網址超過 2000 字時 redirect 會被丟掉 | low | reject | 實際網址不會這麼長。 |
| 26 | edge | `HrefLink` | `target="_blank"` 時仍在同一分頁開啟 | low | reject | 目前沒有任何地方這樣使用。 |
| 27 | edge | `authenticate` | 舊 bcrypt 帳號與不存在的 Email 回應時間不同 | low | reject | 只差在雜湊演算法；帳號在第一次登入後就升級成 argon2。 |
| 28 | edge | `authenticate` | 無法辨識的雜湊格式會回 500 | false | reject | 雜湊只由程式產生，沒有途徑寫入無法辨識的格式。 |
| 29 | edge | `AccessTokenCreate` | email／password 不是字串時回 422，不是 401 | low | reject | 型別錯誤的 422 不透露帳號是否存在，不違反 Intent。 |
| 30 | edge | `ProfileUpdate.school_id` | 不是 UUID 時回英文的 pydantic 訊息 | low | reject | 前端只會送學校清單裡的 id。 |
| 31 | edge | `update_profile` | 同一帳號同時送兩個 PATCH 可能互相覆蓋 | low | reject | 只有本人會改自己的資料，後送出的那筆勝出，結果仍合理。 |
| 32 | edge | `update_profile` | 檢查後學校被刪除會回 500 | false | reject | 學校資料只由遷移匯入，沒有刪除的途徑。 |
| 33 | edge | `auth.test.tsx` | 測試另建 QueryClient，沒有驗證畫面上用的 client | false | reject | 這個測試檢查的是 handler 會清掉傳入的 client，傳入哪一個 client 由第 1 項的測試涵蓋。 |
| 34 | edge | `identity/deps.py` | Intent 寫「在 core 提供依賴」，實作放在 identity | low | reject | 修正方式是改 spec 的文字；Design Notes 已依 AD-3 說明要放在 identity。 |

## Design Notes

**登入與憑證**：`POST /api/v1/access-tokens`，JSON `{email, password}` → `{access_token, token_type: "bearer", expires_at}`。前端存在 `localStorage["flow-access-token"]`，每個請求帶 `Authorization: Bearer`；登出只在前端清除（無狀態 JWT，不做伺服器端撤銷）。不做 refresh token。

**權限依賴與 AD-3**：core 不能 import 模組。做法是由 identity 提供依賴：`identity/deps.py` 定義 `CurrentAccount = Annotated[AccountRead, Depends(get_current_account)]`、`VerifiedAccount`、`PlatformAdmin`，其他模組的 router 直接 import 這些依賴（呼叫方向符合 disputes → … → identity）。token 解碼放在 `core/security.py`。

**錯誤碼**：`INVALID_CREDENTIALS`（401，「Email 或密碼錯誤。」）、`AUTHENTICATION_REQUIRED`（401，「請先登入。」，回應帶 `WWW-Authenticate: Bearer`）、`EMAIL_NOT_VERIFIED`（403，「完成 Email 驗證後才能使用這個功能。」）、`PLATFORM_ADMIN_REQUIRED`（403，「只有平台管理員可以使用這個功能。」）。登入失敗時即使 Email 不存在也要跑一次密碼雜湊比對，回應時間不洩漏帳號是否存在。

**身分清單**：`GET /api/v1/accounts/me/identities` → `[{key, label, home_path}]`，依序 `browse`「瀏覽賽事」`/`；`platform_admin`「平台管理」`/admin/applications`。之後的 Story 在同一個 service 函式加入「我的隊伍」「裁判」「主辦方後台」。

**帳號資料**：`PATCH /api/v1/accounts/me` 接受 `display_name`、`school_id`（可為 null 以清除）；寫操作紀錄 `account.profile_updated`（before／after 只含有變動的欄位）。登入不寫操作紀錄。

**上次身分**：`localStorage["flow-last-identity"]` 存 `key`；登出時保留，下次登入沿用。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy（若新增遷移，套用成功）。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過，涵蓋 I/O 矩陣後端各列，coverage 達 `fail_under`。
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bun run --filter frontend typecheck` -- expected: 無錯誤。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。

**Manual checks (if no CLI):**
- 以瀏覽器用首位平台管理員登入 → 頂欄出現身分切換器，有「瀏覽賽事」「平台管理」→ 重新整理仍是登入狀態 → 到 S10 改顯示名稱 → 登出回到 S1；在 1280 與 375 px 寬各看一次 S6、S10、S11 與切換器。
