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

  it("載入前後是同一個 role=status 元素，螢幕閱讀器才會唸出結果", async () => {
    let resolveHealth: (value: HealthCheckResult) => void = () => {}
    vi.spyOn(UtilsService, "healthCheck").mockReturnValue(
      new Promise<HealthCheckResult>((resolve) => {
        resolveHealth = resolve
      }) as ReturnType<typeof UtilsService.healthCheck>,
    )
    renderHome()

    const loading = await screen.findByRole("status")
    expect(loading).toHaveAttribute("aria-busy", "true")

    resolveHealth({ data: true } as HealthCheckResult)

    await screen.findByText("後端狀態：正常")
    const done = screen.getByRole("status")
    expect(done).toBe(loading)
    expect(done).toHaveAttribute("aria-busy", "false")
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
