import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { useRouter } from "@tanstack/react-router"
import { useCallback, useEffect, useRef } from "react"

import { type NotificationRead, NotificationsService } from "@/client"
import { ME_QUERY_KEY, useIsSignedIn } from "@/features/identity/auth"

/** 通知相關 query 的共同前綴（未讀數與列表）。 */
export const NOTIFICATIONS_QUERY_KEY = ["notifications"] as const

/** 未讀數輪詢間隔（AD-14：全站唯一的未讀數輪詢）。 */
export const UNREAD_POLL_INTERVAL_MS = 30_000
/** Popover 顯示的則數（取列表第 1 頁的前幾則）。 */
export const POPOVER_LIMIT = 8
/** 徽章最多顯示到 99，超過顯示「99+」。 */
export const BADGE_MAX = 99

export const NO_NOTIFICATIONS_TEXT = "還沒有通知。"

// 與後端 `MAX_PAGE` 相同；超過時後端回 422
export const MAX_PAGE = 100_000

/** S14 網址上的查詢參數；省略代表第 1 頁。 */
export type NotificationsSearch = { page?: number }

/** 解析網址的 `page`：不是 2～`MAX_PAGE` 的整數時當成第 1 頁，網址上不留預設值。 */
export function parsePage(value: unknown): number | undefined {
  const page = typeof value === "string" ? Number(value) : value
  return typeof page === "number" &&
    Number.isInteger(page) &&
    page > 1 &&
    page <= MAX_PAGE
    ? page
    : undefined
}

/** 徽章文字：0 或沒有資料時不顯示（回傳 null），超過 99 顯示「99+」。 */
export function badgeText(count: number | undefined): string | null {
  if (!count || count <= 0) return null
  return count > BADGE_MAX ? `${BADGE_MAX}+` : String(count)
}

export const unreadCountQueryOptions = () =>
  queryOptions({
    queryKey: [...NOTIFICATIONS_QUERY_KEY, "unread-count"],
    queryFn: async () => (await NotificationsService.getUnreadCount()).data,
  })

export const notificationsQueryOptions = (page: number) =>
  queryOptions({
    queryKey: [...NOTIFICATIONS_QUERY_KEY, "list", { page }],
    queryFn: async () =>
      (await NotificationsService.listNotifications({ query: { page } })).data,
  })

/**
 * 頂欄鈴鐺的未讀數：登入時每 30 秒輪詢。未讀數增加時（例如收到主辦方申請核准），
 * 重新取得帳號與身分清單（UX-DR8），並重新取得通知列表，讓新通知出現在最上方。
 * 輪詢失敗時回傳 undefined（不顯示徽章、不跳錯）。
 */
export function useUnreadCount(): number | undefined {
  const signedIn = useIsSignedIn()
  const queryClient = useQueryClient()
  const query = useQuery({
    ...unreadCountQueryOptions(),
    enabled: signedIn,
    refetchInterval: UNREAD_POLL_INTERVAL_MS,
  })
  const count = query.isError ? undefined : query.data?.count
  const previous = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (count === undefined) return
    const before = previous.current
    previous.current = count
    if (before !== undefined && count > before) {
      void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
      void queryClient.invalidateQueries({
        queryKey: [...NOTIFICATIONS_QUERY_KEY, "list"],
      })
    }
  }, [count, queryClient])

  return count
}

/** S14 的通知列表；換頁時先保留上一頁的資料，不再顯示 Skeleton。 */
export function useNotifications(page: number, enabled = true) {
  return useQuery({
    ...notificationsQueryOptions(page),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useMarkNotificationRead() {
  return useMutation({
    mutationFn: async (notificationId: string) =>
      (
        await NotificationsService.markNotificationRead({
          path: { notification_id: notificationId },
        })
      ).data,
  })
}

/**
 * 點擊一則通知：未讀時先標為已讀，再重新取得未讀數與列表，最後導向它的 `link`。
 * 標記失敗仍然導向（不跳錯）；不做 optimistic update。
 */
export function useOpenNotification(): (
  notification: NotificationRead,
) => Promise<void> {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { mutateAsync } = useMarkNotificationRead()
  return useCallback(
    async (notification: NotificationRead) => {
      if (notification.read_at === null) {
        try {
          await mutateAsync(notification.id)
        } catch {
          // 標記失敗仍導向 link
        }
        await queryClient.invalidateQueries({
          queryKey: NOTIFICATIONS_QUERY_KEY,
        })
      }
      router.history.push(notification.link)
    },
    [mutateAsync, queryClient, router],
  )
}
