// S4 申訴入口的資料：登入者本隊的申訴狀態，以及送出申訴（multipart）。
import { useQuery } from "@tanstack/react-query"

import { DisputesService, type PublicMatchDetail } from "@/client"
import {
  matchQueryKey,
  matchVersion,
  samePlaceholder,
} from "@/features/competition/match-source"
import { useIsSignedIn } from "@/features/identity/auth"

/** 可以提出申訴、S4 顯示申訴期區塊的場次狀態 */
export const APPEALABLE_STATUSES: ReadonlySet<PublicMatchDetail["status"]> =
  new Set(["appeal_window", "appealed"])

/**
 * 申訴狀態的 query key：接在這一場的 `matchQueryKey` 後面（invalidate 前綴就會重抓），
 * 再帶場次版本，場次有變動（例如另一隊申訴讓場次轉為申訴中）就重抓。
 */
export function appealStateQueryKey(detail: PublicMatchDetail) {
  return [
    ...matchQueryKey(detail.tournament.id, detail.id),
    "appeal-state",
    ...matchVersion(detail),
  ] as const
}

/**
 * 登入者本隊的申訴狀態；未登入、場次不在申訴期／申訴中時不查詢（`state` 為 undefined）。
 * `isPlaceholder`：場次版本改變、新狀態還沒回來時，`state` 是上一個版本的資料。
 */
export function useAppealState(detail: PublicMatchDetail) {
  const signedIn = useIsSignedIn()
  const enabled = signedIn && APPEALABLE_STATUSES.has(detail.status)
  const query = useQuery({
    queryKey: appealStateQueryKey(detail),
    queryFn: async () =>
      (
        await DisputesService.readAppealState({
          path: { tournament_id: detail.tournament.id, match_id: detail.id },
        })
      ).data,
    enabled,
    placeholderData: samePlaceholder(detail.id),
    retry: false,
  })
  return enabled
    ? { state: query.data, isPlaceholder: query.isPlaceholderData }
    : { state: undefined, isPlaceholder: false }
}

export type AppealValues = {
  description: string
  /** 選填的截圖 */
  attachment: File | null
}

/** 送出申訴；上傳截圖時以 `onProgress` 回報 0～100。失敗時拋出（AxiosError）。 */
export async function fileAppeal({
  tournamentId,
  matchId,
  values,
  onProgress,
}: {
  tournamentId: string
  matchId: string
  values: AppealValues
  onProgress?: (percent: number) => void
}) {
  const attachment = values.attachment
  return (
    await DisputesService.fileAppeal({
      path: { tournament_id: tournamentId, match_id: matchId },
      body: {
        description: values.description,
        attachment: attachment ?? undefined,
      },
      onUploadProgress:
        attachment && onProgress
          ? (event) => {
              if (event.total) onProgress((event.loaded / event.total) * 100)
            }
          : undefined,
    })
  ).data
}
