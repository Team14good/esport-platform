import { CompetitionService, type PublicBracket } from "@/client"
import { parseApiError } from "@/lib/api-error"
import { BracketNotFoundError } from "./use-bracket-polling"

/** S3 對戰樹輪詢的 query key（每個賽事一份） */
export function publicBracketQueryKey(tournamentId: string) {
  return ["competition", "bracket", tournamentId] as const
}

/**
 * 取得公開對戰樹。尚未抽籤（404 `BRACKET_NOT_FOUND`，賽事不存在也是這個代碼）時拋 `BracketNotFoundError`：
 * `useBracketPolling` 不把它算成連線失敗，照常輪詢，抽籤後就會出現。
 */
export async function fetchPublicBracket(
  tournamentId: string,
): Promise<PublicBracket> {
  try {
    const { data } = await CompetitionService.readPublicBracket({
      path: { tournament_id: tournamentId },
    })
    return data
  } catch (error) {
    // 只認後端的 BRACKET_NOT_FOUND；其他 404（例如反向代理找不到路由）照一般失敗處理，會累計成連線中斷
    const apiError = parseApiError(error)
    if (apiError.kind === "business" && apiError.code === "BRACKET_NOT_FOUND")
      throw new BracketNotFoundError()
    throw error
  }
}
