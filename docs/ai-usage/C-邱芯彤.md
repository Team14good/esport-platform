# 邱芯彤 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

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
