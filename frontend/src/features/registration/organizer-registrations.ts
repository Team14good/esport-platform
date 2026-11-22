// S29 報名清單（Story 3.8）：篩選、查詢、段位截圖（授權 blob）與退回報名。
import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { useEffect, useState } from "react"

import {
  type OrganizerRegistrationMember,
  RegistrationService,
  type RegistrationStatus,
  type TournamentRead,
} from "@/client"
import { notifySuccess } from "@/lib/feedback"
import { REGISTRATION_QUERY_KEY } from "./queries"
import { REGISTRATION_STATUS_LABELS } from "./registration-status"

export const ORGANIZER_REGISTRATIONS_TITLE = "報名清單"
export const NO_REGISTRATIONS_TEXT = "還沒有隊伍報名。"
export const FILTERED_EMPTY_TEXT = "沒有符合篩選條件的報名。"
export const COPY_TOURNAMENT_LINK_TEXT = "複製賽事頁連結"
export const RANK_SCREENSHOT_TEXT = "段位截圖"
export const REJECT_TEXT = "退回報名"
export const REJECT_REASON_LABEL = "退回原因"
export const REJECT_REASON_MAX_LENGTH = 200
export const REJECTED_TOAST_TEXT = "已退回報名"
export const NOT_UPLOADED_TEXT = "未上傳"
export const SCREENSHOT_FAILED_TEXT = "無法載入段位截圖。"
export const PREVIOUS_MEMBER_TEXT = "上一位"
export const NEXT_MEMBER_TEXT = "下一位"

/** 退回確認對話框的內文：依賽事狀態（開放報名可重送；報名截止後不可重送）。 */
export const REJECT_DESCRIPTIONS = {
  open: "退回後隊伍名單會解鎖，隊伍可在報名截止前修正後重新送出。若隊伍是正取，名額會由候補遞補。",
  closed:
    "報名已截止，退回後隊伍無法重新送出。若隊伍是正取，名額會由候補遞補。",
} as const

/**
 * 退回確認對話框的內文：仍在報名期間（開放報名且未過截止時間）才是可重送的內文，
 * 與後端通知的 `can_resubmit` 相同；截止時間到了、賽事還沒轉為報名截止時也是不可重送。
 */
export function rejectDescription(
  tournament: Pick<TournamentRead, "status" | "registration_end"> | undefined,
  now: Date = new Date(),
): string {
  const resubmittable =
    tournament?.status === "open" &&
    now.getTime() < new Date(tournament.registration_end).getTime()
  return resubmittable ? REJECT_DESCRIPTIONS.open : REJECT_DESCRIPTIONS.closed
}

/** S29 的篩選：報名狀態，或「全部」（組隊中沒有送出，不會出現在清單）。 */
export type RegistrationFilter = Exclude<RegistrationStatus, "forming"> | "all"
export const DEFAULT_REGISTRATION_FILTER: RegistrationFilter = "all"

// 順序與清單的預設分組相同
const FILTER_STATUSES: Exclude<RegistrationStatus, "forming">[] = [
  "accepted",
  "waitlisted",
  "pending",
  "drawn",
  "retired",
  "rejected",
  "withdrawn",
  "disqualified",
]

export const REGISTRATION_FILTERS: {
  value: RegistrationFilter
  label: string
}[] = [
  { value: "all", label: "全部" },
  ...FILTER_STATUSES.map((status) => ({
    value: status,
    label: REGISTRATION_STATUS_LABELS[status],
  })),
]

/** S29 網址上的查詢參數；省略代表預設值（全部、第 1 頁）。 */
export type OrganizerRegistrationsSearch = {
  status?: RegistrationFilter
  page?: number
}

/** 解析網址的 `status`：不認得的值當成「全部」，網址上不留預設值。 */
export function parseRegistrationFilter(
  value: unknown,
): RegistrationFilter | undefined {
  const match = REGISTRATION_FILTERS.find((filter) => filter.value === value)
  return match && match.value !== DEFAULT_REGISTRATION_FILTER
    ? match.value
    : undefined
}

