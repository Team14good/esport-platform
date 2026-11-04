import { QueryClient } from "@tanstack/react-query"
import { act, cleanup, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  type MockInstance,
  vi,
} from "vitest"

import { IdentityService, type OrganizerApplicationRead } from "@/client"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  currentAccountQueryOptions,
} from "@/features/identity/auth"
import { organizerApplicationQueryOptions } from "@/features/identity/organizer-application"
import {
  ORGANIZER_APPLY_BANNER_TEXT,
  organizerBannerDismissedKey,
} from "@/features/tournaments/OrganizerApplyBanner"
import { EMPTY_TOURNAMENTS_TEXT } from "@/features/tournaments/TournamentList"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadApplicationResult = Awaited<
  ReturnType<typeof IdentityService.readCurrentOrganizerApplication>
>
type ListSchoolsResult = Awaited<ReturnType<typeof IdentityService.listSchools>>

const APPLY_BUTTON = { name: "申請成為主辦方" } as const

function application(
  status: OrganizerApplicationRead["status"],
): OrganizerApplicationRead {
  return {
    id: "app-1",
    club_name: "臺大電競社",
    school_id: "school-ntu",
    school_name: "國立臺灣大學",
    status,
    reject_reason: status === "rejected" ? "資料不完整" : null,
    created_at: "2026-10-29T06:05:00Z",
  }
}

/** 最新申請；null 表示沒申請過（產生的 client 會把 null 回應換成 {}）。 */
function mockApplication(app: OrganizerApplicationRead | null) {
  return vi
    .spyOn(IdentityService, "readCurrentOrganizerApplication")
    .mockResolvedValue({ data: app ?? {} } as unknown as ReadApplicationResult)
}

// renderApp 在 provider 裡自己建立 QueryClient；從 mount 的 this 取得最新一個，
// 才能等查詢真的落定（success 或 error），不會在 pending 時就斷言「不顯示」
let mountQueryClient: MockInstance<QueryClient["mount"]>

function currentQueryClient(): QueryClient {
  const { contexts } = mountQueryClient.mock
  const client = contexts[contexts.length - 1]
  if (!(client instanceof QueryClient)) throw new Error("QueryClient 尚未掛載")
  return client
}

type Settled = "success" | "error" | "pending"

/**
 * 等 S1 出現、帳號與申請查詢走到指定狀態，再讓畫面套用最新的查詢結果。
 * 斷言「不顯示」前一定要等到這裡，否則查詢還在 pending 時本來就不顯示，測試會空過。
 */
async function settle(expected: { account: Settled; application: Settled }) {
  expect(await screen.findByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
  await waitFor(() => {
    const client = currentQueryClient()
    expect(
      client.getQueryState(currentAccountQueryOptions().queryKey)?.status,
    ).toBe(expected.account)
    expect(
      client.getQueryState(organizerApplicationQueryOptions().queryKey)?.status,
    ).toBe(expected.application)
  })
  await act(async () => {})
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await import("@/features/tournaments/TournamentList")
})

beforeEach(() => {
  // setup.ts 每個測試後會 restoreAllMocks，所以每個測試重新掛上
  mountQueryClient = vi.spyOn(QueryClient.prototype, "mount")
})

function bannerText() {
  return screen.queryByText(ORGANIZER_APPLY_BANNER_TEXT)
}

