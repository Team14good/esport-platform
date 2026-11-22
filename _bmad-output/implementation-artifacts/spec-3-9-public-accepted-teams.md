---
title: 'Story 3.9：公開正取名單與取消賽事通知（第 1 部分）'
type: 'feature'
created: '2026-11-22'
status: 'in-progress'
baseline_commit: '41c2f4fb704d67620feb598c86f046b5ba4c96e6'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-4-file-report.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** S2 只有「總覽」「對戰表」兩個分頁，觀眾看不到哪些隊伍已正取（FR-34）；總覽在開放報名期間也沒有「已正取隊數／名額」（UX-DR38）。6.4 期中只在總覽放「檢舉隊伍」，正取隊伍每列的「檢舉」等本 Story 補上。

**Approach:** registration 新增不需登入的公開 API，回傳某賽事正取隊伍的隊名（校園賽優先期內不公布，改回公布時間）；前端在 S2 加「正取隊伍」分頁（每列對隊長顯示「檢舉」，沿用 6.4 的 S20），總覽開放報名時顯示已正取隊數。取消賽事的通知等 Story 2.6，見〈第 2 部分〉。

## Decisions（2026-11-22，王閎立；flow-bot 無人值守時依推薦做法選定，組員可在 PR 提出異議）

- **列入名單的狀態**：`accepted`、`drawn`、`retired`（目前握有或曾經參賽的名額）。`disqualified` 不列：抽籤前取消資格的名額會被遞補，列進來會超過名額；抽籤後的取消資格已由 S3 對戰樹標示。`pending`、`waitlisted` 不列。
- **只回 id 與隊名**：AC 寫「看到正取隊伍的隊名」，不列隊員與遊戲 ID；schema 名為 `Public*`（AD-19）。排序依 `(隊名, id)`，與 6.4 `reportable-teams` 一致。
- **優先期內不公布由後端決定**：校園賽且 `now < priority_end` 時回 `announce_at = priority_end`、`teams = []`，前端只依 `announce_at` 顯示空狀態與倒數。`PublicTournament` 沒有 `mode`，而且 tournaments 是 B 的模組，不為此改它的 schema。`upcoming` 的校園賽同樣適用（優先期還沒結束）。自訂模式（3.10 尚未完成）一律直接公布。
- **公布後沒有正取時的空狀態**：「目前還沒有正取隊伍。」（EXPERIENCE.md 只定義了優先期內的文案，比照〈通用狀態〉「一句事實」補一句，不加按鈕）。
- **總覽的已正取隊數**：只在 `open` 顯示，文字「已正取 {n}／{capacity} 隊」，放在報名截止倒數之下、「建立隊伍」之上；n 取同一支公開 API 的 `teams.length`（優先期內為 0，照實顯示）。不另開計數 API。
- **已取消的賽事**：API 照常回傳名單（資訊唯讀，FR-34）；「檢舉」依 6.4 規則在 `finished`、`cancelled` 時不顯示。
- **每列「檢舉」**：顯示條件與 6.4「檢舉隊伍」相同（已登入、此賽事有四種狀態隊伍、是隊長、賽事未結束或取消），且該列隊伍在 `reportable-teams` 之內（自己的隊伍不在，FR-32）。`has_open_report` 的列不顯示按鈕，改顯示「已檢舉・處理中」（`muted`）。按「檢舉」開 6.4 的 `ReportTeamDialog`，`teams` 只傳該列一隊。
  - 不改 C 的 `ReportTeamDialog`／`ReportTeamEntry`（CLAUDE.md：動到別人的模組只新增檔案或公開函式），所以對話框不會預先選好對象，使用者在只有一個選項的「檢舉對象」選一次。若 C 同意，之後可在 `ReportTeamDialog` 加選填的預設對象，PR 說明會列出。
  - 判斷隊長身分的查詢鏈在新檔案重寫一份（與 `ReportTeamEntry` 共用同樣的 query key，快取共用），不抽出共用 hook（抽出要改 C 的檔案）。
- **分頁路由**：`/tournaments/$tournamentId/teams`，分頁值 `teams`、標籤「正取隊伍」，排在「對戰表」之後（`TournamentTabs.tsx` 註解已預留 3.9 在白名單加一項）。
- **e2e**：新增假資料（`page.route`）的 `accepted-teams.spec.ts` 驗證分頁三種狀態與版面（desktop、mobile-375）；真 API 的觀眾測試（`spectator.spec.ts`）加一步「抽籤後觀眾在正取隊伍分頁看到所有隊伍」。deferred-work 第 180 行要求的是「完整賽事演練、分配後抽籤前」，本份只在觀眾測試補上抽籤後的檢查，該項不刪除。

## Boundaries & Constraints

