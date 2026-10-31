# 王閎立 的 AI 使用紀錄

格式與等級定義見 [README](README.md)。只在檔尾新增，最新的在最下面。

> 以下 7 筆由黃鉅燊的 Claude Code 於 2026-10-28 依 git 歷史與 BMAD 的 `.memlog.md`、審查紀錄補登，內容都有對應的檔案可查。**請閎立確認**：實際由其他組員操作的，搬到該成員的檔案；有數字更準確的，直接修改。

### 2026-10-14｜需求／產品簡介與 PRD｜由專案背景產出產品簡介與 PRD（FR-1～38、NFR-1～9）

- Story／範圍：規劃階段
- 工具：Claude Code ＋ bmad-product-brief、bmad-prd（陪練模式）
- 怎麼用：以 `docs/project-background.md` 為輸入，用「旅程優先」逐段問答，寫出簡介與 PRD
- AI 產出：`briefs/brief-*/brief.md`、`addendum.md`，`prds/prd-*/prd.md`（FR 都有可測結果）
- 人做了什麼：選定方案 A、主要使用者與抽籤方式；決定新增「平台管理員」角色、建立賽事的欄位
- 驗證：PRD 依 `review-rubric.md` 審查，並於 2026-10-15 回寫審查結果（`review-update-2026-10-15.md`）
- 問題與修正：原本想串遊戲 API 取得比分與 KDA，AI 查證後發現 VALORANT API 需要審核通過的 production key 加玩家授權、LoL 的 dev key 每 24 小時過期，於是調整需求
- 成熟度：L3（AI 依背景資料產出、主動查證外部限制，人在每個決策點裁示）
- 證據：`_bmad-output/planning-artifacts/briefs/`、`prds/` 與其 `.memlog.md`

### 2026-10-14｜設計／架構骨幹｜架構決策 AD-1～21 與 C、D 文件打底稿

- Story／範圍：規劃階段
- 工具：Claude Code ＋ bmad-architecture
- 怎麼用：輸入 PRD 與簡介，產出架構骨幹與課程 C（軟體設計）、D（物件設計）的打底稿
- AI 產出：`ARCHITECTURE-SPINE.md`（AD-1～21、模組依賴方向、目錄結構）、`c-d-design-groundwork.md`（類別圖、循序圖）
- 人做了什麼：採用範本的技術堆疊；確認依賴方向與交易式 outbox 等決策
- 驗證：審查關卡依序跑 lint、版本查證、對抗式審查、規格完整性檢查（`reviews/review-gate-summary.md`）
- 問題與修正：對抗式審查找出 7 個「各自守規則、合起來卻不相容」的漏洞，例如申訴送出與 worker 自動確認同時發生、worker 一筆失敗就整批回滾、公開 API 外洩個資，全部回寫成 AD-5、AD-6、AD-8、AD-10、AD-17～19
- 成熟度：L4（固定流程加多視角審查，問題在實作前就被擋下）
- 證據：`_bmad-output/planning-artifacts/architecture/`

### 2026-10-14～10-23｜設計／UX 設計｜DESIGN.md、EXPERIENCE.md（S1～S38）、Logo 與 mockup

- Story／範圍：規劃階段
- 工具：Claude Code ＋ bmad-ux
- 怎麼用：輸入簡介、PRD、架構，先整理出 32 個待釐清問題，再逐一決定
- AI 產出：外觀規範 `DESIGN.md`、38 個畫面的 `EXPERIENCE.md`、FLOW Logo（SVG）、對戰樹與場次頁的 HTML mockup
- 人做了什麼：命名 FLOW、指定「科幻流動感」的品牌感覺；選定身分切換器的資訊架構、後台用側欄
- 驗證：`validation-report.md`，以及與 PRD、架構、簡介的對照紀錄（`reconcile-*.md`）
- 問題與修正：對照時找出與上游文件的落差，記在 `reconcile-*.md` 後回寫
- 成熟度：L3（AI 產出完整規格與視覺稿，人做品牌與資訊架構決策）
- 證據：`_bmad-output/planning-artifacts/ux-designs/`

