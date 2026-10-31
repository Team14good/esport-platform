import { cn } from "@/lib/utils"

type BracketMarkTagProps = {
  /** 取消資格用 destructive，其餘（輪空、棄權）用預設的 muted-foreground */
  tone?: "default" | "destructive"
  children: string
}

/** Bracket mark tag：貼在隊伍列右側的小標記，1px currentColor 外框、rounded-xs、caption 字級。 */
export function BracketMarkTag({
  tone = "default",
  children,
}: BracketMarkTagProps) {
  return (
    <span
      data-slot="bracket-mark-tag"
      data-tone={tone}
      className={cn(
        // 淘汰列的名稱有刪除線，標記本身不跟著劃線
        "shrink-0 whitespace-nowrap rounded-xs border border-current px-1 text-caption leading-4 no-underline",
        tone === "destructive" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {children}
    </span>
  )
}
