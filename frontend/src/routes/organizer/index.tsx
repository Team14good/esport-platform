import { createFileRoute } from "@tanstack/react-router"
import { TrophyIcon } from "lucide-react"

import { EmptyState } from "@/components/common/EmptyState"
import {
  BackofficeLayout,
  type BackofficeNavItem,
} from "@/components/layout/BackofficeLayout"
import { AccountGate } from "@/features/identity/AccountGate"
import { requireSignedIn } from "@/features/identity/auth"

const NO_TOURNAMENTS_TEXT = "你還沒有建立賽事。"

// 主辦方後台的側欄第一層；Story 2.2 接手這個檔案，加入「建立賽事」與賽事清單
const ORGANIZER_NAV: BackofficeNavItem[] = [
  { to: "/organizer", label: "我的賽事", icon: TrophyIcon },
]

export const Route = createFileRoute("/organizer/")({
  beforeLoad: requireSignedIn,
  head: () => ({ meta: [{ title: "我的賽事 · FLOW" }] }),
  component: OrganizerHome,
})

/** S25 我的賽事（佔位頁）：只有主辦方能看，其他帳號顯示 S38 的 403。 */
function OrganizerHome() {
  return (
    <AccountGate allow={(account) => account.is_organizer}>
      <BackofficeLayout title="主辦方後台" items={ORGANIZER_NAV}>
        <section className="flex min-w-0 flex-col gap-6">
          <h1 className="text-heading-lg">我的賽事</h1>
          <EmptyState title={NO_TOURNAMENTS_TEXT} />
        </section>
      </BackofficeLayout>
    </AccountGate>
  )
}
