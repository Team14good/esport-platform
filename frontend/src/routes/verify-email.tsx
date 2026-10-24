import { createFileRoute } from "@tanstack/react-router"

import { safeRedirect } from "@/features/identity/redirect"
import { VerifyEmailPage } from "@/features/identity/VerifyEmailPage"

type VerifyEmailSearch = { token?: string; redirect?: string }

export const Route = createFileRoute("/verify-email")({
  // 一律回傳兩個鍵：根路由沒有驗證查詢參數，沒覆寫的話不合格的值會原樣傳下來
  validateSearch: (search: Record<string, unknown>): VerifyEmailSearch => ({
    token:
      typeof search.token === "string" && search.token.length > 0
        ? search.token
        : undefined,
    redirect: safeRedirect(search.redirect),
  }),
  head: () => ({ meta: [{ title: "Email 驗證 · FLOW" }] }),
  component: VerifyEmailRoute,
})

function VerifyEmailRoute() {
  const { token, redirect } = Route.useSearch()
  return <VerifyEmailPage token={token} redirect={redirect} />
}
