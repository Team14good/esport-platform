---
name: FLOW
description: 校際與社群中小型電競盃賽的一站式賽事管理平台。視覺語言為「科幻流動感」：T1 深空霓虹配色、L2 匯流賽道 logo、深色為預設。shadcn/ui（Tailwind 4）之上的品牌層，本文件只寫差異。
status: final
updated: 2026-10-20
colors:
  # 命名規則：沿用 shadcn/Tailwind 的 CSS 結構——無後綴＝淺色值（對應 :root），-dark 後綴＝深色值（對應 .dark）。
  # 執行時預設套用 .dark（深色為預設），淺色是使用者切換後的模式。見正文〈Colors〉。
  # 與 shadcn 同名的 token 一律照 shadcn 的語意使用；FLOW 自己的色（brand、status-*、search-highlight）用不與 shadcn 衝突的名稱。
  # ---- shadcn 語意色（T1 深空霓虹，使用者決定）----
  background: '#F4F6FD'
  card: '#FFFFFF'
  foreground: '#0B1020'
  muted-foreground: '#5B6482'
  border: '#DCE2F2'
  primary: '#0891B2'
  primary-foreground: '#FFFFFF'
  destructive: '#DC2626'
  background-dark: '#070A14'
  card-dark: '#0E1426'
  foreground-dark: '#E6ECFF'
  muted-foreground-dark: '#8A94B8'
  border-dark: '#1F2945'
  primary-dark: '#22D3EE'
  primary-foreground-dark: '#04121A'
  destructive-dark: '#F43F5E'
  # ---- FLOW 品牌紫（T1 的「accent」，使用者決定）：改名 brand，避免與 shadcn --accent（hover 淺底）同名 ----
  brand: '#7C3AED'
  brand-dark: '#8B5CF6'
  brand-foreground: '#FFFFFF'          # [ASSUMPTION] T1 未定義，沿用前版 accent-foreground
  brand-foreground-dark: '#FFFFFF'     # [ASSUMPTION] 同上
  # ---- 賽事狀態色（T1，使用者決定）----
  status-live: '#0891B2'
  status-appeal: '#B45309'
  status-confirmed: '#047857'
  status-eliminated: '#9AA3B8'
  status-waitlist: '#7C3AED'
  search-highlight: '#7C3AED'
  status-live-dark: '#22D3EE'
  status-appeal-dark: '#FBBF24'
  status-confirmed-dark: '#34D399'
  status-eliminated-dark: '#4B5370'
  status-waitlist-dark: '#A78BFA'
  search-highlight-dark: '#8B5CF6'
  # ---- 補齊 shadcn 槽位 [ASSUMPTION]：T1 未定義，依 T1 色相推導（input、ring、popover 為別名，來源見正文〈Colors〉別名表）----
  muted: '#E9EDF8'
  input: '#DCE2F2'
  ring: '#0891B2'
  popover: '#FFFFFF'
  destructive-foreground: '#FFFFFF'
  muted-dark: '#141B31'
  input-dark: '#1F2945'
  ring-dark: '#22D3EE'
  popover-dark: '#0E1426'
  destructive-foreground-dark: '#FFFFFF'
  # ---- shadcn 槽位別名（純別名，非新色；來源見正文〈Colors〉別名表，改色時一起改）----
  accent: '#E9EDF8'
  accent-foreground: '#0B1020'
  card-foreground: '#0B1020'
  popover-foreground: '#0B1020'
  secondary: '#E9EDF8'
  secondary-foreground: '#0B1020'
  sidebar: '#FFFFFF'
  sidebar-foreground: '#0B1020'
  sidebar-primary: '#0891B2'
  sidebar-primary-foreground: '#FFFFFF'
  sidebar-accent: '#E9EDF8'
  sidebar-accent-foreground: '#0B1020'
  sidebar-border: '#DCE2F2'
  sidebar-ring: '#0891B2'
  accent-dark: '#141B31'
  accent-foreground-dark: '#E6ECFF'
  card-foreground-dark: '#E6ECFF'
  popover-foreground-dark: '#E6ECFF'
  secondary-dark: '#141B31'
  secondary-foreground-dark: '#E6ECFF'
  sidebar-dark: '#0E1426'
  sidebar-foreground-dark: '#E6ECFF'
  sidebar-primary-dark: '#22D3EE'
  sidebar-primary-foreground-dark: '#04121A'
  sidebar-accent-dark: '#141B31'
  sidebar-accent-foreground-dark: '#E6ECFF'
  sidebar-border-dark: '#1F2945'
  sidebar-ring-dark: '#22D3EE'
typography:
  # [ASSUMPTION] 未選定字型：不載入 webfont，使用系統 CJK 安全字體堆疊（與 mockups/ 示意圖一致）。
  # 兩組堆疊：介面用 sans 堆疊；比分、倒數用 mono 堆疊。值直接寫在每組 fontFamily。
  display:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 30px
    fontWeight: '700'
    lineHeight: '1.3'
    letterSpacing: 0.01em
  heading-lg:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 24px
    fontWeight: '700'
    lineHeight: '1.35'
  heading-md:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.4'
  body:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.6'
  body-lg:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 12.5px
    fontWeight: '600'
    lineHeight: '1.3'
  caption:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 12px
    fontWeight: '400'
    lineHeight: '1.4'
  overline:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 11px
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: 0.08em
  score:
    fontFamily: '"Cascadia Mono", "Cascadia Code", Consolas, ui-monospace, SFMono-Regular, Menlo, monospace'
    fontSize: 20px
    fontWeight: '800'
    lineHeight: '1.2'
    letterSpacing: 0.04em
  countdown:
    fontFamily: '"Cascadia Mono", "Cascadia Code", Consolas, ui-monospace, SFMono-Regular, Menlo, monospace'
    fontSize: 16px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: 0.06em
  bracket-row:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif'
    fontSize: 12.5px
    fontWeight: '400'
    lineHeight: '1.2'
