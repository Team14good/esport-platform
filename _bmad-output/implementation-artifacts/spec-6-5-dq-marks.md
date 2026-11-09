---
title: 'Story 6.5（第二階段 C）：對戰樹的取消資格標記與處理理由'
type: 'feature'
created: '2026-11-09'
status: 'in-progress'
baseline_commit: 'a015464817b5017e1dd5d170a9d8a34aee17bdec'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-5-resolve-report.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 取消資格後，對戰樹只在「以取消資格判負」的那一場顯示標記；被頂替的隊伍在對戰樹、S4 都看不出被取消資格，隊伍成員在 S12、S17 只看到「取消資格」徽章、看不到處理理由（6.5 AC、FR-33、FR-35、UX-DR26、UX-DR35）。

**Approach:** 公開對戰表與公開單場的隊伍參照帶出「是否已取消資格」，S3 對戰樹與 S4 依此顯示 `destructive` 的「取消資格」標記；disputes 新增查詢隊伍取消資格理由的 API（只限該隊成員），S12、S17 在取消資格時顯示理由。

## Boundaries & Constraints

**Always:**
- 「已取消資格」只以 registration 的報名狀態 `disqualified` 判斷；competition 經 `registration_port` 一次查該賽事所有已取消資格的隊伍（避免逐隊查詢）。
- 公開 schema 只新增欄位（例如 `PublicTeamRef.disqualified: bool`），不含理由（AD-19）；舊欄位與既有標記（以 `disqualified` 判負的那一場）照舊。
- 理由取自該隊被判屬實的檢舉的 `reason`；API 只有該隊成員能讀（`CurrentAccount`＋registration `is_member`，否則 403），沒有取消資格時回 null。
- 標記沿用 4.6 的 `BracketMarkTag`（UX-DR26：與淘汰樣式並存，`destructive`）；頂替的隊伍照舊出現在原位置。
- 動到 D（competition schema、port）、A（S3、S4 元件）、C（S12、S17）的檔案只新增欄位、元件或掛載點，不改既有行為；PR 說明列出並請三人審查。

**Never:**
- 不改取消資格的頂替規則與檢舉處理流程；不做通知（只發事件）、候補遞補。
- 不在公開 API 或觀眾畫面露出理由。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 已贏過後被頂替 | 隊伍 X 贏第 1 輪後被取消資格，Y 頂替進第 2 輪 | 公開對戰表中 X 的隊伍參照 `disqualified=true`；S3 只在 X 出現的最後一張卡（第 1 輪）顯示「取消資格」；第 2 輪顯示 Y | — |
| 以取消資格判負 | 進行中被取消資格 | 該場照舊顯示標記，且 X 的參照 `disqualified=true` | — |
| 抽籤前取消資格 | 沒有對戰表 | 公開對戰表 404 照舊；S12、S17 顯示徽章與理由 | — |
| 成員看理由 | X 的隊員 | 理由文字與處理時間 | — |
| 非成員看理由 | 他隊隊長、觀眾 | — | 403（未登入 401） |
| 沒有取消資格 | 正常隊伍的成員 | null，S12、S17 不顯示理由區塊 | — |

## Decisions

