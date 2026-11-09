# disputes 模組介面約定（提議）

負責人：B 蘇采羚。依 CONTRIBUTING 6.5，先寫下 Epic 6 要用的公開函式、資料表與上游介面，讓 C（6.4）、D（審查 competition 的部分）照約定先寫。名稱與參數有異議，在 PR 留言或直接改這份；合併後以這份為準。

依據：`epic-6-context.md`、架構 `c-d-design-groundwork.md` D-5、[competition.md](competition.md)〈一〉、[tournaments.md](tournaments.md)。

分工（CONTRIBUTING 6.1、epic-6-context）：

| Story | 負責 | 內容 |
| --- | --- | --- |
| 6.1 提出申訴 | B | `file_appeal`；competition 新增 `mark_appealed` |
| 6.2 主辦方處理申訴 | B（D 審查 competition 端） | `resolve_appeals`、S32、S27 待處理、S4 處理結果；competition 新檔 `appeals.py` 新增 `uphold_result`、`correct_result`、`replay_match`（`service.py` 只新增公開函式） |
| 6.4 提出檢舉 | C | `file_report`；只新增檢舉相關檔案 |
| 6.5 查證檢舉與取消資格 | B | `resolve_report`、S33；competition 新增 `disqualify`（D 審查） |
| 6.3 逾期提醒 | 期中擱置 | `Appeal.reminded_at` 先保留欄位，不寫 worker |

2026-11-09（使用者）：Epic 6 的 6.1、6.2、6.5 全部由 B 實作，包含 competition 端的函式（D 審查）；取代 2026-11-08 與 D 協議的模組分工（當時改由 D 實作 6.2、6.5 的 competition 函式）；見 spec-6-2 Decisions。

## 一、資料表（disputes 擁有）

```python
class Appeal(SQLModel, table=True):        # appeal；6.1 建立
    id: UUID
    tournament_id: UUID                     # FK tournament.id；S32 依賽事列出、權限檢查用
    match_id: UUID                          # FK match.id（competition 的表，只建外鍵、不直接讀寫）
    team_id: UUID                           # 提出申訴的隊伍；同一隊對同一場只能有一筆未結案申訴（status='open' 的部分唯一索引；重新比賽後可再申訴）
    filed_by: UUID                          # 提出的隊長帳號
    filed_at: datetime
    description: str                        # 1～1000 字
    attachment_key: str | None              # core.storage 的 key；只有主辦方能下載
    status: AppealStatus                    # open → closed
    decision: AppealDecision | None         # upheld／corrected／rematch；結案時寫入
    reason: str | None                      # 處理理由，結案時必填
    handled_by: UUID | None                 # 處理的主辦方帳號，不覆寫 filed_by
    handled_at: datetime | None
    reminded_at: datetime | None            # 6.3 擱置；期中一律 null

class Report(SQLModel, table=True):        # report；6.4 建立（C），6.5 只更新處理欄位（B）
    id: UUID
    tournament_id: UUID
    reporter_team_id: UUID                  # 檢舉人的隊伍
    filed_by: UUID                          # 檢舉的隊長帳號
    reported_team_id: UUID                  # 被檢舉的隊伍；不能等於 reporter_team_id
    filed_at: datetime
    description: str                        # 1～1000 字
    attachment_key: str | None
    status: ReportStatus                    # open → dismissed／substantiated
    reason: str | None                      # 處理理由，結案時必填；Text（與申訴相同），長度上限由 6.5 驗證
    handled_by: UUID | None
    handled_at: datetime | None
```

`ReportRead`（6.4）不含 `attachment_key`，改以 `has_attachment: bool` 表示有沒有附件；另含 `reporter_team_name`、`reported_team_name` 供 S33 顯示。

`AppealStatus`、`AppealDecision`、`ReportStatus` 已在 `disputes/models.py`（2.x 前置），沿用不改。

## 二、disputes 提供的公開函式

