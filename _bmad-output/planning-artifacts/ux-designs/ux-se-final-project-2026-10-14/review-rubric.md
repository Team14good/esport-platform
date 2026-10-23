# Spine Pair Review — FLOW (se-final-project)

## Overall verdict
這組 spine 可以直接交給下游當契約：四條 UJ 都有具名主角、編號步驟、高潮與例外；所有色彩 token 都有淺／深 hex 成對值，且與 `.working/flow-logo-and-themes-1.html` 的 T1 註解完全一致；38 個 surface 都對到 FR，DESIGN.md 章節順序合乎規格。主要風險集中在「實作時會撞牆」的三處：品牌 `accent` 與 shadcn 語意 `--accent` 同名卻宣稱一一對應、shadcn 必要槽位沒補齊（`card-foreground`、`popover-foreground`、`secondary*`、`sidebar-*`），以及 UX 追加功能（忘記／重設密碼、重寄驗證信、移除隊員、轉讓隊長）在架構沒有對應方法、也沒列入「待回補上游」。沒有 critical；其餘多為 reconcile 已提出但尚未落地的按鈕停用條件與對戰樹邊界狀態。

> 不列為問題的使用者決定：無障礙延後、不設 WCAG 等級、未驗證對比（DESIGN〈Colors〉「對比」、EXPERIENCE〈Accessibility Floor〉）；範圍收斂（移除「全部標為已讀」、輪次 chip、`?team=` 網址）；身分切換器取代統一儀表板；後台側欄；深色預設。

## 1. Flow coverage — adequate
檢查 PRD §2.3 的 UJ-1～UJ-4（名稱逐字一致）與 FR-1～FR-38、NFR 在 Key Flows／IA 的落點。四條 UJ 都有主角、編號步驟、**高潮**、失敗／例外；FR-22 頂替規則、FR-13 先發人數門檻、FR-3 立即出現主辦方入口皆已依 reconcile 修正。未落入旅程的需求已在 Open Questions 1～8 自承。
### Findings
- **medium** 主辦方的不可逆「事後變更」沒有任何旅程或例外段落：FR-10 取消賽事（通知所有報名隊伍）、FR-23 修改場次時間（通知兩隊與裁判、已報到後不可改）、FR-9 抽籤前延長報名／提高名額。UJ-1 例外只提到「延長報名（S28）或取消賽事」一句帶過（EXPERIENCE〈Key Flows〉UJ-1 失敗段、Open Questions #4）。*Fix:* 在 UJ-1 例外補 2～3 行：S27「取消賽事」→ AlertDialog（寫後果：通知所有隊伍、資訊唯讀）→ S2 橫幅；S30 改時間 → 已報到場次停用並說明。

