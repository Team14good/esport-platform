// S12 我的隊伍下一場的 query。
import { queryOptions } from "@tanstack/react-query"

import { CompetitionService } from "@/client"

/** S12 停留時重抓下一場的間隔：對手確定、場次狀態改變後不必重新整理 */
export const NEXT_MATCHES_REFETCH_MS = 60_000

export const nextMatchesQueryKey = ["competition", "next-matches"] as const

/** 登入者所屬、已參賽的每支隊伍的下一場（各最多一場）。 */
export const nextMatchesQueryOptions = () =>
  queryOptions({
    queryKey: nextMatchesQueryKey,
    queryFn: async () => (await CompetitionService.listMyNextMatches()).data,
    refetchInterval: NEXT_MATCHES_REFETCH_MS,
  })
