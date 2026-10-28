---
title: 'Story 1.5：忘記與重設密碼'
type: 'feature'
created: '2026-10-28'
status: 'done'
baseline_commit: '34ab8567bad58a666c9b5789bf911297bb34d032'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 忘記密碼的使用者目前只能重新註冊，舊帳號就回不去了；S6 沒有「忘記密碼」入口，也沒有 S8、S9。

**Approach:** 沿用 1.3 的 AccountToken 與 outbox 寄信管線：S8 申請重設信（不論 Email 是否存在回應都相同），S9 以 1 小時、一次性的重設連結設定新密碼後導向 S6。

## Boundaries & Constraints

**Always:**
- 重設 token 依 AD-21 存在 AccountToken（`purpose=reset_password`、只存 SHA-256 雜湊、1 小時到期）；同帳號重新申請時刪除尚未使用的舊重設 token。
- 申請重設：Email 不存在時不產生 token 與事件，但狀態碼、回應內容與畫面訊息都與已註冊時相同；未驗證 Email 的帳號也能申請。
- `PasswordResetRequested` 只建立 EmailDelivery、不建立站內通知；寄出前 token 已失效（用過、過期、被重新申請作廢）就不寄（比照驗證信）；寄送結束後移除 payload 裡的 token 明文。
- 新密碼沿用註冊的規則（`PasswordField`：8～128 字元）；設定後 token 寫入 `used_at`，舊密碼無法登入、新密碼可以登入。
- 重設成功寫操作紀錄 `account.password_reset`（before／after 不含任何密碼或雜湊）。
- 與到期有關的測試替換 `core.clock` 推進時間（AD-13）。

**Never:**
- 不做頻率限制或鎖定（與登入相同，見 deferred-work）。
- 重設成功後不自動登入。
- 不修改 `docs/`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 申請：已註冊 | S8 送出已註冊的 Email（大小寫、空白不同也算） | 202；畫面顯示「若這個 Email 已註冊，重設信會在幾分鐘內寄達。」；建立 token 與 `PasswordResetRequested` | N/A |
| 申請：未註冊 | S8 送出未註冊的 Email | 與上一列完全相同的 202 與畫面訊息；不產生 token 與事件 | N/A |
| 申請：格式不符 | Email 空白或格式錯誤 | 422，錯誤顯示在欄位下方 | 前端先擋 |
| 重新申請 | 同帳號申請兩次 | 只有第二封信的連結有效；第一封還沒寄出時不寄 | N/A |
| 開啟 S9：有效連結 | 網址帶有效 token | 顯示「新密碼」欄位與「設定新密碼」 | N/A |
| 開啟 S9：失效連結 | token 已用過、超過 1 小時、被重新申請作廢、不存在或缺少 | 不顯示密碼欄位；顯示「此重設連結已失效。」＋「重新寄送重設信」（→ S8） | 400 `RESET_LINK_INVALID`「此重設連結已失效。」 |
| 設定新密碼 | 有效 token＋合格新密碼 | 204；導向 S6 並顯示 Toast「密碼已重設，請用新密碼登入。」 | N/A |
| 新密碼不合格 | 少於 8 或超過 128 字元 | 422，錯誤顯示在欄位下方，token 不會被用掉 | N/A |
| 送出時才失效 | 開啟 S9 後連結過期或被作廢，再送出 | 400 `RESET_LINK_INVALID`，畫面換成失效狀態 | 同上 |

## Decisions（2026-10-28 定案）

- **重設密碼後登出其他裝置**：重設成功後，之前簽發的 access token 一律失效（回 401，前端照 1.4 的登入過期流程處理）；重設後重新登入拿到的新 token 正常可用。
- **重設成功視為 Email 已驗證**：未驗證的帳號完成重設時，一併設 `email_verified = true` 並寫 `account.email_verified` 操作紀錄。
- **保留完整 spec**（約 3,200 tokens，不拆分）。

</frozen-after-approval>

## Code Map

