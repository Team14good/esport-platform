import { toast } from "sonner"

import { getErrorMessage, parseApiError } from "./api-error"

export const SUCCESS_TOAST_DURATION = 3000

/** 非表單動作失敗：錯誤 Toast 顯示伺服器訊息，不會自動消失，要使用者關閉。 */
export function notifyError(error: unknown): void {
  const message = getErrorMessage(parseApiError(error))
  // 以訊息當 id：同樣的錯誤重複發生時只留一則，不會堆疊
  toast.error(message, { id: message, duration: Infinity, closeButton: true })
}

/** 動作成功：一句話的成功 Toast，3 秒後消失。 */
export function notifySuccess(text: string): void {
  toast.success(text, { duration: SUCCESS_TOAST_DURATION })
}
