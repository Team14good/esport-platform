// S30 場次管理（4.3 修改時間、4.4 指派裁判）的 query 與 mutation。
import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import { CompetitionService, TournamentsService } from "@/client"
import { parseApiError } from "@/lib/api-error"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { shouldRetryQuery } from "@/lib/query-client"

export const BRACKET_NOT_FOUND_CODE = "BRACKET_NOT_FOUND"

const MANAGED_MATCHES_KEY = ["competition", "managed-matches"] as const

/** 尚未抽籤：404 `BRACKET_NOT_FOUND`。 */
export function isBracketNotFound(error: unknown): boolean {
  const parsed = parseApiError(error)
  return parsed.kind === "business" && parsed.code === BRACKET_NOT_FOUND_CODE
}

/** 非主辦方（403）、尚未抽籤與其他業務錯誤（4xx）：重試也不會成功。 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  const { kind } = parseApiError(error)
  return (
    kind !== "forbidden" &&
    kind !== "business" &&
    shouldRetryQuery(failureCount, error)
  )
}

/** S30 場次列表（含能否改時間、可指派的裁判）。 */
export const managedMatchesQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...MANAGED_MATCHES_KEY, tournamentId],
    queryFn: async () =>
      (
        await CompetitionService.listManagedMatches({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** 賽事的裁判（已接受邀請），用 `account_id` 對應列表的裁判欄。 */
export const tournamentRefereesQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "referees", tournamentId],
    queryFn: async () =>
      (
        await TournamentsService.listTournamentReferees({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** 成功或失敗（含所有 409）都重抓列表：回傳 promise，讓 mutation 等到列表更新才結束。 */
function useRefetchMatches(tournamentId: string) {
  const queryClient = useQueryClient()
  return () =>
    queryClient.invalidateQueries({
      queryKey: managedMatchesQueryOptions(tournamentId).queryKey,
    })
}

/** 修改場次時間；`scheduledAt` 是 UTC 的 ISO 字串。 */
export function useRescheduleMatch(tournamentId: string, matchId: string) {
  const refetch = useRefetchMatches(tournamentId)
  return useMutation({
    mutationFn: async (scheduledAt: string) =>
      (
        await CompetitionService.rescheduleMatch({
          path: { tournament_id: tournamentId, match_id: matchId },
          body: { scheduled_at: scheduledAt },
        })
      ).data,
    onSuccess: () => notifySuccess("已修改場次時間"),
    onError: notifyError,
    onSettled: refetch,
  })
}

/** 指派裁判；`accountId` 為 null 代表收回，之後由主辦方登錄比分。 */
export function useSetReferee(tournamentId: string, matchId: string) {
  const refetch = useRefetchMatches(tournamentId)
  return useMutation({
    mutationFn: async (accountId: string | null) => {
      const path = { tournament_id: tournamentId, match_id: matchId }
      if (accountId === null) {
        return (await CompetitionService.unassignReferee({ path })).data
      }
      return (
        await CompetitionService.assignReferee({
          path,
          body: { account_id: accountId },
        })
      ).data
    },
    onSuccess: (_data, accountId) =>
      notifySuccess(accountId === null ? "已收回裁判" : "已指派裁判"),
    onError: notifyError,
    onSettled: refetch,
  })
}
