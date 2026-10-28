import { useQuery } from "@tanstack/react-query"
import { useLocation, useNavigate, useRouter } from "@tanstack/react-router"
import { CircleCheckIcon, MailIcon, TriangleAlertIcon } from "lucide-react"
import { type ReactNode, useEffect } from "react"

import { IdentityService } from "@/client"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import "./history-state"
import { ResendVerificationForm } from "./ResendVerificationForm"

export const VERIFICATION_LINK_INVALID = "VERIFICATION_LINK_INVALID"

const iconClass = "size-10"

/** 置中的結果卡片（S7、S9 共用）：圖示＋標題＋內容。 */
export function PageCard({
  icon,
  title,
  children,
}: {
  icon: ReactNode
  title: string
  children: ReactNode
}) {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-5 py-8 sm:py-12">
      <div className="flex flex-col items-center gap-3 text-center">
        {icon}
        <h1 className="text-heading-lg">{title}</h1>
      </div>
      {children}
    </section>
  )
}

/** S7 待驗證：「請收信驗證」＋已寄到哪個 Email＋「重寄驗證信」。 */
function CheckInbox({ redirect }: { redirect?: string }) {
  const registeredEmail = useLocation({
    select: (location) => location.state.registeredEmail,
  })
  return (
    <PageCard
      icon={
        <MailIcon aria-hidden="true" className={`${iconClass} text-primary`} />
      }
      title="請收信驗證"
    >
      <p className="text-center text-body text-muted-foreground">
        {registeredEmail ? (
          <>
            驗證信已寄到
            <span className="mx-1 break-all font-semibold text-foreground">
              {registeredEmail}
            </span>
            ，點信中的「驗證 Email」按鈕完成驗證，連結 24 小時內有效。
          </>
        ) : (
          "請到信箱點驗證信中的「驗證 Email」按鈕完成驗證，連結 24 小時內有效。"
        )}
      </p>
      <p className="text-center text-caption text-muted-foreground">
        沒收到信？確認 Email 後重寄一次。
      </p>
      <ResendVerificationForm
        defaultEmail={registeredEmail}
        redirect={redirect}
      />
    </PageCard>
  )
}

/** S7 點驗證連結後：驗證中、驗證完成、連結失效。 */
function VerifyToken({
  token,
  redirect,
}: {
  token: string
  redirect?: string
}) {
  // 用 query 而不是 mutation：同一個 token 只送一次（StrictMode 重複掛載也不會再送；
  // 否則第二次會因為 token 已用過而顯示失效）
  const verification = useQuery({
    queryKey: ["identity", "email-verification", token],
    queryFn: async () => {
      await IdentityService.verifyEmail({ body: { token } })
      return true
    },
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  // 驗證成功後把網址的 token 換成 verified=1：重新整理或從瀏覽紀錄回到這頁時，
  // 不會再送一次已用過的 token 而被當成「連結已失效」
  const navigate = useNavigate()
  useEffect(() => {
    if (verification.isSuccess) {
      navigate({
        to: "/verify-email",
        search: { redirect, verified: 1 },
        replace: true,
      })
    }
  }, [verification.isSuccess, navigate, redirect])

  if (verification.isPending) {
    return (
      <section
        className="mx-auto flex w-full max-w-md flex-col items-center gap-4 py-12"
        role="status"
        aria-busy="true"
      >
        <Skeleton className="size-10 rounded-full" />
        <Skeleton className="h-8 w-48" />
        <span className="sr-only">正在驗證 Email</span>
      </section>
    )
  }

  if (verification.isSuccess) {
    return <Verified redirect={redirect} />
  }

  const apiError = parseApiError(verification.error)
  // 422 代表 token 格式本身不合格（例如被截斷或改壞的連結），重試也不會成功，視同失效
  const invalidLink =
    (apiError.kind === "business" &&
      apiError.code === VERIFICATION_LINK_INVALID) ||
    apiError.kind === "validation"
  const icon = (
    <TriangleAlertIcon
      aria-hidden="true"
      className={`${iconClass} text-destructive`}
    />
  )

  if (!invalidLink) {
    // 連線失敗或伺服器錯誤：不代表連結失效，讓使用者重試同一個連結
    return (
      <PageCard icon={icon} title={getErrorMessage(apiError)}>
        <LoadingButton
          type="button"
          className="w-full"
          loading={verification.isFetching}
          onClick={() => verification.refetch()}
        >
          重試
        </LoadingButton>
      </PageCard>
    )
  }

  return (
    <PageCard icon={icon} title="此驗證連結已失效。">
      <p className="text-center text-body text-muted-foreground">
        連結用過一次、超過 24 小時，或之後又重寄過驗證信，就會失效。輸入 Email
        重寄一封新的驗證信。
      </p>
      <ResendVerificationForm redirect={redirect} />
    </PageCard>
  )
}

/** S7 驗證完成：「Email 驗證完成」＋「繼續」（有 redirect 時回原頁，否則回首頁）。 */
function Verified({ redirect }: { redirect?: string }) {
  return (
    <PageCard
      icon={
        <CircleCheckIcon
          aria-hidden="true"
          className={`${iconClass} text-primary`}
        />
      }
      title="Email 驗證完成"
    >
      <ContinueLink href={redirect ?? "/"} />
    </PageCard>
  )
}

/**
 * 「繼續」：redirect 可能帶 ?query 與 #hash，直接交給 history 以完整網址導覽，
 * 不經 Link 的 to（to 只代表路徑，查詢參數會被當成路徑的一部分）。
 */
function ContinueLink({ href }: { href: string }) {
  const router = useRouter()
  return (
    <Button asChild className="w-full">
      <a
        href={href}
        onClick={(event) => {
          // 新分頁開啟等修飾鍵點擊交給瀏覽器
          if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          ) {
            return
          }
          event.preventDefault()
          router.history.push(href)
        }}
      >
        繼續
      </a>
    </Button>
  )
}

/**
 * S7 Email 驗證頁：網址有 token 時驗證；驗證成功後網址換成 verified=1，顯示驗證完成；
 * 兩者都沒有時顯示「請收信驗證」。
 */
export function VerifyEmailPage({
  token,
  redirect,
  verified = false,
}: {
  token?: string
  redirect?: string
  verified?: boolean
}) {
  if (token) return <VerifyToken token={token} redirect={redirect} />
  if (verified) return <Verified redirect={redirect} />
  return <CheckInbox redirect={redirect} />
}
