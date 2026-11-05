---
title: 'Story 2.7（第二階段）：S31 裁判管理與 S23 接受裁判邀請畫面'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: 'b1a1f7e557ecd362a833bb7b9ef083d44395667f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-2-7-referee-invitation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 2.7 第一階段（PR #40）的後端已合併，但主辦方沒有畫面產生、複製裁判邀請連結與查看裁判，受邀者也沒有頁面可以接受邀請，只能直接呼叫 API。

**Approach:** 新增 S31 `/organizer/tournaments/$tournamentId/referees`（主辦方賽事後台側欄「裁判」）與 S23 `/referee-invite/$inviteToken`，只呼叫第一階段的 API（`frontend/src/client` 已有）；S31 的連結欄沿用 C 的 `InviteLinkField`。

## Boundaries & Constraints

**Always:**
- S31 放在既有的主辦方賽事後台版面（`OrganizerTournamentLayout`，權限與 403／404 由版面處理），側欄新增「裁判」。
- S31 連結欄用 `features/registration/InviteLinkField`：未產生過顯示「產生邀請連結」；有效時顯示連結、「複製連結」（Toast「已複製」）與「{絕對時間} 到期」；過期時顯示「連結已過期」＋「產生新連結」。
- S31 裁判名單依接受時間排序，顯示顯示名稱與接受時間；空狀態「還沒有裁判接受邀請。複製邀請連結傳給裁判。」。
- S23 不需登入即可預覽（賽事名稱、到期時間）；過期時不顯示「接受邀請」，改寫「此裁判邀請已過期，請向主辦方索取新連結。」。
- S23 接受前：未登入提供「註冊帳號」「登入」並帶 `redirect=/referee-invite/{token}`（註冊、驗證 Email 後回到原頁，照 S19 的寫法）；Email 未驗證時用 `VerificationRequired` 停用按鈕。
- 業務錯誤顯示繁中訊息：`ORGANIZER_CANNOT_BE_REFEREE`、`TOURNAMENT_NOT_ACCEPTING_REFEREES`、`REFEREE_INVITATION_EXPIRED`（顯示過期文案）、`REFEREE_INVITATION_NOT_FOUND`（「找不到這個裁判邀請」＋回首頁）。
- 接受成功後讓身分清單查詢失效，身分切換器出現「裁判」（D 的 PR #51 合併後生效）。
- 介面文字繁中，按鈕用動詞＋名詞；375 px 沒有橫向捲軸。

**Never:**
- 不做撤銷裁判、從名單移除裁判、指派裁判到場次（4.4 的 S30 已做）。
- 不改 C 的 `InviteLinkField` 既有行為（只使用）。
- 不手寫 fetch；不改第一階段的 API 行為，只在兩個回應 schema 新增 `accepting` 欄位（Decisions）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| S31 從未產生 | `readRefereeInvitation` 回 null | 說明文字＋「產生邀請連結」；按下後顯示連結與到期時間 | 產生失敗顯示錯誤 Toast |
| S31 有效連結 | 未過期 | 連結、「複製連結」、「{時間} 到期」、「產生新連結」 | — |
| S31 已過期 | `expired: true` | 「連結已過期」、複製停用、「產生新連結」 | — |
| S31 裁判名單 | 三人已接受 | 依接受時間列出顯示名稱與接受時間 | 讀取失敗顯示錯誤＋「重新載入」 |
| S31 沒有裁判 | 空清單 | 空狀態文案 | — |
| S23 有效、已驗證 | 預覽未過期，已登入且已驗證 | 賽事名稱、到期時間、「接受邀請」；成功後顯示已成為裁判 | 409 依代碼顯示繁中訊息 |
| S23 未登入 | 有效連結 | 「註冊帳號」「登入」，帶 redirect 回原頁 | — |
| S23 未驗證 | 已登入未驗證 | 「接受邀請」停用並提示驗證 | — |
| S23 過期 | `expired: true` 或接受回 `REFEREE_INVITATION_EXPIRED` | 過期文案，不顯示接受 | — |
| S23 不存在 | 404 | 「找不到這個裁判邀請」＋回首頁 | — |
| S23 主辦方本人 | 接受回 `ORGANIZER_CANNOT_BE_REFEREE` | 「主辦方不能擔任自己賽事的裁判。」 | — |
| S23 接受成功 | 接受回 200 | 留在 S23 顯示「你已成為「{賽事名稱}」的裁判」＋「查看我執法的場次」（`/me/referee`）；身分清單查詢失效 | — |
| 賽事已結束／已取消 | 預覽或目前邀請 `accepting: false` | S23 不顯示「接受邀請」，改寫「這場賽事已結束或已取消，無法接受裁判邀請。」；S31 停用「產生新連結」並寫出同一原因 | — |
| S31 重新產生 | 舊連結仍有效 | 先 `ConfirmDialog`；確認後產生，舊連結失效 | 取消則不變 |
| S31 重新產生（已過期） | 舊連結已過期 | 直接產生，不確認 | — |

