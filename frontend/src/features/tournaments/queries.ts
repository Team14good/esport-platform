import { queryOptions } from "@tanstack/react-query"

import { TournamentsService } from "@/client"
import { parseApiError } from "@/lib/api-error"
import { shouldRetryQuery } from "@/lib/query-client"

const PUBLIC_TOURNAMENTS_KEY = ["tournaments", "public"] as const

/** S1：所有公開賽事（不需登入）。 */
export const publicTournamentsQueryOptions = () =>
  queryOptions({
    queryKey: [...PUBLIC_TOURNAMENTS_KEY, "list"],
    queryFn: async () =>
      (await TournamentsService.listPublicTournaments()).data,
  })

/** 賽事不存在（404），或網址裡的 id 不是合法格式（422）：重試也不會成功。 */
export function isTournamentNotFound(error: unknown): boolean {
  const status = (error as { response?: { status?: unknown } } | null)?.response
    ?.status
  if (status === 404 || status === 422) return true
  const apiError = parseApiError(error)
  return (
    apiError.kind === "business" && apiError.code === "TOURNAMENT_NOT_FOUND"
  )
}

/** S2：一場賽事的公開資料（不需登入）。 */
export const publicTournamentQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...PUBLIC_TOURNAMENTS_KEY, "detail", tournamentId],
    queryFn: async () =>
      (
        await TournamentsService.readPublicTournament({
          path: { tournament_id: tournamentId },
        })
      ).data,
    // 不存在或 id 格式錯誤不重試；其他沿用全站規則（401 不重試）
    retry: (failureCount, error) =>
      !isTournamentNotFound(error) && shouldRetryQuery(failureCount, error),
  })
