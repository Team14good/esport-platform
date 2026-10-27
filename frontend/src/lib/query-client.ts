import { QueryClient } from "@tanstack/react-query"

import { parseApiError } from "./api-error"

const MAX_QUERY_RETRIES = 3

/** query 失敗時是否重試：401 不重試（交給登入過期流程），其他錯誤沿用預設的 3 次。 */
export function shouldRetryQuery(
  failureCount: number,
  error: unknown,
): boolean {
  if (parseApiError(error).kind === "unauthorized") return false
  return failureCount < MAX_QUERY_RETRIES
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: shouldRetryQuery } },
  })
}
