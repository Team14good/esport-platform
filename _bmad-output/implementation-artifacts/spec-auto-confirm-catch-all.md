---
title: '申訴期滿自動確認遇到非預期例外時只略過那一場'
type: 'bugfix'
created: '2026-11-23'
status: 'done'
baseline_commit: 'e73c7b1187213c64818542144bb020248bf18e08'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `auto_confirm_expired`（5.5）只攔 `confirm_match` 的 `ValueError`（結果不自洽）。拋其他例外（例如 registration 503、非預期的 `BusinessError` 或程式錯誤）時整個工作失敗、交易回滾，下一輪又先挑到同一場，之後所有申訴期滿的場次都無法確認；寫法也和 `auto_draw_due` 不一致。deferred-work「auto_confirm_expired 只攔 ValueError」（未驗證）。

**Approach:** 查證後在資料一致時找不到會拋其他例外的路徑（409 已由狀態預先檢查擋掉），屬防禦性修正：在既有 `except ValueError` 之後加 `except Exception`，同樣回滾 savepoint、記錄日誌、本次呼叫排除該場，改處理下一場。補一個「確認時拋 `BusinessError` 不擋住其他期滿場次」的測試，並刪除該 deferred 項目。擁有者 2026-11-23 授權自動採建議。

</frozen-after-approval>

## Implementation Notes

- `auto_confirm_expired`：既有 `except ValueError` 之後加 `except Exception`，記錄 `Match %s failed to auto-confirm; skipped`、本次呼叫排除該場；docstring 同步。
- 測試 `test_unexpected_error_does_not_block_other_expired_matches` 讓 `advance` 對第一場拋 `RegistrationUnavailableError`（`BusinessError` 子類別；`advance` → `_unassign_if_member` → `registration_port.is_member` 是會走到的路徑）。第一版用 `BusinessError(..., status_code=503)`，但 `BusinessError` 只接受 4xx，建構時就拋 `ValueError`，測試其實走舊分支，執行失敗才發現。
- 鎖（`lock_tournament`、`lock_match`）維持在 try 外：鎖拋的是 SQL 錯誤時外層交易已不能用，攔下來繼續下一場也會失敗，交給 worker 回滾整個工作。
- 驗證：`test_confirm_advance.py`、worker `test_confirm_expired_appeals.py` 50 passed；ruff format 通過，`ruff check` 只有 main 既有的 3 個 E501；mypy 通過。突變檢查：換回 `e73c7b1` 的 `service.py`，新測試 1 failed；換回修正後 1 passed。
- 刪除 deferred-work 對應項目。

## Review Triage Log

- deferred 項目沒刪 — patch。
- spec 沒有紀錄 — patch（補 Implementation Notes）。
- 註解說「registration 暫時無法使用」但確認流程不呼叫 registration — false：`advance` → `_unassign_if_member` → `registration_port.is_member`。
- 測試拋的是 `BusinessError` 子類別，沒有測一般例外 — low，reject：`except Exception` 對所有例外一樣處理。
- 鎖仍在 try 外 — low，reject：理由見上。
- 永久失敗的場次每輪重試並記錄 — low，reject：與既有 `ValueError` 分支相同。
- 沒測「唯一一場拋錯時回 False」與之後重試成功 — low，reject。
- savepoint 內的 SQL 錯誤沒特別處理 — false：savepoint 回滾後外層交易可用；連線中斷時整個工作本來就會失敗。
- 兩個 except 分支重複 — low，reject：分開才能記錄不同訊息。
- 沒斷言日誌等級與 traceback — low，reject。
