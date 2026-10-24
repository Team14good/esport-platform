import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import { RouteErrorPage } from "@/components/layout/ErrorPage"
import { SCHOOL_LIST_ERROR_TEXT } from "@/features/identity/SchoolPicker"
import { routeTree } from "@/routeTree.gen"
import { httpError } from "./helpers"
import { renderRouter } from "./render-router"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListSchoolsResult = Awaited<ReturnType<typeof IdentityService.listSchools>>
type RegisterResult = Awaited<ReturnType<typeof IdentityService.register>>

const SCHOOLS = [
  { id: "school-ntu", name: "國立臺灣大學" },
  { id: "school-nthu", name: "國立清華大學" },
]

function renderSignup(url = "/signup", { mockSchools = true } = {}) {
  if (mockSchools) {
    vi.spyOn(IdentityService, "listSchools").mockResolvedValue({
      data: SCHOOLS,
    } as ListSchoolsResult)
  }
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [url] }),
    defaultErrorComponent: RouteErrorPage,
  })
  renderRouter(router)
  return router
}

async function fillForm(
  user: ReturnType<typeof userEvent.setup>,
  {
    email = "new@example.com",
    password = "12345678",
    displayName = "小安",
  } = {},
) {
  await user.type(await screen.findByLabelText("Email"), email)
  await user.type(screen.getByLabelText("密碼"), password)
  await user.type(screen.getByLabelText("顯示名稱"), displayName)
}

function field(label: string) {
  return screen
    .getByLabelText(label)
    .closest<HTMLElement>("[data-slot=form-item]")!
}

