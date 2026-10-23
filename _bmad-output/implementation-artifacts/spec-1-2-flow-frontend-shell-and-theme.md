---
title: 'Story 1.2：FLOW 前端外框與主題'
type: 'feature'
created: '2026-10-23'
status: 'done'
baseline_commit: 'b20d0dd7c8debda20362228c09547a1baf192cf6'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 前端目前只有 shadcn 預設中性色與一個狀態頁，沒有 FLOW 的主題、頂欄、錯誤呈現與錯誤頁；之後每個畫面都需要共用這套外框，否則各 Story 會各做一套。

**Approach:** 依 DESIGN.md frontmatter 把 T1 深空霓虹主題寫進 Tailwind／shadcn 變數，在根路由建立共用外框（頂欄、主題切換、手機選單、背景）、S38 錯誤頁，以及一組統一的 API 錯誤與成功回饋工具，並以前端單元測試與瀏覽器檢查驗證。

**Decisions（2026-10-23 使用者決定）：**
- 「登入」連到 `/login`、「註冊」連到 `/signup`；頁面在 Story 1.4、1.3 做好之前，點了會看到 S38 404，不做暫時頁面。
- spec 超過 1,600 tokens，使用者選擇保留完整 spec、不拆分。

## Boundaries & Constraints

**Always:**
- 色票、字級、圓角、間距一律取自 DESIGN.md frontmatter（`DESIGN.md:6-169`）；別名槽位依〈Colors〉別名表（`DESIGN.md:353-362`）以 `var()` 指向來源，不重複寫 hex。
- 深色為預設：`<html class="dark">`；主題只有 `dark`／`light` 兩種，存在 `localStorage`，不跟隨作業系統；載入時在繪製前套用已存的主題，不閃爍。
- 頂欄在所有頁面都相同（本 Story 只有未登入狀態；鈴鐺與身分切換器屬 Story 1.4）。
- 前端呼叫 API 只經 `src/client` 產生的 client；錯誤訊息照實顯示伺服器的 `detail.message`，不改寫成泛用文字。
- 介面文字全部繁體中文；按鈕用動詞＋名詞；不用驚嘆號與表情符號。
- 375 px 寬沒有橫向捲軸。

