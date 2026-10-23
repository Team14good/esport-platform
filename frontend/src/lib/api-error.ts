import type { FieldValues, Path, UseFormReturn } from "react-hook-form"

// 解析產生的 client（@hey-api/client-axios，throwOnError）丟出的錯誤。
// 只依賴 axios 錯誤的形狀（isAxiosError、response.status、response.data.detail），
// 不直接呼叫 axios。伺服器訊息照實顯示，不改寫成泛用文字。

export const NETWORK_ERROR_MESSAGE = "無法連線到伺服器"
export const FORBIDDEN_FALLBACK_MESSAGE = "你沒有權限查看這個頁面。"
export const UNEXPECTED_ERROR_MESSAGE = "發生未預期的錯誤"

export type ApiError =
  | { kind: "validation"; fields: Record<string, string> } // 422，key 取 loc 的最後一段
  | { kind: "business"; code: string; message: string } // 4xx 且 detail 是 {code, message}
  | { kind: "forbidden"; message: string; code?: string } // 403（給 S38 用；有業務代碼時一併保留）
  | { kind: "network"; message: typeof NETWORK_ERROR_MESSAGE }
  | { kind: "unknown"; message: string }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function asBusinessDetail(
  detail: unknown,
): { code: string; message: string } | null {
  if (
    isRecord(detail) &&
    typeof detail.code === "string" &&
    typeof detail.message === "string"
  ) {
    return { code: detail.code, message: detail.message }
  }
  return null
}

function asValidationFields(detail: unknown): Record<string, string> | null {
  if (!Array.isArray(detail)) return null
  const fields: Record<string, string> = {}
  for (const item of detail) {
    if (!isRecord(item) || typeof item.msg !== "string") continue
    const loc = Array.isArray(item.loc) ? item.loc : []
    const key = loc.length > 0 ? String(loc[loc.length - 1]) : ""
    // 同一欄位有多個錯誤時只顯示第一個
    if (!Object.hasOwn(fields, key)) fields[key] = item.msg
  }
  // 一個欄位錯誤都沒有收集到時不算欄位錯誤，改走依狀態碼的訊息
  return Object.keys(fields).length > 0 ? fields : null
}

export function parseApiError(error: unknown): ApiError {
  if (!isRecord(error)) {
    return { kind: "unknown", message: UNEXPECTED_ERROR_MESSAGE }
  }

  const response = isRecord(error.response) ? error.response : undefined
  if (!response) {
    // axios 有送出請求卻沒有回應（伺服器沒開、網路斷線、逾時）
    if (error.isAxiosError === true) {
      return { kind: "network", message: NETWORK_ERROR_MESSAGE }
    }
    return { kind: "unknown", message: UNEXPECTED_ERROR_MESSAGE }
  }

  const status = typeof response.status === "number" ? response.status : 0
  const data = response.data
  const detail = isRecord(data) ? data.detail : undefined
  const business = asBusinessDetail(detail)

  if (status === 422) {
    const fields = asValidationFields(detail)
    if (fields) return { kind: "validation", fields }
  }

  if (status === 403) {
    return business
      ? { kind: "forbidden", message: business.message, code: business.code }
      : {
          kind: "forbidden",
          message:
            typeof detail === "string" ? detail : FORBIDDEN_FALLBACK_MESSAGE,
        }
  }

  if (business && status >= 400 && status < 500) {
    return { kind: "business", ...business }
  }

  if (typeof detail === "string" && detail.length > 0) {
    return { kind: "unknown", message: detail }
  }

  return {
    kind: "unknown",
    message: status ? `伺服器發生錯誤（${status}）` : UNEXPECTED_ERROR_MESSAGE,
  }
}

/** 取出要顯示給使用者的一句話；欄位錯誤合併成一行。 */
export function getErrorMessage(apiError: ApiError): string {
  const text =
    apiError.kind === "validation"
      ? Object.values(apiError.fields).join("；")
      : apiError.message
  return text || UNEXPECTED_ERROR_MESSAGE
}

type FormLike<T extends FieldValues> = Pick<
  UseFormReturn<T>,
  "setError" | "getValues"
>

/**
 * 把 422 欄位錯誤寫進 react-hook-form 對應欄位（欄位名＝loc 的最後一段），
 * 回傳寫不進欄位、要顯示在表單頂部 Alert 的部分；全部都寫進欄位時回傳 null。
 * 表單的每個欄位都要有 defaultValues，才能判斷欄位是否存在。
 */
export function applyFieldErrors<T extends FieldValues>(
  form: FormLike<T>,
  error: unknown,
): ApiError | null {
  const apiError = parseApiError(error)
  if (apiError.kind !== "validation") return apiError

  const values: unknown = form.getValues()
  const formFields = isRecord(values) ? Object.keys(values) : []
  const unmatched: Record<string, string> = {}
  let firstField = true
  for (const [field, message] of Object.entries(apiError.fields)) {
    if (field && formFields.includes(field)) {
      form.setError(
        field as Path<T>,
        { type: "server", message },
        { shouldFocus: firstField },
      )
      firstField = false
    } else {
      unmatched[field] = message
    }
  }

  return Object.keys(unmatched).length > 0
    ? { kind: "validation", fields: unmatched }
    : null
}