都在 `disputes/service.py`，不 commit（AD-5）；權限：帳號層級在 router 的 `Depends`，賽事主辦方以 `core.authz.ensure_tournament_owner`，隊長由 disputes 比對成員角色或呼叫 registration 的 `is_captain`，不用 `core.authz.ensure_captain`（它回的是 `TEAM_CAPTAIN_REQUIRED`），兩者都回 403 `CAPTAIN_REQUIRED`（與 competition 報到一致，2026-11-09 B 與 C 協議）。

| 函式 | 誰會呼叫 | 說明 | 提供於 |
| --- | --- | --- | --- |
| `file_appeal(session, *, tournament_id, match_id, account_id, description, attachment: BinaryIO \| None, content_type: str \| None) -> FiledAppeal` | router（S21） | 說明去頭尾空白後 1～1000 字（422 `APPEAL_DESCRIPTION_REQUIRED`／`APPEAL_DESCRIPTION_TOO_LONG`，`loc` 為 `description`）；先以不鎖定的讀取確認場次屬於該賽事（404 `MATCH_NOT_FOUND`），再 `lock_tournament`、`lock_match`，鎖住後確認登入者是兩隊之一的隊長、賽事不是已結束或已取消且場次為申訴期或申訴中（否則 409 `APPEAL_NOT_ALLOWED`）、`now < appeal_deadline`、該隊沒有未結案的申訴（重新比賽後上一輪已結案，可再申訴；2026-11-09 使用者決定）；全部通過才存附件；建立申訴；場次仍在申訴期時呼叫 competition `mark_appealed`。寫 `appeal.filed`（`before` 為 `{match_status}`，`after` 含場次、隊伍、說明、`has_attachment`、新的 `match_status`），發 `AppealFiled`。回傳 `FiledAppeal {appeal: AppealRead, attachment_key}`：router 在交易提交失敗時刪掉剛存的附件（比照 3.2 參賽資料） | 6.1 |
| `get_appeal_state(session, *, tournament_id, match_id, account_id) -> AppealState` | router（S4 入口） | 只回本隊的狀態：`can_file`、`already_filed`、`deadline`（申訴期、申訴中才有值）、`reason`（`not_captain`／`not_appealable`／`deadline_passed`／`already_filed`，與 API 錯誤碼一一對應，順序同 `file_appeal`）；`already_filed` 不論其他原因都照實回傳，只看未結案的申訴；不透露另一隊有沒有申訴（申訴內容不公開）。場次不屬於該賽事 404 `MATCH_NOT_FOUND` | 6.1 |
| `list_tournament_appeals(session, *, tournament_id, actor_id) -> list[AppealGroup]` | router（S32） | 主辦方（403 `TOURNAMENT_OWNER_REQUIRED`）；依場次分組（有未結案申訴的場次在前，依最早一筆未結案申訴的提出時間；已結案的場次依最早提出時間）。`AppealGroup {match_id, match_code, round_name, is_third_place, scheduled_at, match_status, outcome, winner_id, wins_a, wins_b, score_type, best_of, games: list[PublicGame], team_a, team_b, has_open, appeals: list[AppealItem]}`，`AppealItem` 為 `AppealRead`＋`team_name`（場次取自 competition `get_public_match`；`team_name` 依 `appeal.team_id` 以 registration `get_team_names` 查，6.5 頂替後原申訴隊仍顯示隊名） | 6.2 |
| `resolve_appeals(session, *, tournament_id, match_id, actor_id, decision: AppealDecision, reason: str, games: Sequence[GameScoreIn] \| None, replay_at: datetime \| None) -> list[AppealRead]` | router（S32） | 順序：理由去頭尾空白後 1～1000 字（422 `APPEAL_REASON_REQUIRED`／`APPEAL_REASON_TOO_LONG`，`loc` 為 `reason`）→ `corrected` 缺 `games`（422 `APPEAL_GAMES_REQUIRED`）、`rematch` 缺 `replay_at`（422 `APPEAL_REPLAY_AT_REQUIRED`）→ 場次屬於該賽事（404 `MATCH_NOT_FOUND`）→ `lock_tournament` → 主辦方（403）→ `lock_match` → 有未結案申訴（409 `NO_OPEN_APPEALS`）→ competition 函式。同一場次未結案的申訴一次以相同決定與理由結案（寫 `handled_by`、`handled_at`，不改 `filed_by`）。`upheld` → `uphold_result`；`corrected` → `correct_result(games)`；`rematch` → `replay_match(replay_at)`（只用於 `outcome` 為 `forfeit`／`double_forfeit` 的場次）。寫一筆 `appeal.resolved`（`entity_type=match`；`before` 為 `{match_status, outcome, winner_id}`，更正時加 `games`、重賽時加 `scheduled_at`；`after` 含 `decision`、`reason`、`appeal_ids`、新的 `match_status`、`outcome`、`winner_id`，更正時加 `games`、重賽時加 `scheduled_at`），發 `AppealResolved`。另一隊申訴期限未到也可以處理。`upheld`／`corrected` 後場次已確認，任何一隊都不能再申訴；`rematch` 後場次回到待開打，重賽結果送出後兩隊都可以對重賽結果申訴（同一隊同一場只能有一筆未結案申訴） | 6.2 |
| `open_appeal_attachment(session, *, appeal_id, actor_id) -> tuple[BinaryIO, str]` | router | 只有該賽事主辦方（403 `TOURNAMENT_OWNER_REQUIRED`）；申訴不存在 404 `APPEAL_NOT_FOUND`、沒有附件 404 `FILE_NOT_FOUND`；回傳串流與 Content-Type | 6.1 |
| `list_reportable_teams(session, *, tournament_id, account_id) -> list[ReportableTeam]` | router（S20） | 檢舉人資格檢查後（錯誤同 `file_report`），回可被檢舉的隊伍 `{id, name, has_open_report}`（排除自己；`has_open_report`＝本隊對它已有處理中的檢舉），依隊名排序 | 6.4（C） |
| `file_report(session, *, tournament_id, account_id, reported_team_id, description, attachment, content_type) -> FiledReport` | router（S20） | 先 `lock_tournament`。賽事未結束；檢舉人是報名狀態為 `pending`／`accepted`／`waitlisted`／`drawn` 的隊伍隊長；對象同樣四種狀態且不是自己；同一隊對同一對象已有處理中的檢舉時拒絕（結案後可再檢舉）；說明去頭尾空白後 1～1000 字（code point）；全部通過才存附件；寫 `report.filed`，發 `ReportFiled`。回傳 `FiledReport {report: ReportRead, attachment_key}`：router 在交易提交失敗時刪掉剛存的附件 | 6.4（C） |
| `list_tournament_reports(session, *, tournament_id, actor_id) -> list[ReportRead]` | router（S33） | 主辦方；處理中在前，各組依 `filed_at` 由舊到新、再依 id | 6.4（C） |
| `resolve_report(session, *, tournament_id, report_id, actor_id, substantiated: bool, reason: str) -> ReportRead` | router（S33） | 主辦方；駁回只結案；屬實時賽事未結束才呼叫 competition `disqualify`，已結束只記錄屬實。寫 `report.resolved`，發 `ReportResolved` | 6.5 |
| `open_report_attachment(session, *, report_id, actor_id) -> tuple[BinaryIO, str]` | router | 只有該賽事主辦方 | 6.4（C） |
| `count_open_disputes(session, *, tournament_id, actor_id) -> OpenDisputes` | router（S27 待處理清單） | 主辦方（403）。`{appeals, reports, earliest_deadline, items: list[OpenDisputeItem]}`；`OpenDisputeItem {kind: appeal\|report, id, match_id, match_code, filed_at, deadline}`，依處理期限由近到遠。處理期限＝等待結果的下一場（勝隊、敗隊去的場次中最早）的預定時間；決賽與季軍賽為申訴提出後 1 小時。6.5 接上前 `reports` 為 0、沒有檢舉項目（檢舉的處理期限與排序由 6.5 決定，2026-11-09 使用者決定）。S27 前端直接呼叫 disputes 的 API（tournaments 不能呼叫 disputes） | 6.2 |
| `get_public_appeal_result(session, *, tournament_id, match_id) -> PublicAppealResult` | router（S4，公開） | `{decision: upheld\|corrected\|null}`：場次已確認且最後一次處理是維持或更正時才有值；未處理、未確認、重新比賽為 null。不含申訴內容（AD-19）。場次不屬於該賽事 404 `MATCH_NOT_FOUND` | 6.2 |
| `get_replay_window(session, *, tournament_id, match_id, actor_id) -> RescheduleInfo` | router（S32 重新比賽） | 主辦方（403）、場次屬於該賽事（404）後呼叫 competition `get_replay_window` | 6.2 |

