import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router"
import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AppShell } from "@/components/layout/AppShell"
import { ErrorPage, RouteErrorPage } from "@/components/layout/ErrorPage"
import { UNEXPECTED_ERROR_MESSAGE } from "@/lib/api-error"
import { routeTree } from "@/routeTree.gen"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

// 開發工具在測試裡不需要
vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

/** 建一個外框＋會在 loader 丟出指定錯誤的 /resource 路由。 */
function renderLoaderError(loaderError: unknown) {
  const rootRoute = createRootRoute({
    component: () => (
      <AppShell>
        <Outlet />
      </AppShell>
    ),
  })
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => <p>首頁</p>,
  })
  const resourceRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/resource",
    loader: () => {
      throw loaderError
    },
    component: () => <p>資源內容</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, resourceRoute]),
    history: createMemoryHistory({ initialEntries: ["/resource"] }),
    defaultErrorComponent: RouteErrorPage,
  })
  vi.spyOn(console, "warn").mockImplementation(() => {})
  vi.spyOn(console, "error").mockImplementation(() => {})
  return renderRouter(router)
}

function expectBackHomeAndTopBar() {
  expect(screen.getByRole("link", { name: "回到首頁" })).toHaveAttribute(
    "href",
    "/",
  )
  expect(screen.getByRole("link", { name: "FLOW 首頁" })).toBeInTheDocument()
}

describe("S38 錯誤頁", () => {
  it("不存在的網址：外框內顯示 404 文案與「回到首頁」", async () => {
    const router = createRouter({
      routeTree,
      history: createMemoryHistory({ initialEntries: ["/no-such-page"] }),
      defaultErrorComponent: RouteErrorPage,
    })
    renderRouter(router)

    expect(await screen.findByText("找不到這個頁面。")).toBeInTheDocument()
    expectBackHomeAndTopBar()
    expect(screen.getAllByRole("link", { name: "登入" })[0]).toHaveAttribute(
      "href",
      "/login",
    )
  })

  it("路由載入時 API 回 403：外框內顯示 403 文案與「回到首頁」", async () => {
    renderLoaderError(
      httpError(403, {
        detail: { code: "FORBIDDEN", message: "只有平台管理員可以查看。" },
      }),
    )

    expect(
      await screen.findByText("你沒有權限查看這個頁面。"),
    ).toBeInTheDocument()
    expect(screen.queryByText("資源內容")).toBeNull()
    expectBackHomeAndTopBar()
  })

  it("路由載入時 API 回 404：外框內顯示 S38 404，不顯示伺服器原文", async () => {
    renderLoaderError(
      httpError(404, {
        detail: { code: "TOURNAMENT_NOT_FOUND", message: "找不到這個賽事。" },
      }),
    )

    expect(await screen.findByText("找不到這個頁面。")).toBeInTheDocument()
    expect(screen.queryByText("找不到這個賽事。")).toBeNull()
    expectBackHomeAndTopBar()
  })

  it("路由載入時其他業務錯誤（409）：外框內照實顯示伺服器訊息", async () => {
    renderLoaderError(
      httpError(409, {
        detail: { code: "REGISTRATION_CLOSED", message: "報名已截止。" },
      }),
    )

    expect(
      await screen.findByRole("heading", { name: "報名已截止。" }),
    ).toBeInTheDocument()
    expect(screen.queryByText("找不到這個頁面。")).toBeNull()
    expectBackHomeAndTopBar()
  })

  it("路由載入時伺服器 500：外框內顯示狀態碼訊息", async () => {
    renderLoaderError(httpError(500, "Internal Server Error"))

    expect(
      await screen.findByRole("heading", { name: "伺服器發生錯誤（500）" }),
    ).toBeInTheDocument()
    expectBackHomeAndTopBar()
  })

  it("訊息為空時顯示「發生未預期的錯誤」，不會是空白標題", async () => {
    const rootRoute = createRootRoute({
      component: () => <ErrorPage message="" />,
    })
    renderRouter(
      createRouter({
        routeTree: rootRoute,
        history: createMemoryHistory({ initialEntries: ["/"] }),
      }),
    )

    expect(
      await screen.findByRole("heading", { name: UNEXPECTED_ERROR_MESSAGE }),
    ).toBeInTheDocument()
  })
})