- `backend/app/modules/identity/models.py` -- `TokenPurpose.RESET_PASSWORD` 已存在；`AccountToken`、`VerificationEmailRequested`（新事件比照它）、`PasswordField`、`EmailField`、`VerificationEmailCreate`（申請重設的 body 比照，但不帶 redirect）。
- `backend/app/modules/identity/service.py:104` `_issue_verification_token`、`:176` `verify_email`（`for_update` 鎖 token、失效判斷）、`:207` `is_verification_token_active`、`:223` `resend_verification`（Email 不存在時靜默返回）——重設的申請、檢查、設定照同樣寫法；`hash_token`、`normalize_email`、`get_password_hash` 直接沿用。
- `backend/app/core/security.py:23` `create_access_token(subject, expires_delta)`、`:30` `decode_access_token` -- 加上憑證版本 claim（見 Design Notes）；`tests/core/test_security.py` 有既有測試要一起更新。
- `backend/app/modules/identity/service.py:258` `authenticate`（簽發 token）、`:289` `get_current_account`（解碼後比對版本）。
- `backend/app/alembic/versions/` -- 1.3 的 `4c1d9a7e2f30_story_1_3_signup_and_email_verification.py` 是最新一支；新增 `story_1_5` 遷移檔加 Account 欄位（`server_default` 0）；`tests/test_migrations.py` 會檢查遷移與模型一致。
- `backend/app/modules/identity/repository.py` -- `add_token`、`get_token_by_hash(..., for_update)`、`delete_unused_tokens(account_id, purpose)` 直接沿用。
- `backend/app/modules/identity/router.py:26` `PUBLIC_WRITE_ROUTES` -- 新的公開端點都要加進來（`tests/test_auth_required.py` 會檢查）；router 負責 commit。
- `backend/app/modules/notifications/service.py` -- `dispatch_event`、`_compose`、`send_next_email` 目前只認 `VERIFICATION_EMAIL_REQUESTED`；加上 `PasswordResetRequested` 的分支、`reset_password_link(token)`（`FRONTEND_HOST` 去掉結尾斜線＋`/reset-password?token=`）、失效時以 `_StaleEmail` 跳過、結束後 `events.drop_payload_keys(..., "token")`。事件類型登錄機制在 1.6，本 Story 先用分支。
- `backend/tests/identity/test_signup.py`、`backend/tests/notifications/test_email_delivery.py` -- 驗證 token 與驗證信的測試寫法（`frozen_clock`、假 EmailSender）可照抄。
- `frontend/src/routes/verify-email.tsx`、`frontend/src/features/identity/VerifyEmailPage.tsx` -- `validateSearch` 寫法、以 `useQuery`（`retry: false`、`staleTime: Infinity`）送 token 只送一次、`PageCard`、失效畫面；S9 照這個結構。
- `frontend/src/features/identity/ResendVerificationForm.tsx` -- S8 表單照抄（zod Email 驗證、`applyFieldErrors`、成功訊息不透露帳號是否存在）。
- `frontend/src/features/identity/SignupForm.tsx` -- 密碼的 zod 規則（`PASSWORD_MIN_LENGTH`／`MAX`）與 `PasswordInput`（`autoComplete="new-password"`）。
- `frontend/src/routes/login.tsx` -- 在密碼欄位附近加「忘記密碼」連到 `/forgot-password`。
- UX：S8／S9 `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:50-51`、失效 `:353`；FR-40 `prds/prd-se-final-project-2026-10-14/prd.md:156`；AD-21 `ARCHITECTURE-SPINE.md:192`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/identity/models.py`、`backend/app/alembic/versions/` -- Account 新增 `credentials_version: int`（預設 0）與遷移檔；`PasswordResetRequested(account_id, token)` 事件；schema `PasswordResetEmailCreate{email}`、`PasswordResetCheck{token}`、`PasswordResetCreate{token, new_password: PasswordField}`。
- [x] `backend/app/core/security.py`、`backend/app/modules/identity/service.py` -- access token 帶憑證版本，`get_current_account` 版本不符回 401 `AUTHENTICATION_REQUIRED`。
- [x] `backend/app/modules/identity/service.py` -- `request_password_reset(email)`、`is_reset_token_active(token)`、`check_reset_token(token)`（失效拋 `RESET_LINK_INVALID`）、`reset_password(token, new_password)`（鎖 token 與帳號、更新雜湊、`credentials_version`＋1、`used_at`、未驗證時一併驗證、操作紀錄）。
- [x] `backend/app/modules/identity/router.py` -- 三支公開端點（見 Design Notes）並加進 `PUBLIC_WRITE_ROUTES`。
- [x] `backend/app/modules/notifications/service.py` -- 重設信的分派、版型、失效跳過與移除 token 明文。
- [x] `backend/tests/identity/test_password_reset.py`、`backend/tests/notifications/test_email_delivery.py` -- 涵蓋 I/O 矩陣後端各列、1 小時到期（替換時鐘）、舊密碼失效、重設前簽發的 token 回 401、重設後的新 token 可用、未驗證帳號重設後變成已驗證、重設信不建站內通知、失效 token 不寄信。
- [x] `scripts/generate-client.sh` -- 重新產生前端 client（`frontend/src/client`）。
- [x] `frontend/src/routes/{forgot-password,reset-password}.tsx` 與 `frontend/src/features/identity/{ForgotPasswordForm,ResetPasswordPage}.tsx` -- S8、S9；S6 加「忘記密碼」連結。
- [x] `frontend/tests/unit/{forgot-password,reset-password}.test.tsx` -- 涵蓋 I/O 矩陣前端各列與 S6 的連結。
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`、`epic-1-context.md` -- 刪除 deferred-work 中「access token（JWT）只有 `sub` 與 `exp`……重設密碼後舊 token 仍有效」那一筆（本 Story 已處理）；epic-1-context〈Technical Decisions〉補一句：重設密碼會讓之前簽發的 token 失效。

