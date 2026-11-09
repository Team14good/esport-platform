---
title: 'Story 5.1 補遺：S12 我的隊伍顯示下一場'
type: 'feature'
created: '2026-11-09'
status: 'done'
baseline_commit: 'bf7bfa9b7f344776ac18bfbb14a914c725da0440'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** S12 我的隊伍只有報名狀態，抽籤後隊員看不到下一場的對手、時間與報到倒數，也沒有入口進 S4。Story 4.1（epics.md:1365）、5.1（:1575）、5.5（:1714）都有這條 AC（UX-DR37），目前沒有實作，也沒有登記延後。

**Approach:** competition 新增「我的隊伍下一場」API（登入者所屬、已參賽的每支隊伍各回最多一場），S12 每張 Registration status card 下方加一列下一場：對手、時間、報到倒數，點擊進 S4。registration 不呼叫 competition，S12 由前端組合兩支 API。

## Boundaries & Constraints

**Always:**
- 「下一場」= 該隊出現在 `team_a_id`／`team_b_id`、狀態不是 `confirmed`／`voided` 的場次中 `round_no` 最小的一場；沒有這種場次（已淘汰、賽事已結束）就不回。
- 只看 registration 狀態為 `drawn` 的隊伍；略過已取消的賽事（照 S13 的做法）。
- 經 `registration_port` 呼叫 registration 既有的公開函式 `list_my_teams`，不改 registration 的 service／models。
- 倒數沿用 `checkInCountdownPhase`、`Countdown`、`formatMatchDateTime`，時間顯示 Asia/Taipei。
- API 只讀，不 commit；需要登入（`CurrentAccount`）。
- 前端只用產生的 client；重新產生 `frontend/src/client`。

**Never:**
- 不改 C 的 `RegistrationStatusCard` 結構與既有 S12 行為；`MyTeamsPage` 只加可選的插槽 prop。
- 不在 Registration status card（整張是 `<a>`）裡巢狀另一個連結。
- 不做通知（期中版規則 2）、不做 6.3 的「計時暫停」提示（規則 7）。
- 不加資料表、不加遷移。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 兩隊已定、報到未開放 | 下一場 `scheduled`，兩隊都有 | 「下一場 vs {對手} · {時間}」＋ muted「報到開放」倒數；點擊進 S4 | N/A |
| 報到已開放／過預定時間 | 同上，時間已到 | 倒數依 `checkInCountdownPhase` 換成「距預定開始」(live)／「棄權期限」(appeal) | N/A |
| 對手未定 | 下一場有一方為空 | 「下一場 vs 待定 · {時間}」，對手說明沿用 S3 的來源文字；只有「報到開放」倒數 | N/A |
| 進行中 | 下一場 `live` | 「比賽進行中」(live 色)，連到該場 S4 | N/A |
| 申訴期／申訴中 | 下一場 `appeal_window`／`appealed` | 「等待結果確認」(muted)，連到該場 S4 | N/A |
| 已淘汰或賽事已結束 | 沒有未定案場次 | 不顯示下一場列 | N/A |
| 沒有已參賽隊伍 | 全部組隊中／候補 | API 回空陣列，S12 不變 | N/A |
| 未登入 | 無 token | 401 | 既有 401 處理 |
| 下一場 API 失敗 | 500／網路錯誤 | S12 照常顯示卡片，下一場列不出現 | 不擋整頁 |

## Decisions

