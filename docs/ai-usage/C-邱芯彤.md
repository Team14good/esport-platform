# 邱芯彤 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

### 2026-11-01｜需求與設計／spec｜Story 3.4 名額分配規則（第一階段 spec）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（規劃步驟）
- 怎麼用：開工前先用 gh 查 PR 狀況，確認 3.1、2.2 未合併、沒有人在做分配規則；AI 比照 D 的 4.1、5.x 第一階段，提議先寫不碰資料庫的純函式，依 FR-14～17 與 EXPERIENCE.md 的固定字串寫 spec
- AI 產出：spec 一份（I/O 與邊界情況表 10 列、驗收條件 2 條、任務 3 項），並提出範圍問題（只做 3.4，或一次做完 3.4～3.6 的校園賽規則）
- 人做了什麼：決定一次做完校園賽規則、保留約 2,700 tokens 的完整 spec，核准 spec
- 驗證：spec 經人審核後核准
- 問題與修正：AI 第一版 spec 的範圍選項 A 已把 `decide_first_come` 列為任務，但 I/O 表沒有先搶期送出的情境，人決定範圍後由 AI 補上兩列；Never 一節原寫「只用標準函式庫」，與 Code Map 要 import `registration.models` 矛盾，AI 自我檢查時修正
- 成熟度：L4（固定流程產出 spec，人在 checkpoint 決定範圍與核准）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-allocation-policy.md；commit 未記錄（尚未 commit）

### 2026-11-01｜程式／程式生成｜Story 3.4 名額分配規則（第一階段實作）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：由不帶對話脈絡的子代理只依 spec 實作，主流程對照 diff 驗收任務與 I/O 表，並自己重跑全部測試與分支覆蓋率
- AI 產出：registration/allocation.py（排序鍵、優先期結算、先搶期送出判定、兩階段候補順位與原因代碼、截止補位）；測試 29 個
- 人做了什麼：未記錄（待使用者確認子代理對 spec 未寫明處的 4 項解讀，見 spec 的 Implementation Notes）
- 驗證：後端 761 個測試通過；allocation.py 分支覆蓋率 100%（22 個分支）；mypy、ty、ruff 通過
- 問題與修正：無（子代理把 spec 未寫明的 4 項解讀列出交給人確認，沒有自行寫進 spec）
- 成熟度：L4（依 spec 由子代理實作，主流程對照 diff 驗收並自動測試）
- 證據：spec 同上；commit 未記錄（尚未 commit）

### 2026-11-01｜測試／程式審查｜Story 3.4 名額分配規則（第一階段審查與測試）

- Story／範圍：3.4 第一階段（分支 story/3-4，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查者平行審 diff，主流程逐項查證後分類，記在 spec 的 Review Triage Log，修正交回原實作子代理
- AI 產出：審查發現共 20 項；修正 6 組（補「略過候選者本身」的測試、介面字串改為全文比對、兩段 docstring 寫明呼叫端責任、deferred 寫明 `fill_at_deadline` 與 11/12 交接、sprint-status 註解），延後 2 項（代表隊退出的同校遞補對象、分支覆蓋率自動檢查），其餘查證後駁回
- 人做了什麼：未記錄（審查分類由 AI 完成，待使用者確認）
- 驗證：修正後後端 762 個測試通過，allocation.py 分支覆蓋率 100%，lint 通過；主流程在一次性容器中刪掉 `decide_first_come` 的自我排除條件，確認新測試會失敗
- 問題與修正：Verification Gap 審查者指出原本的測試用 `pending` 狀態的候選者，本來就不計入正取，刪掉或反轉過濾條件測試照樣通過，屬於「測試存在但驗證不到」；實作子代理推算新測試能抓到後，主流程實際做一次變異測試確認
- 成熟度：L4（多個獨立審查者加自動測試與變異檢查，主流程查證每項發現）
### 2026-10-30｜需求與設計／spec｜Story 3.2 選手填寫參賽資料（第一段 spec）

- Story／範圍：3.2 第一段（分支 story/3-2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（規劃步驟，前端與 UX 調查交給 Explore 子代理）
- 怎麼用：使用者要求 story/3-2 與 story/3-1 完全獨立；AI 調查後指出 3.2 的參賽資料存在 3.1 才建立的 team_member、入口在 3.1 的 S17，提出三種做法讓使用者選，再依選擇寫 spec
- AI 產出：spec 一份（I/O 與邊界情況表 8 列、驗收條件 4 條、任務 10 項），第二段（依賴 3.1 的部分）寫入 deferred-work
- 人做了什麼：選擇「先做與 3.1 無關的部分，3.1 合併後在同一分支 merge main 再接上」；決定保留約 2,700 tokens 的完整 spec；核准 spec
- 驗證：spec 經人審核後核准
- 問題與修正：AI 一開始直接從 story/3-1 開分支（因為 3.1 未合併），使用者要求獨立後才改從 origin/main 開；AI 調查發現 UX 文件沒有規定上傳進度的樣式、「上場時必須使用這個遊戲 ID」只出現在 epics，改寫進 spec 的設計說明而不是自行假設需求
- 成熟度：L4（固定流程產出 spec，人在 checkpoint 決定範圍與核准）
- 證據：_bmad-output/implementation-artifacts/spec-3-2-player-registration-info.md；commit 未記錄（尚未 commit）

### 2026-10-30｜程式／程式生成｜Story 3.2 選手填寫參賽資料（第一段實作）

- Story／範圍：3.2 第一段（分支 story/3-2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：由不帶對話脈絡的子代理只依 spec 實作，主流程對照 diff 驗收每個任務、驗收條件與 I/O 表每一列的測試，並自己重跑全部測試
- AI 產出：後端 core.storage（存圖片時以 MIME 與檔頭驗證、5 MB 上限、防路徑穿越）、段位驗證函式 rank_score_for、UPLOAD_DIR 設定；前端 Screenshot uploader 元件、S18 參賽資料對話框（手機 Sheet、桌機 Dialog）、檔案檢查函式；新增 2 個後端測試檔、2 個前端測試檔
- 人做了什麼：未記錄（待使用者確認實作子代理自訂的介面文字，見 spec 的 Implementation Notes）
- 驗證：後端 289 個測試通過、覆蓋率 95%（新檔 100%）；mypy、ty、ruff 通過；前端 typecheck、biome 通過，單元測試 185 個通過
- 問題與修正：主流程更新 sprint-status 時用的 python 其實是 Windows Store 的空殼，指令沒有報錯也沒有改檔，主流程從 git diff 為空發現後改用 PowerShell 寫回；子代理發現開發用資料庫的 Alembic 版本停在 story/3-1 的遷移，本分支的 backend 容器起不來，沒有自行修改資料庫，回報給使用者決定
- 成熟度：L4（依 spec 由子代理實作，主流程對照 diff 驗收並自動測試）
- 證據：spec 同上；commit 未記錄（尚未 commit）

### 2026-10-30｜測試／程式審查｜Story 3.2 選手填寫參賽資料（第一段審查與測試）

- Story／範圍：3.2 第一段（分支 story/3-2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查者平行審 diff，主流程逐項查證後分類為修正、延後或駁回，記在 spec 的 Review Triage Log，修正交回原實作子代理
- AI 產出：審查發現共 27 項；修正 6 組（S18 只在重新開啟時重設表單並補測試、伺服器 415／413 改顯示在截圖欄、上傳中不能換檔、拖檔到預覽列不再讓瀏覽器離開頁面、拖曳外框閃爍、進度 NaN），延後 3 項寫入 deferred-work（更換截圖後刪舊檔、上傳請求大小上限、原始檔名規則），其餘查證後駁回
- 人做了什麼：未記錄（審查分類由 AI 完成，待使用者確認）
- 驗證：修正後後端 289 個測試、前端 190 個單元測試全數通過，lint、typecheck、biome 通過
- 問題與修正：Verification Gap 審查者指出 S18 的 10 個測試都只渲染一次，把重設表單的 effect 整個刪掉也會全部通過；Edge Case Hunter 指出檔案拖到已選取的預覽列時沒有處理，瀏覽器會直接開啟圖片、表單內容遺失；兩者都是實作子代理自己的測試沒抓到，補上修正與測試
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每項發現）
- 證據：spec 的 Review Triage Log；_bmad-output/implementation-artifacts/deferred-work.md；commit 未記錄（尚未 commit）
### 2026-10-30｜需求／驗收條件｜Story 3.1 建立隊伍與邀請隊員（spec）

- Story／範圍：3.1（分支 story/3-1，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build
- 怎麼用：以 bmad-build 讀 epic-3 context、tournaments／competition 介面約定與期中文件 B 的資料表，派子代理調查程式碼後產生 spec
- AI 產出：spec 一份（I/O 與邊界情況表 11 列、驗收條件 6 條、任務 11 項），並整理出 3 個需要人決定的問題
- 人做了什麼：決定建隊入口只做 Dialog 元件、「我的隊伍」對所有登入帳號顯示、隊名 1～30 字且同賽事不可重複、保留超長 spec；開工前決定不合併 story/2-2、改用約定介面與測試替身、不用 factory／seed
- 驗證：spec 經人審核後核准
- 問題與修正：AI 調查時發現 tournament 資料表尚未存在（2.2 未合併）、identity 不能呼叫 registration，這兩點規劃文件沒寫，改列為決策題讓人選擇，沒有自行假設
- 成熟度：L4（固定流程產出 spec，人只在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-1-create-team-and-invite-members.md；commit 未記錄（尚未 commit）

### 2026-10-30｜程式／程式生成｜Story 3.1 建立隊伍與邀請隊員（實作）

