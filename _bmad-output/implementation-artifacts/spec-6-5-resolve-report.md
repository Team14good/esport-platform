---
title: 'Story 6.5（第二階段 A）：檢舉處理 resolve_report 與 S33 檢舉處理頁'
type: 'feature'
created: '2026-11-09'
status: 'done'
route: 'dispatch'
baseline_commit: '2b70a7be50c5563ddaa657615fc88defecac181c'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/disputes.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-5-disqualify.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 隊長能提出檢舉（6.4），competition 也有 `disqualify`（6.5 第一階段），但主辦方還不能處理檢舉：沒有 `resolve_report`、沒有 S33。

**Approach:** disputes 新增 `resolve_report` 與 `POST /organizer/reports/{report_id}/resolution`。屬實且賽事未結束時呼叫 competition `disqualify`，並在同一個交易結案受影響場次的未結案申訴。前端新增 S33 `…/$tournamentId/reports`，照 S32 的做法。

## Boundaries & Constraints

**Always:**
- 順序：清理理由 → `lock_tournament` → `ensure_tournament_owner` → 讀檢舉並確認屬於該賽事、仍為 `open` → 判斷 → 寫入（AD-6）。只有 router commit（AD-5）。
- 理由去頭尾空白後 1～1000 字，錯誤碼 `REPORT_REASON_REQUIRED`／`REPORT_REASON_TOO_LONG`（422 欄位錯誤，比照 `_clean_appeal_reason`）。
- 已結案的檢舉 409 `REPORT_ALREADY_RESOLVED`；不屬於該賽事或不存在 404 `REPORT_NOT_FOUND`。
- 結案寫 `status`、`reason`、`handled_by`、`handled_at`；寫操作紀錄 `report.resolved`（before／after 含狀態與理由）；發 `ReportResolved(report_id, substantiated)`。
- `disqualify` 拋出的錯誤原樣回給前端，檢舉維持 `open`，不改任何資料（例如 409 `DISQUALIFY_OPPONENT_PENDING`）。
- 取消資格後，`affected_match_ids` 每一場的未結案申訴用 `repository.close_appeals` 一併結案，理由與處理者同檢舉，寫 `appeal.resolved` 操作紀錄、發 `AppealResolved`。
- S33：Data table 列出檢舉人隊伍、被檢舉隊伍、說明、附件（照 S32 的 `openAttachment`）、提出時間、狀態；未結案的列有「駁回檢舉」「取消資格」，都走 `ConfirmDialog`，理由必填、確認鈕重複動作名；空狀態「目前沒有待處理的檢舉。」。賽事已結束時「取消資格」改為「記錄屬實」。

**Never:**
- 不改 `Report` 資料表（6.4 已建好處理欄位，不需要遷移）。
- 不做 S27 待處理清單的檢舉、對戰樹「取消資格」標記（第二階段 B、C，已記 deferred-work）。
- 不直接改場次或對戰表；不讀其他模組的資料表。

## I/O & Edge-Case Matrix

| 情況 | 狀態 | 結果 | 錯誤處理 |
|---|---|---|---|
| 駁回 | 檢舉 `open` | `dismissed`，對戰表與報名不變 | N/A |
| 屬實、賽事未結束 | 檢舉 `open` | 呼叫 `disqualify`，檢舉 `substantiated`；受影響場次的申訴結案 | `disqualify` 的錯誤原樣回、不改資料 |
| 屬實、賽事已結束 | 賽事 `finished` | 只記錄 `substantiated`，不呼叫 `disqualify` | N/A |
| 非主辦方 | — | 403 `TOURNAMENT_OWNER_REQUIRED` | 不改資料 |
| 已結案 | 檢舉非 `open` | 409 `REPORT_ALREADY_RESOLVED` | 不改資料 |
| 理由空白／超過 1000 字 | — | 422 | 不改資料 |
| 屬實、賽事已取消 | 賽事 `cancelled` | 比照已結束：只記錄 `substantiated`，不呼叫 `disqualify` | N/A |
| 屬實、被檢舉隊伍另有未結案檢舉 | 其他檢舉 `open` | 同交易一併結案為 `substantiated`，理由與處理者同本次，各寫 `report.resolved`、發 `ReportResolved` | N/A |
| 頂替：最近一場勝場是以取消資格勝 | 對手被取消資格後 T 也被取消資格 | 比照「敗隊已取消資格」：判對手獲勝、不往前找更早的敗隊 | N/A |

## Decisions

