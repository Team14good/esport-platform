// 從 Mailpit 的 HTTP API 取信（https://mailpit.axllent.org/docs/api-v1/）。
// worker 每 WORKER_POLL_SECONDS（預設 20 秒）寄一次信，所以要輪詢等待。
import { MAILPIT_URL } from "./env"

type MailpitAddress = { Address: string }
type MailpitSummary = { ID: string; Subject: string; To: MailpitAddress[] }
type MailpitList = { messages: MailpitSummary[] | null }
export type MailpitMessage = { Subject: string; Text: string; HTML: string }

/** 驗證信主旨（backend/app/modules/notifications/service.py） */
export const VERIFICATION_SUBJECT = "完成 FLOW 的 Email 驗證"

const POLL_INTERVAL_MS = 2_000
const DEFAULT_TIMEOUT_MS = 60_000

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${MAILPIT_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Mailpit ${path} 回應 HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

async function recentRecipients(): Promise<string[]> {
  const recent = await getJson<MailpitList>("/api/v1/messages?limit=20")
  const addresses = (recent.messages ?? []).flatMap((message) =>
    message.To.map((to) => to.Address),
  )
  return [...new Set(addresses)]
}

/** 等寄給 `to`、主旨為 `subject` 的信；逾時就失敗並列出 Mailpit 最近的收件人。 */
export async function waitForEmail(
  to: string,
  subject: string,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<MailpitMessage> {
  const query = encodeURIComponent(`to:"${to}"`)
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const list = await getJson<MailpitList>(
      `/api/v1/search?query=${query}&limit=50`,
    )
    const found = (list.messages ?? []).find(
      (message) => message.Subject === subject,
    )
    if (found) return getJson<MailpitMessage>(`/api/v1/message/${found.ID}`)
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }
  const recipients = await recentRecipients()
  throw new Error(
    `${timeoutMs / 1000} 秒內沒有收到寄給 ${to} 的「${subject}」。` +
      `Mailpit 最近的收件人：${recipients.length > 0 ? recipients.join("、") : "（沒有任何信）"}`,
  )
}

/** 取出信中第一個指向 `pathname` 的連結（優先用純文字內容）。 */
export function extractLink(message: MailpitMessage, pathname: string): string {
  const sources = [message.Text, message.HTML.replace(/&amp;/g, "&")]
  const escaped = pathname.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const pattern = new RegExp(`https?://[^\\s"'<>]+${escaped}\\?[^\\s"'<>]+`)
  for (const source of sources) {
    const match = pattern.exec(source)
    if (match) return match[0]
  }
  throw new Error(`信「${message.Subject}」裡找不到 ${pathname} 的連結`)
}

/** 等驗證信並取出驗證連結（${FRONTEND_HOST}/verify-email?token=…）。 */
export async function waitForVerificationLink(email: string): Promise<string> {
  const message = await waitForEmail(email, VERIFICATION_SUBJECT)
  return extractLink(message, "/verify-email")
}
