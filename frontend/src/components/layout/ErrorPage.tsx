import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import {
  getErrorMessage,
  parseApiError,
  UNEXPECTED_ERROR_MESSAGE,
} from "@/lib/api-error"

const ERROR_TEXT = {
  404: "找不到這個頁面。",
  403: "你沒有權限查看這個頁面。",
} as const

type ErrorPageProps =
  | { status: keyof typeof ERROR_TEXT; message?: never }
  /** 不是 403／404 的錯誤：直接顯示這句訊息（空字串時顯示「發生未預期的錯誤」） */
  | { status?: never; message: string }

/** S38 錯誤頁：一句說明＋「回到首頁」。 */
export function ErrorPage({ status, message }: ErrorPageProps) {
  const text = status ? ERROR_TEXT[status] : message || UNEXPECTED_ERROR_MESSAGE
  return (
    <section className="flex flex-col items-center gap-6 py-20 text-center">
      <h1 className="text-heading-md">{text}</h1>
      <Button asChild>
        <Link to="/">回到首頁</Link>
      </Button>
    </section>
  )
}

export function NotFoundPage() {
  return <ErrorPage status={404} />
}

function isApiNotFound(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false
  const { isAxiosError, response } = error as {
    isAxiosError?: unknown
    response?: { status?: unknown }
  }
  return isAxiosError === true && response?.status === 404
}

/** 路由載入失敗時的錯誤元件：API 回 404／403 顯示 S38，其他錯誤照實顯示訊息。 */
export function RouteErrorPage({ error }: { error: unknown }) {
  if (isApiNotFound(error)) return <ErrorPage status={404} />
  const apiError = parseApiError(error)
  if (apiError.kind === "forbidden") return <ErrorPage status={403} />
  return <ErrorPage message={getErrorMessage(apiError)} />
}
