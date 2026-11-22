# tournaments 模組介面約定（B 蘇采羚）

- 狀態：提議中（2026-10-30），請 C、D 在 PR 確認；A 的 5.2、7.1 也會用到
- 依據：`docs/midterm/D-物件設計文件.md`〈tournaments〉、c-d-design-groundwork D-2、epic-2～7-context、`contracts/competition.md`〈二〉
- 函式都在 `app.modules.tournaments.service`，第一個參數是 `session: Session`，其餘用關鍵字參數；service 不 commit（AD-5）
- 「提供於」是預計實作的 Story；還沒合併前，下游照 `contracts/README.md` 用測試替身先寫

## 一、Schema（`tournaments/models.py`）

```python
class RankTierRead(BaseModel):   # 2.1 已實作
    name: str
    score: int

class GameRead(BaseModel):       # 2.1 已實作（平台管理員維護的遊戲設定）
    id: UUID
    name: str
    starters: int
    substitutes: int
    default_bo: int
    game_minutes: int
    score_type: ScoreType
    rank_tiers: list[RankTierRead]   # 積分由高到低

class TournamentRead(BaseModel):
    id: UUID
    organizer_id: UUID
    name: str
    status: TournamentStatus
    mode: TournamentMode             # 期中一律 campus
    capacity: int                    # 正取名額
    registration_start: datetime
    priority_end: datetime           # 優先期結束 = registration_start + 優先期時數（校園賽）
    registration_end: datetime
    start_at: datetime               # 開賽時間（第 1 輪）
    round_interval_minutes: int
    forfeit_minutes: int             # 棄權時限，≥ 15
    appeal_minutes: int              # 申訴期，≥ 30
    livestream_url: str | None
    # 以下來自建立賽事時複製的遊戲快照（AD-12），之後不再讀 GameTitle
    game_id: UUID
    game_name: str
    starters: int
    substitutes: int
    bo: int                          # 賽事的 BO（預設帶入遊戲的 default_bo，主辦方可改）
    game_minutes: int                # 每局預估時間（分鐘）
    score_type: ScoreType
    rank_tiers: list[RankTierRead]   # 段位對照表快照，積分由高到低
    round_bo: list[RoundBo]          # 2.3 分輪 BO：有設定的輪次，依距決賽的輪數由小到大；沒列出的輪次用 bo

class RoundBo(BaseModel):        # 2.3
    rounds_from_final: int           # 距決賽的輪數：決賽 0、4 強 1、8 強 2…
    bo: int                          # 1、3、5、7

class RefereeRead(BaseModel):    # 2.7 已實作
    account_id: UUID
    display_name: str
    accepted_at: datetime            # 接受邀請的時間

class RefereeInvitationRead(BaseModel):   # 2.7：主辦方看到的邀請（S31）
    tournament_id: UUID
    token: str                       # 明文，用來組出邀請連結
    created_at: datetime
    expires_at: datetime             # 產生後 7 天；重新產生時舊的設為當下
    expired: bool                    # expires_at <= 現在
    accepting: bool                  # 賽事不是 finished／cancelled（2.7 第二階段）

class PublicRefereeInvitation(BaseModel):  # 2.7：不需登入的邀請預覽（S23，AD-19）
    tournament_name: str
    expires_at: datetime
    expired: bool
    accepting: bool                  # 賽事不是 finished／cancelled（2.7 第二階段）

class PublicTournament(BaseModel):   # 2.4 已實作：不需登入的公開 API 用（AD-19）
    id: UUID
    name: str
    status: TournamentStatus
    game_name: str
    capacity: int                    # 正取名額
    registration_start: datetime
    priority_end: datetime
    registration_end: datetime
    start_at: datetime               # 開賽時間（第 1 輪）
    round_interval_minutes: int
    livestream_url: str | None
```