**Always:**
- 後端 API：`GET /api/v1/tournaments/{tournament_id}/accepted-teams`，不需登入（GET 不必加 `PUBLIC_WRITE_ROUTES`），回 `PublicAcceptedTeams{announce_at: datetime | None, teams: list[PublicAcceptedTeam{id, name}]}`；賽事不存在 404 `TOURNAMENT_NOT_FOUND`（沿用 `tournaments_service.get_tournament`）。
- registration 新增公開函式 `list_public_accepted_teams(session, *, tournament_id) -> PublicAcceptedTeams`，時間用 `clock.now()`；查詢沿用既有 `repository.list_teams_by_status`，在 Python 依 `(name, id)` 排序。回應不含 Email、學校、遊戲 ID、段位、截圖鍵值。
- 前端只呼叫產生的 `frontend/src/client`；新 query 加在 `features/registration/queries.ts`（只新增匯出）。
- 優先期倒數用 `Countdown`，`label="優先期結束"`、`variant="muted"`，歸零後重抓名單（照 S2 的倒數歸零輪詢，單次失敗不重試）。
- 介面文字：分頁「正取隊伍」；空狀態「優先期結束後公布正取隊伍。」與「目前還沒有正取隊伍。」；按鈕「檢舉」；「已檢舉・處理中」；總覽「已正取 {n}／{capacity} 隊」。
- 分頁頁面與「對戰表」分頁相同骨架：取消時 destructive banner「此賽事已取消」、`TournamentHeader`、`TournamentTabs current="teams"`；賽事不存在顯示 404 頁。手機 375px 不出現橫向捲動。

**Never:**
- 不做取消賽事的通知、不登錄 `TournamentCancelled` 的收件規則、不寫假的 `TournamentCancelled` 事件或 stub（第 2 部分）。
- 不改 tournaments 的 schema 與既有函式；`TournamentTabs.tsx` 只在白名單加一項、`TournamentOverview.tsx` 只在 `open` 分支加一個掛載點（B 的檔案，PR 說明列出）。
- 不改 registration、disputes 的既有函式與元件（C 的模組，只新增）；不改 S2 預設分頁的規則。
- 不新增資料表或遷移。

## I/O & Edge-Case Matrix

時鐘以 `frozen_clock` 控制；「四種狀態」＝`pending`、`accepted`、`waitlisted`、`drawn`。

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已分配 | 校園賽 `open`、優先期已過；隊伍 B（accepted）、A（accepted）、C（waitlisted）、D（pending）、E（forming） | 200，`announce_at == null`，`teams` 為 A、B（依隊名），每項只有 `id`、`name` | N/A |
| 抽籤後 | 賽事 `published`；隊伍為 `drawn`、`retired`、`disqualified`、`rejected`、`withdrawn` 各一 | `teams` 只有 `drawn`、`retired` 兩隊 | N/A |
| 優先期內 | 校園賽 `open`、`now < priority_end`（含有 `accepted` 的異常資料） | `announce_at == priority_end`、`teams == []` | N/A |
| 尚未開放 | 校園賽 `upcoming` | `announce_at == priority_end`、`teams == []` | N/A |
| 優先期結束那一刻 | `now == priority_end` | 公布（`announce_at == null`） | N/A |
| 自訂模式 | `mode == custom`、`now < priority_end`、有 `accepted` | 直接公布 | N/A |
| 已取消 | 賽事 `cancelled`、有 `accepted` | 照常回傳名單 | N/A |
| 未登入 | 無 token | 200 | N/A |
| 賽事不存在 | 隨機 id | 拒絕 | 404 `TOURNAMENT_NOT_FOUND` |
| 不洩漏個資 | 隊員有遊戲 ID、學校、截圖 | 回應 JSON 只有 `announce_at`、`teams[].id`、`teams[].name` | N/A |
| S2 分頁：優先期內 | `announce_at` 有值 | 空狀態「優先期結束後公布正取隊伍。」＋「優先期結束」倒數（muted）；歸零後重抓 | N/A |
| S2 分頁：名單 | `teams` 2 隊 | 依回傳順序列出隊名 | 載入失敗顯示錯誤訊息與「重新載入」 |
| S2 分頁：空名單 | `announce_at == null`、`teams == []` | 空狀態「目前還沒有正取隊伍。」 | N/A |
| 每列「檢舉」 | 登入者是 A 隊長（accepted）；B 在 `reportable-teams`、`has_open_report == false`；C 為 `has_open_report == true` | A 列沒有「檢舉」；B 列有「檢舉」，按下開 S20、檢舉對象只有 B；C 列顯示「已檢舉・處理中」 | S20 的錯誤沿用 6.4 |
| 「檢舉」不顯示 | 觀眾／隊員／組隊中的隊長／賽事 `finished` 或 `cancelled` | 所有列都沒有「檢舉」；隊員不呼叫 `reportable-teams` | N/A |
| 總覽已正取數 | 賽事 `open`、名額 16、正取 3 隊 | 總覽顯示「已正取 3／16 隊」；其他狀態不顯示 | 名單載入失敗時不顯示這一行 |
| 分頁列 | 任何 S2 頁面 | 分頁依序為「總覽」「對戰表」「正取隊伍」，點「正取隊伍」到 `/tournaments/{id}/teams` | N/A |

