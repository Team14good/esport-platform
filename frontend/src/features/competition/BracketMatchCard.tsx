import type { CSSProperties } from "react"

import { StatusBadge, type StatusTone } from "@/components/common/StatusBadge"
import { cn } from "@/lib/utils"
import { BracketMarkTag } from "./BracketMarkTag"
import type {
  BracketSide,
  MatchOutcome,
  MatchStatus,
  PublicMatch,
} from "./bracket-types"
import { formatMatchDateTime } from "./match-time"

const THIRD_PLACE_LABEL = "季軍賽"
const EMPTY_TEAM_TEXT = "—"

/** 待開打以外的狀態在標頭接的徽章（DESIGN.md〈Status badge〉場次欄） */
const STATUS_BADGES: Record<
  Exclude<MatchStatus, "scheduled">,
  { tone: StatusTone; label: string; pulse?: boolean }
> = {
  live: { tone: "live", label: "進行中", pulse: true },
  appeal_window: { tone: "appeal", label: "申訴期" },
  appealed: { tone: "appeal", label: "申訴中", pulse: true },
  confirmed: { tone: "confirmed", label: "已確認" },
  voided: { tone: "muted", label: "已取消" },
}

/** 顯示比分的狀態；待開打留空、已取消沒有比分 */
const SCORED_STATUSES: ReadonlySet<MatchStatus> = new Set([
  "live",
  "appeal_window",
  "appealed",
  "confirmed",
])

/** 沒有實際比賽的結果：兩列都不顯示比分 */
const UNSCORED_OUTCOMES: ReadonlySet<MatchOutcome> = new Set([
  "forfeit",
  "double_forfeit",
  "disqualified",
  "walkover",
])

type RowMark = { label: string; tone: "default" | "destructive" }

type RowView = {
  name: string
  /** 隊伍未定（待定列或確定沒有隊伍）：muted-foreground */
  pending: boolean
  marks: RowMark[]
  score: string
  winner: boolean
  eliminated: boolean
}

function rowView(match: PublicMatch, side: BracketSide): RowView {
  const team = side === "a" ? match.team_a : match.team_b
  const source = side === "a" ? match.source_a : match.source_b
  const wins = side === "a" ? match.wins_a : match.wins_b
  const { outcome, winner_id: winnerId, status } = match

  const marks: RowMark[] = []
  // 由輪空進入本輪的一方，或確定不會有隊伍的位置（沒有隊伍也沒有來源）
  if (match.bye_side === side || (team === null && source === null)) {
    marks.push({ label: "輪空", tone: "default" })
  }
  const isLoser = team !== null && winnerId !== null && team.id !== winnerId
  if (outcome === "double_forfeit" || (outcome === "forfeit" && isLoser)) {
    marks.push({ label: "棄權", tone: "default" })
  }
  if (outcome === "disqualified" && isLoser) {
    marks.push({ label: "取消資格", tone: "destructive" })
  }

  const showScore =
    SCORED_STATUSES.has(status) &&
    (outcome === null || !UNSCORED_OUTCOMES.has(outcome))

  // 勝隊與淘汰列樣式只在「已確認」套用：申訴期內結果未確認、不顯示晉級
  const confirmed = status === "confirmed"
  const winner = confirmed && team !== null && team.id === winnerId
  const eliminated =
    confirmed && team !== null && (outcome === "double_forfeit" || isLoser)

  return {
    name: team?.name ?? source ?? EMPTY_TEAM_TEXT,
    pending: team === null || status === "voided",
    marks,
    score: showScore ? String(wins) : "",
    winner,
    eliminated,
  }
}

function TeamRow({ view, side }: { view: RowView; side: BracketSide }) {
  return (
    <div
      data-slot="bracket-team-row"
      data-side={side}
      data-winner={view.winner || undefined}
      data-eliminated={view.eliminated || undefined}
      data-pending={view.pending || undefined}
      className={cn(
        "flex h-bracket-row-height items-center gap-2 px-2.5 text-bracket-row",
        side === "b" && "border-t",
        view.pending && "text-muted-foreground",
        view.eliminated && "text-status-eliminated",
      )}
    >
      <span
        data-slot="bracket-team-name"
        title={view.name}
        className={cn(
          "min-w-0 flex-1 truncate",
          view.winner && "font-bold",
          view.eliminated && "line-through decoration-1",
        )}
      >
        {view.name}
      </span>
      {view.marks.map((mark) => (
        <BracketMarkTag key={mark.label} tone={mark.tone}>
          {mark.label}
        </BracketMarkTag>
      ))}
      <span
        data-slot="bracket-score"
        className={cn(
          "min-w-3 text-right font-bold font-mono tabular-nums",
          view.winner && "text-primary",
        )}
      >
        {view.score}
      </span>
    </div>
  )
}

type BracketMatchCardProps = {
  match: PublicMatch
  /** 輪詢時這張卡有變動：底色以 muted 淡入淡出一次 */
  flash?: boolean
  className?: string
  style?: CSSProperties
}

/** Bracket match card：上方 overline 標頭＋兩列隊伍，各狀態樣式見 DESIGN.md〈Components〉。 */
export function BracketMatchCard({
  match,
  flash = false,
  className,
  style,
}: BracketMatchCardProps) {
  const label = match.is_third_place ? THIRD_PLACE_LABEL : match.code
  const scheduled = match.status === "scheduled"
  const time = scheduled ? formatMatchDateTime(match.scheduled_at) : ""
  const badge =
    match.status === "scheduled" ? null : STATUS_BADGES[match.status]

  return (
    <article
      aria-label={label}
      data-slot="bracket-match-card"
      data-match-id={match.id}
      data-status={match.status}
      data-flash={flash || undefined}
      className={cn(
        "relative w-bracket-column-min rounded-md border bg-background",
        match.status === "live" &&
          "border-[color-mix(in_oklab,var(--status-live)_55%,var(--border))] shadow-[0_0_0_3px_color-mix(in_oklab,var(--status-live)_12%,transparent)]",
        flash && "update-flash",
        className,
      )}
      style={style}
    >
      <div
        data-slot="bracket-match-header"
        className="absolute inset-x-0 -top-4 flex h-3.5 items-center justify-between gap-1.5 whitespace-nowrap text-muted-foreground text-overline leading-3.5"
      >
        <span className="truncate">{time ? `${label} · ${time}` : label}</span>
        {badge && (
          <StatusBadge
            tone={badge.tone}
            pulse={badge.pulse}
            className="gap-[5px] px-[7px] py-0 text-overline leading-3.5"
          >
            {badge.label}
          </StatusBadge>
        )}
      </div>
      <TeamRow view={rowView(match, "a")} side="a" />
      <TeamRow view={rowView(match, "b")} side="b" />
    </article>
  )
}
