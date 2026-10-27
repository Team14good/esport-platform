import { QueryClient } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRouter,
  type RegisteredRouter,
} from "@tanstack/react-router"
import { screen, waitFor } from "@testing-library/react"
import {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { client } from "@/client/client.gen"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearAccessToken,
  configureApiClient,
  createUnauthorizedHandler,
  getAccessToken,
  ME_QUERY_KEY,
  SESSION_EXPIRED_TEXT,
  setAccessToken,
} from "@/features/identity/auth"
import { createQueryClient, shouldRetryQuery } from "@/lib/query-client"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, mockAccountApis } from "./auth-fixtures"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

const AUTH_REQUIRED = httpError(401, {
  detail: { code: "AUTHENTICATION_REQUIRED", message: "請先登入。" },
})

function setup(url: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [url] }),
    defaultErrorComponent: RouteErrorPage,
  }) as unknown as RegisteredRouter
  const queryClient = new QueryClient()
  renderRouter(router)
  return {
    router,
    queryClient,
    handle: createUnauthorizedHandler(router, queryClient),
  }
}

describe("access token 存取", () => {
  it("存在 localStorage 的 flow-access-token", () => {
    setAccessToken("abc")
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("abc")
    expect(getAccessToken()).toBe("abc")
  })

  it("localStorage 不能用：讀不到時視為未登入，不丟例外", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked")
    })

    expect(getAccessToken()).toBeNull()
  })

  it("localStorage 寫不進去：token 存在記憶體，這個分頁仍是登入狀態，登出後清除", () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("blocked")
      })
    }

    expect(() => setAccessToken("abc")).not.toThrow()
    expect(getAccessToken()).toBe("abc")

    expect(() => clearAccessToken()).not.toThrow()
    expect(getAccessToken()).toBeNull()

    // localStorage 恢復後寫入成功：改回以 localStorage 為準
    vi.restoreAllMocks()
    setAccessToken("def")
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("def")
    clearAccessToken()
    expect(getAccessToken()).toBeNull()
  })
})

describe("API client 設定", () => {
  type CapturedRequest = { url?: string; authorization?: unknown }

  function stubAdapter(
    respond: (config: InternalAxiosRequestConfig) => AxiosResponse,
  ) {
    const requests: CapturedRequest[] = []
    // axios.create 的實例上，defaults 被 setConfig 換掉後不再影響請求：改以 client 設定傳入
    // adapter（產生的 client 會把設定原樣交給 client.instance）
    client.setConfig({
      adapter: async (config: InternalAxiosRequestConfig) => {
        requests.push({
          url: config.url,
          authorization: config.headers.get("Authorization"),
        })
        const response = respond(config)
        if (response.status >= 400) {
          throw new AxiosError(
            `Request failed with status code ${response.status}`,
            "ERR_BAD_REQUEST",
            config,
            {},
            response,
          )
        }
        return response
      },
    })
    return {
      requests,
      restore: () => {
        client.setConfig({ adapter: undefined })
      },
    }
  }

  function jsonResponse(
    config: InternalAxiosRequestConfig,
    status: number,
    data: unknown,
  ): AxiosResponse {
    return { status, statusText: "", data, headers: {}, config }
  }

  it("已登入：需要登入的 API 帶 Authorization: Bearer <token>", async () => {
    const { router, queryClient } = setup("/signup")
    await screen.findByRole("heading", { name: "註冊帳號" })
    const eject = configureApiClient(router, queryClient)
    const adapter = stubAdapter((config) => jsonResponse(config, 200, ACCOUNT))
    try {
      setAccessToken("token-1")

      const response = await IdentityService.readCurrentAccount()

      expect(response.data).toEqual(ACCOUNT)
      // 頁面本身（頂欄的身分切換器）也會經過同一個 client：每個 /accounts/me 都要帶 token
      const meRequests = adapter.requests.filter(
        (request) => request.url === "/api/v1/accounts/me",
      )
      expect(meRequests.length).toBeGreaterThan(0)
      for (const request of meRequests) {
        expect(request.authorization).toBe("Bearer token-1")
      }

      // 公開 API（OpenAPI 沒有標 bearer）不帶 token
      adapter.requests.length = 0
      await IdentityService.listSchools()
      expect(adapter.requests).toEqual([
        { url: "/api/v1/schools", authorization: undefined },
      ])
    } finally {
      adapter.restore()
      eject()
    }
  })

  it("其他分頁換了 token（登入、登出、換帳號）：清掉這個分頁的快取", async () => {
    const { router, queryClient } = setup("/signup")
    await screen.findByRole("heading", { name: "註冊帳號" })
    const eject = configureApiClient(router, queryClient)
    try {
      queryClient.setQueryData([...ME_QUERY_KEY, "account"], ACCOUNT)

      window.dispatchEvent(new StorageEvent("storage", { key: "unrelated" }))
      expect(queryClient.getQueryData([...ME_QUERY_KEY, "account"])).toEqual(
        ACCOUNT,
      )

      window.dispatchEvent(
        new StorageEvent("storage", { key: ACCESS_TOKEN_STORAGE_KEY }),
      )
      expect(queryClient.getQueryData([...ME_QUERY_KEY, "account"])).toBe(
        undefined,
      )
    } finally {
      eject()
    }
  })

  it("API 回 401 AUTHENTICATION_REQUIRED：清除 token，導向 S6 並帶 redirect", async () => {
    const { router, queryClient } = setup("/signup?x=1")
    await screen.findByRole("heading", { name: "註冊帳號" })
    const eject = configureApiClient(router, queryClient)
    const adapter = stubAdapter((config) =>
      jsonResponse(config, 401, {
        detail: { code: "AUTHENTICATION_REQUIRED", message: "請先登入。" },
      }),
    )
    try {
      setAccessToken("expired-token")

      await expect(IdentityService.readCurrentAccount()).rejects.toMatchObject({
        response: { status: 401 },
      })

      expect(getAccessToken()).toBeNull()
      await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
      expect(router.state.location.search).toEqual({ redirect: "/signup?x=1" })
    } finally {
      adapter.restore()
      eject()
    }
  })
})