describe("S5 註冊頁", () => {
  it("顯示 Email、密碼、顯示名稱、學校欄位，文字為繁體中文", async () => {
    renderSignup()

    expect(
      await screen.findByRole("heading", { name: "註冊帳號" }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toBeInTheDocument()
    expect(screen.getByLabelText("密碼")).toBeInTheDocument()
    expect(screen.getByLabelText("顯示名稱")).toBeInTheDocument()
    expect(screen.getByLabelText("學校")).toHaveAttribute("role", "combobox")
    expect(screen.getByRole("button", { name: "顯示密碼" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "註冊帳號" })).toBeEnabled()
  })

  it("註冊成功：送出正規化後的資料，導向 S7 並顯示剛註冊的 Email", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register").mockResolvedValue({
      data: {
        id: "acc-1",
        email: "new@example.com",
        display_name: "小安",
        school_id: "school-nthu",
        email_verified: false,
      },
    } as RegisterResult)
    const router = renderSignup("/signup?redirect=%2Ftournaments%2F1")

    await fillForm(user, { email: "  New@Example.com ", displayName: " 小安 " })
    await user.click(screen.getByLabelText("學校"))
    await user.type(
      await screen.findByRole("combobox", { name: "搜尋學校" }),
      "清華",
    )
    await user.click(screen.getByRole("option", { name: "國立清華大學" }))
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(
      await screen.findByRole("heading", { name: "請收信驗證" }),
    ).toBeInTheDocument()
    expect(register).toHaveBeenCalledWith({
      body: {
        email: "New@Example.com",
        password: "12345678",
        display_name: "小安",
        school_id: "school-nthu",
        redirect: "/tournaments/1",
      },
    })
    expect(router.state.location.pathname).toBe("/verify-email")
    expect(router.state.location.search).toEqual({ redirect: "/tournaments/1" })
    // Email 不放進網址
    expect(router.state.location.href).not.toContain("example.com")
    expect(screen.getByText("new@example.com")).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveValue("new@example.com")
    expect(
      screen.getByRole("button", { name: "重寄驗證信" }),
    ).toBeInTheDocument()
  })

  it("Email 已註冊（409）：表單頂部 Alert 顯示伺服器訊息", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "register").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "EMAIL_ALREADY_REGISTERED",
          message: "這個 Email 已經註冊過。",
        },
      }),
    )
    renderSignup()

    await fillForm(user)
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這個 Email 已經註冊過。",
    )
  })

  it("密碼太短：送出前在密碼欄下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register")
    renderSignup()

    await fillForm(user, { password: "1234567" })
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(
      await within(field("密碼")).findByText("密碼至少需要 8 個字元"),
    ).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("伺服器的 422：密碼錯誤顯示在密碼欄、SCHOOL_NOT_FOUND 顯示在學校欄", async () => {
    const user = userEvent.setup()
    vi.spyOn(IdentityService, "register").mockRejectedValue(
      httpError(422, {
        detail: [
          {
            type: "password_too_short",
            loc: ["body", "password"],
            msg: "密碼至少需要 8 個字元",
          },
          {
            type: "SCHOOL_NOT_FOUND",
            loc: ["body", "school_id"],
            msg: "找不到這間學校",
          },
        ],
      }),
    )
    renderSignup()

    await fillForm(user)
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(
      await within(field("密碼")).findByText("密碼至少需要 8 個字元"),
    ).toBeInTheDocument()
    expect(
      within(field("學校")).getByText("找不到這間學校"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("必填欄位空白：顯示繁中提示", async () => {
    const user = userEvent.setup()
    renderSignup()

    await user.click(await screen.findByRole("button", { name: "註冊帳號" }))

    expect(
      await within(field("Email")).findByText("請輸入 Email"),
    ).toBeInTheDocument()
    expect(
      within(field("顯示名稱")).getByText("請輸入顯示名稱"),
    ).toBeInTheDocument()
  })

  it("redirect 參數不是站內路徑時忽略", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register").mockResolvedValue({
      data: {
        id: "acc-2",
        email: "new@example.com",
        display_name: "小安",
        school_id: null,
        email_verified: false,
      },
    } as RegisterResult)
    const router = renderSignup(
      "/signup?redirect=https%3A%2F%2Fevil.example.com",
    )

    await fillForm(user)
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    await screen.findByRole("heading", { name: "請收信驗證" })
    expect(register.mock.calls[0][0].body.redirect).toBeNull()
    expect(register.mock.calls[0][0].body.school_id).toBeNull()
    expect(router.state.location.href).toBe("/verify-email")
  })

  it("顯示名稱以碼位計算：50 個 emoji／擴展區漢字可以送出", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register").mockResolvedValue({
      data: {
        id: "acc-3",
        email: "new@example.com",
        display_name: "x",
        school_id: null,
        email_verified: false,
      },
    } as RegisterResult)
    renderSignup()
    // 每個字都是 2 個 UTF-16 單位：共 50 個字、100 個單位
    const astralName = "😀𠀀".repeat(25)
    expect(astralName.length).toBe(100)

    await fillForm(user, { displayName: astralName })
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    await screen.findByRole("heading", { name: "請收信驗證" })
    expect(register.mock.calls[0][0].body.display_name).toBe(astralName)
  })

  it("51 個 emoji 的顯示名稱：在欄位下方提示", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register")
    renderSignup()

    await fillForm(user, { displayName: "😀".repeat(51) })
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(
      await within(field("顯示名稱")).findByText("顯示名稱最多 50 個字"),
    ).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("密碼超過 128 個字元（以碼位計算）：在密碼欄下方提示，不呼叫 API", async () => {
    const user = userEvent.setup()
    const register = vi.spyOn(IdentityService, "register")
    renderSignup()

    // 129 個 emoji：UTF-16 長度 258，碼位 129
    await fillForm(user, { password: "😀".repeat(129) })
    await user.click(screen.getByRole("button", { name: "註冊帳號" }))

    expect(
      await within(field("密碼")).findByText("密碼最多 128 個字元"),
    ).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it("學校清單載入失敗：選單停用，顯示「無法載入學校清單」，按「重新載入」再抓一次", async () => {
    const user = userEvent.setup()
    const listSchools = vi
      .spyOn(IdentityService, "listSchools")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValueOnce({ data: SCHOOLS } as ListSchoolsResult)
    renderSignup("/signup", { mockSchools: false })

    const picker = await screen.findByLabelText("學校")
    await within(field("學校")).findByText(SCHOOL_LIST_ERROR_TEXT)
    expect(picker).toBeDisabled()
    expect(screen.queryByText("找不到這間學校")).toBeNull()

    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(listSchools).toHaveBeenCalledTimes(2)
    await within(field("學校")).findByText("選擇學校（選填）")
    expect(screen.getByLabelText("學校")).toBeEnabled()
    expect(screen.queryByRole("button", { name: "重新載入" })).toBeNull()
  })
})
