import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLinkIcon } from "lucide-react"
import { useEffect } from "react"

import type { PublicTournament } from "@/client"
import { PageBannerSlot } from "@/components/common/PageBanner"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { cn } from "@/lib/utils"
import { isTournamentNotFound, publicTournamentQueryOptions } from "./queries"
import { TOURNAMENT_STATUS_LABEL } from "./status"
import { TournamentOverview } from "./TournamentOverview"
import { TournamentTabs } from "./TournamentTabs"

export const CANCELLED_BANNER_TEXT = "此賽事已取消"

/** S2 標題列：賽事名稱、狀態；有直播連結時「觀看直播」另開分頁。 */
export function TournamentHeader({
  tournament,
}: {
  tournament: PublicTournament
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="break-words text-heading-lg sm:text-display">
          {tournament.name}
        </h1>
        <p
          className={cn(
            "text-label",
            tournament.status === "cancelled"
              ? "text-destructive"
              : "text-muted-foreground",
          )}
        >
          {TOURNAMENT_STATUS_LABEL[tournament.status]}
        </p>
      </div>
      {tournament.livestream_url ? (
        <Button asChild variant="outline">
          <a
            href={tournament.livestream_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            觀看直播
            <ExternalLinkIcon aria-hidden />
          </a>
        </Button>
      ) : null}
    </header>
  )
}

/**
 * 依賽事名稱設定分頁標題「{賽事名稱} · FLOW」。路由的 head 拿不到 useQuery 的資料，
 * 所以在資料到了之後覆寫；離開頁面或換賽事時還原成覆寫前的標題
 * （下一頁的 head 標題文字相同時，router 不會重寫標題）。
 */
function useTournamentTitle(name: string | undefined) {
  useEffect(() => {
    if (!name) return
    const previous = document.title
    document.title = `${name} · FLOW`
    return () => {
      document.title = previous
    }
  }, [name])
}

function PageSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-4">
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-5 w-20" />
      <Skeleton className="h-9 w-24" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

/** S2 賽事頁（第一階段只有「總覽」分頁）。不需登入；賽事不存在時顯示 404 頁。 */
export function TournamentPage({ tournamentId }: { tournamentId: string }) {
  const queryClient = useQueryClient()
  const tournament = useQuery(publicTournamentQueryOptions(tournamentId))
  useTournamentTitle(tournament.data?.name)

  // 倒數歸零後的輪詢重抓：本身每 5 秒一次，所以單次失敗不重試
  const refetchAfterCountdown = () => {
    void queryClient
      .fetchQuery({
        ...publicTournamentQueryOptions(tournamentId),
        retry: false,
      })
      .catch(() => undefined)
  }

  // 倒數歸零後的重抓失敗時保留畫面上的資料，不換成錯誤頁
  if (tournament.data) {
    const data = tournament.data
    return (
      <section className="flex flex-col gap-6">
        <PageBannerSlot
          banners={[
            data.status === "cancelled" && {
              variant: "destructive",
              children: CANCELLED_BANNER_TEXT,
            },
          ]}
        />
        <TournamentHeader tournament={data} />
        <TournamentTabs tournamentId={data.id} current="overview">
          <TournamentOverview
            tournament={data}
            onCountdownExpire={refetchAfterCountdown}
          />
        </TournamentTabs>
      </section>
    )
  }

  if (isTournamentNotFound(tournament.error)) return <ErrorPage status={404} />

  return (
    <>
      {/* 一直掛著的 live region（載入與錯誤之間切換時不重新掛載），只換內容 */}
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
