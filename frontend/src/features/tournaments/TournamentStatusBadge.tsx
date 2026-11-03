import type { TournamentStatus } from "@/client"
import { StatusBadge } from "@/components/common/StatusBadge"
import { TOURNAMENT_STATUS_BADGE, TOURNAMENT_STATUS_LABEL } from "./status"

/** 賽事狀態徽章：S25、S27 使用，S1、S2（2.4 第二階段）可沿用。 */
export function TournamentStatusBadge({
  status,
  className,
}: {
  status: TournamentStatus
  className?: string
}) {
  const badge = TOURNAMENT_STATUS_BADGE[status]
  return (
    <StatusBadge tone={badge.tone} pulse={badge.pulse} className={className}>
      {TOURNAMENT_STATUS_LABEL[status]}
    </StatusBadge>
  )
}
