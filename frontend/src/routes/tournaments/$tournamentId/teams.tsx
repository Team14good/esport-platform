import { createFileRoute } from "@tanstack/react-router"

import { AcceptedTeamsPage } from "@/features/registration/AcceptedTeamsPage"

// S2 的「正取隊伍」分頁（TournamentTabs），不需登入（Story 3.9）。
export const Route = createFileRoute("/tournaments/$tournamentId/teams")({
  head: () => ({ meta: [{ title: "正取隊伍 · FLOW" }] }),
  component: AcceptedTeamsRoute,
})

function AcceptedTeamsRoute() {
  const { tournamentId } = Route.useParams()
  return <AcceptedTeamsPage key={tournamentId} tournamentId={tournamentId} />
}