- 2026-11-09（使用者）：6.5 第二階段拆成三個 PR，本 spec 只做 A（`resolve_report`＋S33）；S27 待處理清單的檢舉（B）、對戰樹「取消資格」標記（C）已記 deferred-work。
- 2026-11-09（使用者）：取消資格時一併結案的申訴，`decision` 新增 `disqualified`，S4 顯示「取消資格」（改 `AppealDecision`、`test_enums.py`、`PublicAppealResult.decision` 與前端；欄位為字串，不需遷移）。
- 2026-11-09（使用者）：賽事已取消時比照已結束，只能駁回或記錄屬實；S33 的屬實按鈕寫「記錄屬實」。
- 2026-11-09（使用者）：被取消資格的隊伍另有未結案的檢舉時，同交易自動結案為 `substantiated`。
- 2026-11-09（使用者，回應 D 在 #65 的建議 2）：頂替時最近一場勝場若是 `disqualified` 勝（沒有真的打敗對手），比照「敗隊已取消資格」判對手獲勝，不往前找；只有 `walkover` 勝場會被略過往前找。

</frozen-after-approval>

## Code Map

- `backend/app/modules/disputes/models.py` -- `ReportStatus`（open／dismissed／substantiated）、`Report`（處理欄位已存在）、`ReportRead`；新增 `ReportResolveIn {substantiated: bool, reason: str}`、`ReportResolved` 事件（約定 L104：`report_id, substantiated`）。參考 `AppealResolveIn` L230、`AppealResolved` L139。
- `backend/app/modules/disputes/service.py` -- 參考 `resolve_appeals` L633 的順序與操作紀錄；`_to_read` L136、`_report_not_found` L88、`_owned_tournament` L607、`list_tournament_reports` L285（隊名用 `registration_service.get_team_names`）。檔頭 docstring L1–8 列出可呼叫的跨模組函式，要補 competition `disqualify`。
- `backend/app/modules/disputes/repository.py` -- `get_report` L99、`list_open_match_appeals` L53、`close_appeals` L73；新增檢舉的結案函式與「某隊未結案的檢舉」查詢（用 `ix_report_reported_team_id_status`）。
- `AppealDecision`（disputes/models.py L30）新增 `DISQUALIFIED = "disqualified"`；`tests/test_enums.py` L58 固定了值要一起改；`PublicAppealResult.decision`（models L244，`Literal["upheld","corrected"] | None`）加上 `"disqualified"`；前端 S4 顯示申訴結果的地方加「取消資格」。
- `backend/app/modules/competition/disqualification.py` -- `_replacement` 往前找勝場時（L151 附近 `reversed(wins)`），遇到 `outcome == disqualified` 的勝場要判對手獲勝、不再往前；只略過 `walkover`。`tests/competition/test_disqualify.py` 已有 16 隊的 `_sixteen_to_semis` 可沿用。
- `backend/app/modules/disputes/router.py` -- 已有 S33 列表 L81 與附件下載 L99；新增 resolution 路由，照 `resolve_appeals` L214–236（`Organizer`、service、`session.commit()`）。
- `backend/app/modules/competition/service.py` -- `disqualify` L2252，docstring 補「呼叫端須在同交易把 `affected_match_ids` 的未結案申訴結案」（D 建議 1）。`DisqualifyResult` 只含直接改動的場次，不含晉級連鎖確認的場次（D 建議 3：之後要通知時從事件或操作紀錄取）。
- `backend/tests/disputes/test_reports.py` -- 真的 registration（`World`、`_world`、`_team`、`_set_registration`）；`Report` 的隊伍有外鍵到 `team.id`，所以要真隊伍。取消資格的整合測試用真隊伍＋competition `draw`，不用 `fake_registration`。
- `frontend/src/routes/organizer/tournaments/$tournamentId/appeals.tsx`、`features/disputes/AppealsPage.tsx`、`ResolveAppealDialogs.tsx`、`organizer-queries.ts` -- S32 的範本；`components/common/ConfirmDialog.tsx`（`reason`、`destructive`）、`DataTable`、`EmptyState`、`StatusBadge`。
- `frontend/src/client/` -- 後端加路由後跑 `scripts/generate-client.sh` 重新產生；`routeTree.gen.ts` 掛整個 `frontend/` 跑 `bunx vite build` 重新產生。

## Tasks & Acceptance