const ORGANIZER_REGISTRATIONS_KEY = [
  ...REGISTRATION_QUERY_KEY,
  "organizer-registrations",
] as const

export const organizerRegistrationsQueryOptions = (
  tournamentId: string,
  filter: RegistrationFilter,
  page: number,
) =>
  queryOptions({
    queryKey: [...ORGANIZER_REGISTRATIONS_KEY, tournamentId, { filter, page }],
    queryFn: async () =>
      (
        await RegistrationService.listOrganizerRegistrations({
          path: { tournament_id: tournamentId },
          query: { status: filter === "all" ? undefined : filter, page },
        })
      ).data,
  })

/** S29 的報名清單；換篩選或換頁時先保留上一頁的資料，不再顯示 Skeleton。 */
export function useOrganizerRegistrations(
  tournamentId: string,
  filter: RegistrationFilter,
  page: number,
) {
  return useQuery({
    ...organizerRegistrationsQueryOptions(tournamentId, filter, page),
    placeholderData: keepPreviousData,
  })
}

/** 退回報名；成功或失敗都讓這場賽事的清單重新取得（狀態、順位與遞補都可能改變）。 */
export function useRejectRegistration(tournamentId: string) {
  const queryClient = useQueryClient()
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: [...ORGANIZER_REGISTRATIONS_KEY, tournamentId],
    })
  return useMutation({
    mutationFn: async ({
      registrationId,
      reason,
    }: {
      registrationId: string
      reason: string
    }) =>
      (
        await RegistrationService.rejectRegistration({
          path: {
            tournament_id: tournamentId,
            registration_id: registrationId,
          },
          body: { reason },
        })
      ).data,
    onSuccess: () => {
      void refresh()
      notifySuccess(REJECTED_TOAST_TEXT)
    },
    onError: () => {
      void refresh()
    },
  })
}

/**
 * 段位截圖圖片的 query key：帶截圖版本（鍵值的雜湊），隊員換截圖後換成新的 key，
 * 不會顯示快取的舊圖。
 */
export function rankScreenshotQueryKey(
  tournamentId: string,
  registrationId: string,
  accountId: string,
  version: string | null,
) {
  return [
    ...REGISTRATION_QUERY_KEY,
    "rank-screenshot",
    tournamentId,
    registrationId,
    accountId,
    version,
  ] as const
}

/**
 * 隊員的段位截圖：經產生的 client 以授權 blob 下載，轉成 object URL 給 `<img>`。
 * 沒有截圖時不查詢。
 */
export function useRankScreenshotImage(
  tournamentId: string,
  registrationId: string,
  member: OrganizerRegistrationMember,
) {
  const version = member.rank_screenshot_version ?? null
  const enabled = member.has_rank_screenshot && version !== null
  const query = useQuery({
    queryKey: rankScreenshotQueryKey(
      tournamentId,
      registrationId,
      member.account_id,
      version,
    ),
    queryFn: async () =>
      (
        await RegistrationService.downloadRankScreenshot({
          path: {
            tournament_id: tournamentId,
            registration_id: registrationId,
            account_id: member.account_id,
          },
        })
      ).data as Blob,
    enabled,
    // 同一個版本的圖不會變
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })
  const blob = enabled ? query.data : undefined
  const [image, setImage] = useState<{ blob: Blob; url: string } | null>(null)
  // 換圖或卸載時釋放 object URL
  useEffect(() => {
    if (!blob) {
      setImage(null)
      return
    }
    const url = URL.createObjectURL(blob)
    setImage({ blob, url })
    return () => URL.revokeObjectURL(url)
  }, [blob])
  // 換隊員或換圖的那一次 render，effect 還沒更新：只回傳屬於目前 blob 的網址，不閃出舊圖
  const url = image && image.blob === blob ? image.url : null
  return { url, failed: enabled && query.isError }
}

/** 賽事頁（S2）的完整網址：空狀態的「複製賽事頁連結」。 */
export function tournamentPageUrl(tournamentId: string): string {
  return `${window.location.origin}/tournaments/${encodeURIComponent(tournamentId)}`
}
