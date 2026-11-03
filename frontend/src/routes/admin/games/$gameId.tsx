import { createFileRoute } from "@tanstack/react-router"

import { EditGamePage } from "@/features/tournaments/AdminGamesPage"

export const Route = createFileRoute("/admin/games/$gameId")({
  head: () => ({ meta: [{ title: "編輯遊戲 · FLOW" }] }),
  component: EditGameRoute,
})

function EditGameRoute() {
  const { gameId } = Route.useParams()
  return <EditGamePage gameId={gameId} />
}
