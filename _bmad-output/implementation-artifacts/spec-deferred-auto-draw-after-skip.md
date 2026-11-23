---
title: '略過自動抽籤後提高名額再自動抽籤'
type: 'bugfix'
created: '2026-11-23'
status: 'done'
baseline_commit: '064f3a59c1c8fb113be0d86fe46d8df61d1c09d7'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.2 報名截止時正取不足 2 隊，`auto_draw` 寫一筆 `AutoDrawSkip` 後，同一個 `registration_end` 就永遠不再自動抽籤。主辦方之後在「報名截止」用 3.7 `raise_capacity` 讓候補遞補到 2 隊以上，賽事仍停在報名截止，只能手動抽籤（4.5 Decisions 第 8 項延後）。

**Approach:** 略過紀錄只用來「不重複發事件」：`auto_draw` 鎖內查到略過紀錄時，若目前正取已 ≥2 就照常抽籤；`auto_draw_due` 的不加鎖預先排除同樣放寬。正取仍不足時維持不做事、不重複寫紀錄或發事件。

## Boundaries & Constraints

**Always:** 鎖賽事後再判斷（AD-6）；與手動抽籤、重複呼叫同時進行仍只抽一次；操作者為系統（`actor_id=None`），抽籤沿用 `_create_bracket`（照常發 `BracketDrawn`、寫 `bracket.drawn` 操作紀錄）。

**Never:** 不刪除或修改既有略過紀錄（保留判定當下的正取數，操作紀錄只增不改）；不改 3.7 `raise_capacity` 與 registration 模組；不做遷移；不改手動抽籤。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 略過後補足 | 有略過紀錄、報名截止、開賽未到、正取 ≥2 | `auto_draw` 回 `drawn`，產生對戰表、賽事轉賽程已公布；不再發 `AutoDrawSkipped` | N/A |
| 略過後仍不足 | 有略過紀錄、正取 0 或 1 | 回 `not_due`；不新增略過紀錄、操作紀錄或事件 | N/A |
| worker 一輪 | 略過後 `raise_capacity` 遞補到 2 隊 | `auto_draw_due` 回 True 並抽籤；下一輪回 False | N/A |
| worker 仍不足 | 略過後正取仍 1 隊 | `auto_draw_due` 不鎖這場、回 False | N/A |
| 已手動抽籤 | 略過後主辦方先手動抽籤 | `auto_draw` 回 `not_due`，不重複抽籤 | N/A |
| 開賽已過 | 有略過紀錄、正取 ≥2、開賽時間已過 | 回 `not_due`（沿用 `_draw_blocked`） | N/A |

## Decisions

- （擁有者 2026-11-23，照建議）略過後正取補足 2 隊，worker 下一輪就自動抽籤，與截止時正取足夠立即抽籤一致；主辦方分兩次提高名額時，第一次補足即抽籤。
- ~~（擁有者 2026-11-23，照建議）「正取不足 2 隊，無法抽籤」通知內文後加一句「提高名額讓正取達 2 隊後，系統會自動抽籤。」~~
- （擁有者 2026-11-23 審查後改決定）通知文字不變。審查時查證：報名截止時已用候補補滿（`fill_from_waitlist`），截止後的順位已計入每校上限，名額最小 2，所以略過時已沒有排得上的候補，`raise_capacity` 不會增加正取；那句話會誤導主辦方。程式保留，供 3.10 自訂模式（主辦方截止後收隊）使用。

</frozen-after-approval>

## Code Map