## 2. Token completeness — adequate
抽出 frontmatter 全部 token（colors 44 個、typography 11 組、rounded 6、spacing 10、components 20 組）與兩份文件內所有 `{path.to.token}` 引用。每個色彩 token 都有 hex 且淺／深成對；EXPERIENCE 引用的 `{colors.status-*}`、`{colors.ring}`、`{colors.muted}`、`{spacing.touch-target}`、`{spacing.sidebar-width}`、`{typography.countdown}` 全部可解析。對比目標依使用者決定不設，不列問題。
### Findings
- **high** 品牌 `accent`（`#7C3AED`／`#8B5CF6`）與 shadcn 語意 `--accent` 同名，而〈Colors〉又宣稱「token 與 shadcn 產生的 CSS 變數一一對應」。照字面鏡像會把 `--accent` 設成品牌紫，讓 DropdownMenu、Command、Select 項目與 ghost／outline Button 的 hover 全部變紫——正是同一節 [ASSUMPTION] 規則禁止的結果；要守規則就得逐一改寫 shadcn 元件 class，之後每次 `shadcn add` 都會回退（DESIGN〈Colors〉「與 shadcn `accent` 的衝突」、frontmatter `accent`／`accent-dark`）。*Fix:* 品牌紫改名為 `brand`（`--brand`／`brand-dark`），shadcn `accent`／`accent-foreground` 改填 `muted`／`foreground` 的值；同步更新 `{colors.accent}` 的引用（logo-lockup、賽程已公布徽章、Identity switcher、EXPERIENCE〈賽事狀態〉）。
- **high** 宣稱「補齊 shadcn 必要槽位」，但仍缺 `card-foreground`、`popover-foreground`、`secondary`、`secondary-foreground`（Card、Popover、DropdownMenu 文字與 Button／Badge secondary variant 會用到），若採用 shadcn Sidebar 還缺 `sidebar`、`sidebar-foreground`、`sidebar-primary`、`sidebar-primary-foreground`、`sidebar-accent`、`sidebar-accent-foreground`、`sidebar-border`、`sidebar-ring`。下游只能沿用 shadcn 中性灰（與 T1 藍調不合）或自行發明（DESIGN frontmatter `colors` 第 41～53 行、〈Colors〉「補齊槽位」）。*Fix:* 每個槽位補淺／深 hex，或在 frontmatter 註明別名（例：`card-foreground` = `foreground`、`secondary` = `muted`、`sidebar` = `card`、`sidebar-accent` = `muted`、`sidebar-primary` = `primary`）。
- **medium** `typography.*.fontFamily` 的值是 `'sans'`／`'mono'`，實際字體堆疊只寫在 YAML 註解裡；YAML 解析器會丟掉註解，token 消費端拿到的只是字串 `sans`（DESIGN frontmatter 第 55～57 行）。*Fix:* 新增 `fontFamilies:`（或在每組 typography 直接寫完整堆疊），讓 `sans`／`mono` 成為可解析 token。
- **low** 部分 component token 用無法解析的速記：`'C 15%'`、`'C 38%'`、`'0 0 0 1px primary/60%, …'`、`'{colors.status-live} 55%'`、`'radial 520x220 at 90% -8%, primary-dark 16%'`（DESIGN frontmatter `status-badge`、`button-primary.glow-dark`、`bracket-match-card-live`、`app-backdrop-dark`）；淺色模式背景光暈（`primary` 8%）只寫在 prose，沒有 token。*Fix:* 改為 `color-mix` 形式或拆成 `{colors.x}` ＋ `opacity` 兩欄；補 `app-backdrop-light`。

## 3. Component coverage — adequate
DESIGN〈Components〉19 項與 EXPERIENCE〈Component Patterns〉22 項（多出的 AlertDialog、Toast、Skeleton 屬 DESIGN 列出的 shadcn 繼承元件）逐一對照，名稱與規則大致一致、規則具體。缺口在流程與狀態中出現、但兩邊都沒有規格的元件。
### Findings
- **medium** S17 的「名單與每人資料完成度」清單（UJ-2 步驟 4、FR-13 送出門檻「逐項列出缺什麼」）與 S4 的報到區（「顯示雙方報到狀態」、報到鈕、報到開放倒數）是 UJ-2、UJ-3 的核心操作，卻沒有任何元件列（EXPERIENCE〈報名狀態〉組隊中列、〈場次狀態〉待開打・可報到列）。*Fix:* 兩份 spine 各加 `Roster list`（每人列：名稱、遊戲 ID、段位、截圖已上傳、完成勾；隊長端移除／轉讓入口）與 `Check-in panel`（兩隊狀態、按鈕、倒數）的視覺與行為列。
- **medium** 流程中提到但未規格化：頁頂橫幅（「此賽事已取消」、「連線中斷，正在重試」、S1「申請成為主辦方」）、S29「段位截圖檢視器」（UJ-1 步驟 5）、對戰表的冠軍／亞軍／季軍標記與「冠亞季置頂」區（〈State Patterns〉對戰表標記、〈對戰樹〉版型）。Bracket mark tag 只定義四種標籤。*Fix:* 指定橫幅＝shadcn `Alert`（destructive／default 各用在哪）；段位截圖檢視器＝`Dialog` 內圖片＋隊員切換；冠亞季用哪個 token 與位置寫進 Bracket 元件。
- **medium** Countdown 的變體在兩份文件不一致：DESIGN 說數字預設 `status-appeal`、下方固定有進度條，報到前 `muted-foreground`、可報到後 `status-live`；EXPERIENCE〈倒數與時間〉另有報名截止 24 小時切色、申訴處理期限 `{colors.destructive}`，且只有申訴期寫「＋進度條」（DESIGN〈Components〉Countdown、frontmatter `countdown`、EXPERIENCE 倒數表）。*Fix:* 在 DESIGN Countdown 列出 tone 變體（muted／live／appeal／destructive）與「進度條只在申訴期」或「全部都有」二擇一，EXPERIENCE 表只引用變體名。
- **low** 輪詢有變動的場次卡用 `{colors.primary}` 光環閃一次，與 DESIGN〈Elevation & Depth〉「同一視窗發光元素 ≤ 3 種（主要按鈕、進行中場次、搜尋命中路徑）」衝突（EXPERIENCE〈通用狀態〉輪詢重抓、〈對戰樹〉更新）。*Fix:* 把「更新閃光」列為第四種例外，或改用非發光的底色淡入。

