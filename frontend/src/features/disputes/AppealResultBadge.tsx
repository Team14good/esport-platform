import { useQuery } from "@tanstack/react-query"

import { DisputesService, type PublicMatchDetail } from "@/client"
import { StatusBadge } from "@/components/common/StatusBadge"
import {
  matchQueryKey,
  matchVersion,
} from "@/features/competition/match-source"
import { DECISION_LABEL } from "./decision-label"

/** 公開申訴結果的 query key：接在這一場的 key 後面，場次版本改變就重抓。 */
export function appealResultQueryKey(detail: PublicMatchDetail) {
  return [
    ...matchQueryKey(detail.tournament.id, detail.id),
    "appeal-result",
    ...matchVersion(detail),
  ] as const
}

/**
 * S4 頁首（6.2）：經申訴處理的已確認場次顯示「維持原結果」或「更正結果」。
 * 公開 API，不需登入；不含申訴內容。其他狀態不查詢、不顯示。
 */
export function AppealResultBadge({ detail }: { detail: PublicMatchDetail }) {
  const enabled = detail.status === "confirmed"
  const query = useQuery({
    queryKey: appealResultQueryKey(detail),
    queryFn: async () =>
      (
        await DisputesService.readAppealResult({
          path: { tournament_id: detail.tournament.id, match_id: detail.id },
        })
      ).data,
    enabled,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  })
  const decision = enabled ? query.data?.decision : null
  if (!decision) return null
  return <StatusBadge tone="muted">{DECISION_LABEL[decision]}</StatusBadge>
}
