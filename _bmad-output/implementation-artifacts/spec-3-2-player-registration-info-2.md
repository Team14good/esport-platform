---
title: 'Story 3.2 選手填寫參賽資料（第二段：存檔 API、S17 入口與平均段位積分）'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '2a499fd21005d996b1b878f08d6d7ad72cda5fb9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-2-player-registration-info.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第一段做好了 `core.storage`、段位驗證與 S18 對話框，但參賽資料還不能存：`team_member` 沒有欄位、沒有 API，S17 也沒有「填寫我的資料」入口，名單看不到誰填完、隊伍平均段位積分也沒有顯示。3.1（#23）已合併並同步到本分支。

**Approach:** `team_member` 加參賽資料欄位與遷移；新增 multipart API 讓隊員存自己的遊戲 ID、段位與段位截圖；`TeamDetail` 帶出段位對照表、每位隊員的資料與缺漏、平均段位積分與能否編輯；S17 的 Roster list 顯示資料完成度，自己那列有「填寫我的資料」開 S18，名單下方顯示平均段位積分。

## Decisions（2026-11-03，邱芯彤）

- 平均段位積分只算已填段位的成員並註明人數，例如「平均段位積分 23.33（3／5 人已填）」；全員都填了只顯示「平均段位積分 23.33」；沒有人填時顯示「平均段位積分：尚無人填寫」。一律顯示兩位小數。後端回傳 `avg_rank_score`（數值，沒人填時為 null）與 `rank_filled_count`。這是刻意偏離 PRD FR-12「由名單上所有成員計算」的送出前顯示；3.3 送出時要求全員填完，凍結的值與 PRD 一致。
- spec 篇幅約 3,500～4,000 tokens，超過 1600，保留完整 spec，不拆分。
- spec 審查後（同日）：檢查順序改為先查隊伍再鎖賽事（與 3.1 `join_team` 相同）；遊戲 ID 在 service 驗證並用繁中錯誤碼；後端回傳 `profile_editable`，不能編輯時 S18 一律唯讀。

## Boundaries & Constraints

**Always:**
- 存資料的檢查順序：查隊伍（404 `TEAM_NOT_FOUND`）→ `lock_tournament()` → 是隊員（403 `TEAM_MEMBER_REQUIRED`）→ 賽事 `open`（`ensure_accepting_registrations`，409 `REGISTRATION_CLOSED`）→ 報名仍是 `forming`（409 `ROSTER_LOCKED`「名單已鎖定，資料無法修改。」）→ 欄位驗證 → 存圖片。欄位格式驗證在 service 做，不用 FastAPI 的 Form 限制，確保鎖之後才回 422。
- 只能改自己的資料（API 路徑是 `me`，不收帳號 id）。
- 段位用 `rank_score_for` 驗證並存積分；圖片用 `core.storage.save_image` 存，資料庫只存鍵值與清理過的原始檔名。
- 換新截圖時，router commit 成功後才刪除舊檔；沒換截圖時保留原檔。
- 操作紀錄 `team_member.profile_updated`（帶 `tournament_id`；`after` 含遊戲 ID、段位、積分、是否換截圖，不含鍵值）。
- `TeamDetail` 只給隊員看（沿用 3.1）；任何回應都不含截圖鍵值，也沒有下載截圖的 API。
- `profile_editable` = 賽事 `open` 且報名 `forming`；為 false 時 S18 唯讀。
- 平均段位積分即時計算、取到小數第二位、含替補；3.3 送出時才凍結到 Registration，本段不加 Registration 欄位。

