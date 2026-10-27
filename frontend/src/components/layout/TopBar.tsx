import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import { useCurrentIdentity, useIsSignedIn } from "@/features/identity/auth"
import { IdentitySwitcher } from "./IdentitySwitcher"
import { Logo } from "./Logo"
import { MobileMenu } from "./MobileMenu"
import { ThemeToggle } from "./ThemeToggle"

/** 所有頁面共用的頂欄：未登入時有「登入」「註冊」，登入後換成身分切換器。 */
export function TopBar() {
  const signedIn = useIsSignedIn()
  const currentIdentity = useCurrentIdentity()

  return (
    <header className="sticky top-0 z-40 border-b bg-card/85 backdrop-blur-sm">
      <div className="mx-auto flex h-14 w-full max-w-content-max items-center gap-4 px-gutter-mobile sm:gap-6 sm:px-gutter-desktop">
        <Logo homePath={signedIn ? currentIdentity?.home_path : undefined} />
        <nav aria-label="主要導覽" className="hidden h-full sm:flex">
          <Link
            to="/"
            activeOptions={{ exact: true }}
            className="flex h-full items-center border-b-2 border-transparent text-label text-muted-foreground transition-colors hover:text-foreground data-[status=active]:border-primary data-[status=active]:text-foreground"
          >
            賽事
          </Link>
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-1 sm:gap-2">
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>
          {signedIn ? (
            <IdentitySwitcher />
          ) : (
            <>
              <Button asChild variant="ghost" className="h-touch-target">
                <Link to="/login">登入</Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="hidden sm:inline-flex"
              >
                <Link to="/signup">註冊</Link>
              </Button>
            </>
          )}
          <MobileMenu signedIn={signedIn} />
        </div>
      </div>
    </header>
  )
}
