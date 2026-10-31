import { Alert, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

// 「最後更新」以 Asia/Taipei 顯示到秒（EXPERIENCE.md：所有時間以台北時間顯示、不標時區）
const clockFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Taipei",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
})

/** 台北時間的「HH:mm:ss」 */
export function formatClockWithSeconds(date: Date): string {
  const parts: Record<string, string> = {}
  for (const part of clockFormatter.formatToParts(date))
    parts[part.type] = part.value
  return `${parts.hour}:${parts.minute}:${parts.second}`
}

type ConnectionLostBannerProps = {
  /** 最後一次成功取得資料的時間；從未成功時不寫「最後更新」 */
  lastUpdatedAt: Date | null
  className?: string
}

/** 輪詢連續失敗時的頁頂橫幅（DESIGN.md〈Page banner〉default variant）；恢復後由呼叫端移除。 */
export function ConnectionLostBanner({
  lastUpdatedAt,
  className,
}: ConnectionLostBannerProps) {
  const text = lastUpdatedAt
    ? `連線中斷，正在重試 · 最後更新 ${formatClockWithSeconds(lastUpdatedAt)}`
    : "連線中斷，正在重試"
  return (
    <Alert
      data-slot="connection-lost-banner"
      className={cn("rounded-md", className)}
    >
      <AlertTitle className="line-clamp-none font-normal">{text}</AlertTitle>
    </Alert>
  )
}
