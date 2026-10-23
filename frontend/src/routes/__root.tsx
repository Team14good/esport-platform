import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools"

import { AppShell } from "@/components/layout/AppShell"
import { NotFoundPage, RouteErrorPage } from "@/components/layout/ErrorPage"

export const Route = createRootRoute({
  head: () => ({
    meta: [{ title: "FLOW" }],
  }),
  component: () => (
    <>
      <HeadContent />
      <AppShell>
        <Outlet />
      </AppShell>
      <TanStackRouterDevtools position="bottom-right" />
      <ReactQueryDevtools initialIsOpen={false} />
    </>
  ),
  // 不存在的網址：在外框內的 Outlet 顯示 S38 404
  notFoundComponent: NotFoundPage,
  // 根路由本身出錯時外框也要在；子路由的錯誤由 router 的 defaultErrorComponent 在外框內顯示
  errorComponent: ({ error }) => (
    <AppShell>
      <RouteErrorPage error={error} />
    </AppShell>
  ),
})