## Decisions

- 2026-11-05（使用者）：S23 接受成功後留在原頁顯示成功狀態「你已成為「{賽事名稱}」的裁判」，並提供「查看我執法的場次」連到 D 的 S13 `/me/referee`（PR #51；合併前用一般連結，不用型別化的 `Link`）。接受與預覽的回應沒有 tournament_id，不連到 S2。
- 2026-11-05（使用者）：後端在 `PublicRefereeInvitation`（預覽）與 `RefereeInvitationRead`（目前邀請、產生邀請的回應）新增 `accepting: bool`＝賽事不是 `finished`／`cancelled`（沿用 `ensure_accepting_referees` 的判斷）；`expired` 的意思不變。畫面據此提前顯示「這場賽事已結束或已取消，無法接受裁判邀請。」，S31 停用「產生新連結」並寫出原因。要重新產生 `frontend/src/client`，並刪除第一階段的那一筆延後項目。
- 2026-11-05（使用者）：S31「產生新連結」在舊連結仍有效時先以 `ConfirmDialog` 確認：標題「產生新連結」、內文「舊的邀請連結會立即失效，已收到舊連結的人要改用新連結。已接受的裁判不受影響。」、確認鈕「產生新連結」；舊連結已過期或從未產生時直接產生。

</frozen-after-approval>

## Code Map

