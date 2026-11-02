import { Link, type LinkOptions } from "@tanstack/react-router"
import { type LucideIcon, MenuIcon } from "lucide-react"
import { type ReactNode, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

export type BackofficeNavItem = {
  to: LinkOptions["to"]
  label: string
  icon?: LucideIcon
}

type BackofficeLayoutProps = {
  /** 後台名稱，例如「平台管理」「主辦方後台」；也是側欄導覽的名稱 */
  title: string
  /** 側欄第一層項目，由呼叫端傳入（平台管理後台、主辦方後台共用這個版面） */
  items: BackofficeNavItem[]
  children: ReactNode
}

// active：左側 2px primary 條＋sidebar-accent 底、文字 foreground（DESIGN.md〈Sidebar nav〉）
const NAV_ITEM_CLASS =
  "flex h-touch-target items-center gap-2 rounded-md border-l-2 border-transparent px-3 text-label text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground data-[status=active]:border-primary data-[status=active]:bg-sidebar-accent data-[status=active]:text-foreground"

function BackofficeNav({
  title,
  items,
  onNavigate,
}: {
  title: string
  items: BackofficeNavItem[]
  onNavigate?: () => void
}) {
  return (
    <nav aria-label={title}>
      <ul className="flex flex-col gap-1">
        {items.map((item) => {
          const Icon = item.icon
          return (
            <li key={item.label}>
              <Link
                to={item.to}
                className={NAV_ITEM_CLASS}
                onClick={onNavigate}
              >
                {Icon && (
                  <Icon aria-hidden="true" className="size-4 shrink-0" />
                )}
                <span className="truncate">{item.label}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

/**
 * 後台的側欄版面（平台管理後台、主辦方後台共用）：`≥ lg` 左側 240px 側欄；
 * `< lg` 側欄收進 `Sheet`，從內容區頂端的選單鈕開啟，選擇項目後自動關閉。
 */
export function BackofficeLayout({
  title,
  items,
  children,
}: BackofficeLayoutProps) {
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:gap-8">
      <aside
        data-slot="backoffice-sidebar"
        className="hidden w-sidebar-width shrink-0 self-start rounded-lg border bg-sidebar p-2 text-sidebar-foreground lg:block"
      >
        <p className="px-3 py-2 text-caption text-muted-foreground">{title}</p>
        <BackofficeNav title={title} items={items} />
      </aside>
      <div className="flex items-center gap-2 lg:hidden">
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <Button
              variant="outline"
              className="h-touch-target"
              aria-label={`開啟${title}選單`}
            >
              <MenuIcon aria-hidden="true" />
              {title}
            </Button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-sidebar-width gap-2 bg-sidebar px-2 pb-6 text-sidebar-foreground"
          >
            <SheetHeader className="px-3">
              <SheetTitle>{title}</SheetTitle>
              <SheetDescription className="sr-only">
                {title}的功能選單
              </SheetDescription>
            </SheetHeader>
            <BackofficeNav
              title={title}
              items={items}
              onNavigate={() => setSheetOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  )
}
