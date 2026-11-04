// S4 場次頁的資料來源：公開單場經產生的 client 取得，報到、比分登錄的查詢共用同一組 query key 前綴。
import { CompetitionService, type PublicMatchDetail } from "@/client"
import { parseApiError } from "@/lib/api-error"

/** 找不到場次（不存在、尚未抽籤、不屬於該賽事） */
export class MatchNotFoundError extends Error {
  constructor() {
    super("找不到這個場次")
    this.name = "MatchNotFoundError"
  }
}

/** S4 的網址；給只接受字串的地方（對戰樹場次卡的 matchHref）使用 */
export function matchPath(tournamentId: string, matchId: string): string {
  return `/tournaments/${encodeURIComponent(tournamentId)}/matches/${encodeURIComponent(matchId)}`
}

type MatchKey = { tournamentId: string; matchId: string }

/**
 * 一場的 query key 前綴：公開單場用這個 key，報到狀態與比分登錄在後面再接一段。
 * invalidate 這個前綴就會重抓這一場的所有資料（寫入成功後、倒數歸零時）。
 */
export function matchQueryKey(tournamentId: string, matchId: string) {
  return ["competition", "match", tournamentId, matchId] as const
}

/**
 * 面板查詢的 `placeholderData`：只在同一場內保留上一份資料（key 更新時不閃空白），
 * 換到另一場時不沿用，避免回應前顯示上一場的報到按鈕或各局。
 */
export function samePlaceholder(matchId: string) {
  return <T>(
    previous: T | undefined,
    query: { queryKey: readonly unknown[] } | undefined,
  ): T | undefined => (query?.queryKey[3] === matchId ? previous : undefined)
}

/**
 * 面板查詢 key 的變動部分：場次 `updated_at` 加上兩隊報到時間。
 * 後端報到成功會更新 `updated_at`（#49）；仍帶上報到時間，不靠單一欄位判斷要不要重抓。
 */
export function matchVersion(detail: {
  updated_at: string
  check_in_a_at?: string | null
  check_in_b_at?: string | null
}) {
  return [
    detail.updated_at,
    detail.check_in_a_at ?? null,
    detail.check_in_b_at ?? null,
  ] as const
}

/**
 * 取得一場的公開資料。後端回 404 `MATCH_NOT_FOUND` 時拋 `MatchNotFoundError`；
 * 網址的 id 不是 UUID（422）時這場一定不存在，也當成找不到，不算連線失敗。
 */
export async function fetchMatchDetail({
  tournamentId,
  matchId,
}: MatchKey): Promise<PublicMatchDetail> {
  try {
    const { data } = await CompetitionService.readPublicMatch({
      path: { tournament_id: tournamentId, match_id: matchId },
    })
    return data
  } catch (error) {
    const apiError = parseApiError(error)
    if (
      (apiError.kind === "business" && apiError.code === "MATCH_NOT_FOUND") ||
      apiError.kind === "validation"
    )
      throw new MatchNotFoundError()
    throw error
  }
}
