import { createFileRoute } from "@tanstack/react-router"

import { AdminGamesPage } from "@/features/tournaments/AdminGamesPage"

export const Route = createFileRoute("/admin/games/")({
  head: () => ({ meta: [{ title: "遊戲設定 · FLOW" }] }),
  component: AdminGamesPage,
})