### API（提議）

| 方法與路徑 | 權限 | 說明 |
| --- | --- | --- |
| `GET /api/v1/tournaments/{tid}/matches/{mid}/appeal-state` | `CurrentAccount` | `AppealState` |
| `POST /api/v1/tournaments/{tid}/matches/{mid}/appeals` | `VerifiedAccount` | multipart：`description`、`attachment?`；201 `AppealRead` |
| `GET /api/v1/organizer/tournaments/{tid}/appeals` | `Organizer` | S32 |
| `POST /api/v1/organizer/tournaments/{tid}/matches/{mid}/appeal-resolution` | `Organizer` | `AppealResolveIn {decision, reason, games?, replay_at?}`（`replay_at` 必須帶時區）；200 `list[AppealRead]` |
| `GET /api/v1/organizer/tournaments/{tid}/matches/{mid}/replay-window` | `Organizer` | `RescheduleInfo`（S32 重新比賽的時間範圍） |
| `GET /api/v1/tournaments/{tid}/matches/{mid}/appeal-result` | 不需登入 | `PublicAppealResult`（S4） |
| `GET /api/v1/organizer/appeals/{appeal_id}/attachment` | `Organizer` | 下載附件 |
| `GET /api/v1/tournaments/{tid}/reportable-teams` | `VerifiedAccount` | S20 選單 |
| `POST /api/v1/tournaments/{tid}/reports` | `VerifiedAccount` | multipart：`reported_team_id`、`description`（預設空字串）、`attachment?`（空檔視為未附）；201 `ReportRead` |
| `GET /api/v1/organizer/tournaments/{tid}/reports` | `Organizer` | S33 |
| `POST /api/v1/organizer/reports/{report_id}/resolution` | `Organizer` | `{substantiated, reason}` |
| `GET /api/v1/organizer/reports/{report_id}/attachment` | `Organizer` | 下載附件 |
| `GET /api/v1/organizer/tournaments/{tid}/open-disputes` | `Organizer` | S27 待處理 |