## 4. State coverage — adequate
逐一走 S1～S38，檢查載入、空、錯誤、權限、失效連結、到期、離線。通用狀態表、四組狀態機（賽事／場次／報名／主辦方申請）與到期行為都寫得完整；離線明確宣告不支援。以下為仍缺的狀態，多數已由 reconcile-prd／reconcile-architecture 提出但未回寫。
### Findings
- **medium** 對戰樹邊界狀態缺漏：FR-25 雙方皆未報到（兩隊皆淘汰、下一輪對手輪空；準決賽時另一場勝隊直接成冠軍、季軍賽取消）；FR-20 正取少於 4 隊時沒有季軍賽，但〈對戰樹〉假設季軍賽固定在決賽下方（EXPERIENCE〈對戰樹〉版型、〈場次狀態〉；reconcile-prd b1、b2）。*Fix:* 在〈對戰樹〉場次卡加「雙方棄權」呈現（兩列皆淘汰灰＋棄權標籤、下一輪顯示輪空），並寫「無季軍賽時不顯示該卡、置頂區只列冠亞軍」。
- **medium** 隊伍搜尋——UJ-2、UJ-4 的高潮——沒有零結果與「隊伍不在對戰表上」（候補、撤回、尚未抽籤）的狀態（EXPERIENCE〈對戰樹〉隊伍搜尋）。*Fix:* 補一句零結果文案（例：「對戰表上沒有符合的隊伍。」）與尚未抽籤時搜尋框停用或隱藏。
- **medium** FR 規定的按鈕停用條件未落到介面：FR-30 每隊每場只能申訴一次（S4 已申訴後的按鈕狀態）；FR-32 不能檢舉自己的隊伍（S2「正取隊伍」自己那列）；FR-23 已有隊伍報到後不可改時間（S30）；FR-9 抽籤後 S28 只剩唯讀；`RefereeInvitation.expires_at`（S23 缺「已過期」原因）（reconcile-prd b3～b5、reconcile-architecture b1）。*Fix:* 在對應 surface 的 State Patterns 各加一列：停用＋一句原因。
- **medium** Score entry panel 的存檔模型不明：每局是「登錄即送伺服器」（才能讓觀眾即時看到每局，UJ-3 步驟 4）還是確認前只是本機草稿（「確認前可改任何一局，預覽即時重算」）。兩種解讀會導出不同 API 與 NFR-1 併發處理（EXPERIENCE〈Component Patterns〉Score entry panel）。*Fix:* 明寫「每局送出即存伺服器；修改某局＝更新該局；確認系列結果才鎖定」或相反。
- **low** 缺少的空狀態與失效狀態：S25 尚無賽事、S31 尚無已接受裁判、S35 無待審核申請、S2「正取隊伍」分頁在分配前、S9 重設連結過期或無效。*Fix:* 在〈通用狀態〉表補五列，沿用「一句事實＋一個下一步」。

