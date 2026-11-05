---
title: 'S13 我執法的場次與「裁判」身分（4.4 最後一塊）'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'cd0cce84ce38d57c4fadc6af7269d0d01b9dfc24'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-4-4-assign-referee-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.4 後端與 S30 已能把裁判指派到場次，但裁判沒有地方看到自己被指派的場次；身分切換器也沒有「裁判」。epics 4.4：接受過任一裁判邀請的帳號，身分切換器出現「裁判」（多個賽事合併為一項），首頁 S13 依賽事分組列出被指派的場次與預定時間，點擊進入 S4；沒有指派時顯示「主辦方還沒有指派場次給你。」；5.1：兩隊都報到時該場標示「可開始」。

**Approach:** competition 新增「我執法的場次」查詢與 `GET /me/referee/matches`；identity 新增 `IdentityKey.REFEREE` 與一個註冊點，由組裝層把 tournaments 的「是否為任一賽事的裁判」接上（identity 是最底層，不能往上呼叫）；前端新增 `/me/referee` 頁面與身分圖示。

## Boundaries & Constraints

**Always:**
- 呼叫方向不變：identity 只新增 `register_referee_lookup(fn)`（存一個 `Callable[[Session, UUID], bool]`），`list_identities` 在「我的隊伍」之後、「主辦方後台」之前，lookup 存在且回真時加 `Identity(key=REFEREE, label="裁判", home_path="/me/referee")`；沒註冊時不加、不報錯。
- tournaments 新增公開函式 `has_referee_role(session, *, account_id) -> bool`（任一賽事有 `TournamentReferee` 列即為真，不看賽事狀態）；註冊在組裝層（`app/api/main.py` 或 `app/main.py`，選架構測試允許的那個），不在 tournaments 匯入時產生副作用。
- `GET /me/referee/matches`（`CurrentAccount`）：回 `list[RefereeTournamentMatches]`，每組 `{tournament: PublicTournamentRef, matches: list[RefereeMatch]}`；`RefereeMatch` 為 `PublicMatch` 的欄位＋`round_name`＋`both_checked_in: bool`。只列 `referee_account_id` 為登入者、狀態不是 `voided` 的場次；組內依 `scheduled_at`、再依 `code`；各組依組內最早的 `scheduled_at`。沒有指派回 `[]`。不需要是裁判身分也能呼叫（沒有就是空的）。
- 「可開始」：`status == scheduled` 且 `both_checked_in`；其他狀態顯示 `MATCH_STATUS_BADGES`。
- S13 頁 `/me/referee`（`requireSignedIn`，檔名照 `me_.teams.tsx` 的寫法）：依賽事分組（組標題為賽事名稱），每場顯示場次（`matchLabel`）、輪次、對戰（隊名或待定說明）、時間（`formatMatchDateTime`）、狀態或「可開始」，整列連到 S4。空狀態「主辦方還沒有指派場次給你。」；載入失敗顯示錯誤與重新載入。
- `IDENTITY_ICONS` 補 `referee`（lucide 圖示，例如 `FlagIcon` 或 `GavelIcon`）。

**Never:**
- identity 不 import tournaments／competition；不改 identity、tournaments 的既有函式簽名（`list_identities` 內部可以加判斷）。
- 不做通知、分頁（期中規模）、S4 的任何變更。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 身分：裁判 | 接受過任一賽事的裁判邀請 | 身分清單有「裁判」→ `/me/referee`，位置在「我的隊伍」之後 | — |
| 身分：多賽事 | 是兩個賽事的裁判 | 只有一項「裁判」 | — |
| 身分：非裁判 | 沒接受過邀請 | 沒有「裁判」 | — |
| 列表 | 兩個賽事各被指派數場 | 依賽事分組、組內依時間 | — |
| 可開始 | 待開打且兩隊都已報到 | 該場標示「可開始」 | — |
| 已取消 | 指派的場次被取消（季軍賽 voided） | 不列出 | — |
| 收回／改派 | 場次改派給別人 | 不再出現在原裁判的列表 | — |
| 沒有指派 | 是裁判但沒有指派 | `[]`；S13 空狀態「主辦方還沒有指派場次給你。」 | — |
| 未登入 | — | API 401；頁面導向登入 | — |