describe("S1「想辦賽事？」banner", () => {
  it("未登入：不顯示，也不送帳號與申請請求", async () => {
    const readAccount = vi.spyOn(IdentityService, "readCurrentAccount")
    const readApplication = mockApplication(null)
    renderApp("/")

    expect(await screen.findByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
    await act(async () => {})
    expect(bannerText()).toBeNull()
    expect(readAccount).not.toHaveBeenCalled()
    expect(readApplication).not.toHaveBeenCalled()
  })

  it("一般帳號、沒申請過：顯示；點「申請成為主辦方」到 /organizer/apply", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApplication(null)
    vi.spyOn(IdentityService, "listSchools").mockResolvedValue({
      data: [{ id: "school-ntu", name: "國立臺灣大學" }],
    } as ListSchoolsResult)
    const router = renderApp("/")

    const button = await screen.findByRole("button", APPLY_BUTTON)
    expect(bannerText()).toBeInTheDocument()
    expect(button.closest('[data-slot="page-banner"]')).toHaveAttribute(
      "role",
      "status",
    )

    await user.click(button)
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/organizer/apply"),
    )
  })

  it("最新申請被退回：顯示", async () => {
    signInAs()
    mockApplication(application("rejected"))
    renderApp("/")

    expect(await screen.findByRole("button", APPLY_BUTTON)).toBeInTheDocument()
  })

  it("最新申請待審核：不顯示", async () => {
    signInAs()
    mockApplication(application("pending"))
    renderApp("/")

    await settle({ account: "success", application: "success" })
    expect(bannerText()).toBeNull()
  })

  it("主辦方：不顯示", async () => {
    signInAs({
      account: { ...ACCOUNT, is_organizer: true },
    })
    mockApplication(application("approved"))
    renderApp("/")

    await settle({ account: "success", application: "success" })
    expect(bannerText()).toBeNull()
  })

  it("申請資料載入中：不顯示", async () => {
    signInAs()
    vi.spyOn(
      IdentityService,
      "readCurrentOrganizerApplication",
    ).mockReturnValue(new Promise(() => {}) as never)
    renderApp("/")

    await settle({ account: "success", application: "pending" })
    expect(bannerText()).toBeNull()
  })

  it("申請資料載入失敗：不顯示，也不另顯示錯誤", async () => {
    signInAs()
    vi.spyOn(
      IdentityService,
      "readCurrentOrganizerApplication",
    ).mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/")

    await settle({ account: "success", application: "error" })
    expect(bannerText()).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("帳號載入失敗：不顯示", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
    vi.spyOn(IdentityService, "readCurrentAccount").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    vi.spyOn(IdentityService, "listCurrentIdentities").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    mockApplication(null)
    renderApp("/")

    await settle({ account: "error", application: "success" })
    expect(bannerText()).toBeNull()
  })

  it("關閉：立即消失並記在 localStorage；重新整理後仍不顯示", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApplication(null)
    renderApp("/")

    await user.click(await screen.findByRole("button", { name: "關閉提示" }))
    expect(bannerText()).toBeNull()
    expect(
      window.localStorage.getItem(organizerBannerDismissedKey(ACCOUNT.id)),
    ).toBe("1")

    // 重新整理：整個畫面重新渲染
    cleanup()
    signInAs()
    mockApplication(null)
    renderApp("/")
    await settle({ account: "success", application: "success" })
    expect(bannerText()).toBeNull()
  })

  it("換另一個帳號登入：仍會顯示", async () => {
    window.localStorage.setItem(organizerBannerDismissedKey(ACCOUNT.id), "1")
    signInAs({ account: { ...ACCOUNT, id: "acc-2", email: "bo@example.com" } })
    mockApplication(null)
    renderApp("/")

    expect(await screen.findByRole("button", APPLY_BUTTON)).toBeInTheDocument()
  })

  it("localStorage 讀寫丟例外：讀不到視為沒關閉；關閉後本次隱藏，不報錯", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApplication(null)
    const key = organizerBannerDismissedKey(ACCOUNT.id)
    const getItem = Storage.prototype.getItem
    const setItem = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      name: string,
    ) {
      if (name === key) throw new DOMException("blocked", "SecurityError")
      return getItem.call(this, name)
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      name: string,
      value: string,
    ) {
      if (name === key) throw new DOMException("full", "QuotaExceededError")
      setItem.call(this, name, value)
    })
    renderApp("/")

    await user.click(await screen.findByRole("button", { name: "關閉提示" }))
    expect(bannerText()).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })
})
