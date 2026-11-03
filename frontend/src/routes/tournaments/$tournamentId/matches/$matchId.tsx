import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"

import { Countdown } from "@/components/common/Countdown"
import { NotFoundPage } from "@/components/layout/ErrorPage"
import { Skeleton } from "@/components/ui/skeleton"
import { ConnectionLostBanner } from "@/features/competition/ConnectionLostBanner"
import { matchTitle } from "@/features/competition/MatchHeader"
import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import { fetchMatchDetail } from "@/features/competition/match-source"
import { useMatchPolling } from "@/features/competition/use-match-polling"

export const Route = createFileRoute(
  "/tournaments/$tournamentId/matches/$matchId",
)({
  // 只用來決定頁面標題；畫面資料由 useMatchPolling 輪詢。找不到場次或取得失敗時標題維持「FLOW」
  loader: async ({ params }) => {
    try {
      const detail = await fetchMatchDetail(params)
      return { title: `${matchTitle(detail)} · ${detail.tournament.name}` }
    } catch {
      return null
    }
  },
  head: ({ loaderData }) => ({
    meta: [{ title: loaderData ? `${loaderData.title} · FLOW` : "FLOW" }],
  }),
  component: MatchRoute,
})

function MatchRoute() {
  const { tournamentId, matchId } = Route.useParams()
  // 換場次（例如點同輪其他場次）時重新掛載：不沿用上一場的資料與 flash 狀態
  return (
    <MatchPage
      key={`${tournamentId}/${matchId}`}
      tournamentId={tournamentId}
      matchId={matchId}
    />
  )
}

/** S4 場次頁（觀眾檢視）：每 5 秒輪詢；找不到場次時顯示 404。 */
function MatchPage({
  tournamentId,
  matchId,
}: {
  tournamentId: string
  matchId: string
}) {
  const queryClient = useQueryClient()
  const queryKey = ["match", tournamentId, matchId]
  const { detail, changed, connectionLost, lastUpdatedAt, notFound, error } =
    useMatchPolling({
      queryKey,
      queryFn: () => fetchMatchDetail({ tournamentId, matchId }),
    })

  if (notFound) return <NotFoundPage />
  // 申訴期倒數（appeal 變體，帶進度條）；歸零後由 Countdown 每 5 秒呼叫 onExpire 重抓，直到伺服器回傳新狀態
  const appealDeadline = detail?.appeal_deadline
  const appealCountdown = appealDeadline ? (
    <Countdown
      label="剩餘時間"
      deadline={appealDeadline}
      variant="appeal"
      onExpire={() => void queryClient.invalidateQueries({ queryKey })}
    />
  ) : undefined
  // 第一次載入就失敗（不是 404）時沒有舊畫面可保留，不等連續失敗 3 次，直接顯示橫幅並繼續重試
  const showBanner = connectionLost || error != null
  return (
    <div className="flex min-w-0 flex-col gap-5">
      {showBanner && <ConnectionLostBanner lastUpdatedAt={lastUpdatedAt} />}
      {detail ? (
        <MatchSpectatorView
          detail={detail}
          changed={changed}
          appealCountdown={appealCountdown}
        />
      ) : (
        <div data-slot="match-loading" className="flex flex-col gap-4">
          <Skeleton className="h-20 w-64 max-w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}
    </div>
  )
}
