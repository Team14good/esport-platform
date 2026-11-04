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
### 2026-10-29｜程式／商業規則實作｜Story 5.1 第一階段：隊長報到的時間規則（checkin.py）

- Story／範圍：Story 5.1（第一階段），PR #7
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理（與 5.3 在兩個 git worktree 平行實作）
- 怎麼用：AI 讀 Story 5.1 與 epic context 寫 spec，寫的時候主動找出原文沒講清楚的地方交給人決定；核准後由不帶對話脈絡的子代理實作，三個審查代理審查
- AI 產出：`competition/checkin.py`（報到開放時間、能否報到與原因代碼、賽事開始時間）、`tests/competition/test_checkin.py`（38 個測試）
- 人做了什麼：核准 spec；決定「棄權期限一到就不能報到，即使系統還沒判棄權」
- 驗證：全套 291 個測試通過，`checkin.py` 分支覆蓋率 100%；故意改錯期限邊界 → 2 個測試失敗，改錯提前時間 → 12 個失敗
- 問題與修正：PRD 只寫「過了棄權期限判棄權」，沒寫期限到了、worker 還沒執行的那一兩分鐘能不能報到；照原文實作，遲到幾十秒的隊伍可能因 worker 晚跑而逃過棄權。AI 在寫 spec 時就列為問題交給人決定。審查代理另外發現性質測試只檢查「允許或拒絕」、沒檢查拒絕原因，原因順序寫錯也不會被發現，已改為逐項比對
- 成熟度：L4（spec 階段主動找出需求缺口；平行子代理實作與多代理審查）
- 證據：PR #7、`spec-5-1-check-in-rules.md` 的 Review Triage Log

### 2026-10-29｜程式／前端元件｜Story 5.1：Check-in panel（後端未完成前先做只吃 props 的元件）

- Story／範圍：Story 5.1（第一階段之二），PR #7
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理（與 Score entry panel 在兩個 worktree 平行實作）、Vitest＋Testing Library
- 怎麼用：後端 API 要等上游，AI 讀 UX-DR30、EXPERIENCE.md、mockup 寫 spec，把元件做成只吃 props、動作用 callback；倒數留插槽給 Epic 2 的共用元件，不重複實作
- AI 產出：`CheckInPanel.tsx`、`match-time.ts`（台北時間格式）、29 個元件與單元測試
- 人做了什麼：核准 spec 與 AI 補的介面文字
- 驗證：新增測試全過，整體 191 個通過，build、biome 通過；拿掉連按防護 → 測試失敗
- 問題與修正：三個審查代理指出：對手未定時元件根本無法表示（props 要求兩隊都有名稱）、觀眾看不到「對手確定後才能報到」、時間字串錯誤會讓整頁當掉；Verification Gap 代理證明「連按只送出一次」的測試拿掉防護也會通過（第二次點擊時按鈕已停用）。子代理第一次補的測試仍抓不到，改成在同一個 `act()` 裡連點兩次才有效。另外發現兩個分支各自寫的 `match-time.ts` 行為相同但內容不同，合併時會衝突，已統一成同一份
- 成熟度：L4（平行子代理實作、多代理審查、mutation 驗證）
- 證據：PR #7、`spec-5-1-check-in-panel.md` 的 Review Triage Log

### 2026-10-29｜測試／測試穩定性｜確認前端舊測試的偶發失敗不是新元件造成的

- Story／範圍：Story 5.1、5.3 前端元件驗證
- 工具：Claude Code（Opus 5.5）、Docker、Vitest
- 怎麼用：新元件加入後整體單元測試出現 4～32 個失敗，全在登入、註冊等舊測試；AI 在沒有任何前端改動的分支與新分支上，以相同條件各跑兩次比較
- AI 產出：對照結果與 deferred-work 項目
- 人做了什麼：無（AI 自行判斷是否阻擋合併）
- 驗證：未改動的分支第一次 14 個失敗、第二次全過；新分支第一次 7 個失敗、第二次 191 個全過。證明是既有的冷啟動逾時，不是新程式造成
- 問題與修正：子代理第一次回報時只說「應該是負載」；若直接採信或為了讓測試通過去改舊測試，都可能掩蓋真正的問題。對照實驗後才記入 deferred-work，並寫下可能的修法
- 成熟度：L4（以對照實驗取代「看起來像是負載」的猜測）
- 證據：`deferred-work.md` 的前端測試冷啟動項目
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