### 2026-10-15｜需求／Epic 與 Story 拆解｜7 個 Epic、46 個 Story 與驗收條件，並以多代理審查

- Story／範圍：規劃階段
- 工具：Claude Code ＋ bmad-create-epics-and-stories、bmad-party-mode（5 個 AI 角色：分析師、PM、UX、架構師、工程師）
- 怎麼用：由 PRD、架構、UX 拆出 Epic 與 Story，再讓 5 個角色從各自立場審查 `epics.md`
- AI 產出：`epics.md`（Given／When／Then 驗收條件、待決事項）
- 人做了什麼：在角色之間有爭議時裁示，例如先搶期遞補規則保留但補上說明、賽後檢舉不改名次、覆蓋率目標 90%
- 驗證：多角色審查
- 問題與修正：工程師角色抓到 Story 1.5 依賴 1.6（平台管理員帳號）的順序問題；架構師指出 6 項 PRD 回寫是開工前的阻擋項，修正後才開始實作
- 成熟度：L4（多代理互相審查，人只裁示有爭議的地方）
- 證據：`_bmad-output/planning-artifacts/epics.md`、`_bmad-output/party-mode/memories/installed/.memlog.md`

### 2026-10-16～10-28｜需求、設計／期中文件 A～D｜由 BMAD 文件產生四份交付文件與 PDF、Word

- Story／範圍：期中交付
- 工具：Claude Code（自寫排版程式）
- 怎麼用：依去年範本的章節，從 BMAD 文件改寫成 A～D 四份文件；use case 圖與泳道圖用自訂的文字語法描述，由程式畫成圖
- AI 產出：四份 Markdown；`_build/build.mjs`（產生 PDF 與 Word）、`usecase.js`、`swimlane.js`；7 張 use case 圖與 2 張泳道圖
- 人做了什麼：10/19 提出審閱意見；10/28 手動修改 Word 版，再讓 AI 把修改寫回 Markdown 與 `meta.json`
- 驗證：排版程式會列出字太小的圖（縮放比例低於 0.62）與畫圖錯誤
- 問題與修正：10/19 審閱時發現多條規則沒有定義或互相矛盾（輪空與雙方棄權、棄權計時暫停、用語不一致），一併寫回 PRD、架構、Epic 與 UX，保持一致
- 成熟度：L3（AI 產出文件與工具鏈，人審閱並決定規則）
- 證據：`docs/midterm/`、`docs/midterm/README.md`〈2026-10-19 依審閱意見修訂〉

### 2026-10-23～10-28｜程式、測試／Story 1.1～1.5｜以 bmad-build 實作專案骨架、前端外框、註冊、登入、重設密碼

- Story／範圍：1.1～1.5
- 工具：Claude Code ＋ bmad-build（spec → 實作子代理 → 3 個審查者：Blind Hunter、Edge Case Hunter、Verification Gap）
- 怎麼用：每個 Story 先由 AI 寫 spec，人核准後由子代理實作並寫測試，再交給 3 個審查者
- AI 產出：後端 6 個模組的骨架與 identity 功能、前端外框與主題、3 支 Alembic 遷移；後端 166 個測試函式、前端 23 個單元測試檔
- 人做了什麼：核准 spec；在 1.4、1.5 的 spec 寫下 Decisions（例如登入 7 天有效、不做 refresh token、重設密碼後登出其他裝置）
- 驗證：後端測試覆蓋率門檻 85%（`pyproject.toml`），加上 mypy、ty、ruff、biome、tsc
- 問題與修正：審查找出的問題記在各 spec 的 Review Triage Log；1.1、1.2、1.3、1.5 各有一個「Code Review 修正」commit；延後處理的 10 項記在 `deferred-work.md`
- 成熟度：L4（固定流程、多審查者、自動測試，人在 spec checkpoint 決策）
- 證據：commit `b20d0dd`～`338742d`，`_bmad-output/implementation-artifacts/spec-1-*.md`

### 2026-10-28｜專案管理與流程／範圍調整｜期中範圍：30 個主線 Story，擱置 15 個

