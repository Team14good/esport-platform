import { ChevronRightIcon } from "lucide-react"

import { HrefLink } from "@/components/common/HrefLink"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { cn } from "@/lib/utils"
import { setLastIdentity, useCurrentIdentity, useIdentities } from "./auth"
import { identityIcon } from "./identity-icons"

/** S11 身分選擇：列出此帳號擁有的身分卡，各導向該身分首頁並記住為上次使用的身分。 */
export function IdentityPicker() {
  const identities = useIdentities()
  const current = useCurrentIdentity()

  return (
    <section className="mx-auto flex w-full max-w-xl flex-col gap-6 py-8 sm:py-12">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg">選擇身分</h1>
        <p className="text-body text-muted-foreground">
          切換身分只改變導覽與首頁；之後也能從頂欄右側的身分切換器切換。
        </p>
      </div>
      {identities.isPending ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <span className="sr-only">載入中</span>
        </div>
      ) : identities.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(identities.error))}
          </p>
          <Button variant="outline" onClick={() => identities.refetch()}>
            重新載入
          </Button>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {identities.data.map((identity) => {
            const Icon = identityIcon(identity.key)
            const isCurrent = identity.key === current?.key
            return (
              <li key={identity.key}>
                <HrefLink
                  href={identity.home_path}
                  aria-current={isCurrent ? "true" : undefined}
                  onClick={() => setLastIdentity(identity.key)}
                  className={cn(
                    "flex min-h-16 items-center gap-3 rounded-lg border border-l-2 bg-card px-4 py-3 outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50",
                    isCurrent && "border-l-brand",
                  )}
                >
                  <Icon aria-hidden="true" className="size-5 text-primary" />
                  <span className="flex-1 text-label">{identity.label}</span>
                  <ChevronRightIcon
                    aria-hidden="true"
                    className="size-4 text-muted-foreground"
                  />
                </HrefLink>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
