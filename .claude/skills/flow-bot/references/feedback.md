# 處理審查意見（feedback、instruct）

目標：PR 上每一則待處理的意見都有結果：已修正並回覆，或已回覆理由並交給 OWNER。

1. `git log -1` 確認你在 PR 的 head 分支。讀 PR 說明、它的 spec（`_bmad-output/implementation-artifacts/spec-*.md`，由分支名稱的 Story 編號找）。
2. 收集待處理的意見：
   - 所有未解決的 review thread（`gh api graphql` 查 `reviewThreads`，`isResolved: false`）。
   - 最近一則含 `<!-- flow-bot -->` 的留言之後，組員的 PR 留言與 review 內文。
   - `instruct` 任務：prompt 的「指示」就是 OWNER 的要求，優先照做；先 `gh pr edit --remove-label "flow-bot:等待回覆"`。
3. 依 `superpowers:receiving-code-review` 逐條判斷：先在程式碼裡驗證意見是否成立，再決定修或不修。
4. 成立的：修正 → 跑受影響的測試到全過 → commit。
5. 不成立或看不懂的：走 SKILL.md 的「需要人判斷時」，回覆裡附上你的證據。
6. push 後逐條回覆 thread（`gh api repos/{owner}/{repo}/pulls/comments/{id}/replies`），寫改了什麼、在哪個 commit。一般留言就在 PR 留一則總結。
7. 有新的決定（OWNER 的指示、審查者的要求改變了做法）就寫進 spec 的 `Decisions`（frozen 區塊外）。
8. AI 使用紀錄新增一筆「測試／程式審查」：審查者抓到 AI 的什麼錯、怎麼修。

完成條件：步驟 2 收集到的每一則意見，都在 PR 上看得到對應的回覆。
