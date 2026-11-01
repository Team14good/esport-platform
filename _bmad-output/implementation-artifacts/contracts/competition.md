# competition 模組介面約定（D 黃鉅燊）

- 狀態：提議中（2026-10-29），請 A、B、C 在 PR 確認
- 依據：`docs/midterm/D-物件設計文件.md`〈五、competition〉、B 文件 MATCH 資料表、epic-4／5／6-context
- 函式都在 `app.modules.competition.service`，第一個參數是 `session: Session`，其餘用關鍵字參數

## 一、competition 提供給其他模組

### Schema（`competition/models.py`）

```python
class MatchRead(BaseModel):
    id: UUID
    tournament_id: UUID
    round_no: int                 # 1 起算；季軍賽與決賽同輪
    slot_no: int                  # 該輪由上到下，1 起算；季軍賽排在決賽之後
    is_third_place: bool
    code: str                     # 顯示用編號 "M3"：依輪次、同輪由上到下，輪空不佔編號
    team_a_id: UUID | None        # 未確定時為 None
    team_b_id: UUID | None
    bye_a: bool                   # 4.1 新增：a 方由輪空直接進入本場
    bye_b: bool                   # 4.1 新增：b 方由輪空直接進入本場（輪空多於 P÷4 時兩方都可能是）
    referee_account_id: UUID | None
    scheduled_at: datetime
    status: MatchStatus
    outcome: MatchOutcome | None
    winner_id: UUID | None
    wins_a: int
    wins_b: int
    forfeit_deadline: datetime | None   # 兩隊都確定才有值
    appeal_deadline: datetime | None
    next_match_id: UUID | None
    loser_next_match_id: UUID | None    # 4.1 新增：只有準決賽有，指向季軍賽

class BracketRead(BaseModel):
    id: UUID
    tournament_id: UUID
    size: int                     # P
    rounds: int
    drawn_at: datetime
    delayed_rounds: list[int]     # 4.1 新增：因最小間隔大於每輪間隔而被順延的輪次（S27 提示）
    matches: list[MatchRead]

class PublicMatch(BaseModel):    # 公開 API 用（AD-19）：不含 Email、學校、截圖鍵值
    id: UUID
    code: str
    round_no: int
    slot_no: int
    is_third_place: bool
    team_a: PublicTeamRef | None  # {id, name}
    team_b: PublicTeamRef | None
    source_a: str | None          # 待定時的說明，例如 "M4 勝者"、"M29 敗者"（由 competition/bracket.py 產生）；該方已有隊伍、或確定不會有隊伍（已確認的 walkover、已取消的季軍賽）時為 null
    source_b: str | None
    bye_a: bool                   # a 方由輪空直接進入本輪，前端標「輪空」
    bye_b: bool                   # b 方同上；輪空多於 P÷4 時兩方可能都是輪空
    scheduled_at: datetime
    status: MatchStatus
    outcome: MatchOutcome | None
    winner_id: UUID | None
    wins_a: int
    wins_b: int

class PublicPodium(BaseModel):   # 5.5 新增：名次，從缺為 null
    champion: PublicTeamRef | None
    runner_up: PublicTeamRef | None
    third_place: PublicTeamRef | None

class PublicGame(BaseModel):     # 5.8：已登錄的一局（5.3 第二階段起取自 match_game 表）；不含登錄者
    game_no: int                  # 1 起算
    winner_side: Literal["a", "b"]
    score_a: int | None           # rounds 型態的回合數；win_loss 為 null
    score_b: int | None

class PublicTournamentRef(BaseModel):
    id: UUID
    name: str

class PublicMatchDetail(PublicMatch):   # 5.8：公開單場（A 的 S4 場次頁）；欄位名稱與 A 的 match-types.ts 一致
    tournament: PublicTournamentRef
    game_name: str                # 遊戲名稱快照
    best_of: int                  # 本輪 BO（`bo_for_round`）
    score_type: ScoreType         # "win_loss" | "rounds"
    round_name: str               # 季軍賽為「季軍賽」，其餘同 PublicBracket.round_names
    games: list[PublicGame]
    same_round: list[PublicMatch] # 同輪其他場次（不含自己），依 slot_no、季軍賽在最後；季軍賽與決賽互相列出
    appeal_deadline: datetime | None   # 只在申訴期、申訴中有值，其他狀態 null
    updated_at: datetime          # 這場與同輪其他場次 updated_at 的最大值
    check_in_a_at: datetime | None     # 5.1：a 隊報到時間，未報到或該方未確定為 null；未登入也看得到
    check_in_b_at: datetime | None     # 5.1：b 隊同上（同輪列表的 PublicMatch 不含這兩欄）

class CheckInRead(BaseModel):    # 5.1
    match_id: UUID
    team_id: UUID
    at: datetime

class CheckInStatus(BaseModel):  # 5.1：登入者對某場次的報到狀態，和報到 API 用同一套檢查
    side: Literal["a", "b"] | None   # 登入者是 a 或 b 隊的隊長；不是隊長、或兩隊未確定為 null（兩隊已確定就先算，場次不可報到時也回傳）
    reason: Literal["teams_pending", "already_checked_in", "too_early", "closed",
                    "not_checkable", "not_captain"] | None
                                 # null 代表現在可報到；小寫代碼就是 CheckInPanel 吃的 CheckInReason（前端已補 not_checkable、not_captain）
    opens_at: datetime           # 報到開放時間（預定開始 − 30 分鐘）

class GameScoreIn(BaseModel):    # 5.3：PUT .../games/{game_no} 的請求內容（避開 tournaments 的 GameIn，以免 OpenAPI 重名）
    winner_side: Literal["a", "b"] | None = None   # win_loss 只給這個
    score_a: int | None = None    # rounds 只給 score_a、score_b；嚴格整數 0–99，超出或型別不符回 422
    score_b: int | None = None    # 欄位與賽事的 score_type 不符（例如 win_loss 給數字）回 409 SCORE_INVALID

class SeriesRead(BaseModel):     # 5.3：scoring.series 的結果
    wins_a: int
    wins_b: int
    winner: Literal["a", "b"] | None   # 達到勝局門檻的一方；未達或有多餘的局為 null
    can_submit: bool
    wins_needed: int              # 勝局門檻＝（BO＋1）÷ 2
    reason: Literal["not_decided", "redundant_games"] | None   # 不能送出的原因；能送出為 null

class ScoreEntryState(BaseModel):  # 5.3：S4 Score entry panel 的讀取結果；寫入 API 也回傳最新的這個
    is_scorer: bool               # 登入者是不是記分者：有指派裁判時只有該裁判，未指派時為賽事主辦方
    reason: Literal["not_accepting_scores", "result_submitted", "not_recordable",
                    "teams_pending", "check_in_incomplete"] | None
                                 # 現在不能登錄的原因（與寫入 API 的錯誤碼一一對應，見下方）；null 代表可以登錄
    games: list[PublicGame]       # 依 game_no 遞增
    series: SeriesRead | None
    submitted_by_name: str | None # 送出者顯示名稱；尚未送出為 null（公開 API 不出現送出者）
    submitted_at: datetime | None
    # is_scorer 為 false 時其他欄位一律是空值（reason null、games []、series null），不洩漏送出者

class RescheduleIn(BaseModel):   # 4.3：PATCH .../schedule 的請求內容
    scheduled_at: datetime        # 必須帶時區，否則 422

class RescheduleInfo(BaseModel): # 4.3：某場次現在能不能改時間與 S30 時間選擇器的範圍
    can_reschedule: bool
    reason: Literal["tournament_not_reschedulable", "match_not_reschedulable",
                    "forfeit_due", "already_checked_in", "no_valid_time"] | None
                                 # 與修改 API 錯誤碼一一對應：TOURNAMENT_NOT_RESCHEDULABLE、MATCH_NOT_RESCHEDULABLE（`match_not_reschedulable` 與 `forfeit_due` 共用）、MATCH_ALREADY_CHECKED_IN、RESCHEDULE_NO_VALID_TIME；可改為 null
    earliest: datetime | None     # 允許範圍（含邊界）；因狀態不能改時為 null，no_valid_time 時仍附上
    latest: datetime | None       # 決賽、季軍賽沒有上限為 null

class ManagedMatch(BaseModel):   # 4.3：S30 場次列表的一列（只給主辦方）
    id: UUID
    code: str
    round_no: int
    slot_no: int
    is_third_place: bool
    team_a: PublicTeamRef | None  # 與公開對戰樹相同
    team_b: PublicTeamRef | None
    source_a: str | None          # 待定說明，例如 "M4 勝者"
    source_b: str | None
    scheduled_at: datetime
    status: MatchStatus
    referee_account_id: UUID | None   # 4.4 前為 null
    reschedule: RescheduleInfo

class PublicBracket(BaseModel):
    tournament_id: UUID
    rounds: int
    round_names: list[str]        # ["16 強", "8 強", "4 強", "決賽"]（EXPERIENCE.md 用語）
    matches: list[PublicMatch]
    podium: PublicPodium | None   # 5.5 新增：賽事為 finished 才有，否則 null（場次資料不自洽時也為 null 並記錄日誌）
    updated_at: datetime          # 前端判斷是否有變動（update-flash）
```