rounded:
  # shadcn（Tailwind 4）預設 --radius: 0.625rem 推導的階梯，原樣繼承；xs 為 FLOW 追加。
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 14px
  full: 9999px
spacing:
  # Tailwind 4 預設 4px 階梯原樣繼承（1=4px、2=8px、3=12px、4=16px、6=24px、8=32px…）。以下為 FLOW 具名追加 [ASSUMPTION]。
  gutter-mobile: 16px
  gutter-desktop: 28px
  content-max: 1280px
  sidebar-width: 240px
  touch-target: 40px
  bracket-row-height: 32px
  bracket-match-gap: 18px
  bracket-connector-width: 28px
  bracket-column-min: 200px
  match-aside-width: 400px
  match-column-gap: 20px
  backdrop-grid: 28px
  screenshot-viewer-max: 960px
components:
  # 所有 {colors.<token>} 在深色模式解析為 {colors.<token>-dark}。
  # 透明度寫成 color-mix(in oklab, <色> N%, transparent)；「tone」＝該元件 tones 欄列出的其中一個 token。
  logo-lockup:
    mark-gradient-from: '{colors.primary}'
    mark-gradient-to: '{colors.brand}'
    wordmark: '{colors.foreground}'
    height: 28px
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    radius: '{rounded.md}'
    glow-dark: '0 0 0 1px color-mix(in oklab, {colors.primary-dark} 60%, transparent), 0 4px 18px -6px {colors.primary-dark}'
  status-badge:
    tones: '{colors.status-live} | {colors.status-appeal} | {colors.status-confirmed} | {colors.status-eliminated} | {colors.status-waitlist} | {colors.brand} | {colors.destructive} | {colors.muted-foreground}'
    foreground: 'tone'
    background-opacity: '15%'
    border-opacity: '38%'
    radius: '{rounded.full}'
    typography: '{typography.label}'
  bracket-match-card:
    background: '{colors.background}'
    border: '{colors.border}'
    radius: '{rounded.md}'
    row-height: '{spacing.bracket-row-height}'
    header: '{typography.overline}'
  bracket-match-card-live:
    border: 'color-mix(in oklab, {colors.status-live} 55%, {colors.border})'
    ring: '0 0 0 3px color-mix(in oklab, {colors.status-live} 12%, transparent)'
  bracket-team-row-winner:
    fontWeight: '700'
    score: '{colors.primary}'
  bracket-team-row-eliminated:
    foreground: '{colors.status-eliminated}'
    decoration: 'line-through 1px'
  bracket-team-row-search-hit:
    background: 'color-mix(in oklab, {colors.search-highlight} 14%, transparent)'
    inset-bar: '3px {colors.search-highlight}'
    outline: '1.5px {colors.search-highlight}'
  bracket-team-row-tbd:
    foreground: '{colors.muted-foreground}'
    outline-when-on-search-path: '1.5px dashed {colors.search-highlight}'
  bracket-mark-tag:
    border: '1px currentColor'
    radius: '{rounded.xs}'
    typography: '{typography.caption}'
    foreground: '{colors.muted-foreground}'
    foreground-disqualified: '{colors.destructive}'
    foreground-champion: '{colors.brand}'
  podium:
    background: '{colors.card}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    champion: '{typography.heading-md}'
    others: '{typography.body}'
  update-flash:
    background: '{colors.muted}'
    duration: 1.5s
  countdown:
    label: '{colors.muted-foreground}'
    value: '{typography.countdown}'
    bar-height: 4px
  countdown-muted:
    foreground: '{colors.muted-foreground}'
  countdown-live:
    foreground: '{colors.status-live}'
  countdown-appeal:
    foreground: '{colors.status-appeal}'
    bar-track: 'color-mix(in oklab, {colors.status-appeal} 16%, transparent)'
    bar-fill: '{colors.status-appeal}'
  countdown-destructive:
    foreground: '{colors.destructive}'
  score-display:
    typography: '{typography.score}'
    winner: '{colors.foreground}'
    loser: '{colors.status-eliminated}'
  card:
    background: '{colors.card}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
  nav-item-active:
    foreground: '{colors.foreground}'
    indicator: '2px {colors.primary}'
    sidebar-background: '{colors.sidebar-accent}'
  notification-unread-dot:
    background: '{colors.primary}'
    radius: '{rounded.full}'
  identity-switcher-trigger:
    background: '{colors.card}'
    border: '{colors.border}'
    radius: '{rounded.md}'
    current-identity-bar: '2px {colors.brand}'
  roster-list:
    row-divider: '{colors.border}'
    complete: '{colors.status-confirmed}'
    incomplete: '{colors.muted-foreground}'
    meta: '{typography.caption}'
  check-in-panel:
    background: '{colors.card}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    checked-in: '{colors.status-confirmed}'
    not-checked-in: '{colors.muted-foreground}'
  page-banner:
    radius: '{rounded.md}'
    default-border: '{colors.border}'
    destructive: '{colors.destructive}'
  rank-screenshot-viewer:
    max-width: '{spacing.screenshot-viewer-max}'
    image-background: '{colors.background}'
    image-radius: '{rounded.md}'
  app-backdrop-dark:
    base: '{colors.background-dark}'
    glow-primary: 'radial-gradient(520px 220px at 90% -8%, color-mix(in oklab, {colors.primary-dark} 16%, transparent), transparent)'
    glow-brand: 'radial-gradient(420px 200px at -10% 105%, color-mix(in oklab, {colors.brand-dark} 12%, transparent), transparent)'
    grid-line: '1px color-mix(in oklab, {colors.border-dark} 45%, transparent)'
    grid-size: '{spacing.backdrop-grid}'
  app-backdrop-light:
    base: '{colors.background}'
    glow-primary: 'radial-gradient(520px 220px at 90% -8%, color-mix(in oklab, {colors.primary} 8%, transparent), transparent)'
