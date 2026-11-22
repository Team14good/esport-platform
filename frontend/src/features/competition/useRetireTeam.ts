import { useMutation, useQueryClient } from "@tanstack/react-query"

import { CompetitionService } from "@/client"
import {
  myTeamsQueryOptions,
  teamQueryOptions,
} from "@/features/registration/queries"
import { notifySuccess } from "@/lib/feedback"
import { nextMatchesQueryKey } from "./next-match-queries"
import { retirementQueryKey } from "./retirement-queries"

export const RETIRED_TEXT = "已退賽"

/**
 * S17 隊長在抽籤後退賽（Story 4.5）。成功後 Toast「已退賽」，並讓隊伍（S17）、我的隊伍與
 * 下一場（S12）、退賽狀態重新取得；被拒時也重新取得，讓畫面跟上伺服器。錯誤訊息由
 * ConfirmDialog 顯示。S3 對戰樹每 5 秒輪詢，不必另外失效。
 */
export function useRetireTeam(teamId: string) {
  const queryClient = useQueryClient()

  const refresh = () => {
    for (const queryKey of [
      teamQueryOptions(teamId).queryKey,
      myTeamsQueryOptions().queryKey,
      nextMatchesQueryKey,
      retirementQueryKey(teamId),
    ]) {
      queryClient.invalidateQueries({ queryKey })
    }
  }

  return useMutation({
    mutationFn: async () =>
      (await CompetitionService.retireTeam({ path: { team_id: teamId } })).data,
    onSuccess: () => {
      refresh()
      notifySuccess(RETIRED_TEXT)
    },
    onError: refresh,
  })
}
