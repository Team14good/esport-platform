// S4 場次頁的公開單場資料型別。contracts/competition.md 還沒有定義公開的單場 API，
// 這份形狀是第二階段要請 D 補進 contract 的提議；改用產生的 client 型別後刪除。
import type { BracketSide, PublicMatch } from "./bracket-types"

/** 比分型態：win_loss 只記勝負；rounds 記每局回合數（不可平手） */
export type ScoreType = "win_loss" | "rounds"

/** 已登錄的一局 */
export type PublicGame = {
  /** 1 起算 */
  game_no: number
  winner_side: BracketSide
  /** rounds 型態的回合數；win_loss 型態為 null */
  score_a: number | null
  score_b: number | null
}

export type PublicMatchDetail = PublicMatch & {
  tournament: { id: string; name: string }
  /** 遊戲名稱（賽事建立時的快照），例如「特戰英豪」 */
  game_name: string
  /** 本輪 BO */
  best_of: number
  score_type: ScoreType
  /** 輪次名稱，例如「32 強」「決賽」（與 PublicBracket.round_names 相同用語） */
  round_name: string
  /** 已登錄的局，依 game_no 遞增；段位截圖不出現在公開 API（AD-19） */
  games: PublicGame[]
  /** 同一輪的其他場次（不含自己）；季軍賽與決賽同輪，會互相列出 */
  same_round: PublicMatch[]
  /** 申訴期截止時間（ISO）；申訴期、申訴中才有值，其他狀態為 null */
  appeal_deadline: string | null
  /** ISO 時間 */
  updated_at: string
}
