import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { IdentityService } from "@/client"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  LAST_IDENTITY_STORAGE_KEY,
} from "@/features/identity/auth"
import {
  ACCOUNT,
  BROWSE,
  PLATFORM_ADMIN,
  renderApp,
  signInAs,
} from "./auth-fixtures"

type ReadApplicationResult = Awaited<
  ReturnType<typeof IdentityService.readCurrentOrganizerApplication>
>
type ListSchoolsResult = Awaited<ReturnType<typeof IdentityService.listSchools>>
type ListApplicationsResult = Awaited<
  ReturnType<typeof IdentityService.listOrganizerApplications>
>

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

async function openSwitcher(user: ReturnType<typeof userEvent.setup>) {
  const banner = await screen.findByRole("banner")
  await user.click(
    await within(banner).findByRole("button", { name: /切換身分（目前：/ }),
  )
  return screen.findByRole("menu")
}

describe("頂欄", () => {
  it("未登入：有「登入」（站內連結）與「註冊」，沒有身分切換器", async () => {
    renderApp("/")

    const banner = await screen.findByRole("banner")
    expect(
      await within(banner).findByRole("link", { name: "登入" }),
    ).toHaveAttribute("href", "/login")
    expect(within(banner).getByRole("link", { name: "註冊" })).toBeVisible()
    expect(
      within(banner).queryByRole("button", { name: /切換身分/ }),
    ).toBeNull()
  })

  it("已登入：重新整理（重新渲染）後仍是登入狀態，「登入」「註冊」消失", async () => {
    signInAs()
    renderApp("/")

    const banner = await screen.findByRole("banner")
    expect(
      await within(banner).findByRole("button", {
        name: "切換身分（目前：瀏覽賽事）",
      }),
    ).toBeInTheDocument()
    expect(within(banner).queryByRole("link", { name: "登入" })).toBeNull()
    expect(within(banner).queryByRole("link", { name: "註冊" })).toBeNull()
  })

  it("已登入的手機選單：Sheet 內沒有「註冊」", async () => {
    const user = userEvent.setup()
    signInAs()
    renderApp("/")

    await user.click(await screen.findByRole("button", { name: "開啟選單" }))

    const sheet = await screen.findByRole("dialog", { name: "選單" })
    expect(within(sheet).queryByRole("link", { name: "註冊" })).toBeNull()
  })

  it("Logo 連到目前身分的首頁", async () => {
    window.localStorage.setItem(LAST_IDENTITY_STORAGE_KEY, "platform_admin")
    signInAs({ identities: [BROWSE, PLATFORM_ADMIN] })
    renderApp("/")

    await waitFor(() =>
      expect(screen.getByRole("link", { name: "FLOW 首頁" })).toHaveAttribute(
        "href",
        "/admin/applications",
      ),
    )
  })
})