### 2026-10-31｜專案管理／審查｜盤點組員 PR、審查上游約定與他人 PR、解掉合併衝突

- Story／範圍：PR #4、#6、#9、#10、#12、#13、#14
- 工具：Claude Code（Opus 5.5）、`gh` CLI、審查子代理
- 怎麼用：AI 盤點全組 PR 與分支，對照自己的 competition 程式檢查 B 的 tournaments 約定（#14）與 2.2 的狀態轉換表；另派一個子代理在容器裡審 A 的 4.6、5.8 前端
- AI 產出：#14 核准（附兩點 competition 端的處理方式）；#13 審查意見、#12 要求修改（場次卡連結的可及名稱只剩「M3」）；發現 1.7 與 2.1 的遷移會形成兩個 Alembic head，在 #9、#10 提醒；把 main 合進 #4、把 #4 合進 #6，解掉衝突
- 人做了什麼：授權 AI 處理全部後續；決定把約定的 `bye_side` 改成 `bye_a`／`bye_b`
- 驗證：#4、#6 由 CONFLICTING 變為 MERGEABLE；對戰樹與場次相關的前端測試 50 個（#13）、139 個（#12）在容器裡通過
- 問題與修正：審 A 的前端時才發現**我自己寫的約定有漏洞**：`bye_side` 只能標一方，但輪空多於 P÷4（9、10 隊等）時第二輪會有兩方都來自輪空的場次；A 的假資料剛好把這種情況丟掉，所以雙方的測試都沒抓到。審查子代理則把全套前端測試的逾時失敗歸因於環境，但沒在 base 上做對照，這點在審查意見中如實註明
- 成熟度：L4（AI 跨 PR 對照約定與實作，發現單看一個 PR 看不出的問題）
- 證據：PR #12、#13、#14 的審查，#9、#10 的留言

### 2026-10-31｜程式／後端實作｜Story 4.1 第二階段：對戰表資料表、抽籤 service 與 API

- Story／範圍：Story 4.1（第二階段），分支 `story/4-1-draw`（疊在 B 的 2.2 上）
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、實作子代理、3 個平行審查子代理
- 怎麼用：AI 寫 spec，人核准範圍與分支基底後交給不帶對話脈絡的子代理實作；C 的 registration 函式還沒寫，用轉接檔在呼叫時查找，缺少時回 503，測試用替身
- AI 產出：Bracket、Match 兩張表與遷移；`draw()`（鎖賽事、提前抽籤先呼叫截止補位、排定各輪時間、設定棄權期限、轉為已公布、操作紀錄與事件）、`transition_match`、`start_forfeit_clock`、公開對戰樹；抽籤與公開對戰樹兩支 API；前端 client 重新產生；84 個新測試
- 人做了什麼：核准 spec；決定 `bye_a`／`bye_b` 與空缺方不顯示待定字串；決定「開賽時間已過就拒絕抽籤」
- 驗證：容器內全套 784 個測試通過，ruff、mypy、ty 通過；competition 分支覆蓋率 100%；突變檢查（拿掉 `start_forfeit_clock`、允許 `confirmed→live`）各有測試失敗
- 問題與修正：實作子代理遇到 spec 沒寫的「兩方都輪空」時，自己把約定改成 `"both"`，沒有回報需求缺口；主代理改請人決定，改用兩個布林值。Edge Case Hunter 抓出「開賽時間已過仍可抽籤，第一輪會排在過去」，屬於需求缺口，交給人決定。Verification Gap 指出兩個 503 測試只是因為這個分支的 registration 剛好沒有函式才通過，C 合併後會壞掉，改用 `delattr` 固定前提
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 人決定需求缺口 → 修正）
- 證據：`spec-4-1-draw-backend.md` 的 Spec Change Log、Review Triage Log（19 項）、Implementation Notes