**Never:**
- 不載入 webfont；卡片不加陰影；不保留 shadcn 的 `--chart-*` 變數與 `system` 主題選項。
- 不做登入、註冊、鈴鐺、身分切換器、通知、Status badge、Data table、Sidebar 版面（屬 1.3～1.8）。
- 不修改後端；不手寫 fetch／axios；不修改 `_bmad/`、`docs/`、`.claude/`、規劃文件。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 首次造訪 | `localStorage` 沒有主題 | `<html>` 帶 `dark`；主題切換顯示太陽圖示（點了切到淺色），淺色時顯示月亮 | N/A |
| 切換主題 | 點主題切換 | 立即換成 light 並寫入 `localStorage`；重新整理後仍是 light | 存取 `localStorage` 失敗時仍可切換，只是不保存 |
| 無效的已存主題 | `localStorage` 值不是 `dark`／`light` | 視為 dark | N/A |
| 422 欄位錯誤 | 表單送出得到 422 `detail[]`（`loc` 末段為欄位名） | 對應欄位下方顯示該欄位的 `msg` | 找不到對應欄位的錯誤改顯示在表單頂部 `Alert` |
| 表單業務錯誤 | 表單送出得到 4xx `{"detail":{"code","message"}}` | 表單頂部 `Alert` 顯示 `message` | N/A |
| 非表單業務錯誤 | 一般動作得到 4xx 業務錯誤 | 錯誤 Toast 顯示 `message`，不會自動消失，要使用者關閉 | N/A |
| 連不到伺服器 | 沒有回應（網路錯誤） | 顯示「無法連線到伺服器」 | N/A |
| 成功回饋 | 動作成功 | 一句話的成功 Toast，3 秒後消失 | N/A |
| 不存在的網址 | 開啟 `/no-such-page` | S38 404：「找不到這個頁面。」＋「回到首頁」連結 | N/A |
| 沒有權限 | 路由載入時 API 回 403 | S38 403：「你沒有權限查看這個頁面。」＋「回到首頁」連結 | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/index.css` -- 目前是 shadcn neutral 色票與 `--chart-*`；整份改為 FLOW 主題：`:root`（light）、`.dark`、`@theme inline`（FLOW 色 `--color-brand`、`--color-status-*`、`--color-search-highlight`、字級 `--text-*` 含 line-height／weight／letter-spacing 子變數、`--radius-xs`、具名間距），背景光暈與格線依 `DESIGN.md:281-289`（實作可參考 `mockups/flow-logo-and-themes.html:58-64`）。
- `frontend/index.html` -- 已有 `class="dark"`、`lang="zh-Hant"`；加入繪製前套用主題的 inline script 與 favicon 連結。
- `frontend/src/components/theme-provider.tsx` -- shadcn 原版（含 `system`、storageKey `vite-ui-theme`）；改為只有 dark／light、預設 dark、key `flow-theme`，`localStorage` 存取包 try/catch，無效值視為 dark。
- `frontend/src/main.tsx` -- 已掛 `ThemeProvider defaultTheme="dark"` 與 `<Toaster richColors closeButton />`；保留，調整 Toaster 預設以符合 Toast 規則。
- `frontend/src/routes/__root.tsx` -- 目前只有 Outlet 與簡單 notFound；改為外框（頂欄＋內容區）並使用 S38 作為 `notFoundComponent` 與 403 的 `errorComponent`。
- `frontend/src/routes/index.tsx` -- 健康檢查狀態頁，保留在外框內；首次載入改用 `Skeleton`（不再顯示「檢查中」文字）。
- `frontend/src/components/ui/{sheet,skeleton,sonner,alert,button,card,loading-button}.tsx` -- shadcn 元件已存在可直接用；`card.tsx` 的陰影要移除；`button.tsx` 的 default variant 在 dark 加 primary 光暈（`DESIGN.md:182、408`）。
- 品牌素材 `_bmad-output/planning-artifacts/ux-designs/ux-se-final-project-2026-10-14/brand/`：`flow-logo-L2-lockup-{dark,light}.svg`（162×50）、`flow-logo-L2-mark.svg`（66×66，只有深色漸層）。三者都用 `id="flow-l2-grad"`，同頁內嵌會衝突，一律用 `<img>` 引用複製到 `frontend/public/brand/` 的檔案；淺色 mark 以淺色 lockup 的漸層（#0891B2→#7C3AED）衍生；單色 mark 依 mockup `:317-322` 的做法衍生。
- 頂欄規則：`DESIGN.md:173-177、425、446-450`；`EXPERIENCE.md:38`（公開導覽只有「賽事」→ `/`）、`:218`（logo 點擊回首頁）、`:393`（`< sm` 選單）。
- Toast／Alert／Skeleton／按鈕：`EXPERIENCE.md:22、163、219、233、247-248、345、360`。
- S38：`EXPERIENCE.md:107、363-364`（文件沒有文案，本 Story 訂定）。
- 目前 `frontend/` 沒有單元測試框架（只有 Playwright 設定、`frontend/tests/` 只有 `.gitkeep`）。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/index.css` -- 依 Code Map 重寫主題 token、別名、背景；移除 `--chart-*` -- UX-DR1～4。
- [x] `frontend/index.html`、`frontend/public/` -- 繪製前套用主題的 inline script；favicon：16px 單色版、32px 起漸層版（以 PNG 提供並標 `sizes`，另附 180px apple-touch-icon），單色版用固定顏色，不依賴 `currentColor` -- UX-DR5。
- [x] `frontend/public/brand/` -- 放入深淺色 lockup、深淺色 mark、單色 mark 的 SVG。
- [x] `frontend/src/components/theme-provider.tsx` -- 依 Code Map。
- [x] `frontend/src/components/layout/{TopBar,Logo,ThemeToggle,MobileMenu}.tsx` -- 頂欄：`≥ sm` 為 lockup（高 28px，點擊回 `/`）、「賽事」導覽（目前頁以 2px primary 底線標示）、主題切換、「登入」（ghost）、「註冊」（outline）；`< sm` 只有 mark、「登入」、選單按鈕，選單 `Sheet` 內有「註冊」、「賽事」、主題切換 -- UX-DR5～7、23。
- [x] `frontend/src/components/layout/ErrorPage.tsx`、`frontend/src/routes/__root.tsx` -- S38 404／403 與外框。
- [x] `frontend/src/lib/api-error.ts`、`frontend/src/lib/feedback.ts`、`frontend/src/components/common/FormErrorAlert.tsx` -- 依 Design Notes 的介面 -- UX-DR16、21。
- [x] `frontend/src/components/ui/{card,button}.tsx` -- 移除卡片陰影；primary 按鈕深色光暈。
- [x] `frontend/src/routes/index.tsx` -- 首次載入用形狀相符的 `Skeleton` -- UX-DR22。
- [x] `frontend/package.json`、`bun.lock`、`frontend/vitest.config.ts`、`frontend/tests/unit/` -- 加入 Vitest＋jsdom＋Testing Library（Bun 1.4 容器內安裝、更新根目錄 `bun.lock`），新增 `test:unit` script；測試涵蓋 I/O 矩陣每一列（主題、錯誤解析與呈現、Toast 時長、S38）。

