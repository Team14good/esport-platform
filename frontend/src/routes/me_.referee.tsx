import { createFileRoute } from "@tanstack/react-router"

import { RefereeMatchesPage } from "@/features/competition/RefereeMatchesPage"
import { requireSignedIn } from "@/features/identity/auth"

// 檔名 me_.referee：與 me_.teams 相同，不巢狀在 /me（S11）底下
export const Route = createFileRoute("/me_/referee")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "我執法的場次 · FLOW" }] }),
  component: RefereeMatchesPage,
})