### 2026-10-29｜程式／商業規則實作｜Story 5.5 第一階段：晉級推進與名次規則（progression.py）

- Story／範圍：Story 5.5（第一階段，含 5.6 的季軍賽、雙方棄權與名次規則），PR #6
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、子代理
- 怎麼用：Match 資料表要等上游合併，先把「確認一場後要做哪些變更」寫成純函式 `advance()`，回傳依序套用的變更清單；人核准 spec 後交給不帶對話脈絡的子代理實作
- AI 產出：`competition/progression.py`（填位、連鎖輪空、季軍賽取消、起算棄權期限、賽事結束與名次）、`tests/competition/test_progression.py`（77 個測試，含 2～32 隊隨機打到結束的性質測試）
- 人做了什麼：核准 spec；決定「決賽被取消資格時亞軍從缺」
- 驗證：全套 476 個測試通過，`progression.py` 分支覆蓋率 99%，ruff 與 mypy 通過
- 問題與修正：spec 寫「亞軍＝決賽的另一隊」，AI 照字面實作，結果被取消資格的隊伍會拿亞軍，與 PRD FR-22「亞軍從缺」矛盾。實作子代理在回報時列為疑點、審查代理 Blind Hunter 也獨立指出；AI 對照 PRD 後交給人決定，再撤回程式重做。測試沒抓到，是因為測試的「預期名次」照抄了程式的邏輯（等於自己改自己的考卷），重做時改為逐案寫死預期值
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 人決定需求缺口 → 重做）
- 證據：PR #6、`spec-5-5-progression-rules.md` 的 Spec Change Log 與 Review Triage Log #1、#2

### 2026-10-29｜測試／性質測試與 mutation｜用隨機賽事與故意改錯程式，驗證晉級規則的測試是否可靠

- Story／範圍：Story 5.5（第一階段），PR #6
- 工具：Claude Code（Opus 5.5）、pytest、三個平行審查代理
- 怎麼用：請 AI 以 4.1 的對戰表產生器產生 2～32 隊的賽事，隨機決定每場結果（含雙方棄權、取消資格）一路推進到結束，檢查不變式；再故意把程式改錯，確認測試會失敗
- AI 產出：性質測試的不變式（每場最後已確認或已取消、只結束一次、同一位置不填兩次、被取消資格的隊伍不再出場、季軍賽只在準決賽沒有勝隊時取消、每次新湊齊兩隊的場次剛好起算一次棄權期限）
- 人做了什麼：逐項認可兩輪共 41 項發現的判定（含實作子代理的 5 個疑點；合併後記成 16＋11 筆）
- 驗證：故意改錯程式：決賽取消資格仍給亞軍 → 25 個測試失敗；只對直接確認的下一場起算棄權期限 → 31 個失敗
- 問題與修正：第 1 輪的 Verification Gap 審查代理指出，性質測試只檢查「發出起算訊號時兩隊都在」，沒檢查「該發的都有發」；若程式漏掉連鎖輪空後湊齊的場次，測試仍全綠，那場比賽就永遠不會自動判棄權。重做時改成比對「新湊齊的場次集合＝起算訊號集合」
- 成熟度：L5（用性質測試、mutation 與獨立審查代理檢驗測試本身）
- 證據：PR #6、`spec-5-5-progression-rules.md` 的 Verification 結果

### 2026-10-31｜程式／後端實作｜Story 5.5、5.6 第二階段：確認結果、晉級推進、申訴期滿自動確認與賽事結束

