import { useQuery } from "@tanstack/react-query"

import { publicAcceptedTeamsQueryOptions } from "./queries"

// S2 總覽（開放報名時）的已正取隊數（Story 3.9）。獨立成檔，總覽不必 import
// 「正取隊伍」分頁（分頁又會 import S2 的元件，形成循環）。

/** 總覽的已正取隊數文字 */
export function acceptedCountText(count: number, capacity: number): string {
  return `已正取 ${count}／${capacity} 隊`
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
