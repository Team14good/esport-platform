import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type EmptyStateProps = {
  /** 一句事實，例如「目前沒有待審核的主辦方申請。」 */
  title: string
  /** 選填的說明 */
  description?: ReactNode
  /** 最多一個主要動作 */
  action?: ReactNode
  className?: string
}

/** 空狀態：置中的 L2 標誌本體（muted-foreground 單色、48px）＋一句話＋說明＋最多一個主要按鈕。 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        "flex flex-col items-center gap-3 px-4 py-12 text-center",
        className,
      )}
    >
      {/* 以標誌本體當遮罩填 muted-foreground，深淺色都是單色 */}
      <span
        aria-hidden="true"
        className="size-12 bg-muted-foreground"
        style={{
          maskImage: "url(/brand/flow-logo-L2-mark.svg)",
          maskSize: "contain",
          maskRepeat: "no-repeat",
          maskPosition: "center",
        }}
      />
      <p className="text-heading-md">{title}</p>
      {description && (
        <p className="text-body text-muted-foreground">{description}</p>
      )}
      {action}
    </div>
  )
}