---

## Brand & Style

FLOW 是給校際與社群電競盃賽用的賽事管理平台。名字本身就是產品承諾：報名、名額、抽籤、報到、比分、申訴，一路「流」到冠軍，不再散落在 Google 表單、Excel、FB 公告與 Discord 之間。

視覺姿態是**科幻流動感**——像比賽轉播片頭的深空夜色，青色霓虹是正在發生的事，紫色光暈是晉級與收斂的方向。它要有電競的興奮與速度，但本質是一個要讓主辦方「出事時拿得出紀錄」的工具：霓虹只用在有意義的地方（進行中、主要動作、晉級路徑），其餘維持安靜、可讀、資訊密度高的 shadcn 介面。

FLOW 完整繼承 shadcn/ui 預設元件（Button、Card、Dialog、AlertDialog、Alert、Form、Sheet、Sidebar、DropdownMenu、Popover、Tabs、Table、Toast/Sonner、Input、Select、Skeleton、Badge、Avatar、Separator、Tooltip）。本文件只定義品牌層：T1 色票、賽事狀態色、等寬比分與倒數字、深色背景光暈，以及對戰樹等 FLOW 專屬元件。

**示意圖：**只有 S3、S4 畫了示意圖（使用者決定），其餘畫面只有文字規格：

| 檔案 | 示意內容 |
|---|---|
| [`mockups/flow-logo-and-themes.html`](mockups/flow-logo-and-themes.html) | Logo 與配色比較稿：L1–L4 四款 logo、T1–T4 四組配色（各含深／淺色）；採用的是 L2 與 T1（稿中 T1 的「accent」即本文件的 `brand`） |
| [`mockups/key-s3-bracket.html`](mockups/key-s3-bracket.html) | S3 對戰表：手機（375px）隊伍搜尋命中（晉級路徑、虛線待定列）、手機搜尋找不到；桌機（1280px）完整 32 隊對戰樹 |
| [`mockups/key-s4-match.html`](mockups/key-s4-match.html) | S4 場次頁＋S24 比分登錄：桌機裁判系列進行中、送出後申訴期（含隊長端「提出申訴」）、手機觀眾申訴期（稿內按鈕仍寫舊名「確認系列結果」，以本文件為準） |

文件與示意圖衝突時，以文件為準。

**Logo — L2 匯流賽道（Converging Bracket）：**四條流線兩兩匯合、再匯成一個發光點：同時是「流動」與「對戰樹收斂到冠軍」。不透明度越靠近冠軍點越高，單色版本也看得出方向；字標 FLOW 為中等筆重的圓角線條字，O 做成跑道形。

| 檔案 | 用途 |
|---|---|
| [`brand/flow-logo-L2-mark.svg`](brand/flow-logo-L2-mark.svg) | 標誌本體（漸層 `{colors.primary-dark}` → `{colors.brand-dark}`）；favicon、載入、空狀態插圖 |
| [`brand/flow-logo-L2-lockup-dark.svg`](brand/flow-logo-L2-lockup-dark.svg) | 標誌＋字標，深底用（字標 `{colors.foreground-dark}`） |
| [`brand/flow-logo-L2-lockup-light.svg`](brand/flow-logo-L2-lockup-light.svg) | 標誌＋字標，淺底用（漸層 `{colors.primary}` → `{colors.brand}`、字標 `{colors.foreground}`） |

16px favicon 用單色版（`currentColor`）；漸層版從 32px 起使用。

## Colors

**模式與命名：**深色是預設模式，淺色由使用者切換。Token 命名沿用 shadcn/Tailwind 的 CSS 結構：無後綴的 token 是淺色值（寫在 `:root`），`-dark` 後綴是深色值（寫在 `.dark`）。實作時 `<html>` 預設帶 `class="dark"`；切到淺色才移除。所以文件中的 `{colors.primary}` 在預設畫面上實際呈現的是 `{colors.primary-dark}`。選這個方向而不是「無後綴＝深色」，是為了讓 token 與 shadcn 產生的 CSS 變數一一對應，不必反轉範本。

**與 shadcn 的對應：**與 shadcn 同名的 token（`background`、`card`、`primary`、`accent`、`secondary`、`sidebar-*`…）直接寫進同名 CSS 變數，語意也照 shadcn：例如 `--accent` 是選單項目與 ghost／outline Button 的 hover／focus 淺底，FLOW 把它設成與 `muted` 相同的中性藍灰，因此 `shadcn add` 進來的元件不需改 class。FLOW 自己的色——`brand`、`status-*`、`search-highlight`——是新增的 CSS 變數（`--brand` 等），在 Tailwind 4 的 `@theme inline` 註冊為 `--color-brand` 等，供 FLOW 專屬元件使用。