### HTTP API（D 在 4.1 提供，A 的 4.6、5.8 使用）

| 方法與路徑 | 權限 | 回傳 |
| --- | --- | --- |
| `GET /api/v1/tournaments/{tournament_id}/bracket` | 公開 | `PublicBracket`；尚未抽籤回 404 `BRACKET_NOT_FOUND` |
| `GET /api/v1/tournaments/{tournament_id}/matches/{match_id}` | 公開 | `PublicMatchDetail`（5.8）；賽事不存在、尚未抽籤、場次不存在、場次不屬於該賽事，一律 404 `MATCH_NOT_FOUND`（回應 `{"detail":{"code":"MATCH_NOT_FOUND","message":"找不到這個場次。"}}`；尚未抽籤也回這個碼而非 `BRACKET_NOT_FOUND`，不透露是哪一種）。`same_round` 的項目是一般 `PublicMatch`，不含單場的延伸欄位；`games` 依 `game_no` 遞增列出已登錄的局（5.3 第二階段起；不含登錄者，送出者也不出現在公開 API） |
| `POST /api/v1/tournaments/{tournament_id}/draw` | 該賽事主辦方 | 201 `BracketRead` |
| `GET /api/v1/tournaments/{tournament_id}/manage/matches` | 該賽事主辦方 | `list[ManagedMatch]`（4.3，S30）；依輪次、季軍賽在決賽之後；尚未抽籤 404 `BRACKET_NOT_FOUND`、賽事不存在 404 `TOURNAMENT_NOT_FOUND`、非主辦方 403 `TOURNAMENT_OWNER_REQUIRED`（一般帳號 403 `ORGANIZER_REQUIRED`） |
| `PATCH /api/v1/tournaments/{tournament_id}/matches/{match_id}/schedule` | 該賽事主辦方 | 200 `MatchRead`（4.3）；body `RescheduleIn`；範圍與列表的 `RescheduleInfo` 同一套計算（`schedule.reschedule_window`／`check_reschedule`） |
| `POST /api/v1/tournaments/{tournament_id}/matches/{match_id}/check-in` | 登入者（須為該場兩隊之一的隊長） | 201 `CheckInRead`（5.1）；隊伍由登入者是哪一隊的隊長推得，請求不帶內容；一隊一場一次、不能取消 |
| `GET /api/v1/tournaments/{tournament_id}/matches/{match_id}/check-in` | 登入者 | `CheckInStatus`（5.1）；場次不存在或不屬於該賽事回 404 `MATCH_NOT_FOUND` |
| `GET /api/v1/tournaments/{tournament_id}/matches/{match_id}/score-entry` | 登入者 | `ScoreEntryState`（5.3）；不是記分者時 `is_scorer=false`、其他欄位空；場次不存在或不屬於該賽事回 404 `MATCH_NOT_FOUND` |
| `PUT /api/v1/tournaments/{tournament_id}/matches/{match_id}/games/{game_no}` | 記分者 | 200 `ScoreEntryState`（5.3）；body `GameScoreIn`；局號＝目前局數＋1 為新增、≤ 目前局數為覆寫；第一局登錄時場次由待開打轉為進行中 |
| `DELETE /api/v1/tournaments/{tournament_id}/matches/{match_id}/games/{game_no}` | 記分者 | 200 `ScoreEntryState`（5.3）；只能刪最後一局；刪到沒有任何局時場次維持進行中 |
| `POST /api/v1/tournaments/{tournament_id}/matches/{match_id}/submit` | 記分者 | 200 `ScoreEntryState`（5.4）；寫 `outcome=played`、勝隊、送出者與時間、`appeal_deadline`＝現在＋申訴時限，轉為申訴期並發 `MatchResultSubmitted`；不寫 `confirmed_at`、勝隊不晉級（5.5 申訴期滿才確認並推進） |

