import { createFileRoute } from "@tanstack/react-router"

import { requireSignedIn } from "@/features/identity/auth"
import { OrganizerApplyPage } from "@/features/identity/OrganizerApplyPage"

export const Route = createFileRoute("/organizer/apply")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "申請成為主辦方 · FLOW" }] }),
  component: OrganizerApplyPage,
})