</intent-contract>

## 第 2 部分（等 Story 2.6）

Story 2.6（B，取消賽事）尚未完成：目前沒有取消賽事的 API、沒有 `TournamentCancelled` 事件類別，也就無法登錄收件規則。2.6 合併後接著做：

- **驗收條件**：Given 有報名隊伍的賽事，when 主辦方取消賽事（`TournamentCancelled` 事件），then 所有已送出報名的隊伍，隊長與選手都收到站內通知與 Email（FR-10）。
- **缺什麼**：2.6 在 `backend/app/modules/tournaments/models.py` 定義的 `TournamentCancelled(Event)`（至少要有 `tournament_id`）與發出它的取消流程。
- **之後接在哪裡**：
  - `backend/app/modules/notifications/rules.py`：仿照 `_registration_allocated`／`_bracket_drawn`，新增 `_tournament_cancelled` 並 `register(TournamentCancelled, ...)`；收件人是報名狀態為「已送出」的隊伍成員。
  - 「已送出」的狀態集合要在 2.6 合併後確認（建議 `pending`、`accepted`、`waitlisted`、`drawn`，與 6.4 的四種狀態相同；`forming`、`rejected`、`withdrawn` 不通知）。隊伍用 registration 既有的 `list_teams_by_status`，成員用 rules.py 既有的 `_member_ids`。
  - 通知文案（站內與 Email 範本 `notifications/templates/`）照 1.6 的格式，連結到 S2；測試放 `backend/tests/notifications/`，並在 `backend/tests/traceability.yaml` 標 `stories: ["3.9"]`、`frs: [FR-10]`。
- 第 2 部分完成後，spec `status` 與 `sprint-status.yaml` 才改為完成。

## Code Map