修改場次時間的錯誤碼（4.3，依檢查順序）：`Organizer` 依賴最先執行（未登入 401、非主辦方帳號 403 `ORGANIZER_REQUIRED`，早於所有 404）→ `TOURNAMENT_NOT_FOUND`／`MATCH_NOT_FOUND` 404（場次不屬於網址上的賽事也是 `MATCH_NOT_FOUND`）→ `lock_tournament`、`lock_match` → `TOURNAMENT_OWNER_REQUIRED` 403 → `TOURNAMENT_NOT_RESCHEDULABLE` 409（賽事不是賽程已公布或進行中）→ `MATCH_NOT_RESCHEDULABLE` 409（場次不是待開打，或棄權期限已過、無人報到而等待判棄權；列表原因代碼分別為 `match_not_reschedulable`、`forfeit_due`）→ `MATCH_ALREADY_CHECKED_IN` 409（任一隊已報到）→ 範圍（皆 409，訊息附台北時間的允許範圍，例如「可選 10/26（一）12:55～14:35。」，無上限只寫起點；最早可選時間＝現在進位到整分＋30 分鐘（`checkin.CHECK_IN_LEAD`），列表與修改 API 用同一個值，所以最早在這個時間之前一律 `RESCHEDULE_BEFORE_NOW`）：`RESCHEDULE_BEFORE_NOW`、`RESCHEDULE_BEFORE_FEEDER`、`RESCHEDULE_AFTER_NEXT_MATCH`、`RESCHEDULE_NO_VALID_TIME`；沒有時區 422；未登入 401。下一場＝勝隊去的場次，準決賽取決賽與季軍賽中較早的一場；前一輪場次＝勝隊或敗隊會進入本場的場次。新時間與原時間相同時回傳目前的 `MatchRead`、不寫入任何東西（不寫紀錄、不發事件）；新時間一律轉 UTC 儲存與回傳。成功：寫入 `scheduled_at`、`updated_at`，兩隊都已確定的場次經 `start_forfeit_clock` 重算棄權期限，寫操作紀錄 `match.rescheduled`（`before`、`after` 各含 `scheduled_at`、`forfeit_deadline`），發 `MatchRescheduled`；任何拒絕都不改時間、棄權期限、操作紀錄與事件。

