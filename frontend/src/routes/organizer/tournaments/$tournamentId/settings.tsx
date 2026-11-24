import { createFileRoute } from "@tanstack/react-router"

import { TournamentSettingsPage } from "@/features/tournaments/TournamentSettingsPage"

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/settings",
)({
  head: () => ({ meta: [{ title: "賽事設定 · FLOW" }] }),
  component: SettingsRoute,
})

/** S28 賽事設定（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function SettingsRoute() {
  const { tournamentId } = Route.useParams()
  return <TournamentSettingsPage tournamentId={tournamentId} />
}