**Acceptance Criteria:**
- Given 服務已啟動，when 在 1280 px 與 375 px 寬開啟首頁，then 頂欄內容符合上述兩種版面，且 `document.documentElement.scrollWidth` 不超過視窗寬度。
- Given 深色模式，when 檢視首頁，then 背景有右上 primary、左下 brand 光暈與 28px 格線；切到淺色後只有右上光暈、沒有格線。
- Given 任一頁面，when 檢查 `<head>`，then 有 16px（單色）與 32px（漸層）兩個 favicon 連結，且沒有載入任何 webfont。
- Given 前端專案，when 執行型別檢查、建置、Biome 與單元測試，then 全部通過。

## Implementation Notes

- `ApiError` 的 forbidden 多一個選填 `code`：所有 403 都歸為 forbidden，保留 `EMAIL_NOT_VERIFIED` 這類業務代碼；畫面仍照實顯示 message。
- 沒有伺服器訊息時的文字：`detail` 是字串就照實顯示（例如 FastAPI 預設的 "Not authenticated"）；其他情況顯示「伺服器發生錯誤（狀態碼）」或「發生未預期的錯誤」。
- `applyFieldErrors` 以 `getValues()` 的 key 判斷欄位是否存在，表單的每個欄位都要有 defaultValues。
- `src/lib/utils.ts` 以 `extendTailwindMerge` 登錄 FLOW 字級、陰影與具名間距；不然 `text-label` 會被當成文字顏色，和 `text-muted-foreground` 互相覆蓋。
- 單色 mark 與 16px favicon 固定為 #0891B2（spec 要求不依賴 `currentColor`），在深色與淺色分頁列上都看得到；PNG 以 headless Edge 從 SVG 轉出。
- 別名槽位在 `:root, .dark` 都宣告，讓套用 `.dark` 的元素重新解析 `var()`。
- 額外：`card.tsx` 圓角改為 `rounded-lg`（依 DESIGN.md card）；`sheet.tsx`、`sonner.tsx` 的英文 aria label 改成繁中；`playwright.config.ts` 忽略 `tests/unit/`；router 設 `defaultErrorComponent`，子路由出錯時頂欄仍保留。
- 主程式 chunk 約 501 kB，vite 會出現大小警告，不影響建置。

## Spec Change Log

## Review Triage Log

第 1 輪（Blind Hunter = BH、Edge Case Hunter = EC、Verification Gap = VG）。

