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

### 2026-10-29｜程式／商業規則實作｜Story 5.3 第一階段：逐局比分與系列結果規則（scoring.py，含 5.4）

- Story／範圍：Story 5.3（第一階段，含 5.4 的送出條件），PR #8
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理（與 5.1 在兩個 git worktree 平行實作）
- 怎麼用：AI 讀 Story 5.3、5.4 寫 spec，主動推演「送出前可覆寫某一局」會出什麼問題；核准後由子代理實作、三個審查代理審查
- AI 產出：`competition/scoring.py`（勝局門檻、單局輸入檢查、能否登錄／覆寫／刪除第 N 局、系列結果與能否送出）、`tests/competition/test_scoring.py`（134 個測試，含 BO1～7 隨機登錄、覆寫、刪除的性質測試與手寫案例表）
- 人做了什麼：核准 spec；決定「會造成多餘局的覆寫要拒絕，另外允許送出前刪除最後一局」
- 驗證：全套 387 個測試通過，`scoring.py` 分支覆蓋率 100%；拿掉多餘局檢查 → 11 個測試失敗，勝局門檻算錯 → 30 個失敗
- 問題與修正：PRD 只寫「以同一局號覆寫、系列結果跟著重算」（還標了 [ASSUMPTION]）。AI 推演出 BO3 已登錄 a、b、a 時把第 1 局改成 b，b 在第 2 局就贏了、第 3 局變成不該存在的局；若只禁止這種覆寫，裁判輸錯時會無法自行修正，所以提出三個選項交給人決定。審查代理又指出性質測試的預期邏輯與程式分支相同（5.5 犯過的同一個錯），已另加手寫的固定案例表
- 成熟度：L4（spec 階段推演出原文沒想到的狀態並交給人決定；多代理審查）
- 證據：PR #8、`spec-5-3-score-rules.md` 的 Review Triage Log

### 2026-10-29｜程式／前端元件｜Story 5.3：Score entry panel（含 5.4 的送出與 AlertDialog）

- Story／範圍：Story 5.3（第一階段之二，含 5.4 的送出），PR #8
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理、Vitest＋Testing Library
- 怎麼用：AI 依 UX-DR31、EXPERIENCE.md〈比分登錄（S24）〉與 mockup 寫 spec，元件只吃 props、系列結果由後端 `scoring.py` 計算後傳入，前端不重寫規則；新增共用的 shadcn AlertDialog
- AI 產出：`ScoreEntryPanel.tsx`、`components/ui/alert-dialog.tsx`、54 個元件與單元測試
- 人做了什麼：核准 spec 與 AI 補的錯誤訊息文字（例如「這樣修改後，後面的局就不需要打了。請先刪除後面的局再修改」）
- 驗證：新增測試全過，整體 216 個通過，build、biome、`bun install --frozen-lockfile` 通過；拿掉「編輯中不能送出」→ 2 個測試失敗
- 問題與修正：實作子代理自己發現「正在修改某一局時仍可送出系列結果，未存的修改會被丟掉」並回報，三個審查代理也都指出；送出後無法再改，屬於最嚴重的一項，改為編輯中停用送出並說明原因。審查也抓到中文輸入法的全形數字會被整個清空、沒有對應文字的錯誤代碼會完全沒有訊息。另有一個依審查要求新增的測試，子代理以 mutation 證明它不可能失敗（對話框第一次點擊就關閉），因此刪除而不是保留一個假的測試
- 成熟度：L4（多代理審查、mutation 驗證，刪除無效測試）
- 證據：PR #8、`spec-5-3-score-entry-panel.md` 的 Review Triage Log
