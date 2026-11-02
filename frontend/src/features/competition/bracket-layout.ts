// 對戰樹的版面計算（純函式）。尺寸取自 DESIGN.md〈Layout & Spacing〉與 index.css 的 --spacing-bracket-*：
// 欄寬 200、連接線 28、場次間距 18、列高 32。直排位置照完整的 2 的次方排：第一輪輪空的位置不畫卡片，
// 但仍佔一格，所以第二輪以後每張卡都對齊兩個來源位置的正中間。

import type { PublicBracket, PublicMatch } from "./bracket-types"

export const BRACKET_COLUMN_WIDTH = 200
export const BRACKET_CONNECTOR_WIDTH = 28
export const BRACKET_MATCH_GAP = 18
export const BRACKET_ROW_HEIGHT = 32
/** 兩列 32px＋中間 1px 分隔＋上下 1px 外框 */
export const BRACKET_CARD_HEIGHT = BRACKET_ROW_HEIGHT * 2 + 1 + 2
/** 卡片上方的 overline 標頭（14px 高、距卡片 2px）所需的空間，與示意圖相同 */
export const BRACKET_CARD_HEADER_SPACE = 19
/** 季軍賽卡與決賽卡之間的距離（決賽卡底到季軍賽卡頂），與示意圖相同 */
export const BRACKET_THIRD_PLACE_GAP = 83

const COLUMN_STEP = BRACKET_COLUMN_WIDTH + BRACKET_CONNECTOR_WIDTH
const SLOT_PITCH = BRACKET_CARD_HEIGHT + BRACKET_MATCH_GAP

export type BracketColumn = {
  roundNo: number
  name: string
  x: number
}

export type BracketCardPosition = {
  match: PublicMatch
  /** 卡片左上角，相對於畫布 */
  x: number
  y: number
}

export type BracketConnector = {
  /** 下一輪那一場的 id */
  id: string
  /** SVG path 的 d：直角折線，前後各半條連接線寬 */
  d: string
}

export type BracketLayout = {
  width: number
  height: number
  columns: BracketColumn[]
  cards: BracketCardPosition[]
  connectors: BracketConnector[]
}

function columnX(roundNo: number): number {
  return (roundNo - 1) * COLUMN_STEP
}

/** 第 roundNo 輪、第 position 格（0 起算）的卡片中心 y */
function centerY(roundNo: number, position: number): number {
  const span = 2 ** (roundNo - 1)
  return (
    BRACKET_CARD_HEADER_SPACE +
    BRACKET_CARD_HEIGHT / 2 +
    SLOT_PITCH * (span * position + (span - 1) / 2)
  )
}

export function bracketCanvasWidth(rounds: number): number {
  if (rounds < 1) return 0
  return rounds * BRACKET_COLUMN_WIDTH + (rounds - 1) * BRACKET_CONNECTOR_WIDTH
}

export function layoutBracket(bracket: PublicBracket): BracketLayout {
  const { rounds } = bracket
  const columns: BracketColumn[] = []
  for (let roundNo = 1; roundNo <= rounds; roundNo++) {
    columns.push({
      roundNo,
      name: bracket.round_names[roundNo - 1] ?? "",
      x: columnX(roundNo),
    })
  }

  const sorted = [...bracket.matches].sort(
    (a, b) =>
      a.round_no - b.round_no ||
      Number(a.is_third_place) - Number(b.is_third_place) ||
      a.slot_no - b.slot_no,
  )

  const cards: BracketCardPosition[] = []
  // 「輪次:格」→ 卡片，用來畫連接線
  const bySlot = new Map<string, BracketCardPosition>()
  let final: BracketCardPosition | undefined
  for (const match of sorted) {
    if (match.is_third_place) continue
    const position = match.slot_no - 1
    const card = {
      match,
      x: columnX(match.round_no),
      y: centerY(match.round_no, position) - BRACKET_CARD_HEIGHT / 2,
    }
    cards.push(card)
    bySlot.set(`${match.round_no}:${position}`, card)
    if (match.round_no === rounds && position === 0) final = card
  }

  // 季軍賽放在決賽卡下方、不與決賽相連
  for (const match of sorted) {
    if (!match.is_third_place) continue
    const anchorY = final?.y ?? centerY(rounds, 0) - BRACKET_CARD_HEIGHT / 2
    cards.push({
      match,
      x: columnX(rounds),
      y: anchorY + BRACKET_CARD_HEIGHT + BRACKET_THIRD_PLACE_GAP,
    })
  }

  const connectors: BracketConnector[] = []
  for (const card of cards) {
    const { match } = card
    if (match.is_third_place || match.round_no < 2) continue
    const position = match.slot_no - 1
    const from = columnX(match.round_no - 1) + BRACKET_COLUMN_WIDTH
    const mid = from + BRACKET_CONNECTOR_WIDTH / 2
    const to = from + BRACKET_CONNECTOR_WIDTH
    const parentY = card.y + BRACKET_CARD_HEIGHT / 2
    // 輪空的來源位置沒有卡片，也就沒有那半邊的線
    const childYs = [2 * position, 2 * position + 1]
      .map((p) => bySlot.get(`${match.round_no - 1}:${p}`))
      .filter((c): c is BracketCardPosition => c !== undefined)
      .map((c) => c.y + BRACKET_CARD_HEIGHT / 2)
    if (childYs.length === 2) {
      const [ya, yb] = childYs
      connectors.push({
        id: match.id,
        d: `M${from} ${ya} H${mid} V${yb} H${from} M${mid} ${parentY} H${to}`,
      })
    } else if (childYs.length === 1) {
      connectors.push({
        id: match.id,
        d: `M${from} ${childYs[0]} H${mid} V${parentY} H${to}`,
      })
    }
  }

  const height = cards.reduce(
    (max, card) => Math.max(max, card.y + BRACKET_CARD_HEIGHT),
    0,
  )

  return {
    width: bracketCanvasWidth(rounds),
    height,
    columns,
    cards,
    connectors,
  }
}
