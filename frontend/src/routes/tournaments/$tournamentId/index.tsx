import { createFileRoute } from "@tanstack/react-router"

import { TournamentPage } from "@/features/tournaments/TournamentPage"

// S2 賽事頁。不建立包住 S4（matches/$matchId）的 layout route：分頁列是元件（TournamentTabs）。
export const Route = createFileRoute("/tournaments/$tournamentId/")({
  head: () => ({ meta: [{ title: "賽事 · FLOW" }] }),
  component: TournamentRoute,
})

function TournamentRoute() {
  const { tournamentId } = Route.useParams()
  return <TournamentPage tournamentId={tournamentId} />
}
