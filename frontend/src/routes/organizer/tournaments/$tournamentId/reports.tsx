import { createFileRoute } from "@tanstack/react-router"

import { ReportsPage } from "@/features/disputes/ReportsPage"

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/reports",
)({
  head: () => ({ meta: [{ title: "檢舉 · FLOW" }] }),
  component: ReportsRoute,
})

/** S33 檢舉（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function ReportsRoute() {
  const { tournamentId } = Route.useParams()
  return <ReportsPage tournamentId={tournamentId} />
}