- Story／範圍：3.1（分支 story/3-1，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：由不帶對話脈絡的子代理只依 spec 實作，主流程再對照 diff 驗收每個任務與驗收條件
- AI 產出：後端 registration 三張資料表與一支遷移檔、5 個 API、報名狀態轉換、4 個公開函式；前端 4 個元件（Invite link field、Roster list、Registration status card、建立隊伍 Dialog）與 3 個頁面（S17、S19、S12）；身分切換器加入「我的隊伍」
- 人做了什麼：審核 spec 決策；確認動到 A 的 identity 模組只新增不改既有邏輯，需在 PR 說明列出
- 驗證：後端 369 個測試通過、覆蓋率 95%；mypy、ty、ruff 通過；前端 typecheck、biome、build 通過，單元測試 184 個通過
- 問題與修正：主流程驗收時發現子代理做的 TeamRead 少了期中設計文件要求的「隊員帳號與角色」（其他模組靠它判斷隊長），由主流程補上並加測試；子代理自行發現 S12 路由若照 spec 命名會因 /me 沒有 Outlet 而不顯示，改用 me_.teams.tsx
- 成熟度：L4（依 spec 由子代理實作，主流程對照 diff 驗收並自動測試）
- 證據：spec 同上；commit 未記錄（尚未 commit）

### 2026-10-30｜測試／程式審查｜Story 3.1 建立隊伍與邀請隊員（審查與測試）

- Story／範圍：3.1（分支 story/3-1，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查者平行審 diff，主流程逐項查證後分類為修正、延後或駁回，記在 spec 的 Review Triage Log
- AI 產出：審查發現共約 35 項；修正 5 項（隊名查重改由資料庫轉小寫、補「先鎖賽事再檢查」順序與使用鎖定值的測試、補我的隊伍排序與系統操作者測試、S19 已在隊伍時加「查看我的隊伍」、加入後更新邀請預覽），延後 2 項寫入 deferred-work（2.4 的建隊入口與回賽事頁連結、2.2 合併後移除 raising=False 替身），其餘查證後駁回
- 人做了什麼：未記錄（審查分類由 AI 完成，待使用者確認）
- 驗證：修正後後端 369 個測試、前端 184 個單元測試全數通過，lint 與 build 通過
- 問題與修正：主流程誤判報名狀態圖沒有「已參賽 → 取消資格」，要求子代理移除；子代理查證期中文件 B 第 590 行後拒絕修改，主流程重新查證確認是自己只讀到第 589 行而漏看，改判為誤報並刪除錯誤的 deferred 項目。另外，Verification Gap 審查者指出測試替身只記錄「有呼叫鎖」，順序寫錯也不會被抓到，因此補了測試
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每項發現）
- 證據：spec 的 Review Triage Log；_bmad-output/implementation-artifacts/deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-02｜程式／整合｜Story 3.1 收尾：接上 2.2 的真實賽事

- Story／範圍：3.1 收尾（分支 story/3-1，PR #23）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、三個審查子代理）
- 怎麼用：2.2（#15）合併後，由 AI 將 origin/main 合併進 story/3-1、解衝突（`sprint-status.yaml`；`frontend/src/client`、`routeTree.gen.ts` 以重新產生處理）、把遷移的 down_revision 改接 2.2 的 head；再以 bmad-build 產生收尾 spec，由子代理實作，三個審查子代理審 diff
- AI 產出：三張表的 tournament_id 外鍵、移除測試替身與 type: ignore、測試改用真實賽事、新增真實 PostgreSQL 平行加入測試（5 人搶 2 個空位）、外鍵孤兒資料測試；找出前端偶發失敗的原因（路由延遲載入，首次渲染 930～1006 ms，超過 findBy 的 1000 ms）並修正
- 人做了什麼：決定測試的真實賽事改用 2.2 的共用工具 `tests/helpers.make_tournament`（原本偏好各測試檔自己 insert）；決定保留約 3,000 tokens 的完整 spec；核准 spec
- 驗證：合併後一開始有 103 個後端測試失敗、mypy 4 個錯誤；完成後後端 1131 個測試通過，mypy、ty、ruff 通過，Alembic 只有一個 head；前端 327 個單元測試、typecheck、biome 通過，`team-pages.test.tsx` 連跑 10 次無失敗
- 問題與修正：三個審查者共提出 23 項（合併重複後 15 項），修正 7 項（併發測試清理不完整、barrier 例外被吞掉、說明誤寫「每次測試重建」、孤兒資料測試沒確認是外鍵擋下、非開放狀態只測部分等），延後 1 項（A 的 admin-applications 測試偶發失敗），其餘查證後駁回。主流程給子代理的修正指示寫錯：要求「該隊加入紀錄恰好 2 筆」，但併發前已有 3 名隊員加入，實際是 5 筆；子代理執行時發現並改成只算同時加入的 5 人
- 成熟度：L4（固定流程，子代理實作、多個獨立審查者加自動測試，人只在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-1-tournament-integration.md（Review Triage Log）；deferred-work.md；merge commit 1494bc2；收尾的 commit 未記錄（尚未 commit）

### 2026-11-02｜測試／瀏覽器實測｜Story 3.1 PR 檢查清單：瀏覽器與 375 px

- Story／範圍：3.1（分支 story/3-1，PR #23）
- 工具：Claude Code（Opus 5.5）＋ Playwright（容器內的 Chromium）
- 怎麼用：AI 先修好本機開發資料庫的遷移版本，再寫腳本經 API 準備資料（遊戲、主辦方、開放報名的賽事、6 個帳號），用 Playwright 在桌機與 375 px 寬度走過 S17、S19、S12、身分切換器，逐項斷言並截圖，主流程再看截圖確認版面
- AI 產出：實測腳本與截圖；42 項檢查全部通過（含 375 px 每頁沒有水平捲動、複製連結 Toast、額滿後連結失效）
- 人做了什麼：要求在送審前完成 PR 檢查清單的瀏覽器實測與 375 px 檢查
- 驗證：42/42 通過；人工查看 6 張截圖（S17 額滿、S17 有邀請連結、S19 未登入、S12、身分切換器、S17 桌機）
- 問題與修正：AI 寫在 #23 說明的資料庫指示有誤（只寫 downgrade 再 upgrade），實際執行時 Alembic 找不到 tournament 表才發現：舊版 story/3-1 的資料庫沒跑過 2.1、1.7、2.2 的遷移，要先 stamp 回 1.5 再升級；腳本第一次執行時連結名稱寫錯（「登入」應為「登入帳號」）而中斷；準備資料時發現中文 email 的驗證信寄不出去，已記進 deferred-work 給 A
- 成熟度：L3（AI 自動化實測與截圖，人決定要做哪些檢查）
- 證據：PR #23 檢查清單；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-03｜程式／程式生成｜Story 3.1 收尾之二：S2 的「建立隊伍」入口

- Story／範圍：3.1（分支 story/3-1，PR #23）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、三個審查子代理）＋ Playwright
- 怎麼用：AI 實測時發現 B 的 2.4 spec 寫明建隊入口由 3.1 接上，但 #23 說明與 deferred-work 寫成由 B 接，提出給人決定；再以 bmad-build 產生 spec、由子代理實作、三個審查子代理審 diff，最後用 Playwright 在瀏覽器實測
- AI 產出：新元件 CreateTeamEntry（未登入不顯示、未驗證停用並說明、本賽事主辦方不顯示、已有隊伍改顯示隊伍卡片）、掛到 S2 總覽、15 個單元測試
- 人做了什麼：決定在 #23 接上入口；決定主辦方由前端判斷後不顯示、已有隊伍時改顯示隊伍卡片；核准 spec；要求把 sprint 狀態改成 done
- 驗證：前端 typecheck、biome 通過，單元測試 542 個中 540 個通過（2 個是 A、D 檔案的已知偶發逾時，另一次執行全過）；Playwright 實測 S2 共 26 項全部通過（含 375 px 與實際建隊導向 S17）
- 問題與修正：三個審查者共提出 21 項（合併重複後 14 項），修正 1 組（補主辦方賽事載入中、帳號載入中與失敗、卡片優先於主辦方判斷共 4 個測試；子代理逐一改壞程式確認測試會失敗），其餘查證後駁回；其中「後端沒有擋主辦方建隊」經查 `_ensure_can_join` 已有檢查且實測被拒，判為誤報。實測腳本少了結束程式的呼叫，跑完後掛住約 50 分鐘才由主流程發現並停止
- 成熟度：L4（固定流程，子代理實作、多個獨立審查者加自動測試與瀏覽器實測，人只在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-1-create-team-entry.md（Review Triage Log）；commit 未記錄（尚未 commit）

### 2026-11-03｜需求／設計｜Story 3.2 第二段 spec：存檔 API、S17 入口與平均段位積分

- Story／範圍：3.2 第二段（分支 story/3-2，PR #24）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（兩個調查子代理、一個 spec 審查子代理）
- 怎麼用：3.1（#23）合併後，AI 先把本機落後遠端的 story/3-2 快轉、合併 origin/main 並解 `sprint-status.yaml` 衝突；兩個子代理分別調查後端與前端，主流程寫出 spec；使用者要求審查 spec，由另一個子代理對照程式與 PRD／UX 審查
- AI 產出：spec-3-2-player-registration-info-2.md（I/O 矩陣 12 列、13 項 Tasks）；調查時發現前端拿不到段位對照表（公開賽事 API 沒有 `rank_tiers`），改由 `TeamDetail` 帶出
- 人做了什麼：決定平均段位積分只算已填者並註明人數（PRD 只寫「所有成員的平均」，未說明未填完時怎麼顯示）；決定保留約 3,500～4,000 tokens 的完整 spec；同意審查後對凍結區塊的 4 項修改；核准 spec
- 驗證：spec 審查子代理提出 15 項，主流程抽查其中兩項（`join_team` 的檢查順序、deferred 項目數）屬實
- 問題與修正：AI 初稿有三個錯誤，都由 spec 審查子代理抓到。一是檢查順序寫成「先鎖賽事再查隊伍是否存在」，但要先查到隊伍才知道鎖哪個賽事（3.1 的 `join_team` 就是先查再鎖）；二是遊戲 ID 用 FastAPI 的 Form 限制驗證，會在鎖之前就回英文 422；三是平均值型別寫成 `Decimal`，Pydantic 會序列化成字串。另外初稿寫「刪除 deferred-work 四項」，實際只有三項該刪。合併時 AI 一開始直接在落後遠端的本機分支上合併 main，看到衝突內容不對才發現，改為先快轉再合併
- 成熟度：L4（固定流程，多個子代理調查與審查，人在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-2-player-registration-info-2.md（Decisions）；commit 未記錄（尚未 commit）

