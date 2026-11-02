import {
  createFileRoute,
  Outlet,
  type ParsedLocation,
  redirect,
} from "@tanstack/react-router"
import { ClipboardCheckIcon } from "lucide-react"

import {
  BackofficeLayout,
  type BackofficeNavItem,
} from "@/components/layout/BackofficeLayout"
import { AccountGate } from "@/features/identity/AccountGate"
import { requireSignedIn } from "@/features/identity/auth"

// 平台管理後台的側欄項目；S36（遊戲設定、學校清單）在 Story 2.1 加入
const ADMIN_NAV: BackofficeNavItem[] = [
  { to: "/admin/applications", label: "主辦方申請", icon: ClipboardCheckIcon },
]

export const Route = createFileRoute("/admin")({
  beforeLoad: ({ location }: { location: ParsedLocation }) => {
    requireSignedIn({ location })
    // 後台沒有自己的首頁：/admin 直接到第一個項目
    if (location.pathname.replace(/\/$/, "") === "/admin") {
      throw redirect({ to: "/admin/applications" })
    }
  },
  component: AdminBackoffice,
})

/** 平台管理後台的版面：只有平台管理員能看，其他帳號顯示 S38 的 403。 */
function AdminBackoffice() {
  return (
    <AccountGate allow={(account) => account.is_platform_admin}>
      <BackofficeLayout title="平台管理" items={ADMIN_NAV}>
        <Outlet />
      </BackofficeLayout>
    </AccountGate>
  )
}
