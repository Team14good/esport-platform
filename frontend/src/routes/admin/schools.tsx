import { createFileRoute } from "@tanstack/react-router"

import { AdminSchoolsPage } from "@/features/identity/AdminSchoolsPage"

export const Route = createFileRoute("/admin/schools")({
  head: () => ({ meta: [{ title: "學校清單 · FLOW" }] }),
  component: AdminSchoolsPage,
})
