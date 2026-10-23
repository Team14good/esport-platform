---
input: briefs/brief-se-final-project-2026-10-14/brief.md + addendum.md
spines: DESIGN.md, EXPERIENCE.md（2026-10-15 版）
checked: 2026-10-15
---

# 輸入對照：產品簡介（brief）＋補充資料（addendum）

> brief 開頭已註明「細節以 PRD 為準」；以下凡 brief 與 PRD 不同、spine 跟隨 PRD 者，列為「已被 PRD 取代」而非待修衝突。

## (a) spine 已涵蓋的 UX 相關項目

| brief／addendum 項目 | spine 位置 |
|---|---|
| 痛點：表單、Excel、FB、Discord 東拼西湊 | DESIGN〈Brand & Style〉；EXPERIENCE〈Inspiration & Anti-patterns〉「現行做法」 |
| 主辦方「出事查得到」、每一步留紀錄 | DESIGN〈Brand & Style〉「出事時拿得出紀錄」；EXPERIENCE S34 |
| 隊長「不必翻 FB 與 Discord 找賽程」 | EXPERIENCE S12、〈Inspiration〉「S12 要一頁看完」 |
| 選手「一個頁面看完」 | EXPERIENCE S12（明文回應 brief） |
| 裁判「每場結果與證據都在同一頁」 | EXPERIENCE S4（各局＋結算截圖）、S24 |
| 平台管理員「新增遊戲不用改程式」 | EXPERIENCE S36 |
| 觀眾不登入看即時對戰表 | EXPERIENCE S3、UJ-4、〈Inspiration〉「不採用未登入註冊彈窗」 |
| 隊長是隊伍內身分，不是帳號類型 | EXPERIENCE〈身分切換器〉「隊長不是獨立身分」 |
| 申訴 30 分、遲到 15 分只能放寬不能縮短 | EXPERIENCE〈Interaction Primitives〉S28 輸入下限 |
| 三階段名額分配、候補 | EXPERIENCE〈State Patterns／報名狀態〉、S17、S29 |
| 抽籤、輪空、季軍賽 | EXPERIENCE〈對戰樹〉、Bracket mark tag |
| 願景：視覺化對戰樹、勝負／晉級／淘汰即時更新 | EXPERIENCE〈對戰樹〉；DESIGN bracket 元件 |
| 差異本質＝台灣校園賽規則做成可設定流程；Challonge／start.gg 為比較對象 | EXPERIENCE〈Inspiration〉「比較對象，不是風格參考」 |
| 範圍「不做」：直播（只放連結）、手機推播、金流 | EXPERIENCE〈Responsive & Platform〉、Open Questions #8 |
| addendum：LoL 記勝負、VALORANT 記回合 13:x | EXPERIENCE Score entry panel `win_loss`／`rounds` |
| addendum：抽籤無迴避 | EXPERIENCE〈對戰樹〉「不顯示任何種子或籤位編號」 |
| addendum：名單 5＋1、提交後鎖定 | EXPERIENCE UJ-2 步驟 5、AlertDialog 文案 |
| 坦白、平實的口吻（「坦白說，差異不在技術門檻」） | EXPERIENCE〈Voice and Tone〉「平實、短句」 |

## (b) 未反映／被捨棄的項目

1. **選手要查「戰績」**（brief〈使用者〉選手列）：S12 只列報名狀態、下一場對手與時間、報到倒數；沒有本隊已打場次的歷史結果清單。屬質性需求被部分捨棄。
2. **「從開放報名到公布對戰表不用開 Excel」**作為主辦方的成功畫面：S27 有狀態與待辦，但 spine 沒有把「不用開 Excel」轉成主辦方的關鍵時刻描述（UJ-1 高潮寫的是抽籤自動完成，可視為已涵蓋精神；文字未引用）。
3. **addendum「段位分數表：無排位 0」**：S18「段位（從對照表選）」未說明是否含「無排位」選項。
4. **addendum「雙方都無法開始 → 雙方淘汰」**：spine 沒有雙方棄權的對戰樹／場次頁呈現（PRD FR-25 也有，詳見 reconcile-prd.md）。
5. **addendum「每局每位選手 K／D／A」**：Score entry panel 無 KDA 欄位。PRD §7.2 已列為加分不做，屬有意捨棄。
6. **addendum「處罰異議 1 日內」「單場 2 次警告淘汰」「需審查在學資格」「教練簽名」**：spine 未反映；PRD §6 已明列不做，屬有意捨棄。
7. **brief 加分項目**（KDA、LoL API、雙敗／循環、地圖選取）：spine 未保留任何延伸位置；符合 PRD 範圍，屬有意捨棄。
8. **brief 待確認「Challonge、start.gg 是否真的缺少台灣校園賽規則」**：spine 直接採「差異在台灣校園賽規則」，未保留此不確定性。

## (c) 衝突

| # | brief／addendum | spine | 判斷 |
|---|---|---|---|
| C1 | 產品名「電競賽事管理平台」 | 產品名 `FLOW`（DESIGN／EXPERIENCE frontmatter） | 使用者決定的品牌名；brief 未更新。需在上游或課程文件註明兩者關係。 |
| C2 | 用詞「簽到」「檢錄」（brief〈解決方案〉4、addendum） | 一律「報到」（依 PRD §3） | 已被 PRD 名詞表取代；spine 正確。 |
| C3 | 棄權條件「預定開賽 15 分鐘後仍無法開始**或人數不足**」；addendum「不足 5 人棄權」 | 只依「未報到」判棄權（FR-25） | 已被 PRD 取代；spine 正確。 |
| C4 | 申訴向「裁判長」提出（addendum） | 由主辦方處理（S32） | brief 頂部已註明裁判長改為主辦方；spine 正確。 |

## (d) 結論

spine 忠實承接 brief 的意圖與語氣（統一一處、可追查、不登入看對戰樹、平實口吻）。四項衝突皆為 brief 已被 PRD 或使用者決定取代，無需改 spine。值得補的只有：S12 是否加入「本隊已打場次／戰績」（brief 選手需求），以及 S18 段位選單是否含「無排位」。
