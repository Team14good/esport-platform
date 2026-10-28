import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { RESET_REQUESTED_TEXT } from "@/features/identity/ForgotPasswordForm"
import { renderApp } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type RequestResult = Awaited<
  ReturnType<typeof IdentityService.requestPasswordResetEmail>
>

function mockRequestSuccess() {
  return vi
    .spyOn(IdentityService, "requestPasswordResetEmail")
    .mockResolvedValue({ data: undefined } as RequestResult)
}

describe("S6 的「忘記密碼」", () => {
  it("S6 有「忘記密碼」連結，點了到 S8", async () => {
    const user = userEvent.setup()
    const router = renderApp("/login")

    const link = await screen.findByRole("link", { name: "忘記密碼" })
    expect(link).toHaveAttribute("href", "/forgot-password")
    await user.click(link)

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/forgot-password"),
    )
    expect(
      await screen.findByRole("heading", { name: "忘記密碼" }),
    ).toBeInTheDocument()
  })
})

describe("S8 忘記密碼", () => {
  it("送出 Email：呼叫 API（去掉前後空白），畫面顯示不透露帳號是否存在的訊息", async () => {
    const user = userEvent.setup()
    const request = mockRequestSuccess()
    renderApp("/forgot-password")

    const status = await screen.findByRole("status")
    expect(status).toHaveTextContent("")
    await user.type(screen.getByLabelText("Email"), "  an@example.com ")
    await user.click(screen.getByRole("button", { name: "寄送重設信" }))

    await waitFor(() => expect(status).toHaveTextContent(RESET_REQUESTED_TEXT))
    expect(RESET_REQUESTED_TEXT).toBe(
      "若這個 Email 已註冊，重設信會在幾分鐘內寄達。",
    )
    expect(request).toHaveBeenCalledWith({
      body: { email: "an@example.com" },
    })
  })

  it.each([
    ["空白", "   ", "請輸入 Email"],
    ["格式不符", "not-an-email", "請輸入有效的 Email"],
  ])("Email %s：在欄位下方提示，不呼叫 API", async (_, email, message) => {
    const user = userEvent.setup()
    const request = mockRequestSuccess()
    renderApp("/forgot-password")

    await user.type(await screen.findByLabelText("Email"), email)
    await user.click(screen.getByRole("button", { name: "寄送重設信" }))

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(request).not.toHaveBeenCalled()
  })

  it("伺服器的 422：錯誤顯示在 Email 欄位下方，不顯示成功訊息", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "requestPasswordResetEmail").mockRejectedValue(
      httpError(422, {
        detail: [{ loc: ["body", "email"], msg: "請輸入有效的 Email" }],
      }),
    )
    renderApp("/forgot-password")

    await user.type(await screen.findByLabelText("Email"), "an@example.com")
    await user.click(screen.getByRole("button", { name: "寄送重設信" }))

    expect(await screen.findByText("請輸入有效的 Email")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("")
  })

  it("伺服器錯誤：表單頂部顯示錯誤，不顯示成功訊息", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "requestPasswordResetEmail").mockRejectedValue(
      httpError(500, {}),
    )
    renderApp("/forgot-password")

    await user.type(await screen.findByLabelText("Email"), "an@example.com")
    await user.click(screen.getByRole("button", { name: "寄送重設信" }))

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("")
  })
})
