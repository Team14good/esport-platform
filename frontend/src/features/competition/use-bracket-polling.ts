import {
  keepPreviousData,
  type QueryKey,
  useQuery,
} from "@tanstack/react-query"
import { useState } from "react"

import type { PublicBracket, PublicMatch } from "@/client"
import { useConsecutiveFailures } from "./use-consecutive-failures"

// 公開對戰樹每 5 秒輪詢（AD-14、EXPERIENCE.md〈Foundation〉即時性）
export const BRACKET_POLL_INTERVAL_MS = 5000
/** 連續失敗幾次才顯示連線中斷 banner */
export const BRACKET_CONNECTION_LOST_AFTER = 3

const NO_CHANGES: ReadonlySet<string> = new Set()

/**
 * 對戰樹不存在（404 `BRACKET_NOT_FOUND`，例如尚未抽籤）。`fetchPublicBracket` 收到 404 時拋出它：
 * 不算連線失敗，照常輪詢，抽籤後就會出現。
 */
export class BracketNotFoundError extends Error {
  constructor() {
    super("BRACKET_NOT_FOUND")
    this.name = "BracketNotFoundError"
  }
}

function sameTeam(a: PublicMatch["team_a"], b: PublicMatch["team_a"]) {
  return a?.id === b?.id && a?.name === b?.name
}

function sameMatch(a: PublicMatch, b: PublicMatch): boolean {
  return (
    a.status === b.status &&
    a.outcome === b.outcome &&
    a.winner_id === b.winner_id &&
    sameTeam(a.team_a, b.team_a) &&
    sameTeam(a.team_b, b.team_b) &&
    a.wins_a === b.wins_a &&
    a.wins_b === b.wins_b &&
    a.scheduled_at === b.scheduled_at &&
    a.source_a === b.source_a &&
    a.source_b === b.source_b &&
    a.bye_a === b.bye_a &&
    a.bye_b === b.bye_b
  )
}

/** 逐場比較兩份對戰樹，回傳有變動（或新出現）的場次 id。 */
export function diffBracketMatches(
  previous: PublicBracket,
  next: PublicBracket,
): ReadonlySet<string> {
  const before = new Map(previous.matches.map((m) => [m.id, m]))
  const changed = new Set<string>()
  for (const match of next.matches) {
    const old = before.get(match.id)
    if (old === undefined || !sameMatch(old, match)) changed.add(match.id)
  }
  return changed.size > 0 ? changed : NO_CHANGES
}

type UseBracketPollingOptions = {
  queryKey: QueryKey
  /** S3 傳 `fetchPublicBracket`（產生的 client）；測試傳假資料 */
  queryFn: () => Promise<PublicBracket>
  /** false 時不抓取也不輪詢 */
  enabled?: boolean
}

export type BracketPollingResult = {
  /** 最後一份成功取得的對戰樹；重抓或失敗時保留舊資料，不回到 loading */
  bracket: PublicBracket | undefined
  /** 與上一份資料相比有變動的場次；第一次載入為空。每次資料變動都是新的 Set */
  changedMatchIds: ReadonlySet<string>
  /** 連續失敗 3 次為 true，成功一次就回到 false */
  connectionLost: boolean
  /** 最後一次成功取得資料的時間 */
  lastUpdatedAt: Date | null
  /** 第一次載入、還沒有任何資料 */
  isLoading: boolean
  /** 對戰樹不存在（BracketNotFoundError），而且沒有資料可顯示；之後的暫時失敗不會讓它變回 false */
  notFound: boolean
  /** 第一次載入就失敗（沒有資料、也沒收到過「對戰樹不存在」）時的錯誤 */
  error: unknown
}

type Snapshot = {
  data: PublicBracket | undefined
  changed: ReadonlySet<string>
}

/**
 * 公開對戰樹的輪詢：每 5 秒重抓、分頁在背景時暫停、回到前景立即重抓。
 * 失敗不由 TanStack 重試，連續失敗次數由這個 hook 自己算。
 */
export function useBracketPolling({
  queryKey,
  queryFn,
  enabled = true,
}: UseBracketPollingOptions): BracketPollingResult {
  const query = useQuery({
    queryKey,
    queryFn,
    enabled,
    refetchInterval: BRACKET_POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const { data, dataUpdatedAt, errorUpdateCount } = query

  // 資料換了一份（structural sharing 下內容相同時參照不變）才重新比較，在 render 中同步更新
  const [snapshot, setSnapshot] = useState<Snapshot>({
    data,
    changed: NO_CHANGES,
  })
  let changed = snapshot.changed
  if (snapshot.data !== data) {
    changed =
      snapshot.data !== undefined &&
      data !== undefined &&
      snapshot.data.tournament_id === data.tournament_id
        ? diffBracketMatches(snapshot.data, data)
        : NO_CHANGES
    setSnapshot({ data, changed })
  }

  // 還沒有資料時收到「對戰樹不存在」不算連線失敗，連續失敗也歸零；
  // 已有對戰樹後才收到 404（例如之後的撤銷抽籤）照一般失敗累計，連續 3 次顯示連線中斷，不會無聲停在舊的對戰樹
  const consecutiveFailures = useConsecutiveFailures(
    dataUpdatedAt,
    errorUpdateCount,
    query.error instanceof BracketNotFoundError && data === undefined,
  )
  // 收到過「對戰樹不存在」、之後還沒拿到資料：畫面維持「尚未抽籤」，中間的暫時失敗只累計連續失敗次數，
  // 不當成第一次載入就失敗（連續 3 次才顯示連線中斷）
  const [sawNotFound, setSawNotFound] = useState(false)
  let notFoundSeen = sawNotFound
  if (data !== undefined) notFoundSeen = false
  else if (query.error instanceof BracketNotFoundError) notFoundSeen = true
  if (notFoundSeen !== sawNotFound) setSawNotFound(notFoundSeen)
  const notFound = data === undefined && notFoundSeen

  return {
    bracket: data,
    changedMatchIds: changed,
    connectionLost: consecutiveFailures >= BRACKET_CONNECTION_LOST_AFTER,
    lastUpdatedAt: dataUpdatedAt > 0 ? new Date(dataUpdatedAt) : null,
    isLoading: query.isPending,
    notFound,
    error: data === undefined && !notFound ? query.error : null,
  }
}
