import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import {
  RegistrationService,
  type TournamentCreate,
  type TournamentRead,
  TournamentsService,
  type TournamentUpdate,
} from "@/client"
import { parseApiError } from "@/lib/api-error"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { shouldRetryQuery } from "@/lib/query-client"
import { isTournamentNotFound, PUBLIC_TOURNAMENTS_KEY } from "./queries"

export const TOURNAMENT_CANCELLED_TEXT = "已取消賽事。"

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

/**
 * 取消賽事（2.6）。成功 Toast「已取消賽事。」並以回傳值更新 S27；失敗（含 409
 * `TOURNAMENT_NOT_CANCELLABLE`）以錯誤 Toast 顯示伺服器訊息，並重抓 S27 讓狀態跟上。
 * 兩種情況都讓 S25 清單與公開賽事（S1、S2）失效，等重抓完 mutation 才結束。
 */
export function useCancelTournament(tournamentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (
        await TournamentsService.cancelMyTournament({
          path: { tournament_id: tournamentId },
        })
      ).data,
    onSuccess: (cancelled) => {
      queryClient.setQueryData(
        myTournamentQueryOptions(tournamentId).queryKey,
        cancelled,
      )
      notifySuccess(TOURNAMENT_CANCELLED_TEXT)
    },
    onError: (error) => {
      notifyError(error)
      return queryClient.invalidateQueries({
        queryKey: myTournamentQueryOptions(tournamentId).queryKey,
      })
    },
    onSettled: () =>
      Promise.all(
        [myTournamentsQueryOptions().queryKey, PUBLIC_TOURNAMENTS_KEY].map(
          (queryKey) => queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  })
}

/** 修改賽事或提高名額成功後：以回傳值更新 S27／S28，並讓 S25 清單與公開賽事重抓。 */
function useApplyTournamentUpdate(tournamentId: string) {
  const queryClient = useQueryClient()
  return (updated: TournamentRead) => {
    queryClient.setQueryData(
      myTournamentQueryOptions(tournamentId).queryKey,
      updated,
    )
    for (const queryKey of [
      myTournamentsQueryOptions().queryKey,
      PUBLIC_TOURNAMENTS_KEY,
    ]) {
      void queryClient.invalidateQueries({ queryKey })
    }
  }
}

/**
 * S28 儲存設定（2.5）：`PATCH` 只帶有變動的欄位。失敗時由呼叫端把欄位錯誤寫回表單；
 * 業務錯誤（例如 409 抽籤後、已結束或已取消）另外重抓賽事，畫面才會跟上目前的狀態。
 */
export function useUpdateTournament(tournamentId: string) {
  const queryClient = useQueryClient()
  const apply = useApplyTournamentUpdate(tournamentId)
  return useMutation({
    mutationFn: async (body: TournamentUpdate) =>
      (
        await TournamentsService.updateMyTournament({
          path: { tournament_id: tournamentId },
          body,
        })
      ).data,
    onSuccess: apply,
    onError: (error) => {
      if (parseApiError(error).kind === "business") {
        void queryClient.invalidateQueries({
          queryKey: myTournamentQueryOptions(tournamentId).queryKey,
        })
      }
    },
  })
}

/**
 * S28 提高名額：沿用 3.7 的 API，候補依順位立即遞補。業務錯誤（例如 409
 * `CAPACITY_NOT_EDITABLE`）時重抓賽事，畫面才會跟上目前的狀態。
 */
export function useRaiseCapacity(tournamentId: string) {
  const queryClient = useQueryClient()
  const apply = useApplyTournamentUpdate(tournamentId)
  return useMutation({
    mutationFn: async (capacity: number) =>
      (
        await RegistrationService.raiseCapacity({
          path: { tournament_id: tournamentId },
          body: { capacity },
        })
      ).data,
    onSuccess: apply,
    onError: (error) => {
      if (parseApiError(error).kind === "business") {
        void queryClient.invalidateQueries({
          queryKey: myTournamentQueryOptions(tournamentId).queryKey,
        })
      }
    },
  })
}