### 2026-11-03｜程式／程式生成｜Story 3.2 第二段實作與審查

- Story／範圍：3.2 第二段（分支 story/3-2，PR #24）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、三個審查子代理）
- 怎麼用：實作子代理只依 spec 實作；主流程讀 diff 對照 Tasks 與 I/O 矩陣，自己重建容器跑測試；三個審查子代理（Blind Hunter、Edge Case Hunter、Verification Gap）審 diff，主流程逐項查證後分類，修正交回同一個實作子代理
- AI 產出：`team_member` 五個欄位與遷移、`PUT /teams/{team_id}/members/me/profile`（multipart）、`core.storage.delete_file`、遊戲 ID／檔名清理與平均值純函式、S17 名單的完成度與「填寫我的資料」、上傳進度；22 個檔案、新增 2107 行、刪除 65 行；新增 32 個 API 測試（I/O 矩陣 12 列都有對應測試）
- 人做了什麼：核准 spec 後交由流程執行
- 驗證：後端 1400 個測試通過、覆蓋率 97%，mypy、ty、ruff 通過；前端 typecheck、biome 通過，49 個檔、587 個單元測試通過。瀏覽器實測（375 px、兩個帳號、確認舊截圖檔被刪除）未做
- 問題與修正：三個審查者共提出 18 項（Verification Gap 0 項），修正 5 組：遊戲 ID 只去頭尾空白，含 NUL 時 PostgreSQL 會拒絕而回 500、含 U+202E 會讓隊友看到的名單文字反轉；前後端計算「50 字」的方式不同（UTF-16 與 code point）；儲存失敗後 S17 沒有重新抓資料，S18 仍顯示可編輯；兩個檢查順序測試與一個去空白測試缺漏。其餘 10 項駁回，其中 3 項查證為誤報（例如「段位積分會過期」：賽事的段位表存在建立時的快照，不會變）。實作子代理有兩處偏離 spec 字面並說明原因：Form 欄位給空字串預設值，否則 FastAPI 會在鎖之前回自己的 422；新檔清理分在 service 與 router 兩處，因為例外發生時 router 拿不到鍵值
- 成熟度：L4（固定流程，子代理實作、多個獨立審查者加自動測試，主流程查證每項發現）
- 證據：spec-3-2-player-registration-info-2.md（Review Triage Log、Implementation Notes）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-03｜測試／瀏覽器實測｜Story 3.2 第二段：S17、S18 的瀏覽器與 375 px

- Story／範圍：3.2 第二段（分支 story/3-2，PR #24）
- 工具：Claude Code（Opus 5.5）＋ Playwright 1.63（容器內的 Chromium）
- 怎麼用：AI 寫 Node 腳本經 API 準備資料（管理員建遊戲、主辦方註冊驗證並經審核、建立開放報名的賽事、隊長建隊、隊員以邀請連結加入），再用 Playwright 以隊員（375 px）與隊長（桌機）兩個帳號操作 S17、S18 並逐項斷言、截圖；結束後比對 uploads volume 與資料庫的截圖鍵值
- AI 產出：資料準備與實測腳本、7 張截圖；28 項檢查全部通過（缺漏文字、平均值三種顯示、只有自己那列有按鈕、手機 Sheet／桌機 Dialog、重開 S18 只顯示檔名不顯示圖片、遊戲 ID 去頭尾空白、換截圖、隊長看不到隊員的截圖檔名、375 px 各畫面沒有水平捲動）
- 人做了什麼：決定在 commit 前先做瀏覽器實測
- 驗證：28/28 通過；實測共上傳 3 張截圖，uploads volume 最後剩 2 張，與資料庫的兩個鍵值一致，確認換掉的舊檔已刪除；人工查看 3 張截圖確認版面。上傳進度條在本機傳輸太快，沒有在瀏覽器觀察到（由單元測試涵蓋）
- 問題與修正：準備資料的腳本第一次把中文標籤放進 email 的 @ 前面，驗證信寄不出去而中斷，正是 deferred-work 裡已記錄的 identity 問題，改用英文 email；第二次因賽事每輪間隔 60 分鐘低於最小值 75 分鐘被拒，改成 90 分鐘
- 成熟度：L3（AI 自動化實測與截圖，人決定要做這項檢查）
- 證據：PR #24 檢查清單；commit 未記錄（尚未 commit）

### 2026-11-03｜需求／設計｜Story 3.3 spec：送出報名與鎖定名單

- Story／範圍：3.3（分支 story/3-3）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（兩個調查子代理、一個 spec 審查子代理）
- 怎麼用：先用 `gh pr list` 確認沒有人在做 3.3，從最新的 main 開分支（並取消 git 自動設成 origin/main 的上游）；兩個子代理分別調查後端與前端／UX，主流程寫出 spec；使用者要求審查 spec，由另一個子代理對照程式、PRD、UX 與架構文件審查
- AI 產出：spec-3-3-submit-registration.md（I/O 矩陣 16 列、12 項 Tasks）；調查時發現 identity 沒有讀帳號學校的公開函式、賽事到截止時間不會自動轉為截止（要到 3.6），以及架構文件要求送出時就分配正取或候補，但分配規則在未合併的 #28
- 人做了什麼：決定先搶期送出一律轉為待分配、等 3.5 再接上分配；決定非隊長顯示「由隊長送出報名」與缺漏；保留約 4,000 tokens 的完整 spec；審查後同意截止時間檢查擴及建隊、加入、改參賽資料，以及其他 4 項凍結區塊的修改
- 驗證：spec 審查子代理提出 15 項，主流程抽查 3 項（段位積分上限、`core/authz.py` 的寫法、`ROSTER_LOCKED` 既有訊息）皆屬實
- 問題與修正：AI 初稿照抄架構文件的平均值欄位 `numeric(6,2)`，但段位積分上限是 PostgreSQL integer 上限，大積分的遊戲送出時會溢位而回 500；初稿要加入已鎖定隊伍時沿用既有的 `ROSTER_LOCKED`，S19 會顯示「資料無法修改」這種不對的文字；Code Map 寫錯測試工具的參數（`make_tournament` 只能傳 `priority_hours`，不能傳 `priority_end`）；初稿只讓送出比對截止時間，截止後畫面會一邊寫「已截止」一邊還能改資料。以上都由 spec 審查子代理抓到
- 成熟度：L4（固定流程，多個子代理調查與審查，人在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-3-submit-registration.md（Decisions）；commit 未記錄（尚未 commit）

### 2026-11-03｜程式／程式生成｜Story 3.3 實作與審查

- Story／範圍：3.3（分支 story/3-3）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、三個審查子代理）
- 怎麼用：實作子代理只依 spec 實作；主流程讀 diff 對照 Tasks 與 I/O 矩陣、重建容器跑測試；三個審查子代理審 diff，主流程逐項查證後分類，兩項需要改凍結內容的交給使用者決定，修正交回同一個實作子代理
- AI 產出：`POST /teams/{team_id}/submission`、報名快照三欄與遷移、送出條件純函式（前端停用原因與伺服器拒絕共用）、名單鎖定與邀請連結狀態（已鎖定、已截止）、截止時間檢查擴及建隊／加入／改資料、`core.authz.ensure_captain` 與 identity 的 `get_account_school_ids`（都只新增）、S17 送出區塊與兩種倒數、S19 鎖定畫面；22 個檔案、新增 2384 行；送出報名測試 45 個（I/O 矩陣 16 列都有對應測試，含兩個多連線併發測試）
- 人做了什麼：核准 spec；決定截止後的邀請連結顯示「連結已失效：報名已截止」；決定 `ensure_captain` 改為預設通用訊息、送出時傳入專用文字
- 驗證：後端 1446 個測試通過、覆蓋率 97%，mypy、ty、ruff 通過，兩個併發測試連跑 3 次通過；前端 typecheck、biome 通過，50 個檔、624 個單元測試通過。瀏覽器實測尚未做
- 問題與修正：三個審查者共提出 22 項（合併後 18 組），修正 6 組，駁回 12 組（其中 1 組查證為誤報）。重點：截止後還在組隊中的隊伍，邀請連結仍顯示有效但加入一定失敗（本次加了截止檢查卻沒更新連結狀態）；共用的 `ensure_captain` 訊息寫死成「送出報名」，是主流程寫 spec 時造成的，D 之後做報到會用錯文字；裝置休眠時倒數先歸零，按鈕卻仍可按；加入時「先鎖再查」的順序沒有測試保護。實作子代理補併發測試時第一次就失敗，查出原因是新加入的人沒有參賽資料、送出本來就會被擋，改為依兩種先後順序分別斷言
- 成熟度：L4（固定流程，子代理實作、多個獨立審查者加自動測試，主流程查證每項發現，人只在凍結內容的修改上決策）
- 證據：spec-3-3-submit-registration.md（Review Triage Log、Implementation Notes）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-03｜測試／瀏覽器實測｜Story 3.3：送出報名、名單鎖定與截止倒數

