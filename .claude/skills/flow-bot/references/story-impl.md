# 實作已核准的 Story（story_impl）

目標：依已核准的 spec 完成實作，CI 檢查在本機全過，PR 轉為 ready for review。

1. 確認在 PR 的 head 分支，`gh pr edit --remove-label "flow-bot:等待核准"`。
2. 找到 spec（`_bmad-output/implementation-artifacts/spec-<E>-<S>-*.md`），frontmatter 的 `status` 設為 `ready-for-dev`。frozen 區塊從這裡起只讀。
3. 執行 `bmad-build-auto`，invocation 指向該 spec 檔，它會直接進 step-03 實作。照專案的偏好（Story 不各自 review）在 step-03 完成後結束，不跑 step-04。
4. 實作中發現 frozen 區塊需要改：走 SKILL.md 的「需要人判斷時」。
5. 跑 `ci.yml` 的全部檢查到通過。
6. 有畫面變動時：用 compose 的 `e2e` profile 跑相關的 Playwright 測試（desktop 與 mobile-375），截圖存到 repo 根目錄的 `e2e-screenshots/`（不 commit，workflow 會上傳成 artifact）。
7. spec 的 `status` 改 `done`，`sprint-status.yaml` 改 `review`。
8. AI 使用紀錄新增「程式」「測試」各一筆，並把狀態 issue `ai-log` 區塊的項目搬進來（見 SKILL.md）。
9. commit、push。更新 PR 說明（照範本，含測試結果、跨模組新增的公開函式、截圖 artifact 會出現在執行紀錄網址）。`gh pr ready`，再 `gh pr edit --add-reviewer sususu0804,happyhappy-happy,OG-Matcha`（排除 OWNER 自己）。

完成條件：PR 已 ready、檢查全過、spec 與 sprint-status 狀態已更新。
