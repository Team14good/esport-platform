// 主辦方處理申訴（6.2）：S32 申訴列表、處理申訴、重賽時間範圍，以及 S27 待處理清單。
import { queryOptions, useQueryClient } from "@tanstack/react-query"

import {
  type AppealDecision,
  type AppealGroup,
  type AppealResolveIn,
  DisputesService,
  type OpenDisputes,
} from "@/client"
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

/** S27 待處理清單：未結案的申訴（檢舉由 6.5 接上，目前一律 0）。 */
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

/**
 * 處理後（成功或失敗）重抓 S32 列表與 S27 待處理清單，以及會隨處理改變的主辦方賽事詳情
 * （決賽處理後賽事轉為已結束，S27 摘要要跟著變）與 S30 場次列表。
 */
export function useRefetchAppeals(tournamentId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all(
      [
        tournamentAppealsQueryOptions(tournamentId).queryKey,
        openDisputesQueryOptions(tournamentId).queryKey,
        myTournamentQueryOptions(tournamentId).queryKey,
        managedMatchesQueryOptions(tournamentId).queryKey,
      ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    )
}

/**
 * 同一場次的申訴中最後一次處理的決定（`handled_at` 最新的一筆），與 S4 公開結果一致。
 * 結案時一定會寫 `handled_at`；萬一缺少，排在有時間的處理之前。
 */
export function latestDecision(
  appeals: AppealGroup["appeals"],
): AppealDecision | null {
  let latest: AppealDecision | null = null
  let latestAt = Number.NEGATIVE_INFINITY
  for (const appeal of appeals) {
    if (!appeal.decision) continue
    const at = appeal.handled_at
      ? Date.parse(appeal.handled_at)
      : Number.NEGATIVE_INFINITY
    if (latest === null || at > latestAt) {
      latest = appeal.decision
      latestAt = at
    }
  }
  return latest
}

/** 待處理清單依處理期限由近到遠（同期限依提出時間）。 */
export function sortOpenItems(items: OpenDisputes["items"]) {
  return [...items].sort(
    (a, b) =>
      Date.parse(a.deadline) - Date.parse(b.deadline) ||
      Date.parse(a.filed_at) - Date.parse(b.filed_at),
  )
}
