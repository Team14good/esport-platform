// 場次狀態與結果的顯示規則：對戰樹場次卡（4.6）與 S4 場次頁（5.8）共用同一份對照。
import type { StatusTone } from "@/components/common/StatusBadge"
import type {
  BracketSide,
  MatchOutcome,
  MatchStatus,
  PublicMatch,
} from "./bracket-types"

export const THIRD_PLACE_LABEL = "季軍賽"

export type MatchStatusBadge = {
  tone: StatusTone
  label: string
  pulse?: boolean
}

/** 場次狀態徽章（DESIGN.md〈Status badge〉場次欄）；「申訴中」由 6.1 開始出現 */
export const MATCH_STATUS_BADGES: Record<MatchStatus, MatchStatusBadge> = {
  scheduled: { tone: "muted", label: "待開打" },
  live: { tone: "live", label: "進行中", pulse: true },
  appeal_window: { tone: "appeal", label: "申訴期" },
  appealed: { tone: "appeal", label: "申訴中", pulse: true },
  confirmed: { tone: "confirmed", label: "已確認" },
  voided: { tone: "muted", label: "已取消" },
}

/** 顯示比分的狀態；待開打留空、已取消沒有比分 */
export const SCORED_STATUSES: ReadonlySet<MatchStatus> = new Set([
  "live",
  "appeal_window",
  "appealed",
  "confirmed",
])

/** 沒有實際比賽的結果：不顯示比分 */
export const UNSCORED_OUTCOMES: ReadonlySet<MatchOutcome> = new Set([
  "forfeit",
  "double_forfeit",
  "disqualified",
  "walkover",
])

/** 場次的顯示名稱：季軍賽寫「季軍賽」，其他寫編號（M3） */
export function matchLabel(
  match: Pick<PublicMatch, "code" | "is_third_place">,
) {
  return match.is_third_place ? THIRD_PLACE_LABEL : match.code
}

/** 這一場是否顯示比分 */
export function hasScore(match: Pick<PublicMatch, "status" | "outcome">) {
  return (
    SCORED_STATUSES.has(match.status) &&
    (match.outcome === null || !UNSCORED_OUTCOMES.has(match.outcome))
  )
}

export type SideMark = { label: string; tone: "default" | "destructive" }

export type SideView = {
  /** 隊名；未定時為來源說明（「M4 勝者」），確定沒有隊伍時為「—」 */
  name: string
  /** 隊伍未定（待定或確定沒有隊伍）或場次已取消：muted-foreground */
  pending: boolean
  /** Bracket mark tag：輪空、棄權、取消資格 */
  marks: SideMark[]
  /** 勝方樣式：只在已確認時套用 */
  winner: boolean
  /** 淘汰樣式：只在已確認時套用 */
  eliminated: boolean
}

export const EMPTY_TEAM_TEXT = "—"

/** 一方隊伍的顯示內容（名稱、標記、勝敗樣式），場次卡與 S4 比分共用。 */
export function sideView(match: PublicMatch, side: BracketSide): SideView {
  const team = side === "a" ? match.team_a : match.team_b
  const source = side === "a" ? match.source_a : match.source_b
  const { outcome, winner_id: winnerId, status } = match

  const bye = side === "a" ? match.bye_a : match.bye_b
  // 確定不會有隊伍的位置：約定是 source 為 null；已確認的 walkover 空缺方即使還帶著 source 也算（保險）
  const empty =
    team === null &&
    (source === null || (status === "confirmed" && outcome === "walkover"))

  const marks: SideMark[] = []
  // 由輪空進入本輪的一方，或確定不會有隊伍的位置
  if (bye || empty) {
    marks.push({ label: "輪空", tone: "default" })
  }
  const isLoser = team !== null && winnerId !== null && team.id !== winnerId
  if (outcome === "double_forfeit" || (outcome === "forfeit" && isLoser)) {
    marks.push({ label: "棄權", tone: "default" })
  }
  if (outcome === "disqualified" && isLoser) {
    marks.push({ label: "取消資格", tone: "destructive" })
  }

  // 勝隊與淘汰樣式只在「已確認」套用：申訴期內結果未確認、不顯示晉級
  const confirmed = status === "confirmed"
  return {
    name: team?.name ?? (empty ? EMPTY_TEAM_TEXT : source) ?? EMPTY_TEAM_TEXT,
    pending: team === null || status === "voided",
    marks,
    winner: confirmed && team !== null && team.id === winnerId,
    eliminated:
      confirmed && team !== null && (outcome === "double_forfeit" || isLoser),
  }
}
