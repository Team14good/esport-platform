import { createFileRoute } from "@tanstack/react-router"

import type { TeamDetail } from "@/client"
import { TeamDisqualificationReason } from "@/features/disputes/TeamDisqualificationReason"
import { requireSignedIn } from "@/features/identity/auth"
import { TeamPage } from "@/features/registration/TeamPage"

export const Route = createFileRoute("/teams/$teamId")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "隊伍 · FLOW" }] }),
  component: TeamRoute,
})

// 取消資格時在報名狀態下方顯示主辦方的處理理由（disputes，6.5）
function renderDisqualificationReason(team: TeamDetail) {
  return team.registration_status === "disqualified" ? (
    <TeamDisqualificationReason teamId={team.id} />
  ) : null
}

function TeamRoute() {
  const { teamId } = Route.useParams()
  return (
    <TeamPage
      key={teamId}
      teamId={teamId}
      renderStatusExtra={renderDisqualificationReason}
    />
  )
}