## Decisions

- 2026-11-04（使用者）：先做 S13，S27 抽籤按鈕等 C 的 registration 函式合併後再做。
- 2026-11-04（使用者）：「裁判」身分用 identity 開註冊點的做法（不違反呼叫方向；PR 說明列出動到 A 的 identity 模組）。
- 2026-11-04（使用者）：核准草稿：列出所有被指派、未取消的場次（含已結束，用狀態徽章區分）、依賽事分組、不分頁。

</frozen-after-approval>

## Code Map

- `backend/app/modules/identity/{models,service}.py` -- `IdentityKey`（389）、`list_identities`（554，目前 `session` 未使用、有 `noqa: ARG001`）
- `backend/app/modules/tournaments/{service,repository}.py` -- `is_referee`（725）、`TournamentReferee.account_id` 有索引
- `backend/app/api/main.py`、`backend/app/main.py` -- 組裝層；`backend/tests/test_architecture.py` 的規則
- `backend/app/modules/competition/{models,repository,service,router}.py` -- `PublicMatch`、`_public_matches`、`get_public_match`（`round_name`、`check_in` 的寫法）、`bracket_rules.round_name`、`list_check_ins`
- `frontend/src/routes/me_.teams.tsx`、`features/registration/MyTeamsPage.tsx` -- 頁面寫法；`features/identity/identity-icons.ts`
- `frontend/src/features/competition/` -- `match-status.ts`（`matchLabel`、`MATCH_STATUS_BADGES`）、`match-time.ts`、`OrganizerMatchesPage.tsx` 的對戰欄寫法
- 測試：`backend/tests/identity/` 中 `list_identities` 的測試、`tests/competition/test_assign_referee.py` 的 `Setup.referee()`；前端 `tests/unit/organizer-matches.test.tsx`、S12 的測試

## Tasks & Acceptance

**Execution:**
- [x] identity：`IdentityKey.REFEREE`、`register_referee_lookup`、`list_identities`
- [x] tournaments：`has_referee_role`；組裝層註冊
- [x] competition：`RefereeMatch`、`RefereeTournamentMatches`、repository 查詢、`list_my_referee_matches`、`GET /me/referee/matches`
- [x] 後端測試：I/O 矩陣每一列（身分清單在真的組裝下也出現「裁判」）
- [x] `scripts/generate-client.sh` 重新產生 client
- [x] 前端：`me_.referee.tsx`、`features/competition/RefereeMatchesPage.tsx`（＋queries）、`IDENTITY_ICONS`；重新產生 `routeTree.gen.ts`；單元測試
- [x] contracts（competition 的 API 表與型別、identity／tournaments 的新公開函式若有 contracts 檔一併）、`deferred-work.md` 刪除 S13 項目、`sprint-status.yaml` 4.4 註記

**Acceptance Criteria:**
- Given 透過 S30 指派 API 被指派的裁判，when 呼叫 `GET /me/referee/matches`，then 該場出現；收回後消失。
- Given 接受過邀請的帳號，when `GET /me/identities`（或現有身分 API），then 有 `referee` 一項。

## Implementation Notes

- 註冊點放在 `app/api/main.py`（進入點，架構測試允許組裝任何模組）；`app.main` 匯入它，所以真的組裝下的測試看得到「裁判」。只直接呼叫 `identity_service.list_identities` 而沒載入組裝層時沒有註冊，`test_no_referee_identity_without_registered_lookup` 涵蓋這條路徑。
- `Match.referee_account_id` 沒有索引，`GET /me/referee/matches` 在期中規模直接掃表；規模變大時要補索引（需另開 Alembic 遷移，這次未加以免動 schema）。
- `both_checked_in` 以 `CheckIn` 列與兩個已確定隊伍比對（任一方待定為 false）；`RefereeMatch.round_name` 由後端提供，前端直接使用。
- `routeTree.gen.ts`：掛整個 `frontend/` 跑 `bunx vite build`，route tree 在 vite 因舊映像缺 `@radix-ui/react-alert-dialog` 而打包失敗前已產生並寫回，內容只新增 `/me_/referee`。
- 測試替身 `FakeRegistration` 只記得最近一次抽籤的隊伍，兩個賽事的測試把 `names` 設為空 dict，隊名顯示為「未知隊伍」，不影響分組與排序的驗證。