**T1 深空霓虹（使用者決定）：**hex 值以 frontmatter 為準，下表只寫用途。

| Token | 用途 | 不用於 |
|---|---|---|
| `background` | 頁面底色；深色時疊上 `app-backdrop-dark` 光暈與格線 | 卡片內部 |
| `card` | 卡片、頂欄、表格底 | — |
| `foreground` | 內文、勝隊名稱、標題 | — |
| `muted-foreground` | 次要文字、時間、輪次標頭、待定隊伍 | 可點擊的主要文字 |
| `border` | 1px 分隔、卡片外框、場次卡外框 | 狀態表達 |
| `primary` | 主要動作按鈕、目前導覽項底線、勝方比分、連結 | 大面積背景、裝飾 |
| `primary-foreground` | `primary` 上的文字 | — |
| `brand` | 品牌紫：logo 漸層終點、深色背景左下光暈、「賽程已公布」徽章（對戰樹收斂成形）、身分切換器的目前身分、對戰樹「冠軍」標記 | 任何 shadcn 元件的 hover／focus 底 |
| `destructive` | 取消賽事、退回、取消資格、刪除類確認；表單錯誤；「此賽事已取消」橫幅 | 「淘汰」（淘汰用灰，不是紅） |

**賽事狀態色（使用者決定）：**淺色版刻意比深色版暗，讓白底上的文字仍可讀。每個狀態徽章用哪個 token，完整對照見〈Components〉Status badge。

| Token | 對應狀態 |
|---|---|
| `status-live` | 進行中（場次與賽事）、可報到、可開始 |
| `status-appeal` | 申訴期（倒數）、申訴中、待審核、「時間正在流逝」的倒數（見 Countdown 的 `appeal` 變體） |
| `status-confirmed` | 已確認、正取、核准、遞補成功、已報到、資料完成 |
| `status-eliminated` | 淘汰（FR-35 的「灰色」）、已結束賽事的次要資訊 |
| `status-waitlist` | 候補（含候補順位） |
| `search-highlight` | 對戰樹隊伍搜尋的命中列與晉級路徑 |

`status-live` 與 `primary` 同值是刻意的：青色霓虹在 FLOW 裡就是「正在發生」。`status-waitlist`、`search-highlight` 與 `brand` 都屬紫色系，但不會同時出現在同一個畫面區塊上（候補只在報名脈絡、搜尋只在對戰樹進行中、冠軍標記只在已結束的對戰樹）。

**補齊槽位 [ASSUMPTION]：**T1 稿沒有定義 `muted`、`input`、`ring`、`popover`、`destructive-foreground`、`brand-foreground`；依 T1 色相補值（見 frontmatter）。其餘 shadcn 槽位一律是既有 token 的**別名**（來源見下表，改色時一起改）：

| shadcn 槽位 | 別名自 |
|---|---|
| `accent`、`secondary`、`sidebar-accent` | `muted` |
| `accent-foreground`、`card-foreground`、`popover-foreground`、`secondary-foreground`、`sidebar-foreground`、`sidebar-accent-foreground` | `foreground` |
| `popover`、`sidebar` | `card` |
| `input`、`sidebar-border` | `border` |
| `ring`、`sidebar-primary`、`sidebar-ring` | `primary` |
| `sidebar-primary-foreground` | `primary-foreground` |

`sidebar-*` 供後台側欄（主辦方賽事後台、平台管理後台）的 shadcn `Sidebar` 使用：底色與 `card` 相同，active 項目底色為 `muted`。

**對比：**使用者決定延後無障礙檢查；以上組合未做對比驗證，也不宣稱任何 WCAG 等級。

避免：第三種品牌色（金色獎牌也不加）、把霓虹青用在大面積背景、用紅色表示「淘汰」、狀態只靠顏色沒有文字（見 Do's and Don'ts）。

## Typography

**字型 [ASSUMPTION]：**尚未選定字型，不載入 webfont。介面用系統 CJK 安全字體堆疊（Segoe UI Variable／微軟正黑體／蘋方-繁／Noto Sans TC → system-ui）；比分、倒數、場次編號用等寬堆疊（Cascadia Mono／Consolas → ui-monospace），讓 `08:42`、`2 : 1` 在跳動時不會左右晃。完整堆疊即 frontmatter 各組 `fontFamily` 的值（例：`{typography.body.fontFamily}`、`{typography.countdown.fontFamily}`）。logo 字標是 SVG 路徑，不依賴字型。

| 角色 | Token | 用在 |
|---|---|---|
| 頁面主標 | `{typography.display}` | 賽事頁賽事名稱、空狀態主句 |
| 區塊標題 | `{typography.heading-lg}` / `{typography.heading-md}` | 頁內區塊、卡片標題、Dialog 標題、冠軍隊名 |
| 內文 | `{typography.body}`（shadcn 預設 `text-sm`）；手機長文用 `{typography.body-lg}` | 表單、清單、說明 |
| 標籤 | `{typography.label}` | 按鈕、狀態徽章、導覽項 |
| 輔助 | `{typography.caption}` / `{typography.overline}` | 時間、輪次標頭（16 強／8 強）、表格欄名 |
| 比分 | `{typography.score}` | 場次頁系列比分 `2 : 1` |
| 倒數 | `{typography.countdown}` | 申訴期、報到、棄權、報名截止倒數 |
| 對戰樹列 | `{typography.bracket-row}` | 對戰樹中的隊伍名與比分 |

