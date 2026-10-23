---
input: architecture/architecture-se-final-project-2026-10-14/ARCHITECTURE-SPINE.md + c-d-design-groundwork.md
spines: DESIGN.md, EXPERIENCE.md（2026-10-15 版）
checked: 2026-10-15
---

# 輸入對照：架構骨幹＋C／D 打底稿

## (a) spine 已涵蓋的 UX 相關項目

| 架構項目 | spine 位置 |
|---|---|
| 技術堆疊 React 19、TanStack Router／Query、Tailwind 4、shadcn/ui | EXPERIENCE〈Foundation〉UI 系統；DESIGN frontmatter description |
| 前端結構 `src/routes/` 檔案路由 | EXPERIENCE〈Information Architecture〉路由欄（$ 參數寫法） |
| API 巢狀不超過兩層 | EXPERIENCE IA 註記「與 API 慣例一致」 |
| AD-10 前端隱藏按鈕不算權限 | EXPERIENCE〈Foundation〉權限、〈身分切換器〉「不改權限」 |
| AD-11 狀態以英文 `StrEnum` | EXPERIENCE Open Questions #18 |
| AD-13 UTC 儲存、前端顯示 Asia/Taipei | EXPERIENCE〈Foundation〉、〈倒數與時間〉 |
| AD-14 5 秒輪詢、無 WebSocket／SSE | EXPERIENCE〈Foundation〉即時性、〈對戰樹〉更新 |
| AD-7 worker 每 15～30 秒、NFR-4 1 分鐘內 | EXPERIENCE〈倒數與時間〉到期行為「前端不自行改狀態」 |
| AD-8 Email 失敗不影響主流程 | EXPERIENCE〈通知〉Email |
| AD-15 JPG／PNG 5 MB、MIME 驗證；申訴／檢舉附件只給主辦方 | EXPERIENCE Screenshot uploader（前端先檢、伺服器再驗）；申訴中「不顯示申訴內容給觀眾」 |
| AD-17 Mailpit | EXPERIENCE S37 |
| AD-18 比分型態 `win_loss`、`rounds` | EXPERIENCE Score entry panel（值完全一致） |
| AD-19 公開 API 不含 Email、學校、段位截圖 | EXPERIENCE 需求覆蓋 NFR-6、隊伍搜尋只搜隊名 |
| 錯誤格式 `detail.message`、422 | EXPERIENCE〈Foundation〉、〈通用狀態〉表單驗證錯誤 |
| 介面文字繁中，資料庫值與代碼英文 | EXPERIENCE〈Foundation〉語言 |
| D-1 Account `display_name`、`school`；主辦方／平台管理員旗標 | EXPERIENCE S10、〈身分切換器〉身分來源 |
| D-2 TournamentReferee 以賽事為範圍 | EXPERIENCE 身分切換器「裁判」 |
| D-4 Match `scheduled_at`、`forfeit_deadline`、`appeal_deadline`、`is_third_place`、單一 `referee_id` | EXPERIENCE〈倒數與時間〉表（欄位名一致）、〈對戰樹〉季軍賽 |
| D-5 申訴每隊每場一次；維持／更正、駁回／取消資格 | EXPERIENCE S32、S33、AlertDialog 理由必填 |
| D-6 Notification `title`、`link`、`read_at` | EXPERIENCE〈通知〉 |
| AD-9 操作紀錄只增不改、主辦方可查 | EXPERIENCE S34（唯讀） |

## (b) 未反映／被捨棄的項目

1. **RefereeInvitation `expires_at`**（D-2）：裁判邀請會過期；S23 失效原因清單（隊伍已滿／名單已鎖定／已在同賽事其他隊伍／連結無效）沒有「已過期」，S31 也未顯示有效期限或重新產生。
2. **AD-9 worker 操作者記為 `system`**：S34 未定義 `system` 的顯示名稱（例如「系統自動」）。
3. **D-5 申訴「每隊每場一次」**：S4 未寫本隊已申訴後的按鈕狀態（同 reconcile-prd b4）。
4. **D-4 Bracket `drawn_at`／〈暫不決定〉抽籤結果寫入操作紀錄**：S27／S34 未提示抽籤時間與抽籤紀錄可查，質性的「抽籤公正可查」意圖未在介面表達。
5. **D-2 `priority_hours`（以小時為單位）**：S26 未定優先期輸入單位；PRD 寫「預設 1 天」。

## (c) 衝突

