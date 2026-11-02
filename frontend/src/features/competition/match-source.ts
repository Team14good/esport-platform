// S4 場次頁唯一的資料來源；元件不呼叫 API，只透過這個函式取得資料。
// 第一階段：公開的單場 API 還沒合併，只在開發模式（import.meta.env.DEV）回傳由對戰樹假資料推導的場次；
// 正式 build 一律拋出 MatchNotFoundError（S4 顯示 404），不會出現假的比分。
// 第二階段：換成呼叫產生的 client（frontend/src/client），API 回 404 時同樣拋出 MatchNotFoundError。
import type { PublicMatchDetail } from "./match-types"

/** 找不到場次（不存在、或正式 build 尚未開放） */
export class MatchNotFoundError extends Error {
  constructor() {
    super("找不到這個場次")
    this.name = "MatchNotFoundError"
  }
}

/** 開發模式假對戰樹的賽事 id（與 createBracketFixture 相同），/dev/bracket 的卡片連結用它 */
export const DEV_MATCH_SOURCE_TOURNAMENT_ID = "tournament-fixture"

/** S4 的網址；給只接受字串的地方（對戰樹場次卡的 matchHref）使用 */
export function matchPath(tournamentId: string, matchId: string): string {
  return `/tournaments/${encodeURIComponent(tournamentId)}/matches/${encodeURIComponent(matchId)}`
}

type MatchKey = { tournamentId: string; matchId: string }

let devDetails: ((matchId: string) => PublicMatchDetail | undefined) | null =
  null

async function fetchDevMatchDetail({
  tournamentId,
  matchId,
}: MatchKey): Promise<PublicMatchDetail> {
  if (devDetails === null) {
    // 動態 import：正式 build 時這個分支被移除，假資料不會進 bundle
    const [{ createBracketFixture }, { matchDetailFromBracket }] =
      await Promise.all([
        import("./bracket-fixtures"),
        import("./match-fixtures"),
      ])
    const bracket = createBracketFixture({
      teamCount: 32,
      scenario: "in_progress",
    })
    devDetails = (id) => matchDetailFromBracket(bracket, id)
  }
  const detail =
    tournamentId === DEV_MATCH_SOURCE_TOURNAMENT_ID
      ? devDetails(matchId)
      : undefined
  if (detail === undefined) throw new MatchNotFoundError()
  return detail
}

/** 取得一場的公開資料；找不到時拋出 MatchNotFoundError。 */
export async function fetchMatchDetail(
  key: MatchKey,
): Promise<PublicMatchDetail> {
  if (import.meta.env.DEV) return fetchDevMatchDetail(key)
  throw new MatchNotFoundError()
}