錯誤碼（提議）：`APPEAL_DEADLINE_PASSED` 409、`APPEAL_NOT_ALLOWED` 409（賽事已結束或已取消、場次不是申訴期／申訴中）、`APPEAL_DESCRIPTION_REQUIRED`／`APPEAL_DESCRIPTION_TOO_LONG` 422（申訴說明空白或超過 1000 字）、`APPEAL_ALREADY_FILED` 409、`CAPTAIN_REQUIRED` 403（沿用）、`NO_OPEN_APPEALS` 409、`REPLAY_ONLY_FOR_FORFEIT` 409、`CORRECTION_ONLY_FOR_PLAYED` 409（6.2：更正結果只用於 `outcome=played`）、`APPEAL_REASON_REQUIRED`／`APPEAL_REASON_TOO_LONG`／`APPEAL_GAMES_REQUIRED`／`APPEAL_REPLAY_AT_REQUIRED` 422（6.2）、`REPORT_NOT_ALLOWED` 409（檢舉人或對象的報名狀態不符、賽事已結束）、`REPORT_SELF` 422、`REPORT_ALREADY_FILED` 409（同一隊對同一對象已有處理中的檢舉）、`REPORT_DESCRIPTION_INVALID` 422（欄位錯誤，`loc` 為 `body.description`）、`REPORT_ALREADY_RESOLVED` 409、`APPEAL_NOT_FOUND`／`REPORT_NOT_FOUND` 404；附件沿用 `core.storage` 的錯誤（格式、大小）。

### 事件（`core.events.publish`，期中只發不通知）

| 事件 | payload | 時機 |
| --- | --- | --- |
| `AppealFiled` | `appeal_id`, `match_id`, `team_id` | 6.1 提出申訴 |
| `AppealResolved` | `match_id`, `decision` | 6.2 結案（同一場一次） |
| `ReportFiled` | `report_id`, `tournament_id`, `reported_team_id` | 6.4 提出檢舉 |
| `ReportResolved` | `report_id`, `substantiated` | 6.5 結案 |

