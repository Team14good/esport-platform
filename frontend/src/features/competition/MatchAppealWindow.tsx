import { type ReactNode, useId } from "react"
import type { MatchStatus, PublicMatchDetail } from "@/client"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { formatMatchDateTime } from "./match-time"

/** 顯示申訴期區塊的狀態：申訴中也顯示，因為另一隊在期限內仍可申訴（FR-30） */
const APPEAL_WINDOW_STATUSES: ReadonlySet<MatchStatus> = new Set([
  "appeal_window",
  "appealed",
])

type MatchAppealWindowProps = {
  detail: Pick<PublicMatchDetail, "status" | "appeal_deadline">
  /** 倒數插槽：S4 路由放入 Countdown（`appeal` 變體）；有傳入時由 Countdown 顯示截止時間 */
  countdown?: ReactNode
  /** 動作插槽（6.1）：S4 路由放入申訴入口（`AppealPanel`），顯示在倒數下方 */
  action?: ReactNode
  className?: string
}

/**
 * S4「申訴期」區塊：標題，加上倒數插槽或「{絕對時間} 截止」（有倒數時只顯示倒數）。
 * 只在申訴期／申訴中且有截止時間時顯示。不讀裝置時鐘判斷是否到期，到期後的呈現屬於 Countdown。
 * 申訴中另寫「申訴處理中」；倒數照常顯示（另一隊在期限內仍可申訴）。
 */
export function MatchAppealWindow({
  detail,
  countdown,
  action,
  className,
}: MatchAppealWindowProps) {
  const titleId = useId()
  const deadline = detail.appeal_deadline
  if (!APPEAL_WINDOW_STATUSES.has(detail.status) || !deadline) return null
  const hasCountdown =
    countdown !== undefined && countdown !== null && countdown !== false
  const hasAction = action !== undefined && action !== null && action !== false
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
      {detail.status === "appealed" && (
        <p data-slot="appeal-in-progress" className="text-sm font-medium">
          申訴處理中
        </p>
      )}
      {hasCountdown ? (
        // Countdown 下方自己就有「{絕對時間} 截止」，這裡不再重複
        <div data-slot="appeal-countdown">{countdown}</div>
      ) : (
        <p
          data-slot="appeal-deadline"
          className="text-caption text-muted-foreground"
        >
          {formatMatchDateTime(deadline)} 截止
        </p>
      )}
      {hasAction && (
        // 申訴入口不顯示時（不是隊長）不佔間距
        <div data-slot="appeal-action" className="empty:hidden">
          {action}
        </div>
      )}
    </Card>
  )
}
