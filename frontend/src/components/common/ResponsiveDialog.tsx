import type { ReactNode } from "react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { useIsMobile } from "@/hooks/useMobile"

export type ResponsiveDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  /** 測試用 id 的前綴：手機為 `<testIdPrefix>-sheet`、桌機為 `<testIdPrefix>-dialog` */
  testIdPrefix: string
  children: ReactNode
}

/**
 * 表單對話框的外框：手機（< 768px）用底部 Sheet、桌機用 Dialog（S18、S20）。
 * 關閉只用右上角的關閉鈕、Esc 或點遮罩；送出中不能關閉由呼叫端在 `onOpenChange` 擋下。
 */
export function ResponsiveDialog({
  open,
  onOpenChange,
  title,
  description,
  testIdPrefix,
  children,
}: ResponsiveDialogProps) {
  const isMobile = useIsMobile()
  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="bottom"
          className="max-h-[90dvh] overflow-y-auto"
          data-testid={`${testIdPrefix}-sheet`}
        >
          <SheetHeader>
            <SheetTitle>{title}</SheetTitle>
            <SheetDescription>{description}</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-4">{children}</div>
        </SheetContent>
      </Sheet>
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={`${testIdPrefix}-dialog`}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}
