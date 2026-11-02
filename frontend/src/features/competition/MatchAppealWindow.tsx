import { type ReactNode, useId } from "react"

import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { MatchStatus } from "./bracket-types"
import { formatMatchDateTime } from "./match-time"
import type { PublicMatchDetail } from "./match-types"

/** 顯示申訴期區塊的狀態：申訴中也顯示，因為另一隊在期限內仍可申訴（FR-30） */
const APPEAL_WINDOW_STATUSES: ReadonlySet<MatchStatus> = new Set([
  "appeal_window",
  "appealed",
])

type MatchAppealWindowProps = {
  detail: Pick<PublicMatchDetail, "status" | "appeal_deadline">
  /** 倒數插槽：B 的 Countdown（`appeal` 變體）做好後由呼叫端放入；沒有傳入時不顯示、不留空白 */
  countdown?: ReactNode
  className?: string
}

/**
 * S4「申訴期」區塊：標題、倒數插槽、「{絕對時間} 截止」。
 * 只在申訴期／申訴中且有截止時間時顯示。不讀裝置時鐘判斷是否到期，到期後的呈現屬於 Countdown。
 */
export function MatchAppealWindow({
  detail,
  countdown,
  className,
}: MatchAppealWindowProps) {
  const titleId = useId()
  const deadline = detail.appeal_deadline
  if (!APPEAL_WINDOW_STATUSES.has(detail.status) || !deadline) return null
  const hasCountdown =
    countdown !== undefined && countdown !== null && countdown !== false
  return (
    <Card
      role="region"
      aria-labelledby={titleId}
      data-slot="match-appeal-window"
      className={cn("gap-2.5 p-4", className)}
    >
      <h2 id={titleId} className="text-label text-status-appeal">
        申訴期
      </h2>
      {hasCountdown && <div data-slot="appeal-countdown">{countdown}</div>}
      <p
        data-slot="appeal-deadline"
        className="text-caption text-muted-foreground"
      >
        {formatMatchDateTime(deadline)} 截止
      </p>
    </Card>
  )
}