抽籤的錯誤碼（4.1）：`NOT_ENOUGH_TEAMS` 409（正取不足 2 隊）、`BRACKET_ALREADY_DRAWN` 409（已有對戰表，優先於狀態檢查）、`TOURNAMENT_NOT_DRAWABLE` 409（狀態不是 `open`、`closed`）、`TOURNAMENT_START_PASSED` 409（`start_at <= now`）、`TOURNAMENT_OWNER_REQUIRED` 403、`ORGANIZER_REQUIRED` 403、`TOURNAMENT_NOT_FOUND` 404、`REGISTRATION_UNAVAILABLE` 503（registration 尚未提供抽籤用函式）。報到的錯誤碼（5.1，檢查順序；`REGISTRATION_UNAVAILABLE` 503 在判斷隊長身分時才發生，所以排在 `CAPTAIN_REQUIRED` 之前，兩隊未確定或場次不可報到時不會觸發）：`MATCH_NOT_FOUND` 404（場次不存在或不屬於網址上的賽事）、`MATCH_NOT_CHECKABLE` 409（賽事不是賽程已公布或進行中，或場次不是待開打）、`MATCH_TEAMS_PENDING` 409（兩隊未確定）、`CAPTAIN_REQUIRED` 403（不是兩隊任一隊的隊長）、`ALREADY_CHECKED_IN` 409、`CHECK_IN_NOT_OPEN` 409（訊息為台北時間的絕對時間，例如「10/18（六）19:00 起可報到。」，跨年才加年份、不標時區）、`CHECK_IN_CLOSED` 409（現在 >= `forfeit_deadline`）；兩隊已確定卻沒有 `forfeit_deadline`、或期限不晚於開放時間（資料不一致）回 `MATCH_NOT_CHECKABLE`（狀態查詢為 `not_checkable`），不會是 500；併發重複報到撞唯一鍵一樣回 `ALREADY_CHECKED_IN`；狀態查詢的小寫原因代碼與 API 錯誤碼一一對應（`teams_pending`→`MATCH_TEAMS_PENDING`、`already_checked_in`→`ALREADY_CHECKED_IN`、`too_early`→`CHECK_IN_NOT_OPEN`、`closed`→`CHECK_IN_CLOSED`、`not_checkable`→`MATCH_NOT_CHECKABLE`、`not_captain`→`CAPTAIN_REQUIRED`）、`REGISTRATION_UNAVAILABLE` 503（registration 尚未提供 `is_captain`）；未登入 401。報到成功寫操作紀錄 `match.checked_in` 並發 `TeamCheckedIn`。賽事開始 worker（`start_due_tournaments`）：賽程已公布且最早場次的報到開放時間（`checkin.tournament_starts_at`）已到，轉為進行中（操作者為系統），以 `bracket.start_handled_at` 標記已處理；賽事不是賽程已公布（已進行、已取消、已結束）只標記略過。`start_due_tournament` 回傳 True 代表處理了一個對戰表（轉為進行中或標記略過），worker 會再呼叫；沒有候選、或鎖住後發現還沒到開始時間（期間被改期）回傳 False。兩隊都報到後期限已過的場次維持待開打，由 5.3 裁判登錄第一局推進為進行中（5.2 不會判棄權）。比分登錄、刪除、送出的錯誤碼（5.3、5.4，依檢查順序；任何拒絕都不改局、場次與操作紀錄）：`MATCH_NOT_FOUND` 404（場次不存在或不屬於網址上的賽事）→ 鎖住場次（`lock_match`）→ `TOURNAMENT_NOT_ACCEPTING_SCORES` 409（tournaments `ensure_accepting_scores`：賽事不是賽程已公布或進行中；狀態查詢為 `not_accepting_scores`）→ `SCORER_REQUIRED` 403（不是記分者）→ `RESULT_ALREADY_SUBMITTED` 409（申訴期、申訴中、已確認；`result_submitted`）、`MATCH_NOT_RECORDABLE` 409（已取消；`not_recordable`）→ `MATCH_TEAMS_PENDING` 409（`teams_pending`）、`CHECK_IN_INCOMPLETE` 409（兩隊未都報到；`check_in_incomplete`）→ 比分規則（`scoring.py`，皆 409）：`SCORE_TIE`、`SCORE_INVALID`、`SERIES_DECIDED`、`REDUNDANT_GAMES`、`INVALID_GAME_NO`、`NOT_LAST_GAME`；送出時未達門檻 `SERIES_NOT_DECIDED`（訊息「任一隊拿到 {N} 勝後才能送出。」），有多餘的局 `REDUNDANT_GAMES`；未登入 401；回合數超出 0–99 回 422。每次登錄或刪除後依 `scoring.series` 重算 `wins_a`、`wins_b` 並更新 `updated_at`。操作紀錄：`match.game_recorded`（`before` 為覆寫前的局、新增時為 null；`after` 含新的局與勝局數）、`match.game_deleted`（`before` 為被刪的局）、`match.result_submitted`。同時兩個登錄請求經 `lock_match` 串行，後到的新增會變成覆寫；`(match_id, game_no)` 唯一鍵是最後防線。場次相關：`MATCH_NOT_FOUND` 404、`MATCH_INVALID_TRANSITION` 409、`MATCH_TEAMS_NOT_SET` 409（`start_forfeit_clock` 用在兩隊未確定的場次）。

