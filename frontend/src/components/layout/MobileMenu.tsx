import { Link } from "@tanstack/react-router"
import { MenuIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { ThemeToggle } from "./ThemeToggle"

/** < sm 的選單：Sheet 內有「賽事」與主題切換；未登入時另有「註冊」。 */
export function MobileMenu({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label="開啟選單"
          className="size-touch-target sm:hidden"
        >
          <MenuIcon aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="gap-2 px-4 pb-6">
        <SheetHeader className="px-0">
          <SheetTitle>選單</SheetTitle>
        </SheetHeader>
        <nav aria-label="主要導覽" className="flex flex-col gap-1">
          <SheetClose asChild>
            <Link
              to="/"
              activeOptions={{ exact: true }}
              className="flex h-touch-target items-center border-l-2 border-transparent px-3 text-label text-muted-foreground hover:text-foreground data-[status=active]:border-primary data-[status=active]:text-foreground"
            >
              賽事
            </Link>
          </SheetClose>
        </nav>
        <ThemeToggle showLabel />
        {!signedIn && (
          <SheetClose asChild>
            <Button asChild variant="outline" className="mt-2 h-touch-target">
              <Link to="/signup">註冊</Link>
            </Button>
          </SheetClose>
        )}
      </SheetContent>
    </Sheet>
  )
}