**Acceptance Criteria:**
- Given 服務已啟動，when 在 S6 點「忘記密碼」、在 S8 送出已註冊的 Email，then Mailpit 收到主旨「重設 FLOW 的密碼」的信，點信中的按鈕開啟 S9。
- Given 在 S9 設定新密碼後，when 回到 S6，then 舊密碼登入回 401 `INVALID_CREDENTIALS`、新密碼可以登入；再開一次同一封信的連結顯示「此重設連結已失效。」。
- Given 375 px 寬，when 瀏覽 S8、S9，then 沒有橫向捲軸，介面文字全部為繁體中文。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

### Review Findings

第二輪 Code Review（2026-10-28，Blind Hunter、Edge Case Hunter、Verification Gap、Acceptance Auditor）。

- [x] [Review][Patch] 瀏覽器留著失效的 token 時，開啟 S9（以及 S7、S8、註冊頁）會被 401 導回 S6 [`frontend/src/features/identity/auth.ts:264`] — 使用者決定（2026-10-28）：在 `/signup`、`/verify-email`、`/forgot-password`、`/reset-password` 這四個免登入的帳號頁收到 401 時，只清掉 token，不顯示 Toast、不導向 S6；其他頁面維持 1.4 的行為；補前端測試。原始發現：這個瀏覽器的 token 已過期，或在別的裝置重設過密碼而 `ver` 不符時，TopBar 的 `IdentitySwitcher` 會用 `useCurrentAccount` 打 `/accounts/me`，拿到 401。`auth.ts` 的 `createUnauthorizedHandler` 只放過 `/login`，所以會清掉 token、跳出「登入已過期，請重新登入。」，並導到 `/login?redirect=/reset-password?token=…`，重設流程就此中斷。使用者要回信箱再點一次連結才能繼續，重設 token 也被帶進 S6 的網址。忘記密碼的人很可能就是久沒登入、token 已過期的人；1.5 的 `ver` 也讓別台裝置更常出現這種失效的 token。（medium；來源：Edge Case Hunter，已查證 `auth.ts:264-270` 與 `useIsSignedIn` 只看 token 是否存在）
- [x] [Review][Patch] deferred-work 的 1.5 項目沒有自己的標題，排在 1.4 的標題下 [`_bmad-output/implementation-artifacts/deferred-work.md:22`] — 寫入本輪延後項目時已補上 `## Deferred from: code review of spec-1-5-forgot-reset-password.md (2026-10-28)`，既有項目內容沒有改動。
- [x] [Review][Patch] 沒有 `ver` 的舊 token 沒有 API 層級的測試 [`backend/tests/identity/test_password_reset.py`] — 只測了 `decode_access_token`；要補「沒有 `ver` 的 token 對版本 0 的帳號，`/accounts/me` 回 200；重設一次後回 401」，對應 Design Notes「不會讓現有登入全部失效」。
- [x] [Review][Patch] 兩支重設信測試假設 `FRONTEND_HOST` 沒有結尾斜線 [`backend/tests/notifications/test_email_delivery.py`] — `test_reset_password_link_points_to_s9` 與 `test_sent_reset_email_has_subject_body_button_and_link` 直接拿 `settings.FRONTEND_HOST` 比對；程式本身有 `rstrip("/")`，所以測試要改成和 `settings.FRONTEND_HOST.rstrip("/")` 比對。
- [x] [Review][Defer] 「重設信不建立站內通知」沒有斷言 [`backend/tests/notifications/test_email_delivery.py`] — deferred：目前還沒有 notification 表，要等 Story 1.6 建立站內通知時補斷言。
- [x] [Review][Defer] 遷移測試不比對 server default，也沒有測到「有資料的資料庫升級」 [`backend/tests/test_migrations.py:14`] — deferred：pre-existing（Story 1.1 起只開 `compare_type`）；開 `compare_server_default` 前，要先確認其他欄位沒有誤報。

