import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import { Logo } from "./Logo"
import { MobileMenu } from "./MobileMenu"
import { ThemeToggle } from "./ThemeToggle"

// 「登入」「註冊」的頁面在 Story 1.4、1.3 才建立，路由還不存在，
// 所以先用一般連結；在那之前點了會看到 S38 404。

/** 所有頁面共用的頂欄（未登入版）。 */
export function TopBar() {
  return (
    <header className="sticky top-0 z-40 border-b bg-card/85 backdrop-blur-sm">
      <div className="mx-auto flex h-14 w-full max-w-content-max items-center gap-4 px-gutter-mobile sm:gap-6 sm:px-gutter-desktop">
        <Logo />
        <nav aria-label="主要導覽" className="hidden h-full sm:flex">
          <Link
            to="/"
            activeOptions={{ exact: true }}
            className="flex h-full items-center border-b-2 border-transparent text-label text-muted-foreground transition-colors hover:text-foreground data-[status=active]:border-primary data-[status=active]:text-foreground"
          >
            賽事
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>
          <Button asChild variant="ghost" className="h-touch-target">
            <a href="/login">登入</a>
          </Button>
          <Button asChild variant="outline" className="hidden sm:inline-flex">
            <a href="/signup">註冊</a>
          </Button>
          <MobileMenu />
        </div>
      </div>
    </header>
  )
}
