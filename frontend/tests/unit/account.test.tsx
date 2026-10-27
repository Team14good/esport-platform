import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { PROFILE_SAVED_TEXT } from "@/features/identity/AccountProfilePage"
import { RESEND_SUCCESS_TEXT } from "@/features/identity/ResendVerificationForm"
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

type ListSchoolsResult = Awaited<ReturnType<typeof IdentityService.listSchools>>
type ResendResult = Awaited<
  ReturnType<typeof IdentityService.resendVerificationEmail>
>
type UpdateResult = Awaited<
  ReturnType<typeof IdentityService.updateCurrentAccount>
>

const SCHOOLS = [
  { id: "school-ntu", name: "國立臺灣大學" },
  { id: "school-nthu", name: "國立清華大學" },
]

function mockSchools() {
  vi.spyOn(IdentityService, "listSchools").mockResolvedValue({
    data: SCHOOLS,
  } as ListSchoolsResult)
}

describe("需要登入的頁面", () => {
  it("未登入開啟 /account?x=1：導向 S6 並帶 redirect，登入後回到 /account?x=1", async () => {
    const user = userEvent.setup()
    mockSchools()
    const router = renderApp("/account?x=1")

    expect(
      await screen.findByRole("heading", { name: "登入" }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/login")
    expect(router.state.location.search).toEqual({ redirect: "/account?x=1" })

    mockLoginSuccess()
    mockAccountApis()
    await user.type(screen.getByLabelText("Email"), "an@example.com")
    await user.type(screen.getByLabelText("密碼"), "12345678")
    await user.click(screen.getByRole("button", { name: "登入" }))

    await waitFor(() => expect(router.state.location.href).toBe("/account?x=1"))
    expect(
      await screen.findByRole("heading", { name: "帳號資料" }),
    ).toBeInTheDocument()
  })

  it("未登入開啟 /me：導向 S6 並帶 redirect", async () => {
    const router = renderApp("/me")

    await screen.findByRole("heading", { name: "登入" })
    expect(router.state.location.search).toEqual({ redirect: "/me" })
  })
})

describe("S10 帳號資料", () => {
  it("Email 唯讀，顯示名稱與學校帶入目前資料", async () => {
    mockSchools()
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    renderApp("/account")

    const email = await screen.findByLabelText("Email")
    expect(email).toHaveValue("an@example.com")
    expect(email).toHaveAttribute("readonly")
    expect(screen.getByLabelText("顯示名稱")).toHaveValue("小安")
    expect(await screen.findByText("國立臺灣大學")).toBeInTheDocument()
    expect(screen.queryByLabelText("密碼")).toBeNull()
  })

  it("修改顯示名稱並清除學校：送出後顯示成功 Toast，頂欄的名稱也更新", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockSchools()
    signInAs({ account: { ...ACCOUNT, school_id: "school-ntu" } })
    const update = vi
      .spyOn(IdentityService, "updateCurrentAccount")
      .mockResolvedValue({
        data: { ...ACCOUNT, display_name: "阿明", school_id: null },
      } as UpdateResult)
    renderApp("/account")

    const name = await screen.findByLabelText("顯示名稱")
    await screen.findByText("國立臺灣大學")
    await user.clear(name)
    await user.type(name, " 阿明 ")
    await user.click(screen.getByRole("button", { name: "清除學校" }))
    await user.click(screen.getByRole("button", { name: "儲存帳號資料" }))

    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(PROFILE_SAVED_TEXT, {
        duration: 3000,
      }),
    )
    expect(update).toHaveBeenCalledWith({
      body: { display_name: "阿明", school_id: null },
    })
    expect(screen.getByLabelText("顯示名稱")).toHaveValue("阿明")
  })

  it("學校不在清單（422 SCHOOL_NOT_FOUND）：錯誤顯示在學校欄位下方", async () => {
    const user = userEvent.setup()
    mockSchools()
    signInAs()
    vi.spyOn(IdentityService, "updateCurrentAccount").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            type: "SCHOOL_NOT_FOUND",
            loc: ["body", "school_id"],
            msg: "找不到這間學校",
          },
        ],
      }),
    )
    renderApp("/account")

    await user.click(
      await screen.findByRole("button", { name: "儲存帳號資料" }),
    )

    const message = await screen.findByText("找不到這間學校")
    expect(message.closest("[data-slot=form-item]")).toContainElement(
      screen.getByLabelText("學校"),
    )
  })

  it("顯示名稱空白：在欄位下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    mockSchools()
    signInAs()
    const update = vi.spyOn(IdentityService, "updateCurrentAccount")
    renderApp("/account")

    await user.clear(await screen.findByLabelText("顯示名稱"))
    await user.click(screen.getByRole("button", { name: "儲存帳號資料" }))

    expect(await screen.findByText("請輸入顯示名稱")).toBeInTheDocument()
    expect(update).not.toHaveBeenCalled()
  })

  it("未驗證的帳號：Email 下方說明尚未驗證", async () => {
    mockSchools()
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    renderApp("/account")

    expect(await screen.findByText(/Email 尚未驗證/)).toBeInTheDocument()
  })

  it("未驗證的帳號：可以在 S10 重寄驗證信", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockSchools()
    signInAs({ account: { ...ACCOUNT, email_verified: false } })
    const resend = vi
      .spyOn(IdentityService, "resendVerificationEmail")
      .mockResolvedValue({ data: undefined } as ResendResult)
    renderApp("/account")

    await user.click(await screen.findByRole("button", { name: "重寄驗證信" }))

    expect(resend).toHaveBeenCalledWith({
      body: { email: "an@example.com", redirect: null },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(RESEND_SUCCESS_TEXT, {
        duration: 3000,
      }),
    )
  })

  it("已驗證的帳號：S10 沒有「重寄驗證信」", async () => {
    mockSchools()
    signInAs()
    renderApp("/account")

    await screen.findByLabelText("顯示名稱")
    expect(screen.queryByRole("button", { name: "重寄驗證信" })).toBeNull()
  })
})

describe("S11 身分選擇", () => {
  it("列出身分卡，選擇後記住身分並前往該身分首頁", async () => {
    const user = userEvent.setup()
    signInAs({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/me")

    const admin = await screen.findByRole("link", { name: "平台管理" })
    expect(admin).toHaveAttribute("href", "/admin/applications")
    expect(screen.getByRole("link", { name: "瀏覽賽事" })).toHaveAttribute(
      "href",
      "/",
    )

    await user.click(admin)

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/admin/applications"),
    )
    expect(window.localStorage.getItem("flow-last-identity")).toBe(
      "platform_admin",
    )
  })
})