- 列舉沿用 `models.py` 既有的 `ScoreType`、`TournamentMode`、`TournamentStatus`。
- 時間一律帶時區（UTC）。
- 分輪 BO（2.3）：`POST /organizer/tournaments` 的 `round_bo: list[RoundBo]`（預設空清單）只列有設定的輪次。值的規則錯誤（BO 不是 1／3／5／7、輪次重複或小於 0、輪次超出名額可能的輪數；名額 N 共 ⌈log₂N⌉ 輪，可設距決賽 0～輪數−1）回 422，`loc` 為 `["body", "round_bo"]`；項目型別錯誤（例如 `bo` 是字串、`null` 或缺欄位）沿用欄位層級的 `loc`：`["body", "round_bo", <i>, <欄位>]`。存於 `round_setting` 表（主鍵 `tournament_id`＋`rounds_from_final`），建立後不能修改（修改屬 2.5）。
- 不登入就能呼叫的公開 API 用另外的 `Public*` schema（2.4 定義的 `PublicTournament`），不含 `organizer_id`、Email 與學校（AD-19）。
- 裁判 API（2.7）：
  - `POST /organizer/tournaments/{tournament_id}/referee-invitation`（主辦方）：產生新邀請，201 回 `RefereeInvitationRead`；同賽事尚未過期的舊邀請 `expires_at` 設為現在（不刪除）。
  - `GET /organizer/tournaments/{tournament_id}/referee-invitation`（主辦方）：最新一筆邀請（含 `expired`、`accepting`），從未產生回 `null`。
  - `GET /organizer/tournaments/{tournament_id}/referees`（主辦方）：`list[RefereeRead]`，依接受時間排序。
  - 以上三支：不存在 404 `TOURNAMENT_NOT_FOUND`、別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`；產生邀請時賽事已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
  - `GET /referee-invites/{token}`（不需登入）：`PublicRefereeInvitation`；不存在 404 `REFEREE_INVITATION_NOT_FOUND`，過期仍回 200（`expired: true`）。
  - `POST /referee-invites/{token}/accept`（已驗證 Email）：200 回 `RefereeRead`；已是裁判回原本的資料（冪等）。不存在 404、過期或已作廢 409 `REFEREE_INVITATION_EXPIRED`、賽事已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`、主辦方本人 409 `ORGANIZER_CANNOT_BE_REFEREE`、未登入 401、未驗證 403 `EMAIL_NOT_VERIFIED`。
  - 不檢查受邀者是否為參賽隊員，由 4.4 指派裁判時檢查。
- 操作紀錄 API（2.8）：`GET /organizer/tournaments/{tournament_id}/audit-log?page=`（主辦方，唯讀）：`AuditLogPage`（`items: list[AuditLogEntry]`、`total`、`page`、`page_size`，每頁 20 筆）。
  - `AuditLogEntry`：`id`、`at`、`actor_id`、`actor_display_name`、`action`、`entity_type`、`entity_id`、`before`、`after`；`actor_id` 為 null 代表系統（worker），此時 `actor_display_name` 也是 null（「系統自動」由前端顯示）。
  - 由新到舊（同時間依寫入順序倒序）；`page` 超過總頁數時 `items` 為空、`total` 照實；`page` 小於 1 或大於 100000 回 422。
  - 只經 `core.audit.list_for_tournament()` 查詢，service 反轉後切片（資料庫層分頁列為延後項目）；不含其他賽事與帳號類紀錄。
  - 不存在 404 `TOURNAMENT_NOT_FOUND`、別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`、不是主辦方 403 `ORGANIZER_REQUIRED`、未登入 401。
- 公開 API（2.4，不需登入）：`GET /tournaments` 回傳所有賽事的 `list[PublicTournament]`，依開賽時間排序；`GET /tournaments/{tournament_id}` 回傳 `PublicTournament`，不存在 404 `TOURNAMENT_NOT_FOUND`，id 格式錯誤 422。
- 取消賽事 API（2.6）：`POST /organizer/tournaments/{tournament_id}/cancel`（主辦方本人），200 回 `TournamentRead`（`status: cancelled`）。不存在 404 `TOURNAMENT_NOT_FOUND`；別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`；非主辦方 403 `ORGANIZER_REQUIRED`；未登入 401；已結束或已取消 409 `TOURNAMENT_NOT_CANCELLABLE`（「已結束或已取消的賽事不能取消。」），狀態、操作紀錄與事件都不變。

## 二、公開函式

