# Epic 3 Context: 組隊報名與名額分配

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

讓隊長為某個賽事組隊、隊員填寫參賽資料、隊長送出報名並鎖定名單，再由系統依校園賽的三階段規則（優先期代表隊 → 先搶期先到先得 → 截止補位）分配正取與候補，多人同時送出也不超收。名額分配是本專案最核心的業務規則與併發測試題材。期中做 3.1～3.6，只處理校園賽；撤回、退回、公開正取名單、自訂模式與隊員異動都擱置。

## Stories

- Story 3.1: 建立隊伍與邀請隊員
- Story 3.2: 選手填寫參賽資料
- Story 3.3: 送出報名與鎖定名單
- Story 3.4: 優先期結束自動分配
- Story 3.5: 先搶期即時分配
- Story 3.6: 報名截止與截止補位
- Story 3.7: 抽籤前撤回報名（期中擱置）
- Story 3.8: 主辦方檢視段位截圖與退回報名（期中擱置）
- Story 3.9: 公開正取名單與取消賽事通知（期中擱置）
- Story 3.10: 自訂模式的先到先得分配（期中擱置）
- Story 3.11: 隊員異動與解散隊伍（期中擱置）

## Requirements & Constraints

- **組隊**：隊伍只屬於一個賽事；同一帳號在同一賽事只能在一支隊伍（`ALREADY_IN_TOURNAMENT`）；主辦方不能在自己的賽事建隊或加入（`ORGANIZER_CANNOT_JOIN`）；須 Email 已驗證；人數不超過「先發＋替補」，額滿後邀請連結失效；未登入或未驗證的訪客先註冊驗證，再自動回到加入頁。
- **參賽資料**：遊戲 ID、段位（只能選賽事快照對照表內的）、段位截圖（JPG／PNG、5 MB 內，前端先驗、伺服器以 MIME 與大小再驗）。只能改自己的資料。隊伍平均段位積分＝名單上所有成員（含替補）的平均，取到小數第二位。
- **送出報名**：只有隊長、只在報名期間；人數不足先發、有人資料未填完、有隊員未設學校或學校不同時拒絕並逐項指出。送出後名單與參賽資料全部鎖定，隊伍邀請連結失效。送出時凍結學校、平均段位積分、送出時間。
- **分配規則**：
  - 優先期結束：各校平均段位積分最高的一隊為代表隊，代表隊超過名額時取前 N 隊正取，其餘候補。
  - 先搶期：優先期沒有報名、目前也沒有正取的學校，第一支送出的隊伍立即正取；其他一律候補。
  - 報名截止：剩餘名額由所有候補依平均段位積分補位，每校最多 2 隊正取，會超過的略過；補位後仍有空位就保留。
  - 所有排序同分時先送出者優先，再依報名 id。
- **候補順位**：「候補第 N 位」＝接下來陸續釋出名額時第幾個被遞補；照當下規則會被略過的候補沒有順位，顯示「候補・目前不在遞補順序中」與原因。
- **併發**：名額只剩 1 個時多隊同時送出只有 1 隊正取；整合測試在真實 PostgreSQL 平行送出 200 筆，正取不超過名額、沒有遺失或重複。
- **定時**：優先期結束與報名截止由 worker 在 1 分鐘內執行，重複執行結果不變；分配、補位要寫操作紀錄（操作者 `system`）。
- **期中範圍**：
  - 所有賽事都是校園賽，自訂模式的條件（`TOURNAMENT_INVITE_REQUIRED` 等）不做。
  - 撤回、退回、隊員異動不做，所以釋出名額的遞補不會發生。
  - 正取、候補、補位的通知只發事件。
  - 報名截止後賽事停在「報名截止」，等主辦方手動抽籤（4.2 擱置）。

## Technical Decisions

- registration 擁有 Team、TeamMember、Registration。Registration 在建立隊伍時產生（`forming`），狀態只能經 `mark_status` 修改；完整列舉 `forming/pending/accepted/waitlisted/rejected/withdrawn/drawn/retired/disqualified`，轉換表依期中文件 B 的報名狀態圖。
- 會改變名單或名額的操作（建隊、加入、填資料、送出、優先期結算、截止補位）都要先呼叫 tournaments 的 `lock_tournament()`，鎖住後才檢查身分、人數與名單；TeamMember 帶 `tournament_id`，以（tournament_id, account_id）唯一鍵當最後防線。
- 正取判定、候補排序、補位對象與每校上限只能寫在 `AllocationPolicy`（純函式，依賽事模式分支；`waitlist_order` 算順位），截止補位就是 `waitlist_order` 在截止後階段的前 N 位，不另寫排序。純函式的單元測試分支覆蓋率要達 90%。
- 段位積分存整數、平均存 `numeric(6,2)`。截圖經 `core.storage` 存入 volume，資料庫只存鍵值；段位截圖只有該賽事主辦方能下載，上傳者本人也看不到圖片。
- 隊長身分只看 `TeamMember.role`（`captain`／`player`），每隊恰好一位；送出等隊長動作由 service 呼叫 `core.authz.ensure_captain`。
- 其他模組會呼叫的公開函式（10/29～10/30 約定）：`get_team`（`TeamRead`）、`get_registration`（`RegistrationRead`）、`is_member`、`fill_at_deadline`（4.1 在開放報名中抽籤時呼叫），以及抽籤時取得正取隊伍、把報名標為已參賽的函式。送出前呼叫 tournaments「賽事是否仍可接受報名」。

## UX & Interaction Patterns

- **路由與畫面**：S16 建立隊伍 `Dialog`（S2 的「建立隊伍」）、S17 `/teams/$teamId`、S18 填寫資料（手機 `Sheet`、桌機 `Dialog`）、S19 `/join/$inviteToken`、S12 `/me/teams`（身分切換器「我的隊伍」）。
- **本 Epic 建立的元件**：Invite link field（3.1，期中由此建立，2.7 沿用）、Roster list（3.1：隊長加 outline Badge「隊長」、人數「4／6 人（先發 5）」）、Screenshot uploader（3.2：拖放區＋「選擇圖片」、縮圖預覽、進度、錯誤用 `destructive`）、Registration status card（3.1：賽事名＋遊戲、隊伍名、狀態徽章）。
- **狀態呈現**：「組隊中」「已送出・待分配」（優先期內附「優先期結束後分配名額」＋倒數）「正取」「候補第 N 位」或「候補・目前不在遞補順序中」＋原因（原因字串依 EXPERIENCE.md 固定介面字串）。先搶期送出後依伺服器回應直接顯示結果，不做 optimistic update。
- 「送出報名」停用時逐項列出缺什麼；確認對話框內文「送出後名單會鎖定，只有被主辦方退回才能修改。」；手機上滿版、高度至少 40px。報名截止後 S2 總覽顯示「抽籤準備中」。

## Cross-Story Dependencies

- 依賴 B 的 2.2（Tournament、`lock_tournament`、遊戲快照，10/31）與 2.4（S2 頁面、Countdown）。
- 3.1 → 3.2 → 3.3 → 3.4／3.5 → 3.6 依序疊加；`AllocationPolicy` 在 3.4 建立，3.5、3.6 擴充。
- **跨人交接**：3.1 的 Invite link field 要在 11/3 前完成（B 的 2.7 在等）；3.6 要在 11/12 前完成（D 的 4.1 接上截止補位，B 的 6.5 也在等）。6.4（同為 C）會用報名狀態判斷檢舉資格。
- 抽籤後的「已參賽」狀態由 competition（4.1）呼叫 registration 的函式設定。