describe("query 重試", () => {
  it("401 不重試，其他錯誤沿用預設的 3 次", () => {
    expect(shouldRetryQuery(0, AUTH_REQUIRED)).toBe(false)
    const serverError = httpError(500, {})
    expect(shouldRetryQuery(0, serverError)).toBe(true)
    expect(shouldRetryQuery(2, serverError)).toBe(true)
    expect(shouldRetryQuery(3, serverError)).toBe(false)
    expect(createQueryClient().getDefaultOptions().queries?.retry).toBe(
      shouldRetryQuery,
    )
  })
})

describe("API 回 401 的處理", () => {
  it("登入狀態下：清除 token 與所有快取、顯示「登入已過期」，導向 S6 並帶 redirect 回原頁", async () => {
    const toastError = vi.spyOn(toast, "error")
    mockAccountApis()
    setAccessToken("expired-token")
    const { router, queryClient, handle } = setup("/me?tab=2")
    await screen.findByRole("heading", { name: "選擇身分" })
    queryClient.setQueryData([...ME_QUERY_KEY, "account"], ACCOUNT)
    // 不在 ME_QUERY_KEY 底下的 query 也可能帶著這個帳號的資料
    queryClient.setQueryData(["teams", "mine"], [])

    await expect(handle(AUTH_REQUIRED)).rejects.toBe(AUTH_REQUIRED)

    expect(getAccessToken()).toBeNull()
    expect(queryClient.getQueryData([...ME_QUERY_KEY, "account"])).toBe(
      undefined,
    )
    expect(queryClient.getQueryData(["teams", "mine"])).toBe(undefined)
    expect(SESSION_EXPIRED_TEXT).toBe("登入已過期，請重新登入。")
    expect(toastError).toHaveBeenCalledWith(
      SESSION_EXPIRED_TEXT,
      expect.objectContaining({ id: SESSION_EXPIRED_TEXT }),
    )
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(router.state.location.search).toEqual({ redirect: "/me?tab=2" })
    // 登入後回到原頁時表單是空的：不保留任何內容
    expect(
      await screen.findByRole("heading", { name: "登入" }),
    ).toBeInTheDocument()
  })

  it("未登入時寫入被拒（401）：導向 S6 並帶 redirect，不顯示「登入已過期」", async () => {
    const toastError = vi.spyOn(toast, "error")
    const { router, handle } = setup("/signup")
    await screen.findByRole("heading", { name: "註冊帳號" })

    await expect(handle(AUTH_REQUIRED)).rejects.toBe(AUTH_REQUIRED)

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(router.state.location.search).toEqual({ redirect: "/signup" })
    expect(toastError).not.toHaveBeenCalled()
  })

  it("登入 API 的 401（INVALID_CREDENTIALS）：不處理", async () => {
    const toastError = vi.spyOn(toast, "error")
    setAccessToken("still-valid")
    const { router, handle } = setup("/signup")
    await screen.findByRole("heading", { name: "註冊帳號" })
    const invalid = httpError(401, {
      detail: { code: "INVALID_CREDENTIALS", message: "Email 或密碼錯誤。" },
    })

    await expect(handle(invalid)).rejects.toBe(invalid)

    expect(getAccessToken()).toBe("still-valid")
    expect(router.state.location.pathname).toBe("/signup")
    expect(toastError).not.toHaveBeenCalled()
  })

  it("其他錯誤（403、500、連線失敗）：原樣拋出，不改變登入狀態", async () => {
    setAccessToken("still-valid")
    const { router, handle } = setup("/signup")
    await screen.findByRole("heading", { name: "註冊帳號" })

    for (const error of [
      httpError(403, { detail: { code: "EMAIL_NOT_VERIFIED", message: "x" } }),
      httpError(500, {}),
      new Error("Network Error"),
    ]) {
      await expect(handle(error)).rejects.toBe(error)
    }
    expect(getAccessToken()).toBe("still-valid")
    expect(router.state.location.pathname).toBe("/signup")
  })

  it("已經在 S6：不再導向（避免 redirect 指回登入頁）", async () => {
    const { router, handle } = setup("/login?redirect=%2Faccount")
    await screen.findByRole("heading", { name: "登入" })

    await expect(handle(AUTH_REQUIRED)).rejects.toBe(AUTH_REQUIRED)

    expect(router.state.location.search).toEqual({ redirect: "/account" })
  })
})
