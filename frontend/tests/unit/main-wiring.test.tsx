import { waitFor } from "@testing-library/react"
import {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios"
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { client } from "@/client/client.gen"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  getAccessToken,
  setAccessToken,
} from "@/features/identity/auth"
import { ACCOUNT } from "./auth-fixtures"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 正式啟動程式 `src/main.tsx` 在模組載入時建立 router 與 QueryClient，並呼叫
// `configureApiClient` 接上 Bearer 標頭與 401 攔截器。這裡真的載入 main.tsx（只載入一次），
// 所以刪掉那一行接線，下面兩個測試都會失敗。

type CapturedRequest = { url?: string; authorization?: unknown }

const requests: CapturedRequest[] = []
let unauthorized = false

function respond(config: InternalAxiosRequestConfig): AxiosResponse {
  const status = unauthorized ? 401 : 200
  const data = unauthorized
    ? { detail: { code: "AUTHENTICATION_REQUIRED", message: "請先登入。" } }
    : config.url?.endsWith("/api/v1/accounts/me")
      ? ACCOUNT
      : []
  return { status, statusText: "", data, headers: {}, config }
}

describe("main.tsx 啟動接線", () => {
  beforeAll(async () => {
    client.setConfig({
      adapter: async (config: InternalAxiosRequestConfig) => {
        requests.push({
          url: config.url,
          authorization: config.headers.get("Authorization"),
        })
        const result = respond(config)
        if (result.status >= 400) {
          throw new AxiosError(
            `Request failed with status code ${result.status}`,
            "ERR_BAD_REQUEST",
            config,
            {},
            result,
          )
        }
        return result
      },
    })
    // 瀏覽器開啟時已登入（token 在 localStorage），先於 main.tsx 載入設好
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
    window.history.replaceState(null, "", "/?x=1")
    const root = document.createElement("div")
    root.id = "root"
    document.body.append(root)
    await import("@/main")
  })

  afterAll(() => {
    client.setConfig({ adapter: undefined })
    document.body.innerHTML = ""
    window.history.replaceState(null, "", "/")
  })

  it("已登入的請求帶 Authorization: Bearer <token>", async () => {
    // main.tsx 的 configureApiClient 設了 baseURL，所以網址前面會多出 VITE_API_URL
    const meRequests = () =>
      requests.filter((item) => item.url?.endsWith("/api/v1/accounts/me"))
    // 第一次渲染要載入各路由的程式碼，比預設的等待上限久
    await waitFor(() => expect(meRequests().length).toBeGreaterThan(0), {
      timeout: 10000,
    })
    for (const request of meRequests()) {
      expect(request.authorization).toBe("Bearer token-1")
    }
  })

  it("API 回 401：清除登入狀態並導向 S6，帶 redirect", async () => {
    // 每個測試結束時 setup.ts 會清空 localStorage，這裡重設為已登入
    setAccessToken("token-1")
    unauthorized = true

    await expect(IdentityService.readCurrentAccount()).rejects.toMatchObject({
      response: { status: 401 },
    })

    await waitFor(() => expect(window.location.pathname).toBe("/login"))
    expect(new URLSearchParams(window.location.search).get("redirect")).toBe(
      "/?x=1",
    )
    expect(getAccessToken()).toBeNull()
  })
})
