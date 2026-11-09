---
title: 'Story 6.4 合併後審查的後續（併發測試、刪檔測試、403 重抓隊伍）'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-4-file-report.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** D 在 #64 合併後審查（PR #64 的審查與留言）指出三點：
1. `test_report_concurrency.py` 拿掉 `lock_tournament` 也可能通過。兩個執行緒在 Barrier 後各跑約 8 次查詢才寫入，第一個常在第二個檢查前就 commit，所以測試證明不了「重複檢舉只會成功一筆」靠的是鎖。
2. `test_reports.py` 的兩支刪檔測試（存檔後 service 失敗、commit 失敗）只斷言上傳目錄是空的，實作根本沒存檔也會通過。
3. 送出檢舉時回 403 `CAPTAIN_REQUIRED`（例如送出期間隊長被轉讓），`useFileReport.ts` 只重抓檢舉對象，S2 的「檢舉隊伍」入口不會消失。

**Approach:**
1. 併發測試：monkeypatch disputes 的 `repository.list_open_reported_team_ids`，讓第一個做完檢查的執行緒等 `threading.Event`（1 秒逾時），直到第二個執行緒也做完檢查才繼續寫入，刻意拉開「檢查」和「寫入」的時間差。有鎖時第二個執行緒被擋在鎖外，第一個逾時後寫入，結果仍只成功一筆。接著暫時把 `file_report` 的 `lock_tournament` 換成不加鎖的讀取，實際跑一次確認測試會失敗（不提交這個改動），結果記進 spec-6-4 的 Review Triage Log。
2. 刪檔測試：spy `storage.save_image`，斷言有被呼叫一次，而且它回傳的鍵值最後不在上傳目錄裡。
3. 前端：403 `CAPTAIN_REQUIRED` 時，另外讓我的隊伍（`["registration","my-teams"]`）與隊伍詳情（`["registration","team"]` 開頭）失效，S2 依最新的隊長身分決定要不要顯示入口；補一個單元測試。

</frozen-after-approval>

## Implementation Notes

- 不改產品的後端程式；暫時拿掉鎖只用來驗證測試，跑完就還原。
- 隊伍詳情用 `["registration","team"]` 前綴失效：`useFileReport` 只知道賽事 id，不知道隊伍 id。
- 改的檔案：`backend/tests/disputes/test_report_concurrency.py`、`backend/tests/disputes/test_reports.py`、`frontend/src/features/disputes/useFileReport.ts`、`frontend/tests/unit/report-team.test.tsx`；結果另記進 spec-6-4 的 Review Triage Log #24～#26。
- 拿掉鎖的驗證：在容器內把 `file_report` 的 `lock_tournament` 暫時換成 `get_tournament`。舊版測試連跑 5 次都通過（證實 D 的觀察）；新版連跑 3 次都失敗（`['ok', 'ok']`）。跑完還原，有鎖時新版通過。
- 意外：第一次寫的前端判斷用 `apiError.kind === "business"`，新測試失敗才發現 403 被 `parseApiError` 歸類為 `forbidden`；改成直接比對業務代碼。原本 `REPORT_NOT_ALLOWED`（409）的行為不變。
- 刪檔測試的 spy 包住真實的 `save_image`，仍會實際存檔，再斷言該鍵值的檔案已不在。
- 拿掉鎖的重現步驟（之後重構 `file_report` 時可照做；只在容器內改，跑完還原）：
  ```bash
  docker compose exec -T backend bash -c 'cp app/modules/disputes/service.py /tmp/service.bak \
    && python - <<EOF
  p = "app/modules/disputes/service.py"
  s = open(p).read()
  i = s.index("def file_report(")
  j = s.index("tournaments_service.lock_tournament(", i)
  s = s[:j] + "tournaments_service.get_tournament(" + s[j + len("tournaments_service.lock_tournament("):]
  open(p, "w").write(s)
  EOF
  python -m pytest tests/disputes/test_report_concurrency.py -q -p no:cacheprovider
  cp /tmp/service.bak app/modules/disputes/service.py'
  ```
  預期：`AssertionError: ['ok', 'ok']`。
- 驗證（2026-11-09）：修審查意見前的完整驗證，後端 `scripts/test.sh` 2376 個通過（覆蓋率 97%）、`lint.sh` 通過，前端 typecheck、biome 通過、單元測試 70 檔 990 個通過；修審查意見後重跑受影響範圍，`tests/disputes` 160 個通過、`report-team.test.tsx` 32 個通過、lint 與 biome、typecheck 通過。

## Review Triage Log

Blind Hunter（2026-11-09）提出 9 項：

| # | 發現 | 判定 | 處理 | 依據 |
|---|------|------|------|------|
| 1 | 併發測試沒有斷言先檢查的一方是逾時才繼續 | medium | patch | 記下 `wait` 回傳值，斷言 `first_timed_out == [True]`，直接證明對方被擋在鎖外 |
| 2 | `checks == 2` 的註解說的比斷言多 | low | patch | 配合 #1 改寫註解 |
| 3 | 拿掉鎖的驗證步驟沒留下 | low | patch | 重現步驟寫進 Implementation Notes；不寫斷言「沒鎖時失敗」的測試，避免在測試裡固定錯誤行為 |
| 4 | 固定等 1 秒、逾時值沒依據 | low | 拒絕 | 只影響手動拿掉鎖的驗證；已在註解寫明 1 秒遠大於到達檢查所需時間 |
| 5 | 6.1 申訴的刪檔測試有同樣弱點 | medium | defer | B 的既有測試，非本次造成；已記進 deferred-work |
| 6 | 說明驗證失敗的測試可斷言根本沒存檔 | low | patch | 加 spy，斷言 `saved == []` |
| 7 | spec 缺驗證與完成狀態 | false | 拒絕 | 收尾時寫入（本段與上方驗證紀錄） |
| 8 | 缺 AI 使用紀錄 | false | 拒絕 | 流程最後一步才寫 |
| 9 | `"code" in apiError` 也涵蓋 401 | low | patch | 只比對兩個完整代碼，無實際影響；註解寫明刻意不看 kind |
