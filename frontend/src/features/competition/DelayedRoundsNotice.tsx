import { useQuery } from "@tanstack/react-query"

import type { TournamentRead } from "@/client"
import { fetchPublicBracket, publicBracketQueryKey } from "./bracket-queries"

export function delayedRoundsText(
  delayedRounds: readonly number[],
  roundNames: readonly string[],
): string {
  const labels = delayedRounds
    .map((round) => {
      const name = roundNames[round - 1]
      return name ? `第 ${round} 輪（${name}）` : `第 ${round} 輪`
    })
    .join("、")
  return `${labels}因前一輪 BO 數較多已順延開始時間，請到場次管理確認。`
}

/**
 * S27 的順延提示（FR-23）：抽籤後（手動或自動）有輪次被順延時顯示，只給主辦方。
 * 順延的輪次由後端的抽籤狀態（`DrawStatus.delayed_rounds`）提供，前端不重算；
 * 輪次名稱取自後端的對戰樹。對戰樹讀取失敗時不顯示提示（靜默），也不影響其他區塊。
 */
export function DelayedRoundsNotice({
  tournament,
  delayedRounds,
}: {
  tournament: Pick<TournamentRead, "id">
  delayedRounds: readonly number[]
}) {
  const bracket = useQuery({
    queryKey: publicBracketQueryKey(tournament.id),
    queryFn: () => fetchPublicBracket(tournament.id),
    enabled: delayedRounds.length > 0,
    retry: false,
  })
  if (delayedRounds.length === 0) return null
  // 等對戰樹回來再顯示（避免先出現輪次號碼、隨後又變成名稱）；讀取失敗靜默不顯示
  if (!bracket.data) return null
  return (
    <section aria-label="順延提示" className="mt-6">
      <p role="status" className="text-body text-muted-foreground">
        {delayedRoundsText(delayedRounds, bracket.data.round_names)}
      </p>
    </section>
  )
}
