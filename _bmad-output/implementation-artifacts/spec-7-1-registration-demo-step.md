---
title: 'Story 7.1（第三階段）：示範資料的 registration 步驟'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'one-shot'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 示範賽事「FLOW 校園盃 特戰英豪」沒有隊伍，competition 步驟抽籤時會因隊伍不足略過，啟動後看不到 Story 7.1 要求的「已抽籤的 32 隊賽事」。原本排給 registration 步驟的這段沒有人做。

**Approach:** 新增 registration 步驟，透過 identity、registration 的公開 service 建立 32 支已送出報名的隊伍（每校一隊、每隊 5 人），由既有的 competition 步驟在同一次啟動抽籤。

</frozen-after-approval>

## Implementation Notes

- 步驟放在 `STEPS` 的 `tournaments.seed` 與 `competition.seed` 之間。
- 第一隊是 `國立中央大學電競隊`，隊長與第 2 位隊員是示範帳號 `captain@`、`player@`；其餘隊員的 Email 為 `team01-m3@<網域>`，密碼同 `DEMO_PASSWORD`。
- 每隊各自一個 savepoint，被業務規則拒絕時只略過那一隊與它的帳號。
- 隊長已有這場賽事的隊伍就略過整隊，再次啟動不重算雜湊。
- `identity.service.ensure_demo_account` 的密碼雜湊加上 `cache`：同一密碼的示範帳號共用一個雜湊，否則第一次啟動約多 16 秒（一次載入 19.1 秒降到 5.5 秒，為測試時的量測值）。
- 測試的上傳目錄改為 session 層級的暫存資料夾（`tests/conftest.py`），示範資料每次載入會存 160 張截圖，不寫進容器的上傳 volume。
- 抽籤後正取隊伍的狀態是 `drawn`，不是 `accepted`。

## Decisions

- 2026-11-09（使用者）：「幫我把我能做的做一做」，由 A 接手原本沒有人開工的 registration 步驟；需要選擇時採最推薦的作法。

## Verification

- `tests/identity/test_demo_data.py` 新增 4 個測試：32 隊抽籤完成、示範隊長與選手同隊、載入兩次不重複、單隊被拒只略過該隊與帳號。
- 真實 commit 路徑：第一次 `initial_data` 7.1 秒、再次 1.5 秒；資料庫查得 32 筆 `drawn`、1 張對戰表、32 場（含季軍賽）。
