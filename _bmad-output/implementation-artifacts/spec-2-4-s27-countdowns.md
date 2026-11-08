---
title: 'Story 2.4 補遺：S27 報名截止與優先期結束倒數'
type: 'feature'
created: '2026-11-07'
status: 'done'
baseline_commit: '453b84764d3a0eb4987f4531783000e96bb5c732'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** epics.md Story 2.4 的 AC 要求「開放報名中的賽事，主辦方檢視 S27 時顯示報名截止倒數（S27 另有優先期結束倒數）」，EXPERIENCE.md〈倒數與時間〉也列 S27。但 2.2 第二階段 spec 寫「不做 S27 的倒數」、2.4 spec 只做 S2，S27 總覽目前只有絕對時間，這條 AC 沒有實作也沒有追蹤（2026-11-07 文件比對時發現），Story 卻已標 done。

**Approach:** 只改前端 `features/tournaments/`：S27 總覽在設定清單上方加狀態倒數區，沿用 2.4 的 `Countdown` 與 `registrationEndVariant`；倒數歸零時與 S2 一樣每 5 秒重抓 S27 的賽事資料（最多 2 分鐘），直到狀態改變。

## Boundaries & Constraints

**Always:**
- 開放報名中：「報名截止」倒數，`deadline=registration_end`，變體用 `registrationEndVariant`（最後 24 小時 `appeal`，其餘 `muted`），歸零後顯示「已截止 · 系統處理中」並重抓 `myTournamentQueryOptions` 的資料（Countdown 的 `onExpire`）。
- 開放報名中且優先期尚未結束：「優先期結束」倒數，`deadline=priority_end`，變體 `muted`；歸零後直接隱藏這個倒數（不顯示「系統處理中」、不重抓），只留報名截止倒數。
- 尚未開放：「報名開始」倒數，`deadline=registration_start`，變體 `muted`，下方「{絕對時間} 開放報名」，歸零後顯示「報名開放中 · 系統處理中」並重抓（與 S2 相同，沿用 `REGISTRATION_OPENING_TEXT`）。
- 倒數字串、格式、歸零與逾時行為全部由 `Countdown` 提供，不另寫一份。
- 倒數區放在 `OrganizerTournamentSummary`（標題列與設定清單之間），不動 `OrganizerTournamentOverview` 的回傳（#56 會在那裡插入抽籤按鈕，避免衝突）。
- 其他狀態（報名截止、賽程已公布、進行中、已結束、已取消）不顯示倒數。

**Never:**
- 不改後端、API、client；不改 `Countdown` 元件本身；不改 S2；不做 S27 的待辦、抽籤、取消賽事。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 尚未開放 | upcoming | 「報名開始」倒數，下方「{時間} 開放報名」 | 歸零：「報名開放中 · 系統處理中」並重抓，狀態變為開放報名後換成開放報名的倒數 |
| 開放報名、優先期內 | open，`now < priority_end` | 「優先期結束」＋「報名截止」兩個倒數 | — |
| 優先期倒數歸零 | open，停在頁面上直到優先期結束 | 優先期倒數消失，只剩報名截止倒數；不出現「系統處理中」 | — |
| 開放報名、優先期已過 | open，`priority_end <= now` | 只有「報名截止」倒數 | — |
| 報名截止最後 24 小時 | open，剩 ≤ 24 小時 | 報名截止倒數為 `appeal` 變體 | — |
| 報名截止歸零 | open，倒數到 0 | 「已截止 · 系統處理中」，每 5 秒重抓；狀態變為報名截止後倒數區消失 | 2 分鐘仍未變：Countdown 的逾時文字 |
| 已截止或之後 | closed／published／ongoing／finished／cancelled | 不顯示倒數 | — |

## Decisions

- 2026-11-07（使用者）：尚未開放的賽事，S27 也顯示「報名開始」倒數（照 EXPERIENCE.md〈倒數與時間〉第 544 行，與 S2 相同）。
- 2026-11-07（使用者）：優先期結束倒數歸零後直接隱藏，不顯示「系統處理中」；優先期結束後賽事狀態不變，S27 讀不到分配是否完成，顯示處理中會在 2 分鐘後誤報逾時。

</frozen-after-approval>

## Code Map