- Story／範圍：全專案
- 工具：Claude Code ＋ bmad-correct-course
- 怎麼用：說明時程限制，請 AI 分析擱置哪些 Story 影響最小，以及每個主線 Story 要怎麼調整
- AI 產出：`sprint-change-proposal-2026-10-28.md`；`epics.md` 的〈期中範圍〉一節與 23 個 Story 的「期中版調整」；Epic 1～7 的 context；CONTRIBUTING 第 6 節的分工、時程與交接期限
- 人做了什麼：選定 6.5 取消資格、2.2 只開放校園賽、6.4 入口、1.8 刷新方式等規則
- 驗證：成功標準是每個主線 Story 的 spec 都不要求實作擱置的功能
- 問題與修正：AI 發現擱置 4.2 後，原版 4.1 只能在報名截止前抽籤，流程會卡住，於是放寬；也發現 CONTRIBUTING 原本的 6.3 規則與架構 AD-7 不一致，已更正
- 成熟度：L4（AI 做影響分析並找出流程卡點，人做取捨）
- 證據：`_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-28.md`、commit `5aa5e0e`、`50a3bdc`

### 2026-10-29｜程式、測試／Story 1.7｜以 bmad-build 實作「申請成為主辦方」（S15、Status badge）

- Story／範圍：1.7
- 工具：Claude Code（Opus 5.5）＋ bmad-build（spec → 實作子代理；step-04 審查依使用者決定略過）
- 怎麼用：輸入「/bmad-build 1.7 有問題直接選最推薦那個」，由 AI 依 epic-1 context 寫 spec、自行選定推薦方案並記進 Decisions，再交給實作子代理
- AI 產出：spec 一份（Decisions 9 項）；後端 `OrganizerApplication` 資料表、遷移 `c7e2a4d9b8f1`（部分唯一索引限制每個帳號只有一筆待審核）、2 支 API；前端 S15 頁面、全站共用的 `StatusBadge`、`formatDateTime`、身分切換器入口；commit 共 23 個檔案、新增 1971 行。測試：後端 `test_organizer_application.py` 18 個測試函式（參數化後 24 個），前端新增 `status-badge` 3 個、`organizer-apply` 12 個，並在 `identity-switcher` 增補
- 人做了什麼：授權 AI 直接採用推薦方案；決定不再每個 Story 各自跑 code review，改在最後統一審查（寫進 spec 的 Decisions）
- 驗證：合併最新 `main` 後重跑全部檢查：後端 278 個測試通過、覆蓋率 95%；mypy、ty、ruff 通過；前端 21 個檔案 190 個測試通過，biome、tsc 通過；Alembic 只有一個 head；另以瀏覽器手動走過 S15
- 問題與修正：單元測試全部通過，S15 在實際瀏覽器卻崩潰。原因是產生的 client 會把後端的 `null` 回應換成 `{}`，AI 寫的程式與測試都假設會收到 `null`，所以測試測不到。手動檢查時才發現，改成以有沒有 `id` 判斷，測試也照實改用 `{}` 模擬，並寫進 spec 的 Implementation Notes 提醒後續 Story。另外子代理自己列出兩個沒處理的風險：遷移一致性測試可能不比對部分索引的 WHERE 條件；`school_id` 整個缺少時的 422 訊息是 pydantic 的英文預設訊息
- 成熟度：L3（AI 依 spec 產出並自動驗證，但這次略過多審查者，`null` 問題是靠人手動檢查才發現）
- 證據：commit `d3b77d4b956da8f563f174647a95db6cb7296f86`、`_bmad-output/implementation-artifacts/spec-1-7-apply-to-be-organizer.md`

### 2026-10-29｜需求、設計／Story 1.8 spec｜由 epic context 與程式調查寫出審核主辦方申請的 spec

