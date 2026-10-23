import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from "@tanstack/react-router"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { MobileMenu } from "@/components/layout/MobileMenu"
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
})