describe("頂欄的跨分頁同步與 Logo 點擊", () => {
  it.each([
    ["其他分頁登出", ACCESS_TOKEN_STORAGE_KEY],
    ["其他分頁清除網站資料（key 為 null）", null],
  ])("%s：這個分頁的頂欄換回「登入」", async (_, key) => {
    signInAs()
    renderApp("/")
    const banner = await screen.findByRole("banner")
    await within(banner).findByRole("button", { name: /切換身分/ })

    act(() => {
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
      window.dispatchEvent(new StorageEvent("storage", { key }))
    })

    expect(
      await within(banner).findByRole("link", { name: "登入" }),
    ).toBeInTheDocument()
  })

  it("Logo 的修飾鍵與中鍵點擊交給瀏覽器（開新分頁），一般點擊在站內導覽", async () => {
    window.localStorage.setItem(LAST_IDENTITY_STORAGE_KEY, "platform_admin")
    signInAs({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/")
    const logo = await screen.findByRole("link", { name: "FLOW 首頁" })
    await waitFor(() =>
      expect(logo).toHaveAttribute("href", "/admin/applications"),
    )
    // 記下 HrefLink 處理後是否已 preventDefault，再擋掉 jsdom 不支援的整頁導覽
    const handledInApp: boolean[] = []
    const record = (event: MouseEvent) => {
      handledInApp.push(event.defaultPrevented)
      event.preventDefault()
    }
    window.addEventListener("click", record)
    try {
      for (const init of [
        { ctrlKey: true },
        { metaKey: true },
        { shiftKey: true },
        { altKey: true },
        { button: 1 },
      ]) {
        fireEvent.click(logo, init)
      }
      expect(handledInApp).toEqual([false, false, false, false, false])
      expect(router.state.location.pathname).toBe("/")

      fireEvent.click(logo)

      expect(handledInApp[handledInApp.length - 1]).toBe(true)
      await waitFor(() =>
        expect(router.state.location.pathname).toBe("/admin/applications"),
      )
    } finally {
      window.removeEventListener("click", record)
    }
  })
})

describe("身分切換器", () => {
  it("平台管理員：列出「瀏覽賽事」「平台管理」，目前身分有 brand 左條，底部有「帳號資料」「登出」", async () => {
    const user = userEvent.setup()
    signInAs({
      account: { ...ACCOUNT, is_platform_admin: true },
      identities: [BROWSE, PLATFORM_ADMIN],
    })
    renderApp("/")

    const menu = await openSwitcher(user)

    const items = within(menu).getAllByRole("menuitem")
    expect(items.map((item) => item.textContent)).toEqual([
      "瀏覽賽事",
      "平台管理",
      "全部身分",
      "申請成為主辦方",
      "帳號資料",
      "登出",
    ])
    const browse = within(menu).getByRole("menuitem", { name: "瀏覽賽事" })
    expect(browse).toHaveAttribute("aria-current", "true")
    expect(browse).toHaveClass("border-l-2", "border-brand")
    expect(
      within(menu).getByRole("menuitem", { name: "平台管理" }),
    ).not.toHaveClass("border-brand")
    expect(within(menu).getByText("小安")).toBeInTheDocument()
    expect(within(menu).getByText("an@example.com")).toBeInTheDocument()
  })

  it("切換身分：記住身分並前往該身分首頁，目前身分隨之改變", async () => {
    const user = userEvent.setup()
    signInAs({
      account: { ...ACCOUNT, is_platform_admin: true },
      identities: [BROWSE, PLATFORM_ADMIN],
    })
    vi.spyOn(IdentityService, "listOrganizerApplications").mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 20 },
    } as unknown as ListApplicationsResult)
    const router = renderApp("/")

    const menu = await openSwitcher(user)
    await user.click(within(menu).getByRole("menuitem", { name: "平台管理" }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/admin/applications"),
    )
    expect(window.localStorage.getItem(LAST_IDENTITY_STORAGE_KEY)).toBe(
      "platform_admin",
    )
    expect(
      await screen.findByRole("heading", { name: "主辦方申請" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "切換身分（目前：平台管理）" }),
    ).toBeInTheDocument()
  })

  it("「全部身分」到 S11，「帳號資料」到 S10", async () => {
    const user = userEvent.setup()
    signInAs({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/")

    let menu = await openSwitcher(user)
    await user.click(within(menu).getByRole("menuitem", { name: "全部身分" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/me"))

    menu = await openSwitcher(user)
    await user.click(within(menu).getByRole("menuitem", { name: "帳號資料" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/account"))
  })

  it.each([
    ["已驗證", ACCOUNT],
    ["未驗證 Email", { ...ACCOUNT, email_verified: false }],
  ])(
    "非主辦方（%s）：「帳號資料」上方有「申請成為主辦方」，點了到 S15",
    async (_, account) => {
      const user = userEvent.setup()
      signInAs({ account })
      vi.spyOn(
        IdentityService,
        "readCurrentOrganizerApplication",
      ).mockResolvedValue({ data: {} } as unknown as ReadApplicationResult)
      vi.spyOn(IdentityService, "listSchools").mockResolvedValue({
        data: [{ id: "school-ntu", name: "國立臺灣大學" }],
      } as ListSchoolsResult)
      const router = renderApp("/")

      const menu = await openSwitcher(user)
      const labels = within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent)
      expect(labels.indexOf("申請成為主辦方")).toBe(
        labels.indexOf("帳號資料") - 1,
      )
      await user.click(
        within(menu).getByRole("menuitem", { name: "申請成為主辦方" }),
      )

      await waitFor(() =>
        expect(router.state.location.pathname).toBe("/organizer/apply"),
      )
    },
  )

  it("主辦方：沒有「申請成為主辦方」", async () => {
    const user = userEvent.setup()
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    renderApp("/")

    const menu = await openSwitcher(user)
    await within(menu).findByRole("menuitem", { name: "帳號資料" })

    expect(
      within(menu).queryByRole("menuitem", { name: "申請成為主辦方" }),
    ).toBeNull()
  })

  it("登出：不需確認，清除登入狀態並回到 S1；上次身分保留", async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(LAST_IDENTITY_STORAGE_KEY, "platform_admin")
    signInAs({ identities: [BROWSE, PLATFORM_ADMIN] })
    const router = renderApp("/me")

    const menu = await openSwitcher(user)
    await user.click(within(menu).getByRole("menuitem", { name: "登出" }))

    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    expect(window.localStorage.getItem(LAST_IDENTITY_STORAGE_KEY)).toBe(
      "platform_admin",
    )
    const banner = await screen.findByRole("banner")
    expect(
      await within(banner).findByRole("link", { name: "登入" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alertdialog")).toBeNull()
  })
})
