import { act, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { type NotificationRead, NotificationsService } from "@/client"
import {
  badgeText,
  parsePage,
  UNREAD_POLL_INTERVAL_MS,
} from "@/features/notifications/queries"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

type UnreadCountResult = Awaited<
  ReturnType<typeof NotificationsService.getUnreadCount>
>
type ListResult = Awaited<
  ReturnType<typeof NotificationsService.listNotifications>
>
type MarkReadResult = Awaited<
  ReturnType<typeof NotificationsService.markNotificationRead>
>

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

afterEach(() => {
  vi.useRealTimers()
})

function notification(
  index: number,
  overrides: Partial<NotificationRead> = {},
): NotificationRead {
  return {
    id: `n-${index}`,
    type: "OrganizerApplicationApproved",
    title: `通知 ${index}`,
    body: "說明",
    link: "/me",
    // UTC 11:00 = 台北 19:00
    created_at: "2026-10-18T11:00:00Z",
    read_at: null,
    ...overrides,
  }
}

function mockUnread(...counts: number[]) {
  const spy = vi.spyOn(NotificationsService, "getUnreadCount")
  for (const count of counts) {
    spy.mockResolvedValueOnce({ data: { count } } as UnreadCountResult)
  }
  const last = counts[counts.length - 1] ?? 0
  spy.mockResolvedValue({ data: { count: last } } as UnreadCountResult)
  return spy
}

function mockList(items: NotificationRead[], total = items.length) {
  return vi.spyOn(NotificationsService, "listNotifications").mockResolvedValue({
    data: { items, total, page: 1, page_size: 20 },
  } as ListResult)
}

async function bell(name: string | RegExp = /^通知/) {
  const banner = await screen.findByRole("banner")
  return within(banner).findByRole("button", { name })
}

describe("徽章文字", () => {
  it("0 不顯示、5 顯示 5、超過 99 顯示 99+", () => {
    expect(badgeText(undefined)).toBeNull()
    expect(badgeText(0)).toBeNull()
    expect(badgeText(5)).toBe("5")
    expect(badgeText(99)).toBe("99")
    expect(badgeText(120)).toBe("99+")
  })

  it("網址的 page：不是 2 以上的整數時當成第 1 頁", () => {
    expect(parsePage("2")).toBe(2)
    expect(parsePage(3)).toBe(3)
    expect(parsePage("1")).toBeUndefined()
    expect(parsePage("0")).toBeUndefined()
    expect(parsePage("abc")).toBeUndefined()
    expect(parsePage("1.5")).toBeUndefined()
  })
})

describe("頂欄鈴鐺", () => {
  it("未登入時沒有鈴鐺", async () => {
    renderApp("/")

    const banner = await screen.findByRole("banner")
    await within(banner).findByRole("link", { name: "登入" })
    expect(within(banner).queryByRole("button", { name: /^通知/ })).toBeNull()
  })

  it("未讀 120 則顯示「99+」，0 則不顯示徽章", async () => {
    mockUnread(120)
    signInAs()
    renderApp("/")

    const button = await bell("通知（99+ 則未讀）")
    expect(within(button).getByText("99+")).toBeInTheDocument()
  })

  it("沒有未讀時不顯示徽章", async () => {
    mockUnread(0)
    signInAs()
    renderApp("/")

    const button = await bell("通知")
    expect(button.querySelector('[data-slot="unread-badge"]')).toBeNull()
  })

  it("輪詢失敗時不顯示徽章、不跳錯", async () => {
    vi.spyOn(NotificationsService, "getUnreadCount").mockRejectedValue(
      httpError(500, { detail: "boom" }),
    )
    signInAs()
    renderApp("/")

    const button = await bell("通知")
    expect(button.querySelector('[data-slot="unread-badge"]')).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("每 30 秒輪詢一次未讀數；增加時重新取得身分清單", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const unread = mockUnread(1, 2)
    const { listIdentities } = signInAs()
    renderApp("/")

    await bell("通知（1 則未讀）")
    expect(unread).toHaveBeenCalledTimes(1)
    const identityCalls = listIdentities.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(UNREAD_POLL_INTERVAL_MS)
    })

    await bell("通知（2 則未讀）")
    expect(unread).toHaveBeenCalledTimes(2)
    await waitFor(() =>
      expect(listIdentities.mock.calls.length).toBeGreaterThan(identityCalls),
    )
  })

  it("Popover：最新 8 則、未讀有圓點、相對與絕對時間，底部「查看全部」", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date("2026-10-18T11:03:00Z"))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    mockUnread(10)
    const list = mockList(
      Array.from({ length: 10 }, (_, i) =>
        notification(i, i % 2 === 1 ? { read_at: "2026-10-18T11:01:00Z" } : {}),
      ),
      10,
    )
    signInAs()
    renderApp("/")

    await user.click(await bell("通知（10 則未讀）"))

    const dialog = await screen.findByRole("dialog", { name: "通知" })
    await within(dialog).findByText("通知 0")
    expect(list).toHaveBeenCalledWith({ query: { page: 1 } })
    const items = within(dialog).getAllByRole("listitem")
    expect(items).toHaveLength(8)
    expect(within(dialog).queryByText("通知 8")).toBeNull()
    // 未讀的圓點是 primary 色，已讀的透明
    const dots = items.map((item) =>
      item.querySelector('[data-slot="unread-dot"]'),
    )
    expect(dots[0]).toHaveClass("bg-primary")
    expect(dots[1]).toHaveClass("bg-transparent")
    expect(
      within(items[0]).getByRole("button", { name: "未讀：通知 0" }),
    ).toBeInTheDocument()
    expect(within(items[0]).getByText("3 分鐘前")).toBeInTheDocument()
    expect(within(items[0]).getByText("10/18（日）19:00")).toBeInTheDocument()
    expect(
      within(dialog).getByRole("link", { name: "查看全部" }),
    ).toHaveAttribute("href", "/notifications")
  })

  it("Popover 沒有通知時顯示「還沒有通知。」", async () => {
    const user = userEvent.setup()
    mockUnread(0)
    mockList([])
    signInAs()
    renderApp("/")

    await user.click(await bell("通知"))

    const dialog = await screen.findByRole("dialog", { name: "通知" })
    expect(await within(dialog).findByText("還沒有通知。")).toBeInTheDocument()
  })

  it("點擊未讀通知：標為已讀、重新取得未讀數，並導向 link", async () => {
    const user = userEvent.setup()
    const unread = mockUnread(1, 0)
    mockList([notification(1, { link: "/me" })])
    const markRead = vi
      .spyOn(NotificationsService, "markNotificationRead")
      .mockResolvedValue({
        data: notification(1, { read_at: "2026-10-18T11:05:00Z" }),
      } as MarkReadResult)
    signInAs()
    const router = renderApp("/")

    await user.click(await bell("通知（1 則未讀）"))
    const dialog = await screen.findByRole("dialog", { name: "通知" })
    await user.click(
      await within(dialog).findByRole("button", { name: "未讀：通知 1" }),
    )

    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))
    expect(markRead).toHaveBeenCalledWith({ path: { notification_id: "n-1" } })
    expect(unread.mock.calls.length).toBeGreaterThanOrEqual(2)
    await bell("通知")
  })

  it("標記失敗仍導向 link", async () => {
    const user = userEvent.setup()
    mockUnread(1)
    mockList([notification(1, { link: "/me" })])
    vi.spyOn(NotificationsService, "markNotificationRead").mockRejectedValue(
      httpError(404, {
        detail: { code: "NOTIFICATION_NOT_FOUND", message: "找不到這則通知。" },
      }),
    )
    signInAs()
    const router = renderApp("/")

    await user.click(await bell("通知（1 則未讀）"))
    const dialog = await screen.findByRole("dialog", { name: "通知" })
    await user.click(
      await within(dialog).findByRole("button", { name: "未讀：通知 1" }),
    )

    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))
  })

  it("點擊已讀通知不再標記，直接導向", async () => {
    const user = userEvent.setup()
    mockUnread(0)
    mockList([notification(1, { read_at: "2026-10-18T11:05:00Z" })])
    const markRead = vi.spyOn(NotificationsService, "markNotificationRead")
    signInAs()
    const router = renderApp("/")

    await user.click(await bell("通知"))
    const dialog = await screen.findByRole("dialog", { name: "通知" })
    await user.click(
      await within(dialog).findByRole("button", { name: /通知 1/ }),
    )

    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))
    expect(markRead).not.toHaveBeenCalled()
  })
})

