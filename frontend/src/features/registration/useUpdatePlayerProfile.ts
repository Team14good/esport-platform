import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { RegistrationService } from "@/client"
import type { PlayerProfileValues } from "./PlayerProfileDialog"
import { teamQueryOptions } from "./queries"

/**
 * S18 存自己的參賽資料（multipart）。成功後以回應更新 S17 的隊伍快取；
 * 上傳截圖時 `uploadProgress` 為 0～100，沒有在上傳時為 null。
 */
export function useUpdatePlayerProfile(teamId: string) {
  const queryClient = useQueryClient()
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const mutation = useMutation({
    mutationFn: async (values: PlayerProfileValues) => {
      const screenshot = values.rank_screenshot
      setUploadProgress(screenshot ? 0 : null)
      try {
        return (
          await RegistrationService.updateMyPlayerProfile({
            path: { team_id: teamId },
            body: {
              game_account_id: values.game_account_id,
              rank_tier: values.rank_tier,
              // 未附檔表示保留已上傳的截圖
              rank_screenshot: screenshot ?? undefined,
            },
            onUploadProgress: screenshot
              ? (event) => {
                  if (event.total) {
                    setUploadProgress((event.loaded / event.total) * 100)
                  }
                }
              : undefined,
          })
        ).data
      } finally {
        setUploadProgress(null)
      }
    },
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryOptions(teamId).queryKey, team)
    },
    // 被拒（例如名單已鎖定、賽事已截止）時重新取得隊伍，讓 profile_editable 跟上
    onError: () => {
      queryClient.invalidateQueries({
        queryKey: teamQueryOptions(teamId).queryKey,
      })
    },
  })

  return { save: mutation.mutateAsync, uploadProgress }
}