- Story／範圍：Story 5.5、5.6（第二階段），分支 `story/5-5-confirm`（疊在 4.1 第二階段 #19 上）
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、實作子代理、3 個平行審查子代理
- 怎麼用：AI 寫 spec、人核准；子代理把第一階段 `progression.py` 算出的變更寫進資料庫，加上 worker 工作
- AI 產出：`confirm_match`、`advance`、`confirm_walkover`、`auto_confirm_expired`、`get_podium`；`Match.confirmed_at` 遷移與索引；`MatchResultConfirmed`、`MatchOpponentsDecided` 事件；公開對戰樹加名次；2、3、8、13 隊從抽籤到賽事結束的整合測試
- 人做了什麼：核准 spec
- 驗證：容器內全套 907 個測試通過，lint 通過，competition 分支覆蓋率 99%；突變檢查（不套用起算棄權期限、拿掉期限條件）各有 6 個測試失敗
- 問題與修正：子代理把「待開打的場次能不能 `confirm_match`」當成待確認問題，其實 spec 已寫明要擋，主代理直接答覆。審查抓到兩個測試全綠卻存在的問題：(1) 申訴期滿但沒有結果的場次會永遠排在最前面，worker 每輪都卡在它，原本的測試用 monkeypatch 只回一次候選而遮住問題；(2) 呼叫端照約定先鎖場次、`advance` 才鎖賽事，和 worker 的加鎖順序相反，可能死結。兩者都改掉並補上用真查詢的測試
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 修正）
- 證據：`spec-5-5-confirm-advance.md` 的 Review Triage Log（15 項）與 Implementation Notes

### 2026-10-31｜審查回應｜回應 A 對 #5～#8 的審查並修正

- Story／範圍：PR #5（4.3）、#6（5.5）、#7（5.1）、#8（5.3）第一階段
- 工具：Claude Code（Opus 5.5）、容器內的測試與突變檢查
- 怎麼用：逐條查證 A 的審查意見，能直接修的就修並證明測試抓得到
- AI 產出：#5 補兩個測試並註明準決賽改時間要考慮季軍賽（記入 deferred-work）；#7 拿掉 list 上不被支援的 `aria-disabled`；#8 把列內錯誤改成依內容清除，避免第二階段輪詢時錯誤訊息消失
- 人做了什麼：無（授權 AI 處理）
- 驗證：A 指出改錯也不會失敗的兩處，補測試後在容器裡實際改錯，各有 1 個測試失敗；score-entry-panel 46 個、check-in-panel 20 個測試通過，build 通過
- 問題與修正：A 發現第一階段的測試有盲點：兩個最小間隔在測試裡剛好都是 85 分，把其中一個換成另一個測試仍全過。這是 AI 寫測試時用了相同數值造成的，說明測試資料要刻意讓不同參數取不同值
- 成熟度：L4（人審查加上 AI 查證與突變驗證）
- 證據：PR #5～#8 的留言與 commit

### 2026-10-31｜程式／後端實作｜Story 5.8 後端：公開單場 API

- Story／範圍：5.8（A 的 S4 場次頁需要的後端），分支 `story/5-8-api`（疊在 #20 上）
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、實作子代理、3 個平行審查子代理
- 怎麼用：依 A 在 deferred-work 的請求與 A 前端的 `PublicMatchDetail` 型別寫 spec，人核准後子代理實作
- AI 產出：`GET /tournaments/{id}/matches/{id}`、`PublicMatchDetail` 等 schema、從公開對戰樹抽出共用的 `PublicMatch` 組法、12 個 API 測試、重新產生前端 client、約定文件
- 人做了什麼：核准 spec
- 驗證：容器內全套 919 個測試通過，lint 通過；突變檢查（同輪列表納入自己、拿掉場次所屬賽事檢查、同輪不過濾輪次）分別有 4、1、4 個測試失敗
- 問題與修正：審查指出測試只用 8 隊與 2 隊，都沒有輪空；而單場 API 只拿同輪場次去組隊名與來源，最容易在有輪空的對戰表出錯。補上 3、5、6 隊的對照測試（單場與整棵對戰樹逐欄相同）。其餘 10 點審查意見逐條判定駁回或延後，理由記在 spec
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 修正）
- 證據：`spec-5-8-public-match-api.md` 的 Review Triage Log（11 項）

### 2026-11-01｜程式／後端實作｜Story 5.1 第二階段：報到 API、給 5.2 的查詢與賽事開始 worker