## 5. Visual reference coverage — adequate
`mockups/`、`wireframes/` 尚不存在，`imports/` 為空；`.working/` 有 3 個 logo SVG 與 1 份比較稿，全部在 DESIGN〈Brand & Style〉逐一連結並寫明用途（無孤兒、無籠統引用）；「spine 與稿件衝突時以 spine 為準」兩份文件都有寫。依本次流程，關鍵畫面稿與 `.working/` 資產提升留待 Finalize，故不重判。
### Findings
- **medium** 四個連結都指向 `.working/`（暫存區）。Finalize 把 logo SVG 與主題稿提升出 `.working/` 時，DESIGN 的連結會全部失效；比較稿也包含已否決的 L1／L3／L4 與 T2～T4（DESIGN〈Brand & Style〉logo 表與第 224 行）。*Fix:* Finalize 時把三個 SVG 移到正式資產資料夾並改寫連結；比較稿另存一份只含 L2＋T1 的版本，或保留但改在連結旁註明「僅 L2、T1 區塊有效」。
- **low** EXPERIENCE 沒有任何構圖參考；S3 對戰樹（招牌畫面，含連接線、搜尋路徑、橫向捲動）、S4 場次頁兩欄、S17 報名頁幾何最複雜，最需要關鍵畫面稿（EXPERIENCE〈對戰樹〉、〈Responsive & Platform〉）。*Fix:* Finalize 的關鍵畫面優先做 S3（桌機＋375 px＋搜尋命中）、S4、S17，並在對應段落加「→ Composition reference」行。

## 6. Bloat & overspecification — adequate
DESIGN 的 prose 帶編輯語氣但都連到決策；EXPERIENCE 以表格為主，IA／需求覆蓋表對下游有用。只有幾處重述會造成漂移風險。
### Findings
- **low** FR-22 頂替規則在 EXPERIENCE 寫了三次（〈對戰樹〉場次卡、UJ-1 例外、UJ-2 例外），與文件開頭「需求內容不在此重述，只引用 FR 編號」相違；上一輪 reconcile 抓到的實質衝突正是這段重述漂移所致。*Fix:* 只在〈對戰樹〉保留一次（寫畫面上怎麼呈現），旅程中改為「依 FR-22 調整（見〈對戰樹〉）」。
- **low** DESIGN〈Colors〉兩張表重列所有 hex，與 frontmatter 重複；日後改色要改兩處（DESIGN〈Colors〉）。*Fix:* 表格保留「用途／不用於」，hex 欄改為只引用 token 名，或註明「以 frontmatter 為準」。
- **low** IA 表「旅程」欄的「— （缺口）」與 Open Questions 1～8 重複同一份清單（EXPERIENCE〈Information Architecture〉）。*Fix:* 擇一保留。

