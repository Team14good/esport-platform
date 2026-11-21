import type { NotificationRead } from "@/client"
import { formatRelativeTime, formatShortDateTime } from "@/lib/datetime"
import { cn } from "@/lib/utils"

type NotificationListProps = {
  notifications: NotificationRead[]
  onOpen: (notification: NotificationRead) => void
  /** 計算相對時間的基準（預設為現在；測試用） */
  now?: Date
  className?: string
}

/**
 * 通知列表（Popover 與 S14 共用）：每則一個按鈕，顯示 `title`、相對時間與一行絕對時間；
 * 未讀的左側有 8px 圓點。
 */
export function NotificationList({
  notifications,
  onOpen,
  now = new Date(),
  className,
}: NotificationListProps) {
  return (
    <ul className={cn("flex flex-col", className)}>
      {notifications.map((notification) => {
        const unread = notification.read_at === null
        return (
          <li key={notification.id}>
            <button
              type="button"
              onClick={() => onOpen(notification)}
              aria-label={unread ? `未讀：${notification.title}` : undefined}
              className="flex w-full min-w-0 items-start gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
            >
              <span
                aria-hidden="true"
                data-slot="unread-dot"
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  unread ? "bg-primary" : "bg-transparent",
                )}
              />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span
                  className={cn(
                    "break-words text-body",
                    unread ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {notification.title}
                </span>
                <span className="text-caption text-muted-foreground">
                  {formatRelativeTime(notification.created_at, now)}
                </span>
                <span className="text-caption text-muted-foreground">
                  {formatShortDateTime(notification.created_at)}
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
