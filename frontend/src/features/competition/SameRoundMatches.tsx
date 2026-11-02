import { Link } from "@tanstack/react-router"

import { StatusBadge } from "@/components/common/StatusBadge"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { PublicMatch } from "./bracket-types"
import { MATCH_STATUS_BADGES, matchLabel } from "./match-status"

type SameRoundMatchesProps = {
  tournamentId: string
  /** 同一輪的其他場次（不含自己）；季軍賽與決賽互相列出 */
  matches: PublicMatch[]
  className?: string
}

/** Same-round list：S4 右欄最下方「同輪其他場次」，每場一個連到該場 S4 的小列。同輪沒有其他場次時不顯示。 */
export function SameRoundMatches({
  tournamentId,
  matches,
  className,
}: SameRoundMatchesProps) {
  if (matches.length === 0) return null
  return (
    <Card
      data-slot="same-round-matches"
      className={cn("gap-2.5 p-4", className)}
    >
      <h2 className="font-semibold text-label text-muted-foreground">
        同輪其他場次
      </h2>
      <ul className="flex flex-wrap gap-x-3.5 gap-y-2">
        {matches.map((match) => {
          const badge = MATCH_STATUS_BADGES[match.status]
          return (
            <li key={match.id}>
              <Link
                to="/tournaments/$tournamentId/matches/$matchId"
                params={{ tournamentId, matchId: match.id }}
                data-slot="same-round-link"
                className="inline-flex items-center gap-1.5 rounded-sm text-caption text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <span className="font-mono">{matchLabel(match)}</span>
                <StatusBadge
                  tone={badge.tone}
                  pulse={badge.pulse}
                  className="gap-[5px] px-[7px] py-0 text-overline leading-3.5"
                >
                  {badge.label}
                </StatusBadge>
              </Link>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
