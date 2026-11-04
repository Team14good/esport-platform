import { createFileRoute } from "@tanstack/react-router"

import { NewGamePage } from "@/features/tournaments/AdminGamesPage"

export const Route = createFileRoute("/admin/games/new")({
  head: () => ({ meta: [{ title: "新增遊戲 · FLOW" }] }),
  component: NewGamePage,
})
