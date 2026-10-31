import { useState } from "react"

type FailureBaseline = {
  /** 上一次成功的時間（dataUpdatedAt） */
  successAt: number
  /** 上一次成功時累計的失敗次數（errorUpdateCount） */
  errorsAtSuccess: number
}

/**
 * 輪詢 hook 共用：由 TanStack Query 的 dataUpdatedAt 與 errorUpdateCount 算出「最後一次成功之後連續失敗幾次」。
 * 成功一次（dataUpdatedAt 改變）就歸零。
 */
export function useConsecutiveFailures(
  dataUpdatedAt: number,
  errorUpdateCount: number,
): number {
  const [baseline, setBaseline] = useState<FailureBaseline>({
    successAt: dataUpdatedAt,
    errorsAtSuccess: errorUpdateCount,
  })
  let errorsAtSuccess = baseline.errorsAtSuccess
  if (baseline.successAt !== dataUpdatedAt) {
    errorsAtSuccess = errorUpdateCount
    setBaseline({ successAt: dataUpdatedAt, errorsAtSuccess })
  }
  return errorUpdateCount - errorsAtSuccess
}
