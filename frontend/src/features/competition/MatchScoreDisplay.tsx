import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { BracketMarkTag } from "./BracketMarkTag"
import type { BracketSide } from "./bracket-types"
import {
  EMPTY_TEAM_TEXT,
  hasScore,
  type SideView,
  sideView,
} from "./match-status"
import type { PublicMatchDetail } from "./match-types"

function TeamName({ view, side }: { view: SideView; side: BracketSide }) {
  return (
    <div
      data-slot="score-team"
      data-side={side}
      data-winner={view.winner || undefined}
      data-eliminated={view.eliminated || undefined}
      data-pending={view.pending || undefined}
      className={cn(
        // 兩隊隊名都向比分對齊：A 靠右、B 靠左；標記放在外側
        "flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-body-lg",
        side === "a" ? "flex-row-reverse justify-start text-right" : "",
        view.pending && "text-muted-foreground",
        view.eliminated && "text-status-eliminated",
      )}
    >
      <span
        data-slot="score-team-name"
        className={cn("min-w-0 wrap-anywhere", view.winner && "font-bold")}
      >
        {view.name}
      </span>
      {view.marks.map((mark) => (
        <BracketMarkTag key={mark.label} tone={mark.tone}>
          {mark.label}
        </BracketMarkTag>
      ))}
    </div>
  )
}

type MatchScoreDisplayProps = {
  detail: PublicMatchDetail
  /** 輪詢時比分或狀態有變動：底色以 muted 淡入淡出一次 */
  flash?: boolean
  className?: string
}

/**
 * Score display：「隊A 2 : 1 隊B」。比分只計已登錄的局；沒有比分（待開打、棄權、輪空、取消資格、已取消）時中間是「—」。
 * 勝方粗體、敗方 status-eliminated 只在已確認時套用。
 */
export function MatchScoreDisplay({
  detail,
  flash = false,
  className,
}: MatchScoreDisplayProps) {
  const a = sideView(detail, "a")
  const b = sideView(detail, "b")
  const scored = hasScore(detail)
  return (
    <Card
      data-slot="score-display"
      data-flash={flash || undefined}
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 p-4",
        flash && "update-flash",
        className,
      )}
    >
      <TeamName view={a} side="a" />
      {scored ? (
        <span
          data-slot="score"
          className="whitespace-nowrap font-mono text-score tabular-nums"
        >
          <span
            data-slot="score-a"
            className={cn(a.eliminated && "text-status-eliminated")}
          >
            {detail.wins_a}
          </span>
          <span className="mx-1.5 text-muted-foreground">:</span>
          <span
            data-slot="score-b"
            className={cn(b.eliminated && "text-status-eliminated")}
          >
            {detail.wins_b}
          </span>
        </span>
      ) : (
        <span
          data-slot="score"
          className="font-mono text-muted-foreground text-score"
        >
          {EMPTY_TEAM_TEXT}
        </span>
      )}
      <TeamName view={b} side="b" />
    </Card>
  )
}