介面不使用英文全大寫，中文不加寬字距；`overline` 的 0.08em 字距只用於英數混排的輪次標頭，其他 `overline` 用法不加字距。不使用斜體。

## Layout & Spacing

Tailwind 4 預設 4px 階梯原樣繼承。具名追加 [ASSUMPTION]：

- **邊距**：手機 `{spacing.gutter-mobile}`、桌機 `{spacing.gutter-desktop}`；內容最大寬 `{spacing.content-max}`。
- **後台**：主辦方賽事後台與平台管理後台使用 shadcn `Sidebar`，寬 `{spacing.sidebar-width}`；`< lg` 改為從頂欄開啟的 `Sheet`。
- **公開頁與個人頁**：頂欄導覽＋單欄內容；賽事頁以 `Tabs` 分區。
- **觸控**：手機上的關鍵動作按鈕（報到、送出報名、送出系列結果）高度不小於 `{spacing.touch-target}`，滿版寬。
- **對戰樹**：
  - 尺寸：每輪一欄，欄寬固定為 `{spacing.bracket-column-min}`（桌機也不拉伸）[ASSUMPTION]；欄間連接線寬 `{spacing.bracket-connector-width}`；同欄場次間距 `{spacing.bracket-match-gap}`；隊伍列高 `{spacing.bracket-row-height}`。
  - 桌機：32 隊五欄共 5 × 200 + 4 × 28 = 1112px，在 1280px 視窗（扣掉 `{spacing.gutter-desktop}` 兩側邊距）內完整排開、不出現橫向捲軸；只有對戰樹總寬大於容器時才橫向捲動（例如 64 隊、或較窄的視窗）[ASSUMPTION]。示意：[`mockups/key-s3-bracket.html`](mockups/key-s3-bracket.html) (b)。
  - 手機：375px 下不縮放、橫向捲動（行為見 EXPERIENCE.md〈對戰樹〉）。
- **場次頁（S4）**：`≥ lg` 兩欄——左欄 `minmax(0, 1fr)`、右欄固定 `{spacing.match-aside-width}`、欄距 `{spacing.match-column-gap}` [ASSUMPTION]；`< lg` 單欄堆疊。各欄放什麼、手機堆疊順序見 EXPERIENCE.md〈場次頁（S4）〉。示意：[`mockups/key-s4-match.html`](mockups/key-s4-match.html)。
- **頁頂橫幅**：位於頂欄下方、內容區最上方，與內容同寬。

## Elevation & Depth

深色模式不用陰影分層，用**光**。同一個視窗內，發光元素不超過三種（主要按鈕、進行中場次、搜尋命中路徑）。以下的百分比＝該色與透明混合的比例，即 frontmatter 的 `color-mix`。

- **背景**：`app-backdrop-dark`——右上 `primary` 16% 光暈、左下 `brand` 12% 光暈、每 `{spacing.backdrop-grid}` 一條 `border` 45% 的細格線（「星圖格線」）。只鋪在頁面背景，不鋪在卡片內。淺色模式用 `app-backdrop-light`：只保留右上 `primary` 8% 光暈，沒有格線。
- **卡片**：`{colors.card}` 平面＋1px `{colors.border}`，不加陰影。
- **主要按鈕（深色）**：1px `primary` 60% 外框＋向下 18px 擴散的 `primary` 光暈——整個畫面最亮的地方應該是使用者下一步要按的按鈕。
- **進行中的場次卡**：3px `status-live` 12% 光環。
- **輪詢更新提示**：有變動的場次卡底色以 `{colors.muted}` 淡入淡出一次（`update-flash`，1.5 秒）——**不發光**，不計入發光元素上限 [ASSUMPTION]。
- **Popover／Dialog／Sheet**：繼承 shadcn 陰影與遮罩，不另加光暈。

## Shapes

繼承 shadcn（Tailwind 4）由 `--radius: 0.625rem` 推導的階梯：`{rounded.sm}` 6px 給輸入框與小按鈕；`{rounded.md}` 8px 給按鈕、對戰樹場次卡與頁頂橫幅；`{rounded.lg}` 10px 給一般卡片；`{rounded.xl}` 14px 給 Dialog 與大型容器。FLOW 追加 `{rounded.xs}` 4px，只給對戰樹的標記標籤（輪空／棄權／取消資格／退賽／冠軍／亞軍／季軍）。`{rounded.full}` 只用在狀態徽章、未讀點、頭像。

形狀語言跟 logo 一致：圓角線條、跑道形——不用切角、不用尖銳 HUD 框（那是 L4，未採用）。

## Components

繼承不改：〈Brand & Style〉列出的 shadcn 元件。以下是品牌層與 FLOW 專屬元件（所有 `{colors.<token>}` 在深色模式解析為 `{colors.<token>-dark}`；括號內為 frontmatter `components` 的 key；沒有括號 key 的條目是 shadcn 元件與既有 token 的組合，在 `components` 中沒有對應項目）。

### 全域

