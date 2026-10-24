---
title: 'Story 1.3：以 Email 註冊並完成驗證'
type: 'feature'
created: '2026-10-24'
status: 'done'
baseline_commit: '37720e47a401a924348729b4870e64fe814254a1'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 平台還沒有任何帳號建立方式；訪客需要用 Email 註冊、收驗證信完成驗證，後續的登入、報名與主辦方申請才有帳號可用。寄信也還沒有管線。

**Approach:** 在 identity 建立 School（附大專校院名錄初始資料與公開清單 API）、AccountToken 與註冊／驗證／重寄的 service；在 core 建立 `events.publish` 與 OutboxEvent；在 notifications 建立 EmailDelivery 與寄信，由 worker 逐筆處理；前端做 S5 註冊頁（含 School picker）與 S7 驗證頁。

**Decisions（2026-10-24 使用者決定）：**
- 重寄驗證信以 Email 識別：S7 有 Email 欄位（註冊後自動帶入剛註冊的 Email）；不論 Email 是否存在、是否已驗證，回應都相同，只有未驗證的帳號真的會寄出（不透露帳號是否存在）。
- 學校清單：實作時從政府資料開放平臺下載教育部「大專校院名錄」CSV，只取校名，整理成本 Story 遷移檔的初始資料；README 註明資料來源與下載日期。
- 密碼規則：至少 8 個字元，不限字元種類。
- spec 超過 1,600 tokens，使用者選擇保留完整 spec、不拆分。

## Boundaries & Constraints

**Always:**
- 交易：註冊、重寄、驗證各是一個使用案例＝一個交易，由 router commit；帳號、token 與 OutboxEvent 寫在同一個交易裡。worker 每處理一則事件、每寄一封信各是一個獨立交易（AD-5）。
- token 只存 SHA-256 雜湊，明文只出現在事件 payload 與信件連結；驗證 token 24 小時到期、用過即失效；同帳號重新產生時舊的驗證 token 全部作廢（AD-21）。
- Email 一律以去除前後空白、轉小寫後的值儲存與比對，資料庫以 `lower(email)` 唯一。
- 驗證信只建立 EmailDelivery、不建站內通知；以（event_id, account_id）唯一約束去重；寄信失敗記錄 `attempts` 與 `last_error`，之後的輪詢再試，第 5 次仍失敗就標為 `failed` 不再重試。
- 時間一律經 `core.clock.now()`；寄信經可替換的 EmailSender，測試以假物件替換、以 `frozen_clock` 推進時間，不等待真實時間。
- 前端只用產生的 client；錯誤呈現沿用 Story 1.2 的 `applyFieldErrors`／`FormErrorAlert`／`notifyError`；介面文字繁體中文。

