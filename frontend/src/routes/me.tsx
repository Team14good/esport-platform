import { createFileRoute } from "@tanstack/react-router"
import { requireSignedIn } from "@/features/identity/auth"
import { IdentityPicker } from "@/features/identity/IdentityPicker"

export const Route = createFileRoute("/me")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "選擇身分 · FLOW" }] }),
  component: IdentityPicker,
})
