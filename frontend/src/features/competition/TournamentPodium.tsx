import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import type { PublicBracket, PublicMatch, PublicTeamRef } from "@/client"
import { Card } from "@/components/ui/card"
import { publicTournamentQueryOptions } from "@/features/tournaments/queries"
import { cn } from "@/lib/utils"
import { BracketMarkTag } from "./BracketMarkTag"
import { fetchPublicBracket, publicBracketQueryKey } from "./bracket-queries"
import { matchPath } from "./match-source"
import { PLACEMENT_MARKS, type SideMark } from "./match-status"

/** 該隊最後一場：該隊出現過、沒有取消的場次中輪次最大的一場；找不到時回傳 null。 */
export function teamLastMatchId(
  matches: readonly PublicMatch[],
  teamId: string,
): string | null {
  let last: PublicMatch | null = null
  for (const match of matches) {
    if (match.status === "voided") continue
    if (match.team_a?.id !== teamId && match.team_b?.id !== teamId) continue
    if (last === null || match.round_no > last.round_no) last = match
  }
  return last?.id ?? null
}

type PodiumRowProps = {
  mark: SideMark
  team: PublicTeamRef
  /** 該隊最後一場 S4 的網址；找不到場次時隊名不是連結 */
  href: string | null
  champion: boolean
}

function PodiumRow({ mark, team, href, champion }: PodiumRowProps) {
  const nameClass = cn(
    "min-w-0 truncate",
    champion ? "text-heading-md" : "text-body",
  )
  return (
    <div data-slot="podium-row" className="flex min-w-0 items-center gap-2">
      {href === null ? (
        <span title={team.name} className={nameClass}>
          {team.name}
        </span>
      ) : (
        <Link
          to={href}
          title={team.name}
          className={cn(nameClass, "hover:underline")}
        >
          {team.name}
        </Link>
      )}
      <BracketMarkTag tone={mark.tone}>{mark.label}</BracketMarkTag>
    </div>
  )
}

type TournamentPodiumProps = {
  bracket: Pick<PublicBracket, "tournament_id" | "matches" | "podium">
}

/** Podium：賽事已結束時列出冠軍、亞軍、季軍；從缺的名次不列，手機直排、桌機三欄。 */
export function TournamentPodium({ bracket }: TournamentPodiumProps) {
  const { podium, matches, tournament_id: tournamentId } = bracket
  if (podium === null) return null

  const rows = [
    { mark: PLACEMENT_MARKS.champion, team: podium.champion },
    { mark: PLACEMENT_MARKS.runnerUp, team: podium.runner_up },
    { mark: PLACEMENT_MARKS.thirdPlace, team: podium.third_place },
  ].flatMap(({ mark, team }) => (team === null ? [] : [{ mark, team }]))
  if (rows.length === 0) return null

  return (
    <section aria-label="賽事名次">
      <Card
        data-slot="podium"
        className="grid grid-cols-1 items-center gap-3 p-4 md:grid-cols-3"
      >
        {rows.map(({ mark, team }) => {
          const lastMatchId = teamLastMatchId(matches, team.id)
          return (
            <PodiumRow
              key={mark.label}
              mark={mark}
              team={team}
              href={
                lastMatchId === null
                  ? null
                  : matchPath(tournamentId, lastMatchId)
              }
              champion={mark === PLACEMENT_MARKS.champion}
            />
          )
        })}
      </Card>
    </section>
  )
}

/** S2 頁面最上方的 Podium：只有賽事已結束時才抓對戰表，載入中或失敗時不顯示。 */
export function FinishedTournamentPodium({
  tournamentId,
}: {
  tournamentId: string
}) {
  const tournament = useQuery(publicTournamentQueryOptions(tournamentId))
  const bracket = useQuery({
    queryKey: publicBracketQueryKey(tournamentId),
    queryFn: () => fetchPublicBracket(tournamentId),
    enabled: tournament.data?.status === "finished",
    retry: false,
  })
  if (tournament.data?.status !== "finished" || !bracket.data) return null
  return <TournamentPodium bracket={bracket.data} />
}
