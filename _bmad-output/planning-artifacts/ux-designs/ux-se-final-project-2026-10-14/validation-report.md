# Validation Report — FLOW (se-final-project)

- **DESIGN.md:** `C:\Users\hw453\Desktop\se-final-project\_bmad-output\planning-artifacts\ux-designs\ux-se-final-project-2026-10-14\DESIGN.md`
- **EXPERIENCE.md:** `C:\Users\hw453\Desktop\se-final-project\_bmad-output\planning-artifacts\ux-designs\ux-se-final-project-2026-10-14\EXPERIENCE.md`
- **Run at:** 2026-10-15T11:36:03+08:00

## Overall verdict
這組 spine 可以直接交給下游當契約：四條 UJ 都有具名主角、編號步驟、高潮與例外；所有色彩 token 都有淺／深 hex 成對值，且與 `.working/flow-logo-and-themes-1.html` 的 T1 註解完全一致；38 個 surface 都對到 FR，DESIGN.md 章節順序合乎規格。主要風險集中在「實作時會撞牆」的三處：品牌 `accent` 與 shadcn 語意 `--accent` 同名卻宣稱一一對應、shadcn 必要槽位沒補齊（`card-foreground`、`popover-foreground`、`secondary*`、`sidebar-*`），以及 UX 追加功能（忘記／重設密碼、重寄驗證信、移除隊員、轉讓隊長）在架構沒有對應方法、也沒列入「待回補上游」。沒有 critical；其餘多為 reconcile 已提出但尚未落地的按鈕停用條件與對戰樹邊界狀態。

本次只跑 rubric walker（使用者於 Reviewer Gate 選擇，見 memlog）。不列為問題的使用者決定：無障礙延後、不設 WCAG 等級、未驗證對比；範圍收斂；身分切換器取代統一儀表板；後台側欄；深色預設。mockups／wireframes 與 `.working/` 資產提升留待 Finalize，視覺參考類別未加重判。工作區內四份 `reconcile-*.md` 為輸入對照報告，不是審查 lens；其必修項已依 memlog 回寫，未處理的 b 項已併入下方 State 與 Inheritance 類別。

## Category verdicts
- Flow coverage — adequate
- Token completeness — adequate
- Component coverage — adequate
- State coverage — adequate
- Visual reference coverage — adequate
- Bloat & overspecification — adequate
- Inheritance discipline — adequate
- Shape fit — strong

## Findings by severity

### Critical (0)

無。

### High (3)

**[Token completeness]** — 品牌 `accent` 與 shadcn 語意 `--accent` 同名，卻宣稱 token 與 shadcn CSS 變數一一對應（§ DESIGN〈Colors〉「與 shadcn accent 的衝突」；frontmatter `accent`／`accent-dark`）  
照字面鏡像會讓 DropdownMenu、Command、Select 與 ghost／outline Button 的 hover 全部變成品牌紫——正是同節 [ASSUMPTION] 規則禁止的結果；要守規則就得逐一改寫 shadcn 元件 class，每次 `shadcn add` 都會回退。  
Fix: 品牌紫改名為 `brand`（`--brand`／`brand-dark`），shadcn `accent`／`accent-foreground` 改填 `muted`／`foreground` 的值；同步更新所有 `{colors.accent}` 引用（logo-lockup、賽程已公布徽章、Identity switcher、EXPERIENCE〈賽事狀態〉）。

**[Token completeness]** — 宣稱「補齊 shadcn 必要槽位」，仍缺 `card-foreground`、`popover-foreground`、`secondary`、`secondary-foreground` 與 `sidebar-*`（§ DESIGN frontmatter `colors` 第 41～53 行；〈Colors〉補齊槽位）  
Card、Popover、DropdownMenu 文字與 Button／Badge secondary variant 會用到；若採用 shadcn Sidebar 還缺 8 個 `sidebar-*`。下游只能沿用 shadcn 中性灰（與 T1 藍調不合）或自行發明。  
Fix: 每個槽位補淺／深 hex，或在 frontmatter 註明別名（`card-foreground` = `foreground`、`secondary` = `muted`、`sidebar` = `card`、`sidebar-accent` = `muted`、`sidebar-primary` = `primary`）。

