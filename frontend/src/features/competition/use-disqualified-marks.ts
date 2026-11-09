import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import type { PublicMatchDetail } from "@/client"
import { fetchPublicBracket, publicBracketQueryKey } from "./bracket-queries"
import { disqualifiedLastMatches } from "./match-status"

const NONE: ReadonlySet<string> = new Set()

/**
 * S4（6.5）：這一場的兩隊中，已取消資格、且這一場是它在對戰樹出現的最後一場的隊伍 id。
 * 只有兩隊之一已取消資格時才讀公開對戰樹（與 S3 同一個 query key）；讀取中或失敗時不標記。
 */
export function useDisqualifiedMarks(
  detail: PublicMatchDetail,
): ReadonlySet<string> {
  const tournamentId = detail.tournament.id
  const enabled =
    detail.team_a?.disqualified === true || detail.team_b?.disqualified === true
  const bracket = useQuery({
    queryKey: publicBracketQueryKey(tournamentId),
    queryFn: () => fetchPublicBracket(tournamentId),
    enabled,
    retry: false,
  })
  const data = enabled ? bracket.data : undefined
  return useMemo(() => {
    if (data === undefined) return NONE
    const last = disqualifiedLastMatches(data.matches)
    const ids = [detail.team_a, detail.team_b]
      .filter((team) => team?.disqualified === true)
      .map((team) => team?.id ?? "")
      .filter((id) => last.get(id) === detail.id)
    return ids.length > 0 ? new Set(ids) : NONE
  }, [data, detail])
}