describe("S14 通知中心", () => {
  it("未登入導向 S6 並帶 redirect", async () => {
    const router = renderApp("/notifications?page=2")

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(router.state.location.search).toEqual({
      redirect: "/notifications?page=2",
    })
  })

  it("沒有通知時顯示 Empty state「還沒有通知。」", async () => {
    mockUnread(0)
    mockList([])
    signInAs()
    renderApp("/notifications")

    const main = await screen.findByRole("heading", { name: "通知", level: 1 })
    expect(main).toBeInTheDocument()
    expect(await screen.findByText("還沒有通知。")).toBeInTheDocument()
  })

  it("頁碼寫在網址：第 2 頁抓第 2 頁，換頁時更新網址", async () => {
    const user = userEvent.setup()
    mockUnread(0)
    const list = vi
      .spyOn(NotificationsService, "listNotifications")
      .mockImplementation(((options?: { query?: { page?: number } }) =>
        Promise.resolve({
          data: {
            items: [notification(options?.query?.page ?? 1)],
            total: 45,
            page: options?.query?.page ?? 1,
            page_size: 20,
          },
        } as ListResult)) as unknown as typeof NotificationsService.listNotifications)
    signInAs()
    const router = renderApp("/notifications?page=2")

    expect(await screen.findByText("通知 2")).toBeInTheDocument()
    expect(list).toHaveBeenCalledWith({ query: { page: 2 } })

    await user.click(screen.getByRole("button", { name: "下一頁" }))

    expect(await screen.findByText("通知 3")).toBeInTheDocument()
    expect(router.state.location.search).toEqual({ page: 3 })
  })

  it("點擊未讀通知：標為已讀並導向 link", async () => {
    const user = userEvent.setup()
    mockUnread(1, 0)
    mockList([notification(7, { link: "/me" })])
    const markRead = vi
      .spyOn(NotificationsService, "markNotificationRead")
      .mockResolvedValue({
        data: notification(7, { read_at: "2026-10-18T11:05:00Z" }),
      } as MarkReadResult)
    signInAs()
    const router = renderApp("/notifications")

    await user.click(
      await screen.findByRole("button", { name: "未讀：通知 7" }),
    )

    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))
    expect(markRead).toHaveBeenCalledWith({ path: { notification_id: "n-7" } })
  })
})
