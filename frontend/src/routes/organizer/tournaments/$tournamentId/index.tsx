import { createFileRoute } from "@tanstack/react-router"

import { OrganizerTournamentOverview } from "@/features/tournaments/OrganizerTournamentOverview"

export const Route = createFileRoute("/organizer/tournaments/$tournamentId/")({
  head: () => ({ meta: [{ title: "賽事總覽 · FLOW" }] }),
  component: OrganizerTournamentOverviewRoute,
})

/** S27 賽事總覽（主辦方賽事後台的「總覽」）。 */
function OrganizerTournamentOverviewRoute() {
  const { tournamentId } = Route.useParams()
  return <OrganizerTournamentOverview tournamentId={tournamentId} />
}
