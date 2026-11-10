---
title: 'Story 7.2 收尾：處理 PR #77 審查的 6 點'
type: 'bugfix'
created: '2026-11-10'
status: 'done'
route: 'oneshot'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #77 審查指出 7.2 演練測試有 6 個問題：資料庫密碼可能進 Playwright 報告、S17「正取」與「賽程已公布」沒有真的檢查、報到與季軍檢查可能空過、改申訴期改到 0 列時沒有報錯。

**Approach:** 只改 `frontend/tests/e2e/`：

1. `support/db.ts` 的 `psql` 改用 `PGHOST` 等環境變數連線，密碼不再出現在 argv 與錯誤訊息。
2. worker 分配後，隊長在 S17 看到「正取」（對齊 `spec-7-2-e2e-tournament-drill-3.md` 的 I/O 表，所以補斷言而不是改 spec）。
3. 抽籤後斷言賽事狀態為 `published`。
4. 報到檢查限縮到自己隊伍那一格。
5. 季軍隊伍不存在時直接拋錯（用 `teamsOf`）。
6. `expireAppealWindows` 加 `RETURNING id`，筆數與傳入場次數不符就拋錯。

</frozen-after-approval>

## Implementation Notes

- 依使用者偏好（Story 不各自 review，最後統一做），跳過本流程的 Blind Hunter 審查。
- 第 1 點：`new URL` 解析失敗時的錯誤物件帶 `input`（整串 URL），所以 catch 後改丟不含 URL 的訊息。
- 第 2 點：新增 `expectRegistrationAccepted`，放在 `support/matchday.ts`，與 `submitRegistration` 相鄰。
- 第 4 點：`checkInOnPage` 多一個隊名參數，用含該隊名的 `li` 定位，拿掉 `.first()`，定位到多個元素時會直接失敗。
- 驗證：完整 e2e（desktop＋mobile-375）20 passed；暫時的測試（未提交）確認 `psql` 失敗時錯誤不含密碼、改到 0 列時拋錯。