- 2026-11-09（使用者）：6.5 第二階段 C 不再拆小，後端欄位、S3／S4 標記、S12／S17 理由在同一個 PR；因每週額度剩約 6%，每個步驟後查用量，超過 98% 先提交到本機再停。
- 2026-11-09（使用者）：對戰樹的「取消資格」標記只標在該隊出現的最後一張場次卡（依輪次，季軍賽排在決賽之後），其他卡照舊；S4 只在該隊出現的最後一場顯示。
- 2026-11-10（使用者）：每週額度超過 98% 時，先把目前進度提交、推上 GitHub 並開草稿 PR，交給其他組員接手。實作完成時額度已達 97%，因此不跑 bmad-build 的三位審查者，直接交接；審查、修正與介面文字確認（「主辦方的處理理由」「處理時間：…」）由接手的人完成。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/models.py` -- `PublicTeamRef`（id、name）用於 `PublicMatch.team_a/b` 與公開單場；新增欄位。
- `backend/app/modules/competition/service.py` -- `_public_matches` 附近兩處建 `PublicTeamRef`（以 `names.get(team_id, …)`），改為同時帶 `disqualified`；公開單場同理。
- `backend/app/modules/competition/registration_port.py` -- `get_team_names`、`get_registration_state` 的寫法；新增「某賽事已取消資格的隊伍 id」包裝（registration 若沒有對應函式，在 registration `service.py` 只新增）。
- `backend/app/modules/disputes/{service,router,models}.py` -- 新增隊伍取消資格理由查詢；屬實的檢舉以 6.5 A 的 `ReportStatus` 判斷；成員檢查用 registration `is_member`。
- 前端：`features/competition/{BracketMarkTag,BracketMatchCard,MatchHeader}.tsx`、`match-status.ts:133`（既有判負標記）；`features/registration/{TeamPage,RegistrationStatusCard,registration-status}.tsx`（S17、S12）；新元件放 `features/disputes/`。
- 測試：`backend/tests/competition/`（公開對戰表）、`backend/tests/disputes/`；前端 `tests/unit/` 既有 bracket、team page 測試寫法。

## Tasks & Acceptance

**Execution:**
- [x] `registration/service.py`（必要時）、`competition/{registration_port,models,service}.py` -- 公開隊伍參照帶 `disqualified`
- [x] `disputes/{models,service,router}.py` -- 理由查詢 API
- [x] 後端測試 -- 覆蓋 I/O 矩陣
- [x] `frontend/src/client/` -- 重新產生
- [x] S3、S4 標記；S12、S17 理由區塊；前端單元測試
- [x] `contracts/competition.md`、`contracts/disputes.md`、`deferred-work.md`（刪「6.5 第二階段（C）」）、`sprint-status.yaml`（6-5 改 `done`）

**Acceptance Criteria:**
- Given 隊伍 X 贏過第 1 輪後被取消資格，when 觀眾開 S3，then X 帶「取消資格」標記、Y 出現在第 2 輪原位置，第 1 輪結果不變。
- Given X 的隊員開 S17，when 頁面載入，then 看到「取消資格」徽章與主辦方的處理理由。

## Implementation Notes

- 2026-11-10（實作）：registration 已有公開函式 `list_teams_by_status`（6.4），所以不改 registration；`registration_port.list_disqualified_team_ids` 以 `statuses=[disqualified]` 呼叫它、只取 id，`_public_matches` 每次查一次（沒有隊伍時不查）。
- `PublicTeamRef.disqualified` 預設 `False`（產生的 client 為選填 `disqualified?: boolean`）。公開對戰表的名次（`podium`）也經同一個 `team_ref`，會帶出實際值；`get_podium`、S30 的 `ManagedMatch` 不判斷，一律 `False`。既有測試中斷言 `PublicTeamRef` 鍵值的兩處（`test_bracket_api.py`、`test_confirm_advance.py` 名次）補上 `disqualified`；`FakeRegistration` 新增 `list_disqualified_team_ids`（不記入 `calls`，以免改變呼叫順序斷言）。
- 理由 API：`GET /teams/{team_id}/disqualification`（`CurrentAccount`）。非隊員與隊伍不存在都回 403 `TEAM_MEMBER_REQUIRED`（沿用 registration S17 的錯誤碼）；報名狀態不是取消資格（含賽事結束後只記錄屬實）回 null；理由取對該隊屬實、`handled_at` 最近的檢舉（一併結案的檢舉理由相同）。
- 前端：`match-status.ts` 新增 `disqualifiedLastMatches`（依 `round_no`、季軍賽在決賽之後、`slot_no` 找每隊最後一張卡）與 `withDisqualifiedMark`（已有以取消資格判負的標記時不重複）。S3 由 `BracketTree` 算好傳給 `BracketMatchCard`（新增選填 prop）。S4 只有公開單場帶回的兩隊之一已取消資格時，`useDisqualifiedMarks` 才讀公開對戰表（與 S3 同一個 query key）判斷這一場是否為該隊最後一場，經 `MatchSpectatorView` 的新 prop 傳給 `MatchScoreDisplay`；同輪其他場次的小卡不標。
- S12、S17：新元件 `features/disputes/TeamDisqualificationReason.tsx`（標題「主辦方的處理理由」、理由、「處理時間：…」）只在報名狀態為取消資格時由路由掛載：S12 加在 `renderTeamExtra`（卡片連結外），S17 在 `TeamPage` 新增選填 `renderStatusExtra`（報名狀態徽章下方），registration 的頁面不依賴 disputes。理由為 null、讀取中或失敗時不顯示。介面文字「主辦方的處理理由」「處理時間：」為實作時自訂，待人確認。

## Spec Change Log

## Review Triage Log

## Verification

本工作樹與其他工作樹的容器同時在跑，compose 指令都加 `-p espory-6-5c -f compose.yml -f "C:/Users/grace/AppData/Local/Temp/claude/e0d68722dc8fbcc4/1fabc1f3-312d-4d81-a1f5-4b734a9929d3/scratchpad/ports-6-5c.yml"`（以下簡寫 `dc`）；不要停止或重建其他專案的容器。產生 client 時 `scripts/generate-client.sh` 在 Git Bash 解 tar 會失敗，改在容器內產生後用 `tar --force-local` 解開。

**Commands:**
- `dc up -d --build --wait db backend mailpit frontend` 後 `dc exec -T backend bash scripts/test.sh` -- expected: 全部通過、覆蓋率門檻通過
- `dc exec -T backend bash scripts/lint.sh` -- expected: 通過
- `dc exec -T frontend bun run --filter frontend build`、`… typecheck`、`bunx biome check`、`bun run test:unit` -- expected: 全部通過
