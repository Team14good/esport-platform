import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  type AnyRouter,
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterContextProvider,
  RouterProvider,
} from "@tanstack/react-router"
import { render } from "@testing-library/react"
import type { ReactNode } from "react"

import { ThemeProvider } from "@/components/theme-provider"

/** 以與 main.tsx 相同的 provider 包住 router 來渲染。 */
export function renderRouter(router: AnyRouter) {
  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

/** 把單一元件放進只有根路由的 router 渲染，讓元件裡的 Link 能產生 href。 */
export async function renderInRouter(ui: ReactNode) {
  const rootRoute = createRootRoute({ component: () => ui })
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const result = renderRouter(router)
  await router.load()
  return { ...result, router }
}

/**
 * 只提供 router context（不經過路由渲染）來渲染元件，讓元件裡的 Link 能產生 href；
 * 回傳的 rerender 同樣包著 router，適合需要同步 rerender 的測試。
 */
export function renderWithRouterContext(ui: ReactNode) {
  const rootRoute = createRootRoute()
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const wrap = (node: ReactNode) => (
    <RouterContextProvider router={router}>{node}</RouterContextProvider>
  )
  const result = render(wrap(ui))
  return {
    ...result,
    rerender: (node: ReactNode) => result.rerender(wrap(node)),
  }
}
