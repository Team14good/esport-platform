# 黃鉅燊 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

### 2026-10-28｜專案管理與流程／改善 AI 工作流程｜盤點 BMAD 文件，修正 epic context 每次都重新產生

- Story／範圍：PR #1
- 工具：Claude Code（Opus 5.5）
- 怎麼用：請 AI 盤點 repo 的文件與架構，確認是否符合 BMAD；先開分支提出方案，討論後再執行
- AI 產出：盤點報告；刪除 2 份備份（共 5756 行）；`_bmad/custom/bmad-build.toml` 與 `bmad-build-auto.toml`
- 人做了什麼：決定處理範圍與協作原則（標準軟體工程流程、對 AI 協作友善）
- 驗證：實際執行 BMAD 的 render，確認規則有注入 workflow；在分支上模擬判斷，結果是「context 有效、不重新產生」
- 問題與修正：AI 讀 bmad-build 的步驟時發現，它用檔案修改時間判斷 epic context 是否過期，但 git 不保存檔案時間，所以每個人 clone 或 pull 後都會被判定過期而重新產生（這可能是組長 token 燒很快的原因之一）。改成依 git commit 判斷。另外發現 `epics.backup-*.md` 會被 `*epic*` 檔名比對抓到，可能被當成需求來源讀進去
- 成熟度：L5（用 AI 找出並修正 AI 工作流程本身的缺陷，有驗證）
- 證據：PR #1（squash commit `97bfb90`）、`_bmad/custom/bmad-build.toml`

### 2026-10-28｜測試／CI｜每個 PR 自動跑全部測試，並擋下 AI 常漏的兩種錯誤

- Story／範圍：PR #1
- 工具：Claude Code（Opus 5.5）、GitHub Actions
- 怎麼用：請 AI 依 README 的測試指令寫 CI，另外檢查 Alembic 只有一個 head、API client 與後端一致
- AI 產出：`.github/workflows/ci.yml`（10 個步驟）
- 人做了什麼：把 repo 改成 public（CI 不受分鐘數限制），決定直接合併
- 驗證：PR 上實際跑 CI，接著 `main` 上再跑一次，兩次都全綠
- 問題與修正：CI 第一次執行就抓到 `main` 上的真實錯誤：Story 1.5 的 Code Review 修正改了後端 docstring，但沒有重新產生 `frontend/src/client`。這是 AI 實作時漏掉、人工審查也沒看出來的，已補一個 commit 修正
- 成熟度：L5（以外部自動驗證取代「AI 自己說測試通過」，並實際擋下 AI 的錯誤）
- 證據：PR #1、GitHub Actions run `40710158556`（失敗）與 `40712474316`（main，成功）

### 2026-10-28｜專案管理與流程／協作規則｜讓四個人的 Claude Code 照同一套流程協作

- Story／範圍：PR #1、本紀錄機制
- 工具：Claude Code（Opus 5.5）、GitHub CLI
- 怎麼用：請 AI 依標準軟體工程流程定案協作規則，並寫成每個人的 Claude 都會讀到的規則
- AI 產出：CONTRIBUTING 第 3 節（Draft PR 即認領、Squash merge、合併前改 `done`）、`CLAUDE.md` 的 Git 規則、PR 範本、CODEOWNERS、`main` 的保護規則；本資料夾的 AI 使用紀錄格式，以及 BMAD 結束時自動提示記錄的 `on_complete`
- 人做了什麼：完成 repo 轉移到 Team14good；提供分工與成員對應；提出要記錄 AI 使用情形
- 驗證：PR #1 在 approve 前被 GitHub 擋下（`BLOCKED / REVIEW_REQUIRED`），確認保護規則有生效
- 問題與修正：CODEOWNERS 中兩位組員的帳號是 AI 依帳號名稱推斷的，已請使用者確認無誤
- 成熟度：L4（AI 把協作規則同時寫成給人看的文件和給 AI 讀的規則，並由 GitHub 強制執行）
- 證據：PR #1、`CONTRIBUTING.md`、`CLAUDE.md`、`docs/ai-usage/`
