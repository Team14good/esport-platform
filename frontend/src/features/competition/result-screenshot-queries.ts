// S4 結算截圖（5.7）的查詢：公開圖片（blob）、登入者能不能上傳、上傳。
import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { CompetitionService, type PublicMatchDetail } from "@/client"
import { useIsSignedIn } from "@/features/identity/auth"
import { matchQueryKey, matchVersion, samePlaceholder } from "./match-source"

/**
 * 結算截圖圖片的 query key。刻意不放在 `matchQueryKey` 前綴底下：S4 的 `refresh` 會
 * invalidate 整個前綴（報到、登錄比分、申訴、倒數歸零），圖片不必跟著重新下載。
 * key 帶上傳時間，更換截圖後自然換成新的 key。
 */
export function resultScreenshotImageQueryKey(
  tournamentId: string,
  matchId: string,
  uploadedAt: string | null,
) {
  return [
    "competition",
    "result-screenshot",
    tournamentId,
    matchId,
    uploadedAt,
  ] as const
}

/**
 * 公開的結算截圖：經產生的 client 以 blob 下載，轉成 object URL 給 `<img>`。
 * key 帶上傳時間，勝隊更換截圖後（公開單場的 `result_screenshot_at` 改變）會重新下載。
 * 沒有截圖時不查詢。
 */
export function useResultScreenshotImage(detail: PublicMatchDetail) {
  const tournamentId = detail.tournament.id
  const matchId = detail.id
  const uploadedAt = detail.result_screenshot_at ?? null
  const query = useQuery({
    queryKey: resultScreenshotImageQueryKey(tournamentId, matchId, uploadedAt),
    queryFn: async () =>
      (
        await CompetitionService.downloadResultScreenshot({
          path: { tournament_id: tournamentId, match_id: matchId },
        })
      ).data as Blob,
    enabled: uploadedAt !== null,
    // 同一個上傳時間的圖不會變
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })
  const blob = uploadedAt !== null ? query.data : undefined
  const [url, setUrl] = useState<string | null>(null)
  // 換圖或卸載時釋放 object URL
  useEffect(() => {
    if (!blob) {
      setUrl(null)
      return
    }
    const next = URL.createObjectURL(blob)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [blob])
  return { url, failed: uploadedAt !== null && query.isError }
}

/**
 * 登入者能不能上傳這場的結算截圖（勝隊隊長）；未登入、系列結果未送出時不查詢。
 * key 帶場次版本：申訴更正換勝隊等變動後重抓。
 */
export function useResultScreenshotState(detail: PublicMatchDetail) {
  const signedIn = useIsSignedIn()
  const enabled = signedIn && detail.result_screenshot_enabled === true
  const tournamentId = detail.tournament.id
  const matchId = detail.id
  const query = useQuery({
    queryKey: [
      ...matchQueryKey(tournamentId, matchId),
      "result-screenshot-state",
      ...matchVersion(detail),
      detail.winner_id ?? null,
    ],
    queryFn: async () =>
      (
        await CompetitionService.readResultScreenshotState({
          path: { tournament_id: tournamentId, match_id: matchId },
        })
      ).data,
    enabled,
    placeholderData: samePlaceholder(matchId),
    retry: false,
  })
  return enabled ? query.data : undefined
}

/** 上傳或更換結算截圖；以 `onProgress` 回報 0～100。失敗時拋出（AxiosError）。 */
export async function uploadResultScreenshot({
  tournamentId,
  matchId,
  file,
  onProgress,
}: {
  tournamentId: string
  matchId: string
  file: File
  onProgress?: (percent: number) => void
}) {
  return (
    await CompetitionService.uploadResultScreenshot({
      path: { tournament_id: tournamentId, match_id: matchId },
      body: { screenshot: file },
      onUploadProgress: onProgress
        ? (event) => {
            if (event.total) onProgress((event.loaded / event.total) * 100)
          }
        : undefined,
    })
  ).data
}
