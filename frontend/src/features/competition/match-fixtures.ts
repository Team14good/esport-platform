// S4 場次頁的假資料：從 createBracketFixture 的對戰樹推導每一場的 PublicMatchDetail，
// 只給單元測試使用（S4 已接上公開單場 API，正式畫面不再用假資料）。
import type {
  PublicBracket,
  PublicGame,
  PublicMatch,
  PublicMatchDetail,
  ScoreType,
} from "@/client"
import { type BracketSide, hasScore } from "./match-status"

export const FIXTURE_TOURNAMENT_NAME = "2026 秋季校際盃"
export const FIXTURE_GAME_NAME = "特戰英豪"
export const FIXTURE_BEST_OF = 3
/** rounds 型態每局勝方的回合數 */
const ROUNDS_TO_WIN = 13

/**
 * 依系列比分排出固定的局序：勝局較多的一方先拿第一局、兩方交替，一方用完後由另一方補齊，
 * 所以系列勝方一定拿下最後一局。平手（進行中）時由 A 先。
 */
export function gameWinners(winsA: number, winsB: number): BracketSide[] {
  const first: BracketSide = winsB > winsA ? "b" : "a"
  const second: BracketSide = first === "a" ? "b" : "a"
  const left: Record<BracketSide, number> = { a: winsA, b: winsB }
  const order: BracketSide[] = []
  while (left.a + left.b > 0) {
    for (const side of [first, second]) {
      if (left[side] > 0) {
        order.push(side)
        left[side] -= 1
      }
    }
  }
  return order
}

/** 比分型態依場次交替（奇數編號 rounds、偶數 win_loss），讓兩種都看得到 */
export function fixtureScoreType(match: PublicMatch): ScoreType {
  const n = Number.parseInt(match.code.replace(/\D/g, ""), 10)
  return Number.isNaN(n) || n % 2 === 1 ? "rounds" : "win_loss"
}

function fixtureGames(match: PublicMatch, scoreType: ScoreType): PublicGame[] {
  if (!hasScore(match)) return []
  const seed = Number.parseInt(match.code.replace(/\D/g, ""), 10) || 0
  return gameWinners(match.wins_a, match.wins_b).map((winner, i) => {
    const gameNo = i + 1
    if (scoreType === "win_loss") {
      return {
        game_no: gameNo,
        winner_side: winner,
        score_a: null,
        score_b: null,
      }
    }
    // 敗方回合數 5～11，依場次與局數固定
    const loserRounds = 5 + ((seed * 3 + gameNo * 5) % 7)
    return {
      game_no: gameNo,
      winner_side: winner,
      score_a: winner === "a" ? ROUNDS_TO_WIN : loserRounds,
      score_b: winner === "b" ? ROUNDS_TO_WIN : loserRounds,
    }
  })
}

/** 同輪場次的排列：一般場次依位置，季軍賽排在決賽之後 */
function sameRoundOrder(a: PublicMatch, b: PublicMatch) {
  return (
    Number(a.is_third_place) - Number(b.is_third_place) || a.slot_no - b.slot_no
  )
}

/** 假資料的申訴期長度：預定時間後 2 小時截止 */
const FIXTURE_APPEAL_WINDOW_MS = 2 * 60 * 60 * 1000

/** 申訴期、申訴中的場次才有截止時間，其他狀態為 null */
function fixtureAppealDeadline(match: PublicMatch): string | null {
  if (match.status !== "appeal_window" && match.status !== "appealed")
    return null
  const scheduled = Date.parse(match.scheduled_at)
  if (Number.isNaN(scheduled)) return null
  return new Date(scheduled + FIXTURE_APPEAL_WINDOW_MS).toISOString()
}

/** 假資料的申訴時限（賽事預設 30 分鐘）：開始時間＝截止－時限，與後端算法相同 */
const FIXTURE_APPEAL_MINUTES_MS = 30 * 60 * 1000

function fixtureAppealStartedAt(deadline: string | null): string | null {
  if (deadline === null) return null
  return new Date(
    Date.parse(deadline) - FIXTURE_APPEAL_MINUTES_MS,
  ).toISOString()
}

/** 由一份對戰樹推導其中一場的 PublicMatchDetail；找不到時回傳 undefined。 */
export function matchDetailFromBracket(
  bracket: PublicBracket,
  matchId: string,
): PublicMatchDetail | undefined {
  const match = bracket.matches.find((m) => m.id === matchId)
  if (match === undefined) return undefined
  const scoreType = fixtureScoreType(match)
  return {
    ...match,
    tournament: { id: bracket.tournament_id, name: FIXTURE_TOURNAMENT_NAME },
    game_name: FIXTURE_GAME_NAME,
    best_of: FIXTURE_BEST_OF,
    score_type: scoreType,
    round_name: bracket.round_names[match.round_no - 1] ?? "",
    games: fixtureGames(match, scoreType),
    same_round: bracket.matches
      .filter((m) => m.round_no === match.round_no && m.id !== match.id)
      .sort(sameRoundOrder),
    appeal_deadline: fixtureAppealDeadline(match),
    appeal_started_at: fixtureAppealStartedAt(fixtureAppealDeadline(match)),
    updated_at: bracket.updated_at,
  }
}
