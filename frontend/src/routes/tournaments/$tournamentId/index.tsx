import { createFileRoute } from "@tanstack/react-router"

import { FinishedTournamentPodium } from "@/features/competition/TournamentPodium"
import { TournamentPage } from "@/features/tournaments/TournamentPage"

// S2 賽事頁。不建立包住 S4（matches/$matchId）的 layout route：分頁列是元件（TournamentTabs）。
export const Route = createFileRoute("/tournaments/$tournamentId/")({
  head: () => ({ meta: [{ title: "賽事 · FLOW" }] }),
  component: TournamentRoute,
})

function TournamentRoute() {
  const { tournamentId } = Route.useParams()
  // Podium 放在 B 的 TournamentPage 上方（賽事已結束才有內容），不改動 TournamentPage
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <FinishedTournamentPodium tournamentId={tournamentId} />
      <TournamentPage tournamentId={tournamentId} />
    </div>
  )
}
