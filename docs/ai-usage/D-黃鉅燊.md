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

### 2026-10-29｜設計／介面設計｜competition 模組介面約定

- Story／範圍：CONTRIBUTING 6.5 約定介面（PR #3）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：請 AI 讀 D 物件設計文件、B 文件的 MATCH 資料表與 epic 4～6 context，整理出 competition 對外提供與向上游要求的函式
- AI 產出：`contracts/competition.md`，內容包括 4 個 schema、2 個 HTTP API、12 個公開函式、6 個事件，以及要 tournaments、registration 提供的 12 個函式
- 人做了什麼：決定先約定介面、讓各模組不必等上游，請 A、B、C 審查
- 驗證：未記錄（等組員在 PR #3 確認）
- 問題與修正：AI 整理時發現設計文件沒有指定申訴相關函式（`mark_appealed` 等）由誰實作，列為待確認問題請 B 回覆；後來 4.1 實作時發現約定的 `is_bye` 不足以表示是哪一方輪空、輪次名「準決賽」與 UX 文件的「4 強」不一致，已在 PR #3 補一個 commit 修正
- 成熟度：L3（AI 依設計文件產出介面，人決定協作方式）
- 證據：PR #3、`_bmad-output/implementation-artifacts/contracts/competition.md`

### 2026-10-29｜程式／程式生成｜Story 4.1 第一階段：對戰表產生器 bracket.py

- Story／範圍：4.1 第一階段（PR #4）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（spec → 實作子代理）
- 怎麼用：上游 2.2、3.x 還沒完成，請 AI 先做不碰資料庫的純函式。bmad-build 先寫 spec，人核准後交給沒有對話脈絡的子代理實作
- AI 產出：`backend/app/modules/competition/bracket.py`（`plan`、`assign`、`round_name`、`source_label`），以及 `tests/competition/test_bracket.py`（146 個測試案例，2～64 隊逐一檢查）
- 人做了什麼：在 spec checkpoint 核准；決定 spec 超過建議長度時保留不拆
- 驗證：全部 399 個後端測試通過；`bracket.py` 分支覆蓋率 100%（48 個分支，要求 90%）；lint 通過
- 問題與修正：AI 在 spec 初稿漏掉範本規定的 3 個區段，審查時才補回；輪次名稱兩份需求文件不一致（epic context 寫「準決賽」、UX 寫「4 強」），AI 以 UX 文件為準並記在 spec
- 成熟度：L4（spec → 實作 → 多審查者 → 自動驗證，人只在 checkpoint 決策）
- 證據：`_bmad-output/implementation-artifacts/spec-4-1-bracket-generator.md`

### 2026-10-29｜測試／測試審查與突變測試｜三位 AI 審查者找出測試沒釘住的規則

- Story／範圍：4.1 第一階段
- 工具：Claude Code（Opus 5.5）＋ bmad-build 的 3 位審查者（Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：3 位沒有對話脈絡的審查子代理平行審查 diff；主代理逐項查證、判定後，把要修的交回實作子代理
- AI 產出：16 項發現。7 項修正（都是測試與 docstring）、1 項在完成步驟處理、3 項判定不屬實、2 項不修，分類紀錄寫在 spec 的 Review Triage Log
- 人做了什麼：未介入（依 bmad-build 規則，沒有需求缺口就不需要人決定）
- 驗證：主代理自己做突變測試。把輪空分散改成依序排列 → 39 個測試失敗；把季軍賽來源改錯 → 62 個測試失敗。兩者在修正前都不會被抓到
- 問題與修正：**實作子代理的測試全綠、覆蓋率 100%，但沒有真正驗證「輪空交替落在上、下半區」**：13 隊與 10 隊兩種順序結果相同，換掉演算法測試也不會失敗。Verification Gap 審查者指出這點，主代理用 14 隊補上精確測試，再用突變測試證明新測試有效。這個案例說明覆蓋率 100% 不等於規則有被驗證
- 成熟度：L5（以多個獨立 AI 審查者加上突變測試，抓出 AI 自己寫的測試的盲點）
- 證據：spec 的 Review Triage Log 與 Implementation Notes