- **Logo lockup**（`logo-lockup`）— 頂欄左側，高 28px；深色用 `lockup-dark`、淺色用 `lockup-light`；`< sm` 只顯示標誌本體。漸層 `{colors.primary}` → `{colors.brand}`。
- **Button (primary)**（`button-primary`）— `{colors.primary}` 底、`{colors.primary-foreground}` 字、`{rounded.md}`；深色加光暈（見 Elevation）。其他 variant 繼承 shadcn（`secondary` 使用 `{colors.secondary}`、ghost／outline 的 hover 使用 `{colors.accent}`＝中性 `muted`）；`destructive` variant 用 `{colors.destructive}`。
- **Status badge**（`status-badge`）— 藥丸形 `{rounded.full}`、`{typography.label}`；文字色＝對應的 tone（`status-*`、`brand`、`destructive` 或 `muted-foreground`），底色為同色 15%、外框同色 38%。「進行中」「申訴中」前加 6px 脈動圓點；其他狀態無圓點。**徽章永遠帶文字**，顏色只是輔助。各狀態的 tone（`[ASSUMPTION]`；狀態色 token 本身為使用者決定）：

| Tone | 賽事 | 場次 | 報名 | 主辦方申請 |
|---|---|---|---|---|
| `{colors.status-live}` | 開放報名；進行中（＋脈動點） | 待開打・可報到（外框、無點）；待開打・可開始；進行中（＋脈動點） | — | — |
| `{colors.status-appeal}` | — | 申訴期（無點）；申訴中（＋脈動點）；棄權計時暫停 | 已送出・待分配 | 待審核 |
| `{colors.status-confirmed}` | — | 已確認 | 正取、遞補、已參賽 | 核准 |
| `{colors.status-waitlist}` | — | — | 候補 | — |
| `{colors.brand}` | 賽程已公布 | — | — | — |
| `{colors.destructive}` | 已取消 | — | 退回、取消資格 | 退回 |
| `{colors.muted-foreground}` | 尚未開放、報名截止、已結束 | 待開打；已取消（季軍賽） | 組隊中、撤回 | — |

- **Countdown**（`countdown` ＋ 變體）— 左側說明文字（`{colors.muted-foreground}`）、右側 `{typography.countdown}` 數字。數字顏色由變體決定；哪個倒數用哪個變體見 EXPERIENCE.md〈倒數與時間〉：
  - `muted`（`countdown-muted`）：還不急的倒數。
  - `live`（`countdown-live`）：可以行動了。
  - `appeal`（`countdown-appeal`）：時間正在流逝。
  - `destructive`（`countdown-destructive`）：主辦方逾期風險。
  - **進度條只在申訴期倒數出現**：數字下方 4px 進度條（底 `status-appeal` 16%、填色 `status-appeal`，隨時間縮短）。其他倒數沒有進度條。
- **Card**（`card`）— `{colors.card}`、1px `{colors.border}`、`{rounded.lg}`、內距 12–16px。
- **Top nav / Sidebar nav**（`nav-item-active`）— active 項目文字 `{colors.foreground}`；頂欄用 2px `primary` 底線，側欄用左側 2px `primary` 條＋`{colors.sidebar-accent}` 底。
- **Identity switcher**（`identity-switcher-trigger`）— 頂欄右側 `DropdownMenu` trigger：`{colors.card}` 底、1px 外框、`{rounded.md}`；顯示目前身分圖示＋名稱，目前身分在選單中以 2px `{colors.brand}` 左條標示；選單項目 hover 照 shadcn（`{colors.accent}`＝中性）。
- **Notification bell**（`notification-unread-dot`）— 頂欄鈴鐺 icon；有未讀時右上角 `{colors.primary}` 底的數字徽章（`{rounded.full}`）。清單中未讀項目左側 8px `notification-unread-dot`。
- **Theme toggle** — 頂欄 icon button（月亮／太陽），繼承 shadcn ghost Button。
- **Top bar（未登入，`< sm`）** — 左：L2 標誌本體；右：ghost Button「登入」＋選單 icon button（`Sheet`）。沒有鈴鐺與身分切換器 [ASSUMPTION]。示意：[`mockups/key-s3-bracket.html`](mockups/key-s3-bracket.html) (a)。
- **Page banner**（`page-banner`）— shadcn `Alert`，滿版寬、`{rounded.md}`，置於頂欄下方。兩種：
  - `destructive` variant：例「此賽事已取消」。
  - `default` variant（1px `{colors.border}`、無色底，可附一個 outline Button）：例「連線中斷，正在重試 · 最後更新 HH:mm:ss」。
- **Screenshot uploader** — 虛線外框 `{rounded.lg}` 拖放區＋「選擇圖片」outline Button；選檔後在送出前顯示本機縮圖預覽（`{rounded.md}`）、檔名、移除鈕；送出後，若為段位截圖，只顯示「已上傳」＋檔名，不再顯示圖片（AD-15：只有主辦方能下載）；錯誤時外框與說明文字用 `{colors.destructive}`。
- **School picker** — 學校欄（S5、S10、S15）：shadcn `Popover`＋`Command` 組成的可搜尋下拉，外觀同 `Input`；只能選學校清單內的項目，沒有自由輸入 [ASSUMPTION]。
- **Data table** — 繼承 shadcn `Table`；表頭 `{typography.overline}`、`muted-foreground`；狀態欄一律用 Status badge。`< md` 改為 `Card` 清單。
- **Empty state** — 置中：L2 標誌本體（`muted-foreground` 單色、48px）＋`{typography.heading-md}` 一句話＋`{typography.body}` 說明＋最多一個主要按鈕。

### 對戰樹（S3）

「對戰表」只用作 S3 畫面與分頁名稱；畫面上的圖形與其元件、標記一律稱「對戰樹」。

