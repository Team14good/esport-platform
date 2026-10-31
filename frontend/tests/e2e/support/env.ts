// 端對端測試的環境設定；compose 的 e2e 服務會傳入這些變數，在主機上執行時用預設值。

/** 瀏覽器呼叫的 API 網址（與前端 VITE_API_URL 相同） */
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000"

/** Mailpit 的 HTTP API（測試程式直接呼叫，不經過瀏覽器） */
export const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025"

/** 平台管理員帳號（與後端建立首位平台管理員的 FIRST_ADMIN_* 相同） */
export function platformAdminCredentials(): {
  email: string
  password: string
} {
  const email = process.env.FIRST_ADMIN_EMAIL
  const password = process.env.FIRST_ADMIN_PASSWORD
  if (!email || !password) {
    throw new Error(
      "缺少 FIRST_ADMIN_EMAIL 或 FIRST_ADMIN_PASSWORD；請用 docker compose --profile e2e run --rm e2e 執行",
    )
  }
  return { email, password }
}
