import { useMutation, useQueryClient } from "@tanstack/react-query"

import { IdentityService } from "@/client"
import { notifySuccess } from "@/lib/feedback"

export const SCHOOL_CREATED_TOAST_TEXT = "已新增學校"
export const SCHOOL_RENAMED_TOAST_TEXT = "已修正學校名稱"
// 與後端 `SCHOOL_NAME_MAX_LENGTH` 相同
export const SCHOOL_NAME_MAX_LENGTH = 255
// 與 `useSchools()`（schools.ts）的 queryKey 相同
export const SCHOOLS_QUERY_KEY = ["identity", "schools"]

/**
 * 學校清單異動後讓 `["identity","schools"]` 失效：S36 的清單，以及註冊、主辦方申請、
 * 帳號頁的學校選單（同一個查詢，`staleTime: Infinity`）都會立即重抓。
 */
function useInvalidateSchools(): () => Promise<void> {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: SCHOOLS_QUERY_KEY })
}

export function useCreateSchool() {
  const invalidate = useInvalidateSchools()
  return useMutation({
    mutationFn: async (name: string) =>
      (await IdentityService.createSchool({ body: { name } })).data,
    onSuccess: () => {
      notifySuccess(SCHOOL_CREATED_TOAST_TEXT)
      void invalidate()
    },
  })
}

export function useRenameSchool() {
  const invalidate = useInvalidateSchools()
  return useMutation({
    mutationFn: async ({
      schoolId,
      name,
    }: {
      schoolId: string
      name: string
    }) =>
      (
        await IdentityService.renameSchool({
          path: { school_id: schoolId },
          body: { name },
        })
      ).data,
    onSuccess: () => {
      notifySuccess(SCHOOL_RENAMED_TOAST_TEXT)
      void invalidate()
    },
  })
}