**Rejected**

- `signOut` 不論登入的是誰都會執行（BH＋EC）：low。要在同一個瀏覽器以 A 登入、再重設 B 的密碼才會發生；前端只拿得到 token，不知道是哪個帳號，修正要新增 API 回傳或加判斷。
- spec 的 `status: done` 與 sprint-status 的 `review` 不一致（BH＋AA）：本次審查結束時會一併同步，而且修正等於改 spec。
- 「忘記密碼」連結在送出按鈕下方，不在密碼欄位旁（BH）：low。UX 只規定 S6 要有這個入口；手動檢查時已看過位置。
- `reset_password` 在持有鎖時才跑 argon2（BH）：low。只有同一帳號同時申請與重設時才會多等幾百毫秒；把雜湊提前到驗證 token 之前，反而會讓無效 token 也耗掉 argon2 的 CPU。
- 操作紀錄的 `before` 在＋1 之後才回推（BH）：false。目前的值是對的；文中說的錯誤要先改動程式才會發生。
- `get_account_by_email(for_update=True)` 沒有 `populate_existing`（BH）：low。現有呼叫端在鎖之前都沒有載入過同一個帳號，讀不到舊值；沒有能證明的錯誤狀態。
- S8 再送一次會作廢前一封信，畫面沒有提示（BH）：low。開到舊連結時，S9 的失效畫面已說明「之後又申請過重設信，就會失效」，並附重新寄送；改提示文案屬於 UX 決定。
- Code Map 的行號已過時、Implementation Notes 有工作過程的敘述（BH）：修正等於改 spec。
- notifications 的事件清單與 `_compose` 分支是兩處平行的清單（BH）：Story 1.6 會改成事件類型登錄機制，本 Story 依 spec 先用分支。
- 缺少 token 時 API 回 422，不是 400（AA）：low。網址沒有 token 時前端直接顯示失效，不會送出；422 的 token 欄位錯誤，前端也會顯示失效畫面，使用者看到的行為符合矩陣。
- S9 錯誤畫面的按鈕叫「重試」，不是動詞＋名詞（AA）：Design Notes 明定用「重試」，也與 S7 一致；要改需另外決定。
- 內容損壞的重設事件會把 token 明文留在 outbox（AA）：low。沿用 1.3 的既有行為，正常流程不會產生這種事件；修正要多加分支。
- deferred-work 的並行測試項目沒有點到 `get_account` 的 `populate_existing`（VG other）：low。該項已涵蓋 `reset_password` 的整段鎖定重查；既有項目不能修改。

