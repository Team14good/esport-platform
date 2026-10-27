import { useRouter } from "@tanstack/react-router"
import {
  ChevronDownIcon,
  LayoutGridIcon,
  LogOutIcon,
  UserRoundCogIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useCurrentAccount,
  useCurrentIdentity,
  useIdentities,
  useLogout,
  useSwitchIdentity,
} from "@/features/identity/auth"
import { identityIcon } from "@/features/identity/identity-icons"
import { cn } from "@/lib/utils"

/**
 * 頂欄右側的身分切換器（`DropdownMenu`）：列出後端給的身分，目前身分以 2px brand 左條
 * 標示；另有「全部身分」（S11），底部「帳號資料」「登出」。`< sm` 時 trigger 只顯示圖示。
 */
export function IdentitySwitcher() {
  const router = useRouter()
  const account = useCurrentAccount()
  const identities = useIdentities()
  const current = useCurrentIdentity()
  const switchIdentity = useSwitchIdentity()
  const logout = useLogout()
  const CurrentIcon = identityIcon(current?.key)

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          aria-label={
            current ? `切換身分（目前：${current.label}）` : "切換身分"
          }
          className="h-touch-target min-w-touch-target gap-2 rounded-md border-border bg-card px-2 sm:px-3 dark:bg-card"
        >
          <CurrentIcon aria-hidden="true" />
          {current ? (
            <span className="hidden max-w-32 truncate sm:inline">
              {current.label}
            </span>
          ) : (
            <Skeleton className="hidden h-4 w-16 sm:block" />
          )}
          <ChevronDownIcon
            aria-hidden="true"
            className="hidden opacity-60 sm:block"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-[min(16rem,calc(100vw-2rem))]"
      >
        <DropdownMenuLabel className="flex min-w-0 flex-col gap-0.5">
          {account.data ? (
            <>
              <span className="truncate">{account.data.display_name}</span>
              <span className="truncate font-normal text-caption text-muted-foreground">
                {account.data.email}
              </span>
            </>
          ) : (
            <Skeleton className="h-4 w-24" />
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup aria-label="身分">
          {identities.isPending && (
            <div className="px-2 py-1.5">
              <Skeleton className="h-4 w-28" />
            </div>
          )}
          {identities.data?.map((identity) => {
            const Icon = identityIcon(identity.key)
            const isCurrent = identity.key === current?.key
            return (
              <DropdownMenuItem
                key={identity.key}
                aria-current={isCurrent ? "true" : undefined}
                data-current={isCurrent ? "" : undefined}
                className={cn(
                  "rounded-l-none border-l-2 border-transparent",
                  isCurrent && "border-brand font-medium",
                )}
                onSelect={() => switchIdentity(identity)}
              >
                <Icon aria-hidden="true" />
                {identity.label}
              </DropdownMenuItem>
            )
          })}
          <DropdownMenuItem
            className="border-l-2 border-transparent"
            onSelect={() => router.navigate({ to: "/me" })}
          >
            <LayoutGridIcon aria-hidden="true" />
            全部身分
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.navigate({ to: "/account" })}>
          <UserRoundCogIcon aria-hidden="true" />
          帳號資料
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={logout}>
          <LogOutIcon aria-hidden="true" />
          登出
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
