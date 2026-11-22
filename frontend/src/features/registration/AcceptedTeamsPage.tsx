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
  AcceptedTeamReportAction,
  useReportableTeamsById,
} from "@/features/disputes/AcceptedTeamReportAction"
import {
  isTournamentNotFound,
  publicTournamentQueryOptions,
} from "@/features/tournaments/queries"
import {
  CANCELLED_BANNER_TEXT,
  TournamentHeader,
} from "@/features/tournaments/TournamentPage"
import { TournamentTabs } from "@/features/tournaments/TournamentTabs"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { publicAcceptedTeamsQueryOptions } from "./queries"

// S2「正取隊伍」分頁（Story 3.9，路由 /tournaments/$tournamentId/teams）：不需登入。
// 標題列、分頁列、取消 banner 沿用 S2（B 的 features/tournaments）匯出的元件與常數。

export const PRIORITY_HIDDEN_TEXT = "優先期結束後公布正取隊伍。"
export const NO_ACCEPTED_TEAMS_TEXT = "目前還沒有正取隊伍。"

/** 總覽的已正取隊數文字 */
export function acceptedCountText(count: number, capacity: number): string {
  return `已正取 ${count}／${capacity} 隊`
}

/**
 * 分頁標題「{賽事名稱} · FLOW」；離開頁面時還原。
 * 下一頁的 head 可能已先寫入自己的標題，那時不還原，免得蓋掉它。
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

/** 正取名單：優先期內的空狀態與倒數、名單、空名單、載入失敗。 */
function AcceptedTeamsList({ tournament }: { tournament: PublicTournament }) {
  const queryClient = useQueryClient()
  const options = publicAcceptedTeamsQueryOptions(tournament.id)
  const accepted = useQuery(options)
  const reportable = useReportableTeamsById(tournament.id, tournament.status)

  // 優先期倒數歸零後重抓名單；倒數本身每 5 秒呼叫一次，單次失敗不重試
  const refetchAfterCountdown = () => {
    void queryClient
      .fetchQuery({ ...options, retry: false })
      .catch(() => undefined)
  }

  if (accepted.data) {
    const { announce_at: announceAt, teams } = accepted.data
    if (announceAt) {
      return (
        <EmptyState
          title={PRIORITY_HIDDEN_TEXT}
          action={
            // EmptyState 的說明是 <p>，倒數是 <div>，放在動作的位置
            <Countdown
              key={`priority-end-${announceAt}`}
              label="優先期結束"
              deadline={announceAt}
              variant="muted"
              onExpire={refetchAfterCountdown}
              className="w-full max-w-xs text-left"
            />
          }
        />
      )
    }
    if (teams.length === 0) return <EmptyState title={NO_ACCEPTED_TEAMS_TEXT} />
    return (
      <ul
        data-slot="accepted-teams"
        className="flex flex-col divide-y rounded-lg border bg-card"
      >
        {teams.map((team) => (
          <li
            key={team.id}
            className="flex min-h-12 items-center justify-between gap-3 px-4 py-2"
          >
            <span className="min-w-0 break-words text-body">{team.name}</span>
            <AcceptedTeamReportAction
              tournamentId={tournament.id}
              team={reportable.get(team.id)}
            />
          </li>
        ))}
      </ul>
    )
  }

  if (accepted.isPending) {
    return (
      <>
        <span role="status" className="sr-only">
          載入中
        </span>
        <Skeleton data-slot="accepted-teams-loading" className="h-48 w-full" />
      </>
    )
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-body text-destructive">
        {getErrorMessage(parseApiError(accepted.error))}
      </p>
      <Button variant="outline" onClick={() => accepted.refetch()}>
        重新載入
      </Button>
    </div>
  )
}

/** 總覽（開放報名時）的「已正取 n／名額 隊」；載入中或失敗時不顯示。 */
export function AcceptedCount({
  tournamentId,
  capacity,
}: {
  tournamentId: string
  capacity: number
}) {
  const accepted = useQuery(publicAcceptedTeamsQueryOptions(tournamentId))
  if (!accepted.data) return null
  return (
    <p className="text-body">
      {acceptedCountText(accepted.data.teams.length, capacity)}
    </p>
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

/** S2「正取隊伍」分頁。不需登入；賽事不存在時顯示 404 頁。 */
export function AcceptedTeamsPage({ tournamentId }: { tournamentId: string }) {
  const tournament = useQuery(publicTournamentQueryOptions(tournamentId))
  useTournamentTitle(tournament.data?.name)

  if (tournament.data) {
    return (
      <section className="flex min-w-0 flex-col gap-6">
        <PageBannerSlot
          banners={[
            tournament.data.status === "cancelled" && {
              variant: "destructive",
              children: CANCELLED_BANNER_TEXT,
            },
          ]}
        />
        <TournamentHeader tournament={tournament.data} />
        <TournamentTabs tournamentId={tournamentId} current="teams">
          <AcceptedTeamsList tournament={tournament.data} />
        </TournamentTabs>
      </section>
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
