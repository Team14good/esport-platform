import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { vi } from "vitest"

import {
  type AccountRead,
  type Identity,
  IdentityService,
  UtilsService,
} from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { routeTree } from "@/routeTree.gen"
import { renderRouter } from "./render-router"

type ReadAccountResult = Awaited<
  ReturnType<typeof IdentityService.readCurrentAccount>
>
type ListIdentitiesResult = Awaited<
  ReturnType<typeof IdentityService.listCurrentIdentities>
>
type LoginResult = Awaited<ReturnType<typeof IdentityService.login>>
type HealthCheckResult = Awaited<ReturnType<typeof UtilsService.healthCheck>>

export const BROWSE: Identity = {
  key: "browse",
  label: "瀏覽賽事",
  home_path: "/",
}
export const PLATFORM_ADMIN: Identity = {
  key: "platform_admin",
  label: "平台管理",
  home_path: "/admin/applications",
}

export const ACCOUNT: AccountRead = {
  id: "acc-1",
  email: "an@example.com",
  display_name: "小安",
  school_id: null,
  email_verified: true,
  is_platform_admin: false,
  is_organizer: false,
}

/** 模擬目前帳號與身分清單的 API（不改變登入狀態）。 */
export function mockAccountApis({
  account = ACCOUNT,
  identities = [BROWSE],
}: {
  account?: AccountRead
  identities?: Identity[]
} = {}) {
  const readAccount = vi
    .spyOn(IdentityService, "readCurrentAccount")
    .mockResolvedValue({ data: account } as ReadAccountResult)
  const listIdentities = vi
    .spyOn(IdentityService, "listCurrentIdentities")
    .mockResolvedValue({ data: identities } as ListIdentitiesResult)
  return { readAccount, listIdentities }
}

/** 已登入：localStorage 有 token，目前帳號與身分清單的 API 回傳指定資料。 */
export function signInAs(options: Parameters<typeof mockAccountApis>[0] = {}) {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
  return mockAccountApis(options)
}

export function mockLoginSuccess(accessToken = "token-new") {
  return vi.spyOn(IdentityService, "login").mockResolvedValue({
    data: {
      access_token: accessToken,
      token_type: "bearer",
      expires_at: "2026-11-03T11:00:00Z",
    },
  } as LoginResult)
}

/** 以完整路由樹渲染某個網址，回傳 router（可檢查導向結果）。 */
export function renderApp(url: string) {
  // S1 會呼叫健康檢查；導向到 S1 的測試不需要真的連線
  vi.spyOn(UtilsService, "healthCheck").mockResolvedValue({
    data: true,
  } as HealthCheckResult)
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [url] }),
    defaultErrorComponent: RouteErrorPage,
  })
  renderRouter(router)
  return router
}
