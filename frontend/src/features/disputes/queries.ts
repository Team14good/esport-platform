import { queryOptions } from "@tanstack/react-query"

import { DisputesService } from "@/client"

/** disputes 相關 query 的共同前綴。 */
export const DISPUTES_QUERY_KEY = ["disputes"] as const

/**
 * S20 檢舉對象選單。不符資格（403、409）時重試也不會成功，所以不重試
 * （全站預設會對 403／409 重試 3 次）。
 */
export const reportableTeamsQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...DISPUTES_QUERY_KEY, "reportable-teams", tournamentId],
    queryFn: async () =>
      (
        await DisputesService.listReportableTeams({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: false,
  })