## 三、competition 新增的申訴、取消資格函式

2026-11-09 起：下表五個函式（`mark_appealed`、`uphold_result`、`correct_result`、`replay_match`、`disqualify`）都由 B 新增，D 審查；取代 2026-11-08 改由 D 實作後四個的協議。

B 依 CONTRIBUTING 6.6 把這些函式寫在 competition **新增的檔案**（`competition/appeals.py`、`competition/disqualification.py`），`service.py` 只新增公開函式（以函式內 import 呼叫，避免循環 import），不改 D 的既有函式；需要改 D 的既有函式時先在 PR 問 D。例外：6.2 依 AC「一方或雙方」把 D 的 `get_replay_window` 由只接受 `forfeit` 改為也接受 `double_forfeit`（與 `replay_match` 一致），在 PR 說明列出。所有函式的呼叫端都先 `lock_tournament`，函式內 `lock_match` 並以鎖住後的狀態判斷（AD-6）。

| 函式 | 呼叫者 | 說明 | 用到 D 的 |
| --- | --- | --- | --- |
| `mark_appealed(session, *, match_id) -> MatchRead` | disputes `file_appeal` | `appeal_window` → `appealed`；已是 `appealed` 不動（第二隊申訴）；其他狀態 `MATCH_INVALID_TRANSITION` 409。不改 `appeal_deadline`（另一隊在原期限內仍可申訴）；worker `auto_confirm_expired` 只挑申訴期，申訴中的場次等主辦方處理 | `lock_match`、`transition_match` |
| `uphold_result(session, *, match_id, actor_id) -> MatchRead` | disputes `resolve_appeals` | 只接受 `appealed`；沿用已寫入的 outcome、勝隊呼叫 `confirm_match`（內含晉級） | `confirm_match` |
| `correct_result(session, *, match_id, games: Sequence[GameScoreIn], actor_id) -> CorrectionResult` | disputes `resolve_appeals` | 只接受 `appealed`、`outcome=played`（否則 409 `CORRECTION_ONLY_FOR_PLAYED`）；以 `scoring.py` 驗證整組新的各局（與 5.3 相同規則），並套用 5.4 送出時的兩個檢查：未達門檻 `SERIES_NOT_DECIDED`、有多餘的局 `REDUNDANT_GAMES`（不能更正成沒打完的系列）；通過後整份替換 `match_game`（competition repository **新增** `delete_games`）、重算勝局數與勝隊，再 `confirm_match`；回傳 `CorrectionResult {before_games: list[PublicGame], after_games: list[PublicGame], winner_id}` 給操作紀錄。不另寫操作紀錄（前後各局記在 disputes 的 `appeal.resolved`） | `scoring.series`、`confirm_match` |
| `replay_match(session, *, match_id, scheduled_at, actor_id) -> ReplayCleared` | disputes `resolve_appeals` | 只接受 `appealed`、`outcome` 為 `forfeit`／`double_forfeit`（6.2 依 AC「一方或雙方」；其他 409 `REPLAY_ONLY_FOR_FORFEIT`）；賽事不是 `published`／`ongoing` 時 409 `TOURNAMENT_NOT_RESCHEDULABLE`（與 `get_replay_window` 一致）；`scheduled_at` 以 D 的 ★ `check_replay_time` 檢查（與 4.3 改期同一個 `_reschedule_window`，錯誤碼與訊息也相同）；`clear_for_replay` → `transition_match(→ scheduled)` → 寫入新時間 → `start_forfeit_clock` → 操作紀錄 `match.replay_scheduled` → 發 `MatchRescheduled`；同一交易。裁判保留（`clear_for_replay` 不動裁判，與 4.4 一致） | `clear_for_replay`、`transition_match`、`start_forfeit_clock`、★ `check_replay_time` |
| `disqualify(session, *, tournament_id, team_id, actor_id) -> DisqualifyResult` | disputes `resolve_report` | 依 epic-6-context〈取消資格（期中版）〉的 7 種情況頂替；抽籤前只改報名狀態（registration `mark_status(→ disqualified)`）。頂替改變場次的隊伍後：**重新檢查裁判衝突**（頂替進來的隊伍含該場裁判時收回指派，寫 `match.referee_unassigned`、操作者為系統、發 `RefereeUnassigned`，與 `advance` 相同）；兩隊湊齊的場次呼叫 `start_forfeit_clock`。未結案的該場申訴由 disputes 一併結案（`DisqualifyResult` 回傳受影響的 `match_id`） | `list_team_matches`、`confirm_walkover`、`advance`、`confirm_match`、`start_forfeit_clock`、★ `unassign_referee_if_member` |

