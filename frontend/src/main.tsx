import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { client } from "./client/client.gen"
import { RouteErrorPage } from "./components/layout/ErrorPage"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import { SUCCESS_TOAST_DURATION } from "./lib/feedback"
import "./index.css"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
})

const queryClient = new QueryClient()

const router = createRouter({
  routeTree,
  // 子路由載入失敗時在外框內顯示（403 → S38），頂欄保留
  defaultErrorComponent: RouteErrorPage,
})
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
