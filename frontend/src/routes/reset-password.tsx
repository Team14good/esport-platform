import { createFileRoute } from "@tanstack/react-router"

import { ResetPasswordPage } from "@/features/identity/ResetPasswordPage"

type ResetPasswordSearch = { token?: string }

export const Route = createFileRoute("/reset-password")({
  // 一律回傳 token 鍵：根路由沒有驗證查詢參數，沒覆寫的話不合格的值會原樣傳下來
  validateSearch: (search: Record<string, unknown>): ResetPasswordSearch => ({
    token:
      typeof search.token === "string" && search.token.length > 0
        ? search.token
        : undefined,
  }),
  head: () => ({ meta: [{ title: "重設密碼 · FLOW" }] }),
  component: ResetPasswordRoute,
})

function ResetPasswordRoute() {
  const { token } = Route.useSearch()
  return <ResetPasswordPage token={token} />
}
