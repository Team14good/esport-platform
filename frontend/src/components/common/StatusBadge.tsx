import { cn } from "@/lib/utils"

/** 狀態徽章的色調；各狀態用哪個 tone 見 DESIGN.md〈Status badge〉對照表。 */
export type StatusTone =
  | "live"
  | "appeal"
  | "confirmed"
  | "waitlist"
  | "eliminated"
  | "brand"
  | "destructive"
  | "muted"

// 文字為該色、底色同色 15%、外框同色 38%；寫成完整 class 名稱，Tailwind 才掃描得到
const TONE_CLASSES: Record<StatusTone, string> = {
  live: "text-status-live bg-status-live/15 border-status-live/38",
  appeal: "text-status-appeal bg-status-appeal/15 border-status-appeal/38",
  confirmed:
    "text-status-confirmed bg-status-confirmed/15 border-status-confirmed/38",
  waitlist:
    "text-status-waitlist bg-status-waitlist/15 border-status-waitlist/38",
  eliminated:
    "text-status-eliminated bg-status-eliminated/15 border-status-eliminated/38",
  brand: "text-brand bg-brand/15 border-brand/38",
  destructive: "text-destructive bg-destructive/15 border-destructive/38",
  muted:
    "text-muted-foreground bg-muted-foreground/15 border-muted-foreground/38",
}

type StatusBadgeProps = {
  tone: StatusTone
  /** 「進行中」「申訴中」這類正在發生的狀態：文字前加 6px 脈動圓點 */
  pulse?: boolean
  /** 狀態文字：徽章永遠帶文字，顏色只是輔助 */
  children: string
  className?: string
}

/** 全站共用的狀態徽章：藥丸形、永遠帶文字，色調依狀態對照表。 */
export function StatusBadge({
  tone,
  pulse = false,
  children,
  className,
}: StatusBadgeProps) {
  return (
    <span
      data-slot="status-badge"
      data-tone={tone}
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-label",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {pulse && (
        <span
          aria-hidden="true"
          data-slot="status-badge-pulse"
          className="size-1.5 shrink-0 animate-pulse rounded-full bg-current motion-reduce:animate-none"
        />
      )}
      {children}
    </span>
  )
}
