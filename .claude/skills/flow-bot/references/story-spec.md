# 寫 spec 並開 draft PR（story_spec）

目標：Story 的 spec 寫好、draft PR 開好，OWNER 收到請他核准的留言。這個任務不寫程式。

1. `gh pr list --state all --search "Story <X.Y>"`：已經有這個 Story 的 PR 就留言到狀態 issue 說明並結束。
2. 從 `origin/main` 開分支 `story/<E>-<S>-<英文 kebab slug>`（例：`story/1-6-notification-center`）。
3. `sprint-status.yaml` 這個 Story 改成 `in-progress`，行尾註解保留。
4. 執行 `bmad-build-auto`，invocation 寫：`Story <X.Y>：<sprint-status 的名稱>。需求依 CLAUDE.md 的需求來源順序。Halt after planning.`
   - 它會產出 `_bmad-output/implementation-artifacts/spec-<E>-<S>-<slug>.md` 並在規劃後停下。
   - 若它以 `blocked`／`intent gap` 停下：把它列出的問題原樣帶到步驟 7 的留言，仍然開 draft PR。
5. AI 使用紀錄新增一筆「需求」：spec 路徑、驗收條件數、AI 自己判斷的地方。
6. commit、push，開 draft PR：標題 `feat: Story <X.Y> <名稱>`，說明照 `.github/pull_request_template.md`（實作相關欄位寫「待核准 spec 後實作」）。加上標籤 `flow-bot:等待核准`。
7. 在 PR 留言 @OWNER：
   - spec 的路徑與一段話摘要；
   - spec 裡由 AI 自己判斷、沒有需求來源依據的地方（逐條）；
   - 需要 OWNER 回答的問題（若有）；
   - 核准方式：看過 spec 後留言 `/flow-bot approve`；要改就留言 `/flow-bot <要改什麼>`。

完成條件：draft PR 存在、帶 `flow-bot:等待核准`、留言已送出。
