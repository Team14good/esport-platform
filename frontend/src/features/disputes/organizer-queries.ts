// 主辦方處理申訴（6.2）：S32 申訴列表、處理申訴、重賽時間範圍，以及 S27 待處理清單；
// 主辦方處理檢舉（6.5）：S33 檢舉列表、處理檢舉。
import { queryOptions, useQueryClient } from "@tanstack/react-query"

import {
  type AppealResolveIn,
  DisputesService,
  type OpenDisputes,
  type ReportResolveIn,
} from "@/client"
import { publicBracketQueryKey } from "@/features/competition/bracket-queries"
import { managedMatchesQueryOptions } from "@/features/competition/organizer-matches-queries"
import { myTournamentQueryOptions } from "@/features/tournaments/organizer-queries"
import { parseApiError } from "@/lib/api-error"
import { shouldRetryQuery } from "@/lib/query-client"

const DISPUTES_KEY = ["disputes", "organizer"] as const

/** 非主辦方（403）與其他業務錯誤（4xx）：重試也不會成功。 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  const { kind } = parseApiError(error)
  return (
    kind !== "forbidden" &&
    kind !== "business" &&
    shouldRetryQuery(failureCount, error)
  )
}

/** S32：該賽事的申訴，依場次分組（未結案在前）。 */
export const tournamentAppealsQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...DISPUTES_KEY, "appeals", tournamentId],
    queryFn: async () =>
      (
        await DisputesService.listTournamentAppeals({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** S27 待處理清單：未結案的申訴（與 6.4 起的檢舉）。 */
export const openDisputesQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...DISPUTES_KEY, "open-disputes", tournamentId],
    queryFn: async () =>
      (
        await DisputesService.readOpenDisputes({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** S32 重新比賽的時間範圍；對話框開啟時才查詢，每次開啟都取最新值。 */
export const replayWindowQueryOptions = (
  tournamentId: string,
  matchId: string,
) =>
  queryOptions({
    queryKey: [...DISPUTES_KEY, "replay-window", tournamentId, matchId],
    queryFn: async () =>
      (
        await DisputesService.readReplayWindow({
          path: { tournament_id: tournamentId, match_id: matchId },
        })
      ).data,
    retry: shouldRetry,
    staleTime: 0,
  })

/** 處理同一場次的申訴；失敗時拋出（AxiosError），由對話框顯示伺服器訊息。 */
export async function resolveAppeals({
  tournamentId,
  matchId,
  body,
}: {
  tournamentId: string
  matchId: string
  body: AppealResolveIn
}) {
  return (
    await DisputesService.resolveAppeals({
      path: { tournament_id: tournamentId, match_id: matchId },
      body,
    })
  ).data
}

/** 處理後（成功或失敗）重抓 S32 列表與 S27 待處理清單。 */
export function useRefetchAppeals(tournamentId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: tournamentAppealsQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: openDisputesQueryOptions(tournamentId).queryKey,
      }),
    ])
}

/** S33：該賽事的檢舉（處理中在前，各組依提出時間由舊到新）。 */
export const tournamentReportsQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: [...DISPUTES_KEY, "reports", tournamentId],
    queryFn: async () =>
      (
        await DisputesService.listTournamentReports({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** 處理一筆檢舉（駁回或屬實）；失敗時拋出（AxiosError），由對話框顯示伺服器訊息。 */
export async function resolveReport({
  reportId,
  body,
}: {
  reportId: string
  body: ReportResolveIn
}) {
  return (
    await DisputesService.resolveReport({
      path: { report_id: reportId },
      body,
    })
  ).data
}

/**
 * 處理檢舉後（成功或失敗）重抓 S33 列表；屬實時會取消資格、改對戰表、一併結案申訴，
 * 所以 S32 列表、S27 賽事與待處理清單、S30 場次與公開對戰樹也重抓。
 */
export function useRefetchReports(tournamentId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: tournamentReportsQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: tournamentAppealsQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: openDisputesQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: myTournamentQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: managedMatchesQueryOptions(tournamentId).queryKey,
      }),
      queryClient.invalidateQueries({
        queryKey: publicBracketQueryKey(tournamentId),
      }),
    ])
}

/**
 * 待處理清單與後端同一順序：沒有期限的檢舉排在最後；
 * 再依處理期限由近到遠、提出時間、id（id 讓順序固定）。
 */
export function sortOpenItems(items: OpenDisputes["items"]) {
  return [...items].sort(
    (a, b) =>
      Number(a.deadline === null) - Number(b.deadline === null) ||
      (a.deadline !== null && b.deadline !== null
        ? Date.parse(a.deadline) - Date.parse(b.deadline)
        : 0) ||
      Date.parse(a.filed_at) - Date.parse(b.filed_at) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
}
