// S17 退賽按鈕（Story 4.5）：這支隊伍現在能不能退賽。
import { queryOptions } from "@tanstack/react-query"

import { CompetitionService } from "@/client"

export const retirementQueryKey = (teamId: string) =>
  ["competition", "retirement", teamId] as const

/** 後端判斷的可退賽狀態：`retirable`，或停用按鈕並顯示 `reason`（沒有 `reason` 就不顯示按鈕）。 */
export const retirementQueryOptions = (teamId: string) =>
  queryOptions({
    queryKey: retirementQueryKey(teamId),
    queryFn: async () =>
      (
        await CompetitionService.readRetirementStatus({
          path: { team_id: teamId },
        })
      ).data,
  })
