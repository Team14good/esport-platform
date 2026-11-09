import { createFileRoute } from "@tanstack/react-router"

import { AppealsPage } from "@/features/disputes/AppealsPage"

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/appeals",
)({
  head: () => ({ meta: [{ title: "申訴 · FLOW" }] }),
  component: AppealsRoute,
})

/** S32 申訴（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function AppealsRoute() {
  const { tournamentId } = Route.useParams()
  return <AppealsPage tournamentId={tournamentId} />
}
