import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<
  ReturnType<typeof IdentityService.listOrganizerApplications>
>

function mockEmptyList() {
  return vi
    .spyOn(IdentityService, "listOrganizerApplications")
    .mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 20 },
    } as unknown as ListResult)
}

describe("後台側欄版面", () => {
  it("≥ lg：240px 側欄，目前項目以 active 樣式標示", async () => {
    mockEmptyList()
    signInAs({ account: { ...ACCOUNT, is_platform_admin: true } })
    renderApp("/admin/applications")

    await screen.findByRole("heading", { name: "主辦方申請" })
    const sidebar = document.querySelector(
      "[data-slot=backoffice-sidebar]",
    ) as HTMLElement
    expect(sidebar).toHaveClass("w-sidebar-width", "hidden", "lg:block")
    const nav = within(sidebar).getByRole("navigation", { name: "平台管理" })
    const link = within(nav).getByRole("link", { name: "主辦方申請" })
    expect(link).toHaveAttribute("href", "/admin/applications")
    expect(link).toHaveAttribute("data-status", "active")
    expect(link.className).toContain("data-[status=active]:border-primary")
    expect(link.className).toContain("data-[status=active]:bg-sidebar-accent")
  })

  it("< lg：從選單鈕開啟 Sheet，選擇項目後自動關閉", async () => {
    const user = userEvent.setup()
    mockEmptyList()
    signInAs({ account: { ...ACCOUNT, is_platform_admin: true } })
    renderApp("/admin/applications")

    const trigger = await screen.findByRole("button", {
      name: "開啟平台管理選單",
    })
    expect(trigger.parentElement).toHaveClass("lg:hidden")
    await user.click(trigger)

    const sheet = await screen.findByRole("dialog", { name: "平台管理" })
    await user.click(within(sheet).getByRole("link", { name: "主辦方申請" }))

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "平台管理" })).toBeNull(),
    )
  })
})

describe("S25 我的賽事（佔位頁）", () => {
  it("主辦方：側欄只有「我的賽事」，顯示 Empty state，沒有「建立賽事」", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    renderApp("/organizer")

    expect(
      await screen.findByRole("heading", { name: "我的賽事" }),
    ).toBeInTheDocument()
    expect(screen.getByText("你還沒有建立賽事。")).toBeInTheDocument()
    const sidebar = document.querySelector(
      "[data-slot=backoffice-sidebar]",
    ) as HTMLElement
    const links = within(sidebar).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual(["我的賽事"])
    expect(screen.queryByRole("button", { name: "建立賽事" })).toBeNull()
    expect(screen.queryByRole("link", { name: "建立賽事" })).toBeNull()
  })

  it("不是主辦方：顯示 S38 的 403", async () => {
    signInAs()
    renderApp("/organizer")

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
    expect(screen.queryByText("你還沒有建立賽事。")).toBeNull()
  })

  it("未登入：導向 S6 並帶 redirect", async () => {
    const router = renderApp("/organizer")

    await screen.findByRole("heading", { name: "登入" })
    expect(router.state.location.search).toEqual({ redirect: "/organizer" })
  })
})
