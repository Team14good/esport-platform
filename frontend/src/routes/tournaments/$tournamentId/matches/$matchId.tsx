import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import type { PublicMatchDetail } from "@/client"
import { Countdown } from "@/components/common/Countdown"
import { NotFoundPage } from "@/components/layout/ErrorPage"
import { Skeleton } from "@/components/ui/skeleton"
import { ConnectionLostBanner } from "@/features/competition/ConnectionLostBanner"
import { MatchCheckIn, showsCheckIn } from "@/features/competition/MatchCheckIn"
import { matchTitle } from "@/features/competition/MatchHeader"
import { useMatchScoreEntry } from "@/features/competition/MatchScoreEntry"
import { MatchSpectatorView } from "@/features/competition/MatchSpectatorView"
import {
  fetchMatchDetail,
  matchQueryKey,
} from "@/features/competition/match-source"
import { useDisqualifiedMarks } from "@/features/competition/use-disqualified-marks"
import { useMatchPolling } from "@/features/competition/use-match-polling"
import { AppealPanel } from "@/features/disputes/AppealPanel"
import { AppealResultBadge } from "@/features/disputes/AppealResultBadge"

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

/** S4 場次頁：每 5 秒輪詢；找不到場次時顯示 404。報到與比分登錄面板依登入者顯示。 */
function MatchPage({
  tournamentId,
  matchId,
}: {
  tournamentId: string
  matchId: string
}) {
  const queryClient = useQueryClient()
  const queryKey = matchQueryKey(tournamentId, matchId)
  const { detail, changed, connectionLost, lastUpdatedAt, notFound, error } =
    useMatchPolling({
      queryKey,
      queryFn: () => fetchMatchDetail({ tournamentId, matchId }),
    })
  // 重抓這一場的所有資料：公開單場、報到狀態與比分登錄（三者的 key 都以 matchQueryKey 開頭）
  const refresh = () => queryClient.invalidateQueries({ queryKey })

  if (notFound) return <NotFoundPage />
  // 第一次載入就失敗（不是 404）時沒有舊畫面可保留，不等連續失敗 3 次，直接顯示橫幅並繼續重試
  const showBanner = connectionLost || error != null
  return (
    <div className="flex min-w-0 flex-col gap-5">
      {showBanner && <ConnectionLostBanner lastUpdatedAt={lastUpdatedAt} />}
      {detail ? (
        <MatchContent detail={detail} changed={changed} refresh={refresh} />
      ) : (
        <div data-slot="match-loading" className="flex flex-col gap-4">
          <Skeleton className="h-20 w-64 max-w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}
    </div>
  )
}

/** 已取得場次後的畫面：比分登錄面板要依資料查詢，所以拆成自己的元件（hook 不能放在條件分支裡）。 */
function MatchContent({
  detail,
  changed,
  refresh,
}: {
  detail: PublicMatchDetail
  changed: boolean
  refresh: () => Promise<unknown>
}) {
  const scoreEntry = useMatchScoreEntry({ detail, refresh })
  // 6.5：已取消資格的隊伍在它最後一場加「取消資格」標記
  const disqualifiedTeamIds = useDisqualifiedMarks(detail)
  // 申訴期倒數（appeal 變體，進度條從申訴期開始時間起算）；歸零後由 Countdown 每 5 秒呼叫 onExpire 重抓，直到伺服器回傳新狀態
  const appealCountdown = detail.appeal_deadline ? (
    <Countdown
      label="剩餘時間"
      deadline={detail.appeal_deadline}
      startsAt={detail.appeal_started_at ?? undefined}
      variant="appeal"
      onExpire={() => void refresh()}
    />
  ) : undefined
  return (
    <MatchSpectatorView
      detail={detail}
      changed={changed}
      appealCountdown={appealCountdown}
      appealAction={<AppealPanel detail={detail} refresh={refresh} />}
      headerExtra={<AppealResultBadge detail={detail} />}
      checkIn={
        showsCheckIn(detail) ? (
          <MatchCheckIn detail={detail} refresh={refresh} />
        ) : undefined
      }
      scoreEntry={scoreEntry}
      disqualifiedTeamIds={disqualifiedTeamIds}
    />
  )
}