- Story／範圍：1.8
- 工具：Claude Code（Opus 5.5）＋ bmad-build（調查子代理 → spec → checkpoint）
- 怎麼用：輸入「/bmad-build 1.8」，AI 讀 epic-1 context 與 1.7 spec，派子代理調查 identity 模組、前端元件與 UX 文件，再寫 spec 並列出待決問題
- AI 產出：`spec-1-8-review-organizer-applications.md`（I/O 矩陣 8 列、Decisions 6 項、Tasks 14 項）；訂下全專案第一個分頁 API 格式 `{items,total,page,page_size}`
- 人做了什麼：回答 2 個待決問題：核准後的「主辦方後台」身分與 S25 佔位頁在 1.8 做（選 A）、保留完整 spec 不拆分；核准 spec
- 驗證：AI 依 Ready for Development 標準自查；調查時比對 B 的 2.1 分支，沿用 `/admin/` 路徑前綴，並避開 B 也會新增的 `backend/tests/helpers.py`
- 問題與修正：AI 發現 UX 要求核准後連到 S25，但 epics 把 S25 外框排在 B 的 2.2，兩份文件的分工有落差，沒有自己假設，列成待決問題交給人決定；spec 粗估約 4,300 tokens，超過建議的 1,600，也交給人決定
- 成熟度：L3（AI 依既有規格與程式產出 spec，跨人分工的取捨由人決定）
- 證據：`_bmad-output/implementation-artifacts/spec-1-8-review-organizer-applications.md`

### 2026-10-29｜程式、測試／Story 1.8｜以 bmad-build 實作 S35 審核頁、後台版面、Data table 與確認對話框

- Story／範圍：1.8（分支 `story/1-8`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理；step-04 審查依使用者決定略過）
- 怎麼用：spec 核准後交給沒有對話脈絡的實作子代理，只給 spec；主對話再讀 diff 逐項核對任務、I/O 矩陣與驗收條件，並重跑全部檢查
- AI 產出：33 個檔案、新增 3748 行。後端 3 支平台管理 API、唯一的狀態轉換函式、主辦方身分；前端 `ConfirmDialog`、`DataTable`、`BackofficeLayout`、`EmptyState`、`AccountGate`、S35、S15 的核准與退回重送、S25 佔位頁。測試：後端新檔 21 個測試函式（含兩條真實連線的併發測試）；前端新增 4 個測試檔，並補 `organizer-apply` 的情境
- 人做了什麼：核准 spec；決定不跑逐 Story 的 code review
- 驗證：主對話重建容器後重跑：後端 310 個測試通過（1.7 時 278）、覆蓋率 95%；mypy、ty、ruff 通過；前端 25 個檔案 228 個測試通過（1.7 時 190），build、typecheck、biome 通過；Alembic 單一 head；I/O 矩陣 8 列都有通過的測試；子代理另以瀏覽器在 375 px 檢查沒有橫向捲軸
- 問題與修正：子代理發現 shadcn `Sidebar` 的手機斷點寫死 768 px、又是 fixed 定位會蓋住頂欄，改成自己排版；但也因此把手機版開側欄的按鈕放在內容區，與 spec「從頂欄開啟」不同，子代理自己寫進 Implementation Notes，主對話讀 diff 時確認並交給人決定。另外 1.7 的身分切換器測試原本預期 `/admin/applications` 是 404，實作後失效，已改成以平台管理員進入 S35
- 成熟度：L3（AI 依 spec 實作並自動驗證；這次略過多審查者，偏離 spec 的地方靠讀 diff 找出）
- 證據：spec 同上；尚未 commit

### 2026-10-29｜需求、設計／Story 4.6 spec｜在上游 API 未完成時，把對戰樹拆成可先做的第一階段

- Story／範圍：4.6（分支 `story/4-6`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（調查子代理 → spec → checkpoint）
- 怎麼用：輸入「/bmad-build STORY4.6 且不要做 BMAD-CODEREVIEW」，AI 讀 epic-4 context、D 已合併的 competition 介面約定（PR #3）與 D 各分支的做法，派子代理整理 DESIGN.md、EXPERIENCE.md 與對戰樹示意圖的規格
- AI 產出：`spec-4-6-bracket-tree-view.md`（I/O 矩陣 12 列、Decisions 8 項）；指出 4.6 依賴的公開 API（D 的 4.1）與 S2（B 的 2.4）都還沒做，提議照 D 的 5.1、5.3 分兩階段
- 人做了什麼：回答 3 個待決問題（只做第一階段、加開發模式預覽頁、保留完整 spec）並核准 spec；決定不跑 code review
- 驗證：AI 依 Ready for Development 標準自查；比對 D 的分支，讓日期格式檔 `match-time.ts` 與 D 的版本完全相同以免合併衝突
- 問題與修正：調查時發現 1.8 與 D 的 5.3 都新增了 `alert-dialog.tsx` 與同一個套件，合併時會衝突，提醒使用者先和 D 協調；AI 沒有自行假設上游 API 的完成時間，而是把「等或先做」列成待決問題
- 成熟度：L3（AI 依介面約定與既有做法規劃，跨人依賴的取捨由人決定）
- 證據：`_bmad-output/implementation-artifacts/spec-4-6-bracket-tree-view.md`、`_bmad-output/implementation-artifacts/contracts/competition.md`

