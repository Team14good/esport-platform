import { queryOptions, useQuery } from "@tanstack/react-query"

import {
  type ApplicationStatus,
  IdentityService,
  type OrganizerApplicationRead,
} from "@/client"
import type { StatusTone } from "@/components/common/StatusBadge"
import { ME_QUERY_KEY, useIsSignedIn } from "./auth"

export const organizerApplicationQueryOptions = () =>
  queryOptions({
    queryKey: [...ME_QUERY_KEY, "organizer-application"],
    queryFn: async (): Promise<OrganizerApplicationRead | null> => {
      const { data } = await IdentityService.readCurrentOrganizerApplication()
      // 從沒申請過時後端回 null，但產生的 client 會把 null 回應換成 {}（`data ?? {}`）
      return data && "id" in data ? data : null
    },
  })

/** 目前帳號最新的一筆主辦方申請（沒有時為 null）；未登入時不送請求。 */
export function useMyOrganizerApplication() {
  const signedIn = useIsSignedIn()
  return useQuery({ ...organizerApplicationQueryOptions(), enabled: signedIn })
}

// 以產生的 ApplicationStatus 為鍵：後端新增狀態、重新產生 client 後，忘了補對照會編譯失敗
export const APPLICATION_STATUS_BADGES: Record<
  ApplicationStatus,
  { label: string; tone: StatusTone }
> = {
  pending: { label: "待審核", tone: "appeal" },
  approved: { label: "核准", tone: "confirmed" },
  rejected: { label: "退回", tone: "destructive" },
}
