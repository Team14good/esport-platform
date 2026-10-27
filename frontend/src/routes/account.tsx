import { createFileRoute } from "@tanstack/react-router"

import { AccountProfilePage } from "@/features/identity/AccountProfilePage"
import { requireSignedIn } from "@/features/identity/auth"

export const Route = createFileRoute("/account")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "帳號資料 · FLOW" }] }),
  component: AccountProfilePage,
})