## Implementation Notes

- 遷移檔 `9e5b3f1a7c42_story_1_5_password_reset.py`：`account.credentials_version`（`server_default` 0）。
- `decode_access_token` 改回傳 `AccessTokenClaims(subject, version)`；`ver` 不是非負整數時視為無效 token。
- `reset_password` 先鎖帳號再鎖 token（與申請重設相同順序，避免同時進行時互相等待）；`get_token_by_hash(for_update=True)` 加 `populate_existing`，鎖住後一定讀到資料庫最新值。
- 重設成功後前端呼叫 `signOut`（`auth.ts` 改為 export）：這個瀏覽器原本的 token 已失效，不清掉的話到 S6 會先跳一次「登入已過期」。
- `PageCard` 從 `VerifyEmailPage.tsx` export 給 S9 共用；密碼規則抽成 `SignupForm.tsx` 的 `passwordSchema`。
- 實作子代理中途被停止；後端由子代理完成，前端、client 重新產生、文件收尾與驗證由主 session 接手。子代理寫入的檔案是 CRLF，已全部轉回 LF。
- 測試輔助函式 `_latest_token` 原本以 `created_at` 排序，凍結時鐘下會取到舊 token；改為取帳號唯一尚未使用的 token。
- 手動檢查：以 API 走完「註冊 → 登入 → 申請重設 → Mailpit 收信（主旨、寄件者 FLOW、1 小時文案、連結）→ 檢查 → 設定新密碼 → 同一連結失效 → 舊密碼 401、新密碼 200 → 舊 token 401、新 token 200 且 `email_verified=true`」；瀏覽器 375 px 看過 S6 連結、S8 送出後訊息、S9 失效畫面與表單、設定成功後導向 S6 的 Toast，皆無橫向捲軸。

## Spec Change Log

## Review Triage Log

| # | 來源 | 發現 | 判定 | 依據 | 處理 |
|---|------|------|------|------|------|
| 1 | VG＋BH | `reset_password` 的鎖定重查與 `populate_existing` 沒有並行測試 | medium（未證實） | 測試 fixture 共用一條連線，無法互搶鎖；要另一套測試架構 | defer |
| 2 | BH | `create_access_token` 的 `version` 預設 0，之後新增簽發處漏傳會悄悄失效 | low | 開發者新增簽發處時會踩到；改必填是直接修正 | patch |
| 3 | BH＋EC | `reset_password` 用 `assert account is not None` | low | `-O` 下被移除；改成 `RESET_LINK_INVALID` 是直接修正 | patch |
| 4 | EC | `get_account(for_update=True)` 不會刷新 identity map 裡已載入的帳號 | low | SQLAlchemy 只有 `populate_existing` 才覆蓋已載入的屬性；目前呼叫端都還沒載入過帳號，但註解宣稱會刷新 | patch |
| 5 | BH | `test_requesting_again_before_send_only_sends_the_newest_reset_link` 依 `created_at` 排序取第二則 | low | 時間相同時順序不固定；改以 id 排除 | patch |
| 6 | BH | `test_expired_reset_link_is_not_sent` 沒檢查 `attempts`、`last_error`、payload 移除 token | low | 過期後 token 明文留在資料庫的退步測不出來 | patch |
| 7 | BH | 前端缺送出時 422 token 欄位、500 的測試；S8 缺 500 測試 | low | 分支存在但沒有測試 | patch |
| 8 | BH | `PasswordResetCheck` 說明「不使用 token」會被誤讀；新測試斷言 `"notification" not in metadata.tables` 會在 1.6 失敗 | low | 用詞改「不會用掉 token」；移除新測試的表名斷言（1.3 既有的那行留給 1.6 處理） | patch |
| 9 | EC | 重設信沒有頻率限制，可灌爆收件匣並一直作廢對方的連結 | medium | Never 明定不做頻率限制 | defer |
| 10 | BH | 「1 小時」寫死在信件、S8、S9 三處 | low | 只有改 TTL 時才會說錯，修正要新增共用常數 | reject |
| 11 | BH | token 留在網址列、瀏覽紀錄與 Referer | low | 與 1.3 驗證連結相同做法；頁面沒有外部資源，Referer 只送到自家 API；修正要改路由行為 | reject |
| 12 | BH＋EC | 申請重設的回應時間會透露 Email 是否已註冊 | low | 已註冊路徑只多幾毫秒的資料庫寫入（不像登入有 argon2 的百毫秒差距），要大量取樣才量得出；修正要補假工作或固定延遲 | reject |
| 13 | BH | 重設成功沒有寄「密碼已變更」通知信 | low | intent 沒有這項；需要新事件與信件 | reject |
| 14 | BH | 重設後未使用的驗證 token 留在表裡，且排隊中的驗證信不寄沒有測試 | low | `is_verification_token_active` 會檢查帳號已驗證而不寄；殘留 token 不能再驗證出不同結果 | reject |
| 15 | BH | S8 送出成功後改 Email，成功訊息仍在 | low | 訊息本身是「若這個 Email 已註冊」的通用句；修正要加變更處理 | reject |
| 16 | EC | 重設信重試多次後才寄出，信中「1 小時內有效」但只剩幾分鐘 | low | 只有 SMTP 連續失敗時才會發生；修正要加剩餘時間門檻 | reject |
| 17 | EC | 送出時發現失效後，同一 token 重新掛載會因快取再顯示表單 | low | 要從別處再回到同一網址才會發生，送出時會再顯示失效；修正要加快取清除 | reject |

