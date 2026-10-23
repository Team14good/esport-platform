# 補充資料：電競賽事管理平台

> 這裡放不適合寫進簡介、但後續 PRD／架構會用到的細節。

## 真實賽事規程參考（2024 第六屆大專盃電競錦標賽，特戰英豪團體賽）

來源：[競賽規程 PDF（中央大學體育室轉載）](https://pe.ncu.edu.tw/Uploads/2024-07-02/66839de8865eb.pdf)；主辦：中華民國電子競技運動協會（CTESA）、正修科技大學

| 項目 | 規程內容 | 對系統的意義 |
|---|---|---|
| 報名上限 | 64 隊，額滿為止 | 搶名額、不可超收 |
| 同校限制 | 1 校優先 1 隊；同校多隊以「選手牌位積分平均」高者代表；未滿 64 隊依報名先後補，1 校至多 2 隊 | 報名審核規則可參數化（段位→分數對照表） |
| 段位分數表 | 無排位 0、黑鐵 1＝5 … 輻能戰魂＝200 | 遊戲專屬設定資料 |
| 名單 | 6 人（5 先發＋1 替補），提交後不得更換；需審查在學資格 | 名單鎖定、資格審核 |
| 抽籤 | 人工或電腦抽籤，對戰隊伍無迴避 | 系統抽籤產生對戰表 |
| 賽制 | 全程 BO3 單淘汰 | 每場多局、局分 |
| 地圖選取 | 第一局隨機抽出首選方選圖、另一方選陣營；之後由前一局敗方選圖 | VALORANT 專屬流程（可列加分） |
| 檢錄 | 賽前 30 分鐘全員進指定 Discord 頻道向裁判報到；未檢錄不得上場，不足 5 人棄權 | 簽到截止規則 |
| 遲到 | 預定開始 15 分鐘後仍無法開始 → 棄權；雙方都無法開始 → 雙方淘汰 | 自動判負規則 |
| 結果 | 以伺服器結算畫面為準，由裁判紀錄；選手自行截圖存證 | 裁判登錄比分＋截圖佐證 |
| 申訴 | 比賽結束後 30 分鐘內向裁判長提出書面申訴（email 寄申訴書、需教練簽名）；處罰異議 1 日內 | 線上申訴、限時、狀態追蹤 |
| 警告 | 單場累積 2 次警告裁定淘汰 | 違規紀錄 |

## 遊戲 API 可行性（2026-10-14 查證）

- **VALORANT**：Riot 只開放給 Production 等級 API key，個人與開發 key 都不能用；應用須經審核，且玩家須透過 Riot Sign On（RSO）授權。來源：[Riot VALORANT API 文件](https://developer.riotgames.com/docs/valorant)、[Developer API Policy](https://support-developer.riotgames.com/hc/en-us/articles/22698769097107)、[VALORANT API 上線公告](https://www.riotgames.com/en/DevRel/valorant-api-launch)
- **League of Legends**：開發 key 每 24 小時過期、禁止用於正式環境；正式 key 需審核。比賽 KDA 可從 match-v5 的 kills／deaths／assists 欄位計算（未逐欄核對官方文件）。來源：[Riot Tournament API 說明](https://developer.riotgames.com/tournament-api.html)
- **結論**：課程專案不能依賴官方 API。比分與 KDA 以人工登錄為主；串 LoL API 自動帶入可列為加分或未來擴充。

## 初步資料需求（給 PRD／架構）

- 每場比賽 → 多局（BO3）→ 每局比分（LoL：勝負；VALORANT：回合數 13:x）
- 每局每位選手 K／D／A
- 截圖佐證附檔
