import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import type { PublicTournament } from "@/client"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { cn } from "@/lib/utils"
import { publicTournamentsQueryOptions } from "./queries"
import {
  formatRegistrationPeriod,
  groupTournaments,
  TOURNAMENT_STATUS_LABEL,
} from "./status"

export const EMPTY_TOURNAMENTS_TEXT = "目前沒有公開的賽事。"

function Field({ term, children }: { term: string; children: string }) {
  return (
    <div className="flex min-w-0 gap-2">
      <dt className="shrink-0 text-muted-foreground">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/** S1 的一張賽事卡：整張是連往 S2 的連結。 */
function TournamentCard({ tournament }: { tournament: PublicTournament }) {
  const cancelled = tournament.status === "cancelled"
  return (
    <li>
      <Link
        to="/tournaments/$tournamentId"
        params={{ tournamentId: tournament.id }}
        className="flex flex-col gap-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/60 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="min-w-0 break-words text-heading-md">
            {tournament.name}
          </h3>
          <span
            className={cn(
              "text-label",
              cancelled ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {TOURNAMENT_STATUS_LABEL[tournament.status]}
          </span>
        </div>
        <dl className="flex flex-col gap-1 text-body">
          <Field term="遊戲">{tournament.game_name}</Field>
          <Field term="名額">{`${tournament.capacity} 隊`}</Field>
          {tournament.status === "upcoming" ? (
            <Field term="報名開始">
              {formatMatchDateTime(tournament.registration_start)}
            </Field>
          ) : null}
          <Field term="報名期間">{formatRegistrationPeriod(tournament)}</Field>
          <Field term="開賽時間">
            {formatMatchDateTime(tournament.start_at)}
          </Field>
        </dl>
      </Link>
    </li>
  )
}

function ListSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-3">
      <Skeleton className="h-6 w-24" />
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-36 w-full" />
    </div>
  )
}

/** S1 賽事列表：依狀態分組，空的組不顯示。不需登入。 */
export function TournamentList() {
  const tournaments = useQuery(publicTournamentsQueryOptions())

  let content: ReactNode
  if (tournaments.data) {
    const groups = groupTournaments(tournaments.data)
    content =
      groups.length === 0 ? (
        <p className="py-12 text-center text-body-lg text-muted-foreground">
          {EMPTY_TOURNAMENTS_TEXT}
        </p>
      ) : (
        groups.map((group) => {
          const label = TOURNAMENT_STATUS_LABEL[group.status]
          return (
            <section
              key={group.status}
              aria-label={label}
              className="flex flex-col gap-3"
            >
              {/* 畫面上是「進行中 1」，螢幕閱讀器唸「進行中（1 場）」 */}
              <h2
                aria-label={`${label}（${group.tournaments.length} 場）`}
                className="text-label text-muted-foreground"
              >
                {label}
                <span className="ml-1.5">{group.tournaments.length}</span>
              </h2>
              <ul className="grid gap-3 md:grid-cols-2">
                {group.tournaments.map((tournament) => (
                  <TournamentCard key={tournament.id} tournament={tournament} />
                ))}
              </ul>
            </section>
          )
        })
      )
  } else if (tournaments.isPending) {
    content = <ListSkeleton />
  } else {
    content = (
      <div className="flex flex-col items-start gap-3">
        <p className="text-body text-destructive">
          {getErrorMessage(parseApiError(tournaments.error))}
        </p>
        <Button variant="outline" onClick={() => tournaments.refetch()}>
          重新載入
        </Button>
      </div>
    )
  }

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-heading-lg">賽事</h1>
      {/* 一直掛著的 live region，只換內容 */}
      <span role="status" className="sr-only">
        {tournaments.isPending ? "載入中" : null}
      </span>
      {content}
    </section>
  )
}