### 公開函式

| 函式 | 誰會呼叫 | 說明 | 提供於 |
| --- | --- | --- | --- |
| `get_bracket(session, *, tournament_id) -> BracketRead \| None` | A（4.6、5.8、7.1） | 尚未抽籤回 None | 4.1 |
| `get_public_bracket(session, *, tournament_id) -> PublicBracket \| None` | A（4.6） | 公開對戰樹 | 4.1 |
| `get_match(session, *, match_id) -> MatchRead` | A（5.2）、B（6.1、6.2、6.5） | 不存在拋 `MATCH_NOT_FOUND` 404 | 4.1 |
| `list_team_matches(session, *, tournament_id, team_id) -> list[MatchRead]` | B（6.4、6.5） | 依輪次排序，判斷「還沒比過」「最近一場輸給誰」 | 4.1 |
| `lock_match(session, *, match_id) -> Match` | competition 內的新檔案（A 的 5.2、B 的 6.5） | `SELECT … FOR UPDATE`；同時需要賽事鎖時先鎖賽事（AD-6） | 4.1 |
| `transition_match(session, *, match, to: MatchStatus) -> None` | 同上 | 唯一改場次狀態的入口，非法轉換拋 `MATCH_INVALID_TRANSITION` 409 | 4.1 |
| `start_forfeit_clock(session, *, match) -> None` | 同上 | 唯一設定 `forfeit_deadline` 的入口 | 4.1 |
| `list_forfeit_due(session, *, now) -> list[UUID]` | A（5.2 worker） | 待開打、`forfeit_deadline <= now`、且**不是兩隊都已報到**的場次 id，依期限排序（使用者 2026-11-01 決定）；只有一隊報到或沒人報到的場次由 5.2 判棄權 | 5.1 |
| `list_check_ins(session, *, match_id) -> list[CheckInRead]` | A（5.2） | `CheckInRead {match_id, team_id, at}`，依報到時間排序 | 5.1 |
| `check_in(session, *, tournament_id, match_id, account_id) -> CheckInRead`、`get_check_in_status(...) -> CheckInStatus` | router | 報到與狀態查詢；`start_due_tournament(session) -> bool` 給 worker | 5.1 |
| `confirm_match(session, *, match, outcome: MatchOutcome, winner_id: UUID \| None, actor_id: UUID \| None) -> None` | A（5.2）、B（6.2） | 呼叫端先 `lock_tournament` 再 `lock_match` 取得 `match`（AD-6；函式開頭也會鎖賽事）；只接受 `live`、`appeal_window`、`appealed` 的場次；寫入結果、轉為已確認、寫 `confirmed_at`，接著呼叫 `advance`。`actor_id=None` 表示系統。`scheduled`、`confirmed`、`voided` 拋 `MATCH_INVALID_TRANSITION` 409，不改任何資料（待開打直接確認只走輪空：`confirm_walkover` 與 `advance` 內的連鎖輪空；5.2 判棄權是 scheduled → appeal_window，不經 `confirm_match`）（5.5 由 `actor` 改名 `actor_id`） | 5.5 |
| `advance(session, *, match) -> None` | B（6.2 更正後、6.5） | `match` 必須已確認（否則 `ValueError`）。先鎖賽事、再依 id 遞增鎖住整個對戰表的場次；勝隊進下一場、準決賽敗隊進季軍賽；對手確定不會有隊伍時自動 walkover，季軍賽必要時轉為已取消；兩隊湊齊時起算棄權期限並發 `MatchOpponentsDecided`；決賽與季軍賽都定案時賽事轉為 `finished`（`published` 先轉 `ongoing`）並記 `tournament.podium`。後續變更的操作者為系統；重複呼叫沒有副作用。呼叫前對場次的修改必須已 flush | 5.5 |
| `confirm_walkover(session, *, match) -> None` | B（6.5） | 呼叫端先 `lock_tournament` 再 `lock_match` 取得 `match`（AD-6；函式開頭也會鎖賽事）；一方確定不會有隊伍時以 walkover 確認並推進（操作者為系統）；勝隊為場上唯一的隊伍，兩方都沒有時無勝隊；兩隊都在時拋 `MATCH_INVALID_TRANSITION` 409 | 5.5 |
| `clear_for_replay(session, *, match) -> ReplayCleared` | B（6.2 `replay_match`） | 只接受 `appealed`（鎖住後判斷），其他狀態拋 `MATCH_INVALID_TRANSITION` 409、不改資料。刪除該場所有 `check_in`、`match_game`；`outcome`、`winner_id`、`submitted_by`、`submitted_at`、`appeal_deadline`、`confirmed_at`、`forfeit_deadline` 設 null、`wins_a`、`wins_b` 歸 0、更新 `updated_at`；不改狀態、`scheduled_at`、兩隊、裁判、`next_match_id`、`loser_next_match_id`。回傳清除前的 `ReplayCleared {check_ins: list[CheckInRead], games: list[PublicGame], outcome, winner_id, wins_a, wins_b, submitted_by, submitted_at, appeal_deadline, confirmed_at, forfeit_deadline}`，供操作紀錄記變更前後。**不寫操作紀錄、不發事件、不轉換狀態、不改 `scheduled_at`**（棄權期限等欄位會歸零）。呼叫端先 `lock_tournament`，函式內再 `lock_match` 並以鎖住後的狀態判斷。`replay_match` 接下來要做：`transition_match` 轉回待開打 → 寫入新 `scheduled_at` → `start_forfeit_clock` → 寫一筆操作紀錄（用 `ReplayCleared`）→ 發事件；整個序列必須在同一個交易內 | 6.2 前置 |
| `auto_confirm_expired(session) -> bool` | worker（`confirm_expired_appeals`） | 確認一場申訴期、`appeal_deadline <= now` 的場次（沿用已寫入的 outcome、勝隊，操作者為系統）並推進；略過已取消或已結束賽事的場次；回傳是否找到候選 | 5.5 |
| `record_game(session, *, tournament_id, match_id, account_id, game_no, data: GameScoreIn) -> ScoreEntryState`、`delete_game(..., game_no)`、`submit_result(...)`、`get_score_entry(...)` | router | 比分登錄、刪除最後一局、送出系列結果與 S4 讀取；規則一律交給 `scoring.py` | 5.3、5.4 |
| `get_podium(session, *, tournament_id) -> PublicPodium \| None` | A（5.8、7.1） | 名次；尚未抽籤或賽事不是 `finished` 回 None | 5.5 |