**Execution:**
- [x] `disputes/models.py`、`repository.py`、`service.py`、`router.py` -- `resolve_report` 與路由
- [x] `competition/service.py` -- `disqualify` docstring 補呼叫端責任
- [x] `competition/disqualification.py`、`tests/competition/test_disqualify.py` -- `disqualified` 勝場判對手獲勝，補測試
- [x] `disputes/models.py`、`tests/test_enums.py`、前端 S4 -- `AppealDecision.DISQUALIFIED` 與顯示「取消資格」
- [x] `tests/disputes/test_resolve_report.py` -- 情況表每一列；屬實後申訴結案、操作紀錄、事件；`DISQUALIFY_OPPONENT_PENDING` 時不改資料；`traceability.yaml` 補一列
- [x] `frontend/src/client/`、`routes/.../reports.tsx`、`features/disputes/ReportsPage.tsx`、`ResolveReportDialogs.tsx`、`organizer-queries.ts` -- S33
- [x] `frontend/tests/unit/organizer-reports.test.tsx` -- 列表、空狀態、駁回、取消資格、錯誤顯示
- [x] `contracts/disputes.md`、`deferred-work.md`、`sprint-status.yaml` -- 補錯誤碼與 `ReportResolveIn`；刪除已過時的「6.2 `replay_match` 尚未實作」

**Acceptance Criteria:**
- Given 已抽籤、某隊贏了第 1 輪等第 2 輪，when 主辦方以屬實處理對它的檢舉，then 檢舉為 `substantiated`、報名為取消資格、第 1 輪輸給它的隊伍出現在第 2 輪。
- Given 某隊的場次在申訴中，when 對它的檢舉屬實，then 該場判對手獲勝、申訴全部結案，S27 的待處理申訴數減少。

## Implementation Notes

- 2026-11-09（實作）：API 路徑沒有賽事 id（約定的 `POST /organizer/reports/{report_id}/resolution`），router 先以 `get_report_tournament_id` 不鎖定讀出檢舉所屬賽事，再呼叫 `resolve_report`；service 內 `lock_tournament` 後以 `repository.lock_report`（`FOR UPDATE`＋`populate_existing`）重新讀檢舉，避免讀到鎖前已在 identity map 的過時狀態（呼應 spec-6-5-disqualify 審查 #5）。因此檢舉不存在時 404 先於理由的 422。
- 「被檢舉隊伍另有未結案檢舉」一併結案，只在真的取消資格時做（依 Decisions「被取消資格的隊伍」）；賽事已結束或已取消、只記錄屬實時，其他檢舉維持 `open`。情況表該列沒寫賽事狀態，此解讀待人確認。
- `appeal.resolved` 的 `before` 是呼叫 `disqualify` 前讀的場次狀態（`match_status`、`outcome`、`winner_id`），`after` 比照 6.2 另含 `report_id`。
- `report.resolved`：`before` `{status: open, reason: null}`、`after` `{status, reason}`；本筆屬實取消資格時另含 `disqualified`、`affected_match_ids`、`replacement_team_id`，一併結案的檢舉另含 `with_report_id`。
- 審查修正：`AppealDecision` 加入 `disqualified` 後，處理申訴 API 也會收到它；`resolve_appeals` 在任何鎖定與寫入前回 422 `APPEAL_DECISION_INVALID`（`loc` 為 `body.decision`）。S33 在賽事狀態未知（載入中或失敗）時停用屬實按鈕；處理檢舉後另重抓 S27 賽事、S30 場次與公開對戰樹。
- 前端：S32 的 `openAttachment` 抽成 `features/disputes/open-attachment.ts`，S32、S33 共用；主辦方賽事後台側欄新增「檢舉」（`tournaments/organizer-nav.ts`）。S33 以 `myTournamentQueryOptions`（與版面同一個 query）判斷賽事是否已結束或已取消，決定按鈕寫「取消資格」或「記錄屬實」。

## Spec Change Log

## Review Triage Log

2026-11-09 第 1 輪（Blind Hunter、Edge Case Hunter、Verification Gap；差異不含本 spec 與產生的 client、routeTree）：