**Never:**
- 不做送出報名、名單鎖定的觸發、主辦方檢視截圖（3.3、3.8）。
- 不改其他組員的模組；不手寫 fetch／axios；不手改 `frontend/src/client`、`routeTree.gen.ts`。
- 不做請求大小上限（維持 deferred-work，由 `save_image` 邊讀邊擋 5 MB）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 第一次填寫 | 遊戲 ID、對照表內段位、合格截圖 | 200 `TeamDetail`；自己那列資料完成 | N/A |
| 修改但不換截圖 | 已有截圖，未附檔（或空的檔案欄位） | 更新 ID 與段位，截圖不變 | N/A |
| 換截圖 | 已有截圖，附新檔 | 存新檔，commit 後刪舊檔 | N/A |
| 第一次沒附截圖 | 尚無截圖、未附檔 | 不存任何資料 | 422 `RANK_SCREENSHOT_REQUIRED`「請上傳段位截圖」，`loc` 指向 `rank_screenshot` |
| 遊戲 ID 空白 | 去頭尾空白後 0 字 | 不存 | 422 `GAME_ACCOUNT_ID_REQUIRED`「請輸入遊戲 ID」 |
| 遊戲 ID 過長 | 去頭尾空白後超過 50 字 | 不存 | 422 `GAME_ACCOUNT_ID_TOO_LONG`「遊戲 ID 最多 50 個字」 |
| 段位不在對照表 | 任意名稱 | 不存、不留檔 | 422 `RANK_TIER_NOT_ALLOWED` |
| 圖片不合格 | GIF、檔頭不符、超過 5 MB | 不存 | 415／413（第一段的錯誤） |
| 隊伍不存在 | 未知的 team_id | 拒絕 | 404 `TEAM_NOT_FOUND` |
| 非隊員 | 他隊或未加入的帳號 | 拒絕 | 403 `TEAM_MEMBER_REQUIRED` |
| 名單已鎖定 | 報名不是 `forming` | 拒絕；S18 唯讀 | 409 `ROSTER_LOCKED` |
| 賽事非開放報名 | 狀態不是 `open` | 拒絕；S18 唯讀 | 409 `REGISTRATION_CLOSED` |

</frozen-after-approval>

## Code Map