**Never:**
- 不做登入、登出、`require_verified`、身分切換器（Story 1.4）；註冊後不自動登入。
- 不做重設密碼（1.5）、通知中心與事件類型登錄機制（1.6）；本 Story 只為 `VerificationEmailRequested` 寫最小的分派。
- 不做平台管理員維護學校清單的畫面（2.1）。
- 不修改 Story 1.1 的遷移檔；schema 變更新增一支本 Story 的遷移。
- 不修改 `_bmad/`、`docs/`、`.claude/` 與規劃文件；不建立 commit。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 註冊成功 | 新 Email、合規密碼、顯示名稱、學校（選填） | 201；帳號 `email_verified=false`、密碼只存雜湊、`school_id` 正確或為空；同交易有一筆 `verify_email` token 與一則 `VerificationEmailRequested` 事件；前端導向 S7「請收信驗證」 | N/A |
| Email 已註冊 | Email 與既有帳號只差大小寫或前後空白 | 409 `EMAIL_ALREADY_REGISTERED` | 前端顯示在表單頂部 Alert |
| 密碼太短 | 密碼少於 8 個字元 | 422，錯誤顯示在密碼欄下方，不建立帳號 | N/A |
| 學校不在清單 | `school_id` 不存在 | 422 `SCHOOL_NOT_FOUND`，不建立帳號 | 前端顯示在學校欄下方 |
| 交易回滾 | 註冊過程在 commit 前失敗 | 帳號、token、OutboxEvent 都不存在 | N/A |
| worker 寄出驗證信 | 有未處理的 `VerificationEmailRequested` | 下一輪建立 EmailDelivery 並寄出，Mailpit 收到一封寄件者「FLOW」、含驗證連結的信；事件標記已處理 | N/A |
| 重複處理同一事件 | 同一事件被處理兩次 | 只有一筆 EmailDelivery、只寄一封信 | 唯一約束擋下第二筆 |
| 寄信失敗 | SMTP 拋錯 | 該筆 `attempts`+1、記錄 `last_error`，其他事件照常；之後的輪詢再試；第 5 次失敗後為 `failed` | 不中斷 worker |
| 驗證成功 | 24 小時內第一次開啟連結 | 帳號 `email_verified=true`、token 寫入 `used_at`；S7 顯示驗證成功 | N/A |
| 連結失效 | 同一連結第二次開啟、已過期、或已被重寄作廢 | 400 `VERIFICATION_LINK_INVALID`；S7 顯示連結已失效與「重寄驗證信」 | N/A |
| 重寄 | 在 S7 輸入未驗證帳號的 Email 重寄 | 202；產生新 token、舊驗證 token 全部作廢、發出新事件；舊連結之後無法驗證 | N/A |
| 重寄不存在或已驗證的 Email | Email 沒有註冊，或帳號已驗證 | 202，回應與上一列完全相同；不產生 token、不發事件 | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/modules/identity/{models,repository,service,router}.py` -- 已有 `Account`（無 `school_id`）、`TokenPurpose`、`ensure_first_admin`；新增 School、AccountToken、`school_id`、註冊／驗證／重寄。
- `backend/app/core/security.py` -- `get_password_hash`（pwdlib argon2）沿用。
- `backend/app/core/clock.py`、`core/audit.py`、`core/db.py` -- 沿用 `clock.now()` 與 `SessionDep`（router commit）。
- `backend/app/worker/__init__.py:21-41` -- `Job = Callable[[Session], None]`、`run_once` 每個 job 一個交易；AD-5 要求每則事件一個交易，與目前介面衝突（見 Design Notes）。`worker/jobs.py` 的 `JOBS` 目前為空。
- `backend/app/modules/notifications/models.py` -- 已有 `DeliveryStatus`（pending/sent/failed）；資料表尚未建立。
- `backend/app/core/config.py:42-62`、`compose.yml:41-48` -- SMTP 指向 mailpit:1025、`EMAILS_FROM_NAME=FLOW`、`FRONTEND_HOST`；`emails`、`jinja2` 套件已安裝。
- `backend/app/modules/__init__.py` -- 新的 models 要讓 alembic 與 worker 都載入。
- 資料表定義：`docs/midterm/B-軟體需求分析文件.md:716-750`（ACCOUNT、SCHOOL、ACCOUNT_TOKEN）、`:1018-1031`（EMAIL_DELIVERY）、`:1048-1056`（OUTBOX_EVENT）；介面：`_bmad-output/planning-artifacts/architecture/architecture-se-final-project-2026-10-14/c-d-design-groundwork.md:224-239、322、673-679`。
- `frontend/src/lib/api-error.ts`、`feedback.ts`、`components/common/FormErrorAlert.tsx` -- Story 1.2 的錯誤工具，表單直接使用。
- `frontend/src/components/layout/{TopBar,MobileMenu}.tsx` -- 「註冊」目前是 `<a href="/signup">`，本 Story 改成 `<Link>`（「登入」維持到 1.4）。
- `frontend/src/components/ui/` -- 沒有 `popover`、`command`；School picker 需新增這兩個 shadcn 元件（依賴 `@radix-ui/react-popover`、`cmdk`）；`password-input.tsx` 的 aria label 仍是英文。
- UX：S5／S7 `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/EXPERIENCE.md:47-49、245、353、566、587`；School picker `DESIGN.md:455`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/core/events.py` -- `OutboxEvent` model 與 `publish(session, event)`（事件名稱過去式 PascalCase，payload 只帶 id 與事件特有資料）。
- [x] `backend/app/modules/identity/` -- School model（`name` unique）、Account 加 `school_id`（FK、可空）、AccountToken（purpose、token_hash 索引、expires_at、used_at）；`register`、`verify_email`、`resend_verification` service；`GET /schools`（`PublicSchool` 依名稱排序）、`POST /accounts`、`POST /email-verifications`、`POST /verification-emails`。
- [x] `backend/app/modules/notifications/` -- EmailDelivery model；`dispatch_event`（`VerificationEmailRequested` → 依 payload 的 account_id 建 EmailDelivery）；`send_pending_deliveries`；EmailSender 介面與 SMTP 實作；驗證信版型（Jinja2）。
- [x] `backend/app/worker/` -- 依 Design Notes 讓工作可以逐筆處理，每筆一個交易；登錄 outbox 分派與寄信兩個工作。
- [x] `backend/app/alembic/versions/` -- 新增一支遷移：school（含名錄初始資料）、account.school_id、account_token、outbox_event、email_delivery、`lower(email)` 唯一索引。
- [x] `backend/tests/{identity,notifications,worker,core}/` -- 涵蓋 I/O 矩陣每一列。
- [x] `frontend/src/components/ui/{popover,command}.tsx`、`frontend/src/features/identity/SchoolPicker.tsx` -- 可搜尋下拉（不分大小寫、部分符合、沒有符合時顯示「找不到這間學校」、不能自由輸入、可清除）。
- [x] `frontend/src/routes/signup.tsx`、`frontend/src/routes/verify-email.tsx`、`frontend/src/features/identity/` -- S5 表單（Email、密碼、顯示名稱、學校）；S7 的三種狀態；支援 `redirect` 參數一路帶到驗證成功後的「繼續」連結。
- [x] `frontend/src/components/layout/{TopBar,MobileMenu}.tsx` -- 「註冊」改為 `<Link to="/signup">`。
- [x] `frontend/src/client/`、`frontend/tests/unit/` -- 重新產生 client；前端單元測試涵蓋表單錯誤對應、S7 各狀態與 School picker 的搜尋。

