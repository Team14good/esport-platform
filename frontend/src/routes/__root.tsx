import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools"

export const Route = createRootRoute({
  head: () => ({
    meta: [{ title: "FLOW" }],
  }),
  component: () => (
    <>
      <HeadContent />
      <Outlet />
      <TanStackRouterDevtools position="bottom-right" />
      <ReactQueryDevtools initialIsOpen={false} />
    </>
  ),
  notFoundComponent: () => (
    <main className="flex min-h-svh items-center justify-center p-6">
      <p className="text-muted-foreground">找不到這個頁面</p>
    </main>
  ),
})