- Story／範圍：3.3（分支 story/3-3）
- 工具：Claude Code（Opus 5.5）＋ Playwright 1.63（容器內的 Chromium）
- 怎麼用：AI 寫 Node 腳本經 API 準備資料（先發 2 人的遊戲、兩場賽事，其中一場報名截止只剩 4 分鐘；隊長、沒設學校的隊員、未加入的帳號），再用 Playwright 以隊長（375 px）、隊員（桌機）、未加入者三個帳號操作 S17、S19：先看停用原因，再經 API 補齊參賽資料與學校，由隊長在畫面上確認送出；最後等第二場賽事實際截止，觀察倒數歸零後的畫面。結束後查資料庫的報名快照與操作紀錄
- AI 產出：資料準備與實測腳本、7 張截圖；32 項檢查全部通過（停用原因逐項列出、隊員看到「由隊長送出報名」、確認框內文、送出後的徽章與優先期倒數、邀請連結「名單已鎖定」、S18 唯讀、S19 鎖定與截止兩種文字、倒數歸零後顯示「已截止」且 10 秒內沒有轉圈與逾時文字、375 px 沒有水平捲動）
- 人做了什麼：決定在 commit 前先做瀏覽器實測
- 驗證：32/32 通過；資料庫的報名為 `pending`、學校與平均段位積分 20.00 正確、有送出時間，操作紀錄有 `registration.status_changed` 與 `registration.submitted`；人工查看 3 張截圖確認版面
- 問題與修正：第一次就全部通過。人工看截圖時發現優先期倒數下方的日期沿用倒數元件的預設字尾「截止」，語意不精確，未修改，留給使用者決定
- 成熟度：L3（AI 自動化實測與截圖，人決定要做這項檢查）
- 證據：PR 檢查清單；commit 未記錄（尚未 commit）
### 2026-11-04｜程式／程式審查｜Story 3.4 第一階段：依 PR #28 審查加入名額遞補 backfill_vacancies

- Story／範圍：3.4 第一階段審查修正（分支 story/3-4，PR #28）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理、三個審查子代理）
- 怎麼用：AI 先讀 PR #28 的審查，發現建議 1（先搶期空位讓新送出的隊伍插到候補前面）與期中規則 6「抽籤前取消資格不立即遞補」衝突，列出兩種配合方式給人決定；再以 bmad-build 寫 spec、子代理實作、三個審查子代理審 diff，主流程逐項查證後把修正交回同一個實作子代理
- AI 產出：`allocation.py` 新增 `backfill_vacancies` 並改寫 `decide_first_come` 的呼叫端契約；新增 12 個測試函式（參數化後共 24 個案例），I/O 矩陣 6 列都有對應測試；epics.md 規則 6 與 Story 6.5、CONTRIBUTING 6.3、epic-3／epic-6 context 同步改成「之後分配時先由有順位的候補遞補」；deferred-work 新增 2 項
- 人做了什麼：建議 1 選 (b) 先遞補；在「延後遞補（B 的 6.5 不改）」與「立即遞補（要和 B 協調）」中選延後；決定規劃文件的修改放進 #28；核准 spec
- 驗證：後端 1704 個測試全部通過，`allocation.py` 分支覆蓋率 100%（106 statements、22 branches），mypy、ty、ruff 通過
- 問題與修正：三個審查者共提出 15 項，修正 8 項、延後 1 項、駁回 6 項（其中 3 項查證為誤報，例如「優先期內有 pending 會高估空位」：優先期內不會有候補，結果必為空）。AI 實作的錯誤：超額測試只有 1 個有順位候補，拿掉 `max(…, 0)` 測試仍會通過（Verification Gap 抓到，補測資後實際拿掉確認會失敗）；改寫 docstring 時把舊契約涵蓋的撤回、退回、提高名額漏掉；epics.md 新句子與原有括號重複；沒寫明只能在抽籤前呼叫。審查也發現新流程讓「代表隊被取消資格時應由同校遞補」在期中變得可能發生，延後處理。另外，主流程一開始以為審查建議 2、3 還沒做，查 git 才發現使用者已在 `4b30a23` 補上但尚未推送；實作子代理做突變驗證時，因容器掛載可寫入，曾暫時改到本機的 `allocation.py`，它自己改回，主流程再確認
- 成熟度：L4（固定流程，子代理實作、多個獨立審查者加自動測試，人只在規則選擇與 spec 核准時決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-allocation-backfill.md（Decisions、Review Triage Log）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-04｜需求／設計｜Story 3.4 第二階段 spec：優先期結束自動分配

- Story／範圍：3.4 第二階段（分支 story/3-4-phase2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（兩個調查子代理）
- 怎麼用：#28 合併後，AI 從 main 開新分支並 cherry-pick 審查修正的 commit；bmad-build 的單一目標檢查發現 deferred 的「第二階段」其實涵蓋 3.4、3.5、3.6 三個可各自合併的目標，提出拆分與順序；兩個子代理分別調查後端（worker、tournaments、registration、core）與前端（S17、S12、UX 字串），主流程寫出 spec
- AI 產出：spec-3-4-priority-window-allocation.md（I/O 矩陣 9 列、8 項 Tasks）；deferred-work 新增 3.5、3.6 第二階段各 1 項
- 人做了什麼：選擇拆分並依 3.4 → 3.6 → 3.5 的順序做；決定新增兩則「當下階段遞補規則說明」固定字串；決定保留約 2,500 tokens 的完整 spec；核准 spec 並先停在 ready-for-dev
- 驗證：未記錄（尚未實作；spec 未經審查子代理審查）
- 問題與修正：調查發現兩個 spec 必須處理的坑：registration 依架構規則不能直接查賽事表，所以設計結算表兼作「已結算」標記，不必動 B 的模組；3.5 還沒接上前，先搶期送出的報名也會是 `pending`，所以限定只結算 `submitted_at <= priority_end` 的報名。另外 AI 發現 EXPERIENCE.md 要求的「遞補規則說明」沒有固定字串，沒有自行假設，提出給人決定
- 成熟度：L4（固定流程，子代理調查，人在拆分、字串與核准的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md（Decisions）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-04｜程式／程式生成｜Story 3.4 第二階段：優先期結束自動分配

- Story／範圍：3.4 第二階段（分支 story/3-4-phase2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：bmad-build 把 spec 交給沒有對話脈絡的實作子代理，主流程再自己讀 diff，逐項對照 Tasks、驗收條件與 I/O 矩陣
- AI 產出：後端新增優先期結算表與 Alembic 遷移、事件 `RegistrationAllocated`、`settle_priority_window`／`allocate_due_priority_window`、worker 工作 `allocate_priority_windows`，S17／S12 回應加上候補順位、原因代碼、代表隊補充與階段；前端候補徽章、原因與遞補規則說明、正取的報名截止倒數；EXPERIENCE.md 新增兩則固定字串；新增後端測試檔 1 個（審查後共 22 個測試），前端單元測試寫在 2 個既有檔案
- 人做了什麼：spec 有矛盾時選 (甲)，完全沒有報名的賽事不寫結算紀錄，並要求先確認 3.5、3.6 與抽籤不依賴這一點；正式確認保留 `waitlist_phase`、`waitlist_reason` 只回代碼
- 驗證：實作後後端 1879 個測試全過、lint 通過；前端單元測試全量有 2～3 個失敗（見下）
- 問題與修正：主流程做 I/O 矩陣檢查時發現，凍結區塊寫「沒有任何報名的賽事也要寫結算紀錄」，Design Notes 卻規定 worker 只從有 `pending` 的賽事找候選，子代理照後者做而偏離凍結規則；沒有自己決定，停下來問人，改寫 spec 並補一個測試。子代理把前端失敗判斷成「全量平行時的不穩定、與本 Story 無關」，沒有查原因；主流程到 main 跑全量 761 個全過，才找到原因：分支開在 #47 之前，少了 `setup.ts` 的 `asyncUtilTimeout: 5000` 與 `testTimeout: 15000`。主流程第一次比較時，掛載了本機 Windows 的 `node_modules`，條件不同，改成不含 `node_modules` 的複製版本後才公平，套上 main 的兩個檔後 732 個全過。子代理自訂、spec 沒寫的兩點（多一個 API 欄位、原因只回代碼）有主動列出請人確認
- 成熟度：L4（固定流程，子代理實作，主流程依 diff 與矩陣驗證，人在 spec 矛盾與 API 設計的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md（Decisions、Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-04｜測試／程式審查｜Story 3.4 第二階段審查、合併 main 與完整驗證

- Story／範圍：3.4 第二階段（分支 story/3-4-phase2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查子代理平行讀 diff，主流程逐項查證（讀呼叫端、狀態轉換表、notifications 分派、唯一鍵），寫進 spec 的 Review Triage Log；修正交回原本的實作子代理；之後以 `git merge --no-commit origin/main` 合併 3 個新 PR（#46～#48），重新產生 client 並跑完整驗證
- AI 產出：審查發現 Blind Hunter 14 項、Edge Case Hunter 7 項、Verification Gap 2 項＋1 項其他，合併為 21 列：patch 3、defer 2、駁回 16（其中 8 列查證為不成立）；新增 2 個測試（未到期候選固定排在前面、自訂模式不結算）；deferred-work 新增 2 項
- 人做了什麼：決定先審查、再合併 main，合併後重跑全部驗證，不 commit、不 push
- 驗證：合併後後端 1913 個測試全過（含 test_migrations、test_architecture，覆蓋率 97%），mypy、ty、ruff 通過；前端 typecheck、biome 通過，單元測試 61 個檔案 798 個全過；重新產生的 client 與合併結果相同，所有變更檔為 LF，main 沒有新的 Alembic 遷移
- 問題與修正：Verification Gap 抓到實作子代理的多賽事測試用隨機 uuid，未到期候選只有約 1/3 機率排在前面，「遇到未到期就停」的回歸多半仍會通過，改成固定排序。Blind Hunter 抓到刪除舊 deferred 項目時，「`pending` 不能被 `fill_from_waitlist` 漏掉」沒有轉移到 3.6，而開發順序 3.4 → 3.6 → 3.5 正好會遇到。主流程查證 Edge Case Hunter 的「沒結算就抽籤」時，發現 competition 實際呼叫的是 `finalize_for_draw`，主流程先前寫進 Decisions 的只有 `fill_at_deadline`，已更正。合併時 `git stash` 因先前 `git add -N` 標記的新檔失敗，改為先取消標記再備份
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每一項，人決定流程與合併時機）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md（Review Triage Log）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-04｜測試／瀏覽器實測｜Story 3.4 第二階段：S12、S17 分配結果（桌機與 375 px）