| # | 來源 | 發現 | 判定 | 依據 | 去向 |
|---|------|------|------|------|------|
| 1 | EC | 422 的 `detail` 是空陣列時 `fields` 為空，`applyFieldErrors` 回 null，使用者看不到任何錯誤 | low | `asValidationFields` 對空陣列回傳 `{}`；改成回 null 讓它落到依狀態碼的訊息即可 | patch P1 |
| 2 | EC | `getErrorMessage` 遇到空的 `fields` 回空字串，錯誤 Toast 是空白的 | low | 同 #1 的根因；補預設訊息是直接修正 | patch P1 |
| 3 | EC | `ErrorPage` 沒給 `status` 也沒給 `message` 時標題是空的 | low | props 型別允許兩者都不給；`RouteErrorPage` 在 #1 的情況會傳空字串 | patch P1 |
| 4 | BH | `ErrorPageProps` 允許兩者都不給，`<h1>` 會是空的 | low | 同 #3 | patch P1 |
| 5 | BH | `RouteErrorPage` 沒有重試按鈕 | false | spec 的 S38 只要求一句說明加「回到首頁」，這不是缺陷而是新功能 | reject |
| 6 | BH | `notifyError` 沒有去重，加上 `duration: Infinity` 會越疊越多 | low | 同一個動作連續失敗時，每次都多一則要手動關閉的 Toast；加 `id` 是一行修正 | patch P2 |
| 7 | EC | 同上 | low | 同 #6 | patch P2 |
| 8 | VG | 錯誤 Toast 的關閉鈕只靠 `main.tsx` 的 `closeButton`，測試自己重新宣告，沒有驗到正式接線 | medium | 拿掉 `main.tsx` 的 `closeButton` 後，錯誤 Toast 會永遠關不掉，但沒有測試會失敗 | patch P2 |
| 9 | BH | 測試複製 `main.tsx` 的 Toaster 與 router 設定，沒有驗到正式接線 | medium（Toaster）／low（router） | Toaster 部分同 #8；router 的 `defaultErrorComponent` 和根路由的 `errorComponent` 互為後備，只拿掉其中一處畫面不變 | patch P2 |
| 10 | BH | `< sm` 頂欄的「登入」、選單鈕與主題切換只有 36px，小於自訂的 40px 觸控目標 | low | 這些按鈕確實是 `h-9`／`size-9`；手機使用者每次都會碰到；直接加 class 即可 | patch P3 |
| 11 | VG | 首頁的 Skeleton 與狀態文字分支沒有任何測試 | medium | 沒有測試掛載 `/`；把三元運算的兩支對調不會有測試失敗 | patch P4 |
| 12 | BH | 首頁載入時的 Skeleton 沒有 `role="status"`／`aria-busy`，螢幕閱讀器收不到訊息 | low | 確實只有一個沒有語意的 div；直接補屬性與 sr-only 文字 | patch P4 |
| 13 | VG | `cn()` 的 tailwind-merge 擴充沒有測試，`MobileMenu` 的 `h-touch-target` 依賴它 | low | 漏寫 `touch-target` 時會同時留下 `h-9 h-touch-target`，沒有測試會失敗 | patch P5 |
| 14 | BH | `ThemeProvider` 的 `storageKey` 可以自訂，但 `index.html` 寫死 `"flow-theme"` | low | 傳入其他 key 時，繪製前的主題會和 React 狀態不一致；拿掉這個 prop 是直接刪除 | patch P6 |
| 15 | EC | 同上 | low | 同 #14 | patch P6 |
| 16 | VG | 根目錄 `test` script 只跑 Playwright，Vitest 單元測試只能用 `test:unit` 執行，根目錄沒有對應 script | low | 根 `package.json` 確實沒有 `test:unit`；加一行即可 | patch P7 |
| 17 | EC | 422 的欄位名是 `constructor`、`toString` 這類 Object.prototype 的 key 時會被丟掉 | low | `key in fields` 對 `{}` 會找到原型上的屬性；改用 `Object.hasOwn` 是直接修正 | patch P8 |
| 18 | EC | 路由 loader 收到 API 404（資源不存在）時顯示伺服器原文，不是 S38 404 | medium | `RouteErrorPage` 只把 403 對到 S38；2.4 之後的賽事頁一定會碰到；EXPERIENCE 規定不存在的資源顯示 404 | patch P9 |
| 19 | EC | Playwright 的 `testIgnore: 'unit/**'` 會被補成 `**/unit/**`，路徑中有 unit 資料夾就會漏測 | low | 字串 glob 確實會被前綴 `**/`；改成只比對 `tests/unit/` 的 RegExp 是直接修正 | patch P10 |
| 20 | BH | 頂欄規則（`≥ sm` 用 lockup、`< sm` 用 mark、選單內容）沒有任何測試 | low | 已用瀏覽器在 1280 與 375 px 實測；jsdom 沒有 CSS 斷點，無法測顯示與隱藏，但選單 Sheet 的內容可以測 | patch P11（只測 Sheet 內容） |
| 21 | BH | 淺色 primary #0891B2 搭配白字的對比約 3.7:1，未達 WCAG AA 4.5:1；深色 `status-eliminated` 對比約 2.6:1 | medium | 數值與 DESIGN.md frontmatter 一致；根源是設計稿的色票，不是本 Story 的程式 | defer D1 |
| 22 | BH | 被取消的請求（`ERR_CANCELED`）會被當成網路錯誤 | low | 目前的 queryFn 沒有傳 `signal`，取消不會傳到 axios；React Query 取消時也不會觸發錯誤回呼；碰不到，修正要多一個分支 | reject |
| 23 | EC | 同上 | low | 同 #22 | reject |
| 24 | BH | 根路由的 `errorComponent` 又渲染一次外框，若錯誤來自外框本身會整頁空白 | low | 外框元件很簡單，很少在渲染時出錯；修正要再加一層錯誤邊界 | reject |
| 25 | EC | 同上 | low | 同 #24 | reject |
| 26 | BH | 422 只取 `loc` 最後一段，巢狀欄位會對到錯的欄位 | low | 這是凍結區塊 I/O 矩陣明定的行為（`loc` 末段為欄位名），修正要改 spec | reject |
| 27 | EC | 兩個 `loc` 的最後一段相同時，第二個會被丟掉或寫錯欄位 | low | 同 #26 | reject |
| 28 | BH | 401 落進 unknown，會顯示英文的 "Not authenticated"；5xx 帶 `{code, message}` 時訊息被換掉 | false | 照實顯示伺服器訊息正是 spec 的規則，401 的處理屬於 1.4；`BusinessError` 在 Story 1.1 就限定只能是 4xx，所以 5xx 不會帶 `{code, message}` | reject |
| 29 | EC | 5xx 帶業務訊息時被換成「伺服器發生錯誤（500）」 | false | 同 #28 | reject |
| 30 | BH | 沒有「跳到主要內容」的連結 | low | 不在 spec 與 UX 文件的要求內；屬於新功能 | reject |
| 31 | BH | `ThemeProvider` 沒有監聽 `storage` 事件，另一個分頁切換主題時這邊不會跟著變 | low | 確實沒有監聽；但很少同時開多個分頁還切換主題，修正要多一個監聽器 | reject |
| 32 | EC | 同上 | low | 同 #31 | reject |
| 33 | EC | 舊的 `vite-ui-theme` key 沒有遷移，已選淺色的使用者會變回深色 | false | 這個平台從未上線過，沒有任何使用者存過舊的 key | reject |