- Story／範圍：5.1（第二階段），分支 `story/5-1-checkin`（疊在 #21 上）
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、實作子代理、3 個平行審查子代理
- 怎麼用：AI 寫 spec，列出兩個需要人決定的問題（報到時間是否公開、棄權候選是否排除兩隊都已報到）；人選定後子代理實作
- AI 產出：CheckIn 資料表與遷移、`POST`／`GET .../check-in`、`list_check_ins`、`list_forfeit_due`、worker 工作 `start_due_tournaments`、公開單場帶出報到時間、39 個測試、client 與約定文件
- 人做了什麼：回答兩個需求問題、核准 spec；授權 AI 合併已核准的 #5～#8
- 驗證：後端全套 1132 個測試通過、lint 通過；突變檢查（棄權候選不排除兩隊都報到、不捕捉唯一鍵衝突、不依期限排序）各有 1～2 個測試失敗
- 問題與修正：審查抓到三個測試全綠卻存在的問題：(1) 狀態查詢回傳大寫 API 錯誤碼，但第一階段的報到面板吃小寫原因代碼，直接接上會全部顯示成預設文字；(2) 重複送出撞唯一鍵時回 500；(3) 場次缺棄權期限時規則函式拋錯變成 500。另外，子代理回報一次無法重現的 3 個測試失敗，查明是主代理同時在另一個 worktree 跑測試、共用同一個測試資料庫造成，之後改成不同時跑
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 修正 → 突變驗證）
- 證據：`spec-5-1-check-in-backend.md` 的 Review Triage Log（18 項）

### 2026-11-01｜程式／後端實作｜Story 5.3、5.4 第二階段：逐局比分資料表、登錄／刪除／送出 API

- Story／範圍：5.3、5.4（第二階段），分支 `story/5-3-referee`（疊在 #22 上）
- 工具：Claude Code（Opus 5.5）、BMAD `bmad-build`、實作子代理、3 個平行審查子代理
- 怎麼用：AI 讀第一階段規則與現有程式後寫 spec，列出兩個需要人決定的問題（刪光所有局後場次狀態、回合數上限）；人選定後子代理實作
- AI 產出：`match_game` 資料表與遷移、`GET .../score-entry`、`PUT`／`DELETE .../games/{game_no}`、`POST .../submit`、公開單場帶出各局、75 個測試、client 與約定文件
- 人做了什麼：決定刪光後維持進行中、回合數上限 0–99；核准 spec
- 驗證：後端全套 1210 個測試通過、lint 通過；前端 239 個單元測試、biome、build 通過；5 種突變（拿掉報到檢查、不加鎖、送出不轉申訴期、BO 寫死 3、第一局不轉進行中）各有 2～8 個測試失敗
- 問題與修正：(1) 審查發現測試全部用 BO3，BO 讀錯也不會失敗，補上 BO1、BO5 測試後，`_bo` 寫死 3 的突變才被抓到；(2) 賽事不接受比分時，記分者讀面板的路徑沒有測試；(3) 一個測試名稱自稱測了併發，其實只是先後兩次請求，已改名。另外主代理自己做突變測試時，第一次的 sed 改到 5.1 報到裡同名的程式碼、另一條縮排不對，兩個突變都沒有生效卻顯示「全過」；逐行比對差異後才發現，修正後兩個突變都被測試抓到
- 成熟度：L4（spec → 子代理實作 → 多代理審查 → 修正 → 突變驗證）
- 證據：`spec-5-3-referee-score-backend.md` 的 Review Triage Log（17 項）
### 2026-11-03｜程式／測試｜依 A 對 #20（5.5、5.6）的 Request changes 修正自動確認

