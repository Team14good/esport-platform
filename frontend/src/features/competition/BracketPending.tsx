import type { ReactNode } from "react"

import { EmptyState } from "@/components/common/EmptyState"

export const BRACKET_PENDING_TEXT = "報名截止後抽籤，對戰表會出現在這裡。"

type BracketPendingProps = {
  /** 報名截止倒數（Countdown 屬於 Epic 2，由呼叫端傳入；第二階段接上） */
  countdown?: ReactNode
  className?: string
}

/** S3 尚未抽籤：空狀態＋報名截止倒數插槽。 */
export function BracketPending({ countdown, className }: BracketPendingProps) {
  return (
    <EmptyState
      title={BRACKET_PENDING_TEXT}
      // 倒數可能是區塊元素，不放進 description 的 <p>
      action={countdown}
      className={className}
    />
  )
}
