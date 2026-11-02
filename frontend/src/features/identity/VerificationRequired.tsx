import { useMutation } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import { MailWarningIcon } from "lucide-react"
import type { ReactNode } from "react"

import { IdentityService } from "@/client"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { notifyError, notifySuccess } from "@/lib/feedback"
import { cn } from "@/lib/utils"
import { useCurrentAccount, useIsSignedIn } from "./auth"
import { RESEND_SUCCESS_TEXT } from "./ResendVerificationForm"
import { safeRedirect } from "./redirect"

export const GO_TO_VERIFY_TEXT = "前往 Email 驗證"

/** 以帳號 Email 重寄驗證信（S10 與 VerificationRequired 共用）；成功與失敗都以 Toast 回饋。 */
export function useResendVerificationEmail() {
  return useMutation({
    mutationFn: async (email: string) =>
      IdentityService.resendVerificationEmail({
        body: { email, redirect: null },
      }),
    onSuccess: () => notifySuccess(RESEND_SUCCESS_TEXT),
    onError: notifyError,
  })
}

type VerificationRequiredProps = {
  /** 被擋下的動作，接在「完成 Email 驗證後才能」後面，例如「申請成為主辦方」 */
  action: string
  /** 要停用的動作（按鈕、表單）；Email 已驗證或未登入時原樣顯示 */
  children: ReactNode
  /**
   * 把「重寄驗證信」換成「前往 Email 驗證」連結（S7，帶 redirect 回目前頁面）；
   * 整個表單被停用的頁面（S15）用這個
   */
  linkToVerifyPage?: boolean
  className?: string
}

/**
 * Email 未驗證時停用動作，並說明「完成 Email 驗證後才能…」＋「重寄驗證信」
 * （或「前往 Email 驗證」）。
 * 這只是提示：伺服器仍以 `require_verified` 回 403 `EMAIL_NOT_VERIFIED` 為準（AD-10）。
 * 未登入時不處理，交給 401 的導向 S6 流程。
 */
export function VerificationRequired({
  action,
  children,
  linkToVerifyPage = false,
  className,
}: VerificationRequiredProps) {
  const signedIn = useIsSignedIn()
  const account = useCurrentAccount()
  const resend = useResendVerificationEmail()
  const currentHref = useRouterState({ select: (state) => state.location.href })

  if (!signedIn || account.data?.email_verified) return <>{children}</>
  if (!account.data) {
    // 已登入但還不知道是否驗證（載入中或載入失敗）：先停用，不顯示說明
    return (
      <fieldset disabled aria-disabled="true" className="contents">
        {children}
      </fieldset>
    )
  }
  const email = account.data.email

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* disabled 的 fieldset 會停用裡面所有按鈕與欄位 */}
      <fieldset disabled aria-disabled="true" className="contents">
        {children}
      </fieldset>
      <div className="flex flex-col items-start gap-2 rounded-md border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-start gap-2 text-body text-muted-foreground">
          <MailWarningIcon
            aria-hidden="true"
            className="mt-0.5 size-4 shrink-0 text-status-appeal"
          />
          完成 Email 驗證後才能{action}。
        </p>
        {linkToVerifyPage ? (
          <Button asChild variant="outline" size="sm" className="shrink-0">
            <Link
              to="/verify-email"
              search={{ redirect: safeRedirect(currentHref) }}
            >
              {GO_TO_VERIFY_TEXT}
            </Link>
          </Button>
        ) : (
          <LoadingButton
            type="button"
            variant="outline"
            size="sm"
            loading={resend.isPending}
            onClick={() => resend.mutate(email)}
          >
            重寄驗證信
          </LoadingButton>
        )}
      </div>
    </div>
  )
}
