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

class PublicRefereeInvitation(BaseModel):  # 2.7：不需登入的邀請預覽（S23，AD-19）
    tournament_name: str
    expires_at: datetime
    expired: bool

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
- 不登入就能呼叫的公開 API 用另外的 `Public*` schema（2.4 定義的 `PublicTournament`），不含 `organizer_id`、Email 與學校（AD-19）。
- 裁判 API（2.7）：
  - `POST /organizer/tournaments/{tournament_id}/referee-invitation`（主辦方）：產生新邀請，201 回 `RefereeInvitationRead`；同賽事尚未過期的舊邀請 `expires_at` 設為現在（不刪除）。
  - `GET /organizer/tournaments/{tournament_id}/referee-invitation`（主辦方）：最新一筆邀請（含 `expired`），從未產生回 `null`。
  - `GET /organizer/tournaments/{tournament_id}/referees`（主辦方）：`list[RefereeRead]`，依接受時間排序。
  - 以上三支：不存在 404 `TOURNAMENT_NOT_FOUND`、別人的賽事 403 `TOURNAMENT_OWNER_REQUIRED`；產生邀請時賽事已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`。
  - `GET /referee-invites/{token}`（不需登入）：`PublicRefereeInvitation`；不存在 404 `REFEREE_INVITATION_NOT_FOUND`，過期仍回 200（`expired: true`）。
  - `POST /referee-invites/{token}/accept`（已驗證 Email）：200 回 `RefereeRead`；已是裁判回原本的資料（冪等）。不存在 404、過期或已作廢 409 `REFEREE_INVITATION_EXPIRED`、賽事已結束或已取消 409 `TOURNAMENT_NOT_ACCEPTING_REFEREES`、主辦方本人 409 `ORGANIZER_CANNOT_BE_REFEREE`、未登入 401、未驗證 403 `EMAIL_NOT_VERIFIED`。
  - 不檢查受邀者是否為參賽隊員，由 4.4 指派裁判時檢查。
- 公開 API（2.4，不需登入）：`GET /tournaments` 回傳所有賽事的 `list[PublicTournament]`，依開賽時間排序；`GET /tournaments/{tournament_id}` 回傳 `PublicTournament`，不存在 404 `TOURNAMENT_NOT_FOUND`，id 格式錯誤 422。

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
| `bo_for_round(session, *, tournament_id, round_no) -> int` | D（4.3、5.3、5.4） | 期中一律回傳 `TournamentRead.bo`（2.3 分輪 BO 擱置）；`round_no` 從 1 起算 | 2.2 |
| `is_referee(session, *, tournament_id, account_id) -> bool` | D（4.4） | 已接受該賽事的裁判邀請；只在該賽事有效（經 `core.authz.is_tournament_referee` 判斷） | 2.7 |
| `list_referees(session, *, tournament_id) -> list[RefereeRead]` | D（4.4 的 S30 選單） | 依接受邀請的時間排序 | 2.7 |
| `has_referee_role(session, *, account_id) -> bool` | 組裝層（`app/api/main.py`）註冊給 identity 的 `register_referee_lookup`（4.4 S13） | 帳號是不是任一賽事的裁判（有 `TournamentReferee` 列即是，不看賽事狀態）；身分切換器的「裁判」用 | 4.4 |
| `ensure_accepting_referees(tournament: TournamentRead) -> None` | tournaments 的裁判邀請（2.7）；其他模組需要時可呼叫 | 狀態為 `finished`、`cancelled` 時拋 `TOURNAMENT_NOT_ACCEPTING_REFEREES` 409；不碰資料庫 | 2.7 |

三個 `ensure_*` 都不碰資料庫，傳入剛鎖定或讀到的 `TournamentRead`，讓呼叫端在同一次鎖定內判斷。

期中不提供（擱置的 Story）：`update_tournament`、`cancel_tournament`（2.5、2.6）、`reset_invite_link`（3.10）、`list_audit_logs`（2.8）。registration 的「提高名額」（FR-9）同樣到期末。

## 三、狀態轉換

| 從 → 到 | 誰呼叫 | 時機 |
| --- | --- | --- |
| `upcoming` → `open` | tournaments 的 worker 工作（2.2） | 報名開始時間到（1 分鐘內） |
| `open` → `closed` | C（3.6 報名截止） | 報名截止時，截止補位之後 |
| `open` → `published`、`closed` → `published` | D（4.1 抽籤） | 抽籤完成；開放報名中提前抽籤時直接從 `open` 轉 |
| `published` → `ongoing` | D（5.x） | 最早一場開放報到時（開賽前 30 分鐘） |
| `ongoing` → `finished` | D（5.5） | 決賽與季軍賽確定（季軍賽取消或不存在也算） |
| 任何非 `finished` → `cancelled` | B（2.6，期中擱置） | 主辦方取消；期中只保留轉換規則與防呆 |
| `closed` → `open` | B（2.5，期中擱置） | 正取不足 2 隊時延長報名 |

中文名稱：尚未開放、開放報名、報名截止、賽程已公布、進行中、已結束、已取消。

## 四、其他約定

- **操作紀錄**：2.2 在 `audit_log.tournament_id` 加上外鍵到 `tournament.id`（`core/audit.py` 的註記）。各模組寫賽事相關的操作紀錄時帶 `tournament_id`。
- **事件**：tournaments 期中不發其他模組需要處理的事件；之後新增時補在這裡。
- **權限**：主辦方對自己賽事的權限，用 `TournamentRead.organizer_id` 交給 `core.authz.ensure_tournament_owner` 判斷。
- **裁判權限**：`core.authz.is_tournament_referee(referee_tournament_ids, tournament_id)` 與 `ensure_tournament_referee(...)`（403 `TOURNAMENT_REFEREE_REQUIRED`）只比對呼叫端已載入的「該帳號擔任裁判的賽事 id」；一般情況直接呼叫 `is_referee`。

## 五、回覆 competition.md〈三〉

1. **申訴相關函式**：同意。`mark_appealed`、`uphold_result`、`correct_result`、`replay_match` 由 B 在 6.1、6.2 時寫在 competition 新增的檔案，`competition/service.py` 只新增這幾個公開函式，D 審查。
2. **`TournamentRead` 欄位名稱**：以本文件〈一〉為準。每局預估時間叫 `game_minutes`（與 `GameTitle`、設計文件一致），不叫 `game_minutes_per_game`；`competition.md` 已同步修改。
