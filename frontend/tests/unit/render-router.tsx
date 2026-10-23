import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type AnyRouter, RouterProvider } from "@tanstack/react-router"
import { render } from "@testing-library/react"

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