- 2026-11-09（D）：S12 下一場放在 Registration status card 下方另一列（同一個 `<li>`），整列連到 S4；C 的卡片不動，`MyTeamsPage` 只加可選插槽。
- 2026-11-09（D）：進行中顯示「比賽進行中」、申訴期與申訴中顯示「等待結果確認」，都連到該場 S4；已淘汰、賽事結束不顯示。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/registration_port.py` -- 轉接檔；`_lookup` 模式，新增 `list_my_teams` 包裝，只回 `team_id, tournament_id, registration_status`。
- `backend/app/modules/registration/service.py:814` -- `list_my_teams(session, *, account_id) -> list[MyTeamCard]`，只呼叫不改。
- `backend/app/modules/competition/repository.py:62` -- `list_team_matches(session, tournament_id, team_id)`；可重用，或新增一支一次查多隊的查詢。
- `backend/app/modules/competition/service.py:432` `_public_matches`、`:1940` `list_my_referee_matches` -- S13 範本：組隊名、`round_name`、略過已取消賽事。
- `backend/app/modules/competition/models.py:66` `Match`、`:530` `RefereeMatch(PublicMatch)` -- 新回應模型照這個繼承 `PublicMatch`，加 `team_id`、`round_name`、`check_in_opens_at`。
- `backend/app/modules/competition/checkin.py:27` `check_in_opens_at` -- 報到開放時間。
- `backend/app/modules/competition/router.py:172` -- S13 路由；新路由 `GET /me/next-matches` 放旁邊。
- `frontend/src/features/registration/MyTeamsPage.tsx` -- C 的頁面；只加可選插槽 prop。
- `frontend/src/routes/me_.teams.tsx` -- 路由；傳入下一場元件。
- `frontend/src/features/competition/MatchCheckIn.tsx:42` `checkInCountdownPhase`；`components/common/Countdown.tsx`；`features/competition/match-time.ts`；`match-source.ts:14` `matchPath` -- 重用。
- `frontend/src/features/competition/referee-matches-queries.ts` -- query options 範本。
- 測試：`backend/tests/competition/conftest.py`（`FakeRegistration`、`draw_with`）、`test_referee_matches.py`（範本）；`frontend/tests/unit/team-pages.test.tsx:621`（S12）、`referee-matches.test.tsx`、`match-check-in.test.tsx`。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/registration_port.py` -- 新增 `list_drawn_teams_of_account`（呼叫 `list_my_teams`，過濾 `drawn`）-- 不跨模組直接 import。
- [x] `backend/app/modules/competition/models.py`、`service.py`、`repository.py`、`router.py` -- `NextMatch` 模型、`list_my_next_matches`、`GET /me/next-matches` -- 依 Always 的定義挑場次。
- [x] `backend/tests/competition/test_next_matches.py` -- I/O 矩陣每列（含對手未定、淘汰、賽事取消、未登入、只看 drawn），`frozen_clock`；寫進 `traceability.yaml`。
- [x] `frontend/src/client/*` -- 重新產生。
- [x] `frontend/src/features/competition/next-match-queries.ts`、`NextMatchRow.tsx` -- 查詢與一列顯示。
- [x] `frontend/src/features/registration/MyTeamsPage.tsx`、`frontend/src/routes/me_.teams.tsx` -- 插槽與接上。
- [x] `frontend/tests/unit/next-match-row.test.tsx`＋擴充 `team-pages.test.tsx` -- 各狀態、點擊路徑、API 失敗不擋頁。
- [x] `contracts/competition.md` -- 新 API 與 port 函式。

**Acceptance Criteria:**
- Given 已參賽隊伍的隊員，when 開 S12，then 該隊卡片下方顯示下一場，點擊進入該場 S4。
- Given 下一場確認晉級（5.5），when S12 重新取得資料，then 顯示新的下一場。
- Given 架構測試，when 執行，then competition 不直接 import registration 以外的上層模組，registration 不 import competition。

## Implementation Notes

- port：`registration_port.list_drawn_teams_of_account` 經 `_lookup("list_my_teams")` 呼叫，只讀 `team_id`、`tournament_id`、`registration_status`，在 port 內過濾 `drawn`，回傳 `DrawnTeamRef`；以字串 `"drawn"` 比對（`RegistrationStatus` 是 StrEnum），不 import registration 的 models。registration 沒有 `list_my_teams` 時 503 `REGISTRATION_UNAVAILABLE`，前端當作 API 失敗、不顯示下一場列。
- repository 新增 `list_unsettled_team_matches`：一次查多隊、排除 `confirmed`／`voided`，依輪次、季軍賽在後、`slot_no` 排序；service 取每隊第一次出現且 `tournament_id` 相符的場次。
- `NextMatch(PublicMatch)` 除了 Code Map 的 `team_id`、`round_name`、`check_in_opens_at`，另加 `forfeit_deadline`（只在待開打且兩隊都確定時有值，同 `PublicMatchDetail`）：I/O 矩陣第 2 列的「棄權期限」倒數需要它。沒有加 `tournament_id`，S4 連結的賽事 id 取自同一張卡片的 `MyTeamCard.tournament_id`。
- 前端：`MyTeamsPage` 加可選 `renderTeamExtra(card)`，插在同一個 `<li>` 的卡片下方；路由 `me_.teams.tsx` 傳入 `MyTeamNextMatch`。只有 `drawn` 卡片啟用查詢（所有卡片共用同一個 query），所以沒有已參賽隊伍時不呼叫 API。對手未定時下方加一行 caption「對手：{source}」，倒數只在「報到開放」階段顯示。輪次 caption「4 強 · M5」，季軍賽只寫「季軍賽」（同 S4 header）。
- 驗證時發現：service 第二個迴圈原本誤用前一個迴圈留下的 `match` 變數算報到截止（mypy 的型別錯誤揭露），已修正並加 `test_fields_are_per_team_with_mixed_rounds` 防止回歸。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap）：