| 函式 | 誰會呼叫 | 說明 | 提供於 |
| --- | --- | --- | --- |
| `get_game(session, *, game_id) -> GameRead` | tournaments 內部（2.2）、A（7.1 示範資料） | 不存在拋 `GAME_NOT_FOUND` 404 | 2.1 |
| `get_tournament(session, *, tournament_id) -> TournamentRead` | C（3.x）、D（4.x、5.x）、A（5.2、5.8）、B（6.x） | 不存在拋 `TOURNAMENT_NOT_FOUND` 404 | 2.2 |
| `list_public_tournaments(session) -> list[PublicTournament]` | tournaments 的公開路由（2.4 S1） | 所有賽事的公開資料，依開賽時間排序；不需登入 | 2.4 |
| `get_public_tournament(session, *, tournament_id) -> PublicTournament` | tournaments 的公開路由（2.4 S2） | 一場賽事的公開資料；不存在拋 `TOURNAMENT_NOT_FOUND` 404 | 2.4 |
| `lock_tournament(session, *, tournament_id) -> TournamentRead` | C（改名單、名額、分配前）、D（4.1、4.3、4.4、5.5）、A（5.2） | `SELECT … FOR UPDATE` 賽事列，回傳鎖定後的最新值；這是鎖賽事的唯一入口（AD-6）。同時要鎖場次時，先鎖賽事 | 2.2 |
| `transition_tournament(session, *, tournament_id, to, actor_id) -> TournamentRead` | 見〈三〉 | 唯一改賽事狀態的入口（AD-11）；呼叫前要先 `lock_tournament`。非法轉換拋 `TOURNAMENT_INVALID_TRANSITION` 409。寫操作紀錄 `tournament.status_changed`；`actor_id=None` 表示系統（worker） | 2.2 |
| `ensure_accepting_registrations(tournament: TournamentRead) -> None` | C（3.1～3.6） | 狀態不是 `open` 時拋 `REGISTRATION_CLOSED` 409。只看狀態：報名截止由 worker 轉成 `closed` | 2.2 |
| `ensure_accepting_scores(tournament: TournamentRead) -> None` | D（5.3、5.4）、B（6.2） | 狀態不是 `published`、`ongoing` 時拋 `TOURNAMENT_NOT_ACCEPTING_SCORES` 409（已結束、已取消都拒絕） | 2.2 |
| `bo_for_round(session, *, tournament_id, round_no, rounds, is_third_place) -> int` | D（4.3、5.3、5.4、5.8） | 實際對戰表共 `rounds` 輪時第 `round_no` 輪（從 1 起算）的 BO：換算成距決賽的輪數（`rounds - round_no`，季軍賽再 +1，即沿用 4 強）查 `round_bo`，沒有設定回 `TournamentRead.bo`；`round_no` 不在 1～`rounds` 拋 `ValueError`（程式錯誤）。換算是純函式 `resolve_round_bo` | 2.2；2.3 改簽名 |
| `is_referee(session, *, tournament_id, account_id) -> bool` | D（4.4） | 已接受該賽事的裁判邀請；只在該賽事有效（經 `core.authz.is_tournament_referee` 判斷） | 2.7 |
| `list_referees(session, *, tournament_id) -> list[RefereeRead]` | D（4.4 的 S30 選單） | 依接受邀請的時間排序 | 2.7 |
| `has_referee_role(session, *, account_id) -> bool` | 組裝層（`app/api/main.py`）註冊給 identity 的 `register_referee_lookup`（4.4 S13） | 帳號是不是任一賽事的裁判（有 `TournamentReferee` 列即是，不看賽事狀態）；身分切換器的「裁判」用 | 4.4 |
| `list_audit_log(session, *, tournament_id, page) -> AuditLogPage` | tournaments 的主辦方路由（2.8 S34） | 由新到舊分頁的操作紀錄（含操作者顯示名稱）；不檢查權限，呼叫前先 `ensure_tournament_owner` | 2.8 |
| `ensure_accepting_referees(tournament: TournamentRead) -> None` | tournaments 的裁判邀請（2.7）；其他模組需要時可呼叫 | 狀態為 `finished`、`cancelled` 時拋 `TOURNAMENT_NOT_ACCEPTING_REFEREES` 409；不碰資料庫 | 2.7 |
| `find_due_registration_end_id(session) -> UUID \| None` | C（3.6 報名截止 worker 工作） | 一筆狀態為 `open`、`registration_end <= clock.now()` 的賽事 id，依報名截止時間、再依 id，最早到期的優先；不加鎖，呼叫端鎖住後要重新檢查。沒有任何報名的賽事也找得到（C 在 3.6 新增） | 3.6 |
| `list_closed_tournament_ids(session) -> list[UUID]` | D（4.2 自動抽籤 worker 工作） | 狀態為 `closed`、`start_at > clock.now()` 的賽事 id，依報名截止時間、再依 id；不加鎖，呼叫端鎖住後要重新檢查（D 在 4.2 新增） | 4.2 |
| `cancel_tournament(session, *, tournament_id, actor_id) -> TournamentRead` | tournaments 的取消賽事 API（2.6 S27） | 先 `lock_tournament`，再經 `transition_tournament` 轉為 `cancelled`（操作紀錄 `tournament.status_changed`），同一交易發出 `TournamentCancelled`。已結束或已取消拋 `TOURNAMENT_NOT_CANCELLABLE` 409；不存在拋 `TOURNAMENT_NOT_FOUND` 404。主辦方權限由呼叫端以 `authz.ensure_tournament_owner` 判斷 | 2.6 |
| `raise_tournament_capacity(session, *, tournament_id, capacity, actor_id) -> TournamentRead` | C（3.7 registration `raise_capacity`） | 提高名額，回傳改名額後的賽事；呼叫前要先 `lock_tournament`。狀態不是 `upcoming`、`open`、`closed` 時拋 `CAPACITY_NOT_EDITABLE` 409；新名額小於或等於目前名額時拋 `CAPACITY_NOT_INCREASED` 422（`loc=body.capacity`）。寫操作紀錄 `tournament.capacity_changed`（before／after 為名額）。不檢查權限、不做遞補：由呼叫端檢查主辦方，並在同一個鎖內讓候補遞補（C 在 3.7 新增） | 3.7 |