- Story／範圍：3.4 第二階段（分支 story/3-4-phase2，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ Playwright（專案的 e2e 容器）
- 怎麼用：AI 用 SQL 在開發資料庫建兩場名額 3 的校園賽（先搶期、截止後）、4 校 6 隊與 6 個帳號，報名寫成「已送出・待分配」，由實際的 worker 結算；再寫一個沿用專案 Playwright 設定的實測 spec（不放進 repo），以 4 個帳號在桌機與 375 px 登入檢查 S12、S17，最後人工看截圖
- AI 產出：資料準備 SQL、實測 spec 與設定、22 張截圖；8 個情境全部通過（正取、「候補第 1／2 位」、「候補・目前不在遞補順序中」＋兩種原因、代表隊補充、兩則階段規則說明逐字相同，正取倒數截止前顯示、截止後不顯示，沒有橫向捲軸）；修正 `RegistrationStatusCard.tsx` 的版面並補 1 項單元測試斷言
- 人做了什麼：要求先做瀏覽器實測再 commit；在三種版面方案中選「說明移到整列下方」
- 驗證：worker 在 20 秒內結算兩場（各 1 筆摘要、6 筆狀態變更、合計 12 個事件），結果與分配規則一致；修正後瀏覽器實測 8/8、前端單元測試 798 個全過、biome 與 typecheck 通過
- 問題與修正：自動檢查第一次就全過，但 AI 看 375 px 截圖時發現 S12 的長徽章「候補・目前不在遞補順序中」設了不換行、不縮小，占約 170 px，說明欄只剩約 100 px、卡片被拉長到約 350 px；審查與單元測試都沒抓到。AI 列出三種方案請人決定，修正後縮到約 220 px。另外，既有資料裡有一筆沒有送出快照的 `pending` 報名，審查時判定「不會發生」的缺快照情況實際存在於開發資料庫；實測確認結算會略過它、寫入空紀錄，worker 沒有錯誤。AI 補新測試斷言時一次沒有照 biome 格式，biome 擋下後修正
- 成熟度：L3（AI 準備資料、自動化實測並看截圖找出問題，人決定版面方案）
- 證據：_bmad-output/implementation-artifacts/spec-3-4-priority-window-allocation.md（Decisions、Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-04｜需求／設計｜Story 3.6 第二階段之一 spec：給抽籤用的 registration 函式

- Story／範圍：3.6 第二階段之一（分支 story/3-6，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個調查子代理、一個 spec 審查子代理）
- 怎麼用：bmad-build 的單一目標檢查把 3.6 第二階段拆成「給 D 抽籤用的四個函式」與「截止 worker」，先做前者；調查子代理查 competition 的抽籤流程、D 的測試替身與示範資料，主流程查 registration 與 `allocation.py`，參考之前 stash 裡的舊草稿寫出 spec；人選擇先審查 spec，由審查子代理對照程式碼審查
- AI 產出：spec-3-6-draw-functions.md（I/O 矩陣 15 列、5 項 Tasks、6 則 Decisions，約 4,500 tokens）；deferred-work 新增「Story 3.6 第二階段之二：截止 worker」1 項
- 人做了什麼：選擇拆分並先做抽籤函式；決定優先期內抽籤照合約立即結算、晚送出的 `pending` 補做先搶期；保留完整 spec；選擇先審查 spec，並在審查後決定提前抽籤的候補依截止後規則顯示、抽籤觸發的分配操作者記主辦方、完成時刪除 3 項 deferred；核准 spec 並停在 ready-for-dev
- 驗證：spec 審查子代理提出 13 項（必改 5、建議 7、小地方 1），主流程查證後 3 項請人決定、10 項直接修正；新增的矩陣列由主流程依 `allocation.py` 規則手算核對
- 問題與修正：審查抓到 AI 寫的 spec 自相矛盾：AC 寫「抽籤後候補依截止後規則顯示」，但 `_current_phase` 只看報名截止時間，報名截止前抽籤會顯示先搶期規則，主流程查程式確認後交人決定；Tasks 引用已刪除的「Open Question 1」；漏寫補做先搶期時每筆都要重建候選名單（否則會超收或同校兩隊正取）、剩餘名額可能為負數、`mark_drawn` 遇到不存在 id／重複 id／空清單的處理。調查子代理找到 spec 原本沒注意的風險：示範資料的 `load()` 會對沒有報名的示範賽事真的抽籤，`finalize_for_draw` 不能拋出 `BusinessError` 以外的錯誤。舊草稿早於 3.4 第二階段，裡面「優先期學校不另存」與事件名稱已過時，沒有照搬
- 成熟度：L4（固定流程，子代理調查與審查，主流程查證，人在拆分、規則與核准的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-draw-functions.md（Decisions）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-04｜程式／程式生成｜Story 3.6：給抽籤用的 registration 函式

- Story／範圍：3.6（分支 story/3-6，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個實作子代理）
- 怎麼用：主流程把 spec 交給沒有對話脈絡的實作子代理，spec 是唯一依據；子代理完成後，主流程讀完整 diff，逐項核對 Tasks、驗收條件與 I/O 矩陣 15 列，再自己重建容器跑相關測試
- AI 產出：registration `service.py` 新增 4 個公開函式（`finalize_for_draw`、`list_accepted_teams`、`mark_drawn`、`get_team_names`）與 4 個私有函式（共用的鎖內結算、分配、補做先搶期、截止補位），`_current_phase` 改為賽事不是開放報名就用截止後規則；`repository.py` 新增 3 個查詢；新增 2 個測試檔（`test_draw_functions.py` 29 個測試、`test_settlement_concurrency.py` 2 個）；更新 competition 合約與 deferred-work（刪除 3 項）
- 人做了什麼：在 spec 階段做的決策（拆分、提前抽籤立即結算、操作者記主辦方等）；本階段沒有額外決策
- 驗證：主流程重建容器後跑新測試、worker 與 `tests/competition/` 共 935 個全過；子代理把鎖換成不加鎖的讀取，確認兩組併發測試都會失敗（第二個 session 撞結算表主鍵）
- 問題與修正：子代理在容器裡對整個 `tests/` 跑 ruff format 與 `ruff check --fix`，動到 4 個其他組員的測試檔，子代理自己發現後用 `git checkout` 還原並回報。主流程在 Git Bash 用 `python` 改 spec frontmatter 時，叫到的是 Windows Store 的別名（exit 49），改用 `uv run --no-project python`
- 成熟度：L4（固定流程，子代理實作，主流程依 diff 與 I/O 矩陣驗證並自己重跑測試）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-draw-functions.md（Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-04｜測試／程式審查｜Story 3.6 審查與完整驗證

- Story／範圍：3.6（分支 story/3-6，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查子代理平行讀 diff，主流程到程式碼逐項查證（送出報名是否同一把鎖、抽籤 router 何時 commit、`Registration.team_id` 是否唯一、有沒有 registration 合約），寫進 spec 的 Review Triage Log；修正交回原本的實作子代理
- AI 產出：Blind Hunter 15 項、Edge Case Hunter 3 項、Verification Gap 0 項（附追蹤過的分支清單），合併為 18 列：patch 1、defer 0、駁回 16（查證不成立 10、影響輕微 6）、無缺口 1
- 人做了什麼：本階段沒有額外決策
- 驗證：修正後重建容器，後端 1944 個測試全過，mypy、ty、ruff check、ruff format 通過
- 問題與修正：Blind Hunter 抓到 AI 寫的 `get_team_names` 測試用條件過濾建出預期值，查不到隊伍時預期值會跟著變小，測試仍會通過；改成直接斷言兩隊與各自的隊名。審查者提出的「送出報名與抽籤競態」「提前抽籤不足 2 隊時結算紀錄被寫入」，主流程查證後不成立：送出報名同樣先鎖賽事並在鎖內檢查開放狀態，router 只在成功時 commit。主流程為了產生 diff 又用了 `git add -N`（3.4 時已因此讓 `git stash` 失敗），這次在讀完 diff 後立刻取消標記，第二次改用 `git diff --no-index` 附上新檔，不動 index。完整測試加 lint 超過前景 600 秒上限，改在背景執行
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每一項）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-draw-functions.md（Review Triage Log）；commit 未記錄（尚未 commit）

### 2026-11-05｜需求／設計｜Story 3.6 spec：報名截止自動補位