| # | 來源 | 發現 | 判定 | 依據 | 處理 |
|---|---|---|---|---|---|
| 1 | VG | port 只對替身測過，沒對真的 `MyTeamCard` | medium | 測試全以 `SimpleNamespace` 取代 `list_my_teams`，`_lookup` 回 `Any`，mypy 也看不到欄位改名；改名後 S12 下一場會靜默消失 | patch：`test_registration_port.py` 加真 `MyTeamCard` 測試 |
| 2 | BH、EC | 停在 S12 時下一場不會更新；過棄權期限後列上沒有狀態 | medium | `nextMatchesQueryOptions` 沒有 `refetchInterval`，`onExpire` 只重新 render；全域只設 `retry` | patch：倒數歸零時 invalidate，加 60 秒輪詢 |
| 3 | BH | 「對手未定只顯示報到開放」靠比對中文標籤 | low | `checkInCountdownPhase` 回傳的 `label` 是介面文字，改字就失效；`variant` 只有報到開放是 `muted` | patch：改比 `variant` |
| 4 | BH | 沒測輪空隊伍的下一場 | low | 程式讀來正確（輪空隊直接在第二輪、只有一方時 `forfeit_deadline` 為空），但校園賽常見 5～7 隊，沒有測試鎖住 | patch：加 6 隊測試 |
| 5 | BH | 沒測準決賽敗隊的下一場是季軍賽 | low | 排序「同輪季軍賽在後」與 `round_name="季軍賽"` 分支沒有後端測試 | patch：加 4 強確認後勝敗隊的測試 |
| 6 | BH | `traceability.yaml` 只標 5.1 | low | spec 寫明這條 AC 屬於 4.1、5.1、5.5 | patch：stories 補 4.1、5.5 |
| 7 | BH | contracts 的 port 函式寫成段落、沒寫賽事已結束回空 | low | S13 那列寫明 finished／cancelled，本列沒有 | patch：補一行說明 |
| 8 | BH | `World.confirm` 跳過進行中與送出 | false | `confirm_match` 只要求申訴期，測的是晉級後下一場的選擇，與送出流程無關 | 駁回 |
| 9 | BH | 每個對戰表各查一次賽事與隊名 | low | 一位使用者同時參賽的賽事通常 1～2 場，批次化要改 `_public_matches`，日常遇不到 | 駁回 |
| 10 | BH | 下一場列晚出現、失敗時重試三次 | low | 只是外觀位移，加骨架要多一個狀態分支 | 駁回 |
| 11 | BH | 連結內含倒數、可及名稱沒有本隊隊名 | low | `role="timer"` 預設不主動朗讀；列在本隊卡片下方、內容含對手與時間，可區分；改 `aria-label` 會蓋掉倒數 | 駁回 |
| 12 | BH | 沒用 `matchPath`、`== null` | low | TanStack `Link` 用 `to`＋`params` 有型別檢查，比字串路徑好 | 駁回 |
| 13 | EC | `list_my_teams` 回傳同一隊兩次 | false | `team_member` 有 `(tournament_id, account_id)` 唯一鍵，一個帳號在一場賽事只屬於一隊，`list_my_teams` 依成員資格迴圈不會重複 | 駁回 |

## Verification

**Commands:**
- `docker compose run --rm backend pytest tests/competition/test_next_matches.py tests/test_architecture.py tests/test_traceability.py` -- expected: 全過
- `bunx tsc --noEmit && bunx vitest run tests/unit/next-match-row.test.tsx tests/unit/team-pages.test.tsx`（oven/bun:1 容器）-- expected: 全過
- `scripts/lint.sh`、biome -- expected: 通過
