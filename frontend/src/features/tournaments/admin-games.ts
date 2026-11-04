import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import {
  type GameIn,
  type GameRead,
  type ScoreType,
  TournamentsService,
} from "@/client"
import { notifySuccess } from "@/lib/feedback"

export const GAME_CREATED_TOAST_TEXT = "已新增遊戲"
export const GAME_SAVED_TOAST_TEXT = "已儲存變更"

/** 比分型態的顯示文字。 */
export const SCORE_TYPE_LABELS: Record<ScoreType, string> = {
  win_loss: "只記勝負",
  rounds: "記回合比分",
}

const ADMIN_GAMES_KEY = ["tournaments", "admin", "games"]

/** S36 的遊戲列表（後端依名稱排序、不分頁）。 */
export const adminGamesQueryOptions = () =>
  queryOptions({
    queryKey: [...ADMIN_GAMES_KEY, "list"],
    queryFn: async () => (await TournamentsService.listGames()).data,
  })

/** S36 編輯頁的一款遊戲；不存在時後端回 404 `GAME_NOT_FOUND`。 */
export const adminGameQueryOptions = (gameId: string) =>
  queryOptions({
    queryKey: [...ADMIN_GAMES_KEY, "detail", gameId],
    queryFn: async () =>
      (await TournamentsService.readGame({ path: { game_id: gameId } })).data,
    // 404 不會因為重試而變好
    retry: false,
  })

export function useAdminGames() {
  return useQuery(adminGamesQueryOptions())
}

export function useAdminGame(gameId: string) {
  return useQuery(adminGameQueryOptions(gameId))
}

export function useCreateGame() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: GameIn) =>
      (await TournamentsService.createGame({ body })).data,
    onSuccess: (created: GameRead) => {
      notifySuccess(GAME_CREATED_TOAST_TEXT)
      queryClient.setQueryData(
        adminGameQueryOptions(created.id).queryKey,
        created,
      )
      // 只重抓列表；剛寫入的這款遊戲不必重抓
      void queryClient.invalidateQueries({
        queryKey: adminGamesQueryOptions().queryKey,
      })
    },
  })
}

export function useUpdateGame(gameId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: GameIn) =>
      (await TournamentsService.updateGame({ path: { game_id: gameId }, body }))
        .data,
    onSuccess: (updated: GameRead) => {
      notifySuccess(GAME_SAVED_TOAST_TEXT)
      queryClient.setQueryData(
        adminGameQueryOptions(updated.id).queryKey,
        updated,
      )
      void queryClient.invalidateQueries({
        queryKey: adminGamesQueryOptions().queryKey,
      })
    },
  })
}
