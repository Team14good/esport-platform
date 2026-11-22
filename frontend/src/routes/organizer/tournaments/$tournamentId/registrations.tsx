import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"

import { parsePage } from "@/features/identity/admin-applications"
import { OrganizerRegistrationsPage } from "@/features/registration/OrganizerRegistrationsPage"
import {
  DEFAULT_REGISTRATION_FILTER,
  type OrganizerRegistrationsSearch,
  parseRegistrationFilter,
} from "@/features/registration/organizer-registrations"

export const Route = createFileRoute(
  "/organizer/tournaments/$tournamentId/registrations",
)({
  // 篩選與頁碼寫在網址；預設值（全部、第 1 頁）不出現在網址上
  validateSearch: (
    search: Record<string, unknown>,
  ): OrganizerRegistrationsSearch => ({
    status: parseRegistrationFilter(search.status),
    page: parsePage(search.page),
  }),
  head: () => ({ meta: [{ title: "報名清單 · FLOW" }] }),
  component: OrganizerRegistrationsRoute,
})

/** S29 報名清單（主辦方賽事後台）。權限與版面由上層 route 處理。 */
function OrganizerRegistrationsRoute() {
  const { tournamentId } = Route.useParams()
  const { status, page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onSearchChange = useCallback(
    (search: OrganizerRegistrationsSearch, replace = false) =>
      navigate({ search, replace }),
    [navigate],
  )
  return (
    <OrganizerRegistrationsPage
      tournamentId={tournamentId}
      filter={status ?? DEFAULT_REGISTRATION_FILTER}
      page={page ?? 1}
      onSearchChange={onSearchChange}
    />
  )
}