**Acceptance Criteria:**
- Given 服務已啟動，when 在 S5 註冊後等待最多 30 秒，then Mailpit 收到一封驗證信，點信中的按鈕回到 S7 並顯示驗證成功，資料庫中該帳號 `email_verified=true`。
- Given S5，when 在學校欄輸入部分校名（例如「臺灣大學」），then 下拉只列出名稱包含該字串的學校；輸入不存在的名稱顯示「找不到這間學校」，無法送出自由文字。
- Given 1280 與 375 px 寬，when 瀏覽 S5、S7，then 沒有橫向捲軸，介面文字全部為繁體中文。
- Given 後端與前端，when 執行 Verification 的指令，then 全部通過。

## Implementation Notes

- 學校名錄：政府資料開放平臺 dataset 6091（`https://stats.moe.gov.tw/files/opendata/u1_new.csv`），2026-10-24 下載，取 115 學年度、只取校名，共 139 所；README 與遷移檔都有註明。
- `core/errors.py` 新增 `FieldError`：要查資料庫才知道的欄位錯誤（`SCHOOL_NOT_FOUND`）回 422，格式與 FastAPI 的欄位錯誤相同、`loc` 指向 `school_id`，前端因此能顯示在學校欄下方。
- `email_delivery` 多一個 `next_attempt_at` 欄位：失敗後依 1、2、4、8 分鐘延後重試，同一輪不會立刻重寄；第 5 次失敗設為 `failed`。
- Email 唯一改為 `lower(email)` 唯一索引，取代 Story 1.1 的 `ix_account_email`；遷移時把既有 Email 轉小寫。
- 重新產生驗證 token 時，以刪除同帳號、同用途、尚未使用的 token 來作廢。
- 註冊與驗證成功都寫操作紀錄（`account.registered`、`account.email_verified`）。
- 剛註冊的 Email 以 router 的 history state 帶到 S7，不放進網址；重新整理後就沒有了，使用者要自己輸入。
- 後端 422 的欄位訊息與前端送出前的檢查都是繁體中文。
- 驗證信在按鈕下方多一行純文字連結，以防按鈕無法點選。
- 事件名稱只檢查「PascalCase、至少兩個字」，不強制過去式（`Drawn` 這類不規則動詞無法用字尾判斷）。
- `redirect` 只接受站內路徑，前後端都會檢查。
- 驗證時發現 Windows 的 curl 以命令列參數送中文 JSON 會被轉碼成非 UTF-8 而得到 400；用檔案送出就正常，這是工具的問題，不是程式的問題。
- Code Review 後續修正（2026-10-24，commit 49f7075 之後另以 bmad-code-review 唯讀審查，使用者要求修正「需要立即修正」的項目）：
  - S7 驗證成功後以 `replace` 把網址的 token 換成 `?verified=1`（保留 redirect）；`verified=1` 時直接顯示「Email 驗證完成」，重新整理不會再送已用過的 token。使用者選擇前端做法，不改 I/O 矩陣「同一連結第二次開啟回 400」的規則。`verified=1` 只影響顯示，任何人都能手動打開這個網址看到完成畫面，不涉及帳號狀態。
  - S7 遇到 422（token 格式不合格，例如被截斷或改壞的連結）時視同連結失效，顯示重寄而不是「重試」。
  - notifications 改用 identity 的 `VerificationEmailRequested.event_type` 與 `model_validate`，移除重複的事件名稱字串與 payload 結構。
  - 驗證連結組網址前去掉 `FRONTEND_HOST` 結尾的斜線。
  - redirect 前後端都拒絕 C1 控制字元（U+0080～U+009F），修正 U+0085 前端放行、後端拒絕的不一致。
  - 補測試：密碼 128／129 字元（前後端）、SMTP 的 TLS／SSL／帳號密碼參數、`verified=1` 的網址替換與重新整理、422 視同失效、C1 控制字元、連結結尾斜線、事件名稱來源。
  - 兩個既有的前端測試改為先等網址換成 `verified=1` 再找元素：替換時「驗證完成」卡片會重新掛載，舊的元素參照會失效。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter = BH、Edge Case Hunter = EC、Verification Gap = VG、主流程驗證 = VR）。

