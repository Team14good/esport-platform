import { createFileRoute } from "@tanstack/react-router"

import { RefereesPage } from "@/features/tournaments/RefereesPage"

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/referees",
)({
  head: () => ({ meta: [{ title: "裁判 · FLOW" }] }),
  component: RefereesRoute,
})

/** S31 裁判管理（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function RefereesRoute() {
  const { tournamentId } = Route.useParams()
  return <RefereesPage tournamentId={tournamentId} />
}