**[Inheritance discipline]** — UX 追加功能在架構無方法、也未列入「待回補上游」（§ EXPERIENCE Open Questions #9、需求覆蓋表；reconcile-architecture C3、reconcile-prd C3）  
忘記／重設密碼（S8、S9）、重寄驗證信（S7）、移除隊員與轉讓隊長（S17，牽涉 `MemberRole` 與 AD-10 `ensure_captain`）在 D-1 `IdentityService`、D-3 `RegistrationService` 都沒有方法，PRD 也無對應 FR；「已決定、待回補上游」只列直播連結。照 spine 寫故事會做出沒有後端的畫面。  
Fix: 把四項加入「已決定、待回補上游」，逐項寫明回補文件與位置（PRD 新 FR 或 §7 註記、D-1／D-3 方法、Epic），可依範圍收斂原則標優先序。

### Medium (10)

**[Flow coverage]** — 主辦方不可逆的事後變更（FR-10 取消賽事、FR-23 改場次時間、FR-9 延長報名）沒有旅程或例外段（§ EXPERIENCE〈Key Flows〉UJ-1 失敗段；Open Questions #4）  
UJ-1 例外只用一句帶過「延長報名（S28）或取消賽事」；這些動作會通知所有隊伍或裁判，FR-23 還有「已報到後不可改」的限制。  
Fix: 在 UJ-1 例外補 2～3 行：S27「取消賽事」→ AlertDialog（寫後果）→ S2 橫幅；S30 改時間 → 已報到場次停用並說明。

**[Token completeness]** — `fontFamily: 'sans'`／`'mono'` 的實際字體堆疊只寫在 YAML 註解（§ DESIGN frontmatter 第 55～57 行）  
YAML 解析器會丟掉註解，token 消費端只拿到字串 `sans`。  
Fix: 新增 `fontFamilies:` 區塊（或直接在每組 typography 寫完整堆疊），讓 `sans`／`mono` 可解析。

**[Component coverage]** — S17 名單完成度清單與 S4 報到區沒有元件列（§ EXPERIENCE〈報名狀態〉組隊中；〈場次狀態〉待開打・可報到）  
兩者分別是 UJ-2（FR-13 送出門檻「逐項列出缺什麼」）與 UJ-3（雙方報到狀態、報到鈕、倒數）的核心操作。  
Fix: 兩份 spine 各加 `Roster list`（名稱、遊戲 ID、段位、截圖已上傳、完成勾；隊長端移除／轉讓入口）與 `Check-in panel`（兩隊狀態、按鈕、倒數）的視覺與行為列。

**[Component coverage]** — 頁頂橫幅、段位截圖檢視器、冠亞季標記未規格化（§ EXPERIENCE〈State Patterns〉對戰表標記；〈對戰樹〉版型；UJ-1 步驟 5）  
「此賽事已取消」「連線中斷，正在重試」「申請成為主辦方」橫幅、S29 段位截圖檢視器、冠軍／亞軍／季軍標記與置頂區都有行為描述但無元件；Bracket mark tag 只定義四種標籤。  
Fix: 橫幅指定為 shadcn `Alert`（各用哪個 variant）；段位截圖檢視器＝`Dialog` 內圖片＋隊員切換；冠亞季的 token 與位置寫進 Bracket 元件。

**[Component coverage]** — Countdown 變體在兩份文件不一致（§ DESIGN〈Components〉Countdown、frontmatter `countdown`；EXPERIENCE〈倒數與時間〉表）  
DESIGN 寫數字預設 `status-appeal`、固定有進度條；EXPERIENCE 另有報名截止 24 小時切色、申訴處理期限 `{colors.destructive}`，且只有申訴期寫「＋進度條」。  
Fix: 在 DESIGN Countdown 列出 tone 變體（muted／live／appeal／destructive）並決定進度條是否只在申訴期出現；EXPERIENCE 表只引用變體名。