- Story／範圍：5.5 第二階段的 `auto_confirm_expired`、5.5 spec
- 工具：Claude Code（Opus 5.5）
- 怎麼用：A 指出一場結果不自洽的場次會讓所有賽事的自動確認永遠停住。AI 讀 `progression` 確認它拋的是 `ValueError`、`confirm_match` 本身不擋，改成每個候選在 savepoint 內確認，出錯就退回、記錄並排除，再找下一場；補 A 要求的兩個測試，並依 A 的清單更新 spec 與 PR 說明
- AI 產出：`auto_confirm_expired` 與 `find_expired_appeal_id(exclude_matches=)`；壞資料不擋其他賽事的測試、`confirm_match`／`confirm_walkover` 先鎖賽事的測試；spec 的 Code Map、已被取代的決定、驗證數字說明、第 2 輪 triage
- 人做了什麼：A 審查並提出修正項目；使用者要求確認最新狀況後處理
- 驗證：全部後端 1337 個測試通過、lint 通過、單一 Alembic head；`service.py` 分支覆蓋率 99%。突變：拿掉 `ValueError` 處理，壞資料測試失敗；拿掉兩個函式開頭的鎖，兩個鎖測試都失敗
- 問題與修正：第 1 輪 AI 審查時把這個問題判成「那一輪停在它、駁回」，低估了 worker rollback 後下一輪會重選同一場，是 A 的人工審查抓到的。A 建議用第二個 session 的 `FOR UPDATE NOWAIT` 驗證鎖，但測試的所有 session 共用同一條連線與外層交易，另一條連線看不到未 commit 的資料，AI 改成記錄呼叫順序。第一版鎖測試只檢查「有呼叫過 `lock_tournament`」，突變時仍然通過，因為後面的 `advance` 也會鎖；改成斷言第一個動作就是鎖賽事後才抓到
- 成熟度：L3（人審查找出問題，AI 修正並驗證）
- 證據：#20 的審查與 CI 紀錄

### 2026-11-03｜除錯｜#33 合併後 D 的 7 支 PR 前端建置失敗

- Story／範圍：D 的 #20～#27、#34 與 main（含 A 的 #33）同步後的前端建置
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 CI 失敗 log，找出唯一的型別錯誤，在本機前端容器跑 `typecheck` 與 `tsconfig.build.json` 確認修好，並檢查 3 支分支上沒有其他直接建立 `PublicBracket` 的地方
- AI 產出：`bracket-fixtures.ts` 補 `podium: null`，傳到 7 支分支
- 人做了什麼：無（使用者要求確認狀況時發現）
- 驗證：本機 typecheck 只剩映像過舊造成的「找不到 `@radix-ui/react-alert-dialog`」（套件已在 package.json，CI 會重建映像），`podium` 錯誤消失；以 CI 為最終依據
- 問題與修正：這正是 AI 審 #33 時說「合併後不會編譯失敗」的那種衝突。D 的 5.5 在 `PublicBracket` 加了必填的 `podium`，#33 讓假資料改用 client 型別，缺了這個欄位。當時 AI 用 Python 正則比對 main 與 D 鏈尾的型別定義，兩邊都沒比對到（回傳 None），`None == None` 被印成「same」，於是在 #33 的審查與 AI 紀錄裡寫了錯誤的結論。教訓：比對腳本找不到目標時要報錯，不能預設成相同；之後改用實際建置驗證整合，而不是比對文字
- 成熟度：L2（AI 除錯修正；先前的錯誤判斷由 CI 抓到）
- 證據：#20～#27、#34 的 CI 紀錄

### 2026-11-03｜整合｜#24（3.2）先合併後 #20 的遷移分岔

- Story／範圍：D 的 #20（5.5）與 main 同步
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 發現 #20 已核准但落後 main，main 新合的 3.2 遷移 `a3f6b9d2c8e1` 與 5.5 的 `a3d5e7f9b1c4` 都接在 3.1 的 `c5d2e8a4f913` 後面，會變成兩個 head；合 main 後把 5.5 改接 3.2，並更新 spec 的 Code Map
- AI 產出：`a3d5e7f9b1c4` 的 `down_revision` 改成 `a3f6b9d2c8e1`
- 人做了什麼：無（使用者要求確認狀況時發現）
- 驗證：容器內 `alembic heads` 只有一個 head，後端全套測試與 lint 通過，再以 CI 為準
- 問題與修正：原本約定 #20 先合、#24 再改接，結果 #24 先合，改由 #20 這邊改接，結果相同
- 成熟度：L2（AI 整合，CI 驗證）
- 證據：#20 的 commit 與 CI 紀錄

