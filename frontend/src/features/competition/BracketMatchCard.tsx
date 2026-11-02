import { Link } from "@tanstack/react-router"
import type { CSSProperties } from "react"

import { StatusBadge } from "@/components/common/StatusBadge"
import { cn } from "@/lib/utils"
import { BracketMarkTag } from "./BracketMarkTag"
import type { BracketSide, PublicMatch } from "./bracket-types"
import {
  hasScore,
  MATCH_STATUS_BADGES,
  matchLabel,
  type SideView,
  sideView,
} from "./match-status"
import { formatMatchDateTime } from "./match-time"

type RowView = SideView & { score: string }

function rowView(match: PublicMatch, side: BracketSide): RowView {
  const wins = side === "a" ? match.wins_a : match.wins_b
  return {
    ...sideView(match, side),
    score: hasScore(match) ? String(wins) : "",
  }
}

function sideName(view: SideView) {
  return view.marks.length > 0
    ? `${view.name}（${view.marks.map((mark) => mark.label).join("、")}）`
    : view.name
}

/**
 * 整張卡是連結時的可及名稱：連結內的 article 若有 aria-label 會取代卡片內容，
 * 所以把畫面上的標頭、隊名、標記、比分與狀態組成一句，例如「M3，清大 Hydra 對 交大 Nova，2 比 1，已確認」。
 */
export function matchCardAccessibleName(match: PublicMatch): string {
  const scheduled = match.status === "scheduled"
  return [
    matchLabel(match),
    scheduled ? formatMatchDateTime(match.scheduled_at) : "",
    `${sideName(sideView(match, "a"))} 對 ${sideName(sideView(match, "b"))}`,
    hasScore(match) ? `${match.wins_a} 比 ${match.wins_b}` : "",
    MATCH_STATUS_BADGES[match.status].label,
  ]
    .filter(Boolean)
    .join("，")
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
  /** 有提供時整張卡是連到該場 S4 的連結 */
  matchHref?: (matchId: string) => string
  className?: string
  style?: CSSProperties
}

/** Bracket match card：上方 overline 標頭＋兩列隊伍，各狀態樣式見 DESIGN.md〈Components〉。 */
export function BracketMatchCard({
  match,
  flash = false,
  matchHref,
  className,
  style,
}: BracketMatchCardProps) {
  const label = matchLabel(match)
  const scheduled = match.status === "scheduled"
  const time = scheduled ? formatMatchDateTime(match.scheduled_at) : ""
  const badge = scheduled ? null : MATCH_STATUS_BADGES[match.status]
  const href = matchHref?.(match.id)

  const card = (
    <article
      // 包成連結時名稱改由外層連結提供，否則 article 的名稱會蓋掉卡片內容
      aria-label={href === undefined ? label : undefined}
      data-slot="bracket-match-card"
      data-match-id={match.id}
      data-status={match.status}
      data-flash={flash || undefined}
      className={cn(
        "relative w-bracket-column-min rounded-md border bg-background",
        match.status === "live" &&
          "border-[color-mix(in_oklab,var(--status-live)_55%,var(--border))] shadow-[0_0_0_3px_color-mix(in_oklab,var(--status-live)_12%,transparent)]",
        href !== undefined &&
          "transition-colors group-hover:border-muted-foreground/60",
        flash && "update-flash",
        href === undefined && className,
      )}
      style={href === undefined ? style : undefined}
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

  if (href === undefined) return card
  // 整張卡可點：定位樣式移到外層連結，鍵盤 focus 時外框畫在卡片外
  return (
    <Link
      to={href}
      aria-label={matchCardAccessibleName(match)}
      data-slot="bracket-match-link"
      className={cn(
        "group block w-bracket-column-min rounded-md focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2",
        className,
      )}
      style={style}
    >
      {card}
    </Link>
  )
}