- `backend/app/modules/tournaments/models.py` `PublicRefereeInvitation`、`RefereeInvitationRead` -- 新增 `accepting: bool`；`service.py` 的 `_invitation_to_read`、`preview_invitation` 依賽事狀態填入（`_REFEREE_CLOSED_STATUSES`，`ensure_accepting_referees` 同一個判斷）；`get_current_invitation` 要讀賽事狀態。`backend/tests/tournaments/test_referees.py` 補 `accepting` 的測試；`contracts/tournaments.md` 補欄位。
- `frontend/src/routes/organizer/tournaments/$tournamentId/route.tsx` -- 版面路由（`requireSignedIn`＋`AccountGate(is_organizer)`＋`OrganizerTournamentLayout`），子頁不必再檢查權限。
- `frontend/src/routes/organizer/tournaments/$tournamentId/matches.tsx` -- D 的 S30：新增子頁的寫法（`createFileRoute`、`head` 標題）。
- `frontend/src/features/tournaments/organizer-nav.ts:23-42` `tournamentNav` -- 新增「裁判」項目（lucide 圖示）。
- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx:41-72` `OrganizerTournamentLayout`；`organizer-queries.ts` `myTournamentQueryOptions`。
- `frontend/src/features/registration/InviteLinkField.tsx` -- props：`label`、`url`、`invalid?: {title?, reason}`、`note?`、`action?`；`COPIED_TEXT`。`features/registration/queries.ts:29` `teamInviteUrl` 的寫法照抄成 `refereeInviteUrl`。
- `frontend/src/routes/join.$inviteToken.tsx`、`features/registration/JoinTeamPage.tsx:67-165` -- S19：公開頁、未登入帶 `redirect` 到 `/signup`、`/login`、`VerificationRequired`、錯誤代碼對應。
- `frontend/src/features/identity/auth.ts` `useIsSignedIn`、`identitiesQueryOptions`；`VerificationRequired.tsx:48`；`redirect.ts` `safeRedirect`。
- `frontend/src/client/sdk.gen.ts` `TournamentsService.readRefereeInvitation`、`createRefereeInvitation`、`listTournamentReferees`、`previewRefereeInvitation`、`acceptRefereeInvitation`；型別 `RefereeInvitationRead`、`PublicRefereeInvitation`、`RefereeRead`。
- `frontend/src/components/common/{ConfirmDialog,EmptyState,HrefLink}.tsx`、`lib/api-error.ts`、`lib/feedback.ts`。
- `frontend/tests/unit/team-pages.test.tsx`（S19，`beforeAll` 預載路由）、`organizer-matches.test.tsx`（主辦方後台）、`auth-fixtures.ts`、`helpers.ts` `httpError` -- 測試寫法。
- `frontend/src/routeTree.gen.ts` -- 不手改，掛整個 `frontend/` 跑 `bunx vite build` 產生。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/tournaments/{models,service}.py`、`backend/tests/tournaments/test_referees.py`、`contracts/tournaments.md` -- 新增 `accepting`，涵蓋進行中、已結束、已取消；`bash scripts/generate-client.sh` 重新產生 client
- [x] `frontend/src/features/tournaments/referee-queries.ts` -- 查詢與 mutation（產生後讓目前邀請失效；接受後讓身分清單失效）、`refereeInviteUrl`
- [x] `frontend/src/features/tournaments/RefereesPage.tsx`、`routes/organizer/tournaments/$tournamentId/referees.tsx`、`organizer-nav.ts` -- S31
- [x] `frontend/src/features/tournaments/RefereeInvitePage.tsx`、`routes/referee-invite.$inviteToken.tsx` -- S23
- [x] `frontend/tests/unit/referee-pages.test.tsx` -- I/O 矩陣每一列；375 px 卡片版面
- [x] `_bmad-output/implementation-artifacts/deferred-work.md`、`sprint-status.yaml` -- 刪除「2.7 第二階段」與「預覽與目前邀請在賽事已結束／已取消時仍回 expired: false」兩筆；2.7 改 `review`

**Acceptance Criteria:**
- Given 主辦方在 S31 產生連結並複製，when 另一個已驗證帳號開啟並接受，then S31 的裁判名單出現該帳號
- Given 本 spec，when 執行 Verification 的所有指令，then 全部通過

## Implementation Notes

- epic-2 context 之後有 C 的 `4a758e9`（PR #50）動到 planning 文件且沒有 `Epic-Context: unaffected`；它改的是 epics.md 規則 6 與候補文案（Epic 3、6），epic-2 context 沒有這些內容，所以沿用現有 context，沒有重新產生。
- 產生的 client 會把 `null` 回應換成 `{}`（`client.gen.ts` 的 `data ?? {}`），所以 `readRefereeInvitation` 從未產生過時拿到的是 `{}` 而不是 `null`。單元測試 mock 成 `null` 時沒發現，瀏覽器實測才看到 S31 把 `{}` 當成邀請、顯示空白連結與「賽事已結束或已取消」。改為比照 `organizer-application.ts`：`"token" in data` 才算有邀請，測試的 mock 也改回傳 `{}`。
- S31 的裁判名單與 S30 的 `tournamentRefereesQueryOptions` 用同一個 query key（`["tournaments","organizer","referees",id]`），在 `referee-queries.ts` 另寫一份，沒有改 D 的檔案。名單沒有輪詢，靠 TanStack Query 預設的視窗重新取得焦點時重抓。
- 側欄新增「裁判」後，`organizer-tournaments.test.tsx`（S27 側欄項目）的預期清單補上「裁判」與它的網址；這是 2.2 的既有測試，只新增斷言。
- S23 未登入時的「登入」與頂欄的「登入」同名，測試限定在 S23 的內容區查詢；文字照 frozen 區塊寫「登入」，沒有沿用 S19 的「登入帳號」。
- 「產生新連結」在確認對話框的路徑，送出中與失敗訊息由 `ConfirmDialog` 顯示；直接產生（從未產生或已過期）失敗時用錯誤 Toast。

## Spec Change Log

## Review Triage Log

