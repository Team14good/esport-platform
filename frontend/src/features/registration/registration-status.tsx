import type { MyTeamCard, RegistrationStatus } from "@/client"
import { cn } from "@/lib/utils"

/** 報名狀態的介面標籤（EXPERIENCE.md〈報名狀態〉）。 */
export const REGISTRATION_STATUS_LABELS: Record<RegistrationStatus, string> = {
  forming: "組隊中",
  pending: "已送出・待分配",
  accepted: "正取",
  waitlisted: "候補",
  rejected: "退回",
  withdrawn: "撤回",
  drawn: "已參賽",
  retired: "退賽",
  disqualified: "取消資格",
}

// DESIGN.md〈Components〉Status badge：文字色＝tone，底色同色 15%、外框同色 38%
const MUTED_TONE =
  "border-muted-foreground/40 bg-muted-foreground/15 text-muted-foreground"
const STATUS_TONES: Record<RegistrationStatus, string> = {
  forming: MUTED_TONE,
  pending: "border-status-appeal/40 bg-status-appeal/15 text-status-appeal",
  accepted:
    "border-status-confirmed/40 bg-status-confirmed/15 text-status-confirmed",
  waitlisted:
    "border-status-waitlist/40 bg-status-waitlist/15 text-status-waitlist",
  rejected: "border-destructive/40 bg-destructive/15 text-destructive",
  withdrawn: MUTED_TONE,
  drawn:
    "border-status-confirmed/40 bg-status-confirmed/15 text-status-confirmed",
  retired: MUTED_TONE,
  disqualified: "border-destructive/40 bg-destructive/15 text-destructive",
}

/** S17、S12 回應裡的候補資訊（Story 3.4），只在候補時有值。 */
export type WaitlistInfo = Pick<
  MyTeamCard,
  | "waitlist_position"
  | "waitlist_reason"
  | "representative_backfill"
  | "waitlist_phase"
>
type WaitlistReason = NonNullable<WaitlistInfo["waitlist_reason"]>
type WaitlistPhase = NonNullable<WaitlistInfo["waitlist_phase"]>

export const WAITLIST_UNRANKED_LABEL = "候補・目前不在遞補順序中"

/** 「候補第 N 位」（EXPERIENCE.md〈固定介面字串〉）。 */
export function waitlistPositionLabel(position: number): string {
  return `候補第 ${position} 位`
}

/** 候補沒有順位的原因；與後端 `allocation.REASON_MESSAGES`、EXPERIENCE.md 逐字相同。 */
export const WAITLIST_REASON_MESSAGES: Record<WaitlistReason, string> = {
  SCHOOL_NOT_ELIGIBLE:
    "先搶期只遞補優先期沒有報名、目前也沒有正取的學校；報名截止後改依平均段位積分排序。",
  LATER_THAN_SCHOOLMATE:
    "先搶期每校只遞補最早送出的一隊，本校已有更早送出的候補。",
  SCHOOL_LIMIT_REACHED:
    "每校最多 2 隊正取：本校正取加上排在前面的本校候補已達 2 隊。",
}

/** 與後端 `allocation.REPRESENTATIVE_BACKFILL_MESSAGE` 逐字相同。 */
export const REPRESENTATIVE_BACKFILL_MESSAGE =
  "本校代表隊退出時，由本校平均段位積分次高的隊伍遞補。"

/** 當下階段的遞補規則說明（EXPERIENCE.md〈固定介面字串〉，Story 3.4 決定）。 */
export const WAITLIST_PHASE_RULES: Record<WaitlistPhase, string> = {
  first_come: "先搶期由優先期沒有報名、目前也沒有正取的學校，依送出先後遞補。",
  after_deadline: "報名截止後依平均段位積分由高到低遞補，每校最多 2 隊正取。",
}

/**
 * 徽章文字：候補時依順位顯示「候補第 N 位」或「候補・目前不在遞補順序中」；
 * 沒有候補資訊（`waitlist` 未提供或階段為 null）時用狀態名。
 */
export function registrationStatusLabel(
  status: RegistrationStatus,
  waitlist?: WaitlistInfo,
): string {
  if (status !== "waitlisted" || !waitlist?.waitlist_phase) {
    return REGISTRATION_STATUS_LABELS[status]
  }
  return waitlist.waitlist_position === null
    ? WAITLIST_UNRANKED_LABEL
    : waitlistPositionLabel(waitlist.waitlist_position)
}

/**
 * 候補徽章下方的說明（`muted`）：沒有順位時的原因（＋代表隊遞補的補充），
 * 以及當下階段的遞補規則說明。不是候補或沒有候補資訊時不顯示。
 */
export function WaitlistDetails({
  status,
  waitlist,
  className,
}: {
  status: RegistrationStatus
  waitlist: WaitlistInfo
  className?: string
}) {
  const phase = waitlist.waitlist_phase
  if (status !== "waitlisted" || !phase) return null
  const lines: string[] = []
  if (waitlist.waitlist_position === null && waitlist.waitlist_reason) {
    lines.push(WAITLIST_REASON_MESSAGES[waitlist.waitlist_reason])
    if (waitlist.representative_backfill) {
      lines.push(REPRESENTATIVE_BACKFILL_MESSAGE)
    }
  }
  lines.push(WAITLIST_PHASE_RULES[phase])
  // 用 span：S12 的卡片整張是連結（行內內容），不能放 div、p
  return (
    <span
      data-slot="waitlist-details"
      className={cn(
        "flex flex-col gap-1 break-words text-caption text-muted-foreground",
        className,
      )}
    >
      {lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </span>
  )
}

/** 報名狀態徽章：永遠帶文字，顏色只是輔助；不可點擊。候補時傳入 `waitlist` 顯示順位。 */
export function RegistrationStatusBadge({
  status,
  waitlist,
  className,
}: {
  status: RegistrationStatus
  waitlist?: WaitlistInfo
  className?: string
}) {
  return (
    <span
      data-slot="status-badge"
      className={cn(
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-label",
        STATUS_TONES[status],
        className,
      )}
    >
      {registrationStatusLabel(status, waitlist)}
    </span>
  )
}
