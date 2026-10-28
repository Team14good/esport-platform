import { createFileRoute, Link } from "@tanstack/react-router"

import { ForgotPasswordForm } from "@/features/identity/ForgotPasswordForm"

export const Route = createFileRoute("/forgot-password")({
  head: () => ({ meta: [{ title: "忘記密碼 · FLOW" }] }),
  component: ForgotPasswordPage,
})

function ForgotPasswordPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 py-8 sm:py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">忘記密碼</h1>
        <p className="text-body text-muted-foreground">
          輸入註冊時的 Email，我們會寄一封重設信給你，連結 1 小時內有效。
        </p>
      </div>
      <ForgotPasswordForm />
      <p className="text-center text-body text-muted-foreground">
        想起密碼了？
        <Link
          to="/login"
          className="ml-1 font-medium text-primary underline-offset-4 hover:underline"
        >
          回到登入
        </Link>
      </p>
    </section>
  )
}
