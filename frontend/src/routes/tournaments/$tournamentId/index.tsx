import { createFileRoute } from "@tanstack/react-router"

import { FinishedTournamentPodium } from "@/features/competition/TournamentPodium"
import { TournamentPage } from "@/features/tournaments/TournamentPage"

type TournamentSearch = { invite?: string }

// S2 賽事頁。不建立包住 S4（matches/$matchId）的 layout route：分頁列是元件（TournamentTabs）。
export const Route = createFileRoute("/tournaments/$tournamentId/")({
  // `invite`：自訂賽事的賽事報名連結 token（Story 3.10）；由 CreateTeamEntry 讀取，
  // 校園賽忽略。一律回傳 invite 鍵，空字串與非字串視為沒有帶
  validateSearch: (search: Record<string, unknown>): TournamentSearch => ({
    invite:
      typeof search.invite === "string" && search.invite.length > 0
        ? search.invite
        : undefined,
  }),
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
