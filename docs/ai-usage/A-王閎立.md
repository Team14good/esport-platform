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

### 2026-10-30｜設計、程式／程式生成｜Story 7.1 第一階段：示範資料腳本骨架與示範帳號

- Story／範圍：7.1 第一階段（分支 `story/7-1`，PR 未開）
- 工具：Claude Code（Opus 5.5）＋ bmad-build（spec → 實作子代理 → 主對話驗收）
- 怎麼用：AI 先查出上游 tournaments、registration、competition 的 service 在 main 上還是空的，建議只做第一階段（共用種子腳本骨架＋示範帳號），寫 spec 後由子代理依 spec 實作
- AI 產出：`backend/app/demo_data/` 套件（3 個檔案，含各模組新增步驟的擴充說明）、identity 新增 `ensure_demo_account`、`find_account_id_by_email`；設定 `DEMO_PASSWORD`、`DEMO_EMAIL_DOMAIN` 與 README 示範帳號表；6 個測試（涵蓋 spec I/O 表四種情境）
- 人做了什麼：決定先做第一階段、從 `origin/main` 開分支；決定 Email 用單一網域變數、示範帳號屬「國立中央大學」、保留超過 1,600 tokens 的 spec；依個人設定跳過 Story 內的多代理審查，最後統一 code review
- 驗證：在全新 volume 的另一個 compose 專案驗證：主辦方帳號登入成功、`/accounts/me` 的 `email_verified`、`is_organizer` 為 true；帶密碼重啟後 `account` 表維持 5 筆並記錄略過；不帶 `DEMO_PASSWORD` 重啟時只略過示範資料。`scripts/test.sh` 259 passed、總覆蓋率 95%，`scripts/lint.sh` 全數通過
- 問題與修正：(1) 子代理新增了 spec 沒列的公開函式 `find_account_id_by_email`，主對話讀 diff 時發現；因帳號已存在時仍要把 id 交給後續步驟，保留並記在 spec 的 Implementation Notes。(2) 子代理改了測試檔格式後沒有重跑測試，主對話重跑才確認通過。(3) 主對話第一次驗證直接啟動使用者本機的 compose，因為本機資料庫已套用 main 上沒有的 1.7 遷移（`c7e2a4d9b8f1`），backend 起不來，還和驗證專案搶連接埠；改為停掉使用者的 compose，用獨立的 compose 專案驗證，沒有動到使用者的資料庫
- 成熟度：L3（AI 依 spec 產出並自行驗證，人在 checkpoint 決策；這次沒跑多代理審查）
- 證據：`_bmad-output/implementation-artifacts/spec-7-1-demo-seed-data.md`；commit 未建立
