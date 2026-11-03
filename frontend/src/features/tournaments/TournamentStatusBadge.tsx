import type { TournamentStatus } from "@/client"
import { StatusBadge } from "@/components/common/StatusBadge"
import { TOURNAMENT_STATUS_BADGES, TOURNAMENT_STATUS_LABEL } from "./status"

/** 賽事狀態徽章（S1 賽事卡、S2 標題列與總覽、S25 我的賽事、S27 賽事總覽共用）。 */
export function TournamentStatusBadge({
  status,
}: {
  status: TournamentStatus
}) {
  const { tone, pulse } = TOURNAMENT_STATUS_BADGES[status]
  return (
    <StatusBadge tone={tone} pulse={pulse}>
      {TOURNAMENT_STATUS_LABEL[status]}
    </StatusBadge>
  )
}
