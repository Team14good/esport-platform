import { useMemo } from "react"

import { cn } from "@/lib/utils"
import { BracketMatchCard } from "./BracketMatchCard"
import { layoutBracket } from "./bracket-layout"
import type { PublicBracket } from "./bracket-types"

const NO_CHANGES: ReadonlySet<string> = new Set()

// 同一張卡連續兩次輪詢都有變動時，class 沒有改變，動畫不會重播。
// 每一份 changedMatchIds（每次資料變動都是新的 Set）配一個序號，變動的卡以「id:序號」當 key 重新掛載。
const flashGenerations = new WeakMap<ReadonlySet<string>, number>()
let nextFlashGeneration = 0

function flashGeneration(changed: ReadonlySet<string>): number {
  let generation = flashGenerations.get(changed)
  if (generation === undefined) {
    nextFlashGeneration += 1
    generation = nextFlashGeneration
    flashGenerations.set(changed, generation)
  }
  return generation
}

type BracketTreeProps = {
  bracket: PublicBracket
  /** 輪詢時有變動的場次，各 flash 一次（useBracketPolling 的 changedMatchIds） */
  changedMatchIds?: ReadonlySet<string>
  /** 有提供時每張場次卡整張可點，連到該場 S4 */
  matchHref?: (matchId: string) => string
  className?: string
}

/**
 * 視覺化對戰樹：每輪一欄由左到右，欄頭為輪次名，SVG 畫直角連接線。
 * 只有這個容器可以橫向捲動、不縮放；重抓資料時 DOM 不重建，捲動位置保留。
 */
export function BracketTree({
  bracket,
  changedMatchIds = NO_CHANGES,
  matchHref,
  className,
}: BracketTreeProps) {
  const layout = useMemo(() => layoutBracket(bracket), [bracket])
  const generation = flashGeneration(changedMatchIds)

  return (
    <div
      data-slot="bracket-tree"
      className={cn(
        "max-w-full overflow-x-auto overscroll-x-contain",
        className,
      )}
    >
      {/* 4px 內距：讓進行中卡片的 3px 光環不被捲動容器裁掉 */}
      <div className="w-max p-1">
        <div
          data-slot="bracket-round-heads"
          className="relative mb-1 h-5"
          style={{ width: layout.width }}
        >
          {layout.columns.map((column) => (
            <span
              key={column.roundNo}
              className="absolute top-0 w-bracket-column-min text-muted-foreground text-overline leading-5"
              style={{ left: column.x }}
            >
              {column.name}
            </span>
          ))}
        </div>
        <div
          data-slot="bracket-canvas"
          className="relative"
          style={{ width: layout.width, height: layout.height }}
        >
          <svg
            aria-hidden="true"
            className="absolute top-0 left-0 overflow-visible"
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
          >
            <path
              data-slot="bracket-connectors"
              d={layout.connectors.map((c) => c.d).join(" ")}
              fill="none"
              stroke="color-mix(in oklab, var(--muted-foreground) 55%, transparent)"
              strokeWidth={1.5}
            />
          </svg>
          {layout.cards.map(({ match, x, y }) => {
            const flash = changedMatchIds.has(match.id)
            return (
              <BracketMatchCard
                key={flash ? `${match.id}:${generation}` : match.id}
                match={match}
                flash={flash}
                matchHref={matchHref}
                className="absolute"
                style={{ left: x, top: y }}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}
