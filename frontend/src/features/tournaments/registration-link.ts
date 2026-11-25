import {
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"

import { TournamentsService } from "@/client"

/**
 * 自訂賽事的賽事報名連結（Story 3.10）。token 只由主辦方專用端點回傳；S2 只能經公開的
 * 檢查端點得知網址上的 `invite` 是否有效。
 */

export const REGISTRATION_LINK_LABEL = "賽事報名連結"
export const REGISTRATION_LINK_DESCRIPTION = "持有這個連結的帳號才能建立隊伍。"
export const RESET_REGISTRATION_LINK_TEXT = "重設報名連結"
export const RESET_REGISTRATION_LINK_CONFIRM_TEXT =
  "重設後舊連結立即失效，已建立的隊伍不受影響。"
export const REGISTRATION_LINK_RESET_TEXT = "已重設報名連結"
/** S1 卡片的標籤 */
export const INVITE_ONLY_TEXT = "邀請制報名"
/** S2：已登入、沒有帶連結 */
export const INVITE_MISSING_TEXT = "這是邀請制賽事，請向主辦方索取報名連結。"
/** S2：已登入、連結不符（已重設或亂打） */
export const INVITE_EXPIRED_TEXT = "報名連結已失效，請向主辦方索取新的連結。"
/** S2：未登入、帶了連結 */
export const INVITE_SIGN_IN_TEXT = "登入後即可建立隊伍。"

/** 賽事報名連結的網址：S2 加查詢參數 `invite`。 */
export function registrationLinkUrl(
  tournamentId: string,
  token: string,
  origin: string = window.location.origin,
): string {
  return `${origin}${registrationLinkPath(tournamentId, token)}`
}

/** 站內路徑（登入後回到原頁的 redirect 也用它）；token 經 URL 編碼。 */
export function registrationLinkPath(tournamentId: string, token: string) {
  return `/tournaments/${tournamentId}?invite=${encodeURIComponent(token)}`
}

/** S27：主辦方讀取自訂賽事的賽事報名連結。 */
export const registrationLinkQueryOptions = (tournamentId: string) =>
  queryOptions({
    queryKey: ["tournaments", "organizer", "registration-link", tournamentId],
    queryFn: async () =>
      (
        await TournamentsService.readRegistrationLink({
          path: { tournament_id: tournamentId },
        })
      ).data,
  })

/** S2：網址上的 `invite` 是否為這場賽事目前的報名連結（不需登入）。 */
export const registrationLinkStatusQueryOptions = (
  tournamentId: string,
  invite: string,
) =>
  queryOptions({
    queryKey: ["tournaments", tournamentId, "registration-link-status", invite],
    queryFn: async () =>
      (
        await TournamentsService.readRegistrationLinkStatus({
          path: { tournament_id: tournamentId },
          query: { invite },
        })
      ).data,
  })

/** 重設賽事報名連結；成功後以回傳值更新 S27 的快取。 */
export function useResetRegistrationLink(tournamentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (
        await TournamentsService.resetRegistrationLink({
          path: { tournament_id: tournamentId },
        })
      ).data,
    onSuccess: (link) => {
      queryClient.setQueryData(
        registrationLinkQueryOptions(tournamentId).queryKey,
        link,
      )
    },
  })
}
