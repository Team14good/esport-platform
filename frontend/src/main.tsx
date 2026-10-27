import { QueryClientProvider } from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { RouteErrorPage } from "./components/layout/ErrorPage"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import { configureApiClient } from "./features/identity/auth"
import { SUCCESS_TOAST_DURATION } from "./lib/feedback"
import { createQueryClient } from "./lib/query-client"
import "./index.css"
import { routeTree } from "./routeTree.gen"

// 401 不重試：每次重試都會再觸發一次登入過期流程
const queryClient = createQueryClient()

const router = createRouter({
  routeTree,
  // 子路由載入失敗時在外框內顯示（403 → S38），頂欄保留
  defaultErrorComponent: RouteErrorPage,
})

// 需要登入的 API 帶 Authorization；任何 API 回 401 時清除登入狀態並導向 S6（帶 redirect）
configureApiClient(router, queryClient, import.meta.env.VITE_API_URL ?? "")

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        {/* 成功 Toast 3 秒消失；錯誤 Toast 由 notifyError 設為不自動消失，靠關閉鈕關掉 */}
        <Toaster richColors closeButton duration={SUCCESS_TOAST_DURATION} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
