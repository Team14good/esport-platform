// 公開對戰樹的資料型別，照 _bmad-output/implementation-artifacts/contracts/competition.md 的 PublicBracket 先自己寫。
// 第二階段改用產生的 client 型別後刪除。

/** 場次狀態（competition/models.py 的 MatchStatus） */
export type MatchStatus =
  | "scheduled"
  | "live"
  | "appeal_window"
  | "appealed"
  | "confirmed"
  | "voided"

/** 場次結果（competition/models.py 的 MatchOutcome） */
export type MatchOutcome =
  | "played"
  | "forfeit"
  | "double_forfeit"
  | "walkover"
  | "disqualified"

export type BracketSide = "a" | "b"

export type PublicTeamRef = {
  id: string
  name: string
}

export type PublicMatch = {
  id: string
  /** 顯示用編號「M3」：依輪次、同輪由上到下，輪空不佔編號 */
  code: string
  /** 1 起算；季軍賽與決賽同輪 */
  round_no: number
  /** 該輪位置 + 1；第一輪輪空的位置留空號；季軍賽排在決賽之後 */
  slot_no: number
  is_third_place: boolean
  /** 未確定時為 null */
  team_a: PublicTeamRef | null
  team_b: PublicTeamRef | null
  /** 待定時的說明，例如「M4 勝者」「M29 敗者」 */
  source_a: string | null
  source_b: string | null
  /** 該方由輪空直接進入本輪；第二輪可能兩方都是（例如 9 隊時第二輪 4 場有 3 場） */
  bye_a: boolean
  bye_b: boolean
  /** ISO 時間 */
  scheduled_at: string
  status: MatchStatus
  outcome: MatchOutcome | null
  winner_id: string | null
  wins_a: number
  wins_b: number
}

export type PublicBracket = {
  tournament_id: string
  rounds: number
  /** 各輪欄頭，例如 ["16 強", "8 強", "4 強", "決賽"] */
  round_names: string[]
  matches: PublicMatch[]
  /** ISO 時間 */
  updated_at: string
}
