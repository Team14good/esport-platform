import { useMutation, useQueryClient } from "@tanstack/react-query"

import { RegistrationService } from "@/client"
import { notifySuccess } from "@/lib/feedback"
import { myTeamsQueryOptions, teamQueryOptions } from "./queries"

export const WITHDRAWN_TEXT = "已撤回報名"

/**
 * S17 隊長在抽籤前退賽（Story 3.7）。成功後以回應更新隊伍快取、讓 S12 我的隊伍重新取得並
 * Toast「已撤回報名」；被拒時也重新取得隊伍與 S12，讓狀態與「退賽」按鈕跟上伺服器。錯誤訊息由
 * ConfirmDialog 顯示。
 */
export function useWithdrawRegistration(teamId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () =>
      (
        await RegistrationService.withdrawRegistration({
          path: { team_id: teamId },
        })
      ).data,
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryOptions(teamId).queryKey, team)
      queryClient.invalidateQueries({
        queryKey: myTeamsQueryOptions().queryKey,
      })
      notifySuccess(WITHDRAWN_TEXT)
    },
    onError: () => {
      queryClient.invalidateQueries({
        queryKey: teamQueryOptions(teamId).queryKey,
      })
      queryClient.invalidateQueries({
        queryKey: myTeamsQueryOptions().queryKey,
      })
    },
  })
}