| # | 來源 | 發現 | 判定 | 處理 |
|---|---|---|---|---|
| 1 | Verification Gap | `AppealDecision` 新增 `disqualified` 後，`AppealResolveIn.decision` 也收得到；`resolve_appeals` 的 else 分支把它當重新比賽：沒給 `replay_at` 時 `assert` 變 500，有給時重賽卻記成取消資格、S4 顯示「取消資格」 | medium：`service.py` 只檢查 corrected／rematch 的必填欄位，else 直接走 `replay_match` | patch：`resolve_appeals` 拒絕 `disqualified`（422），補測試 |
| 2 | Edge、Blind、Verification Gap | S33 以 `tournament.data?.status ?? ""` 判斷，賽事資料載入中或失敗時已結束的賽事顯示「取消資格」與「無法復原」說明，後端卻只記錄屬實 | low：版面通常已快取同一個 query，但載入失敗時會一直錯 | patch：賽事狀態未知時停用屬實按鈕 |
| 3 | Blind、Edge、Verification Gap | 處理檢舉後只重抓檢舉、申訴、S27；取消資格改了報名、對戰表與場次，主辦方場次管理、對戰表、賽事狀態不會更新；申訴與 S27 的重抓沒有測試 | low：手動重新整理即可，但主辦方處理後馬上去看場次會看到舊資料 | patch：`useRefetchReports` 一併失效賽事、場次管理、公開對戰表的 query，補測試斷言各 key |
| 4 | Blind | 取消資格的確認說明寫「已贏過的隊伍由最近一場輸給它的隊伍頂替」「未結案的申訴一併結案」，實際有不頂替的情況、只結案受影響場次的申訴 | low：直接改文字 | patch：改為「可能由…頂替」「受影響場次的未結案申訴」 |
| 5 | Blind | 約定與 `resolve_report` docstring 寫理由（422）最先檢查，實際 router 先讀檢舉（404） | low：直接改文件 | patch：約定與 docstring 寫明 router 先讀檢舉所屬賽事 |
| 6 | Edge、Blind | 被檢舉隊伍提出檢舉後撤回或被退回，`disqualify` 一律 409 `REGISTRATION_INVALID_TRANSITION`，主辦方只能駁回 | low：撤回、退回只在抽籤前，檢舉後才撤回的情況少見；主辦方可附理由駁回；修正要加分支並改情況表 | reject（可再向人確認是否改為只記錄屬實） |
| 7 | Edge | 賽事在頁面載入後才結束，快取的狀態過時 | low：伺服器依實際狀態處理；修正 3 會一併重抓賽事 | reject |
| 8 | Blind | 「其他未結案檢舉只在真的取消資格時結案」沒有問人 | false：Decisions 寫的是「被取消資格的隊伍」，只記錄屬實時隊伍沒有被取消資格 | reject |
| 9 | Blind | `ReportResolved` 只有 `report_id`、`substantiated` | false：與約定 L104 定義相同；期中只發事件 | reject |
| 10 | Blind | `report.resolved` 的 `before` 寫死為 open | false：鎖住後已確認為 `open`，一併結案的也只查 `open`，寫入值正確 | reject |
| 11 | Blind | 被取消資格隊伍自己提出的檢舉沒有處理 | false：規劃文件沒有這條規則，主辦方仍可個別處理 | reject |
| 12 | Blind | 缺多場申訴同時結案、決賽頂替經 `resolve_report`、已結束賽事駁回等測試 | low：取消資格直接改動的場次最多一場有申訴（其他為待開打）；頂替路徑已在 competition 測試 | reject |
| 13 | Blind | 新增的 deferred-work B 項與 spec-6-2 項重複、`source_spec: none` | low：`none` 是 step-01 規定的格式；兩項都會在 B 完成時刪除 | reject |
| 14 | Blind | 取消資格前查詢所有未結案申訴的場次 | low：未結案申訴通常只有幾筆 | reject |
| 15 | Blind | `ReportResolveIn.reason` 沒有 schema 長度限制 | low：service 驗證並回 422，與申訴處理一致 | reject |
| 16 | Blind | 審查差異不含 spec 與產生的檔案 | false：流程刻意排除 spec；產生的檔案由 CI 檢查一致 | reject |

## Verification

**Commands:**
compose 指令都加 `-p espory-6-5 -f compose.yml -f "C:/Users/grace/AppData/Local/Temp/claude/8ed1151532dbf623/1fabc1f3-312d-4d81-a1f5-4b734a9929d3/scratchpad/ports-6-5.yml"`（簡寫 `dc`）；不要停止或重建其他專案的容器。
- `dc up -d --build --wait db backend` 後 `dc exec backend bash scripts/test.sh`（不帶參數，否則覆蓋率門檻會被關掉） -- expected: 全部通過、覆蓋率門檻通過
- `dc exec backend bash scripts/lint.sh` -- expected: 通過
- `dc exec frontend bun run --filter frontend typecheck`、`dc exec frontend bun run test:unit` -- expected: 通過