- Story／範圍：3.6（分支 story/3-6-deadline，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個 spec 審查子代理）
- 怎麼用：主流程調查 worker 排程、tournaments 的狀態轉換與找候選寫法、epics 的 3.6 驗收條件後寫出 spec；人選擇先審查，由子代理對照程式碼審查；之後 main 合併了 #53 等 5 個 PR，主流程重新查證 D 在 #53 的 4 項建議、合併後的 deferred-work，再更新 spec 並草擬給 D 的回覆
- AI 產出：spec-3-6-deadline-fill.md（I/O 矩陣 16 列、13 項 Tasks、8 則 Decisions，約 5,900 tokens）；#53 上給 D 的回覆（4 項建議的處理）
- 人做了什麼：保留完整 spec；決定截止後的錯誤訊息維持「這場賽事的報名已截止。」、`fill_at_deadline` 由 `finalize_for_draw` 取代、3-6 先改回 in-progress；要求加入提前抽籤失敗回滾測試並驗證確實寫入後才回滾；要求重新確認 6 項 deferred 都已完成或被涵蓋；修改回覆草稿兩處並要求查證送出時間的邊界；選擇以重設分支取代合併 commit；核准 spec 停在 ready-for-dev
- 驗證：spec 審查子代理提出 12 項（必改 3、建議 7、小地方 2），主流程查證後 3 項請人決定、其餘直接修正；deferred-work 要刪的 6 項逐項對照程式碼與測試（`TournamentOverview.tsx`、`mark_drawn`、`_ORDER_STATUSES`、#53 的測試）
- 問題與修正：AI 寫的第一版 spec 有三處錯誤，由審查子代理抓到：Problem 寫「截止後仍可送出報名」，但 registration 早已自己比對截止時間；以為插入新 worker 工作不影響既有測試，`test_email_pipeline.py` 其實比對完整清單；沒注意併發測試留下的 `open` 賽事會讓「找最早到期」的測試不穩定。AI 給 D 的回覆草稿第一版斷言「`submitted_at` 不會晚於截止」，人要求查證後發現截止檢查與寫入 `submitted_at` 是兩次 `clock.now()`，截止前一刻送出時可能晚幾毫秒，改成修正並補回歸測試，回覆也改為承認這個情況。另外發現 `deferred-work.md` 的 `merge=union` 讓 #53 刪掉的 3 項在 #51 合併後又回來
- 成熟度：L4（固定流程，子代理審查，主流程查證，人在規則、範圍與回覆的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md（Decisions）；https://github.com/Team14good/esport-platform/pull/53#issuecomment-6658603472；commit 未記錄（尚未 commit）

### 2026-11-05｜程式／程式生成｜Story 3.6：報名截止自動補位

- Story／範圍：3.6（分支 story/3-6-deadline，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個實作子代理）
- 怎麼用：主流程確認分支基於最新 origin/main、spec 為 ready-for-dev 且 I/O 矩陣 16 列後，把 spec 交給沒有對話脈絡的實作子代理；完成後主流程讀完整 diff，逐項核對 Tasks 與 16 列矩陣，再自己重建容器跑完整測試
- AI 產出：tournaments 新增公開函式 `find_due_registration_end_id` 與 repository 查詢；registration 新增 `close_registration`、`close_due_registration`，`_ensure_registration_period` 遇到 `closed` 回「這場賽事的報名已截止。」，`submit_registration` 只取一次 `now`；worker 新增 `close_registrations`；新增 2 個測試檔（31 個測試案例），在既有測試檔新增 3 個測試與 2 組併發參數，`test_email_pipeline.py` 插入 1 行；更新 tournaments 合約、sprint-status 備註，deferred-work 刪除 6 項
- 人做了什麼：在 spec 階段做的決策（錯誤訊息、不公開 `fill_at_deadline`、回滾測試、送出時間只取一次等）；本階段沒有額外決策
- 驗證：完整後端測試 2015 passed、覆蓋率 97%，lint 通過；子代理把 `submit_registration` 改回取兩次時間，確認新的回歸測試會失敗後還原
- 問題與修正：子代理對 `tests/registration` 跑 ruff format，順手改到別人的 `test_confirm_advance.py`（自己發現並還原），也把自己檔案裡一段既有測試重新排版（由審查抓到，見下一筆）。子代理在審查前就把 spec 狀態改成 `done`，主流程依流程改回 `in-review`。子代理沒有依 Decisions 先把 sprint-status 的 3-6 改回 `in-progress`，只改備註
- 成熟度：L4（固定流程，子代理實作，主流程依 diff 與 I/O 矩陣驗證並自己重跑測試）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md（Tasks、Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-05｜測試／程式審查｜Story 3.6 報名截止的審查與完整驗證

- Story／範圍：3.6（分支 story/3-6-deadline，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查子代理平行讀 diff，主流程到程式碼逐項查證（`finalize_for_draw` 是否已測過非開放狀態、自訂模式的既有處理、`lint.sh` 的檢查範圍、鎖內重新檢查能否空轉），寫進 spec 的 Review Triage Log；修正交回原本的實作子代理
- AI 產出：Blind Hunter 13 項、Edge Case Hunter 4 項、Verification Gap 0 項缺口（另 1 項其他發現），去重後 14 列：patch 1、defer 1、駁回 12（查證不成立 3、與凍結的 I/O 矩陣一致 1、影響輕微 8）
- 人做了什麼：本階段沒有額外決策
- 驗證：修正後重建容器，後端 2015 passed、覆蓋率 97%，ruff check、ruff format 通過
- 問題與修正：Blind Hunter 抓到 AI 在 `test_allocation.py` 混入既有測試的排版變更，還原後只剩新增的 20 行。三個審查者都提出「最早到期的賽事一直失敗會卡住之後的賽事」，與 `open_due_registration` 相同的既有模式，列入 deferred-work。實作子代理回報 `test_allocation.py` 原本就有 `test_story_3_6_example_deadline_fill` 涵蓋 epics E/F/G/H 範例，spec 的 Code Map 寫「沒有 E/F/G/H 範例」是錯的，新增的測試與它重複。主流程在 Git Bash 檢查換行時又叫到 Windows Store 的 `python` 別名（exit 49），改用 `tr -cd '\r' | wc -c`
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每一項）
- 證據：_bmad-output/implementation-artifacts/spec-3-6-deadline-fill.md（Review Triage Log）；deferred-work.md；commit 未記錄（尚未 commit）

### 2026-11-06｜需求／設計｜Story 3.5 spec：先搶期即時分配

- Story／範圍：3.5（分支 story/3-5，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個調查子代理、一個 spec 審查子代理）
- 怎麼用：主流程確認沒有重複的 PR 後從 origin/main 開分支；調查子代理整理送出流程、`allocation.py`、3.6 的鎖內函式、前端送出回應與併發測試寫法，主流程讀 `_first_come_locked` 等程式確認後寫 spec；#58 合併後同步 main、更新行號；人選擇先審查，由子代理對照程式碼審查
- AI 產出：spec-3-5-first-come-allocation.md（I/O 矩陣 13 列、10 項 Tasks、5 則 Decisions，約 15,000 字元）
- 人做了什麼：決定 Toast 維持「已送出報名」、保留完整 spec；要求先審查 spec；核准後停在 ready-for-dev
- 驗證：spec 審查子代理提出 15 項（必改 3、建議 8、小地方 4），主流程到程式碼查證，15 項都成立並修正；確認 #58 合併後刪除的 6 項 deferred 沒有被 `merge=union` 帶回
- 問題與修正：AI 寫的第一版 spec 有兩處照著做會測不過，由審查子代理抓到：矩陣把「同校已有先搶期正取」的原因寫成 `LATER_THAN_SCHOOLMATE`，實際 `allocation.py` 回 `SCHOOL_NOT_ELIGIBLE`；200 筆測試寫「200 隊各屬不同學校」，但初始資料只有 139 所且學校清單測試檢查總數。另外漏了最常見的「優先期沒有任何報名時第一筆送出會寫空結算紀錄」、兩處行號錯誤、deferred 要刪整個項目而不是單行、router docstring 會過時。主流程第一次套用修改時比對字串沒對上，斷言在寫檔前擋下，修正後重跑
- 成熟度：L4（固定流程，子代理調查與審查，主流程查證，人在規則與核准的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-3-5-first-come-allocation.md（Decisions）；commit 未記錄（尚未 commit）

### 2026-11-06｜程式／程式生成｜Story 3.5 先搶期即時分配

- Story／範圍：3.5（分支 story/3-5，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個實作子代理）
- 怎麼用：主流程記下基準 commit `453b847`，把 spec 交給沒有對話脈絡的實作子代理，spec 是唯一需求來源；完成後主流程自己讀 diff、對照 I/O 矩陣逐列核對
- AI 產出：`submit_registration` 在校園賽、`now > priority_end` 時，同一個鎖與交易內先結算優先期再呼叫 `_first_come_locked`（service.py 約 10 行程式）；router docstring 更新並重新產生 client；新增 test_first_come_submission.py（11 支）、test_first_come_concurrency.py（200 筆與名額只剩 1 個，2 支），改 1 支既有測試，前端新增 3 支單元測試；deferred-work 刪 2 項
- 人做了什麼：spec 的 Decisions（Toast 不變、保留 200 筆併發測試）在前一階段決定；本階段沒有新的決策
- 驗證：主流程重新 build 後自己重跑新增與相關測試 61 passed（含 200 筆平行送出）
- 問題與修正：子代理在審查前就把 sprint-status 的 3-5 標成 `done`，主流程比對 diff 時發現，改回 `in-progress`，審查後才標 `done`。主流程用 Git Bash 的 `python` 改 spec frontmatter 時又叫到 Windows Store 的空殼別名，指令沒有錯誤訊息但檔案沒變，`head` 檢查時發現，改用 `py`。子代理修審查意見時自行跑了 `scripts/prestart.sh`，主流程查看腳本內容，只是遷移與初始資料，無害
- 成熟度：L4（依 spec 由子代理實作，主流程獨立讀 diff 與重跑測試）
- 證據：_bmad-output/implementation-artifacts/spec-3-5-first-come-allocation.md（Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-06｜測試／程式審查｜Story 3.5 審查與驗證