- **Bracket match card**（`bracket-match-card`、`bracket-match-card-live`、`bracket-team-row-*`）— `{colors.background}` 底（比所在卡片再暗一階）、1px `{colors.border}`、`{rounded.md}`；上方一行 `{typography.overline}` 標頭：場次編號（M3；編號規則見 EXPERIENCE.md〈對戰樹〉），未開打時後接「· 時間」（如「· 10/18（日）13:00」），其他狀態改接狀態徽章；兩列隊伍，列間 1px 分隔；每列右側一個等寬比分欄。不顯示種子或籤位編號，也沒有「淘汰」標籤（淘汰只用下方淘汰列樣式表達）。示意：[`mockups/key-s3-bracket.html`](mockups/key-s3-bracket.html)。
  - 未開打：比分欄留空（不寫 0、不寫「—」）[ASSUMPTION]。
  - 進行中：外框混入 `status-live`，加光環；比分欄顯示目前已登錄的勝局數（如 1 : 1），兩列都不套勝隊／淘汰樣式 [ASSUMPTION]。
  - 申訴期／申訴中：比分欄顯示系列比分，但**兩列都不套勝隊粗體、也不套淘汰刪除線**——結果未確認、不顯示晉級（FR-29、FR-36）[ASSUMPTION]。
  - 已確認——勝隊列：名稱粗體、比分 `{colors.primary}`。
  - 已確認——淘汰列：整列 `{colors.status-eliminated}`、名稱加 1px 刪除線。
  - 一隊棄權：兩列都**沒有比分**，棄權隊帶「棄權」標記（申訴期內也顯示）。已確認後，棄權隊用淘汰列樣式、對手用勝隊列樣式；申訴期內照上方申訴期規則，兩列都不套樣式 [ASSUMPTION]。
  - 雙方棄權：兩列都用淘汰列樣式，各帶「棄權」標記；沒有比分。
  - 待定列（如「M4 勝者」、季軍賽的「M29 敗者」）：`{colors.muted-foreground}`、比分欄留空；位於搜尋路徑上時加 1.5px 虛線 `search-highlight` 外框（哪些待定列套用，見 EXPERIENCE.md〈對戰樹〉隊伍搜尋）。
  - 搜尋命中列：`search-highlight` 14% 底、左側 3px 實色條、1.5px 外框；連接線同步改為 `search-highlight`。
  - 季軍賽卡：標頭寫「季軍賽」（不寫場次編號）＋時間或狀態徽章，放在決賽卡下方、不與決賽卡相連。
  - 季軍賽已取消（準決賽沒有產生勝隊）：標頭徽章「已取消」（`{colors.muted-foreground}`），兩列都 `{colors.muted-foreground}`、沒有比分 [ASSUMPTION]。
- **Bracket mark tag**（`bracket-mark-tag`）— 1px `currentColor` 外框、`{rounded.xs}`、`{typography.caption}`，貼在隊伍列右側。兩組：
  - 狀態標記：「輪空」「棄權」「取消資格」「退賽」；取消資格用 `{colors.destructive}`，其餘用 `{colors.muted-foreground}`。
  - 名次標記（賽事已結束後）：「冠軍」用 `{colors.brand}`；「亞軍」「季軍」用 `{colors.muted-foreground}` [ASSUMPTION]。不用金銀銅色（不加第三種品牌色）。
- **Podium**（`podium`）— 賽事已結束時置於對戰樹上方的 `Card`：冠軍一列（`{typography.heading-md}`＋「冠軍」名次標記），亞軍、季軍各一列（`{typography.body}`）。手機上直排、桌機三欄並列。不加光暈。
- **Team search** — 對戰樹上方 `Input`（`{rounded.md}`、`{colors.background}` 底），左側放大鏡 icon，placeholder「搜尋隊名」，有輸入時右側 ✕ 清除鈕；游標色 `primary`，輸入框右側命中數「找到 N 隊」用 `search-highlight` 文字；零結果時改為 `{colors.muted-foreground}` 文字。

### 場次頁（S4）

- **Match header** — S4 頁首，不放在 `Card` 內 [ASSUMPTION]：第一行返回連結（`←`＋賽事名稱，`{typography.body}`、`muted-foreground`）；第二行 `{typography.heading-lg}`「32 強 · M3」（季軍賽寫「季軍賽」、決賽寫「決賽 · M31」）＋場次狀態 Status badge；第三行 `{typography.caption}`「特戰英豪 · BO3 · 10/17（六）10:00」（遊戲 · 本輪 BO · 預定時間）。下方接 Score display。
- **Score display**（`score-display`）— 場次頁大比分 `{typography.score}`，`隊A 2 : 1 隊B`；兩隊隊名都向比分對齊；勝方粗體、敗方 `status-eliminated`；冒號用 `muted-foreground`。
- **Check-in panel**（`check-in-panel`）— S4 場次頁的 `Card`：兩欄（手機上下兩列）各一隊——隊名＋報到狀態（`{colors.status-confirmed}`「已報到 19:32」／`{colors.muted-foreground}`「未報到」）。下方為「報到」Button (primary)（手機滿版、高 ≥ `{spacing.touch-target}`）與一則 Countdown。
- **Score entry panel** — 場次頁裁判專用 `Card`，標題「比分登錄」（`{typography.heading-md}`），標題右側在可開始時帶 `status-live` 徽章「可開始」。表頭一列：「局」＋兩隊隊名（`{typography.overline}`、`muted-foreground`）。每局一列，列首「第 N 局」：
  - 未存的列：計分方式為 `win_loss` 時是兩個隊名切換鈕；為 `rounds` 時是兩個數字輸入框；列尾 outline 小按鈕「登錄」[ASSUMPTION]。
  - 已存的列：比分以等寬文字顯示（不是輸入框），列尾 `{colors.muted-foreground}`「已登錄」＋ghost 小按鈕「修改」[ASSUMPTION]。
  - 列下方 outline 小按鈕「新增一局」。
  - 底部：「系列結果預覽」＋`{typography.score}` 比分，右側 Button (primary)「送出系列結果」；停用時按鈕下方以 `{typography.caption}`、`muted-foreground` 寫停用原因 [ASSUMPTION]（停用條件與文字見 EXPERIENCE.md〈動作停用條件〉）。
  - 送出後（唯讀）：所有列只剩文字比分，沒有任何按鈕與「已登錄」；底部標籤改為「系列結果」，下方 `{typography.caption}`「{送出者顯示名稱} 送出 · 10/17（六）11:52」（FR-27 記錄送出者與時間）[ASSUMPTION]。
  - 示意：[`mockups/key-s4-match.html`](mockups/key-s4-match.html) (a)、(b)；稿與本文件的差異見 EXPERIENCE.md〈場次頁（S4）〉。
