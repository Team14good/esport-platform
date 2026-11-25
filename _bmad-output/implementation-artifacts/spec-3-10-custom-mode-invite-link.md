---
title: 'Story 3.10：自訂模式的先到先得分配（第 2 部分：賽事模式選項與賽事報名連結）'
type: 'feature'
created: '2026-11-24'
status: 'done'
route: 'dispatch'
baseline_commit: 'cdd08c528377d52f591324be97954d243813bb88'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-3-10-custom-mode-first-come.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 第 1 部分（#118）已讓自訂賽事依送出時間分配與遞補，但主辦方還不能建立自訂賽事，自訂賽事也沒有「賽事報名連結」，任何人都能建隊（FR-39、FR-11）。

**Approach:** 建立賽事可選「校園賽／自訂」（自訂不填優先期）；自訂賽事有 `Tournament.invite_token`，主辦方在 S27 看到並可重設賽事報名連結；自訂賽事建隊要帶有效 token，否則 `TOURNAMENT_INVITE_REQUIRED`；S1 標「邀請制報名」，S2 只在 `?invite=` 有效時顯示「建立隊伍」；示範資料加自訂賽事（7.1）；`@story-3.10` E2E。

## Decisions（2026-11-23，邱芯彤；第 1 部分 spec 已定）

- 賽事報名連結為 S2 加查詢參數 `/tournaments/{id}?invite={token}`，S2 讀到有效 token 才顯示「建立隊伍」，建隊時把 token 帶給後端。
- 重設連結後，已建立的隊伍不受影響（連結只在建隊時檢查）。
- 文字：S1 標籤「邀請制報名」；S2 沒有連結時「這是邀請制賽事，請向主辦方索取報名連結。」、連結已失效時「報名連結已失效，請向主辦方索取新的連結。」；S27 欄位「賽事報名連結」、說明「持有這個連結的帳號才能建立隊伍。」；重設確認框（destructive）標題與按鈕「重設報名連結」、內文「重設後舊連結立即失效，已建立的隊伍不受影響。」、成功 Toast「已重設報名連結」。

## Decisions（2026-11-24，邱芯彤）

- 動到別人的模組：由 C 直接修改 B 的 tournaments（`TournamentCreate`、`create_tournament`、`update_tournament`、`PublicTournament`、S26／S27／S28、S1 卡片）與 A 的示範資料；PR 說明逐項列出，請 B、A 審查（CLAUDE.md「只新增」規則的例外，使用者核准）。
- S28 在「尚未開放」時可切換模式（FR-9）：校園賽→自訂產生 token、隱藏優先期；自訂→校園賽清除 token、恢復優先期欄位；開放報名後模式唯讀。`TournamentUpdate` 新增 `mode`。
- 未登入者開啟含 `invite` 的 S2（開放報名中的自訂賽事）：顯示「登入後即可建立隊伍。」＋「登入」按鈕；登入（或註冊並驗證 Email）後回到同一個含 `invite` 的網址。
- 不拆分：示範資料一併在本 PR（使用者看過約 4,300 tokens 的長度後決定）。
- 示範資料只建一場開放報名中、自訂模式的《英雄聯盟》校內賽，不建隊伍；評審從 S27 取得連結自行建隊。
- spec 審查後（2026-11-24）：
  - S28 自訂→校園賽時，優先期欄位預填 24 小時（與 S26 預設相同），可修改。
  - `TOURNAMENT_INVITE_REQUIRED` 的訊息依情況沿用 S2 文字：沒帶 token「這是邀請制賽事，請向主辦方索取報名連結。」、token 不符「報名連結已失效，請向主辦方索取新的連結。」（同一個代碼）。
  - 示範自訂賽事：名稱「FLOW 校內賽 英雄聯盟」、名額 8、報名開始為啟動前 1 小時、截止為 3 天後、開賽為 7 天後（比照既有示範賽事）。
- 減少改動別人的程式（2026-11-24，使用者決定）：
  - S27 的報名連結區做成新的元件檔，B 的 `OrganizerTournamentOverview.tsx` 只多一行引用它。
  - 示範自訂賽事用新增的檔案與函式建立，不修改 A 的 `_ensure_tournament`；A 的 `demo_data/__init__.py` 只多一個步驟。

