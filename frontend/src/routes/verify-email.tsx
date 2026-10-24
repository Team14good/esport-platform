import { createFileRoute } from "@tanstack/react-router"

import { safeRedirect } from "@/features/identity/redirect"
import { VerifyEmailPage } from "@/features/identity/VerifyEmailPage"

// verified=1：驗證成功後以它取代網址中的 token，重新整理時不會再送一次已用過的 token
type VerifyEmailSearch = { token?: string; redirect?: string; verified?: 1 }

export const Route = createFileRoute("/verify-email")({
  // 一律回傳所有鍵：根路由沒有驗證查詢參數，沒覆寫的話不合格的值會原樣傳下來
  validateSearch: (search: Record<string, unknown>): VerifyEmailSearch => ({
    token:
      typeof search.token === "string" && search.token.length > 0
        ? search.token
        : undefined,
    redirect: safeRedirect(search.redirect),
    verified: search.verified === 1 || search.verified === "1" ? 1 : undefined,
  }),
  head: () => ({ meta: [{ title: "Email 驗證 · FLOW" }] }),
  component: VerifyEmailRoute,
})

function VerifyEmailRoute() {
  const { token, redirect, verified } = Route.useSearch()
  return (
    <VerifyEmailPage
      token={token}
      redirect={redirect}
      verified={verified === 1}
    />
  )
}
