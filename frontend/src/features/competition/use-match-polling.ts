import {
  keepPreviousData,
  type QueryKey,
  useQuery,
} from "@tanstack/react-query"
import { useState } from "react"

import { MatchNotFoundError } from "./match-source"
import type { PublicMatchDetail } from "./match-types"
import {
  BRACKET_CONNECTION_LOST_AFTER,
  BRACKET_POLL_INTERVAL_MS,
} from "./use-bracket-polling"
import { useConsecutiveFailures } from "./use-consecutive-failures"

/** 場次頁的輪詢設定與公開對戰樹相同：每 5 秒、連續失敗 3 次顯示連線中斷 */
export const MATCH_POLL_INTERVAL_MS = BRACKET_POLL_INTERVAL_MS
export const MATCH_CONNECTION_LOST_AFTER = BRACKET_CONNECTION_LOST_AFTER

/** 比分或狀態有變動：Score display flash 一次 */
export function isMatchScoreChanged(
  previous: PublicMatchDetail,
  next: PublicMatchDetail,
): boolean {
  return (
    previous.status !== next.status ||
    previous.wins_a !== next.wins_a ||
    previous.wins_b !== next.wins_b
  )
}

type UseMatchPollingOptions = {
  queryKey: QueryKey
  /** 傳入 fetchMatchDetail（或預覽頁的假資料函式）；找不到場次時拋出 MatchNotFoundError */
  queryFn: () => Promise<PublicMatchDetail>
  enabled?: boolean
}

export type MatchPollingResult = {
  /** 最後一份成功取得的場次；重抓或失敗時保留舊資料，不回到 loading */
  detail: PublicMatchDetail | undefined
  /** 連續失敗 3 次為 true，成功一次就回到 false */
  connectionLost: boolean
  /** 最後一次成功取得資料的時間 */
  lastUpdatedAt: Date | null
  /** 第一次載入、還沒有任何資料 */
  isLoading: boolean
  /** 找不到場次（MatchNotFoundError），而且沒有資料可顯示 */
  notFound: boolean
  /** 與上一份資料相比比分或狀態有變動；第一次載入為 false，直到下一份資料出現前維持不變 */
  changed: boolean
  /** 第一次載入就失敗、且不是找不到場次時的錯誤 */
  error: unknown
}

type Snapshot = {
  data: PublicMatchDetail | undefined
  changed: boolean
}

/**
 * S4 場次頁的輪詢：每 5 秒重抓、分頁在背景時暫停、回到前景立即重抓。
 * 設定與 useBracketPolling 相同（另外：找不到場次時停止定時重抓）；失敗不由 TanStack 重試，連續失敗次數由 hook 自己算。
 */
export function useMatchPolling({
  queryKey,
  queryFn,
  enabled = true,
}: UseMatchPollingOptions): MatchPollingResult {
  const query = useQuery({
    queryKey,
    queryFn,
    enabled,
    // 找不到場次（而且沒有資料）就停止輪詢；回到前景時仍會重抓一次
    refetchInterval: (q) =>
      q.state.data === undefined && q.state.error instanceof MatchNotFoundError
        ? false
        : MATCH_POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const { data, dataUpdatedAt, errorUpdateCount } = query

  // 資料換了一份（structural sharing 下內容相同時參照不變）才重新比較，在 render 中同步更新
  const [snapshot, setSnapshot] = useState<Snapshot>({ data, changed: false })
  let changed = snapshot.changed
  if (snapshot.data !== data) {
    changed =
      snapshot.data !== undefined &&
      data !== undefined &&
      snapshot.data.id === data.id &&
      isMatchScoreChanged(snapshot.data, data)
    setSnapshot({ data, changed })
  }

  const consecutiveFailures = useConsecutiveFailures(
    dataUpdatedAt,
    errorUpdateCount,
  )
  const firstLoadError = data === undefined ? query.error : null
  const notFound = firstLoadError instanceof MatchNotFoundError

  return {
    detail: data,
    connectionLost: consecutiveFailures >= MATCH_CONNECTION_LOST_AFTER,
    lastUpdatedAt: dataUpdatedAt > 0 ? new Date(dataUpdatedAt) : null,
    isLoading: query.isPending,
    notFound,
    changed,
    error: notFound ? null : firstLoadError,
  }
}
