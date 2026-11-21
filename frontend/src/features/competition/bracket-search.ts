// 對戰樹隊伍搜尋（4.7）的純函式：比對隊名、算出一支隊伍的晉級路徑。
// 只看 PublicBracket 的隊名（PublicTeamRef.name），不搜尋也不顯示學校（NFR-6）。

import type {
  MatchStatus,
  PublicBracket,
  PublicMatch,
  PublicTeamRef,
} from "@/client"
import type { BracketSide } from "./match-status"

/** 對戰樹上的一列：某場次的某一方 */
export type BracketRowRef = {
  matchId: string
  side: BracketSide
}

/** 晉級路徑上相鄰兩輪之間的半段連接線 */
export type BracketPathConnector = {
  /** 前一輪（子場次）的列 */
  child: BracketRowRef
  /** 下一輪（父場次）的列 */
  parent: BracketRowRef
  /** 通往虛線待定列的那段為 true */
  dashed: boolean
}

export type BracketTeamPath = {
  /** 這支隊伍出現過的每一列，依對戰樹順序 */
  hits: BracketRowRef[]
  /** 相鄰兩輪之間的連接線（季軍賽不畫） */
  connectors: BracketPathConnector[]
  /** 下一輪留給它目前未確認場次勝者的待定列；沒有時為 null */
  pending: BracketRowRef | null
  /** 出現過的最大輪次（季軍賽算最後一輪，虛線待定列不算）；沒有出現時為 null */
  farthestRound: number | null
}

/** 結果還沒確認的場次：待開打、進行中、申訴期、申訴中（已取消不算） */
const UNCONFIRMED_STATUSES: ReadonlySet<MatchStatus> = new Set([
  "scheduled",
  "live",
  "appeal_window",
  "appealed",
])

const SIDES: readonly BracketSide[] = ["a", "b"]

function teamOf(match: PublicMatch, side: BracketSide): PublicTeamRef | null {
  return side === "a" ? match.team_a : match.team_b
}

/** 對戰樹由左到右、由上到下的順序：輪次、同輪季軍賽在決賽之後、slot */
function treeOrder(matches: readonly PublicMatch[]): PublicMatch[] {
  return [...matches].sort(
    (x, y) =>
      x.round_no - y.round_no ||
      Number(x.is_third_place) - Number(y.is_third_place) ||
      x.slot_no - y.slot_no,
  )
}

/** 搜尋字串正規化：去掉前後空白、轉小寫；空字串代表沒有搜尋 */
export function normalizeTeamQuery(query: string): string {
  return query.trim().toLocaleLowerCase()
}

/**
 * 隊名部分符合（不分大小寫）的隊伍，依它在對戰樹第一次出現的位置排序。
 * 空字串（或只有空白）回傳空陣列。
 */
export function searchBracketTeams(
  bracket: PublicBracket,
  query: string,
): PublicTeamRef[] {
  const needle = normalizeTeamQuery(query)
  if (needle === "") return []
  const found = new Map<string, PublicTeamRef>()
  for (const match of treeOrder(bracket.matches)) {
    for (const side of SIDES) {
      const team = teamOf(match, side)
      if (
        team !== null &&
        !found.has(team.id) &&
        team.name.toLocaleLowerCase().includes(needle)
      ) {
        found.set(team.id, team)
      }
    }
  }
  return [...found.values()]
}

/** 父場次（下一輪 slot ceil(slot/2)）裡留給這一場勝者的那一方：slot 奇數為 A 方、偶數為 B 方 */
function parentSide(slotNo: number): BracketSide {
  return slotNo % 2 === 1 ? "a" : "b"
}

function findParent(
  bracket: PublicBracket,
  match: PublicMatch,
): PublicMatch | undefined {
  return bracket.matches.find(
    (m) =>
      !m.is_third_place &&
      m.round_no === match.round_no + 1 &&
      m.slot_no === Math.ceil(match.slot_no / 2),
  )
}

/** 一支隊伍在對戰樹上的晉級路徑：命中列、連接線、虛線待定列與最遠輪次。 */
export function bracketTeamPath(
  bracket: PublicBracket,
  teamId: string,
): BracketTeamPath {
  const hits: BracketRowRef[] = []
  // 非季軍賽的出現位置，用來畫連接線與判斷虛線列
  const mainHits: { match: PublicMatch; side: BracketSide }[] = []
  let farthestRound: number | null = null

  for (const match of treeOrder(bracket.matches)) {
    for (const side of SIDES) {
      if (teamOf(match, side)?.id !== teamId) continue
      hits.push({ matchId: match.id, side })
      if (!match.is_third_place) mainHits.push({ match, side })
      farthestRound = Math.max(farthestRound ?? 0, match.round_no)
    }
  }

  const connectors: BracketPathConnector[] = []
  for (const parentHit of mainHits) {
    const { match: parent, side } = parentHit
    if (parent.round_no < 2) continue
    // 子場次：前一輪中會晉級到這一方的那一場
    const childSlot = 2 * parent.slot_no - (side === "a" ? 1 : 0)
    const child = mainHits.find(
      (h) =>
        h.match.round_no === parent.round_no - 1 &&
        h.match.slot_no === childSlot,
    )
    if (child === undefined) continue
    connectors.push({
      child: { matchId: child.match.id, side: child.side },
      parent: { matchId: parent.id, side },
      dashed: false,
    })
  }

  let pending: BracketRowRef | null = null
  const last = mainHits.length > 0 ? mainHits[mainHits.length - 1] : undefined
  if (
    last !== undefined &&
    UNCONFIRMED_STATUSES.has(last.match.status) &&
    last.match.round_no < bracket.rounds
  ) {
    const parent = findParent(bracket, last.match)
    const side = parentSide(last.match.slot_no)
    if (parent !== undefined && teamOf(parent, side) === null) {
      pending = { matchId: parent.id, side }
      connectors.push({
        child: { matchId: last.match.id, side: last.side },
        parent: pending,
        dashed: true,
      })
    }
  }

  return { hits, connectors, pending, farthestRound }
}
