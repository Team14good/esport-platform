import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { DisputesService } from "@/client"
import {
  myTeamsQueryOptions,
  REGISTRATION_QUERY_KEY,
} from "@/features/registration/queries"
import { publicTournamentQueryOptions } from "@/features/tournaments/queries"
import { parseApiError } from "@/lib/api-error"
import { reportableTeamsQueryOptions } from "./queries"
import type { ReportTeamValues } from "./ReportTeamDialog"

/**
 * S20 送出檢舉（multipart）。附截圖時 `uploadProgress` 為 0～100，沒有在上傳時為 null。
 *
 * 成功或失敗都重新取得檢舉對象選單（「已檢舉・處理中」要跟上）；`REPORT_NOT_ALLOWED`
 * （賽事已結束、本隊或對象的報名狀態已改變）時另外重新取得我的隊伍與賽事資料，
 * 讓 S2 的「檢舉隊伍」依最新狀態決定要不要顯示；`CAPTAIN_REQUIRED`（送出期間不再是隊長）
 * 時重新取得我的隊伍與隊伍詳情。
 */
export function useFileReport(tournamentId: string) {
  const queryClient = useQueryClient()
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const mutation = useMutation({
    mutationFn: async (values: ReportTeamValues) => {
      const attachment = values.attachment
      setUploadProgress(attachment ? 0 : null)
      try {
        return (
          await DisputesService.fileReport({
            path: { tournament_id: tournamentId },
            body: {
              reported_team_id: values.reported_team_id,
              description: values.description,
              attachment: attachment ?? undefined,
            },
            onUploadProgress: attachment
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
    onError: (error) => {
      const apiError = parseApiError(error)
      // 刻意只比對業務代碼、不看 kind：409 歸類為 business、403 歸類為 forbidden。
      // 下面只比對兩個完整的代碼，帶代碼的 401 不會誤中
      const code = "code" in apiError ? apiError.code : undefined
      if (code === "REPORT_NOT_ALLOWED") {
        queryClient.invalidateQueries({
          queryKey: myTeamsQueryOptions().queryKey,
        })
        queryClient.invalidateQueries({
          queryKey: publicTournamentQueryOptions(tournamentId).queryKey,
        })
      }
      if (code === "CAPTAIN_REQUIRED") {
        // 送出期間隊長被轉讓：重抓我的隊伍與隊伍詳情（my_role），讓入口依新身分隱藏。
        // 這裡只知道賽事 id，所以隊伍詳情以前綴一併失效
        queryClient.invalidateQueries({
          queryKey: myTeamsQueryOptions().queryKey,
        })
        queryClient.invalidateQueries({
          queryKey: [...REGISTRATION_QUERY_KEY, "team"],
        })
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: reportableTeamsQueryOptions(tournamentId).queryKey,
      })
    },
  })

  return { fileReport: mutation.mutateAsync, uploadProgress }
}