## Design Notes

**錯誤工具介面**（只依賴產生的 client 回傳的 axios 錯誤形狀）：

```ts
type ApiError =
  | { kind: "validation"; fields: Record<string, string> }   // 422，key 取 loc 的最後一段
  | { kind: "business"; code: string; message: string }      // 4xx 且 detail 是 {code, message}
  | { kind: "forbidden"; message: string }                    // 403（給 S38 用）
  | { kind: "network"; message: "無法連線到伺服器" }
  | { kind: "unknown"; message: string }
parseApiError(error: unknown): ApiError
applyFieldErrors(form, error): ApiError | null  // 把 422 寫進 react-hook-form，回傳寫不進欄位的部分
notifyError(error): void      // toast.error(message, { duration: Infinity })
notifySuccess(text): void     // toast.success(text, { duration: 3000 })
```

**主題不閃爍**：`index.html` 已預設 `class="dark"`；在 `<head>` 內聯一小段 script，讀 `localStorage["flow-theme"]`，值為 `light` 時在繪製前把 `dark` 換成 `light`，讀取失敗就維持 dark。

**S38 文案**：404「找不到這個頁面。」、403「你沒有權限查看這個頁面。」，連結「回到首頁」→ `/`。

## Verification

**Commands:**
- `docker compose up -d --build --wait` -- expected: 五個服務 running／healthy。
- `docker compose exec frontend bun run --filter frontend build` -- expected: tsc 與 vite build 成功。
- `docker compose exec frontend bunx biome check` -- expected: 無錯誤。
- `docker compose exec frontend bun run --filter frontend test:unit` -- expected: 全部通過，涵蓋 I/O 矩陣每一列。
- `docker compose exec backend bash scripts/test.sh` -- expected: 後端測試仍全數通過（本 Story 不改後端）。

**Manual checks (if no CLI):**
- 以瀏覽器在 1280 px 與 375 px 檢查頂欄、選單 Sheet、主題切換後重新整理仍保持、`/no-such-page` 顯示 S38、深淺色背景與 favicon。