### 2026-11-03｜實作｜Story 7.1 第二階段：示範資料的 competition 步驟

- Story／範圍：7.1（A 的 Story）裡 D 負責的 competition 示範資料，依 7.1 腳本骨架的擴充方式新增步驟檔
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 7.1 spec、`demo_data` 擴充說明與 4.1 的 `draw`，新增 `demo_data/competition.py`：替 `context.tournament_to_draw` 指定的賽事抽籤（固定亂數種子），沒有指定、已抽過、或抽籤被業務規則拒絕時記錄並略過；抽籤放在 savepoint 裡，失敗不會讓整段示範資料回滾
- AI 產出：`demo_data/competition.py`、`DemoContext.tournament_to_draw` 欄位、`STEPS` 加入 competition、7 個測試、deferred-work 一項
- 人做了什麼：使用者決定先做這項
- 驗證：後端全套 1456 passed、lint 通過；突變測試 3 項（拿掉「已抽過」檢查、拿掉固定種子、改成不攔截業務錯誤）都會讓測試失敗，已還原
- 問題與修正：第一次在容器裡跑測試時，指令經過管線過濾輸出而卡住 10 分鐘，改成把輸出寫進檔案、加上 timeout 後正常。本機用 `ruff check tests` 會把 `app.*` 當第三方套件，提出錯誤的 import 排序建議；CI 只 lint `app/`，所以不採用
- 成熟度：L2（AI 實作，測試與突變驗證）
- 證據：本 PR 的 CI 紀錄

### 2026-11-04｜修正｜依 A 對 #36 的審查讓抽籤不受報名回傳順序影響

- Story／範圍：#36（7.1 competition 步驟）與 4.1 的 `draw`
- 工具：Claude Code（Opus 5.5）
- 怎麼用：A 指出固定種子只保證「同樣的輸入順序得到同樣結果」，C 的 `list_accepted_teams` 若依 UUID 或無 ORDER BY 回傳，示範對戰表每次會不同，而測試用固定順序的替身測不出來。AI 採用 A 的第二個做法：`draw` 洗牌前依隊名（相同再比 id）排序，並補「registration 回傳順序相反時同種子得到同一張表」的測試
- AI 產出：`service.draw` 多呼叫一次 `get_team_names` 並排序；`rng` 說明改為測試與示範資料都會用；兩個測試的呼叫順序與 13 隊完整賽事的季軍預期值隨之更新
- 人做了什麼：A 審查時提出問題
- 驗證：後端全套 1457 passed、lint 通過；拿掉排序時新測試失敗，已還原
- 問題與修正：13 隊完整賽事測試的季軍從隊伍4 變隊伍2，因為替身隊名「隊伍10」排在「隊伍2」前面，洗牌輸入順序改變；這是固定種子的預期值，不是規則改變
- 成熟度：L3（人審查找出問題，AI 修正並驗證）
- 證據：#36 的審查與 CI 紀錄
### 2026-11-04｜文件｜依 A 對 #21 的建議補充 id 格式錯誤的回應

- Story／範圍：#21（5.8 公開單場 API）的約定 `contracts/competition.md`
- 工具：Claude Code（Opus 5.5）
- 怎麼用：A 核准時建議約定補一句：id 不是 UUID 時 FastAPI 回 422 而不是 404。AI 在單場 API 那一列補上，寫法比照 tournaments.md 的公開 API
- AI 產出：約定一句說明
- 人做了什麼：A 審查時提出
- 驗證：只改文件；A 的另一項建議（取同一輪場次會先抓整張對戰表）A 說留著就好，未修改
- 成熟度：L1（AI 依審查意見改文件）
- 證據：#21 的審查紀錄

### 2026-11-04｜審查｜代審 B 的 #40（2.7 第一階段：邀請裁判的後端）

