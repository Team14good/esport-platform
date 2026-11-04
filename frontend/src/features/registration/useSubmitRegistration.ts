import { useMutation, useQueryClient } from "@tanstack/react-query"

import { RegistrationService } from "@/client"
import { notifySuccess } from "@/lib/feedback"
import { myTeamsQueryOptions, teamQueryOptions } from "./queries"

export const SUBMITTED_TEXT = "已送出報名"

/**
 * S17 隊長送出報名。成功後以回應更新隊伍快取、讓 S12 我的隊伍重新取得並 Toast「已送出報名」；
 * 被拒時重新取得隊伍，讓停用原因與名單狀態跟上伺服器。錯誤訊息由 ConfirmDialog 顯示。
 */
export function useSubmitRegistration(teamId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () =>
      (
        await RegistrationService.submitRegistration({
          path: { team_id: teamId },
        })
      ).data,
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryOptions(teamId).queryKey, team)
      queryClient.invalidateQueries({
        queryKey: myTeamsQueryOptions().queryKey,
      })
      notifySuccess(SUBMITTED_TEXT)
    },
    onError: () => {
      queryClient.invalidateQueries({
        queryKey: teamQueryOptions(teamId).queryKey,
      })
    },
  })
}
