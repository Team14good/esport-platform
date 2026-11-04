---
title: '公開單場 API 後續：報到截止、報到更新 updated_at、季軍賽裁判衝突測試'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'f040972c499c36815c21a2af97e440767e0957b1'
route: 'one-shot'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/contracts/competition.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 審 A 的 #47（S4 接真資料）時發現兩件後端要補的事：公開單場沒有報到截止時間，S4 的報到倒數只能寫死 `null`；報到成功不會更新 `match.updated_at`，S4 記分者面板的 query key 只看 `updated_at`，兩隊報到後面板停在「等待雙方報到」。另外 A 審 #46 時建議補季軍賽的裁判衝突測試，並在約定寫明其他改隊伍的流程也要重新檢查衝突。

**Approach:** `PublicMatchDetail` 加 `forfeit_deadline`；報到成功時經 repository 更新場次 `updated_at`；補測試與約定，重新產生 client。

## Boundaries & Constraints

**Always:** 只有報到成功才更新 `updated_at`，任何拒絕不改資料；`forfeit_deadline` 照資料庫原值（兩隊都確定才有值）。

**Never:** 不改前端程式（A 在 #47 自己把 `forfeitDeadline: null` 換掉）；不新增遷移。

## Decisions

- 2026-11-04（使用者）：「那目前我們先把自己能做的事情一樣先做」；這兩項是 D 在 #47 審查承諾要補的後端。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/models.py` -- `PublicMatchDetail.forfeit_deadline`
- `backend/app/modules/competition/service.py` -- `get_public_match` 帶出欄位；`check_in` 成功後 `repository.touch_match`
- `backend/app/modules/competition/repository.py` -- 新增 `touch_match`
- `contracts/competition.md` -- `PublicMatchDetail` 補 `forfeit_deadline`、`appeal_started_at`；報到更新 `updated_at`；改隊伍的流程要重新檢查裁判衝突

## Tasks & Acceptance

**Execution:**
- [x] 後端三個檔案
- [x] `test_match_api.py`：欄位集合、M1 值等於資料庫、待定場次為 null
- [x] `test_check_in.py`：報到成功後公開單場的 `updated_at` 變成報到時間；被拒絕的報到不變
- [x] `test_assign_referee.py`：準決賽敗隊是季軍賽裁判所屬隊伍時自動收回
- [x] contracts、`frontend/src/client/` 重新產生

**Acceptance Criteria:**
- Given 一隊報到成功，when 讀公開單場，then `updated_at` 等於報到時間、`check_in_a_at` 有值。

## Review Triage Log

## Verification

**Commands:**
- 在主 repo 執行、掛 worktree：`python -m pytest -q tests/competition`、`bash scripts/lint.sh` -- 886 passed、lint 通過