申訴相關的 `mark_appealed`、`uphold_result`、`correct_result`、`replay_match`：設計文件放在 MatchService，epic 6 由 disputes 呼叫。**比照 6.6 的 `disqualify`，由 B 寫在 competition 新增的檔案，`service.py` 只新增這幾個公開函式，D 審查。**（B 已確認，2026-10-30）

### 事件（`core.events.publish`，期中只發不通知）

| 事件 | payload | 時機 |
| --- | --- | --- |
| `BracketDrawn` | `tournament_id`, `bracket_id` | 4.1 抽籤完成 |
| `MatchRescheduled` | `match_id`, `scheduled_at` | 4.3 修改時間 |
| `RefereeAssigned` | `match_id`, `referee_account_id` | 4.4 指派或改派 |
| `RefereeUnassigned` | `match_id`, `referee_account_id` | 4.4 收回、5.5 填位後衝突 |
| `MatchResultSubmitted` | `match_id` | 5.4 記分者送出系列結果 |
| `MatchResultConfirmed` | `match_id`, `winner_id`（雙方棄權、無隊伍的輪空為 null） | 5.5 每場確認（含輪空確認） |
| `MatchOpponentsDecided` | `match_id` | 5.5 晉級填位後該場兩隊都確定（通知兩隊隊長下一場對手） |
| `TeamCheckedIn` | `match_id`, `team_id`, `both_checked_in` | 5.1 一隊報到成功；目前沒有消費者（通知在之後的 Story） |

