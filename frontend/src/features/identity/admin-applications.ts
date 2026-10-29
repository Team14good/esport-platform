import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import { type ApplicationStatus, IdentityService } from "@/client"
import { notifySuccess } from "@/lib/feedback"

export const APPROVED_TOAST_TEXT = "已核准主辦方申請。"
export const REJECTED_TOAST_TEXT = "已退回主辦方申請。"
export const REJECT_REASON_MAX_LENGTH = 200

/** S35 的篩選：申請狀態，或「全部」。 */
export type ApplicationFilter = ApplicationStatus | "all"
export const DEFAULT_FILTER: ApplicationFilter = "pending"

export const APPLICATION_FILTERS: {
  value: ApplicationFilter
  label: string
}[] = [
  { value: "pending", label: "待審核" },
  { value: "approved", label: "核准" },
  { value: "rejected", label: "退回" },
  { value: "all", label: "全部" },
]

/** S35 網址上的查詢參數；省略代表預設值（待審核、第 1 頁）。 */
export type ApplicationsSearch = { status?: ApplicationFilter; page?: number }

/** 解析網址的 `status`：不認得的值當成預設（待審核），網址上不留預設值。 */
export function parseFilter(value: unknown): ApplicationFilter | undefined {
  const match = APPLICATION_FILTERS.find((filter) => filter.value === value)
  return match && match.value !== DEFAULT_FILTER ? match.value : undefined
}

/** 解析網址的 `page`：不是大於 1 的整數時當成第 1 頁，網址上不留預設值。 */
export function parsePage(value: unknown): number | undefined {
  const page = typeof value === "string" ? Number(value) : value
  return typeof page === "number" && Number.isInteger(page) && page > 1
    ? page
    : undefined
}

const ADMIN_APPLICATIONS_KEY = ["identity", "admin", "organizer-applications"]

export const adminApplicationsQueryOptions = (
  filter: ApplicationFilter,
  page: number,
) =>
  queryOptions({
    queryKey: [...ADMIN_APPLICATIONS_KEY, { filter, page }],
    queryFn: async () =>
      (
        await IdentityService.listOrganizerApplications({
          query: { status: filter === "all" ? undefined : filter, page },
        })
      ).data,
  })

/** S35 的申請列表；換篩選或換頁時先保留上一頁的資料，不再顯示 Skeleton。 */
export function useAdminApplications(filter: ApplicationFilter, page: number) {
  return useQuery({
    ...adminApplicationsQueryOptions(filter, page),
    placeholderData: keepPreviousData,
  })
}

/** 重新抓取 S35 的列表（審核成功，或審核失敗後關閉對話框時）。 */
export function useRefreshAdminApplications(): () => Promise<void> {
  const queryClient = useQueryClient()
  return () =>
    queryClient.invalidateQueries({ queryKey: ADMIN_APPLICATIONS_KEY })
}

export function useApproveApplication() {
  const refresh = useRefreshAdminApplications()
  return useMutation({
    mutationFn: async (applicationId: string) =>
      (
        await IdentityService.approveOrganizerApplication({
          path: { application_id: applicationId },
        })
      ).data,
    onSuccess: () => {
      notifySuccess(APPROVED_TOAST_TEXT)
      // 不等重新抓取：先讓對話框關閉，列表再更新
      void refresh()
    },
  })
}

export function useRejectApplication() {
  const refresh = useRefreshAdminApplications()
  return useMutation({
    mutationFn: async ({
      applicationId,
      reason,
    }: {
      applicationId: string
      reason: string
    }) =>
      (
        await IdentityService.rejectOrganizerApplication({
          path: { application_id: applicationId },
          body: { reason },
        })
      ).data,
    onSuccess: () => {
      notifySuccess(REJECTED_TOAST_TEXT)
      void refresh()
    },
  })
}
