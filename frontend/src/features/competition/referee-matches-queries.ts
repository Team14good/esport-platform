// S13 我執法的場次的 query。
import { queryOptions } from "@tanstack/react-query"

import { CompetitionService } from "@/client"

/** 指派給我、未取消的場次，依賽事分組。 */
export const refereeMatchesQueryOptions = () =>
  queryOptions({
    queryKey: ["competition", "referee-matches"],
    queryFn: async () => (await CompetitionService.listMyRefereeMatches()).data,
  })