## 二、competition 需要的上游介面（提議，請 B、C 確認）

名稱沿用 epic context 已列的；新增的標 ★。

### tournaments（B）

| 函式 | 用在 | 需要的內容 |
| --- | --- | --- |
| `get_tournament(session, *, tournament_id) -> TournamentRead` | 4.1、4.3、4.4、5.x | 下表欄位 |
| `lock_tournament(session, *, tournament_id) -> TournamentRead` | 4.1、4.3、4.4、5.5 | `SELECT … FOR UPDATE` 賽事列 |
| `transition_tournament(session, *, tournament_id, to, actor_id) -> TournamentRead` | 4.1（→ published）、5.x（→ ongoing、finished） | 非法轉換拋錯 |
| `is_referee(session, *, tournament_id, account_id) -> bool` | 4.4 | 已接受邀請 |
| ★ `list_referees(session, *, tournament_id) -> list[RefereeRead]` | 4.4 的 S30 選單 | `RefereeRead {account_id, display_name}` |
| `bo_for_round(session, *, tournament_id, round_no) -> int` | 4.3、5.3、5.4 | 期中一律回賽事的 BO |

`TournamentRead` 需要的欄位（完整定義與其他函式見 [tournaments.md](tournaments.md)）：

`id`, `organizer_id`, `name`, `status`, `mode`, `capacity`, `registration_end`, `start_at`, `round_interval_minutes`, `forfeit_minutes`, `appeal_minutes`, `bo`, `game_minutes`（遊戲快照的每局預估時間）, `score_type`

