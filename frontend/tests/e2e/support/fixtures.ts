// 端對端測試共用的 fixture：所有測試從這裡 import `test` 與 `expect`。
// - 記錄每個送往 API 的請求的回應時間，附在測試報告（api-timings.json），給 7.3 彙整 NFR-2。
// - 一般請求超過 1 秒就讓測試失敗並列出網址；登入（密碼雜湊）只記錄不判定。
// - `newRoleContext` 為每個角色開獨立的 browser context（各自的 localStorage＝各自的登入狀態）。
import { type BrowserContext, test as base } from "@playwright/test"

import { API_URL } from "./env"

export { expect } from "@playwright/test"

export type ApiTiming = {
  /** 送出請求的角色（browser context） */
  role: string
  method: string
  url: string
  status: number | null
  /** 從送出請求到收完回應的毫秒數；瀏覽器沒有提供時為 null */
  durationMs: number | null
  /** 不判定 1 秒限制的原因；一般請求為 null */
  exempt: string | null
}

export const SLOW_API_THRESHOLD_MS = 1_000

/** 只記錄、不判定 1 秒限制的 API（NFR-2 的「一般操作」不含這些） */
const EXEMPT_ROUTES: { method: string; path: string; reason: string }[] = [
  { method: "POST", path: "/api/v1/access-tokens", reason: "登入（密碼雜湊）" },
]

function exemptionFor(method: string, url: string): string | null {
  const { pathname } = new URL(url)
  return (
    EXEMPT_ROUTES.find(
      (route) => route.method === method && route.path === pathname,
    )?.reason ?? null
  )
}

function trackApiTimings(
  context: BrowserContext,
  role: string,
  timings: ApiTiming[],
) {
  context.on("requestfinished", async (request) => {
    const url = request.url()
    if (!url.startsWith(`${API_URL}/api/`)) return
    const { responseEnd } = request.timing()
    const response = await request.response().catch(() => null)
    timings.push({
      role,
      method: request.method(),
      url,
      status: response?.status() ?? null,
      durationMs: responseEnd >= 0 ? Math.round(responseEnd) : null,
      exempt: exemptionFor(request.method(), url),
    })
  })
}

type E2EFixtures = {
  apiTimings: ApiTiming[]
  /** 開一個新角色的 browser context（沿用專案的 viewport 等設定），測試結束時關閉 */
  newRoleContext: (role: string) => Promise<BrowserContext>
  apiTimingReport: undefined
}

export const test = base.extend<E2EFixtures>({
  // biome-ignore lint/correctness/noEmptyPattern: Playwright 的 fixture 一定要用物件解構
  apiTimings: async ({}, use) => {
    await use([])
  },
  context: async ({ context, apiTimings }, use) => {
    trackApiTimings(context, "預設", apiTimings)
    await use(context)
  },
  newRoleContext: async ({ browser, apiTimings }, use) => {
    const contexts: BrowserContext[] = []
    await use(async (role) => {
      const context = await browser.newContext()
      trackApiTimings(context, role, apiTimings)
      contexts.push(context)
      return context
    })
    await Promise.all(contexts.map((context) => context.close()))
  },
  // auto fixture 最先建立、最後拆除：拆除時所有 context 都已關閉，記錄是完整的
  apiTimingReport: [
    async ({ apiTimings }, use, testInfo) => {
      await use(undefined)
      await testInfo.attach("api-timings.json", {
        body: JSON.stringify(apiTimings, null, 2),
        contentType: "application/json",
      })
      const slow = apiTimings.filter(
        (timing) =>
          timing.exempt === null &&
          timing.durationMs !== null &&
          timing.durationMs > SLOW_API_THRESHOLD_MS,
      )
      if (slow.length > 0) {
        throw new Error(
          `以下 API 請求超過 ${SLOW_API_THRESHOLD_MS} ms（NFR-2）：\n${slow
            .map(
              (timing) =>
                `${timing.method} ${timing.url} → ${timing.status ?? "?"}（${timing.durationMs} ms，${timing.role}）`,
            )
            .join("\n")}`,
        )
      }
    },
    { auto: true },
  ],
})
