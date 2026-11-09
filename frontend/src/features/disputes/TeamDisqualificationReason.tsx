import { queryOptions, useQuery } from "@tanstack/react-query"

import { DisputesService } from "@/client"
import { formatDateTime } from "@/lib/datetime"
import { cn } from "@/lib/utils"
import { DISPUTES_QUERY_KEY } from "./queries"

export const DISQUALIFICATION_REASON_TITLE = "主辦方的處理理由"

/**
 * 隊伍被取消資格的處理理由（只有該隊隊員能讀）。非隊員（403）重試也不會成功，所以不重試
 * （全站預設會對 403 重試 3 次）。
 */
export const teamDisqualificationQueryOptions = (teamId: string) =>
  queryOptions({
    queryKey: [...DISPUTES_QUERY_KEY, "team-disqualification", teamId],
    queryFn: async () =>
      (
        await DisputesService.readTeamDisqualification({
          path: { team_id: teamId },
        })
      ).data,
    retry: false,
  })

/**
 * S12、S17（6.5）：取消資格時顯示主辦方的處理理由與處理時間。
 * 呼叫端只在報名狀態為取消資格時掛載；沒有理由（null）、讀取中或失敗時不顯示。
 */
export function TeamDisqualificationReason({
  teamId,
  className,
}: {
  teamId: string
  className?: string
}) {
  const query = useQuery(teamDisqualificationQueryOptions(teamId))
  const data = query.data
  if (!data) return null
  return (
    <div
      data-slot="disqualification-reason"
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3",
        className,
      )}
    >
      <p className="text-destructive text-label">
        {DISQUALIFICATION_REASON_TITLE}
      </p>
      <p className="whitespace-pre-wrap break-words text-body">{data.reason}</p>
      <p className="text-caption text-muted-foreground">
        處理時間：{formatDateTime(data.handled_at)}
      </p>
    </div>
  )
}
