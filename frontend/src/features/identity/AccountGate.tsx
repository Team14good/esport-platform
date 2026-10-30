import type { ReactNode } from "react"

import type { AccountRead } from "@/client"
import { ErrorPage, RouteErrorPage } from "@/components/layout/ErrorPage"
import { Skeleton } from "@/components/ui/skeleton"
import { useCurrentAccount } from "./auth"

/**
 * 只給特定帳號看的頁面（平台管理後台、主辦方後台）：帳號不符合 `allow` 時顯示 S38 的 403。
 * 這只決定畫面；權限一律由伺服器的 API 檢查。登入檢查在路由的 `requireSignedIn`。
 */
export function AccountGate({
  allow,
  children,
}: {
  allow: (account: AccountRead) => boolean
  children: ReactNode
}) {
  const account = useCurrentAccount()

  if (account.isPending) {
    return (
      <div role="status" aria-busy="true" className="flex flex-col gap-4 py-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <span className="sr-only">載入中</span>
      </div>
    )
  }
  if (account.isError) return <RouteErrorPage error={account.error} />
  if (!allow(account.data)) return <ErrorPage status={403} />
  return children
}