三個 `ensure_*` 都不碰資料庫，傳入剛鎖定或讀到的 `TournamentRead`，讓呼叫端在同一次鎖定內判斷。

期中不提供（擱置的 Story）：`update_tournament`（2.5）、`reset_invite_link`（3.10）。registration 的「提高名額」（FR-9）已由 C 在 3.7 完成：後端與 API（`POST /tournaments/{id}/capacity`，限主辦方）呼叫上表的 `raise_tournament_capacity` 後在同一個鎖內遞補；S28 的修改畫面留給 2.5。

## 三、狀態轉換

| 從 → 到 | 誰呼叫 | 時機 |
| --- | --- | --- |
| `upcoming` → `open` | tournaments 的 worker 工作（2.2） | 報名開始時間到（1 分鐘內） |
| `open` → `closed` | C（3.6 報名截止） | 報名截止時，截止補位之後（C 已在 3.6 實作：worker 工作 `close_registrations` 呼叫 registration `close_registration`，轉為 `closed` 前在同一個鎖內先做優先期結算（尚未結算時）、補做先搶期、截止補位；操作者為系統） |
| `open` → `published`、`closed` → `published` | D（4.1 抽籤） | 抽籤完成；開放報名中提前抽籤時直接從 `open` 轉 |
| `published` → `ongoing` | D（5.x） | 最早一場開放報到時（開賽前 30 分鐘） |
| `ongoing` → `finished` | D（5.5） | 決賽與季軍賽確定（季軍賽取消或不存在也算） |
| 任何非 `finished` → `cancelled` | B（2.6 `cancel_tournament`） | 主辦方在 S27 取消；發出 `TournamentCancelled` |
| `closed` → `open` | B（2.5，期中擱置） | 正取不足 2 隊時延長報名 |

中文名稱：尚未開放、開放報名、報名截止、賽程已公布、進行中、已結束、已取消。

## 四、其他約定

- **操作紀錄**：2.2 在 `audit_log.tournament_id` 加上外鍵到 `tournament.id`（`core/audit.py` 的註記）。各模組寫賽事相關的操作紀錄時帶 `tournament_id`。
- **事件**（`tournaments/models.py`）：
  - `TournamentCancelled(tournament_id: UUID)`（2.6）：主辦方取消賽事時，在同一交易經 `core.events.publish` 寫入 outbox；只帶實體 id。收件規則（所有已報名隊伍的隊長與選手）由 A 的 3.9 在 notifications 登錄，登錄前不會發通知。
- **權限**：主辦方對自己賽事的權限，用 `TournamentRead.organizer_id` 交給 `core.authz.ensure_tournament_owner` 判斷。
- **裁判權限**：`core.authz.is_tournament_referee(referee_tournament_ids, tournament_id)` 與 `ensure_tournament_referee(...)`（403 `TOURNAMENT_REFEREE_REQUIRED`）只比對呼叫端已載入的「該帳號擔任裁判的賽事 id」；一般情況直接呼叫 `is_referee`。

## 五、回覆 competition.md〈三〉

1. **申訴相關函式**：同意。`mark_appealed`、`uphold_result`、`correct_result`、`replay_match` 由 B 在 6.1、6.2 時寫在 competition 新增的檔案，`competition/service.py` 只新增這幾個公開函式，D 審查。
2. **`TournamentRead` 欄位名稱**：以本文件〈一〉為準。每局預估時間叫 `game_minutes`（與 `GameTitle`、設計文件一致），不叫 `game_minutes_per_game`；`competition.md` 已同步修改。
