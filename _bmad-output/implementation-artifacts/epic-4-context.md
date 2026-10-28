# Epic 4 Context: 抽籤與對戰表

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

由主辦方抽籤產生含輪空與季軍賽的單淘汰對戰表，依開賽日期與每輪間隔排定場次時間，指派裁判到場次，並讓觀眾在手機與桌機上看到每 5 秒更新的視覺化對戰樹。這個 Epic 建立 competition 模組的 Bracket 與 Match，是場次進行（Epic 5）與申訴取消資格（Epic 6）的基礎。期中做 4.1、4.3、4.4、4.6；自動抽籤、退賽遞補、隊伍搜尋擱置。

## Stories

- Story 4.1: 主辦方提前抽籤並產生對戰表
- Story 4.2: 報名截止時自動抽籤（期中擱置）
- Story 4.3: 排定與修改場次時間
- Story 4.4: 指派裁判到場次
- Story 4.5: 抽籤後退賽與候補遞補（期中擱置）
- Story 4.6: 視覺化對戰樹
- Story 4.7: 對戰樹隊伍搜尋與晉級路徑（期中擱置）

## Requirements & Constraints

- **抽籤**：
  - 期中只有主辦方手動抽籤，「開放報名中」或「報名截止」且正取至少 2 隊時可按。
  - 開放報名中按下時立即結束報名：仍在優先期內先完成優先期分配，再執行截止補位，最後抽籤。報名截止的賽事直接抽籤。
  - 抽籤只能執行一次，完成後賽事為「賽程已公布」，正取隊伍的報名轉為「已參賽」。
  - 正取不足 2 隊時「抽籤」停用並寫「正取不足 2 隊，無法抽籤」。
- **對戰表結構**：
  - P＝不小於正取隊數的最小 2 的次方，輪數 log₂P，第一輪輪空數＝P－正取數，輪空隊伍直接出現在第二輪。
  - 輪空位置平均分散：輪空數不超過 P ÷ 4 時，兩支輪空隊伍不在第二輪相遇。
  - 正取 4 隊以上才有季軍賽。8 隊為 3 輪、0 輪空、8 場；13 隊為 4 輪、3 輪空、13 場。
  - 重複產生時結構相同、只有對位不同。
- **排定時間**：同一輪排在同一時段，下一輪＝上一輪開始＋每輪間隔；「棄權時限＋BO × 每局預估時間＋申訴期」超過間隔時順延到這個下限並提示主辦方；不自動分批。
- **修改時間**：只限「待開打」場次；新時間不得早於現在，也不得晚於勝隊的下一場（決賽與季軍賽除外）。兩隊都確定的場次，棄權期限隨新時間重算。
- **棄權計時**：只有兩隊都確定的場次才設定 `forfeit_deadline`＝max（預定開始, 兩隊確定的時間）＋棄權時限。抽籤時為第一輪與兩支輪空隊伍相遇的場次設定。
- **指派裁判**：
  - 只能指派該賽事已接受邀請的裁判，每場一位，一位可以指派多場（含同時段）。
  - 不能指派到其隊伍參賽的場次。
  - 送出系列結果前可改派或收回；收回後由主辦方代登，已登錄的局保留。
- **公開對戰樹**：未登入可看；觀眾 10 秒內看到更新；375 px 手機可左右捲動。
- **期中範圍**：抽籤、改時間、指派、改派的通知只發事件；退賽與遞補（4.5）不會出現；所有輪次用同一個 BO（建立賽事時的值）。

## Technical Decisions

- competition 擁有 Bracket、Match、MatchGame、CheckIn、ResultScreenshot。`BracketGenerator.plan／assign` 是純函式（亂數由呼叫端注入，正式用 `secrets`），單元測試分支覆蓋率要達 90%。
- `BracketService.draw／schedule／reschedule／assign_referee／unassign_referee` 依 AD-6 先鎖賽事、再依 id 遞增鎖場次；抽籤結果、改時間、指派都寫操作紀錄。
- Match 狀態（`scheduled/live/appeal_window/appealed/confirmed/voided`）只能經 `transition_match` 修改；`start_forfeit_clock` 是設定 `forfeit_deadline` 的唯一入口。Match 直接存 `referee_account_id`。
- 跨模組：
  - 呼叫 registration 取得正取隊伍、執行優先期分配與截止補位（`fill_at_deadline`）、把報名標為已參賽。
  - 指派前呼叫 `TournamentService.is_referee()` 與 `RegistrationService.is_member()`。
  - 賽事狀態轉換經 tournaments 的 `transition_tournament`。
- 公開 API 只回傳 `PublicBracket`，不含 Email、學校或截圖鍵值。

## UX & Interaction Patterns

- **路由**：S3 `/tournaments/$tournamentId/bracket`（S2 的「對戰表」分頁，賽程已公布與進行中時為預設分頁）、S30 `…/$tournamentId/matches`（主辦方側欄「場次管理」）、S13 `/me/referee`（身分切換器「裁判」，多個賽事合併為一個項目）。
- **對戰樹版型**：
  - 每輪一欄，欄頭為輪次名（32 強…決賽）。
  - 欄寬 200px、連接線 28px、場次間距 18px、列高 32px。
  - 場次編號依輪次、同輪由上到下（輪空不佔編號）。
  - 季軍賽卡放在決賽下方，獨立顯示。
  - 1280px 桌機 32 隊不出現橫向捲軸；375 px 只有對戰樹容器橫向捲動、不縮放。
- **場次卡**：未開打時標頭「M3 · 10/18（日）13:00」、比分欄留空，待定列「M4 勝者」（季軍賽「M29 敗者」）；「輪空」以 Bracket mark tag 標示。
- **更新**：每 5 秒輪詢，背景分頁暫停、回前景立即重抓；保留捲動位置，有變動的卡片 `update-flash` 一次；連續 3 次失敗顯示連線中斷 banner。
- 抽籤確認對話框：開放報名中寫「抽籤只能執行一次，會立即結束報名。」，報名截止寫「抽籤只能執行一次。」。修改時間用 `Dialog`，時間選擇器只開放允許範圍。S13 空狀態「主辦方還沒有指派場次給你。」。

## Cross-Story Dependencies

- 依賴 B 的 2.2（Tournament、`lock_tournament`）與 C 的 3.x（正取隊伍）。4.1 的對戰表計算先寫成純函式與單元測試，3.6 完成（11/12）後再接上截止補位與真資料。
- **跨人交接**：D 的 4.1 要在 11/3 前完成（A 的 4.6 在等，4.6 可先用假資料）；4.4 需要 B 的 2.7（11/6）。
- 5.1 會為 4.3 補上「已有隊伍報到就不能改時間」；5.5 處理晉級後才出現的裁判衝突；6.5 的頂替會改動對戰表，4.6 的輪詢要能反映。