| # | 來源 | 發現 | 判定 | 依據 | 去向 |
|---|------|------|------|------|------|
| 1 | EC | `redirect` 夾帶 tab／換行（`/\t/evil.com`）時，瀏覽器會把它去掉，連結變成 `//evil.com`（開放式導向） | medium | 前後端驗證器都沒有擋控制字元；URL 解析器確實會移除 tab 與換行 | patch P9 |
| 2 | EC | 前端 `safeRedirect` 同上 | medium | 同 #1 | patch P9 |
| 3 | BH | 同上（控制字元），另外後端沒有測反斜線 | medium | 同 #1 | patch P9 |
| 4 | BH | 重寄或驗證完成後，舊事件還在待寄的信仍會寄出，裡面的連結已失效 | medium | 使用者在 worker 寄出第一封信之前（最多 30 秒）就按重寄，就會收到兩封信，其中一封無效；`_compose` 寄送前不檢查 token | patch P2 |
| 5 | EC | 同上（token 已被作廢或過期仍寄出） | medium | 同 #4 | patch P2 |
| 6 | BH | token 明文一直留在 `outbox_event.payload`，等於沒有只存雜湊 | low | AD-21 規定事件帶明文，但寄出後就不再需要；token 24 小時到期，且要有資料庫讀取權才拿得到 | patch P1 |
| 7 | EC | 同上 | low | 同 #6 | patch P1 |
| 8 | VG／BH／EC | 分派失敗（非 ValidationError）時，同一則最舊事件會永遠卡在佇列最前面 | maybe-false（若成立為 medium） | 外鍵讓帳號無法刪除，註冊產生的 payload 一定合法；沒能找到 1.3 實際會持續失敗的情況，要用 1.6 的新事件類型才能驗證 | defer D1 |
| 9 | EC | `_compose` 的資料庫錯誤被廣泛的 except 吞掉，之後 flush 失敗，`attempts` 永遠不會增加，同一封信卡在最前面 | maybe-false（若成立為 medium） | 要有持續性的資料庫讀取錯誤才會發生；和 #8 同屬「有毒項目擋住佇列」 | defer D1 |
| 10 | BH／EC | SMTP 寄出後 commit 失敗會重寄（至少一次的語意），程式裡沒有說明 | low | `sender.send` 確實在交易內執行；spec 的「只寄一封」指的是事件去重；在程式加註解即可 | patch P3 |
| 11 | BH | 事件或收件人不存在這類永久性錯誤，也會重試滿 5 次 | low | 外鍵讓事件與帳號不會消失，碰不到；修正要多一個分支 | reject |
| 12 | BH | 前端用 UTF-16 計算字數，後端用 code point，emoji 與擴充區漢字的長度判斷不一致 | low | zod 的 `.min`／`.max` 確實以 UTF-16 code unit 計算；改用 `[...v].length` 是直接修正 | patch P4 |
| 13 | EC | 同上 | low | 同 #12 | patch P4 |
| 14 | BH | 學校排序依賴資料庫 collation，測試拿 Python 排序比對；`>= 139` 太寬鬆 | low | `ORDER BY name` 確實依 collation；指定 `COLLATE "C"` 並改成 `== 139` 是直接修正 | patch P5 |
| 15 | BH | S7 遇到網路錯誤或 500 時仍寫「連結會失效」，也沒有重試按鈕 | low | 確實只依代碼決定標題，內文固定；網路一斷就會碰到 | patch P6 |
| 16 | EC | 同上 | low | 同 #15 | patch P6 |
| 17 | BH | 學校清單載入失敗時，下拉選單仍可展開，顯示空清單和「找不到這間學校」 | low | `isError` 時只換了 placeholder；會讓使用者以為自己的學校不在名單裡 | patch P7 |
| 18 | EC | 同上 | low | 同 #17 | patch P7 |
| 19 | BH | 帶查詢字串或 hash 的 redirect 會被 `<Link to>` 當成路徑 | low | 3.x 的邀請連結很可能帶查詢參數；拆成 pathname／search／hash 是直接修正 | patch P8 |
| 20 | EC | 同上 | low | 同 #19 | patch P8 |
| 21 | BH | `test_smtp_failure_does_not_block_other_events` 沒檢查註冊回 201，又寫死 Email | low | 確實沒有斷言；直接補上 | patch P10 |
| 22 | BH | Mailpit API 的 8025 埠寫死在測試裡 | low | 只在 compose 內執行，埠號固定 | reject |
| 23 | VG | 註冊與驗證的操作紀錄沒有測試 | medium | 刪掉 `audit.record` 不會有測試失敗 | patch P11 |
| 24 | VG | 1、2、4、8 分鐘的退避沒有精確斷言 | low | 現有測試每次推進 1 小時；改成固定 1 分鐘也會通過 | patch P12 |
| 25 | VG | 同時註冊撞唯一索引時回 409 的 service 路徑沒有測試 | medium | 刪掉 service 的 except 會變成 500，沒有測試會失敗 | patch P13 |
| 26 | VG | `ensure_first_admin` 的 Email 正規化沒有大小寫混合的測試 | medium | 刪掉 `normalize_email` 後，含大寫的 `FIRST_ADMIN_EMAIL` 會讓第二次啟動失敗，測試抓不到 | patch P14 |
| 27 | VG | `SmtpEmailSender` 收到失敗回應時會拋錯，這段沒有測試 | medium | `emails` 套件失敗時是回傳物件而不是拋例外；刪掉檢查會把沒寄出的信標成 sent | patch P15 |
| 28 | VR | `bunx tsc -p tsconfig.json` 在 `frontend/tests/unit/signup.test.tsx:193` 報型別錯誤（`Element` 不能當 `HTMLElement`） | low | 驗證時實際執行得到 TSC_EXIT=2；只影響測試檔的型別檢查 | patch P16 |
| 29 | VG | 遷移檔中正規化既有 Email 的 UPDATE 沒有被執行過 | low | 升級前的資料實際上只有首位管理員；寫逐版升級的遷移資料測試不是直接修正 | reject |
| 30 | BH | 重寄與註冊端點沒有頻率限制，可以無限觸發寄信 | low | 依 AD-17 只在本機 compose 執行、信件只寄到 Mailpit；冷卻期會改變 spec「重寄就產生新 token」的行為 | reject |
| 31 | EC | 同上 | low | 同 #30 | reject |
| 32 | EC | 重寄時，未驗證帳號和不存在帳號的回應時間不同，可推測帳號是否存在 | low | 同 #30，只在本機執行；要讓時間一致得重新設計 | reject |
| 33 | EC | `POST /accounts` 的 409 一樣會透露帳號是否存在 | false | 409 `EMAIL_ALREADY_REGISTERED` 是 AC 明定的行為；不透露的要求只針對重寄 | reject |
| 34 | BH | 註冊時 Email 已存在（409），沒有連到重寄驗證信的入口 | low | 不在 spec 範圍內，屬於新功能 | reject |
| 35 | BH | 驗證完成後 token 仍留在網址與瀏覽紀錄裡 | low | token 只能用一次；改用 replace 導航會讓 S7 失去狀態，不是直接修正 | reject |
| 36 | BH | spec 寫 `send_pending_deliveries`，實作是 `send_next_email` | low | 修正是改 spec，依規則駁回；Implementation Notes 已記下逐筆處理的設計 | reject |
| 37 | EC | 同上 | low | 同 #36 | reject |
| 38 | BH | 遷移檔沒有處理只差大小寫的既有重複資料；`btrim` 與 `strip()` 處理的空白字元不同 | low | 既有資料只有首位管理員；要修正得加事前檢查 | reject |
| 39 | EC | 同上（重複資料會讓唯一索引建立失敗） | low | 同 #38 | reject |
| 40 | EC | IDN（punycode）或 NFC 不同編碼的 Email 可以註冊兩次 | low | 很少見；要修正得改寫正規化流程 | reject |
| 41 | EC | 缺少必填欄位、school_id 不是 UUID、token 太長時，422 訊息是 pydantic 的英文 | low | 前端送出前就擋下這些情況，只有直接打 API 才會碰到 | reject |
| 42 | EC | 兩個 `initial_data` 同時執行時，`ensure_first_admin` 會拋 DuplicateEmailError | false | 只有一個 backend 容器會跑 prestart（同 Story 1.1 #36） | reject |
| 43 | EC | `run_once` 的 `max_items <= 0` 時會跳過所有工作 | false | 沒有任何呼叫端傳入小於 1 的值 | reject |

