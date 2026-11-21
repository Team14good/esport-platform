import {
  type ReactNode,
  type UIEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from "react"
import type { PublicBracket } from "@/client"
import { cn } from "@/lib/utils"
import { BracketMatchCard } from "./BracketMatchCard"
import {
  BRACKET_COLUMN_WIDTH,
  BRACKET_CONNECTOR_WIDTH,
  type BracketLayout,
  bracketColumnX,
  bracketConnectorPath,
  bracketTeamRowCenterY,
  layoutBracket,
} from "./bracket-layout"
import {
  type BracketRowRef,
  type BracketTeamPath,
  bracketTeamPath,
} from "./bracket-search"
import { type BracketSide, disqualifiedLastMatches } from "./match-status"

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

/** 捲動容器的內距（p-1）：讓進行中卡片的 3px 光環不被裁掉 */
const TREE_PADDING = 4

type SearchPaths = {
  /** 實線（已走過的）晉級路徑 */
  solid: string
  /** 通往虛線待定列的那段 */
  dashed: string
}

/** 把晉級路徑的連接線換成 SVG path（列中心到列中心） */
function searchConnectorPaths(
  layout: BracketLayout,
  path: BracketTeamPath,
): SearchPaths {
  const cardY = new Map(layout.cards.map((c) => [c.match.id, c] as const))
  const rowY = ({ matchId, side }: BracketRowRef) => {
    const card = cardY.get(matchId)
    return card === undefined ? undefined : bracketTeamRowCenterY(card.y, side)
  }
  const solid: string[] = []
  const dashed: string[] = []
  for (const connector of path.connectors) {
    const childCard = cardY.get(connector.child.matchId)
    const childY = rowY(connector.child)
    const parentY = rowY(connector.parent)
    if (
      childCard === undefined ||
      childY === undefined ||
      parentY === undefined
    )
      continue
    const d = bracketConnectorPath(childCard.match.round_no, childY, parentY)
    ;(connector.dashed ? dashed : solid).push(d)
  }
  return { solid: solid.join(" "), dashed: dashed.join(" ") }
}

/** 場次 id → 那一方，供場次卡判斷命中列與虛線列 */
function sidesByMatch(
  rows: readonly BracketRowRef[],
): ReadonlyMap<string, BracketSide> {
  return new Map(rows.map((row) => [row.matchId, row.side] as const))
}

/**
 * 讓第 roundNo 輪欄完整露出並帶出下一段連接線的 scrollLeft；
 * 容器比一欄加一段連接線還窄時，以欄的左緣為準。
 */
export function bracketScrollLeftForRound(
  roundNo: number,
  clientWidth: number,
): number {
  const left = bracketColumnX(roundNo) + TREE_PADDING
  const right = left + BRACKET_COLUMN_WIDTH + BRACKET_CONNECTOR_WIDTH
  return Math.max(0, Math.min(left, right - clientWidth))
}

type BracketTreeProps = {
  bracket: PublicBracket
  /** 輪詢時有變動的場次，各 flash 一次（useBracketPolling 的 changedMatchIds） */
  changedMatchIds?: ReadonlySet<string>
  /** 有提供時每張場次卡整張可點，連到該場 S4 */
  matchHref?: (matchId: string) => string
  /** 隊伍搜尋（4.7）目前高亮的隊伍；改變時自動橫向捲到它最遠的一輪 */
  highlightTeamId?: string | null
  /** 固定在視窗頂端的搜尋列（4.7）；有提供時搜尋列與輪次欄頭垂直捲動時固定 */
  toolbar?: ReactNode
  /** 搜尋列下方、不固定的說明（例如零結果） */
  toolbarNote?: ReactNode
  className?: string
}

/**
 * 視覺化對戰樹：每輪一欄由左到右，欄頭為輪次名，SVG 畫直角連接線。
 * 只有 [data-slot=bracket-tree] 可以橫向捲動、不縮放；重抓資料時 DOM 不重建，捲動位置保留。
 * 輪次欄頭在捲動容器之外，隨容器橫向捲動同步位移；有 toolbar 時與搜尋列一起垂直固定（4.7）。
 */
export function BracketTree({
  bracket,
  changedMatchIds = NO_CHANGES,
  matchHref,
  highlightTeamId = null,
  toolbar,
  toolbarNote,
  className,
}: BracketTreeProps) {
  const layout = useMemo(() => layoutBracket(bracket), [bracket])
  // 已取消資格的隊伍只在它出現的最後一張卡加標記（6.5）
  const disqualifiedLast = useMemo(
    () => disqualifiedLastMatches(bracket.matches),
    [bracket],
  )
  const path = useMemo(
    () =>
      highlightTeamId === null
        ? null
        : bracketTeamPath(bracket, highlightTeamId),
    [bracket, highlightTeamId],
  )
  const searchPaths = useMemo(
    () => (path === null ? null : searchConnectorPaths(layout, path)),
    [layout, path],
  )
  const hitSides = useMemo(
    () => (path === null ? null : sidesByMatch(path.hits)),
    [path],
  )
  const generation = flashGeneration(changedMatchIds)

  const treeRef = useRef<HTMLDivElement>(null)
  const headsRef = useRef<HTMLDivElement>(null)
  // 欄頭跟著容器橫向位移：直接改 style，不觸發 re-render
  const syncHeads = useCallback((scrollLeft: number) => {
    if (headsRef.current)
      headsRef.current.style.transform = `translateX(${-scrollLeft}px)`
  }, [])
  const onScroll = (event: UIEvent<HTMLDivElement>) =>
    syncHeads(event.currentTarget.scrollLeft)

  // 只在高亮的隊伍改變時自動捲動；輪詢帶來新資料時不動
  const farthestRound = path?.farthestRound ?? null
  const scrolledTeamRef = useRef<string | null>(null)
  useEffect(() => {
    if (highlightTeamId === scrolledTeamRef.current) return
    scrolledTeamRef.current = highlightTeamId
    const tree = treeRef.current
    if (highlightTeamId === null || farthestRound === null || tree === null)
      return
    tree.scrollLeft = bracketScrollLeftForRound(farthestRound, tree.clientWidth)
    syncHeads(tree.scrollLeft)
  }, [highlightTeamId, farthestRound, syncHeads])

  const sticky = toolbar !== undefined

  return (
    <div data-slot="bracket-explorer" className={cn("min-w-0", className)}>
      {sticky && (
        <div
          data-slot="bracket-toolbar"
          // z-[45]：蓋過全站頂欄（z-40），垂直捲動時看起來像頂欄捲走；對話框（z-50）仍在上層
          className="sticky top-0 z-[45] flex h-13 items-center bg-background"
        >
          {toolbar}
        </div>
      )}
      {toolbarNote}
      <div
        data-slot="bracket-round-heads-viewport"
        className={cn(
          "overflow-hidden",
          sticky && "sticky top-13 z-[45] bg-background",
        )}
      >
        <div
          ref={headsRef}
          data-slot="bracket-round-heads"
          className="relative mx-1 mt-1 mb-1 h-5 will-change-transform"
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
      </div>
      <div
        ref={treeRef}
        data-slot="bracket-tree"
        className="max-w-full overflow-x-auto overscroll-x-contain"
        onScroll={onScroll}
      >
        {/* 4px 內距：讓進行中卡片的 3px 光環不被捲動容器裁掉 */}
        <div className="w-max px-1 pb-1">
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
              {searchPaths?.solid && (
                <path
                  data-slot="bracket-search-connectors"
                  d={searchPaths.solid}
                  fill="none"
                  stroke="var(--search-highlight)"
                  strokeWidth={2}
                />
              )}
              {searchPaths?.dashed && (
                <path
                  data-slot="bracket-search-connectors-pending"
                  d={searchPaths.dashed}
                  fill="none"
                  stroke="var(--search-highlight)"
                  strokeWidth={2}
                  strokeDasharray="4 3"
                />
              )}
            </svg>
            {layout.cards.map(({ match, x, y }) => {
              const flash = changedMatchIds.has(match.id)
              return (
                <BracketMatchCard
                  key={flash ? `${match.id}:${generation}` : match.id}
                  match={match}
                  flash={flash}
                  matchHref={matchHref}
                  placements={bracket}
                  disqualifiedLast={disqualifiedLast}
                  searchHitSide={hitSides?.get(match.id)}
                  searchPendingSide={
                    path?.pending?.matchId === match.id
                      ? path.pending.side
                      : undefined
                  }
                  className="absolute"
                  style={{ left: x, top: y }}
                />
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
