import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { PASSWORD_RESET_TEXT } from "@/features/identity/ResetPasswordPage"
import { renderApp } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type CheckResult = Awaited<
  ReturnType<typeof IdentityService.checkPasswordResetLink>
>
type ResetResult = Awaited<ReturnType<typeof IdentityService.resetPassword>>

const RESET_LINK_INVALID = httpError(400, {
  detail: { code: "RESET_LINK_INVALID", message: "此重設連結已失效。" },
})

function mockCheckValid() {
  return vi
    .spyOn(IdentityService, "checkPasswordResetLink")
    .mockResolvedValue({ data: undefined } as CheckResult)
}

function mockResetSuccess() {
  return vi
    .spyOn(IdentityService, "resetPassword")
    .mockResolvedValue({ data: undefined } as ResetResult)
}

async function expectInvalidLink() {
  expect(
    await screen.findByRole("heading", { name: "此重設連結已失效。" }),
  ).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "重新寄送重設信" })).toHaveAttribute(
    "href",
    "/forgot-password",
  )
  expect(screen.queryByLabelText("新密碼")).toBeNull()
}

async function submitNewPassword(
  user: ReturnType<typeof userEvent.setup>,
  password: string,
) {
  await user.type(await screen.findByLabelText("新密碼"), password)
  await user.click(screen.getByRole("button", { name: "設定新密碼" }))
}

describe("S9 開啟時檢查連結", () => {
  it("有效連結：只檢查一次（不會用掉 token），顯示新密碼欄位", async () => {
    const check = mockCheckValid()
    const reset = mockResetSuccess()
    renderApp("/reset-password?token=abc")

    expect(
      await screen.findByRole("heading", { name: "設定新密碼" }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("新密碼")).toHaveAttribute(
      "autocomplete",
      "new-password",
    )
    expect(check).toHaveBeenCalledTimes(1)
    expect(check).toHaveBeenCalledWith({ body: { token: "abc" } })
    expect(reset).not.toHaveBeenCalled()
  })

  it("網址沒有 token：直接顯示失效，不呼叫 API", async () => {
    const check = mockCheckValid()
    renderApp("/reset-password")

    await expectInvalidLink()
    expect(check).not.toHaveBeenCalled()
  })

  it.each([
    ["已用過、過期或被作廢（RESET_LINK_INVALID）", RESET_LINK_INVALID],
    [
      "token 格式不合格（422）",
      httpError(422, {
        detail: [{ loc: ["body", "token"], msg: "字串太長" }],
      }),
    ],
  ])("%s：顯示「此重設連結已失效。」與「重新寄送重設信」", async (_, error) => {
    vi.spyOn(IdentityService, "checkPasswordResetLink").mockRejectedValue(error)
    renderApp("/reset-password?token=used")

    await expectInvalidLink()
  })

  it("「重新寄送重設信」到 S8", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "checkPasswordResetLink").mockRejectedValue(
      RESET_LINK_INVALID,
    )
    const router = renderApp("/reset-password?token=used")

    await user.click(
      await screen.findByRole("link", { name: "重新寄送重設信" }),
    )

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/forgot-password"),
    )
  })

  it("連線失敗或伺服器錯誤：不當成失效，可以重試同一個連結", async () => {
    const user = userEvent.setup()
    const check = vi
      .spyOn(IdentityService, "checkPasswordResetLink")
      .mockRejectedValueOnce(httpError(500, {}))
      .mockResolvedValueOnce({ data: undefined } as CheckResult)
    renderApp("/reset-password?token=abc")

    await user.click(await screen.findByRole("button", { name: "重試" }))

    expect(await screen.findByLabelText("新密碼")).toBeInTheDocument()
    expect(check).toHaveBeenCalledTimes(2)
  })
})

describe("S9 設定新密碼", () => {
  it("成功：送出 token 與新密碼，清除這個瀏覽器的登入狀態，導向 S6 並顯示成功 Toast", async () => {
    const user = userEvent.setup()
    const toastSuccess = vi.spyOn(toast, "success")
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "old-token")
    mockCheckValid()
    const reset = mockResetSuccess()
    const router = renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "new-password")

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(reset).toHaveBeenCalledWith({
      body: { token: "abc", new_password: "new-password" },
    })
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    expect(toastSuccess).toHaveBeenCalledWith(
      PASSWORD_RESET_TEXT,
      expect.anything(),
    )
    expect(PASSWORD_RESET_TEXT).toBe("密碼已重設，請用新密碼登入。")
    // replace：瀏覽紀錄裡不留帶 token 的網址
    expect(router.history.length).toBe(1)
  })

  it("新密碼少於 8 個字元：在欄位下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    mockCheckValid()
    const reset = mockResetSuccess()
    renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "short")

    expect(await screen.findByText("密碼至少需要 8 個字元")).toBeInTheDocument()
    expect(reset).not.toHaveBeenCalled()
  })

  it("伺服器的 422：錯誤顯示在新密碼欄位下方，仍停在表單", async () => {
    const user = userEvent.setup()
    mockCheckValid()
    vi.spyOn(IdentityService, "resetPassword").mockRejectedValue(
      httpError(422, {
        detail: [{ loc: ["body", "new_password"], msg: "密碼最多 128 個字元" }],
      }),
    )
    renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "new-password")

    expect(await screen.findByText("密碼最多 128 個字元")).toBeInTheDocument()
    expect(screen.getByLabelText("新密碼")).toBeInTheDocument()
  })

  it("開啟後才失效（送出時回 RESET_LINK_INVALID）：畫面換成失效狀態", async () => {
    const user = userEvent.setup()
    mockCheckValid()
    vi.spyOn(IdentityService, "resetPassword").mockRejectedValue(
      RESET_LINK_INVALID,
    )
    renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "new-password")

    await expectInvalidLink()
  })

  it("送出時 token 格式不合格（422 token 欄位）：畫面換成失效狀態", async () => {
    const user = userEvent.setup()
    mockCheckValid()
    vi.spyOn(IdentityService, "resetPassword").mockRejectedValue(
      httpError(422, {
        detail: [{ loc: ["body", "token"], msg: "字串太長" }],
      }),
    )
    renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "new-password")

    await expectInvalidLink()
  })

  it("送出時伺服器錯誤：表單頂部顯示錯誤，仍停在表單、不當成失效", async () => {
    const user = userEvent.setup()
    mockCheckValid()
    vi.spyOn(IdentityService, "resetPassword").mockRejectedValue(
      httpError(500, {}),
    )
    const router = renderApp("/reset-password?token=abc")

    await submitNewPassword(user, "new-password")

    expect(await screen.findByText("伺服器發生錯誤（500）")).toBeInTheDocument()
    expect(screen.getByLabelText("新密碼")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/reset-password")
  })
})
