import { Countdown, type CountdownVariant } from "@/components/common/Countdown"

// 申訴處理期限倒數（6.3；EXPERIENCE.md〈倒數與時間〉「申訴處理期限」）：S27 待處理清單與 S32 共用。

export const HANDLING_DEADLINE_LABEL = "處理期限"
/** 過了處理期限：系統不會自動處理申訴，所以不寫「系統處理中」、也不重抓 */
export const HANDLING_OVERDUE_TEXT = "已超過處理期限"

/** 最後 1 小時改用 destructive（對應 worker 的逾期提醒） */
const LAST_HOUR_MS = 60 * 60 * 1000

/** 剩餘超過 1 小時為 muted，最後 1 小時為 destructive。 */
export function handlingDeadlineVariant(remainingMs: number): CountdownVariant {
  return remainingMs > LAST_HOUR_MS ? "muted" : "destructive"
}

export function HandlingDeadlineCountdown({
  deadline,
  label = HANDLING_DEADLINE_LABEL,
  className,
}: {
  deadline: string
  /** 左側說明；S32 的欄名已是「處理期限」，改寫「剩餘時間」 */
  label?: string
  className?: string
}) {
  return (
    <Countdown
      label={label}
      deadline={deadline}
      variant={handlingDeadlineVariant}
      expiredText={HANDLING_OVERDUE_TEXT}
      expiredVariant="destructive"
      className={className}
    />
  )
}
