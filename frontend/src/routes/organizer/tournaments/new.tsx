import { createFileRoute } from "@tanstack/react-router"

import { BackofficeLayout } from "@/components/layout/BackofficeLayout"
import { AccountGate } from "@/features/identity/AccountGate"
import { requireSignedIn } from "@/features/identity/auth"
import { CreateTournamentForm } from "@/features/tournaments/CreateTournamentForm"
import {
  ORGANIZER_BACKOFFICE_TITLE,
  ORGANIZER_NAV,
} from "@/features/tournaments/organizer-nav"

export const Route = createFileRoute("/organizer/tournaments/new")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "建立賽事 · FLOW" }] }),
  component: CreateTournamentRoute,
})

/** S26 建立賽事：只有主辦方能看，其他帳號顯示 S38 的 403。 */
function CreateTournamentRoute() {
  return (
    <AccountGate allow={(account) => account.is_organizer}>
      <BackofficeLayout
        title={ORGANIZER_BACKOFFICE_TITLE}
        items={ORGANIZER_NAV}
      >
        <CreateTournamentForm />
      </BackofficeLayout>
    </AccountGate>
  )
}