## Design Notes

**API**（路徑比照 1.3 的 `/verification-emails`、`/email-verifications`）：
- `POST /api/v1/password-reset-emails` `{email}` → 202（無內容；Email 存在與否都相同）。
- `POST /api/v1/password-reset-checks` `{token}` → 204／400 `RESET_LINK_INVALID`：S9 開啟時檢查，不使用 token。用 POST 是為了不讓 token 出現在 API 的存取紀錄網址裡。
- `POST /api/v1/password-resets` `{token, new_password}` → 204／400 `RESET_LINK_INVALID`／422。先驗證 body（不合格的密碼不會用掉 token），再鎖住 token 判斷是否有效。

**登出其他裝置**：Account 加 `credentials_version`（int，預設 0），access token 加 claim `ver`；`get_current_account` 在 `ver` 與帳號目前的值不同時回 401。重設成功時＋1。沒有 `ver` 的 token（本 Story 上線前簽發）視為 0，不會讓現有登入全部失效。用版本號而不是 `password_changed_at`＋`iat`：JWT 的 `iat` 只到秒，重設後同一秒內重新登入的 token 會被誤判為舊 token。

**重設信**：主旨「重設 FLOW 的密碼」，內文「點下方按鈕設定新密碼，連結 1 小時內有效。如果你沒有申請重設密碼，可以忽略這封信。」，按鈕「設定新密碼」。

**S9**：以 `useQuery` 送檢查（只送一次）；有效時顯示新密碼表單；任何一步回 `RESET_LINK_INVALID` 或 422 的 token 欄位錯誤，都顯示失效畫面；連線或伺服器錯誤顯示「重試」，不當成失效。成功後 `navigate({ to: "/login", replace: true })`，讓上一頁不會回到帶 token 的網址。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy（若新增遷移，套用成功）。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過，coverage 達 `fail_under`。
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bun run --filter frontend typecheck` -- expected: 無錯誤。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。

**Manual checks (if no CLI):**
- S6 →「忘記密碼」→ S8 送出 → Mailpit 開信 → S9 設定新密碼 → S6 以新密碼登入；同一連結再開一次顯示失效；375 px 寬看一次 S8、S9。