- `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx` -- `OrganizerTournamentSummary` 加倒數區（只新增；`OrganizerTournamentLayout`、`OrganizerTournamentOverview` 不動）。
- `frontend/src/components/common/Countdown.tsx` -- 沿用 `Countdown`（`label`、`deadline`、`variant`、`suffix`、`expiredText`、`onExpire`）；不改。`onExpire` 在歸零當下立即呼叫一次，之後每 5 秒。
- `frontend/src/features/tournaments/TournamentOverview.tsx` -- S2 的 `StatusPanel` 是範本：`key={`open-${registration_end}`}`、`registrationEndVariant`、`REGISTRATION_OPENING_TEXT`。直接 import，不複製。
- `frontend/src/features/tournaments/organizer-queries.ts` -- `myTournamentQueryOptions(tournamentId)`；重抓用 `useQueryClient().invalidateQueries` 或該 query 的 `refetch`。
- `frontend/tests/unit/organizer-tournaments.test.tsx` -- 〈S27 賽事總覽〉describe 的寫法（mock `TournamentsService.readMyTournament`、路由渲染）；新測試加在這裡或新檔。測試用 `vi.useFakeTimers` 推時間時注意 TanStack Query 的計時。
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.4 維持 done，註解補一句本補遺。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/tournaments/OrganizerTournamentOverview.tsx` -- 在 `OrganizerTournamentSummary` 加倒數區，依狀態與 `priority_end` 顯示 -- 補 2.4 AC
- [x] `frontend/tests/unit/organizer-tournaments.test.tsx` -- I/O 矩陣每列一個測試，含歸零後重抓 `readMyTournament` -- 驗證
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.4 註解補「S27 倒數（本補遺）」 -- 追蹤

**Acceptance Criteria:**
- Given 開放報名中、優先期內的賽事，when 主辦方開 S27，then 看到「優先期結束」與「報名截止」兩個倒數，下方各有「{絕對時間} 截止」。
- Given S27 的報名截止倒數歸零，when 伺服器回傳狀態已變為報名截止，then 倒數區消失、徽章變為「報名截止」。

## Implementation Notes

- 倒數區是 `OrganizerTournamentSummary` 內新增的私有元件 `OrganizerStatusCountdowns`；重抓沿用 S2 的寫法（`queryClient.fetchQuery({...myTournamentQueryOptions(id), retry: false})`，失敗時保留畫面）。
- `Countdown` 沒有「歸零後隱藏」的選項且不能改，所以優先期倒數用 `onExpire`（歸零當下立即呼叫）記下已結束的 `priority_end` 並隱藏；初次渲染時 `priority_end <= Date.now()` 就不顯示。歸零到隱藏之間若畫面來得及繪製，顯示的是 `PRIORITY_ENDED_TEXT`「優先期已結束」，不會出現「系統處理中」。
- 測試：S27 掛上時 `readMyTournament` 的呼叫次數不固定（版面與總覽），所以重抓次數以掛上後的次數為基準，伺服器狀態用可變的 `server.current` 模擬。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap 三位並行；無高、中嚴重度）：

| # | 來源 | 發現 | 判定與證據 | 處理 |
|---|------|------|-----------|------|
| 1 | Verification Gap＋Blind | 倒數歸零後重抓失敗（不重試、不換錯誤頁）沒有測試 | low：拿掉 `retry: false` 或 `.catch` 現有測試都會過 | patch：補測試 |
| 2 | Edge | 尚未開放且優先期在未來，沒有測試確認不顯示優先期倒數 | low：程式在 upcoming 分支先 return，但沒有測試鎖住 | patch：補測試 |
| 3 | Blind | 轉為報名截止後的徽章斷言只檢查有 `data-tone` | low：沒檢查值 | patch：斷言實際值 |
| 4 | Edge | 優先期歸零到隱藏之間可能畫出一格「優先期已結束」＋spinner | low：`onExpire` 在 effect 裡呼叫，最多一格；修正需改 `Countdown`（Never） | 不處理 |
| 5 | Edge | `showPriority` 依渲染時的 `Date.now()` | false：歸零後由 `onExpire` 觸發重新渲染並隱藏，不依賴下一次渲染 | 不處理 |
| 6 | Edge | 只假 `setInterval` 時 2 分鐘的真 `setTimeout` 會活過測試 | false：RTL 每個測試後卸載元件，`useExpirePolling` 的 cleanup 會 `clearTimeout` | 不處理 |
| 7 | Blind | 輪詢中 403／404 被吞掉，2 分鐘後只看到逾時文字 | low：期中沒有刪除賽事或換主辦方的流程，平常遇不到；處理需加分支 | 不處理 |
| 8 | Blind | 首次載入時期限已過但狀態未變（worker 延遲）沒有測試 | low：這段行為在 `Countdown`，由它自己的測試涵蓋 | 不處理 |
| 9 | Blind | `priorityEndedFor !== priorityEnd` 分支沒有測試 | low：期中 2.5（修改賽事）擱置，`priority_end` 不會變 | 不處理 |
| 10 | Blind | `PRIORITY_ENDED_TEXT` 匯出但測試只斷言不存在 | low：只是一格的保底文字，不影響行為 | 不處理 |
| 11 | Blind | 優先期結束時螢幕閱讀器沒有提示 | low：使用者決定歸零後直接隱藏（Decisions）；補提示需新增 live region | 不處理 |
| 12 | Blind | S27 從 S2 的元件檔 import 倒數規則，建議搬到 `status.ts` | low：搬移要改 S2 的檔案，違反 Never「不改 S2」 | 不處理 |
| 13 | Blind | sprint-status 註解沒有 PR 編號 | false：PR 尚未建立，開 PR 時補 | 不處理 |
| 14 | Blind | diff 少了 spec 與 epic-2-context | false：spec 依流程只給 Edge Case Hunter；epic-2-context 是重新產生的 context，不是程式 | 不處理 |
| 15 | Blind | 尚未開放與開放報名兩個分支的外層標記不同 | false：兩者都是 `section`（`gap-6`）的直接子元素，間距相同 | 不處理 |

## Verification

**Commands:**
- `cd frontend && bunx biome check src tests` -- 通過
- `cd frontend && bunx tsc --noEmit` -- 0 錯誤
- `cd frontend && bunx vitest run tests/unit/organizer-tournaments.test.tsx` -- 全過（容器內執行，見 CLAUDE.md〈環境上的坑〉）

**Manual checks (if no CLI):**
- 以示範主辦方登入、開示範賽事的 S27：看到兩個倒數；375px 寬沒有橫向捲軸。
