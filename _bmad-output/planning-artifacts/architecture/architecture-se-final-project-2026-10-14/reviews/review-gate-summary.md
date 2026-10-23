# 審查關卡紀錄（2026-10-14）

> 審查方式：本次於主對話內依序執行（未另開子代理），先跑 lint，再逐一套用三個審查視角。

## 1. lint_spine.py
- 1 項 low：`{tournament_id}` 被判為可能未填的佔位符，實為 FastAPI 路徑參數範例 → 誤判，保留。

## 2. 版本查證（finalize_reviewers #1）
- 已查證：範本 master 的 pyproject.toml／package.json／compose.yml（Python 3.14、FastAPI ≥0.141.1、SQLModel ≥0.0.46、Alembic ≥1.19.1、psycopg 3.3、React 19.3、TS 6.0、Vite 8.3、TanStack、openapi-ts 0.97.3、Playwright 1.63.0、postgres:18）。
- 第三方來源：PostgreSQL 18.6（Neon、德文指南）、Locust 2.46.5（piwheels）、Bun 1.4.x（2026-08 Rust 改寫，含破壞性變更）。
- 發現：範本沒有 frontend Dockerfile、前端用 Bun（未固定版本）→ 已補「前端套件管理」慣例與 Bun 1.4 版本列；frontend 容器需自行撰寫 Dockerfile（列為假設，待組員確認）。
- 未固定：pytest、shadcn/ui、Mailpit 標「隨範本」，由範本鎖定檔決定，可接受。

## 3. 對抗式審查（finalize_reviewers #2）——兩個都守規則卻不相容的單元
| # | 漏洞 | 處理 |
|---|---|---|
| 1 | 申訴送出與 worker 申訴期滿自動確認同時發生；原 AD-6 只要求比分操作鎖 Match | 已修：AD-6 改為任何 Match 寫入都先鎖 Match，鎖後再查狀態與期限 |
| 2 | 一人把收件人放進事件內容、另一人讓 notifications 自己查，造成漏發或重複 | 已修：AD-8 規定事件只帶 id，收件人由 notifications 依 FR-37 對照表決定 |
| 3 | core.authz 若自行查詢 competition 的資料，core 就反向依賴模組 | 已修：AD-10 規定 authz 只接收已載入實體；AD-3 規定 core 不得 import 模組 |
| 4 | worker 一次交易處理多筆到期項目，其中一筆失敗就全部回滾 | 已修：AD-5 規定每筆到期項目／事件各自一個交易 |
| 5 | 示範資料直接 INSERT，略過快照與操作紀錄 | 已修：AD-17 規定示範資料經 service 建立 |
| 6 | 公開 API 沿用內部 schema 外洩個資 | 已修：新增 AD-19 |
| 7 | 依遊戲名稱寫分支 | 已修：新增 AD-18 |

## 4. 規格完整性（rubric walker）
- PRD 7 個功能群與 NFR-1～9 都有對應模組與 AD（功能 → 架構對照表）。
- 營運與環境：部署（AD-17）、設定（.env）、日誌／監控（暫不決定）、CI（暫不決定）、正式寄信與 HTTPS（暫不決定）皆有交代。
- NFR-7（375 px、繁中介面）屬 UX 層級，僅保留介面語言慣例；響應式版面交給 bmad-ux。
- 待使用者確認的推導項目見 memlog「distill 時補入」「reconcile 補入」。

結論：無 critical；7 項 high／medium 已自行修正；Bun 與 frontend Dockerfile 為唯一待確認假設。

---

# 審查關卡紀錄（2026-10-15，UX 回補更新）

> 範圍：AD-1、AD-6、AD-14 修訂與新增 AD-21；C／D 打底稿 D-1～D-4、D-6 的欄位與方法。審查於主對話內依序執行（與上次相同，未另開子代理）。

## 1. lint_spine.py
- 1 項 low：`{tournament_id}` 誤判（同上次），保留。

## 2. 版本查證（finalize_reviewers #1）
- 本次未引入新技術或版本；技術堆疊表不變，無需重新查證。

## 3. 對抗式審查（finalize_reviewers #2）
| # | 兩個守規則卻不相容的單元 | 處理 |
|---|---|---|
| 1 | 送出報名在加鎖前檢查名單，移除隊員同時發生，被移除者仍被寫進報名快照 | 已修：AD-6 規定名單異動先鎖 Tournament，送出報名在鎖住後才檢查；C-4.1 循序圖同步調整 |
| 2 | 重寄驗證信與重設密碼各自設計 token 存法與寄信路徑（一個直接寄、一個經 outbox） | 已修：新增 AD-21，統一 AccountToken 與 outbox 只寄 Email |
| 3 | notifications 依 AD-8「收件人依 FR-37 對照表」找不到驗證信／重設信的收件人 | 已修：AD-21 規定這兩種事件只寄 Email；PRD FR-37 同步註明 |
| 4 | 有人在個別頁面另加輪詢頻率，壓測未涵蓋 | 已修：AD-14 列舉三種輪詢且只有三種，並要求納入 NFR-2 壓測 |
| 5 | 有人用 `Team.captain_id`、有人用 `TeamMember.role` 判斷隊長，轉讓後兩邊不一致 | 已修：D-3 規定隊長只看 `TeamMember.role`，每隊恰好一位 |

## 4. 規格完整性（rubric walker）
- PRD 新增的 FR-40、FR-41 已列入功能 → 架構對照表；FR-1、FR-4、FR-7、FR-27、FR-38 的新可測結果在 D 文件有對應欄位或方法。
- 未處理（不在本次回補範圍）：自訂賽事的賽事報名連結 token 欄位、通知「全部標為已讀」、註冊是否收學校（reconcile-architecture C1）、段位截圖對上傳者不可見（C2）。
