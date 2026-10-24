import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { MobileMenu } from "@/components/layout/MobileMenu"
import { THEME_STORAGE_KEY } from "@/components/theme-provider"
import { renderRouter } from "./render-router"

describe("手機選單", () => {
  it("開啟後 Sheet 內有「賽事」、主題切換與「註冊」", async () => {
    const user = userEvent.setup()
    const rootRoute = createRootRoute({ component: MobileMenu })
    renderRouter(
      createRouter({
        routeTree: rootRoute,
        history: createMemoryHistory({ initialEntries: ["/"] }),
      }),
    )

    await user.click(await screen.findByRole("button", { name: "開啟選單" }))

    const sheet = await screen.findByRole("dialog", { name: "選單" })
    expect(within(sheet).getByRole("link", { name: "賽事" })).toHaveAttribute(
      "href",
      "/",
    )
    expect(
      within(sheet).getByRole("button", { name: "切換為淺色模式" }),
    ).toBeInTheDocument()
    expect(within(sheet).getByRole("link", { name: "註冊" })).toHaveAttribute(
      "href",
      "/signup",
    )
  })

  it("Sheet 內的主題切換：點了立即換成淺色並保存，按鈕改為切回深色", async () => {
    // 375 px 寬時頂欄的圖示版切換被隱藏，這顆是手機上唯一的主題切換
    const user = userEvent.setup()
    const rootRoute = createRootRoute({ component: MobileMenu })
    renderRouter(
      createRouter({
        routeTree: rootRoute,
        history: createMemoryHistory({ initialEntries: ["/"] }),
      }),
    )

    await user.click(await screen.findByRole("button", { name: "開啟選單" }))
    const sheet = await screen.findByRole("dialog", { name: "選單" })
    await user.click(
      within(sheet).getByRole("button", { name: "切換為淺色模式" }),
    )

    expect(document.documentElement).toHaveClass("light")
    expect(document.documentElement).not.toHaveClass("dark")
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light")
    expect(
      within(sheet).getByRole("button", { name: "切換為深色模式" }),
    ).toBeInTheDocument()
  })
})
