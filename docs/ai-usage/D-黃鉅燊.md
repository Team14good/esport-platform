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

### 2026-10-29｜程式／商業規則實作｜Story 4.3 第一階段：排定與修改場次時間的規則（schedule.py）

- Story／範圍：Story 4.3（第一階段），PR #5
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理
- 怎麼用：上游資料表還沒合併，先請 AI 寫 spec，把排程規則抽成不碰資料庫的純函式；人核准 spec 後交給不帶對話脈絡的子代理實作
- AI 產出：`competition/schedule.py`（各輪開始時間與順延提示、棄權期限、修改時間的允許範圍與檢查）、`tests/competition/test_schedule.py`（83 個測試）
- 人做了什麼：核准 spec；在審查發現需求缺口時決定「修改時間的上下限都要扣掉比賽長度」
- 驗證：全套 336 個測試通過，`schedule.py` 分支覆蓋率 100%，ruff 與 mypy 通過
- 問題與修正：第一版只檢查「不早於現在、不晚於下一場」，可以把一場改到和勝隊下一場同時開始，或把準決賽排到 8 強賽之前。原 spec 漏掉了這點，AI 實作也照著漏，測試全綠，是審查代理 Blind Hunter 抓出來的。AI 沒有自己猜，而是把它列為需求缺口交給人決定，之後撤回程式、改 spec、重新實作
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 人決定需求缺口 → 重做）
- 證據：PR #5、`spec-4-3-schedule-rules.md` 的 Spec Change Log 與 Review Triage Log #1、#2

### 2026-10-29｜測試／審查與測試充分性｜兩輪多代理審查加 mutation 測試，確認 4.3 的測試抓得到錯誤

- Story／範圍：Story 4.3（第一階段），PR #5
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build` 的三個平行審查代理（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：每輪實作後由三個互不知道實作過程的代理審查；人逐項判定真偽與處理方式，寫進 spec 的 Review Triage Log
- AI 產出：第 1 輪 19 項、第 2 輪 23 項發現；第 2 輪修正 8 項（補 8 個測試、改回傳型別、拿掉會讓錯誤呼叫默默通過的預設值）
- 人做了什麼：認可每一項判定；其中型別、溢位、沒檢查場次狀態等被判為不屬實，理由寫在紀錄裡
- 驗證：故意把程式改錯再跑測試。拿掉 `delayed_by` 的下限 0 → 12 個測試失敗；調換原因代碼的判斷順序 → 1 個測試失敗。這兩個錯誤在第 2 輪修正前都不會被測試發現
- 問題與修正：子代理一開始把修改後的測試掛載到容器裡錯的目錄，跑到的是舊檔，回報 78 個測試通過。它注意到測試數沒有增加，改掛正確的目錄重跑才得到 83 個。這說明要看測試數有沒有變，不能只看「全部通過」
- 成熟度：L5（用 mutation 驗證測試本身，而不是相信「全綠」）
- 證據：PR #5、`spec-4-3-schedule-rules.md` 的 Verification 結果
