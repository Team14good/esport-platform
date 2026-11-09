# Epic 5 Context: 場次進行與晉級

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

讓場次從報到、逾時判棄權、裁判逐局登錄比分、送出系列結果，到申訴期滿自動確認與晉級，一路自動推進到產生冠亞季軍，不需人工推進賽程。這個 Epic 建立 S4 場次頁，是期中 Demo（11/18）「完整校園賽」的後半段。期中做 5.1～5.6、5.8；勝隊上傳結算截圖（5.7）擱置到期末。進度落後時，5.6、5.8 是可以延到期末的項目（延後順序：6.5 → 6.4 → 5.6 → 5.8 → 7.3）。

## Stories

- Story 5.1: 場次頁與隊長報到
- Story 5.2: 逾時判棄權
- Story 5.3: 裁判逐局登錄比分
- Story 5.4: 送出系列結果
- Story 5.5: 申訴期滿自動確認與一般晉級
- Story 5.6: 季軍賽、雙方棄權與賽事結束
- Story 5.7: 勝隊上傳結算截圖（期中擱置）
- Story 5.8: 場次頁與對戰樹結果標示

## Requirements & Constraints

- **報到**：預定開始前 30 分鐘起，只有該場兩隊的隊長能為自己的隊伍報到，不能取消；太早報到時 API 拒絕並回傳可報到時間。兩隊未確定時拒絕（`MATCH_TEAMS_PENDING`）。已有隊伍報到的場次不能再改時間。最早場次的報到時間到了，worker 把賽事由「賽程已公布」轉為「進行中」。
- **判棄權**：過了 `forfeit_deadline` 只有一隊報到 → 未報到者棄權（`forfeit`）；兩隊都沒報到 → `double_forfeit`、沒有勝隊。判定後直接進入申訴期（不經過進行中）並寫入申訴期截止時間，`submitted_by`／`submitted_at` 為空。`forfeit_deadline` 為空（兩隊未確定）的場次不會被選到。
- **登錄比分**：只有被指派的裁判（未指派時為該賽事主辦方）能登錄，兩隊都報到前拒絕。欄位依賽事快照的比分型態（`win_loss` 選勝隊、`rounds` 輸入回合數且不可平手）。第一局登錄後場次轉為「進行中」。送出前可用同一局號覆寫、系列結果跟著重算，操作紀錄記下修改前後。一隊達到勝局門檻後不能新增局。同時登錄同一場次不會互相覆蓋。進行中的場次不能改時間。
- **送出系列結果**：尚無一隊達門檻時不能送出；送出後鎖定（`outcome = played`），記錄送出者與時間，進入申訴期並寫入截止時間。之後裁判不能再改任何一局，只能經申訴更正。
- **自動確認與晉級**：申訴期滿仍為「申訴期」→ 轉為已確認、寫 `confirmed_at`，勝隊填入下一輪。申訴期滿前勝隊不出現在下一輪。已確認的場次之後不會被改動。
  - 下一場兩隊確定時設定棄權期限＝max（預定開始, 現在）＋棄權時限。
  - 某一方確定沒有隊伍時以 `walkover` 直接確認；兩方都沒有時以無勝隊確認，並繼續往下推。
  - 晉級後若指派的裁判是其中一隊的隊員，取消該場指派，改派前由主辦方代登。
- **季軍賽與結束**：準決賽敗隊進入季軍賽（正取少於 4 隊沒有）。雙方棄權的場次申訴期滿後兩隊皆淘汰，下一場以 `walkover` 確認。準決賽雙方棄權時，另一場勝隊以輪空奪冠，季軍賽 `voided`（outcome、勝隊為空），另一場敗隊為亞軍、季軍從缺。決賽與季軍賽都定案（已確認、已取消或不存在）後賽事為「已結束」，S27 唯讀。
- 所有定時工作在 1 分鐘內執行、每筆一個交易、重複執行沒有副作用；已取消或已結束的賽事一律略過。每個結果變更都寫操作紀錄（worker 記 `system`）。
- **期中範圍**：
  - 判棄權、下一場對手與時間、取消指派的通知，都只在同一交易發 outbox 事件，不登錄收件規則。
  - 退賽（4.5）不存在，5.1、5.3 中的退賽限制不做。
  - 申訴中的「棄權計時暫停」提示與申訴逾期提醒屬於 6.3（擱置）；前一場申訴未處理時，下一場兩隊本來就未確定，S4 只依 5.1 停用「報到」並說明原因。
  - 「本輪 BO」一律是建立賽事時的 BO（不做分輪 BO）。
  - 輪空空位期中只會來自雙方棄權與取消資格（無候補遞補）。
  - 「已取消賽事」的略過與拒絕照寫成防呆。