## Design Notes

**worker 逐筆處理**（AD-5）：工作改為「處理一筆就回傳是否還有下一筆」：

```python
Job = Callable[[Session], bool]   # 處理一筆；True 代表處理了一筆、可能還有
def run_once(jobs, *, session_factory, max_items=100):
    for job in jobs:
        for _ in range(max_items):          # 每筆一個 session／交易
            with session_factory() as s:
                try: more = job(s); s.commit()
                except Exception: s.rollback(); log; break
            if not more: break
```

既有的 Story 1.1 worker 測試要改成新的介面。

**事件與寄信**：`dispatch_outbox` 每次取一則未處理事件（`FOR UPDATE SKIP LOCKED`），建立 EmailDelivery 後寫 `processed_at`；`send_pending_email` 每次取一筆 `pending` 寄出，成功設 `sent`，失敗 `attempts`+1；`attempts` 達 5 設 `failed`。信件內容在寄送時依 `event_id` 從 payload 重組（EmailDelivery 不存信件內容）。

**驗證連結**：`{FRONTEND_HOST}/verify-email?token=<明文>`，有 `redirect` 時一併附上；S7 讀取 `token` 後呼叫 `POST /email-verifications`。

**token**：`secrets.token_urlsafe(32)` 產生，資料庫存 `hashlib.sha256` 的十六進位值。

