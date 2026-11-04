import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import { type TournamentCreate, TournamentsService } from "@/client"
import { parseApiError } from "@/lib/api-error"
import { shouldRetryQuery } from "@/lib/query-client"
import { isTournamentNotFound } from "./queries"

const ORGANIZER_TOURNAMENTS_KEY = ["tournaments", "organizer"] as const

/** S25：目前主辦方建立的賽事（新建立的在前）。 */
export const myTournamentsQueryOptions = () =>
  queryOptions({
    queryKey: [...ORGANIZER_TOURNAMENTS_KEY, "list"],
    queryFn: async () => (await TournamentsService.listMyTournaments()).data,
  })

/** 不是自己的賽事（403）：重試也不會成功。 */
export function isTournamentForbidden(error: unknown): boolean {
  return parseApiError(error).kind === "forbidden"
}

/** S27：主辦方自己的一場賽事；不存在 404、別人的賽事 403。 */
export const myTournamentQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...ORGANIZER_TOURNAMENTS_KEY, "detail", tournamentId],
    queryFn: async () =>
      (
        await TournamentsService.readMyTournament({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: (failureCount, error) =>
      !isTournamentNotFound(error) &&
      !isTournamentForbidden(error) &&
      shouldRetryQuery(failureCount, error),
  })

/**
 * S26 可選的遊戲。平台管理員新增遊戲後要立即可選（Epic 2），所以不設長的
 * staleTime：每次進入建立賽事頁都重抓。
 */
export const organizerGamesQueryOptions = () =>
  queryOptions({
    queryKey: ["tournaments", "organizer-games"],
    queryFn: async () =>
      (await TournamentsService.listGamesForOrganizer()).data,
    staleTime: 0,
  })

/** 建立賽事；成功後以回傳值填入 S27 的快取，並讓 S25 重抓。 */
export function useCreateTournament() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TournamentCreate) =>
      (await TournamentsService.createTournament({ body })).data,
    onSuccess: (created) => {
      queryClient.setQueryData(
        myTournamentQueryOptions(created.id).queryKey,
        created,
      )
      void queryClient.invalidateQueries({
        queryKey: myTournamentsQueryOptions().queryKey,
      })
    },
  })
}