## Decisions（2026-11-25，邱芯彤；程式碼審查後）

- 已取消、已結束的自訂賽事：S27 整個「賽事報名連結」區不顯示；後端重設回 409 `TOURNAMENT_NOT_EDITABLE`（沿用修改賽事的代碼與訊息）。
- 自訂賽事的 S27 摘要不顯示「優先期結束」（多改 B 的 `OrganizerTournamentOverview.tsx` 一處，PR 說明列出）。
- 未登入、網址沒帶 `invite` 的開放報名自訂賽事：S2 顯示「這是邀請制賽事，請向主辦方索取報名連結。」。
- 既有測試：因 CHECK 約束（自訂⇔有 token）而直接改賽事列為自訂的既有測試，接受只多設一行 `invite_token`（不改斷言），PR 說明列出（含 D 的 `test_draw_status.py`）。經 API 建隊的三支自訂測試（`test_first_come_submission`、`test_reject_registration`、`competition/test_custom_post_draw_backfill`）維持「先設自訂再建隊」，建隊時帶 token，不改成先建隊再改模式。

## Boundaries & Constraints

**Always:**
- 模式在開放報名後不可更改（FR-7、FR-9）。自訂賽事的 `priority_end` 一律等於報名開始（後端把優先期強制為 0，忽略傳入值），與 #117 修改賽事時重算 `priority_end` 的方式一致。
- `invite_token`：自訂賽事建立時以 `secrets.token_urlsafe` 產生，UNIQUE，校園賽為 null；重設換新 token、舊的立即失效，寫操作紀錄（紀錄不含 token 值）。
- token 不進 `TournamentRead`（`tournament.updated` 的操作紀錄比對它的內容）、不進任何 `Public*` schema；只由主辦方專用端點回傳。資料庫以 CHECK 約束保證「自訂⇔有 token」；比對用 `secrets.compare_digest`，任一方為 null 都視為不符。
- 讀取與重設連結的權限比照既有主辦方端點：router 經 `Organizer` 與 `authz.ensure_tournament_owner`（別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`、不存在 404）；校園賽呼叫回 409 `TOURNAMENT_NOT_CUSTOM`。
- 公開檢查端點只回 `Public*` schema（AD-19）：`PublicRegistrationLinkStatus{valid}`；校園賽或沒帶 `invite` 時 `valid=false`，賽事不存在 404。
- 建隊（自訂）：在既有檢查（鎖賽事、報名期間、主辦方、已在賽事）之後檢查 token，缺少或不符都回 403 `TOURNAMENT_INVITE_REQUIRED`。加入隊伍（隊伍邀請連結）不檢查賽事 token。校園賽建隊不變。
- 依模式的判斷照 AD-20：registration 經 `allocation.py` 問「建隊要不要賽事報名連結」，不自行判斷 `mode`。
- 新的寫入端點都要登入（不加 `PUBLIC_WRITE_ROUTES`）；新的 schema 變更一支 Alembic 遷移檔。

**Never:**
- 不改第 1 部分的分配與遞補規則。
- 不在公開 API、S2 原始碼或操作紀錄露出 token；不讓校園賽多出任何入口限制。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 建立自訂賽事 | S26 選「自訂」 | 不顯示優先期欄位；建立後 `mode=custom`、有 token、`priority_end`＝報名開始；操作紀錄 | N/A |
| 建立校園賽 | S26 預設「校園賽」 | 與現在相同，`invite_token` 為 null | N/A |
| S27 自訂 | 主辦方開 S27 | 顯示「賽事報名連結」（Invite link field，可複製）＋說明＋「重設報名連結」 | 校園賽不顯示 |
| 重設連結 | 主辦方確認重設 | 新連結、Toast「已重設報名連結」、操作紀錄；舊連結建隊被拒；已建立的隊伍不受影響 | 非主辦方 403 |
| 帶有效連結建隊 | 已登入、開 `?invite=` 有效 | S2 顯示「建立隊伍」，建隊成功 | N/A |
| 沒有連結 | 已登入、開放報名的自訂賽事、無 `invite` | S2 顯示「這是邀請制賽事，請向主辦方索取報名連結。」，沒有「建立隊伍」 | 直接呼叫 API → 403 `TOURNAMENT_INVITE_REQUIRED` |
| 連結失效 | `invite` 不符（已重設或亂打） | S2 顯示「報名連結已失效，請向主辦方索取新的連結。」 | API → 403 `TOURNAMENT_INVITE_REQUIRED` |
| 隊友加入 | 自訂賽事的隊伍邀請連結 | 照常加入，不需賽事連結 | N/A |
| 建隊時連結已被重設 | 對話框開著時主辦方重設 | 建隊被拒，對話框顯示「報名連結已失效，請向主辦方索取新的連結。」 | 403 `TOURNAMENT_INVITE_REQUIRED` |
| S2 其他狀態 | 自訂賽事、帶有效連結 | 依序：本賽事主辦方不顯示；已有隊伍顯示狀態卡；Email 未驗證時「建立隊伍」停用並說明（同校園賽）；尚未開放、報名截止時不顯示連結提示（同校園賽） | N/A |
| 校園賽帶 `invite` | 校園賽 `?invite=任意` | 忽略參數，與現在相同 | N/A |
| 未登入開連結 | 未登入、開放報名的自訂賽事、`?invite=` | 顯示「登入後即可建立隊伍。」＋「登入」；登入後回到含 `invite` 的同一網址並顯示「建立隊伍」 | N/A |
| S28 切換模式 | 尚未開放，校園賽↔自訂 | 校園賽→自訂：產生 token、優先期欄位隱藏、優先期存 0；自訂→校園賽：token 清除、優先期欄位出現並預填 24（可改）；操作紀錄不含 token | N/A |
| S28 開放後 | 開放報名後送出 `mode` | 模式欄唯讀 | API → 既有的欄位錯誤 `TOURNAMENT_FIELD_LOCKED`（加進 `_LOCKED_AFTER_OPEN`，訊息「開放報名後不能修改賽事模式」） |
| S1 | 自訂賽事 | 列出並標「邀請制報名」 | N/A |
| 公開資料 | 未登入取 S1／S2 API | 有 `mode`，沒有 token | N/A |
| 示範資料 | 全新資料庫啟動 | 多一場開放報名中、自訂模式的《英雄聯盟》校內賽；重啟不重複建立 | N/A |

</frozen-after-approval>

## Code Map

- tournaments（B）
  - `backend/app/modules/tournaments/models.py` -- `Tournament`(:122-162) 加 `invite_token`（比照 `RefereeInvitation`:178-189 明碼 UNIQUE；長度比照 registration `INVITE_TOKEN_MAX_LENGTH`=64）；`TournamentCreate`(:430-453，docstring :433 寫一律校園賽) 加 `mode`；`PublicTournament`(:515-530) 加 `mode`；新增主辦方用的 `TournamentRegistrationLink` 與公開的 `PublicRegistrationLinkStatus`。`TournamentRead`(:481-512，:487-488「期中一律 campus」註解) 不加 token。:433、:461 與 service.py:402 的「一律校園賽」說明要更新。`Tournament` 加 CHECK 約束（模型與遷移都要有，`test_migrations` 會比對）。
  - `service.py` -- `create_tournament`(:396-472) 目前在 :428 寫死 CAMPUS、:431 算 `priority_end`；`_validate_schedule`(:336-378) 的優先期檢查（:359-366）在自訂時以 0 小時通過。新增公開函式 `get_registration_link`、`reset_invite_link`（鎖賽事、寫操作紀錄；主辦方身分由 router 檢查，比照 `read_my_tournament`）、`invite_token_matches(tournament_id, token)` 給 registration 用。token 產生比照 :1139。S28 切換模式：`update_tournament`(:890-984)、`_editable_values`(:693)、`_requested_changes`(:714)、`_upcoming_row_changes`(:730-802，:768 `model_construct` 要帶 `mode`、:792 重算優先期時自訂強制 0)、`_LOCKED_AFTER_OPEN`(:672-681，開放後送出變更時 :838 回欄位錯誤 `TOURNAMENT_FIELD_LOCKED`) 都要加 `mode`；`TournamentUpdate`(models.py:456-478，docstring :461) 加 `mode`；切換時同一交易產生或清除 token。
  - `router.py` -- 公開 `GET /tournaments`(:70)、`/tournaments/{id}`(:76) 回 `PublicTournament`；主辦方端點 :95-125。新增 `GET`／`POST /organizer/tournaments/{id}/registration-link`（讀取、重設），以及公開唯讀 `GET /tournaments/{id}/registration-link-status?invite=`（回有效與否，給 S2 判斷顯示哪段文字）。
  - `_bmad-output/implementation-artifacts/contracts/tournaments.md` -- :30「mode 一律 campus」、:106、:141「尚未提供 reset_invite_link」要更新。
- 遷移：head `a7d3e9b2c6f4`；範本 `c5d2e8a4f913_story_3_1_team_and_registration.py:32,37`（AutoString(64)＋UniqueConstraint）。`tests/test_migrations.py:13` 比對模型與遷移。
- registration（C）
  - `models.py:307-310` `TeamCreate` 加選填 `invite_token`；`router.py:35-47` 傳入；`service.py:734 create_team` 在 `_ensure_can_join`(:409-417) 之後、隊名檢查(:740) 之前，依 `allocation` 的回答（新函式，例如 `requires_tournament_invite(mode)`）呼叫 tournaments `invite_token_matches`。
  - 測試：`tests/registration/test_teams.py:163-282`；設模式 `_set_mode`（`test_reject_registration.py:118`）只改 `mode`，加 CHECK 約束後要一併設 token。第 1 部分的自訂測試建隊沒帶 token，會被拒：`test_custom_mode.py`（:84、:139、:157 經 API 建隊）、`test_custom_concurrency.py`（:69、:101 直接呼叫 `service.create_team`）、`competition/test_custom_post_draw_backfill.py`；要改 helper 帶入 token。
- identity：`identity/router.py:40-50` `PUBLIC_WRITE_ROUTES` 不加；`tests/test_auth_required.py` 會檢查。
- 示範資料（A）：`backend/app/demo_data/tournaments.py:118-156`（`_ensure_tournament` 寫死 `DEMO_TOURNAMENT_NAME`:88，以同名判斷已建立；**不修改它**）。新增 `backend/app/demo_data/custom_tournament.py`：自己的「以同名判斷已建立」函式，經 `tournaments_service.create_tournament` 建立自訂賽事（可 import `tournaments.py` 既有的常數，不改該檔）；`__init__.py:36-58` 只加一個步驟呼叫它；自訂賽事不能放進 `context.tournament_to_draw`（之後的報名、抽籤步驟只處理校園賽）。測試 `tests/identity/test_demo_data.py`。README:32、:44、CONTRIBUTING.md:170 與 epics.md:219、:2057（期中規則 8）的「示範資料只放校園賽」說明要更新。
- 前端
  - S26 `features/tournaments/CreateTournamentForm.tsx`：zod `formShape`(:93-110)、`createTournamentSchema`(:185-276，S28 共用)、優先期欄位 :778-785 與跨欄檢查 :245-250、`toTournamentCreate`(:279，優先期 :302；自訂時不送非 0 值、跨欄檢查 :245-250 略過)；模式 Select 比照遊戲 Select(:646-700)。測試 `tests/unit/organizer-tournaments.test.tsx:359`（目前斷言「沒有賽事模式欄位」，要翻轉）。
  - S27：新增元件檔 `features/tournaments/RegistrationLinkSection.tsx`（自訂賽事才顯示：連結、說明、重設確認框、Toast），`OrganizerTournamentOverview.tsx`（已顯示模式 :190；`OrganizerTournamentOverview` :249-268）只加一行引用，不改其他內容；元件 `features/registration/InviteLinkField.tsx`、`components/common/ConfirmDialog.tsx`（destructive 範例 `CancelTournamentButton.tsx:33-40`）。
  - S28 `features/tournaments/TournamentSettingsPage.tsx`：區塊「報名與賽程」(:564，優先期 :589-594)；尚未開放時可選模式，開放後唯讀。
  - S1 `features/tournaments/TournamentList.tsx` `TournamentCard`(:35-63)。
  - S2 `routes/tournaments/$tournamentId/index.tsx` 加 `validateSearch`（範例 `routes/login.tsx:10`）；`features/tournaments/TournamentOverview.tsx:85` → `features/registration/CreateTeamEntry.tsx`（目前未登入時回 null；自訂賽事改依登入與 token 狀態顯示提示、「登入」或「建立隊伍」）、`CreateTeamDialog.tsx:63-70`（帶 token）。登入後回原網址：沿用 `routes/login.tsx` 的 redirect 參數（加入隊伍 S19 已有「先登入再回來」的做法，比照它）。
  - `scripts/generate-client.sh` 重新產生 client。
- EXPERIENCE.md：:236 Invite link field 的使用處補 S27；〈固定介面字串〉加本 Story 的 S1／S2／S27／未登入提示字串。
- E2E：`frontend/tests/e2e/support/withdraw.ts:43` 建賽事範本（新增自訂版本的函式，不改既有）；標籤 `@story-3.10`。

## Tasks & Acceptance

**Execution:**
- [x] tournaments 後端（models、service、router、遷移、contracts） -- 建立與修改賽事的模式、token、讀取與重設連結、`invite_token_matches`、`PublicTournament.mode`。
- [x] `backend/app/modules/registration/allocation.py`、`service.py`、`models.py`、`router.py` -- 建隊依模式檢查賽事報名連結。
- [x] 後端測試 -- 新檔 `tests/tournaments/test_registration_link.py`（建立、讀取、重設、權限、S28 切換模式、公開 API 不含 token、操作紀錄不含 token）；`tests/registration/test_custom_team_invite.py`（I/O 矩陣建隊各列，含 null token 不相符）；`test_allocation.py` 補新函式；第 1 部分自訂測試的 helper 改為帶 token（見 Code Map）。
- [x] `backend/app/demo_data/custom_tournament.py`（新檔）、`__init__.py`（只加一個步驟） -- 開放報名中、自訂模式的《英雄聯盟》校內賽（不建隊伍，重啟不重複）；README、CONTRIBUTING:170 更新說明。
- [x] 前端：client、S26 模式欄位、S27 新元件 `RegistrationLinkSection.tsx`（總覽頁只加一行引用）、S28 模式切換、S1 標籤、S2 `invite` 與未登入提示，以及單元測試。
- [x] `frontend/tests/e2e/custom-mode.spec.ts` -- `@story-3.10`：主辦方建立自訂賽事 → 複製連結 → 隊長經連結建隊、隊友經隊伍連結加入 → 無連結者看到提示 → 重設後舊連結失效；桌機與 375 px。
- [x] `backend/tests/traceability.yaml`、EXPERIENCE.md〈固定介面字串〉加本 Story 字串（commit body 加 `Epic-Context: unaffected`）。
- [x] `deferred-work.md` 刪除 spec-3-10 第 1 部分的「第 2 部分」項目；`sprint-status.yaml` 3-10 改 `done`。
- [ ] `docs/ai-usage/C-邱芯彤.md` -- 記錄。

**Acceptance Criteria:**
- Given I/O 矩陣，when 檢查測試，then 每一列至少有一個會執行且通過的測試。
- Given 後端與前端，when 執行 `scripts/test.sh`、`lint.sh`、前端測試與 `@story-3.10` E2E，then 全部通過。既有測試只改下列斷言本 Story 要改的行為者，其餘不需修改：`tests/tournaments/test_tournaments.py:281`（mode 被忽略存為 campus）、`test_public_tournaments.py:18` `PUBLIC_FIELDS`（加 `mode`）、`tests/identity/test_demo_data.py` 中賽事數量的斷言、前端 `organizer-tournaments.test.tsx:359`（沒有賽事模式欄位）與各單元測試的 `PublicTournament` fixture（補必填的 `mode`）、第 1 部分自訂測試的建隊 helper（帶 token）。
- Given 任何公開 API 回應與操作紀錄，when 檢查，then 都不含 `invite_token`。

## Implementation Notes

實作（2026-11-25，子代理，待人確認）：

- 後端 tournaments：`Tournament.invite_token`（AutoString(64)、UNIQUE、可為 null）＋ CHECK 約束 `ck_tournament_custom_has_invite_token`；遷移 `b2f6c8d4e1a9`（down `d4b8f2a6c1e9`；原接 `a7d3e9b2c6f4`，#121 合併後改接，避免兩個 head）。`TournamentCreate.mode`（預設 campus）、`TournamentUpdate.mode`、`PublicTournament.mode`；新 schema `TournamentRegistrationLink`、`PublicRegistrationLinkStatus`。公開函式 `get_registration_link`、`reset_invite_link`（操作紀錄 `tournament.invite_link_reset`，before／after 皆 null）、`invite_token_matches`、`get_registration_link_status`。端點 `GET`／`POST /organizer/tournaments/{id}/registration-link`、`GET /tournaments/{id}/registration-link-status?invite=`。
- 後端 registration：`allocation.requires_tournament_invite(mode)`；`create_team` 在 `_ensure_can_join` 之後呼叫 `_ensure_tournament_invite`；`TeamCreate.invite_token` 選填。
- 示範資料：`demo_data/custom_tournament.py`，`STEPS` 在 tournaments 之後多一步；log 用「Demo custom tournament already exists, reused」。
- 前端（另一個子代理）：`registration-link.ts`（字串、網址、查詢）、`RegistrationLinkSection.tsx`；`OrganizerTournamentOverview.tsx` 只多 import 與一行 JSX；S26／S28 共用 `TournamentModeField`；S2 `validateSearch` 讀 `invite`；`CreateTeamEntry` 依登入與連結狀態顯示；`audit-log.ts` 加「重設報名連結」。
- 實作時自行決定（spec 沒寫）：
  - 遷移在加 CHECK 前替既有的自訂賽事列補 token：本機開發資料庫有第 1 部分檢視畫面時以 SQL 改成自訂的 7 場賽事，沒有補 token 時遷移失敗、backend 起不來（實際發生後才加）。
  - 公開檢查端點與建隊的 `invite` 不設長度上限：過長的值一律視為不符（S2 顯示「已失效」、API 403），不回 422。
  - ~~重設連結不限賽事狀態~~ 審查後改為：已結束或已取消 409 `TOURNAMENT_NOT_EDITABLE`（2026-11-25 Decisions）；校園賽 409。
  - 既有測試直接把賽事列改成自訂的地方（加 CHECK 約束後會失敗），都只多設一行 `invite_token`：除 Code Map 列的檔案外，還有 `competition/test_draw_status.py`（D）、`registration/test_draw_functions.py`、`test_first_come_submission.py`、`test_post_draw_backfill.py`、`test_public_accepted_teams.py`、`worker/test_priority_window_allocation.py`、`worker/test_registration_deadline.py`，沒有改斷言。經 API 建隊的三支自訂測試（`test_first_come_submission`、`test_reject_registration`、`competition/test_custom_post_draw_backfill.py`）維持先設自訂再建隊，建隊時帶 token（審查後依 Decisions 修正；`_api_team` 自動帶賽事的 token）。`test_audit_action_labels.py` 的清單加新動作。
  - 前端子代理原本在 S26／S28 模式欄加了一段 spec 沒有的說明文字，主流程已移除（未經使用者核准的介面文字）。
  - 未登入時不呼叫連結檢查端點，帶 `invite` 就顯示「登入」；沒帶 `invite` 審查後改為顯示「這是邀請制賽事，請向主辦方索取報名連結。」（Decisions）。
- 審查修正（2026-11-25）：S27 已取消、已結束不顯示連結區；自訂賽事 S27 摘要不顯示「優先期結束」；S28 校園賽切自訂再切回還原原本的優先期；API 自訂→校園賽沒帶優先期時用 24；建隊帶空字串 token 視為沒有連結；補 R4、R5 測試；README 補自訂示範賽事 3 天後截止；epics.md 規則 8 改寫。
- 未做：`docs/ai-usage/C-邱芯彤.md` 留給主流程。
- 主流程矩陣稽核（2026-11-25）：「S2 其他狀態」的主辦方本人、已有隊伍、報名截止三種情況原本只有校園賽的測試；在 `custom-mode-invite.test.tsx` 補上自訂賽事帶連結的三個測試（18 passed、biome、tsc 通過）。
- 瀏覽器檢視（2026-11-25，主流程以暫時 Playwright 腳本截圖，看完即刪除、不提交）：桌機與 375 px 各 15 張，涵蓋 S26 選自訂（優先期隱藏）、S27 連結區／重設確認框／Toast／已取消不顯示、S28 未開放可切換（切回校園賽預填 24）／開放後唯讀、S1「邀請制報名」、S2 未登入無連結／未登入帶連結／登入無連結／舊連結失效／有效連結、S16 對話框；兩種寬度都通過且沒有橫向捲動，沒有要修正的畫面問題。看到但非本 Story 造成：S28 側欄「總覽」與「設定」同時反白；S26「遊戲」與「名額」標籤高度差幾 px。

## Spec Change Log

## Review Triage Log

spec 審查（2026-11-24，獨立子代理；主流程抽查 #1、#2、#6、#7、#8 的證據屬實，#2 的示範資料測試實際在 `tests/identity/test_demo_data.py`）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| 1 | 第 1 部分自訂測試建隊沒帶 token，加檢查後會被拒；`_set_mode` 造出「自訂但無 token」；None==None 可能被當相符 | high | 已修正：Code Map 列出要改的 helper；`compare_digest`、null 一律不符 |
| 2 | AC「既有測試不需修改」與實際矛盾（mode 被忽略、公開欄位白名單、示範資料數量、前端 fixture） | high | 已修正：AC 逐一列出例外與理由 |
| 3 | 自訂的優先期沒寫死；S28 切回校園賽時優先期值未定 | medium | 已修正：後端強制 0；切回校園賽預填 24（使用者決定） |
| 4 | `_LOCKED_AFTER_OPEN`、`toTournamentCreate` 行號過時 | low | 已修正 |
| 5 | `TOURNAMENT_INVITE_REQUIRED` 的訊息文字沒定義 | medium | 已修正：依情況沿用 S2 兩則文字（使用者決定），矩陣加「建隊時連結已被重設」 |
| 6 | 公開檢查端點不符 AD-19；校園賽、沒帶 invite、不存在時的回應未定義 | medium | 已修正：`PublicRegistrationLinkStatus`，各情況寫進 Always |
| 7 | token 經 redirect 進驗證信與 outbox、存取紀錄 | medium | 已修正：Design Notes 說明與 S19 相同、可接受；redirect 要 URL 編碼 |
| 8 | 主辦方權限檢查放 service 與既有慣例（router `ensure_tournament_owner`）不一致；校園賽呼叫的代碼未定 | medium | 已修正：比照既有做法；校園賽 409 `TOURNAMENT_NOT_CUSTOM` |
| 9 | S2 缺未驗證 Email、主辦方本人、已有隊伍、校園賽帶 invite 等狀態 | low | 已修正：矩陣加兩列並寫明先後順序（沿用 `CreateTeamEntry` 現有順序） |
| 10 | 示範資料 `_ensure_tournament` 寫死名稱；不能進 `tournament_to_draw`；名稱名額期間未定 | low | 已修正：Code Map 註明；名稱等由使用者決定 |
| 11 | models／service 的「一律校園賽」註解、EXPERIENCE.md:236、epics 規則 8 漏列 | low | 已修正：Code Map 補列 |
| 12 | 建議加 CHECK 約束（自訂⇔有 token） | low | 採納：寫進 Always 與 Code Map |

程式碼審查（2026-11-25，盲審、邊界情況、驗證缺口三個子代理；主流程逐項對照程式碼驗證）：

| # | 發現 | 判定 | 去向 |
|---|------|------|------|
| R1 | S27 對已取消、已結束的自訂賽事仍顯示連結與重設；後端重設不限狀態（盲審、邊界） | medium：`RegistrationLinkSection` 只看 mode，與 S27「已取消時沒有任何動作」衝突 | 問使用者後 patch（見 2026-11-25 Decisions） |
| R2 | S28 校園賽（優先期 48）切自訂再切回校園賽，優先期被改成 24 並送出（盲審、邊界） | medium：`onModeChange` 一律 setValue 24，與初始值不同就送出 | patch：初始為校園賽時還原初始值 |
| R3 | API 自訂→校園賽不帶 `priority_hours` 會存成 0 小時優先期（盲審、邊界） | medium：`_editable_values` 的 0 直接沿用 | patch：未帶時用預設 24（與 S26／S28 預填相同） |
| R4 | 一般修改 upcoming 自訂賽事時 token 保持不變沒有測試（驗證缺口） | medium：`test_custom_ignores_priority_hours_on_update` 提早 return，沒走到 `_upcoming_row_changes` | patch：補測試 |
| R5 | 開放報名的自訂賽事送 `priority_hours` 被忽略沒有測試（驗證缺口） | low：只有 upcoming 路徑被測 | patch：測試參數化 |
| R6 | 遷移補 token 的迴圈沒有對資料執行過的測試（驗證缺口） | medium（未驗證）：repo 沒有帶資料跑遷移的測試設施 | defer |
| R7 | 建隊帶空字串 token 回「已失效」而非「沒有連結」（盲審、邊界） | low：`invite_token is None` 判斷；修正為直接改條件 | patch |
| R8 | `invite_token`／`invite` 沒有長度上限（盲審） | false：過長值以 compare_digest 比對為不符，無害；spec 實作備註已記 | reject |
| R9 | 建隊 403 後 S2 的連結檢查沒失效，關掉對話框仍見「建立隊伍」（盲審） | low：要另加錯誤分支，且再按仍會顯示正確錯誤 | reject |
| R10 | S27 讀取連結失敗、S2 連結檢查失敗時什麼都不顯示（盲審、邊界） | low：網路錯誤少見，修正要加分支；與既有「查詢失敗不顯示」一致 | reject |
| R11 | README 示範說明沒提自訂賽事 3 天後截止（盲審） | low：保留資料庫 3 天後再啟動就不能示範建隊；一句文字 | patch |
| R12 | epics.md 規則 8 自相矛盾（盲審） | low：文字直接改寫 | patch |
| R13 | 重設路徑重複鎖同一列（盲審、驗證缺口） | false：同一交易內重複 FOR UPDATE 無害，沒有錯誤結果 | reject |
| R14 | 重設與建隊並行沒有測試（盲審） | low：兩者都先 FOR UPDATE 鎖賽事，序列化由既有鎖保證；測試要並行設施 | reject |
| R15 | 未登入提示沒有「註冊」按鈕（盲審） | false：spec 只定「登入」；登入頁的註冊連結會帶 redirect | reject |
| R16 | 公開檢查端點可反覆猜 token、token 在查詢字串（盲審） | false：256 位元 token，Design Notes 已接受查詢字串 | reject |
| R17 | 未登入帶失效連結先要求登入，登入後才說失效（邊界） | false：與矩陣「未登入開連結」一致 | reject |
| R18 | 示範資料同名賽事若被改成校園賽或取消仍沿用（邊界） | low：只有手動改示範賽事才會遇到，與校園賽示範一致 | reject |
| R19 | 自訂賽事送 `priority_hours=-1` 仍 422（邊界） | low：前端一律送 0 | reject |
| R20 | AC 低估既有測試改動（邊界） | 修正要改本 spec | reject（已問使用者並記入 Decisions） |

## Design Notes

- token 不放 `TournamentRead`：主辦方的修改賽事會把 `TournamentRead` 前後內容寫進操作紀錄（service.py:958），放進去等於把 token 寫進操作紀錄，S29 之外的人（例如之後的稽核頁）也看得到。
- S2 需要知道 token 有效與否才能分出「沒有連結」與「連結已失效」兩種文字，所以另開唯讀的檢查端點；它只回 `PublicRegistrationLinkStatus{valid}`，不洩漏 token。
- token 放在網址查詢字串，登入或註冊的 `redirect` 會把它帶進驗證信與 outbox 事件（identity/service.py:274-277），也會出現在伺服器存取紀錄。這與隊伍邀請連結（S19 `/join/{token}`）的情況相同，可以接受；redirect 參數要做 URL 編碼。

## Verification

**Commands:**
- `docker build -f backend/Dockerfile -t flow-backend:latest .`、`docker build -f frontend/Dockerfile -t espory-platform-frontend:latest .` 後 `docker compose up -d --no-build --wait`
- `docker compose exec -T backend bash scripts/test.sh`、`bash scripts/lint.sh` -- 全綠
- frontend 容器內 `bunx vitest run`、`bunx biome check`、`bunx tsc --noEmit -p tsconfig.json` -- 通過
- `docker compose --profile e2e run --rm e2e bunx playwright test --grep @story-3.10` -- desktop、mobile-375 通過
