import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  LAST_IDENTITY_STORAGE_KEY,
  postLoginDestination,
  SESSION_EXPIRED_TEXT,
} from "@/features/identity/auth"
import {
  ACCOUNT,
  BROWSE,
  mockAccountApis,
  mockLoginSuccess,
  PLATFORM_ADMIN,
  renderApp,
  signInAs,
} from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

async function submitLogin(
  user: ReturnType<typeof userEvent.setup>,
  { email = "an@example.com", password = "12345678" } = {},
) {
  await user.type(await screen.findByLabelText("Email"), email)
  await user.type(screen.getByLabelText("密碼"), password)
  await user.click(screen.getByRole("button", { name: "登入" }))
}

describe("登入後導向規則", () => {
  it("有合格的 redirect：回到 redirect", () => {
    expect(
      postLoginDestination({
        redirect: "/account?x=1",
        identities: [BROWSE, PLATFORM_ADMIN],
        lastIdentity: "platform_admin",
      }),
    ).toBe("/account?x=1")
  })

  it("不合格的 redirect 視為沒有", () => {
    for (const redirect of ["//evil.com", "https://evil.com", "/\\evil"]) {
      expect(
        postLoginDestination({
          redirect,
          identities: [BROWSE],
          lastIdentity: null,
        }),
      ).toBe("/")
    }
  })

  it("只有 1 種身分：到 S1", () => {
    expect(
      postLoginDestination({ identities: [BROWSE], lastIdentity: "browse" }),
    ).toBe("/")
  })

  it("2 種以上身分：第一次到 S11，之後到上次身分的首頁", () => {
    const identities = [BROWSE, PLATFORM_ADMIN]
    expect(postLoginDestination({ identities, lastIdentity: null })).toBe("/me")
    expect(
      postLoginDestination({ identities, lastIdentity: "platform_admin" }),
    ).toBe("/admin/applications")
    expect(postLoginDestination({ identities, lastIdentity: "browse" })).toBe(
      "/",
    )
    // 記住的身分已不在清單內：視同第一次
    expect(postLoginDestination({ identities, lastIdentity: "referee" })).toBe(
      "/me",
    )
  })
})

describe("S6 登入頁", () => {
  it("顯示 Email、密碼與「登入」，並有連到註冊的連結", async () => {
    renderApp("/login")

    expect(
      await screen.findByRole("heading", { name: "登入" }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toBeInTheDocument()
    expect(screen.getByLabelText("密碼")).toHaveAttribute(
      "autocomplete",
      "current-password",
    )
    expect(screen.getByRole("link", { name: "註冊帳號" })).toHaveAttribute(
      "href",
      "/signup",
    )
  })

  it("登入成功：存下 token，頂欄換成身分切換器，「登入」「註冊」消失", async () => {
    const user = userEvent.setup()
    const login = mockLoginSuccess("token-new")
    mockAccountApis({ identities: [BROWSE] })
    const router = renderApp("/login")

    await submitLogin(user, { email: " An@Example.com " })

    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(login).toHaveBeenCalledWith({
      body: { email: "An@Example.com", password: "12345678" },
    })
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
      "token-new",
    )
    const banner = await screen.findByRole("banner")
    expect(
      await within(banner).findByRole("button", { name: /切換身分/ }),
    ).toBeInTheDocument()
    expect(within(banner).queryByRole("link", { name: "登入" })).toBeNull()
    expect(within(banner).queryByRole("link", { name: "註冊" })).toBeNull()
  })

  it("已登入時再以另一個帳號登入：頂欄顯示新帳號，不留前一個帳號的快取；關掉「登入已過期」", async () => {
    const user = userEvent.setup()
    const dismiss = vi.spyOn(toast, "dismiss")
    const { readAccount } = signInAs({ account: ACCOUNT })
    const router = renderApp("/login")
    await waitFor(() => expect(readAccount).toHaveBeenCalled())
    mockLoginSuccess("token-b")
    mockAccountApis({
      account: {
        ...ACCOUNT,
        id: "acc-2",
        email: "bei@example.com",
        display_name: "小北",
      },
    })

    await submitLogin(user, { email: "bei@example.com" })

    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(dismiss).toHaveBeenCalledWith(SESSION_EXPIRED_TEXT)
    const banner = await screen.findByRole("banner")
    await user.click(
      await within(banner).findByRole("button", { name: /切換身分（目前：/ }),
    )
    const menu = await screen.findByRole("menu")
    expect(await within(menu).findByText("小北")).toBeInTheDocument()
    expect(within(menu).queryByText("小安")).toBeNull()
  })

  it("有 redirect：登入後回到原頁（包含查詢參數）", async () => {
    const user = userEvent.setup()
    mockLoginSuccess()
    mockAccountApis({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/login?redirect=%2Faccount%3Fx%3D1")

    await submitLogin(user)

    await waitFor(() => expect(router.state.location.pathname).toBe("/account"))
    expect(router.state.location.href).toBe("/account?x=1")
    expect(
      await screen.findByRole("heading", { name: "帳號資料" }),
    ).toBeInTheDocument()
  })

  it("不合格的 redirect：視為沒有", async () => {
    const user = userEvent.setup()
    mockLoginSuccess()
    mockAccountApis({ identities: [BROWSE] })
    const router = renderApp("/login?redirect=%2F%2Fevil.com")

    await submitLogin(user)

    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
  })

  it("登入成功但身分清單取得失敗：仍存下 token，回到 S1", async () => {
    const user = userEvent.setup()
    mockLoginSuccess("token-new")
    mockAccountApis()
    vi.spyOn(IdentityService, "listCurrentIdentities").mockRejectedValue(
      httpError(500, {}),
    )
    const router = renderApp("/login")

    await submitLogin(user)

    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
      "token-new",
    )
  })

  it("2 種以上身分、第一次登入：到 S11", async () => {
    const user = userEvent.setup()
    mockLoginSuccess()
    mockAccountApis({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/login")

    await submitLogin(user)

    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))
    expect(
      await screen.findByRole("heading", { name: "選擇身分" }),
    ).toBeInTheDocument()
  })

  it("2 種以上身分、記得上次身分：到該身分首頁", async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(LAST_IDENTITY_STORAGE_KEY, "platform_admin")
    mockLoginSuccess()
    mockAccountApis({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/login")

    await submitLogin(user)

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/admin/applications"),
    )
  })

  it("帳密錯誤（401）：表單頂部 Alert 顯示伺服器訊息，不視為登入過期", async () => {
    const user = userEvent.setup()
    const toastError = vi.spyOn(toast, "error")
    vi.spyOn(IdentityService, "login").mockRejectedValue(
      httpError(401, {
        detail: {
          code: "INVALID_CREDENTIALS",
          message: "Email 或密碼錯誤。",
        },
      }),
    )
    const router = renderApp("/login?redirect=%2Faccount")

    await submitLogin(user)

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email 或密碼錯誤。",
    )
    expect(router.state.location.pathname).toBe("/login")
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    expect(screen.getByLabelText("密碼")).toHaveValue("")
    expect(toastError).not.toHaveBeenCalled()
  })

  it("沒填 Email 或密碼：在欄位下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    const login = vi.spyOn(IdentityService, "login")
    renderApp("/login")

    await user.click(await screen.findByRole("button", { name: "登入" }))

    expect(await screen.findByText("請輸入 Email")).toBeInTheDocument()
    expect(screen.getByText("請輸入密碼")).toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
  })
})