## Technical Decisions

- **狀態**：`MatchStatus` 為 `scheduled／live／appeal_window／appealed／confirmed／voided`（`voided` 只用於準決賽沒有勝隊時的季軍賽）；`MatchOutcome` 為 `played／forfeit／double_forfeit／walkover／disqualified`。狀態只能經 `transition_match` 修改；賽事狀態經 tournaments 的 `transition_tournament`。
- **Match 關鍵欄位**：`round_no`、`slot_no`、`is_third_place`、`team_a_id`／`team_b_id`、`referee_account_id`、`scheduled_at`、`winner_id`、`wins_a`／`wins_b`、`submitted_by`／`submitted_at`（只由 `submit_result` 寫入）、`confirmed_at`（只在轉為已確認時寫入）、`forfeit_deadline`、`appeal_deadline`、`next_match_id`。逐局存在 `MatchGame`（`game_no`、`winner_team_id`、`score_a`、`score_b`），報到存在 `CheckIn`。
- **服務**：MatchService 提供 `check_in／record_game／submit_result／start_forfeit_clock／forfeit_due／auto_confirm_expired／transition_match／lock_match`；BracketService 提供 `start_tournament／advance`。`start_tournament`、`forfeit_due`、`auto_confirm_expired` 由 worker 呼叫。
- **加鎖**：所有 Match 寫入先 `lock_match()`，鎖住後再檢查狀態與期限。會連鎖到下一場或賽事狀態的流程（自動確認、晉級），一開始先鎖賽事列，再依 id 遞增一次鎖住本場、下一場與季軍賽（`next_match_id` 不變，可事先讀出）。
- **權限**：裁判檢查只比對 `Match.referee_account_id` 與帳號 id；主辦方代登時先向 tournaments 取得賽事 schema 再比對擁有者。登錄前呼叫 tournaments「賽事是否仍可接受比分」。
- **遊戲無關**：勝局門檻＝（BO＋1）÷ 2；比分型態與欄位一律讀賽事設定快照，程式不依遊戲名稱或 id 分支。
- **事件**：送出發 `MatchResultSubmitted`、確認發 `MatchResultConfirmed`（過去式命名）。
- **公開 API**：不需登入的 API 只回傳 `PublicMatch` 這類 `Public` schema，段位截圖不出現在任何公開 API。
- **測試**：定時規則一律以替換 `core.clock` 推進時間測試，不等真實時間。
- **跨人實作邊界**：5.2（A）只在 competition 新增棄權判定的檔案與 worker 工作，不修改 D 的 `service.py` 既有函式，需要的查詢請 D 提供公開函式。5.8（A）的前端放在 `features/competition` 中與 D 的頁面不同的檔案。

## UX & Interaction Patterns

- **S4 路由**：`/tournaments/$tournamentId/matches/$matchId`，從對戰樹場次卡（整張可點）、S12、S13、S30 進入，未登入也能看。
- **S4 Match header**：
  - 第一行「← 賽事名稱」→ S3。
  - 第二行「32 強 · M3」（季軍賽寫「季軍賽」、決賽寫「決賽 · M31」）＋狀態徽章。
  - 第三行「特戰英豪 · BO3 · 10/17（六）10:00」。
  - 下接 Score display（`score` 字級「隊A 2 : 1 隊B」，勝方粗體、敗方 `status-eliminated`）。
