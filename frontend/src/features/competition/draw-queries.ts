// S27 抽籤按鈕（4.1）的 query 與 mutation。
import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import { CompetitionService } from "@/client"
import {
  myTournamentQueryOptions,
  myTournamentsQueryOptions,
} from "@/features/tournaments/organizer-queries"
import {
  publicTournamentQueryOptions,
  publicTournamentsQueryOptions,
} from "@/features/tournaments/queries"
import { parseApiError } from "@/lib/api-error"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { shouldRetryQuery } from "@/lib/query-client"
import { managedMatchesQueryOptions } from "./organizer-matches-queries"

export const DRAWN_TEXT = "已完成抽籤"

/** 非主辦方（403）與其他業務錯誤（4xx）：重試也不會成功。 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  const { kind } = parseApiError(error)
  return (
    kind !== "forbidden" &&
    kind !== "business" &&
    shouldRetryQuery(failureCount, error)
  )
}

/** 現在能不能抽籤（後端用抽籤的同一套規則預估，不寫入）。 */
export const drawStatusQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: ["competition", "draw-status", tournamentId],
    queryFn: async () =>
      (
        await CompetitionService.readDrawStatus({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
    // 後端預估要持有賽事列鎖並重做分配，所以用 staleTime 限制頻率：
    // 停在 S27 的主辦方切回分頁時，資料超過 30 秒才重抓；抽籤後的 invalidate 不受 staleTime 影響
    staleTime: 30_000,
  })

/**
 * 抽籤。成功 Toast「已完成抽籤」，失敗（含 409 `NOT_ENOUGH_TEAMS`）以錯誤 Toast 顯示後端訊息；
 * 兩種情況都重抓後台與公開的賽事、場次與抽籤狀態，等重抓完 mutation 才結束（按鈕隨之消失或停用）。
 */
export function useDraw(tournamentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (
        await CompetitionService.draw({
          path: { tournament_id: tournamentId },
        })
      ).data,
    onSuccess: () => notifySuccess(DRAWN_TEXT),
    onError: notifyError,
    onSettled: () =>
      Promise.all(
        [
          drawStatusQueryOptions(tournamentId).queryKey,
          myTournamentQueryOptions(tournamentId).queryKey,
          myTournamentsQueryOptions().queryKey,
          managedMatchesQueryOptions(tournamentId).queryKey,
          // 公開賽事（S1 列表、S2 詳情）：同一次瀏覽切過去要看到新狀態
          publicTournamentQueryOptions(tournamentId).queryKey,
          publicTournamentsQueryOptions().queryKey,
        ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      ),
  })
}
