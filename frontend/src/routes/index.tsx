import { createFileRoute } from "@tanstack/react-router"

import { TournamentList } from "@/features/tournaments/TournamentList"

// S1 賽事列表（不需登入）
export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "賽事 · FLOW" }] }),
  component: TournamentList,
})