`disqualify`（6.5 第一階段，2026-11-08 實作；規則見 `competition/disqualification.py` 與 spec-6-5-disqualify.md）：

```python
class DisqualifyResult(BaseModel):          # competition/models.py
    affected_match_ids: list[UUID]          # 直接被取消資格改動的場次（判對手獲勝、頂替、季軍賽移出隊伍），依處理順序；
                                            # 之後由晉級推進連帶改動的場次不列入；抽籤前或只改報名狀態時為 []
    replacement_team_id: UUID | None        # 頂替原位置的隊伍；沒有頂替為 null
```

- 先 `lock_tournament`，再依 id 遞增鎖住對戰表全部場次，判斷完成後才寫入（AD-6）。賽事已結束或已取消 409 `TOURNAMENT_FINISHED`／`TOURNAMENT_CANCELLED`；隊伍不屬於該賽事 404 `REGISTRATION_NOT_FOUND`；已取消資格 409 `TEAM_ALREADY_DISQUALIFIED`；拒絕時不改資料。
- 報名經 registration 新增的 `disqualify_registration(session, *, team_id, actor_id) -> RegistrationRead`（內部用 `mark_status`）改為 `disqualified`；報名狀態不能轉為取消資格（組隊中、退回、撤回、退賽）時拋 409 `REGISTRATION_INVALID_TRANSITION`，不改資料。
- 頂替時刪除被取消資格隊伍在該場的報到紀錄（決賽頂替時也刪除頂替隊伍在季軍賽的報到）；頂替後兩隊湊齊則 `start_forfeit_clock` 並發 `MatchOpponentsDecided`（與晉級填位相同）。
- 兩隊都在場的場次判對手獲勝時 outcome 為 `disqualified`（不用 walkover）；待開打的場次走 `scheduled → confirmed` 再 `advance`，已開打的走 `confirm_match`。操作紀錄：確認為 `match.confirmed`、換隊為 `match.teams_changed`（`before`／`after` 含 `team_a_id`、`team_b_id`，`after` 另含 `disqualified_team_id`），操作者為 `actor_id`；隨後晉級推進與季軍賽的 walkover 確認操作者為系統。
- 對手還沒確定、需要把一方標記為不會有隊伍的情況（輪空入座等另一場勝隊、決賽要由準決賽敗隊頂替而季軍賽另一方未定）拒絕：409 `DISQUALIFY_OPPONENT_PENDING`「對手尚未確定，請等對手確定後再取消資格。」，不改資料（2026-11-09 D 決定；progression 支援列為期中後，見 deferred-work.md）。

順序（D 確認）：`uphold_result`、`correct_result`、`replay_match` 都是 `lock_match` → 狀態（只接受 `appealed`）→ outcome 檢查 → 其他，與 `confirm_match` 一致。

## 四、6.x 需要的上游介面（請 C、D 確認）

### competition（D）

已在 competition.md〈一〉：`get_match`、`lock_match`、`transition_match`、`start_forfeit_clock`、`confirm_match`、`advance`、`confirm_walkover`、`clear_for_replay`、`list_team_matches`；`MatchRead` 已有 `outcome`（6.2 判斷「重新比賽只用於棄權」）。場次狀態轉換表已允許 `appeal_window → appealed`、`appealed → confirmed／scheduled`。

D 新增的 ★（只新增公開函式、不改既有函式；6.2 開工前合併，D 2026-11-05 在 #55 提議）：

