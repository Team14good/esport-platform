import type { ReactNode } from "react"

import { cn } from "@/lib/utils"
import { MatchAppealWindow } from "./MatchAppealWindow"
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
  /** 申訴期區塊的倒數插槽：B 的 Countdown（`appeal` 變體）做好後由 S4 路由傳入 */
  appealCountdown?: ReactNode
  className?: string
}

/**
 * S4 觀眾檢視（EXPERIENCE.md〈場次頁（S4）〉）：
 * - `≥ lg` 兩欄：左欄 Score display、各局列表；右欄申訴期（最上方）、同輪其他場次（最下方）。
 * - `< lg` 單欄：頁首、Score display、申訴期、各局列表、同輪其他場次。
 *
 * 每個區塊只渲染一次：`< lg` 時兩欄的容器是 `display: contents`，四個區塊直接成為外層 grid 的項目，
 * 再用 `order` 把申訴期排到 Score display 與各局列表之間；`≥ lg` 時容器恢復成兩欄。
 */
export function MatchSpectatorView({
  detail,
  changed = false,
  appealCountdown,
  className,
}: MatchSpectatorViewProps) {
  return (
    <div
      data-slot="match-spectator-view"
      className={cn("flex min-w-0 flex-col gap-5", className)}
    >
      <MatchHeader detail={detail} />
      <div className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_var(--spacing-match-aside-width)] lg:gap-match-column-gap">
        <div
          data-slot="match-main"
          className="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4"
        >
          <MatchScoreDisplay
            key={changed ? `flash:${flashGeneration(detail)}` : "static"}
            detail={detail}
            flash={changed}
            className="min-w-0 max-lg:order-1"
          />
          <MatchGameList detail={detail} className="min-w-0 max-lg:order-3" />
        </div>
        <aside
          data-slot="match-aside"
          className="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4 lg:empty:hidden"
        >
          <MatchAppealWindow
            detail={detail}
            countdown={appealCountdown}
            className="min-w-0 max-lg:order-2"
          />
          <SameRoundMatches
            tournamentId={detail.tournament.id}
            matches={detail.same_round}
            className="min-w-0 max-lg:order-4"
          />
        </aside>
      </div>
    </div>
  )
}
