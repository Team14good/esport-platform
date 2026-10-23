import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { UtilsService } from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { routeTree } from "@/routeTree.gen"
import { renderRouter } from "./render-router"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type HealthCheckResult = Awaited<ReturnType<typeof UtilsService.healthCheck>>

function renderHome() {
  return renderRouter(
    createRouter({
      routeTree,
      history: createMemoryHistory({ initialEntries: ["/"] }),
      defaultErrorComponent: RouteErrorPage,
    }),
  )
}

describe("首頁健康檢查", () => {
  it("首次載入：顯示 Skeleton 與「載入中」狀態，不顯示後端狀態文字", async () => {
    vi.spyOn(UtilsService, "healthCheck").mockReturnValue(
      new Promise<never>(() => {}),
    )
    renderHome()

    expect(
      await screen.findByTestId("health-check-skeleton"),
    ).toBeInTheDocument()
    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveTextContent("載入中")
    expect(screen.queryByText(/後端狀態/)).toBeNull()
  })

  it("後端回應正常：顯示「後端狀態：正常」", async () => {
    vi.spyOn(UtilsService, "healthCheck").mockResolvedValue({
      data: true,
    } as HealthCheckResult)
    renderHome()

    expect(await screen.findByText("後端狀態：正常")).toBeInTheDocument()
    expect(screen.queryByTestId("health-check-skeleton")).toBeNull()
  })

  it("後端沒有回應：顯示「後端狀態：無法連線」", async () => {
    vi.spyOn(UtilsService, "healthCheck").mockRejectedValue(
      new Error("Network Error"),
    )
    renderHome()

    expect(await screen.findByText("後端狀態：無法連線")).toBeInTheDocument()
    expect(screen.queryByTestId("health-check-skeleton")).toBeNull()
  })
})
