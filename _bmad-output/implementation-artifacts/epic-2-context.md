# Epic 2 Context: 遊戲設定與賽事建立

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

讓平台管理員用設定（不改程式）支援任何兩隊對打的遊戲並維護學校清單；讓主辦方建立賽事、邀請裁判；讓觀眾不登入就能瀏覽賽事列表與賽事頁。這個 Epic 定下 Tournament 資料表、遊戲設定快照與主辦方後台外框，是報名（Epic 3）與賽程（Epic 4、5）的前提。期中只做 2.1、2.2、2.4、2.7，而且只開放校園賽。

## Stories

- Story 2.1: 平台管理員維護遊戲設定與學校清單
- Story 2.2: 主辦方建立賽事
- Story 2.3: 分輪設定 BO 數（期中擱置）
- Story 2.4: 公開賽事列表與賽事頁
- Story 2.5: 抽籤前修改賽事（期中擱置）
- Story 2.6: 取消賽事（期中擱置）
- Story 2.7: 邀請裁判
- Story 2.8: 主辦方查閱操作紀錄（期中擱置）

## Requirements & Constraints

- **遊戲設定**：先發人數、替補人數、預設 BO（只能 1、3、5、7，勝局門檻＝（BO＋1）÷ 2）、每局預估時間、比分型態（`win_loss`／`rounds`）、段位積分對照表。新增後主辦方立即可選，不改程式、不重新部署；修改預設值不影響已建立的賽事。非平台管理員呼叫新增、修改 API 回 403。
- **學校清單**：名稱不可重複；新增或修正名稱寫操作紀錄；所有同校檢查都以 `school_id` 比對，改名不影響既有關聯。
- **建立賽事**：只有主辦方能建立。選遊戲自動帶入人數與 BO（可修改）；棄權時限預設 15 分鐘（不得少於）、申訴期預設 30 分鐘（不得少於）、優先期預設 1 天。以下情況拒絕並指出欄位：報名截止晚於開賽日期、報名開始晚於截止、優先期結束晚於截止、名額少於 2、直播連結不是 http／https、每輪間隔少於「棄權時限＋BO × 每局預估時間＋申訴期」（顯示最小間隔）。報名開始已到時建立後為「開放報名」，否則為「尚未開放」，worker 在 1 分鐘內自動轉為開放報名。
- **公開頁**：不登入可看賽事列表（依狀態分組）與賽事頁；不需登入的 API 只回傳 `Public*` schema，不含 Email、學校或主辦方帳號資料。
- **裁判邀請**：連結 7 天有效；重新產生時同賽事未過期的舊邀請立即失效；受邀者須已登入且 Email 已驗證，接受後才成為該賽事的裁判；裁判身分只在該賽事有效。
- **期中範圍**：
  - 只開放校園賽：2.2 表單不顯示賽事模式，一律存 `campus`，但 `mode` 欄位照樣建立。賽事報名連結、`invite_token` 與所有「自訂」相關的驗收條件到期末再做。
  - 不做分輪 BO：每一輪都用建立賽事時的 BO。
  - 不做修改賽事、取消賽事、操作紀錄查閱頁面。「已取消」的狀態檢查可以照寫成防呆。
  - 通知只發事件（不登錄收件規則）。

## Technical Decisions

- tournaments 擁有 GameTitle、RankTier、Tournament、RoundSetting、RefereeInvitation、TournamentReferee。
- 建立賽事時把遊戲的人數、BO、每局預估時間、比分型態與段位對照表複製進賽事（`game_snapshot`），之後一律讀快照。程式中不得依遊戲名稱或 id 寫分支；整合測試用一款人數、BO、比分型態都不同的虛構遊戲驗證。
- Tournament 狀態（`upcoming/open/closed/published/ongoing/finished/cancelled`）只能經 `transition_tournament` 修改；`open_registration` 由 worker 呼叫，先鎖賽事並重新檢查，重複執行沒有副作用，操作者記為 `system`；測試以替換 `core.clock` 推進時間。
- 其他模組會呼叫的公開函式（名稱依架構初稿，實作後以程式為準）：`get_tournament`（回傳 `TournamentRead`）、`lock_tournament`（registration、competition 改名額或賽程前先鎖賽事）、`bo_for_round`（期中一律回傳賽事的 BO）、`is_referee`、「賽事是否仍可接受報名／比分」的檢查。這些介面要在 10/29～10/30 與 C、D 約定。
- `invite_referee` 產生邀請並讓舊邀請 `expires_at` 設為現在；`accept_invitation` 檢查到期。`core.authz` 判斷裁判身分只比對已載入的資料（A 賽事的裁判在 B 賽事判定為否，要有單元測試）。
- 建立賽事、轉為開放報名、學校清單異動都要寫操作紀錄。

## UX & Interaction Patterns

- **路由**：S1 `/`、S2 `/tournaments/$tournamentId`、S25 `/organizer`、S26 `/organizer/tournaments/new`、S27 `/organizer/tournaments/$tournamentId`、S31 `…/$tournamentId/referees`、S23 `/referee-invite/$inviteToken`、S36 `/admin/games`、`/admin/schools`。
- **主辦方賽事後台**：沿用 1.8 的 Sidebar 版面；2.2 建立賽事側欄，最上方「查看賽事頁」連到 S2，下方「總覽」，之後的 Story 把自己的頁面加進側欄。主辦方身分以 S25 為首頁。
- **2.4 建立的元件**：Countdown（說明文字＋等寬數字；24 小時以上「剩 2 天 5 小時」、1～24 小時「剩 5 小時 12 分」、未滿 1 小時 `mm:ss`；下方「{絕對時間} 截止」；變體 `muted`／`live`／`appeal`／`destructive`；歸零後顯示「已截止 · 系統處理中」並每 5 秒重抓，最多 2 分鐘）、Page banner（同頁最多一則）。S2 以 `Tabs` 呈現，2.4 先做「總覽」分頁。
- **Invite link field**：期中改由 Story 3.1 建立，2.7 沿用（唯讀輸入框＋「複製連結」、Toast「已複製」、到期時間與「連結已過期」＋「產生新連結」）。
- **空狀態文案**：S1「目前沒有公開的賽事。」、S25「你還沒有建立賽事。」＋「建立賽事」、S31「還沒有裁判接受邀請。複製邀請連結傳給裁判。」；過期邀請的 S23 寫「此裁判邀請已過期，請向主辦方索取新連結。」。
- 375 px 寬的手機上 S1、S2 沒有橫向捲軸。

## Cross-Story Dependencies

- 2.1、2.2 的畫面依賴 A 的 1.8（後台版面、Data table、AlertDialog，11/1 前完成）；2.2 依賴 2.1 的遊戲資料；2.2 需要 1.8 核准後的主辦方身分。
- **跨人交接**：2.2 的 Tournament 資料表要在 10/31 前完成，C（報名）與 D（對戰表）都在等；2.7 的 TournamentReferee 要在 11/6 前完成，D 的 4.4 指派裁判在等。2.7 需要 C 在 11/3 前完成 3.1 的 Invite link field。
- 2.4 的 Countdown 與 S2 頁面，會被 3.x（報名截止倒數、建立隊伍入口）、4.6（對戰表分頁）、6.4（「檢舉隊伍」入口）沿用。