- `backend/app/modules/competition/service.py:462` `auto_draw` -- 鎖內查到略過紀錄時目前直接回 `not_due`；改為先取正取隊數，`≥ _MIN_DRAW_TEAMS` 就往下抽籤，不足且已有略過紀錄回 `not_due`，不足且沒有紀錄才寫紀錄、操作紀錄與事件。
- `backend/app/modules/competition/service.py:519` `auto_draw_due` -- 不加鎖預先排除：有略過紀錄且 `registration_port.list_accepted_teams` 仍 < 2 才 `continue`。
- `backend/tests/competition/test_auto_draw.py` -- 範本：`test_not_enough_teams_stays_closed_and_notifies_once`、`test_new_registration_end_is_tried_again`、`test_due_draws_closed_and_then_has_nothing_left`；新增 I/O 前兩列與後兩列的測試。
- `backend/tests/worker/test_auto_draw.py` -- 範本：`test_not_enough_teams_after_fill_stays_closed_and_notifies_once`（接真的 registration）；新增「略過後 `raise_capacity` 遞補再一輪抽籤」與「仍不足不鎖、不發事件」。
- `backend/app/modules/competition/models.py:66` `AutoDrawSkip` docstring -- 更新說明：紀錄只防重複事件，正取補足後仍會抽籤。

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/modules/competition/service.py` -- 改 `auto_draw`、`auto_draw_due` 與 docstring
- [x] `backend/app/modules/competition/models.py` -- 更新 `AutoDrawSkip` docstring
- [x] `backend/tests/competition/test_auto_draw.py` -- I/O 第 1、2、5、6 列
- [x] `backend/tests/worker/test_auto_draw.py` -- I/O 第 3、4 列（真的 registration＋`raise_capacity`）
- [x] `backend/tests/traceability.yaml`、`_bmad-output/implementation-artifacts/deferred-work.md` -- 新測試登錄；刪除本項 deferred

**Acceptance Criteria:**
- Given 報名截止時只有 1 隊正取而略過自動抽籤，when 主辦方提高名額讓候補遞補到 2 隊，then 不需手動操作，下一輪 worker 產生對戰表、賽事轉賽程已公布，主辦方沒有收到第二則「正取不足」通知。

## Implementation Notes

- worker 測試：賽事名額最小為 2，截止時 1 隊正取不會有候補；測試在略過後直接寫入一筆候補報名，再用真的 `raise_capacity` 從 2 提高到 3 讓它遞補，遞補與抽籤都走真程式。
- 審查後修正：預先排除抽成 `_skipped_and_still_short` 並放進 `auto_draw_due` 的 try 內（跨模組查詢拋錯只略過這一場）；`contracts/competition.md` 的 `auto_draw` 列改成新規則；worker「仍不足」測試用 spy 斷言不進 `auto_draw`（I/O 第 4 列「不鎖」），拿掉預先排除時該測試失敗（1 failed），放回後通過；traceability 補 3.7。
- 通知文字依擁有者改後的決定還原，未改 `rules.py`。
- 驗證：`pytest tests/competition/test_auto_draw.py tests/competition/test_auto_draw_concurrency.py tests/worker/test_auto_draw.py tests/notifications/test_rules.py tests/test_traceability.py -q` 64 passed；改過的檔案 ruff check／format 通過。後端全套以 CI 為準。

## Spec Change Log

## Review Triage Log

| # | 來源 | 發現 | 判定 | 處理 |
|---|------|------|------|------|
| 1 | Blind、Edge | 通知承諾「提高名額後會自動抽籤」不一定成立 | high：查證後目前完全走不到（截止已補滿、剩下候補超過每校上限） | intent_gap → 擁有者改決定：通知不改、程式保留 |
| 2 | Blind | worker 測試的候補是截止後人為寫入 | medium：與 1 同源，目前沒有真實路徑 | 註解照實寫明模擬 3.10 |
| 3 | Edge | 預先排除的 `list_accepted_teams` 在 try 外，拋錯會中斷後面所有賽事 | medium | patch |
| 4 | Gap | `contracts/competition.md` 仍寫「沒有略過紀錄」為前提 | low | patch |
| 5 | Blind、Edge、Gap | 「不鎖」測試沒有驗證不鎖 | low：I/O 第 4 列要求 | patch（spy＋突變檢查） |
| 6 | Blind | traceability 漏標 3.7 | low | patch |
| 7 | Blind、Edge | 每輪多查一次正取 | low：只對已略過且未開賽的賽事 | reject |
| 8 | Blind | `not_due` 兼兩種意思 | low：呼叫端只分是否為 not_due | reject |
| 9 | Blind | 缺 `raise_capacity` 與自動抽籤併發測試 | low：兩者都先 `lock_tournament`，鎖內重查 | reject |
| 10 | Blind | 延長報名後的行為無測試 | false：`test_new_registration_end_is_tried_again` 已涵蓋 | reject |
| 11 | Blind | 缺 AI 使用紀錄 | 開 PR 前補 | 流程 |

## Verification

**Commands:**
- `docker compose exec -T backend pytest tests/competition/test_auto_draw.py tests/competition/test_auto_draw_concurrency.py tests/worker/test_auto_draw.py tests/notifications/test_rules.py tests/test_traceability.py -q` -- expected: 全部通過（先 `docker compose up -d --build --wait`；跑測試前停掉 worker 容器，避免它搶處理 outbox）
- CI（後端全套）-- expected: 綠