第一輪（2026-11-05）：Blind Hunter 15 筆、Edge Case Hunter 4 筆、Verification Gap 0 筆。

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind | S23 從 `RefereesPage` 匯入文案，公開頁連帶載入主辦方頁的程式 | low：直接把共用文案移到 `referee-queries.ts` | patch |
| 2 | Blind | tournaments 匯入 `features/competition/match-time` 的 `formatMatchDateTime`，依賴方向相反 | low：既有寫法（2.2 的 `OrganizerTournamentOverview`、2.4 的 `TournamentList`、`TournamentOverview` 都這樣用），不是本次造成 | 不處理 |
| 3 | Blind | `shouldRetry`、`businessErrorCode` 與其他模組重複 | low：抽共用要改別人的檔案，沒有已知的分歧 | 不處理 |
| 4 | Blind | S31 的 `refereesQueryOptions` 與 D 的 `tournamentRefereesQueryOptions` 用同一個 key 各定義一次 | medium：任一邊改 `queryFn` 會互相污染快取；改用 D 的定義會讓 tournaments 依賴 competition，應由 D 改為匯入本模組的定義 | defer |
| 5 | Blind | 接受回 `REFEREE_INVITATION_EXPIRED`／`TOURNAMENT_NOT_ACCEPTING_REFEREES` 後，卡片仍寫「{時間} 到期」 | low：這兩種錯誤讓預覽查詢失效重抓 | patch |
| 6 | Blind | 已是裁判的人重新開連結，S23 仍顯示「接受邀請」 | low：接受是冪等的，按下即顯示「你已成為…的裁判」；要先判斷需另查身分清單 | 不處理 |
| 7 | Blind、Edge | 從未產生邀請時，賽事查詢還沒完成或失敗，「產生邀請連結」仍可按 | low：賽事查詢有資料前停用 | patch |
| 8 | Blind | `get_current_invitation` 多讀一次賽事 | low：主辦方頁面、資料量小 | 不處理 |
| 9 | Blind | 產生成功後 `setQueryData` 又 `invalidateQueries`，多打一次 API | low：只寫入快取 | patch |
| 10 | Blind | 沒有測「確認對話框裡產生失敗」 | low：補測試 | patch |
| 11 | Blind | 測試名稱與內容不符；沒有測 `expired`＋`accepting: false` 同時成立的顯示優先順序 | low：改名並補測試 | patch |
| 12 | Blind | `InviteLinkField` 的 `action` 註解寫「連結失效時」，S31 在有效時也傳入 | low：元件本身支援，只是註解；PR 說明列出、請 C 確認 | 不處理 |
| 13 | Blind | 邀請網址對 token 做 `encodeURIComponent`，`redirect` 沒有 | low：統一用同一個 helper | patch |
| 14 | Blind | spec 狀態與 Triage Log 尚未更新 | false：審查進行中，本表即紀錄 | 不處理 |
| 15 | Blind | diff 檔名像 S27 | false：與交付內容無關 | 不處理 |
| 16 | Edge | 裁判名單以 ISO 字串 `localeCompare` 排序 | low：改用時間值比較 | patch |
| 17 | Edge | 產生回 409（賽事在別處被結束）後沒有重抓，`accepting` 停在舊值 | low：錯誤時讓目前邀請失效 | patch |
| 18 | Edge | 接受成功後背景重抓預覽失敗，成功畫面被錯誤畫面取代 | low：有快取資料時優先顯示內容（與 2.1 編輯頁同一修法） | patch |

## Verification

所有檔案與指令都在 `C:\Users\grace\espory-2-7-ui`（分支 `story/2-7-ui`）。

**Commands:**
- 前端 `bun run --filter frontend build`、`typecheck`、`bunx biome check`、`bunx vitest run --maxWorkers=4 tests/unit` -- 全部通過
- 後端 `bash scripts/test.sh`、`bash scripts/lint.sh` -- 全部通過；`bash scripts/generate-client.sh` 後 client 與後端一致

**Manual checks:**
- 瀏覽器以主辦方產生連結、以另一個已驗證帳號接受，確認名單更新；375 px 寬沒有橫向捲軸
