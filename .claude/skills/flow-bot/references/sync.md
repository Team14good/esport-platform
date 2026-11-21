# 同步 main（sync）

目標：PR 分支包含最新的 `main`，衝突解完，CI 的全部檢查在本機通過。

1. 確認在 PR 的 head 分支，`git fetch origin && git merge origin/main`。
2. 有衝突時：
   - `frontend/src/client/`、`frontend/src/routeTree.gen.ts`：先取 `main` 的版本（`git checkout --theirs`），其他檔案解完後重新產生（`scripts/generate-client.sh`；routeTree 用前端容器跑 `bunx vite build`）。
   - `sprint-status.yaml`：兩邊的狀態變動都保留，各自的 Story 行用各自分支的值。
   - `docs/ai-usage/*.md`：兩邊新增的紀錄都保留。
   - 其他檔案：讀兩邊的意圖後合併；兩邊邏輯真的衝突、看不出該怎麼取捨時，`git merge --abort`，走 SKILL.md 的「需要人判斷時」。
3. Alembic：`docker compose exec -T backend alembic heads` 只能有一個 head；有兩個就照 CONTRIBUTING 第 4 節，把本 PR 遷移檔的 `down_revision` 改成 `main` 那支的 revision。
4. 跑 `ci.yml` 的全部檢查到通過，commit merge，push。
5. 在 PR 留言：合併了 `main` 的哪個 commit、解了哪些檔案、怎麼解。

完成條件：`git merge-base --is-ancestor origin/main HEAD` 成立，檢查全過，留言已送出。
