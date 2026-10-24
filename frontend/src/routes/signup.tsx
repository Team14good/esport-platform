import { createFileRoute } from "@tanstack/react-router"

import { safeRedirect } from "@/features/identity/redirect"
import { SignupForm } from "@/features/identity/SignupForm"

type SignupSearch = { redirect?: string }

export const Route = createFileRoute("/signup")({
  // 一律回傳 redirect 鍵：根路由沒有驗證查詢參數，沒覆寫的話不合格的值會原樣傳下來
  validateSearch: (search: Record<string, unknown>): SignupSearch => ({
    redirect: safeRedirect(search.redirect),
  }),
  head: () => ({ meta: [{ title: "註冊 · FLOW" }] }),
  component: SignupPage,
})

function SignupPage() {
  const { redirect } = Route.useSearch()
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">註冊帳號</h1>
        <p className="text-body text-muted-foreground">
          註冊後會寄出驗證信；完成 Email 驗證後才能報名賽事或申請成為主辦方。
        </p>
      </div>
      <SignupForm redirect={redirect} />
    </section>
  )
}
