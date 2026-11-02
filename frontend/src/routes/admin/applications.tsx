import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"
import { AdminApplicationsPage } from "@/features/identity/AdminApplicationsPage"
import {
  type ApplicationsSearch,
  DEFAULT_FILTER,
  parseFilter,
  parsePage,
} from "@/features/identity/admin-applications"

export const Route = createFileRoute("/admin/applications")({
  // 篩選與頁碼寫在網址；預設值（待審核、第 1 頁）不出現在網址上
  validateSearch: (search: Record<string, unknown>): ApplicationsSearch => ({
    status: parseFilter(search.status),
    page: parsePage(search.page),
  }),
  head: () => ({ meta: [{ title: "主辦方申請 · FLOW" }] }),
  component: AdminApplicationsRoute,
})

function AdminApplicationsRoute() {
  const { status, page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onSearchChange = useCallback(
    (search: ApplicationsSearch, replace = false) =>
      navigate({ search, replace }),
    [navigate],
  )
  return (
    <AdminApplicationsPage
      filter={status ?? DEFAULT_FILTER}
      page={page ?? 1}
      onSearchChange={onSearchChange}
    />
  )
}
