import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import type { PublicTournament } from "@/client"
import { Countdown } from "@/components/common/Countdown"
import { EmptyState } from "@/components/common/EmptyState"
import { PageBannerSlot } from "@/components/common/PageBanner"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  isTournamentNotFound,
  publicTournamentQueryOptions,
} from "@/features/tournaments/queries"
import {
  DRAW_PENDING_TEXT,
  registrationEndVariant,
} from "@/features/tournaments/TournamentOverview"
import {
  CANCELLED_BANNER_TEXT,
  TournamentHeader,
} from "@/features/tournaments/TournamentPage"
import { TournamentTabs } from "@/features/tournaments/TournamentTabs"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { BracketPending } from "./BracketPending"
import { BracketTree } from "./BracketTree"
import { fetchPublicBracket, publicBracketQueryKey } from "./bracket-queries"
import { connectionLostText } from "./ConnectionLostBanner"
import { matchPath } from "./match-source"
import { useBracketPolling } from "./use-bracket-polling"

/** 已取消（或狀態不該沒有對戰表）時的空狀態 */
export const BRACKET_ABSENT_TEXT = "這場賽事沒有對戰表。"

// S3 對戰表（S2 的「對戰表」分頁，路由 /tournaments/$tournamentId/bracket）。
// 標題列、分頁列、取消 banner 沿用 S2（B 的 features/tournaments）匯出的元件與常數，不修改它們。

/**
 * 分頁標題「{賽事名稱} · FLOW」；離開頁面時還原。
 * 下一頁（例如 S4）的 head 可能已先寫入自己的標題，那時不還原，免得蓋掉它。
 */
function useTournamentTitle(name: string | undefined) {
  useEffect(() => {
    if (!name) return
    const previous = document.title
    const title = `${name} · FLOW`
    document.title = title
    return () => {
      if (document.title === title) document.title = previous
    }
  }, [name])
}

type TournamentProps = {
  tournament: PublicTournament
  /** 倒數歸零後每 5 秒呼叫一次（最多 2 分鐘），用來重抓賽事 */
  onCountdownExpire: () => void
}

/** 尚未抽籤：空狀態＋依賽事狀態的報名截止倒數或說明。 */
function BracketNotDrawn({ tournament, onCountdownExpire }: TournamentProps) {
  switch (tournament.status) {
    case "upcoming":
    case "open":
      return (
        <BracketPending
          countdown={
            <Countdown
              key={`registration-end-${tournament.registration_end}`}
              label="報名截止"
              deadline={tournament.registration_end}
              variant={registrationEndVariant}
              onExpire={onCountdownExpire}
            />
          }
        />
      )
    case "closed":
      return (
        <BracketPending
          countdown={
            <p className="text-body text-muted-foreground">
              {DRAW_PENDING_TEXT}
            </p>
          }
        />
      )
    default:
      // 已取消、或理應已有對戰表的狀態（資料不一致）：不寫「之後會抽籤」
      return <EmptyState title={BRACKET_ABSENT_TEXT} />
  }
}

/** 已取得賽事資料：Page banner、標題列、分頁列與對戰樹（每 5 秒輪詢）。 */
function BracketSection({ tournament, onCountdownExpire }: TournamentProps) {
  const {
    bracket,
    changedMatchIds,
    connectionLost,
    lastUpdatedAt,
    notFound,
    error,
  } = useBracketPolling({
    queryKey: publicBracketQueryKey(tournament.id),
    queryFn: () => fetchPublicBracket(tournament.id),
  })
  // 第一次載入就失敗（不是尚未抽籤）時沒有舊畫面可保留，直接顯示連線中斷並繼續輪詢重試
  const showConnectionLost = connectionLost || error != null

  // 抽籤、開賽、晉級都會改變對戰表；對戰表一變就重抓賽事，讓標題列的狀態與取消 banner 跟著更新
  const queryClient = useQueryClient()
  const bracketUpdatedAt = bracket?.updated_at
  useEffect(() => {
    if (bracketUpdatedAt === undefined) return
    void queryClient.invalidateQueries({
      queryKey: publicTournamentQueryOptions(tournament.id).queryKey,
      exact: true,
    })
  }, [bracketUpdatedAt, queryClient, tournament.id])

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <PageBannerSlot
        banners={[
          tournament.status === "cancelled" && {
            variant: "destructive",
            children: CANCELLED_BANNER_TEXT,
          },
          showConnectionLost && {
            children: connectionLostText(lastUpdatedAt),
          },
        ]}
      />
      <TournamentHeader tournament={tournament} />
      <TournamentTabs tournamentId={tournament.id} current="bracket">
        {bracket ? (
          <BracketTree
            bracket={bracket}
            changedMatchIds={changedMatchIds}
            matchHref={(matchId) => matchPath(tournament.id, matchId)}
          />
        ) : notFound ? (
          <BracketNotDrawn
            tournament={tournament}
            onCountdownExpire={onCountdownExpire}
          />
        ) : (
          <Skeleton data-slot="bracket-loading" className="h-48 w-full" />
        )}
      </TournamentTabs>
    </section>
  )
}

function PageSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-4">
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-5 w-20" />
      <Skeleton className="h-9 w-40" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

/** S3 對戰表頁。不需登入；賽事不存在時顯示 404 頁。 */
export function TournamentBracketPage({
  tournamentId,
}: {
  tournamentId: string
}) {
  const queryClient = useQueryClient()
  const tournament = useQuery(publicTournamentQueryOptions(tournamentId))
  useTournamentTitle(tournament.data?.name)

  // 報名截止倒數歸零後重抓賽事（例如轉為報名截止）；倒數本身每 5 秒呼叫一次，單次失敗不重試
  const refetchAfterCountdown = () => {
    void queryClient
      .fetchQuery({
        ...publicTournamentQueryOptions(tournamentId),
        retry: false,
      })
      .catch(() => undefined)
  }

  if (tournament.data) {
    return (
      <BracketSection
        tournament={tournament.data}
        onCountdownExpire={refetchAfterCountdown}
      />
    )
  }

  if (isTournamentNotFound(tournament.error)) return <ErrorPage status={404} />

  return (
    <>
      <span role="status" className="sr-only">
        {tournament.isPending ? "載入中" : null}
      </span>
      {tournament.isPending ? (
        <PageSkeleton />
      ) : (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(tournament.error))}
          </p>
          <Button variant="outline" onClick={() => tournament.refetch()}>
            重新載入
          </Button>
        </div>
      )}
    </>
  )
}
