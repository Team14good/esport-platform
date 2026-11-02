import { createFileRoute, Outlet } from "@tanstack/react-router"

import { AccountGate } from "@/features/identity/AccountGate"
import { requireSignedIn } from "@/features/identity/auth"
import { OrganizerTournamentLayout } from "@/features/tournaments/OrganizerTournamentOverview"

// 主辦方賽事後台：側欄（查看賽事頁、總覽…）與賽事資料在這裡載入，
// 之後的 Story 把頁面（例如 referees）加在這個路由底下
export const Route = createFileRoute("/organizer/tournaments/$tournamentId")({
  beforeLoad: requireSignedIn,
  component: OrganizerTournamentBackoffice,
})

/** 只有主辦方能看，其他帳號顯示 S38 的 403；別人的賽事由 API 回 403。 */
function OrganizerTournamentBackoffice() {
  const { tournamentId } = Route.useParams()
  return (
    <AccountGate allow={(account) => account.is_organizer}>
      <OrganizerTournamentLayout tournamentId={tournamentId}>
        <Outlet />
      </OrganizerTournamentLayout>
    </AccountGate>
  )
}
