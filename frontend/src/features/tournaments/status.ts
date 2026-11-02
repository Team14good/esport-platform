import type { PublicTournament, TournamentStatus } from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"

// 賽事狀態的中文名稱（contracts/tournaments.md〈三〉）。
// 第一階段先以文字顯示；1.7 的 StatusBadge 合併後由第二階段換成徽章。
export const TOURNAMENT_STATUS_LABEL: Record<TournamentStatus, string> = {
  upcoming: "尚未開放",
  open: "開放報名",
  closed: "報名截止",
  published: "賽程已公布",
  ongoing: "進行中",
  finished: "已結束",
  cancelled: "已取消",
}

/** S1 的分組順序：觀眾最關心的在前（spec-2-4 Decisions）。 */
export const STATUS_GROUP_ORDER: readonly TournamentStatus[] = [
  "ongoing",
  "open",
  "upcoming",
  "closed",
  "published",
  "finished",
  "cancelled",
]

// 這兩組依開賽時間由新到舊；其他組由近到遠
const NEWEST_FIRST: ReadonlySet<TournamentStatus> = new Set([
  "finished",
  "cancelled",
])

export type TournamentGroup = {
  status: TournamentStatus
  tournaments: PublicTournament[]
}

function startMs(tournament: PublicTournament): number {
  return new Date(tournament.start_at).getTime()
}

/** 依狀態分組並排序；空的組不回傳。 */
export function groupTournaments(
  tournaments: readonly PublicTournament[],
): TournamentGroup[] {
  return STATUS_GROUP_ORDER.flatMap((status) => {
    const direction = NEWEST_FIRST.has(status) ? -1 : 1
    const items = tournaments
      .filter((tournament) => tournament.status === status)
      .sort((a, b) => direction * (startMs(a) - startMs(b)))
    return items.length > 0 ? [{ status, tournaments: items }] : []
  })
}

/** 每輪間隔：「3 小時」「1 小時 30 分」「45 分鐘」。 */
export function formatInterval(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest} 分鐘`
  return rest === 0 ? `${hours} 小時` : `${hours} 小時 ${rest} 分`
}

/** 「報名期間」：開始 ～ 截止（Asia/Taipei）。 */
export function formatRegistrationPeriod(tournament: PublicTournament): string {
  return `${formatMatchDateTime(tournament.registration_start)} ～ ${formatMatchDateTime(tournament.registration_end)}`
}
