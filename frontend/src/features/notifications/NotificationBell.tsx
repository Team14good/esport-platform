import { Link } from "@tanstack/react-router"
import { BellIcon } from "lucide-react"
import { useState } from "react"

import type { NotificationRead } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Skeleton } from "@/components/ui/skeleton"
import { NotificationList } from "./NotificationList"
import {
  badgeText,
  NO_NOTIFICATIONS_TEXT,
  POPOVER_LIMIT,
  useNotifications,
  useOpenNotification,
  useUnreadCount,
} from "./queries"

/**
 * 頂欄鈴鐺（只在登入時出現）：每 30 秒輪詢未讀數，有未讀時右上角顯示數字徽章（超過 99
 * 顯示「99+」）。點擊開啟 Popover，列出最新 8 則，底部「查看全部」→ S14。
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const count = useUnreadCount()
  const badge = badgeText(count)
  const label = badge ? `通知（${badge} 則未讀）` : "通知"

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative size-touch-target"
          aria-label={label}
          title="通知"
        >
          <BellIcon aria-hidden="true" />
          {badge && (
            <span
              aria-hidden="true"
              data-slot="unread-badge"
              className="absolute top-1 right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 font-semibold text-[10px] text-destructive-foreground leading-none"
            >
              {badge}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[min(22rem,calc(100vw-2rem))] p-0"
        aria-label="通知"
      >
        {open && <PopoverBody onClose={() => setOpen(false)} />}
      </PopoverContent>
    </Popover>
  )
}

/** Popover 內容：打開時才抓取列表第 1 頁，只顯示前 8 則。 */
function PopoverBody({ onClose }: { onClose: () => void }) {
  const notifications = useNotifications(1)
  const openNotification = useOpenNotification()
  const items = notifications.data?.items.slice(0, POPOVER_LIMIT)

  const onOpen = (notification: NotificationRead) => {
    onClose()
    void openNotification(notification)
  }

  return (
    <div className="flex flex-col">
      <p className="border-b px-4 py-3 text-heading-md">通知</p>
      <div className="max-h-[min(28rem,70vh)] overflow-y-auto p-1">
        {items === undefined ? (
          notifications.isError ? (
            <p className="px-3 py-6 text-center text-body text-muted-foreground">
              無法載入通知，請稍後再試。
            </p>
          ) : (
            <div
              role="status"
              aria-busy="true"
              className="flex flex-col gap-2 p-2"
            >
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <span className="sr-only">載入中</span>
            </div>
          )
        ) : items.length === 0 ? (
          <p className="px-3 py-6 text-center text-body text-muted-foreground">
            {NO_NOTIFICATIONS_TEXT}
          </p>
        ) : (
          <NotificationList notifications={items} onOpen={onOpen} />
        )}
      </div>
      <div className="border-t p-1">
        <Button asChild variant="ghost" className="w-full">
          <Link to="/notifications" onClick={onClose}>
            查看全部
          </Link>
        </Button>
      </div>
    </div>
  )
}
