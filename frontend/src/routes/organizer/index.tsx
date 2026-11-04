import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"

import { BackofficeLayout } from "@/components/layout/BackofficeLayout"
import { AccountGate } from "@/features/identity/AccountGate"
import { parsePage } from "@/features/identity/admin-applications"
import { requireSignedIn } from "@/features/identity/auth"
import { OrganizerTournamentsPage } from "@/features/tournaments/OrganizerTournamentsPage"
import {
  ORGANIZER_BACKOFFICE_TITLE,
  ORGANIZER_NAV,
} from "@/features/tournaments/organizer-nav"

type OrganizerSearch = { page?: number }

export const Route = createFileRoute("/organizer/")({
  // 頁碼寫在網址；第 1 頁不出現在網址上
  validateSearch: (search: Record<string, unknown>): OrganizerSearch => ({
    page: parsePage(search.page),
  }),
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "我的賽事 · FLOW" }] }),
  component: OrganizerHome,
})

/** S25 我的賽事：只有主辦方能看，其他帳號顯示 S38 的 403。 */
function OrganizerHome() {
  const { page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onPageChange = useCallback(
    (next: number, replace = false) =>
      navigate({ search: { page: next > 1 ? next : undefined }, replace }),
    [navigate],
  )
  return (
    <AccountGate allow={(account) => account.is_organizer}>
      <BackofficeLayout
        title={ORGANIZER_BACKOFFICE_TITLE}
        items={ORGANIZER_NAV}
      >
        <OrganizerTournamentsPage
          page={page ?? 1}
          onPageChange={onPageChange}
        />
      </BackofficeLayout>
    </AccountGate>
  )
}