### 2026-10-29｜程式、測試／Story 4.6 第一階段｜以 bmad-build 實作對戰樹元件、版面計算與輪詢

- Story／範圍：4.6 第一階段（分支 `story/4-6`）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理；依使用者決定不做 code review）
- 怎麼用：spec 核准後交給沒有對話脈絡的實作子代理；主對話讀 diff、確認 `match-time.ts` 與 D 的檔案 blob 相同、逐列對照 I/O 矩陣，並重建容器重跑全部檢查
- AI 產出：19 個檔案、新增 2346 行。版面計算純函式、場次卡與標記、對戰樹（SVG 連接線）、輪詢 hook（5 秒、背景暫停、連續 3 次失敗）、連線中斷 banner、尚未抽籤畫面、`update-flash` 動畫、假資料產生器、開發模式預覽頁 `/dev/bracket`；4 個測試檔、50 個測試（含參數化）
- 人做了什麼：核准 spec 與範圍
- 驗證：前端 29 個檔案 278 個測試通過（4.6 前 228），build、typecheck、biome 通過；後端 310 個測試通過；I/O 矩陣 12 列都有通過的測試；子代理在預覽頁實測 1280px 32 隊沒有橫向捲軸、375px 只有對戰樹容器可捲動，正式 build 的預覽頁只剩 404 元件
- 問題與修正：子代理發現同一張卡連續兩次變動時 class 不變、動畫不會重播，改用重新掛載並加測試；也發現 TanStack Query 在假時鐘下通知會晚一輪，測試期間改用 `queueMicrotask`。另有三個版面常數（卡高 67、首卡上方 19、季軍賽距決賽 83）與 walkover 不顯示比分是 AI 依示意圖與 UX 文件自行判斷，記在 Implementation Notes 交給人確認
- 成熟度：L3（AI 依 spec 實作並自動驗證，未經多審查者）
- 證據：spec 同上；尚未 commit

### 2026-10-30｜需求、設計／spec｜Story 5.8：場次頁觀眾檢視的 spec

- Story／範圍：5.8
- 工具：Claude Code（Opus 5.5）＋ bmad-build（Explore 子代理整理 UX）
- 怎麼用：`/bmad-build 5.8`。子代理先整理 S4 的 UX 規定，涵蓋 EXPERIENCE、DESIGN、mockup 與 contract；AI 依此寫 spec，再把文件沒定義的地方列成問題讓人選
- AI 產出：`spec-5-8-match-page-results.md`，包含 16 列 I/O 矩陣、7 項 Decisions、12 個工作項目。這份 spec 也提議了公開單場 API 的形狀 `PublicMatchDetail`，要請 D 補進 contract
- 人做了什麼：回答 4 個問題：
  - 範圍：相依的 Story 還沒做的部分先用假資料，把 5.8 完整做出來
  - 申訴期只在已確認後才套用勝敗樣式
  - 沒有比分時顯示隊名＋「—」＋標記
  - `win_loss` 型態寫「勝／負」
- 驗證：子代理確認 contract 沒有定義公開的單場 API，也沒有各局的形狀，列為第二階段要補的項目
- 問題與修正：AI 原本規劃只做元件，S4 路由留到之後。使用者要求用假資料把 5.8 做完整，於是改成建立正式的 S4 路由與「場次卡點了進入 S4」，資料改由同一個資料來源函式取得，正式 build 時顯示 404
- 成熟度：L3（AI 依 UX 文件產出 spec，並找出文件沒有定義的地方交給人決定）
- 證據：`_bmad-output/implementation-artifacts/spec-5-8-match-page-results.md`

