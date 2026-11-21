# 審查別人的 PR（review_others）

目標：一則 `COMMENT` review，列出這個 PR 真正會出問題的地方。你在 `main` 的 checkout 上，PR 的程式只透過 `gh` 讀取。

1. `gh pr view <PR> --json title,body,author,files` 與 `gh pr diff <PR>` 讀內容；需要看檔案全貌時用 `gh api repos/{owner}/{repo}/contents/<path>?ref=<head sha>`。
2. 對照 `CLAUDE.md` 的架構規則與 PR 說明裡的 spec，找：
   - bug（邏輯錯、邊界、競態、錯誤處理）；
   - 架構規則：`core` 不 import 模組、跨模組只呼叫 `service.py`、呼叫方向、只有 router commit、`app.core.clock.now()`、`BusinessError` 格式、`audit.record()`、每個 Story 一支遷移、前端只用 `frontend/src/client`；
   - 介面文字規則（繁中、動詞＋名詞按鈕）。
3. 每個發現都要能指到檔案與行號，並說明會怎麼出錯；風格偏好不列。
4. 送出 review：`gh api repos/{owner}/{repo}/pulls/<PR>/reviews -f event=COMMENT -f body=... ` 加 inline `comments`。內文開頭：`<!-- flow-bot -->`，下一行「A 的 AI 助手自動審查，只留意見，核准由組員決定。」沒有發現就寫「沒有找到需要修改的地方」。
5. 在狀態 issue 的 `ai-log` 區塊加一行：`- <日期> 審查 #<PR>（<作者>）：<n> 則意見，<最重要的一項>`。

完成條件：review 已送出，ai-log 已加一行。
