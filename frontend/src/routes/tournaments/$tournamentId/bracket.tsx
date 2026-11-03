import { createFileRoute } from "@tanstack/react-router"

import { TournamentBracketPage } from "@/features/competition/TournamentBracketPage"

// S3 對戰表：S2 的「對戰表」分頁（TournamentTabs），不需登入。
export const Route = createFileRoute("/tournaments/$tournamentId/bracket")({
  head: () => ({ meta: [{ title: "對戰表 · FLOW" }] }),
  component: BracketRoute,
})

function BracketRoute() {
  const { tournamentId } = Route.useParams()
  // 換賽事時重新掛載：輪詢的 keepPreviousData 不會把上一場的對戰樹顯示在這一場底下
  return (
    <TournamentBracketPage key={tournamentId} tournamentId={tournamentId} />
  )
}