## Spec Change Log

- 2026-11-04（審查第 1 輪）：Boundaries 的「未取消」解讀為場次不是 `voided`，且所屬賽事不是 `cancelled`。取消賽事不會把場次改成 `voided`，不過濾的話已取消賽事的場次仍會列出、甚至標「可開始」；已結束（`finished`）的賽事維持列出。

## Review Triage Log

第 1 輪（2026-11-04）：Blind Hunter 11 項、Edge Case Hunter 17 項（另列 8 項已處理）、Verification Gap 約 15 個缺口，合併去重後如下。沒有 intent_gap；「未取消」的解讀記在 Spec Change Log。

| # | 來源 | 發現 | 判定 | 證據與處理 |
|---|---|---|---|---|
| 1 | Blind | `zip(strict=True)` 依位置配對，`_public_matches` 順序或長度變了就 500 或配錯列 | medium | patch：改以 match id 對應 |
| 2 | Blind、Edge | 已取消賽事的場次仍列出、可能標「可開始」 | medium | 取消賽事不會把場次改成 voided。patch：排除 `cancelled` 賽事，已結束維持列出；補測試；記入 Spec Change Log |
| 3 | Edge | 註冊的身分查詢拋例外時 `/me/identities` 整個失敗（每頁都會呼叫） | medium | patch：記 log、略過「裁判」，補測試 |
| 4 | Blind、VG | 未註冊的測試在結尾裝新 lambda，刪掉組裝層的註冊也不一定會紅、且污染全域 | medium | patch：fixture 存原值並還原；新增不碰註冊的組裝層測試，實際刪掉註冊確認會紅 |
| 5 | VG、Edge | 待定一方、換隊後舊報到、分組最早時間、同時間依 `code`、同時間依賽事名、`round_name` 字串（含季軍賽）、進行中／已確認仍列出、平台管理員兼裁判的順序都沒測 | medium | patch：逐項補測試（`test_referee_matches.py` 12→24） |
| 6 | VG | 前端測試用元件匯出的常數比對空狀態與「可開始」，改字不會紅；錯誤訊息沒斷言 | low | patch：改用字面字串，補錯誤訊息斷言 |
| 7 | Edge | `assert bracket is not None` 在 `-O` 下失效 | low | patch：改成記 log 並略過 |
| 8 | Blind | contracts 沒寫分組與排序的平手規則 | low | patch：寫明 |
| 9 | Blind | `referee_account_id` 沒有索引只記在 spec | low | patch：新增延後項目 |
| 10 | Blind | `last_updated` 往回寫 | low | patch |
| 11 | Blind | `scheduled_at` 可能是 None 導致排序 `TypeError` | false | 欄位 NOT NULL（`models.py:96`） |
| 12 | Blind、Edge | 每個賽事各查一次（N+1） | low | 裁判通常只有少數賽事，期中規模。reject |
| 13 | Blind、Edge | S13 query 沒有被 S30／S4 的變更 invalidate | low | 不同使用者的畫面；TanStack 預設 focus 時重抓。reject |
| 14 | Edge | `round_no` 異常時 `round_name` 拋 `ValueError` | low | 只有資料損壞才會發生，與其他公開 API 一致。reject |
| 15 | Edge | 輪空場次沒測 | false | 輪空的場次以 walkover 確認，不會是待開打 |
| 16 | Edge | 已結束賽事的裁判看到「主辦方還沒有指派場次給你。」不符實情 | false | 已結束賽事的場次仍會列出；文案是 UX 文件定案 |
| 17 | Edge | 主辦方移除裁判後仍保有場次 | false | 目前沒有移除裁判的功能 |
| 18 | Blind | spec 狀態與 sprint 註記不一致 | false | 實作中本來就是 in-progress，完成時一起改 |

## Verification

**Commands:**
- 主 repo 執行、掛 worktree 的 backend：`bash scripts/test.sh; bash scripts/lint.sh` -- 全部通過（含 `test_architecture.py`）
- 前端：`bunx biome check src tests`、相關 vitest；`routeTree.gen.ts` 要掛整個 `frontend/` 跑 `bunx vite build`
