import { act, screen, waitFor } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import {
  IdentityService,
  type PublicTournament,
  TournamentsService,
} from "@/client"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { CREATE_TOURNAMENT_TEXT } from "@/features/tournaments/CreateTournamentButton"
import { ORGANIZER_APPLY_BANNER_TEXT } from "@/features/tournaments/OrganizerApplyBanner"
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
type ListResult = Awaited<
  ReturnType<typeof TournamentsService.listPublicTournaments>
>

const CREATE_LINK = { name: CREATE_TOURNAMENT_TEXT } as const

/** 沒申請過主辦方（產生的 client 會把 null 回應換成 {}）。 */
function mockNoApplication() {
  return vi
    .spyOn(IdentityService, "readCurrentOrganizerApplication")
    .mockResolvedValue({ data: {} } as unknown as ReadApplicationResult)
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await import("@/features/tournaments/TournamentList")
})

describe("S1 空狀態的「建立賽事」", () => {
  it("主辦方：空狀態下方顯示「建立賽事」，連到 S26", async () => {
    signInAs({ account: { ...ACCOUNT, is_organizer: true } })
    mockNoApplication()
    renderApp("/")

    expect(await screen.findByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
    expect(await screen.findByRole("link", CREATE_LINK)).toHaveAttribute(
      "href",
      "/organizer/tournaments/new",
    )
  })

  it("主辦方、有賽事：不顯示", async () => {
    const { readAccount } = signInAs({
      account: { ...ACCOUNT, is_organizer: true },
    })
    mockNoApplication()
    const tournament: PublicTournament = {
      id: "t-1",
      name: "期中盃",
      status: "open",
      game_name: "特戰英豪",
      capacity: 16,
      registration_start: "2025-10-12T11:00:00Z",
      priority_end: "2025-10-13T11:00:00Z",
      registration_end: "2025-10-17T11:00:00Z",
      start_at: "2025-10-18T11:00:00Z",
      round_interval_minutes: 180,
      livestream_url: null,
    }
    vi.spyOn(TournamentsService, "listPublicTournaments").mockResolvedValue({
      data: [tournament],
    } as unknown as ListResult)
    renderApp("/")

    expect(
      await screen.findByRole("link", { name: /期中盃/ }),
    ).toBeInTheDocument()
    await waitFor(() => expect(readAccount).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByRole("link", CREATE_LINK)).toBeNull()
  })

  it("一般帳號：不顯示", async () => {
    signInAs()
    mockNoApplication()
    renderApp("/")

    // 申請主辦方 banner 出現代表帳號查詢已成功（is_organizer 為否），不是還在載入
    expect(
      await screen.findByText(ORGANIZER_APPLY_BANNER_TEXT),
    ).toBeInTheDocument()
    expect(screen.getByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("link", CREATE_LINK)).toBeNull()
  })

  it("帳號載入失敗：不顯示", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
    const readAccount = vi
      .spyOn(IdentityService, "readCurrentAccount")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    vi.spyOn(IdentityService, "listCurrentIdentities").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    mockNoApplication()
    renderApp("/")

    expect(await screen.findByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
    await waitFor(() => expect(readAccount).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByRole("link", CREATE_LINK)).toBeNull()
  })

  it("未登入：不顯示，也不查詢帳號", async () => {
    const readAccount = vi.spyOn(IdentityService, "readCurrentAccount")
    renderApp("/")

    expect(await screen.findByText(EMPTY_TOURNAMENTS_TEXT)).toBeInTheDocument()
    await act(async () => {})
    expect(screen.queryByRole("link", CREATE_LINK)).toBeNull()
    expect(readAccount).not.toHaveBeenCalled()
  })
})
