import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AxiosError } from "axios"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { RESEND_SUCCESS_TEXT } from "@/features/identity/ResendVerificationForm"
import { routeTree } from "@/routeTree.gen"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type VerifyResult = Awaited<ReturnType<typeof IdentityService.verifyEmail>>
type ResendResult = Awaited<
  ReturnType<typeof IdentityService.resendVerificationEmail>
>

function renderVerify(url: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [url] }),
    defaultErrorComponent: RouteErrorPage,
  })
  renderRouter(router)
  return router
}

describe("S7 Email 驗證頁", () => {
  it("沒有 token：顯示「請收信驗證」與「重寄驗證信」，不呼叫驗證 API", async () => {
    const verify = vi.spyOn(IdentityService, "verifyEmail")
    renderVerify("/verify-email")

    expect(
      await screen.findByRole("heading", { name: "請收信驗證" }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveValue("")
    expect(
      screen.getByRole("button", { name: "重寄驗證信" }),
    ).toBeInTheDocument()
    expect(verify).not.toHaveBeenCalled()
  })

  it("驗證成功：顯示「Email 驗證完成」，「繼續」回到 redirect 頁", async () => {
    const verify = vi
      .spyOn(IdentityService, "verifyEmail")
      .mockResolvedValue({ data: undefined } as VerifyResult)
    renderVerify("/verify-email?token=abc&redirect=%2Ftournaments%2F7")

    expect(
      await screen.findByRole("heading", { name: "Email 驗證完成" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "繼續" })).toHaveAttribute(
      "href",
      "/tournaments/7",
    )
    expect(verify).toHaveBeenCalledTimes(1)
    expect(verify).toHaveBeenCalledWith({ body: { token: "abc" } })
  })

  it("驗證成功且沒有 redirect：「繼續」回首頁", async () => {
    vi.spyOn(IdentityService, "verifyEmail").mockResolvedValue({
      data: undefined,
    } as VerifyResult)
    renderVerify("/verify-email?token=no-redirect")

    expect(await screen.findByRole("link", { name: "繼續" })).toHaveAttribute(
      "href",
      "/",
    )
  })

  it("驗證中：顯示載入狀態", async () => {
    vi.spyOn(IdentityService, "verifyEmail").mockReturnValue(
      new Promise<never>(() => {}),
    )
    renderVerify("/verify-email?token=pending")

    const status = await screen.findByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveTextContent("正在驗證 Email")
  })

  it("連結失效：顯示「此驗證連結已失效。」與「重寄驗證信」", async () => {
    vi.spyOn(IdentityService, "verifyEmail").mockRejectedValue(
      httpError(400, {
        detail: {
          code: "VERIFICATION_LINK_INVALID",
          message: "此驗證連結已失效。",
        },
      }),
    )
    renderVerify("/verify-email?token=used")

    expect(
      await screen.findByRole("heading", { name: "此驗證連結已失效。" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "重寄驗證信" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "繼續" })).toBeNull()
  })

  it("重寄驗證信：以 Email 與 redirect 呼叫 API，顯示不透露帳號是否存在的成功訊息", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "verifyEmail").mockRejectedValue(
      httpError(400, {
        detail: {
          code: "VERIFICATION_LINK_INVALID",
          message: "此驗證連結已失效。",
        },
      }),
    )
    const resend = vi
      .spyOn(IdentityService, "resendVerificationEmail")
      .mockResolvedValue({ data: null } as ResendResult)
    const success = vi.spyOn(toast, "success")
    renderVerify("/verify-email?token=expired&redirect=%2Fjoin%2Fx")

    await user.type(await screen.findByLabelText("Email"), " me@example.com ")
    await user.click(screen.getByRole("button", { name: "重寄驗證信" }))

    expect(resend).toHaveBeenCalledWith({
      body: { email: "me@example.com", redirect: "/join/x" },
    })
    expect(success).toHaveBeenCalledWith(RESEND_SUCCESS_TEXT, {
      duration: 3000,
    })
  })

  it("重寄時 Email 格式錯誤：顯示在 Email 欄下方，不呼叫 API", async () => {
    const user = userEvent.setup()
    const resend = vi.spyOn(IdentityService, "resendVerificationEmail")
    renderVerify("/verify-email")

    await user.type(await screen.findByLabelText("Email"), "not-an-email")
    await user.click(screen.getByRole("button", { name: "重寄驗證信" }))

    expect(await screen.findByText("請輸入有效的 Email")).toBeInTheDocument()
    expect(resend).not.toHaveBeenCalled()
  })

  it("連線失敗或伺服器錯誤：顯示錯誤訊息與「重試」，不說連結已失效", async () => {
    const user = userEvent.setup()
    const verify = vi
      .spyOn(IdentityService, "verifyEmail")
      .mockRejectedValueOnce(new AxiosError("Network Error", "ERR_NETWORK"))
      .mockResolvedValueOnce({ data: undefined } as VerifyResult)
    renderVerify("/verify-email?token=flaky")

    expect(
      await screen.findByRole("heading", { name: "無法連線到伺服器" }),
    ).toBeInTheDocument()
    expect(screen.queryByText("此驗證連結已失效。")).toBeNull()
    expect(screen.queryByText(/24 小時/)).toBeNull()
    expect(screen.queryByRole("button", { name: "重寄驗證信" })).toBeNull()

    await user.click(screen.getByRole("button", { name: "重試" }))

    expect(
      await screen.findByRole("heading", { name: "Email 驗證完成" }),
    ).toBeInTheDocument()
    expect(verify).toHaveBeenCalledTimes(2)
    expect(verify).toHaveBeenLastCalledWith({ body: { token: "flaky" } })
  })

  it("伺服器 500：顯示狀態碼訊息與「重試」", async () => {
    vi.spyOn(IdentityService, "verifyEmail").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    renderVerify("/verify-email?token=server-error")

    expect(
      await screen.findByRole("heading", { name: "伺服器發生錯誤（500）" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "重試" })).toBeInTheDocument()
  })

  it("redirect 帶查詢參數與 hash：「繼續」導到完整的原網址", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "verifyEmail").mockResolvedValue({
      data: undefined,
    } as VerifyResult)
    const router = renderVerify(
      `/verify-email?token=with-query&redirect=${encodeURIComponent("/join/x?code=abc#top")}`,
    )

    const link = await screen.findByRole("link", { name: "繼續" })
    expect(link).toHaveAttribute("href", "/join/x?code=abc#top")
    await user.click(link)

    expect(router.state.location.pathname).toBe("/join/x")
    expect(router.state.location.search).toEqual({ code: "abc" })
    expect(router.state.location.hash).toBe("top")
  })

  it("redirect 含 tab 等控制字元：忽略，「繼續」回首頁", async () => {
    vi.spyOn(IdentityService, "verifyEmail").mockResolvedValue({
      data: undefined,
    } as VerifyResult)
    renderVerify(
      `/verify-email?token=ctrl&redirect=${encodeURIComponent("/\t/evil.com")}`,
    )

    expect(await screen.findByRole("link", { name: "繼續" })).toHaveAttribute(
      "href",
      "/",
    )
  })
})