- Story／範圍：3.5（分支 story/3-5，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個子代理）
- 怎麼用：三個沒有對話脈絡的審查子代理同時讀 diff；主流程逐條到程式碼查證後判定，修正項交回原實作子代理
- AI 產出：審查意見 13 條（Blind Hunter 9、Edge Case Hunter 4、Verification Gap 0）
- 人做了什麼：未參與判定；判定與證據寫在 spec 的 Review Triage Log 供審閱
- 驗證：判定結果：修正 2 條、駁回 11 條（不成立 5、影響小 6），延後 0 條。修正後重新 build：後端 `scripts/test.sh` 通過、覆蓋率 97%（主流程只看到結尾，通過數未記錄；子代理修正前回報 2028 passed）；`lint.sh` 通過；前端 typecheck、biome 通過，單元測試 63 檔 834 passed
- 問題與修正：Blind Hunter 抓到 AI 只更新 docstring 的下半段，`submit_registration` 第一行仍寫「轉為待分配」，router 說明也漏了自訂模式，已修並重新產生 client。Blind Hunter 與 Edge Case Hunter 都提出「結算函式回傳 False 時，優先期報名會被當先搶期判定」，主流程讀 `_ensure_registration_period` 與 `_priority_window_due` 確認送出時一定已開放且過了優先期，回 False 只會是已結算，判定不成立。Blind Hunter 說前端沒測 `SCHOOL_NOT_ELIGIBLE`，主流程 grep 到既有測試，判定不成立。主流程第一次跑前端單元測試時用 `tail` 截掉了通過數，重跑後只取摘要
- 成熟度：L4（多個獨立審查者加自動測試，主流程查證每一條）
- 證據：_bmad-output/implementation-artifacts/spec-3-5-first-come-allocation.md（Review Triage Log）；commit 未記錄（尚未 commit）

### 2026-11-06｜測試／瀏覽器實測｜Story 3.5：先搶期送出後 S17 直接顯示分配結果（桌機與 375 px）

- Story／範圍：3.5（分支 story/3-5，尚未開 PR）
- 工具：Claude Code（Opus 5.5）＋ Playwright（專案的 e2e 容器）
- 怎麼用：人選擇先做瀏覽器實測再 commit。主流程照 3.4 的做法交給子代理：用 SQL 在開發資料庫建兩場名額 2、正在先搶期的校園賽（桌機、手機各一場，每隊只有隊長一人），寫一個掛進 e2e 容器、沿用專案 Playwright 設定的實測 spec（不放進 repo），由隊長在 S17 依序點「送出報名」
- AI 產出：資料準備 SQL、實測 spec、24 張截圖；兩種寬度各 4 次送出，2 個 Playwright 測試第一次執行就通過（47.6 秒）：X 校隊 1「正取」、X 校隊 2「候補・目前不在遞補順序中」＋學校不符資格原因、Z 校隊填滿名額、Y 校隊「候補第 1 位」；每次都確認 Toast「已送出報名」、沒有整頁重新載入、DOM 從未出現「已送出・待分配」、375 px 沒有水平捲動
- 人做了什麼：決定在 commit 前先做瀏覽器實測
- 驗證：資料庫查核兩場數字相同：每隊 `registration.status_changed` 恰好 2 筆（待分配的操作者為隊長、結果為系統），`registration.priority_window_settled` 每場 1 筆且在第一筆送出的同一交易內、排在第一筆判定之前，`RegistrationAllocated` 每筆報名 1 則（合計 8 則）。主流程親自看了桌機正取、375 px 沒有順位與候補第 1 位三張截圖，徽章與說明正確、沒有截斷
- 問題與修正：沒有發現產品程式的錯誤。子代理的確認框截圖截在開啟動畫中途，呈半透明，屬截圖時機問題。子代理另外注意到名單鎖定後自己那列仍顯示「填寫我的資料」按鈕，3.3 的實測已確認點開後是唯讀，不屬 3.5 範圍，未修改
- 成熟度：L3（AI 準備資料、自動化實測並看截圖，人決定要做這項檢查）
- 證據：_bmad-output/implementation-artifacts/spec-3-5-first-come-allocation.md；commit 未記錄（尚未 commit）

### 2026-11-08｜測試／程式審查｜Story 3.5 處理 PR #59 審查建議並同步 main

- Story／範圍：3.5（分支 story/3-5，PR #59）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：兩位組員（OG-Matcha、max930000）核准 PR #59 後，人請 AI 處理留言。AI 用 gh 讀出審查內容，依序同步 main、補測試、更新 spec
- AI 產出：`git merge origin/main`（解 `sprint-status.yaml` 衝突、以 `scripts/generate-client.sh` 重新產生 client）；併發測試的公平性斷言；`priority_end` 後 1 微秒的邊界測試；5 支測試的操作紀錄操作者斷言；前端 `waitlistLines()` helper 取代五處 `as HTMLElement`；spec Review Triage Log #13–#19
- 人做了什麼：交代處理審查建議；審查者提供公平性斷言的寫法
- 驗證：後端 `scripts/test.sh` 2096 passed、覆蓋率 97%；`lint.sh` 通過；前端 typecheck、biome 通過，單元測試 64 檔 843 passed
- 問題與修正：AI 用 `python` 解衝突時，這台電腦的 `python` 是 WindowsApps 佔位程式，沒有執行也沒有報錯，AI 沒檢查就 `git add`，merge commit 帶著衝突標記。之後同一個佔位程式讓前端替換也沒生效，typecheck 報「`waitlistLines` 宣告但未使用」，AI 才 grep 發現檔案沒變，回頭檢查到 merge commit 的衝突標記；改用 `py -3` 重做，並 amend 尚未推送的 merge commit。另外第 1 輪自審時駁回的公平性斷言（Triage #6，理由是要重算整套規則），審查者指出沒有優先期學校時只要排序取前 N，這次補上
- 成熟度：L3（AI 執行修正與驗證，審查與判斷來自組員）
- 證據：PR #59；commit 2535df5（merge）、676141c；_bmad-output/implementation-artifacts/spec-3-5-first-come-allocation.md（Review Triage Log #13–#19）

### 2026-11-08｜需求／設計｜Story 6.4 spec：提出檢舉

- Story／範圍：6.4（分支 story/6-4，尚未 commit）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個調查子代理、一個 spec 審查子代理）
- 怎麼用：主流程先查 PR 動態與 #59、#61 對 6.4 的影響，從最新 origin/main 開分支；依專案規則用 git 確認 epic-6-context 未過期；調查子代理整理 registration 公開函式、上傳寫法、S2 掛載方式、遷移與測試慣例；主流程對照 #55 的 disputes 介面約定、epics、UX 寫 spec；人回答待決問題後要求審查 spec，由子代理對照程式碼與文件審查
- AI 產出：spec-6-4-file-report.md（I/O 矩陣 21 列、14 項 Tasks、Decisions 7 則、給實作的 7 點提醒，約 6,600 tokens）
- 人做了什麼：決定處理中不能重複檢舉、沒有可檢舉的隊伍時不顯示入口、保留完整 spec；要求審查 spec；核准 20 項修正與 S20 的畫面文字、欄位、錯誤訊息、主辦方列表排序；規定與 #55 約定不同的地方要先取得 B 同意；停在 ready-for-dev，實作改在新的 session
- 驗證：spec 審查子代理提出 20 項（必改 7、建議 8、小地方 5），主流程到程式碼抽查 4 項（query 對 403 重試 3 次、`FieldError` 的 code 必填、`ResponsiveShell` 未 export、multipart 欄位需預設空字串）都屬實，20 項全部修正
- 問題與修正：AI 寫的第一版 spec 有多處照著做會出錯，由審查子代理抓到：`file_report` 回傳不含附件鍵值，router 在 commit 失敗時刪不了檔；S2 入口依 403 判斷隊長，但專案的 query 預設對 403 重試 3 次，隊員打開頁面會連打 4 次 API；說明欄若宣告為必填表單欄位，空白時會回 FastAPI 的英文錯誤而不是中文訊息；`Report` 欄位型別與索引沒寫，與「6.5 不再改表」矛盾；S20 介面文字沒定。另外，AI 寫第一版時已發現 #55 約定的 `CAPTAIN_REQUIRED` 在程式中不存在，改沿用 `TEAM_CAPTAIN_REQUIRED`。主流程第一次用 bash 內嵌 Python 套用修改時解析失敗，檔案未被改動，改成先寫腳本檔再執行
- 成熟度：L4（固定流程，子代理調查與審查，主流程查證，人在待決問題與核准的 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-6-4-file-report.md（Decisions、Implementation Notes）；commit 未記錄（尚未 commit）

### 2026-11-08｜程式／程式生成｜Story 6.4 提出檢舉：實作

- Story／範圍：6.4（分支 story/6-4，尚未 commit）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（一個實作子代理）
- 怎麼用：新的 session 用 bmad-build 接手 ready-for-dev 的 spec，主流程記錄 baseline 後把 spec 交給實作子代理；完成後主流程讀完整 diff，逐項對照 Tasks 與 I/O 矩陣，並自己重跑全部測試
- AI 產出：
  - 後端：`report` 資料表與遷移；disputes 的 4 個公開函式與 4 支 API（含第一支附件下載 API）；registration 新增 2 個公開函式
  - 前端：S20 對話框、S2「檢舉隊伍」入口、queries 與 mutation hook；把 S18 的 `ResponsiveShell` 抽成共用的 `ResponsiveDialog`
  - 測試：後端新增 3 個測試檔，前端新增 `report-team.test.tsx`
- 人做了什麼：spec 階段已決定規則與畫面；這次在 checkpoint 確認實作與審查結果，並決定不由 AI commit
- 驗證：後端 `scripts/test.sh` 2158 個通過（覆蓋率 97%），lint 通過；前端 869 個單元測試通過，typecheck 與 biome 通過；平行送出兩筆相同檢舉的併發測試在真實 PostgreSQL 上只成功一筆
- 問題與修正：
  - 實作子代理把既有測試 `tournament-create-team.test.tsx` 的斷言「報名截止時不查我的隊伍」改成相反的斷言。它有主動回報，主流程對照 spec 的 Design Notes 確認新入口本來就會多查一次，才接受這個修改。
  - 子代理第一次回報時，前端修正後沒有再全部重跑測試，主流程補跑一次（869／869）。
  - 主流程更新 sprint-status 時，又因為 `python` 是 WindowsApps 佔位程式而沒有寫入檔案；grep 結果顯示檔案沒變，才發現，改用 Edit 與 sed。
- 成熟度：L4（固定流程，子代理實作，主流程對照 diff 並重跑驗證，人在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-6-4-file-report.md（Tasks、baseline_commit 7e32d9f）；commit 未記錄（尚未 commit）