### 2026-10-30｜程式、測試／程式生成｜Story 5.8：S4 路由、觀眾檢視元件與單場輪詢

- Story／範圍：5.8
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：子代理只讀 spec 實作；主對話讀 diff，逐列檢查 I/O 矩陣，重建 frontend 後重跑全部檢查
- AI 產出：
  - 新增 11 個原始檔：S4 路由、4 個區塊元件與組合元件、`match-status`、`match-source`、`use-match-polling` 等
  - 修改 4 個檔案：場次卡可點、抽出共用的狀態對照與失敗計數
  - `/dev/match` 預覽頁
  - 新增 8 個測試檔，`bracket-match-card` 測試補上連結的案例
- 人做了什麼：在 checkpoint 核准 spec；略過 code review
- 驗證：
  - 前端單元測試 37 個檔案、354 個通過，新增 76 個
  - build、typecheck、biome 都通過
  - 正式 build 的 `dist/assets` 不含假資料
  - 後端 310 passed
  - 子代理用瀏覽器量過：1280px 兩欄，375px 單欄、沒有橫向捲軸
- 問題與修正：
  - S3 路由還不存在，TanStack `Link` 過不了型別檢查，返回連結先改成一般的 `<a>`，記在 `deferred-work.md`
  - 子代理把「申訴期不套勝敗樣式」解讀成只限系列比分，各局列表照樣套用勝敗樣式，這點寫在 Implementation Notes 給人確認
  - 實作途中 Docker Desktop 停止，人提出後由 AI 重新啟動並重建容器
- 成熟度：L3（AI 依 spec 產出並自動驗證，這次沒有多審查者）
- 證據：`frontend/src/features/competition/`、`frontend/src/routes/tournaments/$tournamentId/matches/$matchId.tsx`；尚未 commit

### 2026-10-30｜程式、測試／程式生成｜Story 5.2：S4 申訴期區塊（截止時間＋倒數插槽）

- Story／範圍：5.2（S4 部分，在 `story/5-8` 實作）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（實作子代理）
- 怎麼用：Countdown 元件是 B 的 2.4，還沒做。AI 提出三個選項，人選了「先顯示截止時間，再留一個倒數插槽」。AI 依 EXPERIENCE.md〈場次頁（S4）〉寫 spec，交給子代理實作，主對話讀 diff 驗收
- AI 產出：
  - 新增 `MatchAppealWindow.tsx`
  - `PublicMatchDetail` 加上 `appeal_deadline`，假資料一併補上
  - `MatchSpectatorView` 重排：`< lg` 用 `display: contents` 加 `order`，把申訴期排在比分與各局之間；`≥ lg` 放在右欄最上方。每個區塊只渲染一次
  - 13 個測試
  - `deferred-work.md` 新增一項
- 人做了什麼：選擇插槽做法，不重做 B 的元件
- 驗證：前端 38 個測試檔、367 個測試通過，新增 13 個；build、typecheck、biome 都通過；子代理在瀏覽器量過 1280px 與 375px 的位置，沒有橫向捲軸
- 問題與修正：子代理沒有用 grid area，因為兩欄會共用列高，左欄會撐出空白，改用 `display: contents`。它也指出手機寬度時 DOM 順序和畫面順序不一致，Epic 6 加「提出申訴」按鈕時要再確認焦點順序，已寫進 Implementation Notes
- 成熟度：L3（AI 依 UX 文件產出並自動驗證，人做範圍取捨；這次沒有多審查者）
- 證據：`_bmad-output/implementation-artifacts/spec-5-2-appeal-window-display.md`、`frontend/src/features/competition/MatchAppealWindow.tsx`；尚未 commit

### 2026-10-31｜程式、測試／依審查修正｜Story 5.8：依 D 的審查修正場次卡可及名稱、首次載入失敗與 flash 判斷