- `backend/app/modules/registration/models.py` -- `TeamMember`（66-88）加欄位；`TeamMemberRead`（140-144）只有 account_id、display_name、role、joined_at；`TeamDetail`（147-164）已有 starters、substitutes、max_members、registration_status、my_role
- `backend/app/modules/registration/service.py` -- `_lock_tournament`／`_get_tournament`／`_ensure_accepting_registrations`（40-51）、`_team_member_required`（91-94）、`_build_detail`（217-248）；`join_team`（328-）的「先查隊伍再鎖」寫法；`audit.record`（294-303）寫法；已 import `TournamentRead`
- `backend/app/modules/registration/router.py` -- 同步 `def`、`SessionDep`、`VerifiedAccount`，service 後 `session.commit()`；沒有 prefix，路徑寫完整
- `backend/app/modules/registration/player_profile.py` -- `rank_score_for(rank_tiers, rank_tier)`；本地 `RankTierLike` Protocol 改用 `tournaments.models.RankTierRead`（deferred-work 第二段項目）
- `backend/app/core/storage.py` -- `save_image(stream, *, content_type) -> str`、`open_file(key)`；鍵值格式 `<hex32>.jpg|png`；新增 `delete_file`
- `backend/app/core/errors.py:44` -- `FieldError(code, message, *, loc)`，422 回應 `{"detail":[{"type","loc","msg"}]}`
- `backend/app/modules/tournaments/models.py` -- `TournamentRead.rank_tiers: list[RankTierRead]`（高到低）、`status`、`starters`、`substitutes`
- `backend/app/alembic/versions/c5d2e8a4f913_story_3_1_team_and_registration.py` -- 目前 head；寫法參考（`sa.Column`、`AutoString(length=N)`、中文 docstring）
- `backend/tests/registration/test_teams.py` -- `_tournament`、`_set_status`、`_make_account`、`_auth`、`_create_ok`、`_join`、`_error_code`、`_audit`、`lock_spy`；`tests/helpers.py` `make_game` 段位預設 鑽石=30、黃金=10
- `pyproject.toml` 已有 `python-multipart`；專案內還沒有任何 `UploadFile` 端點
- `frontend/src/features/registration/PlayerProfileDialog.tsx` -- props：`open`、`onOpenChange`、`rankTiers`、`initialValues`、`uploadedScreenshotName`、`readOnly`、`uploadProgress`、`onSubmit(values)`（`rank_screenshot: File | null`，null 表示保留原圖）；onSubmit reject 時自己顯示錯誤；不會自己關閉；zod 在 78 行
- `frontend/src/features/registration/{TeamPage,RosterList}.tsx` -- `teamQueryOptions(teamId)`；RosterList 24 行註解留給 3.2；`useCurrentAccount()`（`features/identity/auth.ts:130`）取目前帳號 id
- `frontend/src/features/registration/CreateTeamDialog.tsx:63-80` -- mutation 寫法（`setQueryData` 更新 team 快取）
- `frontend/tests/unit/team-pages.test.tsx` -- `vi.spyOn(RegistrationService, ...)`、`member()`／`TEAM` fixture、`beforeAll` 預先載入路由
- 生成的 client 的 options 繼承 axios 設定，可直接傳 `onUploadProgress`；multipart 端點產生後會用 `formDataBodySerializer`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py` -- `TeamMember` 加 `game_account_id`（50）、`rank_tier`（50）、`rank_score`（int）、`rank_screenshot_key`（64）、`rank_screenshot_name`（100），皆可為 null。`TeamMemberRead` 加 `game_account_id: str | None`、`rank_tier: str | None`、`rank_score: int | None`、`has_rank_screenshot: bool`、`rank_screenshot_name: str | None`（只在自己那列有值）、`missing_fields: list[Literal["game_account_id","rank_tier","rank_screenshot"]]`（固定此順序）。`TeamDetail` 加 `rank_tiers: list[RankTierRead]`、`avg_rank_score: float | None`、`rank_filled_count: int`、`profile_editable: bool`
- [x] `backend/app/alembic/versions/<hex>_story_3_2_player_profile.py` -- `add_column` 五欄，`down_revision = "c5d2e8a4f913"`
- [x] `backend/app/core/storage.py` -- `delete_file(key)`：鍵值不合格式或檔案不存在時直接返回；其他 `OSError` 記 log 後返回，不往外拋
- [x] `backend/app/modules/registration/player_profile.py` -- 改用 `RankTierRead`；新增 `clean_file_name`（取最後一段路徑、去控制字元、截到 100 字，空白時用 `rank-screenshot.<副檔名>`）、`validate_game_account_id`（去頭尾空白，錯誤依 I/O 矩陣，`loc=("body","game_account_id")`）、`average_rank_score(scores) -> float | None`（`Decimal` 以 `ROUND_HALF_UP` 取到 0.01 後轉 float）
- [x] `backend/app/modules/registration/{repository,service}.py` -- `update_player_profile(session, *, team_id, account_id, game_account_id: str, rank_tier: str, screenshot: BinaryIO | None, content_type: str | None, file_name: str | None) -> ProfileUpdate`（`detail`、`new_key`、`old_key`）；操作紀錄 `entity_type="team_member"`、`entity_id=member.id`、`before`／`after` 含遊戲 ID、段位、積分；`_build_detail` 填入新欄位
- [x] `backend/app/modules/registration/router.py` -- `PUT /teams/{team_id}/members/me/profile`（multipart：`game_account_id`、`rank_tier` 為 `Form(str)` 不加限制，`rank_screenshot` 為可省略的 `UploadFile`；檔名為空且 0 byte 視為未附檔），`VerifiedAccount`；service 或 commit 拋例外時 `delete_file(new_key)` 後重拋；commit 成功後 `delete_file(old_key)`
- [x] `backend/tests/registration/test_player_profile_api.py` -- I/O 矩陣每一列、先鎖再查（`lock_spy`）、操作紀錄、回應不含鍵值、別人那列沒有檔名、換圖刪舊檔、失敗時不留新檔、平均值（含替補、四捨五入、沒人填為 null）、`missing_fields`、`profile_editable`；`UPLOAD_DIR` 指到 `tmp_path`；`test_player_profile.py` 補新純函式
- [x] `frontend/src/client` -- 以 `scripts/generate-client.sh` 重新產生
- [x] `frontend/src/features/registration/PlayerProfileDialog.tsx` -- zod 的遊戲 ID 加 `.max(50, "遊戲 ID 最多 50 個字")`
- [x] `frontend/src/features/registration/RosterList.tsx` -- 每列 caption「遊戲 ID · 段位 · 段位截圖：已上傳」（只列有填的部分）；右側「資料完成」（`status-confirmed`）或「缺：…」（`muted-foreground`，依 `missing_fields` 順序轉成「遊戲 ID」「段位」「段位截圖」）；自己那列「填寫我的資料」outline 鈕；名單下方平均段位積分（依 Decisions）
- [x] `frontend/src/features/registration/TeamPage.tsx`（必要時另開 `useUpdatePlayerProfile`）-- 開 S18（`readOnly = !profile_editable`）、呼叫 API 並傳 `onUploadProgress`、成功後 `setQueryData`、關閉 S18、Toast「已儲存參賽資料」
- [x] `frontend/tests/unit/team-pages.test.tsx`、`registration-components.test.tsx` -- 完成度、缺漏文字、只有自己那列有按鈕、唯讀、平均值三種顯示、送出呼叫 API 與成功／錯誤
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 刪除第一段留下的三項（第二段待辦、刪檔、檔名規則）；請求大小上限保留，另新增一筆說明再次延後的原因

**Acceptance Criteria:**
- Given S17，when 隊員檢視，then 每人一列顯示已填的遊戲 ID、段位、截圖已上傳，以及「資料完成」或「缺：遊戲 ID、段位、段位截圖」（依實際缺漏，順序固定）。
- Given S17 自己那列，when 按「填寫我的資料」，then 開 S18，段位選項來自賽事對照表，已上傳時只顯示檔名；儲存成功後關閉、名單立即更新並 Toast「已儲存參賽資料」。
- Given 上傳中，when 檔案傳送，then S18 顯示進度百分比。
- Given `profile_editable` 為 false，when 開啟 S18，then 欄位唯讀、沒有「儲存資料」；按鈕文字仍是「填寫我的資料」。
- Given 有隊員填了段位，when 檢視 S17，then 名單下方依 Decisions 顯示平均段位積分（兩位小數）與已填人數。

## Implementation Notes

- 遷移檔 `a3f6b9d2c8e1_story_3_2_player_profile.py`（`down_revision = "c5d2e8a4f913"`）。
- `game_account_id`、`rank_tier` 的 `Form()` 預設為空字串：FastAPI 會把空字串的必填表單欄位當成「缺少」，在鎖之前就回自己的 422；給預設值後，未附或空字串都交給 service，依 I/O 矩陣回 `GAME_ACCOUNT_ID_REQUIRED`／`RANK_TIER_NOT_ALLOWED`。代價是生成的 client 把這兩個欄位標成可省略。
- 新檔的清理分兩處：圖片存下後 service 內的步驟（寫入欄位、操作紀錄、flush、組回應）失敗時，service 自己 `delete_file(new_key)` 再往外拋（例外發生時 router 拿不到鍵值）；commit 失敗時由 router 刪。都只動檔案，不 commit 或 rollback（AD-5）。
- 操作紀錄 `after` 的「是否換截圖」欄位名為 `screenshot_replaced`（第一次上傳也是 true）。
- `clean_file_name` 去掉 Unicode 類別 `Cc` 與 `Cf`（含 U+202E 等雙向覆寫字元，避免檔名在畫面上被反轉顯示）。
- 空的檔案欄位：httpx 會省略 `filename`，FastAPI 收到的是空字串而變成 None；瀏覽器會送 `filename=""`，才會進到 router 的「檔名為空且 0 byte」判斷。兩種都有測試（後者手動組 multipart）。
- S17 只在「填寫我的資料」開啟時才掛載 S18（關閉即卸載，沒有關閉動畫）：平常 S17 不必呼叫 `useIsMobile`，也避免其他導向 S17 的測試因 jsdom 沒有 `matchMedia` 而渲染錯誤頁。
- 平均段位積分放在名單下方人數那行的下一行（同為 caption、`muted-foreground`）；前端用 `toFixed(2)` 補足兩位小數，四捨五入由後端完成。
- 上傳進度：有選新截圖時才傳 `onUploadProgress`（`loaded / total × 100`）；沒有新檔時不顯示進度。
- 瀏覽器手動檢查（375 px、兩個帳號、uploads volume 舊檔消失）尚未執行。

## Spec Change Log

## Review Triage Log

第 1 輪（2026-11-03；B＝Blind Hunter、E＝Edge Case Hunter、V＝Verification Gap）

| 來源 | 發現 | 判定 | 證據 | 去向 |
| --- | --- | --- | --- | --- |
| V | 沒有驗證缺口 | — | 審查員未提出任何項目 | — |
| B1、E1、E2 | 遊戲 ID 只去頭尾空白，可含 NUL、換行、U+202E、只有零寬字元或 U+FEFF | medium | `validate_game_account_id` 只呼叫 `strip()`；NUL 會被 PostgreSQL 拒絕而回 500；U+202E 會讓隊友看到的名單文字反轉；`clean_file_name` 已有同樣的 Cc／Cf 過濾可沿用 | patch |
| B2、E3 | 前端 50 字以 UTF-16 計，後端以 code point 計 | low | zod `.max(50)` 計 UTF-16 單位，含 emoji 的 26～50 字 ID 前端擋、後端收；修正是一行 refine | patch |
| B3 | 前端「去頭尾空白後超過 50 字」的測試輸入沒有空白 | low | 測試只用 `"x".repeat(51)`，沒驗到先去空白再算長度 | patch |
| B4 | 儲存失敗（409、403）後 S17 的 `profile_editable` 不更新，S18 仍可編輯 | medium | `useUpdatePlayerProfile` 沒有 `onError`；名單在別處被鎖或賽事關閉後，使用者會一直送到同一個錯誤 | patch |
| B5 | 檢查順序只部分測試：非隊員＋賽事非開放、遊戲 ID 錯誤＋賽事非開放 | low | 現有測試只用無效段位測賽事非開放；補兩個測試即可 | patch |
| B6 | 段位空白時回 `RANK_TIER_NOT_ALLOWED` 而不是「請選擇段位」 | low | S18 的 zod 已要求段位必填，只有直接呼叫 API 才會遇到；改成新錯誤碼會增加公開介面 | reject |
| B7 | 段位對照表在報名期間改變時，已存的積分會過期 | false | 賽事的段位存在 `tournament.game_snapshot`（tournaments/models.py:113-146，AD-12），建立後不變；tournaments 沒有修改賽事的函式 | reject |
| B8 | 程序在存圖與 commit 之間被殺時留下孤兒檔 | low | 只在程序異常終止時發生；修正要新增定期清理工作 | reject |
| B9 | OpenAPI 只列 422，沒列 403／404／409／413／415 | low | 專案既有端點都沒宣告 `responses=`，前端統一以 `parseApiError` 解析；不是本次造成的 | reject |
| B10 | 上傳進度測試在 mock 內呼叫 `waitFor` | low | 測試能驗到「上傳中 50%」出現；改寫只是結構偏好 | reject |
| B11 | 上傳到 100% 後沒有「儲存中」提示 | false | `PlayerProfileDialog` 的 `LoadingButton` 在 `isSubmitting` 期間顯示載入狀態（PlayerProfileDialog.tsx:237-239） | reject |
| B12 | 請求大小上限在 deferred-work 有兩筆；第一段項目後少一個空行 | false | 新增一筆是 spec Tasks 的要求（只新增不修改舊項目）；少空行在 baseline 就存在 | reject |
| B13 | spec Tasks 寫「先鎖再查」與 Decisions 的順序不一致 | low | 修正對象是本 spec；測試與程式照 Decisions 的順序 | reject |
| B14 | 瀏覽器手動檢查未做、AI 使用紀錄未加 | low | 不是程式缺陷；兩者在 step-05 呈現時處理 | reject |
| E4 | `rank_screenshot` 以文字欄位送出時，FastAPI 在鎖之前回 422 | low | 只有手動構造的請求會發生；S18 一律送檔案或不送 | reject |

## Design Notes

- 截圖可省略：S18 的表單在已有截圖時允許不重選（第一段），所以 API 的截圖欄位可省略；第一次填寫才必填。三項都在同一次送出，不支援只存一部分。
- 檔案清理放在 router（AD-5：service 不 commit，也不知道交易結果）：失敗時刪新檔、成功後刪舊檔。
- `missing_fields` 由後端算，前端只負責把代碼轉成「遊戲 ID」「段位」「段位截圖」，3.3 的送出檢查可沿用同一份。
- 函式名稱 `update_player_profile` 與 `c-d-design-groundwork.md:498` 一致。
- 截圖原始檔名可能含個人資訊，只回給本人；其他隊員只看到 `has_rank_screenshot`。

## Verification

**Commands:**
- `docker compose up -d --build --wait && docker compose exec -T backend bash scripts/test.sh` -- 全綠，`test_migrations.py` 通過
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- `docker compose exec -T frontend bun run --filter frontend typecheck`、`bunx biome check`、`bun run test:unit` -- 通過

**Manual checks:**
- 瀏覽器（含 375 px）：兩個帳號在同一隊，各自填資料，S17 完成度與平均值即時更新；換截圖後 uploads volume 舊檔消失
