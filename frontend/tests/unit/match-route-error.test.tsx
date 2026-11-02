import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { routeTree } from "@/routeTree.gen"
import { renderRouter } from "./render-router"

// 開發工具在測試裡不需要
vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))
// 取得場次一律失敗（不是找不到場次），模擬第一次載入就斷線
vi.mock("@/features/competition/match-source", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("@/features/competition/match-source")
  >()),
  fetchMatchDetail: () => Promise.reject(new Error("network")),
}))

describe("S4 場次頁：第一次載入就失敗", () => {
  it("不等連續失敗 3 次，直接顯示連線中斷橫幅，不是 404", async () => {
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({
        initialEntries: ["/tournaments/t1/matches/match-M3"],
      }),
      defaultErrorComponent: RouteErrorPage,
    })
    renderRouter(router)

    expect(await screen.findByText("連線中斷，正在重試")).toBeInTheDocument()
    expect(screen.queryByText("找不到這個頁面。")).toBeNull()
    expect(document.querySelector("[data-slot=match-loading]")).not.toBeNull()
  })
})
