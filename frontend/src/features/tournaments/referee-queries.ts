// Story 2.7 裁判邀請：S31 裁判管理（主辦方）與 S23 接受裁判邀請的 query 與 mutation。
import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import { type RefereeInvitationRead, TournamentsService } from "@/client"
import { identitiesQueryOptions } from "@/features/identity/auth"
import { parseApiError } from "@/lib/api-error"
import { shouldRetryQuery } from "@/lib/query-client"

export const REFEREE_INVITATION_NOT_FOUND = "REFEREE_INVITATION_NOT_FOUND"
export const REFEREE_INVITATION_EXPIRED = "REFEREE_INVITATION_EXPIRED"
export const TOURNAMENT_NOT_ACCEPTING_REFEREES =
  "TOURNAMENT_NOT_ACCEPTING_REFEREES"
export const ORGANIZER_CANNOT_BE_REFEREE = "ORGANIZER_CANNOT_BE_REFEREE"

/** S23 與 S31 共用：賽事已結束或已取消時的說明。 */
export const NOT_ACCEPTING_TEXT = "這場賽事已結束或已取消，無法接受裁判邀請。"

/** 業務錯誤的代碼；不是業務錯誤時為 null。 */
export function businessErrorCode(error: unknown): string | null {
  const parsed = parseApiError(error)
  return parsed.kind === "business" ? parsed.code : null
}

/** 403 與業務錯誤（4xx）重試也不會成功。 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  const { kind } = parseApiError(error)
  return (
    kind !== "forbidden" &&
    kind !== "business" &&
    shouldRetryQuery(failureCount, error)
  )
}

/** S23 的站內路徑；登入、註冊的 redirect 也用這個，與邀請連結的編碼一致。 */
export function refereeInvitePath(token: string): string {
  return `/referee-invite/${encodeURIComponent(token)}`
}

/** S23 的邀請連結（完整網址）；S31 的 Invite link field 顯示這個。 */
export function refereeInviteUrl(token: string): string {
  return `${window.location.origin}${refereeInvitePath(token)}`
}

/** S31：同賽事最新的一筆裁判邀請（含是否過期、賽事是否仍接受裁判）；從未產生過為 null。 */
export const refereeInvitationQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "referee-invitation", tournamentId],
    queryFn: async (): Promise<RefereeInvitationRead | null> => {
      const { data } = await TournamentsService.readRefereeInvitation({
        path: { tournament_id: tournamentId },
      })
      // 從未產生過時後端回 null，但產生的 client 會把 null 回應換成 {}（`data ?? {}`）
      return data && "token" in data ? data : null
    },
    retry: shouldRetry,
  })

/**
 * S31：已接受邀請的裁判（依接受時間排序）。query key 與 S30 的
 * `tournamentRefereesQueryOptions` 相同，兩頁共用同一份快取。
 */
export const refereesQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "referees", tournamentId],
    queryFn: async () =>
      (
        await TournamentsService.listTournamentReferees({
          path: { tournament_id: tournamentId },
        })
      ).data,
    retry: shouldRetry,
  })

/** S23：不需登入的邀請預覽。 */
export const refereeInvitePreviewQueryOptions = (token: string) =>
  queryOptions({
    queryKey: ["tournaments", "referee-invite", token],
    queryFn: async () =>
      (await TournamentsService.previewRefereeInvitation({ path: { token } }))
        .data,
    retry: shouldRetry,
  })

/** 產生新的裁判邀請（舊的立即失效）；成功後填入並讓目前邀請重抓。 */
export function useCreateRefereeInvitation(tournamentId: string) {
  const queryClient = useQueryClient()
  const queryKey = refereeInvitationQueryOptions(tournamentId).queryKey
  return useMutation({
    mutationFn: async () =>
      (
        await TournamentsService.createRefereeInvitation({
          path: { tournament_id: tournamentId },
        })
      ).data,
    onSuccess: (created) => {
      queryClient.setQueryData(queryKey, created)
    },
    // 例如賽事已在別處結束（409 TOURNAMENT_NOT_ACCEPTING_REFEREES）：重抓以更新 `accepting`
    onError: () => {
      void queryClient.invalidateQueries({ queryKey })
    },
  })
}

/** 接受裁判邀請；成功後讓身分清單重抓（身分切換器出現「裁判」）。 */
export function useAcceptRefereeInvitation(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (await TournamentsService.acceptRefereeInvitation({ path: { token } }))
        .data,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: identitiesQueryOptions().queryKey,
      })
    },
    // 邀請已過期或賽事已結束：重抓預覽，卡片不再顯示「{時間} 到期」
    onError: (error) => {
      const code = businessErrorCode(error)
      if (
        code === REFEREE_INVITATION_EXPIRED ||
        code === TOURNAMENT_NOT_ACCEPTING_REFEREES
      ) {
        void queryClient.invalidateQueries({
          queryKey: refereeInvitePreviewQueryOptions(token).queryKey,
        })
      }
    },
  })
}
