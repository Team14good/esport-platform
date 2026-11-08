import { useQuery } from "@tanstack/react-query"
import { ExternalLinkIcon } from "lucide-react"
import type { ReactNode } from "react"

import type { TournamentMode, TournamentRead } from "@/client"
import { BackofficeLayout } from "@/components/layout/BackofficeLayout"
import { ErrorPage } from "@/components/layout/ErrorPage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { DrawButton } from "@/features/competition/DrawButton"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { tournamentNav } from "./organizer-nav"
import {
  isTournamentForbidden,
  myTournamentQueryOptions,
} from "./organizer-queries"
import { isTournamentNotFound } from "./queries"
import { formatInterval, formatRegistrationPeriod } from "./status"
import { TournamentStatusBadge } from "./TournamentStatusBadge"

export const TOURNAMENT_MODE_LABEL: Record<TournamentMode, string> = {
  campus: "校園賽",
  custom: "自訂",
}

function PageSkeleton() {
  return (
    <div className="flex flex-col gap-4 py-6">
      <span role="status" className="sr-only">
        載入中
      </span>
      <Skeleton aria-hidden className="h-8 w-2/3" />
      <Skeleton aria-hidden className="h-48 w-full" />
    </div>
  )
}

/**
 * 主辦方賽事後台的版面（S27 起的頁面共用）：側欄標題是賽事名稱，項目見 `tournamentNav`。
 * 賽事不存在顯示 404 頁，別人的賽事顯示 S38 的 403。
 */
export function OrganizerTournamentLayout({
  tournamentId,
  children,
}: {
  tournamentId: string
  children: ReactNode
}) {
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))

  if (tournament.data) {
    return (
      <BackofficeLayout
        title={tournament.data.name}
        items={tournamentNav(tournament.data.id)}
      >
        {children}
      </BackofficeLayout>
    )
  }
  if (tournament.isPending) return <PageSkeleton />
  if (isTournamentNotFound(tournament.error)) return <ErrorPage status={404} />
  if (isTournamentForbidden(tournament.error)) return <ErrorPage status={403} />
  return (
    <div className="flex flex-col items-start gap-3 py-6">
      <p className="text-body text-destructive">
        {getErrorMessage(parseApiError(tournament.error))}
      </p>
      <Button variant="outline" onClick={() => tournament.refetch()}>
        重新載入
      </Button>
    </div>
  )
}

function Field({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid min-w-0 grid-cols-[6.5rem_minmax(0,1fr)] gap-2">
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/** S27 總覽的內容：賽事名稱＋狀態徽章，以及建立時的各項設定。 */
export function OrganizerTournamentSummary({
  tournament,
}: {
  tournament: TournamentRead
}) {
  return (
    <section className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="min-w-0 break-words text-heading-lg">
          {tournament.name}
        </h1>
        <TournamentStatusBadge status={tournament.status} />
      </header>
      <dl className="flex flex-col gap-2 rounded-lg border bg-card p-4 text-body">
        <Field term="模式">{TOURNAMENT_MODE_LABEL[tournament.mode]}</Field>
        <Field term="遊戲">{tournament.game_name}</Field>
        <Field term="名額">{`${tournament.capacity} 隊`}</Field>
        <Field term="報名期間">{formatRegistrationPeriod(tournament)}</Field>
        <Field term="優先期結束">
          {formatMatchDateTime(tournament.priority_end)}
        </Field>
        <Field term="開賽時間">
          {formatMatchDateTime(tournament.start_at)}
        </Field>
        <Field term="每輪間隔">
          {formatInterval(tournament.round_interval_minutes)}
        </Field>
        <Field term="BO">{`BO${tournament.bo}`}</Field>
        <Field term="先發／替補">
          {`先發 ${tournament.starters} 人／替補 ${tournament.substitutes} 人`}
        </Field>
        <Field term="棄權時限">{`${tournament.forfeit_minutes} 分鐘`}</Field>
        <Field term="申訴期">{`${tournament.appeal_minutes} 分鐘`}</Field>
        {tournament.livestream_url ? (
          <Field term="直播連結">
            <a
              href={tournament.livestream_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 break-all text-primary underline-offset-4 hover:underline"
            >
              {tournament.livestream_url}
              <ExternalLinkIcon aria-hidden className="size-4 shrink-0" />
            </a>
          </Field>
        ) : null}
      </dl>
    </section>
  )
}

/** S27 賽事總覽（主辦方）。資料由版面先載入，這裡讀同一份快取。 */
export function OrganizerTournamentOverview({
  tournamentId,
}: {
  tournamentId: string
}) {
  const tournament = useQuery(myTournamentQueryOptions(tournamentId))
  if (!tournament.data) return null
  return (
    <>
      <OrganizerTournamentSummary tournament={tournament.data} />
      <DrawButton tournament={tournament.data} />
    </>
  )
}
