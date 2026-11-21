import { createFileRoute } from "@tanstack/react-router"
import { useCallback } from "react"

import { requireSignedIn } from "@/features/identity/auth"
import { NotificationsPage } from "@/features/notifications/NotificationsPage"
import {
  type NotificationsSearch,
  parsePage,
} from "@/features/notifications/queries"

export const Route = createFileRoute("/notifications")({
  beforeLoad: requireSignedIn,
  // 頁碼寫在網址；第 1 頁不出現在網址上
  validateSearch: (search: Record<string, unknown>): NotificationsSearch => ({
    page: parsePage(search.page),
  }),
  head: () => ({ meta: [{ title: "通知 · FLOW" }] }),
  component: NotificationsRoute,
})

function NotificationsRoute() {
  const { page } = Route.useSearch()
  const navigate = Route.useNavigate()
  const onPageChange = useCallback(
    (next: number, options?: { replace?: boolean }) =>
      navigate({
        search: { page: parsePage(next) },
        replace: options?.replace,
      }),
    [navigate],
  )
  return <NotificationsPage page={page ?? 1} onPageChange={onPageChange} />
}