## 7. Inheritance discipline — adequate
`sources` 六個路徑全部存在；UJ 名稱逐字一致；PRD §3 名詞（賽事／場次／局、輪空、報到、正取／候補、申訴期）一致使用，「比賽」只出現在 UJ-4 原標題與「比賽轉播」修辭；架構欄位名（`scheduled_at`、`forfeit_deadline`、`appeal_deadline`、`registration_end`、`win_loss`、`rounds`、`detail.message`、`register(email, password, school)`、`display_name`）與 AD 編號均可對上。
### Findings
- **high** UX 追加且經使用者決定的功能——忘記／重設密碼（S8、S9）、重寄驗證信（S7）、移除隊員與轉讓隊長（S17，牽涉 `MemberRole` 與 AD-10 `ensure_captain`）——在架構 D-1 `IdentityService`、D-3 `RegistrationService` 都沒有方法，PRD 也沒有對應 FR；但 Open Questions「已決定、待回補上游」只列了直播連結（EXPERIENCE Open Questions #9、需求覆蓋表；reconcile-architecture C3、reconcile-prd C3）。照 spine 寫故事的人會做出沒有後端的畫面。*Fix:* 把這四項加入「已決定、待回補上游」，逐項寫明要回補的文件與位置（PRD 新 FR 或 §7 註記、D-1／D-3 方法、Epic），範圍收斂原則下也可標優先序。
- **low** 〈Component Patterns〉Status badge 規定「文字＝PRD 狀態名原字」，但 State Patterns 使用非 PRD 的介面標籤（組隊中、已送出・待分配、待開打・可報到、候補第 N 位）；DESIGN frontmatter `status-badge` 的 C 清單也沒有「賽程已公布」用的 `{colors.accent}`。*Fix:* 改為「文字＝PRD 狀態名，或 State Patterns 表中標示的介面標籤」，並把 `accent`（或改名後的 `brand`）加入 C 清單。
- **low** 輪詢超出 AD-14 範圍（未讀數每 30 秒、倒數到期後任意頁每 5 秒重抓最多 2 分鐘），且「相對時間」依賴架構 `Notification` 沒有的 `created_at`（reconcile-architecture C4、C6）。*Fix:* 列入「待回補上游」或 Open Questions，提醒 NFR-2 壓測納入這些輪詢。

## 8. Shape fit — strong
DESIGN 八節依規格順序（Brand & Style → Colors → Typography → Layout & Spacing → Elevation & Depth → Shapes → Components → Do's and Don'ts）。EXPERIENCE 必要預設節全數存在；Accessibility Floor 依使用者決定只記錄繼承行為，合理。Inspiration（有競品與現行做法）、Responsive（375 px／多斷點）兩個條件節都在。自創的〈對戰樹〉〈身分切換器〉〈通知〉〈倒數與時間〉被 Component Patterns 反覆引用，〈Open Questions〉承接 32 項缺口，皆有存在理由。
### Findings
- 無。

## Mechanical notes
- 元件名稱漂移：DESIGN「Top nav / Sidebar nav item（active）」vs EXPERIENCE「Top nav / Sidebar nav」；「Button（primary）」全形括號 vs「Button (primary)」半形；frontmatter key `identity-switcher-trigger`、`nav-item-active` 與 prose 名稱不同步。建議統一為同一字串。
- Open Questions #7（「UJ-3 沒寫小芸如何找到被指派的場次」）已過時：UJ-3 步驟 2 現在寫了「收到通知 → S13，該場在列」。
- Open Questions #2 仍寫「S7 重寄驗證信……沒有旅程」，與 UJ-1 步驟 1、UJ-2 步驟 3 的 S7 落地無衝突，但可註明只缺「重寄」分支。
- DESIGN frontmatter 無 `sources`（規格不要求）；兩份文件 `status: draft`、`updated: 2026-10-15` 一致。
- 兩份 spine 無 Mermaid 圖，無語法問題。
- `.working/` 三個 SVG 的 hex（`#22D3EE`、`#8B5CF6`、`#E6ECFF`、`#0891B2`、`#7C3AED`、`#0B1020`）與 frontmatter 一致；比較稿 T1 註解的 15 組淺／深值與 frontmatter 完全一致。
- `reconcile-*.md` 四份為輸入對照報告（非審查 lens）；其「必須修正」項（FR-22 頂替、FR-13 先發門檻、FR-3 立即出現、S5 收學校、截圖預覽僅本機、移除 `Date` 標頭校時）已依 memlog 回寫 spine；尚未處理的 b 項已併入上方第 4、7 類。
