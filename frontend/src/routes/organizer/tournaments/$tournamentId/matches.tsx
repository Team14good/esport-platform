import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"

import { OrganizerMatchesPage } from "@/features/competition/OrganizerMatchesPage"
import { parsePage } from "@/features/identity/admin-applications"

type MatchesSearch = { page?: number }

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/matches",
)({
  // 頁碼寫在網址；第 1 頁不出現在網址上
  validateSearch: (search: Record<string, unknown>): MatchesSearch => ({
    page: parsePage(search.page),
  }),
  head: () => ({ meta: [{ title: "場次管理 · FLOW" }] }),
  component: OrganizerMatchesRoute,
})

/** S30 場次管理（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function OrganizerMatchesRoute() {
  const { tournamentId } = Route.useParams()
  const { page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onPageChange = useCallback(
    (next: number, replace = false) =>
      navigate({ search: { page: next > 1 ? next : undefined }, replace }),
    [navigate],
  )
  return (
    <OrganizerMatchesPage
      tournamentId={tournamentId}
      page={page ?? 1}
      onPageChange={onPageChange}
    />
  )
}
