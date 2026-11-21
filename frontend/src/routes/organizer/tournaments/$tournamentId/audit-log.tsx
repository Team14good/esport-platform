import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"

import { parsePage } from "@/features/identity/admin-applications"
import { AuditLogPage } from "@/features/tournaments/AuditLogPage"

type AuditLogSearch = { page?: number }

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/audit-log",
)({
  // 頁碼寫在網址；第 1 頁不出現在網址上
  validateSearch: (search: Record<string, unknown>): AuditLogSearch => ({
    page: parsePage(search.page),
  }),
  head: () => ({ meta: [{ title: "操作紀錄 · FLOW" }] }),
  component: AuditLogRoute,
})

/** S34 操作紀錄（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function AuditLogRoute() {
  const { tournamentId } = Route.useParams()
  const { page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onPageChange = useCallback(
    (next: number, replace = false) =>
      navigate({ search: { page: next > 1 ? next : undefined }, replace }),
    [navigate],
  )
  return (
    <AuditLogPage
      tournamentId={tournamentId}
      page={page ?? 1}
      onPageChange={onPageChange}
    />
  )
}