- **Result screenshot** — S4 左欄（各局列表下方）的 `Card`，標題「結算截圖」；已上傳：縮圖（`{rounded.md}`，最大寬 320px）；未上傳：一行 `{colors.muted-foreground}`「勝隊尚未上傳結算截圖」[ASSUMPTION]；勝隊隊長在同位置看到 Screenshot uploader（S22）。不另做「查看比分證據」按鈕。
- **Appeal action** — 申訴期 Countdown（`appeal` 變體）下方、滿版寬的 outline Button「提出申訴」[ASSUMPTION]（不用 primary：申訴是例外動作，不是預期的下一步）。
- **Same-round list**（同輪其他場次）— S4 右欄最下方的 `Card`，標題「同輪其他場次」；每場一個可點的小列：等寬場次編號＋Status badge，`flex-wrap` 排列 [ASSUMPTION]。

### 隊伍與報名

- **Registration status card** — `Card` 內：賽事名＋遊戲（`{typography.caption}`）、隊伍名、右側 Status badge（正取 `status-confirmed`、候補 `status-waitlist` 並寫「候補第 N 位」）。
- **Roster list**（`roster-list`）— S17 隊伍頁的名單，放在 `Card` 內，列間 1px `{colors.border}`。每人一列：顯示名稱（隊長加 outline `Badge`「隊長」）、`{typography.caption}` 一行「遊戲 ID · 段位 · 段位截圖：已上傳」；右側完成狀態——完成為 `{colors.status-confirmed}`「資料完成」，未完成為 `{colors.muted-foreground}`「缺：段位截圖、遊戲 ID」。隊長端每列（自己除外）右側 `⋯` `DropdownMenu`：「轉讓隊長」「移除隊員」（後者文字 `{colors.destructive}`）；非隊長的隊員在自己那列的 `⋯` 有「退出隊伍」，隊長在名單下方有 destructive outline Button「解散隊伍」。名單鎖定後三者都不顯示。名單下方：人數「4／6 人（先發 5）」與平均段位積分（含替補）。`< md` 不換成表格，維持同一清單。
- **Invite link field** — 唯讀 `Input`＋「複製連結」outline Button；連結失效時整列 `muted-foreground`＋說明文字。裁判邀請另在下方以 `{typography.caption}` 顯示到期時間。
- **Rank screenshot viewer**（`rank-screenshot-viewer`）— S29 主辦方專用 shadcn `Dialog`，最大寬 `{spacing.screenshot-viewer-max}`。標頭：隊名＋目前隊員（顯示名稱、遊戲 ID、申報段位）；主體：截圖以 contain 方式置於 `{colors.background}` 底、`{rounded.md}` 的框內；底部：「上一位」「下一位」outline Button 與「n／N」，右側 destructive outline Button「退回報名」。

## Do's and Don'ts

| Do | Don't |
|---|---|
| 深色為預設；`{colors.<token>}` 對應 shadcn `:root`、`{colors.<token>-dark}` 對應 `.dark` | 反轉 shadcn 的 `:root`／`.dark` 結構 |
| 與 shadcn 同名的 token 照 shadcn 語意用（`accent`＝中性 hover 底）；品牌紫只用 `{colors.brand}`，且只用在〈Colors〉列出的用途 | 把品牌紫寫進 shadcn 的 `--accent`，或讓任何 shadcn 元件的 hover／focus 底使用 `brand` |
| 青色霓虹只給「正在發生」與主要動作 | 用 `primary` 鋪大面積背景或裝飾 |
| 淘汰用灰（`status-eliminated`）＋刪除線 | 用紅色表示淘汰（紅只給取消資格與破壞性動作） |
| 每個狀態徽章都寫字（進行中、申訴中、已確認、候補第 3 位） | 只用顏色或圓點表示狀態 |
| 比分與倒數用等寬字（`{typography.score}`、`{typography.countdown}`） | 用比例字體顯示會跳動的數字 |
| 同一視窗發光元素 ≤ 3 種；輪詢更新用不發光的底色淡入 | 每張卡都加光暈或漸層 |
| 漸層只用在 logo | 把青→紫漸層用在按鈕、標題文字或背景 |
| 圓角、流線、跑道形 | 切角 HUD 框、斜體速度字（L4 未採用） |