**驗證信版型**：主旨「完成 FLOW 的 Email 驗證」；內文「點下方按鈕完成 Email 驗證，連結 24 小時內有效。」；按鈕「驗證 Email」；寄件者名稱 FLOW。

**S7 文案**：待驗證「請收信驗證」＋說明已寄到哪個 Email＋「重寄驗證信」；成功「Email 驗證完成」＋「繼續」（有 `redirect` 時回原頁，否則回首頁）；失效「此驗證連結已失效。」＋「重寄驗證信」。

**錯誤碼**：`EMAIL_ALREADY_REGISTERED`（409）、`SCHOOL_NOT_FOUND`（422，`loc` 指向 `school_id`）、`VERIFICATION_LINK_INVALID`（400）。顯示名稱為必填，去除前後空白後 1～50 字。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy，新遷移套用成功。
- `docker compose exec backend bash scripts/test.sh` -- expected: 全部通過，涵蓋 I/O 矩陣每一列。
- `docker compose exec backend bash scripts/lint.sh` -- expected: 通過。
- `docker compose exec frontend bun run --filter frontend build` -- expected: 成功。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run test:unit` -- expected: 全部通過。

**Manual checks (if no CLI):**
- 以瀏覽器完成一次註冊 → Mailpit（http://localhost:8025）收信 → 點連結 → S7 驗證成功；再點一次同一連結顯示失效；在 S7 重寄後舊連結失效、新連結可用。
