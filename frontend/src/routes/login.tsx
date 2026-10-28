import { createFileRoute, Link } from "@tanstack/react-router"

import { LoginForm } from "@/features/identity/LoginForm"
import { safeRedirect } from "@/features/identity/redirect"

type LoginSearch = { redirect?: string }

export const Route = createFileRoute("/login")({
  // 一律回傳 redirect 鍵：根路由沒有驗證查詢參數，沒覆寫的話不合格的值會原樣傳下來
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    redirect: safeRedirect(search.redirect),
  }),
  head: () => ({ meta: [{ title: "登入 · FLOW" }] }),
  component: LoginPage,
})

function LoginPage() {
  const { redirect } = Route.useSearch()
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">登入</h1>
        <p className="text-body text-muted-foreground">
          以註冊時的 Email 與密碼登入。
        </p>
      </div>
      <LoginForm redirect={redirect} />
      <Link
        to="/forgot-password"
        className="self-end font-medium text-body text-primary underline-offset-4 hover:underline"
      >
        忘記密碼
      </Link>
      <p className="text-center text-body text-muted-foreground">
        還沒有帳號？
        <Link
          to="/signup"
          search={redirect ? { redirect } : {}}
          className="ml-1 font-medium text-primary underline-offset-4 hover:underline"
        >
          註冊帳號
        </Link>
      </p>
    </section>
  )
}