### 2026-11-08｜測試／程式審查＋測試修正｜Story 6.4 提出檢舉：審查與修正

- Story／範圍：6.4（分支 story/6-4，尚未 commit）
- 工具：Claude Code（Opus 5.5）＋ bmad-build 審查步驟（Blind Hunter、Edge Case Hunter、Verification Gap 三個審查子代理）
- 怎麼用：三個審查子代理同時審查 diff，主流程逐項到程式碼核實並分類，寫入 spec 的 Review Triage Log，再把 patch 交回實作子代理
- AI 產出：審查共提出 23 項（Blind Hunter 15、Edge Case Hunter 5、Verification Gap 3）；修正 6 項，前端單元測試從 869 個增加到 874 個，後端從 2158 個增加到 2161 個
- 人做了什麼：在 checkpoint 確認審查分類與修正結果
- 驗證：修正後重跑全部檢查：後端 2161 個通過（覆蓋率 97%）、lint 通過；前端 874 個通過、typecheck 與 biome 通過
- 問題與修正：
  - Edge Case Hunter 抓到一個實際的 bug：送出遇到 `REPORT_NOT_ALLOWED` 後重新取得資料，入口條件不再成立，對話框連同錯誤訊息一起消失，違反 spec「錯誤顯示在對話框內」。已改成對話框開著時保留。
  - Verification Gap 指出「依隊名排序」的測試只有兩隊、id 隨機，拿掉排序約一半機率仍會通過。已改成隊名順序與 id 順序相反。
  - 另外補了上傳進度的串接、對話框重開清空、各種報名狀態的錯誤訊息等測試，並替附件下載加上 `nosniff`、`no-store` 標頭。
  - 駁回 17 項：outbox 會不會因為 `ReportFiled` 沒有 handler 而出錯，主流程讀 `dispatch_event` 確認會記錄後略過；其他是 spec 已規定的行為或低影響項目。
  - 實作子代理修完沒有回報修改內容，主流程用 git 與 grep 逐項確認 6 項都已寫進程式。
- 成熟度：L4（多個審查者加自動驗證，主流程查證，人在 checkpoint 決策）
- 證據：_bmad-output/implementation-artifacts/spec-6-4-file-report.md（Review Triage Log #1–#23）；commit 未記錄（尚未 commit）

### 2026-11-08｜測試／瀏覽器實測｜Story 6.4 提出檢舉：S2 入口與 S20

- Story／範圍：6.4（分支 story/6-4）
- 工具：Claude Code（Opus 5.5）＋ e2e 容器的 Playwright
- 怎麼用：AI 在後端容器用一次性腳本建立賽事、四支隊伍與一筆既有檢舉，再寫一次性的 Playwright 腳本，以桌機與 375 px 兩種寬度操作真實的前後端，並看截圖確認畫面
- AI 產出：測試資料腳本 1 支、Playwright 腳本 1 支（4 個情境），截圖 11 張；兩支腳本都不進 repo
- 人做了什麼：決定在 commit 前做瀏覽器實測
- 驗證：4 個情境全部通過，涵蓋 S2 入口的顯示條件、S20 的停用狀態、前端檢查、字數計算、附件送出與 Toast、主辦方列表與附件下載的權限及標頭、手機版底部 Sheet
- 問題與修正：e2e 容器把 `tests/` 掛成唯讀，腳本放不進去，改成掛到 `/app/frontend/manual` 並另寫設定檔；手機版第一次截圖時 Sheet 還在滑入，看截圖才發現，等動畫結束後重拍。沒有發現產品程式的問題
- 成熟度：L3（AI 依 spec 設計實測並執行，人決定要實測並確認結果）
- 證據：spec-6-4-file-report.md 的 I/O 矩陣 S2／S20 各列；截圖在 frontend/test-results/manual-6-4/（不進 repo）

### 2026-11-09｜專案管理與流程／介面協調｜Story 6.4 依 B 的回覆調整約定差異

- Story／範圍：6.4（PR #64）；與 6.1（PR #63）的介面協調
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 B 在 #63 的回覆，到 main 與 `story/6-1` 查證 B 說的內容，整理成兩個待決問題給使用者選，再依決定修改程式、遷移、測試、spec 與 `contracts/disputes.md`
- AI 產出：
  - 改 4 個程式檔：disputes 的 service、models，遷移檔，以及前後端各一個測試檔。
  - spec 更新 Decisions、Boundaries、I/O 矩陣、Code Map、Design Notes 與 Spec Change Log。
  - 約定檔回寫 7 處差異與 2 個新決定。
- 人做了什麼：決定非隊長錯誤碼改用 `CAPTAIN_REQUIRED`、`report.reason` 改用 `Text`
- 驗證：後端 2171 個測試通過（覆蓋率 97%）；前端 899 個單元測試通過，typecheck 與 biome 通過；lint 第一次發現 1 個檔案格式不符，用 ruff format 修正後通過
- 問題與修正：
  - AI 在 spec 寫「程式中沒有 `CAPTAIN_REQUIRED`」，因此改用 `TEAM_CAPTAIN_REQUIRED`；B 在 #63 指出 competition 5.1 報到就在用。AI 用 `git grep` 查 main，確認 `competition/service.py:1021` 確實有這個碼，原本的判斷有誤。原因是當時只查了 `core/authz.py`，沒有搜尋整個 backend。
  - AI 一開始把 `reason` 定為 200 字，沒考慮 6.5 要寫查證經過；B 指出後改用 `Text`，與申訴一致。
  - AI 手動改程式後沒有先格式化，lint 抓到後才修正。
- 成熟度：L3（AI 查證並執行修改，決定來自組員協調與使用者）
- 證據：PR #64、#63 留言；_bmad-output/implementation-artifacts/spec-6-4-file-report.md（Decisions 2026-11-09、Spec Change Log）；commit 未記錄（尚未 commit）

### 2026-11-09｜測試／依審查建議補強｜Story 6.4 處理 B 在 #64 的審查建議

- Story／範圍：6.4（PR #64）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：AI 讀 B 在 #64 的核准審查（B 用 bmad-code-review 跑了四個審查員），把 4 點不擋合併的建議整理給使用者選；使用者決定合併前處理其中 3 點，AI 實作並重跑驗證
- AI 產出：
  - `report` 表加 `(reported_team_id, status)` 索引，以及 CHECK `reporter_team_id <> reported_team_id`，直接改尚未進 main 的遷移。
  - 新增 4 個測試：資料庫擋下檢舉自己的隊伍、檔案已不在時下載回 404，以及 S2 頁面層的 2 個案例。
  - 更新 PR 說明差異表第 7 項與 spec 的 Spec Change Log。
- 人做了什麼：B 審查並核准；使用者決定合併前處理哪幾點，約定檔殘留的寫法交給 B 合併 #63 時修改
- 驗證：後端 2173 個測試通過（覆蓋率 97%），lint 通過；前端 901 個單元測試通過，typecheck 與 biome 通過
- 問題與修正：新增的 S2 頁面層測試第一次失敗，找不到「檢舉隊伍」，5 秒後逾時。AI 單獨重跑讀錯誤訊息，發現是 jsdom 沒有 `window.matchMedia`：隊長的 S2 會掛載 S20，`useIsMobile` 呼叫它而讓整頁出錯。這不是產品問題（瀏覽器實測正常），照其他測試檔的做法 mock `matchMedia` 後通過。這也說明 B 指出的缺口是真的：之前的測試都直接渲染元件，沒有走過整頁的路徑。
- 成熟度：L4（組員以多代理審查提出建議，AI 實作並以自動測試驗證，人在 checkpoint 決策）
- 證據：PR #64（B 的審查）；_bmad-output/implementation-artifacts/spec-6-4-file-report.md（Spec Change Log 2026-11-09）；commit 未記錄（尚未 commit）

### 2026-11-09｜測試／依合併後審查補強｜Story 6.4 合併後審查的後續

- Story／範圍：6.4 後續（分支 story/6-4-followup）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（oneshot，Blind Hunter 一層審查）
- 怎麼用：AI 整理 D 在 #64 合併後的審查與留言，使用者選擇處理 M1 與兩個順手項目；AI 寫 spec、實作，並實際拿掉鎖驗證測試
- AI 產出：
  - 改 4 個檔：併發測試、刪檔測試、`useFileReport.ts`、前端單元測試。
  - 新增 1 個前端測試；後端在既有的 3 支測試加入 spy 與斷言。
  - 新 spec `spec-6-4-followup-review.md`，spec-6-4 的 Review Triage Log 補 3 列。
- 人做了什麼：D 審查指出問題；使用者決定處理範圍
- 驗證：
  - 拿掉鎖時，舊版併發測試連跑 5 次都通過，證實 D 的觀察；新版連跑 3 次都失敗，有鎖時通過。
  - 完整驗證：後端 2376 個、前端 990 個測試通過；lint、typecheck、biome 通過。
  - Blind Hunter 提出 9 項：修 5、延後 1、駁回 3。
- 問題與修正：
  - AI 第一版前端判斷用 `apiError.kind === "business"`，新測試失敗才發現 403 被 `parseApiError` 歸類為 `forbidden`，改成直接比對錯誤碼。
  - AI 第一版併發測試沒有斷言先到的一方是「逾時」才繼續，Blind Hunter 指出後補上。
  - 開分支時，AI 用的 main 是舊的，查 git log 才發現，重新 fetch 後把分支重建在最新的 main 上。
- 成熟度：L4（組員審查，AI 依流程實作並用「拿掉鎖」驗證測試有效，加上審查與自動測試）
- 證據：PR #64（D 的審查與留言）；_bmad-output/implementation-artifacts/spec-6-4-followup-review.md；spec-6-4-file-report.md（Review Triage Log #24～#26）；commit 未記錄（尚未 commit）
