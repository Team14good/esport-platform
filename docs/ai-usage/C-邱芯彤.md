# 邱芯彤 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

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
