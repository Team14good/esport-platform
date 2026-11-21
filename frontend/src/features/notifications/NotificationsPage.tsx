import { useEffect } from "react"

import { DataTablePagination } from "@/components/common/DataTable"
import { EmptyState } from "@/components/common/EmptyState"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { NotificationList } from "./NotificationList"
import {
  NO_NOTIFICATIONS_TEXT,
  useNotifications,
  useOpenNotification,
} from "./queries"

type NotificationsPageProps = {
  /** 目前頁碼（從 1 開始，寫在網址上） */
  page: number
  /** `replace` 為 true 時取代目前的歷史紀錄（頁碼超出範圍時導回最後一頁用） */
  onPageChange: (page: number, options?: { replace?: boolean }) => void
}

/** S14 通知中心：依建立時間由新到舊、每頁 20 則；點擊一則標為已讀並導向它的 `link`。 */
export function NotificationsPage({
  page,
  onPageChange,
}: NotificationsPageProps) {
  const notifications = useNotifications(page)
  const openNotification = useOpenNotification()
  const data = notifications.data
  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / data.page_size))
    : 1
  // 手動輸入超出範圍的頁碼（例如 25 則時開第 9 頁）：導回最後一頁，不顯示空卡片
  const outOfRange = data !== undefined && data.total > 0 && page > totalPages
  useEffect(() => {
    if (outOfRange) onPageChange(totalPages, { replace: true })
  }, [outOfRange, totalPages, onPageChange])

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 py-8 sm:py-12">
      <h1 className="text-heading-lg">通知</h1>
      {notifications.isPending ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <span className="sr-only">載入中</span>
        </div>
      ) : notifications.isError && !data ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(notifications.error))}
          </p>
          <Button variant="outline" onClick={() => notifications.refetch()}>
            重新載入
          </Button>
        </div>
      ) : data && data.total === 0 ? (
        <EmptyState title={NO_NOTIFICATIONS_TEXT} />
      ) : data && !outOfRange ? (
        <>
          <Card className="gap-0 p-1">
            <NotificationList
              notifications={data.items}
              onOpen={(notification) => void openNotification(notification)}
            />
          </Card>
          {totalPages > 1 && (
            <DataTablePagination
              page={page}
              totalPages={totalPages}
              onPageChange={onPageChange}
            />
          )}
        </>
      ) : null}
    </section>
  )
}
