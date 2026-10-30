import { cn } from "@/lib/utils"
import { MatchGameList } from "./MatchGameList"
import { MatchHeader } from "./MatchHeader"
import { MatchScoreDisplay } from "./MatchScoreDisplay"
import type { PublicMatchDetail } from "./match-types"
import { SameRoundMatches } from "./SameRoundMatches"

// 連續兩次輪詢比分都有變動時，class 沒有改變，動畫不會重播。
// 每一份資料（有變動時一定是新的物件）配一個序號，flash 時以序號當 key 讓 Score display 重新掛載。
const flashGenerations = new WeakMap<PublicMatchDetail, number>()
let nextFlashGeneration = 0

function flashGeneration(detail: PublicMatchDetail): number {
  let generation = flashGenerations.get(detail)
  if (generation === undefined) {
    nextFlashGeneration += 1
    generation = nextFlashGeneration
    flashGenerations.set(detail, generation)
  }
  return generation
}

type MatchSpectatorViewProps = {
  detail: PublicMatchDetail
  /** 輪詢時比分或狀態有變動（useMatchPolling 的 changed）：Score display flash 一次 */
  changed?: boolean
  className?: string
}

/**
 * S4 觀眾檢視：頁首＋`≥ lg` 兩欄（左：Score display、各局列表；右：同輪其他場次）。
 * `< lg` 單欄依序為頁首、Score display、各局列表、同輪其他場次。
 */
export function MatchSpectatorView({
  detail,
  changed = false,
  className,
}: MatchSpectatorViewProps) {
  return (
    <div
      data-slot="match-spectator-view"
      className={cn("flex min-w-0 flex-col gap-5", className)}
    >
      <MatchHeader detail={detail} />
      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_var(--spacing-match-aside-width)] lg:gap-match-column-gap">
        <div data-slot="match-main" className="flex min-w-0 flex-col gap-4">
          <MatchScoreDisplay
            key={changed ? `flash:${flashGeneration(detail)}` : "static"}
            detail={detail}
            flash={changed}
          />
          <MatchGameList detail={detail} />
        </div>
        <aside
          data-slot="match-aside"
          className="flex min-w-0 flex-col gap-4 empty:hidden"
        >
          <SameRoundMatches
            tournamentId={detail.tournament.id}
            matches={detail.same_round}
          />
        </aside>
      </div>
    </div>
  )
}
