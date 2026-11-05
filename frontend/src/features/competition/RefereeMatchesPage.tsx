import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import type { RefereeMatch } from "@/client"
import { EmptyState } from "@/components/common/EmptyState"
import { StatusBadge } from "@/components/common/StatusBadge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getErrorMessage, parseApiError } from "@/lib/api-error"
import { MATCH_STATUS_BADGES, matchLabel } from "./match-status"
import { formatMatchDateTime } from "./match-time"
import { refereeMatchesQueryOptions } from "./referee-matches-queries"

export const NO_REFEREE_MATCHES_TEXT = "主辦方還沒有指派場次給你。"
export const READY_TO_START_TEXT = "可開始"
const PENDING_SIDE_TEXT = "—"

function sideText(
  team: RefereeMatch["team_a"],
  source: RefereeMatch["source_a"],
): string {
  return team?.name ?? source ?? PENDING_SIDE_TEXT
}

/** 待開打且兩隊都已報到標「可開始」，其他狀態用場次狀態徽章。 */
function MatchBadge({ match }: { match: RefereeMatch }) {
  if (match.status === "scheduled" && match.both_checked_in) {
    return <StatusBadge tone="brand">{READY_TO_START_TEXT}</StatusBadge>
  }
  const badge = MATCH_STATUS_BADGES[match.status]
  return (
    <StatusBadge tone={badge.tone} pulse={badge.pulse}>
      {badge.label}
    </StatusBadge>
  )
}

function MatchRow({
  tournamentId,
  match,
}: {
  tournamentId: string
  match: RefereeMatch
}) {
  return (
    <li>
      <Link
        to="/tournaments/$tournamentId/matches/$matchId"
        params={{ tournamentId, matchId: match.id }}
        className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border p-3 hover:bg-muted"
      >
        <span className="font-medium">{matchLabel(match)}</span>
        <span className="text-muted-foreground">{match.round_name}</span>
        <span className="min-w-0 break-words">
          {sideText(match.team_a, match.source_a)} vs{" "}
          {sideText(match.team_b, match.source_b)}
        </span>
        <time
          dateTime={match.scheduled_at}
          className="whitespace-nowrap text-muted-foreground"
        >
          {formatMatchDateTime(match.scheduled_at)}
        </time>
        <span className="ml-auto">
          <MatchBadge match={match} />
        </span>
      </Link>
    </li>
  )
}

/** S13 我執法的場次：依賽事分組，每場整列連到 S4。 */
export function RefereeMatchesPage() {
  const groups = useQuery(refereeMatchesQueryOptions())

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-8 sm:py-12">
      <h1 className="text-heading-lg">我執法的場次</h1>
      {groups.isPending ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <span className="sr-only">載入中</span>
        </div>
      ) : groups.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-body text-destructive">
            {getErrorMessage(parseApiError(groups.error))}
          </p>
          <Button variant="outline" onClick={() => groups.refetch()}>
            重新載入
          </Button>
        </div>
      ) : groups.data.length === 0 ? (
        <EmptyState title={NO_REFEREE_MATCHES_TEXT} />
      ) : (
        groups.data.map((group) => (
          <section
            key={group.tournament.id}
            aria-labelledby={`referee-group-${group.tournament.id}`}
            className="flex flex-col gap-3"
          >
            <h2
              id={`referee-group-${group.tournament.id}`}
              className="text-heading-md"
            >
              {group.tournament.name}
            </h2>
            <ul className="flex flex-col gap-2">
              {group.matches.map((match) => (
                <MatchRow
                  key={match.id}
                  tournamentId={group.tournament.id}
                  match={match}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </section>
  )
}