- **S4 版面**：`≥ lg` 兩欄（左 `minmax(0,1fr)`、右 400px、欄距 20px）；`< lg` 單欄，目前的動作區排在頁首之後。
- **Check-in panel**：兩隊各一欄（手機上下兩列），顯示「已報到 19:32」或「未報到」；只有兩隊隊長看到本隊「報到」。開放前寫「{絕對時間} 起可報到」＋`muted` 倒數；開放後倒數為距預定開始（`live`），過了預定時間改為棄權期限（`appeal`）。手機上報到按鈕滿版、高度至少 40px。判棄權後收起，只留報到時間。S13 在兩隊都報到後標示「可開始」；S12 顯示下一場對手、時間與報到倒數。
- **Score entry panel**：只有被指派裁判（或代登的主辦方）看得到，取代公開的各局列表。
  - 標題「比分登錄」，兩隊報到前停用並寫「等待雙方報到」，可開始時旁邊顯示「可開始」。
  - 每局一列，同一時間只有一列在編輯；送出中該列停用；成功後改為文字比分＋「已登錄」＋「修改」。
  - 底部「系列結果預覽」只算已登錄的局；未達門檻時「送出系列結果」停用並寫「任一隊拿到 {N} 勝後才能送出」。
  - 確認對話框內文「送出後無法再修改，只能經由申訴更正。」。
  - 送出後唯讀，標籤改「系列結果」，寫「{送出者} 送出 · 10/17（六）11:52」；送出者不出現在公開列表。
- **申訴期**：顯示 `appeal` 倒數（唯一帶進度條的倒數）與「{絕對時間} 截止」，不顯示晉級；歸零後「已截止 · 系統處理中」並每 5 秒重抓。
- **5.8 結果標示**：
  - 狀態徽章：待開打、進行中、申訴期、已確認、已取消（申訴中由 6.1 加入）。
  - 對戰樹場次卡：進行中外框混 `status-live` 加光環、顯示目前勝局數；申訴期只顯示比分、不套勝負樣式；已確認時勝隊粗體、比分 `primary`，淘汰列 `status-eliminated` 加刪除線。
  - 「棄權」標記；雙方棄權時兩列都淘汰樣式，下一輪位置「—」＋「輪空」。
  - 「同輪其他場次」Card（等寬編號＋徽章；季軍賽與決賽互列；沒有其他場次時不顯示）。
  - S4 每 5 秒輪詢。
- **5.6 Podium**：賽事結束後放在 S2／S3 對戰樹上方，冠軍一列 `heading-md`，手機直排、桌機三欄，點隊名 → 該隊最後一場 S4。名次標記「冠軍」用 `brand`，亞軍、季軍用 `muted-foreground`，不用金銀銅色。沒有季軍賽時 Podium 只列冠亞；準決賽雙方棄權時決賽卡一隊帶「冠軍」、另一列「—」＋「輪空」，季軍賽卡以「已取消」徽章與灰色兩列呈現。

## Cross-Story Dependencies

- 依賴 Epic 4 的對戰表、場次排程（`schedule` 已為兩隊確定的場次設好棄權期限）與裁判指派（4.1、4.3、4.4）。
- **跨人交接**：
  - D 的 5.1（11/7）→ A 的 5.2。
  - D 的 5.4 與 A 的 5.2（11/11）→ B 的 6.1、D 的 5.6。
  - D 的 5.5（11/12）→ A 的 5.8、B 的 6.2 與 6.5。
- 6.5 的取消資格頂替由 B 寫在 competition 新增的檔案（`service.py` 只新增 `disqualify`），會沿用 5.5 的輪空確認與晉級函式，所以 5.5 要把這兩段做成可重用的函式；D 審查這部分的 PR。
- Epic 6 會呼叫 competition 的公開函式：`mark_appealed`、`uphold_result`／`correct_result`（沿用 5.5 的確認與晉級）、`replay_match`、`next_match_start`、`disqualify`；5.8 的「申訴中」徽章由 6.1 加入。