| # | 架構 | spine | 判斷 |
|---|---|---|---|
| C1 | D-1 `IdentityService.register(email, password, school)`：註冊時就收學校 | S5「Email＋密碼註冊（FR-1）」；學校在 S10 帳號資料 | **欄位衝突**：註冊表單是否收學校（以及 `display_name`）需二擇一。學校影響 FR-13 同校檢查與 AD-12 快照，建議註冊即收。 |
| C2 | AD-15「段位截圖只有該賽事的主辦方能下載」 | S18 Screenshot uploader「上傳後顯示縮圖…可移除重選」；S17 選手可看「自己的資料」 | **權限衝突**：選手重新開啟 S18 時伺服器不會回傳自己的段位截圖；介面只能顯示「已上傳」與檔名，不能顯示縮圖。同理 S20／S21 送出後申請人看不到自己附件。 |
| C3 | D-3 `RegistrationService` 無移除隊員、轉讓隊長方法；D-1 `IdentityService` 無忘記／重設密碼、重寄驗證信；D-6 `NotificationService` 只有單則 `mark_read` | S17 移除隊員／轉讓隊長、S8／S9、S7 重寄驗證信、〈通知〉「全部標為已讀」 | **範圍衝突**：UX 追加的動作在物件設計沒有對應方法；轉讓隊長還牽涉 `MemberRole` 與 AD-10 `ensure_captain`。需回寫 D 文件與 Epic。 |
| C4 | D-6 `Notification` 無 `created_at` 欄位 | 〈通知〉每則顯示「相對時間（3 分鐘前）」並依新到舊排序 | 輕微：打底稿漏欄位；實作時需補。 |
| C5 | D-2 `Tournament` 無「報名資格」欄位，也無直播連結 | S26 建立賽事表單含報名資格（UJ-1 步驟 4）；Open Questions #8 直播連結 | 架構打底稿缺欄位（PRD FR-7 有報名資格）；UX 與 PRD 一致，需架構補。 |
| C6 | AD-14 輪詢只綁定「公開的對戰樹與場次頁」 | spine 另加：倒數到期後任何頁面每 5 秒重抓（最多 2 分鐘）、未讀數每 30 秒輪詢 | 輕微：未違反「不做推播通道」，但超出 AD-14 範圍；壓測（NFR-2）需把這些輪詢負載算進去。 |
| C7 | 時鐘只定義後端 `core.clock.now()` | 〈倒數與時間〉「用 API 回應的 `Date` 標頭計算本機時差」[ASSUMPTION] | 輕微：架構未承諾 `Date` 標頭準確或 CORS 可讀；需確認 FastAPI／Vite proxy 下前端讀得到。 |

## (d) 結論

技術堆疊、輪詢、時區、錯誤格式、比分型態列舉、公開資料限制都一致。需處理：**C1（註冊是否收學校）**、**C2（段位截圖與附件對上傳者不可見）**、**C3（UX 追加動作在 D 文件無方法）**。C4～C7 為打底稿缺欄位或範圍外延，實作或 D 文件定稿時補上即可。

## EXPERIENCE.md Open Questions 回補明細

自 EXPERIENCE.md〈Open Questions〉移入（2026-10-15 編修）；編號與 EXPERIENCE.md 一致，EXPERIENCE.md 只留一行索引。

### OQ 13. `Notification.created_at`

EXPERIENCE.md〈通知〉的相對時間與「新通知在最上方」（FR-38）需要建立時間；架構 D-6 `Notification` 沒有此欄位。回補：D-6。

**✅ 已回補（2026-10-15）**：D-6 `Notification` 新增 `created_at`；`list_for` 依此由新到舊排序。

### OQ 14. `Tournament` 報名資格欄位

PRD FR-7 有「報名資格」，S26 表單也收；架構 D-2 `Tournament` 沒有對應欄位。回補：D-2（欄位型別：自由文字或結構化條件未定）。

**✅ 已回補（2026-10-15）**：PRD 已將「報名資格」改為「賽事模式」（FR-39）；D-2 `Tournament` 新增 `mode: TournamentMode`（`campus`／`custom`，建立後不可改，AD-20）。

### OQ 15. 輪詢範圍超出 AD-14

EXPERIENCE.md 另加未讀數每 30 秒輪詢、倒數到期後任意頁每 5 秒重抓（最多 2 分鐘）。回補：AD-14 註記，並納入 NFR-2 壓測負載。

**✅ 已回補（2026-10-15）**：AD-14 修訂為只允許三種輪詢（對戰樹與場次頁 5 秒、未讀通知數 30 秒、倒數到期後當頁 5 秒最多 2 分鐘），並規定 NFR-2 壓測須包含三者。

### OQ 27. 確認者欄位

FR-27 要求記錄確認的裁判與時間，介面在唯讀面板顯示兩者；架構 D-4 `Match` 有 `confirmed_at`、`referee_id`，但沒有獨立的確認者欄位（未指派裁判、由主辦方代登並確認時 `referee_id` 不是確認者）。回補：D-4 `Match` 加 `confirmed_by`，或註明由 NFR-3 操作紀錄取得。

**✅ 已回補（2026-10-15）**：D-4 `Match` 新增 `confirmed_by`，與 `confirmed_at` 由 `confirm_result` 一起寫入（裁判或代登的主辦方；判棄權為空；申訴更正者記在 `Appeal.handled_by`）。