### registration（C）

| 函式 | 用在 | 說明 |
| --- | --- | --- |
| ★ `list_accepted_teams(session, *, tournament_id) -> list[TeamRead]` | 4.1 | 正取隊伍 |
| ★ `finalize_for_draw(session, *, tournament_id, actor_id) -> None` | 4.1 | 開放報名中提前抽籤時呼叫：仍在優先期就先做優先期分配，再做截止補位（`fill_at_deadline`）。分配規則留在 C，competition 只呼叫這一個 |
| ★ `mark_drawn(session, *, tournament_id, team_ids, actor_id) -> None` | 4.1 | 正取 → 已參賽 |
| `is_member(session, *, team_id, account_id) -> bool` | 4.4（裁判不能是參賽隊員） | |
| ★ `is_captain(session, *, team_id, account_id) -> bool` | 5.1 報到 | 經 `registration_port.is_captain`，缺函式回 503 `REGISTRATION_UNAVAILABLE` |
| ★ `get_team_names(session, *, team_ids) -> dict[UUID, str]` | 4.1 公開對戰樹 | 一次查多隊，避免 N+1 |

`actor_id` 比照 tournaments 的 `transition_tournament`（4.1 由 `actor` 改名）。`list_accepted_teams` 回傳的 `TeamRead` competition 只讀 `id`。

**registration_port（4.1）**：competition 對上面 4 個 ★ 抽籤函式的呼叫全部經過 `competition/registration_port.py`，在呼叫當下才到 `app.modules.registration.service` 以名稱查找；函式不存在時拋 503 `REGISTRATION_UNAVAILABLE`（`BusinessError` 只接受 4xx，port 內的子類別建立後改為 503）。C 照上表名稱與關鍵字參數合併後，competition 不必修改。

## 三、待確認

1. ~~申訴相關函式由誰實作~~：B 實作、D 審查（B 已確認，2026-10-30）。
2. `finalize_for_draw` 合併優先期分配與截止補位，請 C 確認可行。
3. ~~`TournamentRead` 的欄位名稱~~：以 [tournaments.md](tournaments.md) 為準，每局預估時間改名為 `game_minutes`（2026-10-30）。
