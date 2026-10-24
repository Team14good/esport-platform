import { useQuery } from "@tanstack/react-query"

import { IdentityService } from "@/client"

/** 公開的學校清單；變動很少，整個工作階段只抓一次。 */
export function useSchools() {
  return useQuery({
    queryKey: ["identity", "schools"],
    queryFn: async () => (await IdentityService.listSchools()).data,
    staleTime: Number.POSITIVE_INFINITY,
  })
}
