import { StatusBadge } from "@/components/common/StatusBadge"
import { cn } from "@/lib/utils"
import { MATCH_STATUS_BADGES, THIRD_PLACE_LABEL } from "./match-status"
import { formatMatchDateTime } from "./match-time"
import type { PublicMatchDetail } from "./match-types"

/** S4 標題：「32 強 · M3」「決賽 · M31」；季軍賽只寫「季軍賽」。頁面 head 也用同一句。 */
export function matchTitle(
  detail: Pick<PublicMatchDetail, "is_third_place" | "round_name" | "code">,
): string {
  return detail.is_third_place
    ? THIRD_PLACE_LABEL
    : `${detail.round_name} · ${detail.code}`
}

/** S3 對戰表的網址；S3 路由在 4.6 第二階段才建立，之前這個連結會到 404。 */
export function bracketPath(tournamentId: string): string {
  return `/tournaments/${encodeURIComponent(tournamentId)}/bracket`
}

type MatchHeaderProps = {
  detail: PublicMatchDetail
  className?: string
}

/** Match header：返回連結、標題＋狀態徽章、遊戲 · BO · 預定時間（DESIGN.md〈場次頁（S4）〉），不放在 Card 內。 */
export function MatchHeader({ detail, className }: MatchHeaderProps) {
  const badge = MATCH_STATUS_BADGES[detail.status]
  const time = formatMatchDateTime(detail.scheduled_at)
  return (
    <header
      data-slot="match-header"
      className={cn("flex min-w-0 flex-col gap-1", className)}
    >
      {/* S3 路由還不存在，TanStack 的 Link 只接受已註冊的路由，先用一般連結；第二階段改用 Link */}
      <a
        href={bracketPath(detail.tournament.id)}
        data-slot="match-back-link"
        className="w-fit max-w-full truncate rounded-sm text-body text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        ← {detail.tournament.name}
      </a>
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="min-w-0 wrap-anywhere text-heading-lg">
          {matchTitle(detail)}
        </h1>
        <StatusBadge tone={badge.tone} pulse={badge.pulse}>
          {badge.label}
        </StatusBadge>
      </div>
      <p
        data-slot="match-subtitle"
        className="text-caption text-muted-foreground"
      >
        {[detail.game_name, `BO${detail.best_of}`, time]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </header>
  )
}