**[State coverage]** — 對戰樹邊界狀態缺漏：雙方棄權、無季軍賽（§ EXPERIENCE〈對戰樹〉版型、〈場次狀態〉；reconcile-prd b1、b2）  
FR-25 雙方皆未報到（兩隊淘汰、下一輪輪空；準決賽時另一場勝隊直接成冠軍、季軍賽取消）；FR-20 正取少於 4 隊不產生季軍賽，但〈對戰樹〉假設季軍賽固定在決賽下方。  
Fix: 場次卡加「雙方棄權」呈現（兩列淘汰灰＋棄權標籤、下一輪顯示輪空）；寫明無季軍賽時不顯示該卡、置頂區只列冠亞軍。

**[State coverage]** — 隊伍搜尋沒有零結果與「隊伍不在對戰表上」狀態（§ EXPERIENCE〈對戰樹〉隊伍搜尋）  
搜尋是 UJ-2、UJ-4 的高潮；候補、撤回或尚未抽籤時的搜尋結果未定義。  
Fix: 補零結果文案（例：「對戰表上沒有符合的隊伍。」）與尚未抽籤時搜尋框停用或隱藏。

**[State coverage]** — FR 規定的按鈕停用條件未落到介面（§ S4、S2、S30、S28、S23；reconcile-prd b3～b5、reconcile-architecture b1）  
FR-30 每隊每場只能申訴一次；FR-32 不能檢舉自己的隊伍；FR-23 已報到後不可改時間；FR-9 抽籤後 S28 只剩唯讀；`RefereeInvitation.expires_at` 使 S23 缺「已過期」原因。  
Fix: 在對應 surface 的 State Patterns 各加一列：停用＋一句原因。

**[State coverage]** — Score entry panel 存檔模型不明（§ EXPERIENCE〈Component Patterns〉Score entry panel；UJ-3 步驟 4）  
「每局即時出現在 S4（輪詢）」意味每局即存伺服器，「確認前可改任何一局、預覽即時重算」又像本機草稿；兩種解讀導出不同 API 與 NFR-1 併發處理。  
Fix: 明寫「每局送出即存伺服器；修改某局＝更新該局；確認系列結果才鎖定」或相反。

**[Visual reference coverage]** — 四個視覺連結都指向 `.working/`，Finalize 提升資產後會失效（§ DESIGN〈Brand & Style〉logo 表與第 224 行）  
比較稿也含已否決的 L1／L3／L4 與 T2～T4。  
Fix: Finalize 時把三個 SVG 移到正式資產資料夾並改寫連結；比較稿另存只含 L2＋T1 的版本，或在連結旁註明僅 L2、T1 區塊有效。

### Low (9)

**[Token completeness]** — 部分 component token 使用無法解析的速記；淺色背景光暈沒有 token（§ DESIGN frontmatter `status-badge`、`button-primary.glow-dark`、`bracket-match-card-live`、`app-backdrop-dark`）  
`'C 15%'`、`'0 0 0 1px primary/60%'`、`'{colors.status-live} 55%'` 等無法由 resolver 展平；淺色模式 `primary` 8% 光暈只寫在 prose。  
Fix: 改成 `color-mix` 形式或拆成 `{colors.x}`＋`opacity` 兩欄；補 `app-backdrop-light`。

**[Component coverage]** — 更新閃光是第四種發光，與「同視窗發光 ≤ 3 種」衝突（§ EXPERIENCE〈通用狀態〉輪詢重抓；DESIGN〈Elevation & Depth〉）  
輪詢有變動的場次卡以 `{colors.primary}` 光環閃一次。  
Fix: 列為明確例外，或改用非發光的底色淡入。

**[State coverage]** — 缺少數個空狀態與失效狀態（§ EXPERIENCE〈通用狀態〉）  
S25 尚無賽事、S31 尚無已接受裁判、S35 無待審核申請、S2「正取隊伍」分頁在分配前、S9 重設連結過期或無效。  
Fix: 在〈通用狀態〉表補五列，沿用「一句事實＋一個下一步」。