- `backend/app/modules/registration/service.py` -- `list_teams_by_status`（:1255，依隊伍 id 排序、只回 `TeamSummary`）可直接沿用；`tournaments_service.get_tournament`（tournaments `service.py:397`，回 `TournamentRead`，含 `mode`、`priority_end`）；新公開函式放在檔尾的公開函式區附近。
- `backend/app/modules/registration/repository.py` -- `list_teams_by_status`（join team 與 registration，`status IN (...)`），不需新增查詢。
- `backend/app/modules/registration/models.py` -- `RegistrationStatus`（:36）、`TeamSummary`（:332）；新增 `PublicAcceptedTeam`、`PublicAcceptedTeams`。
- `backend/app/modules/registration/router.py` -- 既有公開 GET 範例 `preview_team_invite`（:45，不需登入、只拿 `SessionDep`）；新增 `list_accepted_teams` 路由。
- `backend/app/modules/tournaments/models.py:142` `mode: TournamentMode`（`campus`／`custom`）。
- `backend/tests/helpers.py` -- `make_account`、`make_game`、`make_tournament`；建隊與改狀態可參考 `backend/tests/registration/test_report_functions.py`（6.4 對 `list_teams_by_status` 的測試）與 `test_teams.py:64` `_set_status`。
- `backend/tests/traceability.yaml` -- 新測試檔要加一列（`tests/test_traceability.py` 檢查）。
- `frontend/src/features/tournaments/TournamentTabs.tsx` -- `TOURNAMENT_TABS` 白名單（B，註解預留 3.9）；`TournamentTab` 型別由它推導。
- `frontend/src/features/tournaments/TournamentOverview.tsx` -- `StatusPanel` 的 `open` 分支（倒數＋`CreateTeamEntry`），只加一個掛載點。
- `frontend/src/features/competition/TournamentBracketPage.tsx` -- 分頁頁面骨架範本（banner、`TournamentHeader`、`TournamentTabs`、404、載入與錯誤、`useTournamentTitle`、倒數歸零重抓）。
- `frontend/src/routes/tournaments/$tournamentId/bracket.tsx` -- 路由檔範本；新增 `teams.tsx` 後需重新產生 `routeTree.gen.ts`（掛整個 `frontend/` 跑 `bunx vite build`）。
- `frontend/src/features/disputes/ReportTeamEntry.tsx` -- 隊長判斷查詢鏈（`myTeamsQueryOptions` → `teamQueryOptions(...).my_role` → `reportableTeamsQueryOptions`）、`useFileReport`、成功 Toast「已送出檢舉」；`ReportTeamDialog.tsx` 的 props（`open`、`onOpenChange`、`teams`、`uploadProgress`、`onSubmit`）。都不修改。
- `frontend/src/components/common/{EmptyState,Countdown}.tsx` -- 空狀態與倒數元件。
- `frontend/tests/unit/report-team.test.tsx`、`tournament-bracket-page.test.tsx`、`tournament-pages.test.tsx` -- 單元測試的 mock 寫法（client mock、QueryClient 包裝）。
- `frontend/tests/e2e/spectator.spec.ts:103` -- 真 API 觀眾測試；`support/match-api.ts` 假資料寫法。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/registration/models.py` -- 新增 `PublicAcceptedTeam{id, name}`、`PublicAcceptedTeams{announce_at, teams}`
- [x] `backend/app/modules/registration/service.py` -- 新增 `list_public_accepted_teams`（規則見 Decisions 與 Boundaries）
- [x] `backend/app/modules/registration/router.py` -- 新增 `GET /tournaments/{tournament_id}/accepted-teams`
- [x] `backend/tests/registration/test_public_accepted_teams.py` -- I/O 矩陣後端各列（含優先期結束那一刻、自訂模式、回應欄位只有三個、未登入）；`backend/tests/traceability.yaml` 加一列（integration、`["3.9"]`、`[FR-34]`）
- [x] `frontend/src/client` -- `scripts/generate-client.sh` 重新產生
- [x] `frontend/src/features/registration/queries.ts` -- 新增 `publicAcceptedTeamsQueryOptions(tournamentId)`
- [x] `frontend/src/features/disputes/AcceptedTeamReportAction.tsx` -- 新檔：每列「檢舉」的資格判斷 hook 與按鈕／「已檢舉・處理中」，以及開 `ReportTeamDialog`（只傳該列一隊）
- [x] `frontend/src/features/registration/AcceptedTeamsPage.tsx` -- 新檔：「正取隊伍」分頁頁面（骨架、優先期空狀態與倒數、名單、空名單、錯誤）；匯出總覽用的 `AcceptedCount`
- [x] `frontend/src/routes/tournaments/$tournamentId/teams.tsx` -- 新路由；重新產生 `routeTree.gen.ts`
- [x] `frontend/src/features/tournaments/TournamentTabs.tsx` -- 白名單加「正取隊伍」；更新檔頭註解
- [x] `frontend/src/features/tournaments/TournamentOverview.tsx` -- `open` 分支加 `<AcceptedCount>` 掛載點
- [x] `frontend/tests/unit/accepted-teams.test.tsx` -- I/O 矩陣前端各列（分頁三種狀態、倒數歸零重抓、每列檢舉的顯示條件與只傳一隊、隊員不打 `reportable-teams`、總覽已正取數只在 `open`、分頁順序）
- [x] `frontend/tests/e2e/accepted-teams.spec.ts` -- 假資料：觀眾看名單、優先期內空狀態；desktop 與 mobile-375 無橫向捲動並截圖
- [x] `frontend/tests/e2e/spectator.spec.ts` -- 真 API 測試加一步：抽籤後觀眾在「正取隊伍」看到所有隊伍
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 3-9 維持 `in-progress`（第 1 部分）

**Acceptance Criteria:**
- Given 已分配名額的賽事，when 未登入的觀眾開啟 S2「正取隊伍」，then 看到正取隊伍的隊名，回應與畫面都沒有學校、Email、遊戲 ID 等個資。
- Given 開放報名的賽事，when 開啟 S2 總覽，then 顯示「已正取 n／名額 隊」。
- Given 校園賽、優先期尚未結束，when 開啟「正取隊伍」，then 顯示「優先期結束後公布正取隊伍。」與優先期結束倒數。
- Given 後端與前端，when 執行 `ci.yml` 的檢查，then 全部通過。

## Spec Change Log

## Review Triage Log

## Design Notes

- 公布與否放在後端：前端不知道賽事模式，而且「優先期內就算有 `accepted` 也不公布」的規則集中在一處、可測。
- 為什麼不用 `PublicTournament` 加計數：tournaments 不能呼叫 registration（呼叫方向 registration → tournaments），計數只能由 registration 提供。

## Verification

**Commands:**
- `docker compose up -d --build --wait` 後 `docker compose exec -T backend bash scripts/test.sh` -- 全綠
- `docker compose exec -T backend bash scripts/lint.sh` -- 通過
- 前端 `bun run build`、typecheck、`bunx biome check`、`bun run test:unit` -- 通過（指令照 `.github/workflows/ci.yml`）
- `scripts/generate-client.sh` 後 `git diff --exit-code frontend/src/client`；Alembic 單一 head