| 函式 | 用在 | 需要的內容 |
| --- | --- | --- |
| ★ `check_replay_time(session, *, tournament, match, scheduled_at) -> None` | 6.2 `replay_match` | 用 4.3 改期同一個 `_reschedule_window` 檢查；不符合拋 `RESCHEDULE_BEFORE_NOW`／`RESCHEDULE_BEFORE_FEEDER`／`RESCHEDULE_AFTER_NEXT_MATCH`／`RESCHEDULE_NO_VALID_TIME`（409，訊息附台北時間範圍）；不檢查場次狀態與報到（重賽時是 `appealed`、報到剛被清掉） |
| ★ `get_replay_window(session, *, match_id) -> RescheduleInfo` | 6.2 S32 時間選擇器 | 同一個範圍（最早、最晚） |
| ★ `unassign_referee_if_member(session, *, match) -> None` | 6.5 `disqualify` | 把 `advance` 用的 `_unassign_if_member` 包成公開函式：該場裁判是任一隊隊員時收回、寫 `match.referee_unassigned`（系統）、發 `RefereeUnassigned`。只對 `scheduled`／`live` 呼叫，其他狀態拋 `ValueError`；6.5 要在 `confirm_walkover`／`confirm_match` 之前呼叫 |

申訴拖久時，下一場的預定時間可能已早於重賽最早可選時間，`check_replay_time` 回 `RESCHEDULE_NO_VALID_TIME`；主辦方要先到 S30 把下一場改晚（下一場一方待定，不會有人報到，可以改），再回 S32 選重賽時間。S32 要把這個錯誤的訊息與「前往場次管理」一起顯示。

### registration（C）

| 函式 | 用在 | 需要的內容 |
| --- | --- | --- |
| `get_team(session, *, team_id) -> TeamRead` | 6.1、6.4 | 6.4 取得隊伍與成員，disputes 自己比對隊長角色（6.1 改用 `is_captain`） |
| `get_registration(session, *, team_id) -> RegistrationRead` | 6.4、6.5 | 報名狀態 |
| `is_captain(session, *, team_id, account_id) -> bool` | 6.1 | 已有 |
| `mark_status(session, *, registration, to, actor_id)` | 6.5 取消資格 | 已有；`pending`／`accepted`／`waitlisted`／`drawn` → `disqualified` 都已允許。抽籤前取消資格後的遞補由 3.4 的 `backfill_vacancies` 在下一次分配處理，6.5 不另外處理 |
| ★ `list_teams_by_status(session, *, tournament_id, statuses) -> list[TeamSummary]` | 6.4 檢舉選單 | 只要 id、隊名（6.4 已新增） |
| ★ `find_team_of_account(session, *, tournament_id, account_id) -> TeamRead \| None` | 6.4 | 登入者在該賽事的隊伍（不限角色），隊長由 disputes 比對成員角色，非隊長回 `CAPTAIN_REQUIRED`（6.4 已新增，取代原提議的 `find_captain_team`） |

## 五、待確認

1. **Report 資料表由誰建**：提議 C 在 6.4 建立 `report` 表與遷移（照本約定的欄位，含處理欄位），B 的 6.5 只寫入處理欄位、不再改表。
2. **附件**：每筆申訴、檢舉最多一張圖，沿用 `core.storage.save_image`（jpg／png、5 MB），和 C 的段位截圖相同。
3. **申訴內容長度**：1～1000 字（UX 沒寫上限，先訂這個）。
4. ~~重新比賽的新時間~~：D 確認（2026-11-05）不直接用 `schedule.py`，改用 D 新增的 `check_replay_time`、`get_replay_window`（〈四〉）。
5. ~~更正結果的各局~~：前端送整組新的各局（不是逐局修改），規則與 5.3 相同，另加 5.4 送出時的兩個檢查（D 確認，2026-11-05）。
6. **S4 申訴入口與徽章**：S4 屬於 A（5.8），6.1 由 B 提供 `appeal-state` API，S4 的按鈕、S21 對話框與「申訴中」徽章由誰接？提議 B 在 6.1 一併做（只新增元件，S4 只加掛載點，列在 PR 說明）。