- Story／範圍：5.8（`story/5-8`）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：把 D 的審查意見貼給 AI。AI 先讀被指出的程式與測試，確認問題成立，再修正、補測試，最後重建容器跑全部檢查
- AI 產出：
  - `BracketMatchCard.tsx`：新增 `matchCardAccessibleName()`，連結帶完整名稱，article 包成連結時不帶 `aria-label`
  - S4 路由：第一次載入就失敗時直接顯示連線中斷橫幅
  - `isMatchScoreChanged` 加比結果、勝隊與各局
  - 測試：`bracket-match-card` 改用 `toHaveAccessibleName` 並補 2 個案例，`use-match-polling` 補 2 個，新增 `match-route-error.test.tsx`
  - spec 的 Review Triage Log、`deferred-work.md` 一項（walkover 空缺方，等 PR #13 的約定）
- 人做了什麼：D 審查並找出問題；使用者決定把審查意見交給 AI 修
- 驗證：前端單元測試 39 個檔案、371 個通過（新增 4 個）；typecheck、biome（157 個檔案）通過；改動的檔案都是 LF
- 問題與修正：
  - 10/30 實作時 AI 在 Implementation Notes 寫「article 的 `aria-label` 不變，所以連結的可及名稱包含標頭與隊名」，這是錯的：依 accname 規則，article 的 `aria-label` 會取代內容，連結名稱只剩「M3」
  - 當時的測試用 `toHaveTextContent` 檢查文字，不是檢查可及名稱，所以沒抓到；當時也略過 code review。這次由 D 人工審查發現
  - 修正後改用 `toHaveAccessibleName`，直接驗證讀螢幕軟體聽到的整句
- 成熟度：L3（人審查找出問題，AI 修正並自動驗證）
- 證據：`_bmad-output/implementation-artifacts/spec-5-8-match-page-results.md` 的 Review Triage Log；尚未 commit
### 2026-10-31｜程式、測試／依審查修正｜Story 4.6：依 D 的審查改成 bye_a／bye_b、walkover 空缺方與 404 輪詢

- Story／範圍：4.6（`story/4-6`）
- 工具：Claude Code（Opus 5.5）
- 怎麼用：把 D 的審查意見貼給 AI，AI 先讀被指出的型別、假資料、場次卡與輪詢 hook 確認問題，再修正並補測試，重建 frontend 後跑全部檢查
- AI 產出：
  - `bracket-types.ts` 的 `bye_side` 改成 `bye_a`、`bye_b`，假資料、場次卡、逐場比較跟著改
  - 場次卡：已確認的 walkover 空缺方即使還帶著來源也顯示「—」＋「輪空」
  - `useBracketPolling`：新增 `BracketNotFoundError`，404 不計入連續失敗、照常輪詢，回傳 `notFound`
  - 測試：5、9 隊版面各 1 個、場次卡 3 個、輪詢 2 個
  - spec 的 Review Triage Log 與 Design Notes
- 人做了什麼：D 審查並找出兩方輪空與 walkover 空缺方的問題、決定改約定；使用者決定交給 AI 修
- 驗證：前端單元測試 29 個檔案、285 個通過（新增 7 個）；typecheck、biome、build 通過；改動的檔案都是 LF
- 問題與修正：
  - 10/29 實作時 AI 照當時的約定用 `bye_side`，假資料產生器其實已經算出兩方都輪空（`byeA`、`byeB`），卻用 `byeA ? "a" : byeB ? "b" : null` 丟掉 b 方；測試用的隊數（2、3、4、8、13、16、32）都不會出現兩方輪空，所以沒抓到。D 用 9 隊推算第二輪才發現
  - 假資料在 walkover 後把下一場的 source 清成 null，剛好讓「確定沒有隊伍」的畫面正確，遮住了 API 若保留 source 時會顯示成待定的問題
  - 這次的修正改了 4.6 的檔案，但 `story/5-8` 已經把同一段邏輯搬到 `match-status.ts`，合併 `story/4-6` 進 `story/5-8` 時要手動解衝突
- 成熟度：L3（人審查找出問題，AI 修正並自動驗證）
- 證據：`_bmad-output/implementation-artifacts/spec-4-6-bracket-tree-view.md` 的 Review Triage Log；尚未 commit