- Story／範圍：B 的 2.7 第一階段（B 請 D 代審）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 service、repository、router、models、遷移、約定與 spec Decisions，檢查上鎖順序（產生與接受都先鎖賽事）、冪等新增（ON CONFLICT DO NOTHING RETURNING）、作廢後取最新邀請的排序、檢查順序是否符合 Decisions、公開預覽是否符合 AD-19，並對照 competition 4.4 需要的 `is_referee`、`list_referees` 簽名；以 `git merge-tree` 確認與最新 main 無衝突
- AI 產出：核准與三項不擋合併的建議：遷移與 #35、#22 同接 `a3d5e7f9b1c4`，後合的要改接；`is_referee` 可改用主鍵查一列；token 放在 URL 路徑會進 access log
- 人做了什麼：使用者轉達 B 的請求並要求直接審
- 驗證：送出後查證審查裡「與隊伍邀請做法一致」的說法：registration 也是 `/team-invites/{token}`，屬實。CI 由 B 的 PR 跑過（綠）
- 成熟度：L2（AI 審查，人決定送出）
- 證據：#40 的審查紀錄

### 2026-11-04｜整合｜#21、#36 合併後同步 5.x PR 鏈，並核對程式與文件

- Story／範圍：D 的 #22、#25、#26、#27、#34（5.1、5.3／5.4、4.3、6.2 前置、5.2 收尾）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：#21、#36 squash 合併後，AI 依序把 main 合進鏈上各分支（#21 的 squash 先確認與分支樹相同再以 `-s ours` 吸收）；`contracts/competition.md` 的單場 API 一列，5.3 加的 `games` 說明與 5.8 補的 422 說明衝突，兩者都保留。#36 改了抽籤洗牌順序，推送前在鏈尾跑後端全套確認沒有測試依賴舊順序。使用者問為何不一次開放審查後，把 #25、#26、#27、#34 一起改為可審查；再核對各分支是否包含上游、`sprint-status` 與 PR 說明是否過時
- AI 產出：5 支分支的合併 commit；`sprint-status` 的 5.1 說明移除已合併的「待 C 的 is_captain」；4 支 PR 說明的「維持 Draft」改成目前的審查方式
- 人做了什麼：使用者決定一次開放全部審查，並要求核對同步
- 驗證：鏈尾（含 5.1、5.3、4.3、6.2）後端全套 1636 passed、lint 通過；每支分支只有一個 Alembic head、沒有衝突標記；CI 全綠
- 問題與修正：上一輪把審查紀錄推到 5.1 後沒有再往下同步，5.3、5.2 收尾兩支少了 1 個 commit，這次核對時發現並補上
- 成熟度：L2（AI 整合，測試與 CI 驗證）
- 證據：#22、#25、#26、#27、#34 的 commit 與 CI 紀錄

### 2026-11-04｜修正｜依 C 對 #22（5.1 第二階段）的審查修正兩個 worker 問題

- Story／範圍：5.1 第二階段（#22）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：C 核准時提出 5 項。AI 判斷其中兩項是真的錯誤並修正：棄權查詢沒核對報到的是不是這場兩隊；賽事開始 worker 會被一直出錯的候選卡住，改用 savepoint 加略過集合，做法與 #20 的自動確認相同。另外讓 503 訊息依用途顯示「報到」，並補上用 registration 真實隊長報到的整合測試。第 5 項（改成 `VerifiedAccount`）查證後不改，因為建立和加入隊伍都要求已驗證帳號
- AI 產出：`repository.find_forfeit_due`、`find_unstarted_bracket_id(exclude=)`、`service.start_due_tournament`、`registration_port` 的修改，4 個新測試，spec 的 Review Triage Log
- 人做了什麼：C 審查提出問題；使用者決定接下來所有人的 PR 由 D 這邊審
- 驗證：拿掉兩個修正時對應的新測試都失敗；後端全套 1513 passed、lint 通過
- 成熟度：L3（人審查找出問題，AI 修正並驗證）
- 證據：#22 的審查與 CI 紀錄