**[Visual reference coverage]** — EXPERIENCE 沒有任何構圖參考（§ EXPERIENCE〈對戰樹〉、〈Responsive & Platform〉）  
S3 對戰樹（連接線、搜尋路徑、橫向捲動）、S4 兩欄、S17 報名頁幾何最複雜。  
Fix: Finalize 關鍵畫面優先做 S3（桌機＋375 px＋搜尋命中）、S4、S17，並在對應段落加「→ Composition reference」行。

**[Bloat & overspecification]** — FR-22 頂替規則在 EXPERIENCE 重述三次（§ 〈對戰樹〉場次卡、UJ-1 例外、UJ-2 例外）  
與文件開頭「需求內容不在此重述」相違；上一輪 reconcile 的實質衝突正是這段重述漂移所致。  
Fix: 只在〈對戰樹〉保留一次（寫畫面呈現），旅程改為「依 FR-22 調整（見〈對戰樹〉）」。

**[Bloat & overspecification]** — DESIGN〈Colors〉表格重列所有 hex（§ DESIGN〈Colors〉）  
與 frontmatter 重複，改色要改兩處。  
Fix: 表格保留用途／不用於，hex 欄改為只引用 token 名，或註明以 frontmatter 為準。

**[Bloat & overspecification]** — IA「旅程」欄的缺口標記與 Open Questions 1～8 重複（§ EXPERIENCE〈Information Architecture〉）  
同一份清單寫兩處。  
Fix: 擇一保留。

**[Inheritance discipline]** — Status badge「文字＝PRD 狀態名原字」與介面標籤矛盾（§ EXPERIENCE〈Component Patterns〉Status badge；DESIGN frontmatter `status-badge`）  
State Patterns 使用組隊中、已送出・待分配、待開打・可報到、候補第 N 位；DESIGN 的 C 清單也沒有賽程已公布用的 `{colors.accent}`。  
Fix: 改為「PRD 狀態名，或 State Patterns 表中標示的介面標籤」，並把 `accent`（或改名後的 `brand`）加入 C 清單。

**[Inheritance discipline]** — 輪詢超出 AD-14 範圍；相對時間依賴架構沒有的 `created_at`（§ EXPERIENCE〈通知〉、〈倒數與時間〉；reconcile-architecture C4、C6）  
未讀數每 30 秒、倒數到期後任意頁每 5 秒重抓最多 2 分鐘；`Notification` 無 `created_at`。  
Fix: 列入待回補上游或 Open Questions，並提醒 NFR-2 壓測納入這些輪詢。

## Mechanical notes
- 元件名稱漂移：DESIGN「Top nav / Sidebar nav item（active）」vs EXPERIENCE「Top nav / Sidebar nav」；「Button（primary）」全形括號 vs「Button (primary)」半形；frontmatter key `identity-switcher-trigger`、`nav-item-active` 與 prose 名稱不同步。
- Open Questions #7（UJ-3 沒寫小芸如何找到被指派場次）已過時：UJ-3 步驟 2 已寫「收到通知 → S13，該場在列」。
- Open Questions #2 可註明只缺 S7「重寄驗證信」分支（S7 本身已在 UJ-1、UJ-2 落地）。
- DESIGN frontmatter 無 `sources`（規格不要求）；兩份文件 `status: draft`、`updated: 2026-10-15` 一致。
- 兩份 spine 無 Mermaid 圖，無語法問題。
- `.working/` 三個 SVG 的 hex 與比較稿 T1 註解的 15 組淺／深值，與 DESIGN frontmatter 完全一致。
- `reconcile-*.md` 四份為輸入對照報告（非審查 lens）；其必修項已依 memlog 回寫，未處理的 b 項已併入第 4、7 類。

## Reviewer files
- `review-rubric.md`

（工作區另有 `reconcile-architecture.md`、`reconcile-brief.md`、`reconcile-prd.md`、`reconcile-project-background.md`：輸入對照報告，非審查 lens。）
