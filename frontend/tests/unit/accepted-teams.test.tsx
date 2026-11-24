import { act, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest"

import {
  DisputesService,
  type MyTeamCard,
  type PublicAcceptedTeams,
  type PublicTournament,
  RegistrationService,
  type RegistrationStatus,
  type ReportableTeam,
  type TeamDetail,
  TournamentsService,
} from "@/client"
import {
  ROW_REPORT_TEXT,
  ROW_REPORTED_TEXT,
} from "@/features/disputes/AcceptedTeamReportAction"
import {
  NO_ACCEPTED_TEAMS_TEXT,
  PRIORITY_HIDDEN_TEXT,
} from "@/features/registration/AcceptedTeamsPage"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ReadTournamentResult = Awaited<
  ReturnType<typeof TournamentsService.readPublicTournament>
>
type AcceptedResult = Awaited<
  ReturnType<typeof RegistrationService.listAcceptedTeams>
>
type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>
type ReportableResult = Awaited<
  ReturnType<typeof DisputesService.listReportableTeams>
>

// 裝置時間：台北 2025/10/10（五）20:00
const NOW = new Date("2025-10-10T12:00:00Z")

function at(offsetMs: number): string {
  return new Date(NOW.getTime() + offsetMs).toISOString()
}

function tournament(
  overrides: Partial<PublicTournament> = {},
): PublicTournament {
  return {
    id: "t-1",
    name: "期中盃",
    status: "open",
    mode: "campus",
    game_name: "特戰英豪",
    capacity: 16,
    registration_start: "2025-10-09T11:00:00Z",
    priority_end: "2025-10-10T11:00:00Z",
    registration_end: "2025-10-17T11:00:00Z",
    start_at: "2025-10-18T11:00:00Z",
    round_interval_minutes: 180,
    livestream_url: null,
    ...overrides,
  }
}

function mockTournament(data: PublicTournament) {
  return vi
    .spyOn(TournamentsService, "readPublicTournament")
    .mockResolvedValue({ data } as unknown as ReadTournamentResult)
}

const TEAMS = [
  { id: "team-a", name: "夜貓隊" },
  { id: "team-b", name: "晨鳥隊" },
  { id: "team-c", name: "午後隊" },
]

function accepted(
  teams = TEAMS,
  announceAt: string | null = null,
): PublicAcceptedTeams {
  return { announce_at: announceAt, teams }
}

function mockAccepted(data: PublicAcceptedTeams) {
  return vi
    .spyOn(RegistrationService, "listAcceptedTeams")
    .mockResolvedValue({ data } as unknown as AcceptedResult)
}

function card(status: RegistrationStatus = "accepted"): MyTeamCard {
  return {
    team_id: "team-a",
    team_name: "夜貓隊",
    tournament_id: "t-1",
    tournament_name: "期中盃",
    game_name: "特戰英豪",
    registration_status: status,
    waitlist_position: null,
    waitlist_reason: null,
    representative_backfill: null,
    waitlist_phase: null,
  }
}

const REPORTABLE: ReportableTeam[] = [
  { id: "team-c", name: "午後隊", has_open_report: true },
  { id: "team-b", name: "晨鳥隊", has_open_report: false },
]

/** 登入者是夜貓隊（team-a）的成員；預設為正取隊伍的隊長。 */
function mockMyTeam({
  status = "accepted",
  role = "captain",
}: {
  status?: RegistrationStatus
  role?: "captain" | "player"
} = {}) {
  const myTeams = vi
    .spyOn(RegistrationService, "listMyTeams")
    .mockResolvedValue({ data: [card(status)] } as MyTeamsResult)
  const readTeam = vi.spyOn(RegistrationService, "readTeam").mockResolvedValue({
    data: { id: "team-a", my_role: role } as TeamDetail,
  } as ReadTeamResult)
  const reportable = vi
    .spyOn(DisputesService, "listReportableTeams")
    .mockResolvedValue({ data: REPORTABLE } as ReportableResult)
  return { myTeams, readTeam, reportable }
}

function row(name: string): HTMLElement {
  const item = screen.getByText(name).closest("li")
  if (!item) throw new Error(`找不到 ${name} 的列`)
  return item
}

/** 等所有查詢結束，再確認沒有出現某些元素（避免只是還在載入）。 */
async function settle() {
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免第一個測試因冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await Promise.all([
    import("@/features/tournaments/TournamentPage"),
    import("@/features/registration/AcceptedTeamsPage"),
  ])
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(NOW)
  // jsdom 沒有 matchMedia；S20 的 useIsMobile 只用它監聽變化，寬度看 innerWidth
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe("S2「正取隊伍」分頁", () => {
  it("分頁依序為總覽、對戰表、正取隊伍；點「正取隊伍」到 /teams", async () => {
    mockTournament(tournament())
    mockAccepted(accepted())
    const router = renderApp("/tournaments/t-1")

    await screen.findByRole("tab", { name: "正取隊伍" })
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "總覽",
      "對戰表",
      "正取隊伍",
    ])
    const user = userEvent.setup()
    await user.click(screen.getByRole("tab", { name: "正取隊伍" }))

    expect(await screen.findByText("夜貓隊")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe("/tournaments/t-1/teams")
    expect(screen.getByRole("tab", { name: "正取隊伍" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("觀眾依回傳順序看到隊名，沒有「檢舉」，也不查我的隊伍", async () => {
    mockTournament(tournament())
    mockAccepted(accepted())
    const myTeams = vi.spyOn(RegistrationService, "listMyTeams")
    renderApp("/tournaments/t-1/teams")

    const list = await screen.findByRole("list")
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["夜貓隊", "晨鳥隊", "午後隊"])
    expect(
      screen.getByRole("heading", { level: 1, name: "期中盃" }),
    ).toBeInTheDocument()
    await settle()
    expect(screen.queryByRole("button", { name: ROW_REPORT_TEXT })).toBeNull()
    expect(myTeams).not.toHaveBeenCalled()
  })

  it("公布後沒有正取：「目前還沒有正取隊伍。」", async () => {
    mockTournament(tournament())
    mockAccepted(accepted([]))
    renderApp("/tournaments/t-1/teams")

    expect(await screen.findByText(NO_ACCEPTED_TEAMS_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("timer")).toBeNull()
  })

  it("優先期內：空狀態與「優先期結束」倒數；歸零後重抓並顯示名單", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    vi.setSystemTime(NOW)
    mockTournament(tournament())
    const list = vi
      .spyOn(RegistrationService, "listAcceptedTeams")
      .mockResolvedValueOnce({
        data: accepted([], at(1000)),
      } as unknown as AcceptedResult)
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: accepted() } as unknown as AcceptedResult)
    renderApp("/tournaments/t-1/teams")

    expect(await screen.findByText(PRIORITY_HIDDEN_TEXT)).toBeInTheDocument()
    const countdown = document.querySelector("[data-slot=countdown]")
    expect(countdown).toHaveAttribute("data-variant", "muted")
    expect(countdown).toHaveTextContent("優先期結束")
    expect(screen.getByRole("timer")).toHaveTextContent("00:01")

    // 歸零：立即重抓一次（失敗，不重試，畫面維持空狀態）
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    await settle()
    expect(screen.getByText(PRIORITY_HIDDEN_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "重新載入" })).toBeNull()

    // 5 秒後再抓一次：已公布
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(await screen.findByText("夜貓隊")).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(3)
    expect(screen.queryByText(PRIORITY_HIDDEN_TEXT)).toBeNull()
  })

  it("名單載入失敗：顯示錯誤與「重新載入」，按下後重抓", async () => {
    mockTournament(tournament())
    const list = vi
      .spyOn(RegistrationService, "listAcceptedTeams")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: accepted() } as unknown as AcceptedResult)
    renderApp("/tournaments/t-1/teams")

    const user = userEvent.setup()
    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    expect(await screen.findByText("夜貓隊")).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })

  it("已取消：「此賽事已取消」banner，名單照常顯示", async () => {
    mockTournament(tournament({ status: "cancelled" }))
    mockAccepted(accepted())
    renderApp("/tournaments/t-1/teams")

    expect(await screen.findByRole("alert")).toHaveTextContent("此賽事已取消")
    expect(await screen.findByText("晨鳥隊")).toBeInTheDocument()
  })

  it("不存在的賽事：404 頁", async () => {
    vi.spyOn(TournamentsService, "readPublicTournament").mockRejectedValue(
      httpError(404, {
        detail: { code: "TOURNAMENT_NOT_FOUND", message: "找不到這場賽事。" },
      }),
    )
    mockAccepted(accepted())
    renderApp("/tournaments/no-such/teams")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
  })
})

describe("正取隊伍每列的「檢舉」", () => {
  it("隊長：自己的隊伍沒有、可檢舉的有「檢舉」、處理中的顯示「已檢舉・處理中」", async () => {
    signInAs()
    mockTournament(tournament())
    mockAccepted(accepted())
    mockMyTeam()
    renderApp("/tournaments/t-1/teams")

    await screen.findByText("晨鳥隊")
    expect(
      await within(row("晨鳥隊")).findByRole("button", {
        name: ROW_REPORT_TEXT,
      }),
    ).toBeInTheDocument()
    expect(within(row("午後隊")).getByText(ROW_REPORTED_TEXT)).toBeVisible()
    expect(within(row("午後隊")).queryByRole("button")).toBeNull()
    expect(within(row("夜貓隊")).queryByRole("button")).toBeNull()
    expect(within(row("夜貓隊")).queryByText(ROW_REPORTED_TEXT)).toBeNull()
    expect(
      screen.getAllByRole("button", { name: ROW_REPORT_TEXT }),
    ).toHaveLength(1)
  })

  it("按「檢舉」開 S20，檢舉對象只有該列的隊伍", async () => {
    signInAs()
    mockTournament(tournament())
    mockAccepted(accepted())
    mockMyTeam()
    renderApp("/tournaments/t-1/teams")
    const user = userEvent.setup()

    await screen.findByText("晨鳥隊")
    await user.click(
      await within(row("晨鳥隊")).findByRole("button", {
        name: ROW_REPORT_TEXT,
      }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出檢舉" })
    await user.click(within(dialog).getByRole("combobox", { name: "檢舉對象" }))

    const options = await screen.findAllByRole("option")
    expect(options.map((option) => option.textContent)).toEqual(["晨鳥隊"])
  })

  it("隊員：沒有「檢舉」，也不呼叫 reportable-teams", async () => {
    signInAs()
    mockTournament(tournament())
    mockAccepted(accepted())
    const { readTeam, reportable } = mockMyTeam({ role: "player" })
    renderApp("/tournaments/t-1/teams")

    await screen.findByText("晨鳥隊")
    await vi.waitFor(() => expect(readTeam).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: ROW_REPORT_TEXT })).toBeNull()
    expect(reportable).not.toHaveBeenCalled()
  })

  it("組隊中的隊長：沒有「檢舉」，也不查隊伍", async () => {
    signInAs()
    mockTournament(tournament())
    mockAccepted(accepted())
    const { myTeams, readTeam, reportable } = mockMyTeam({ status: "forming" })
    renderApp("/tournaments/t-1/teams")

    await screen.findByText("晨鳥隊")
    await vi.waitFor(() => expect(myTeams).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: ROW_REPORT_TEXT })).toBeNull()
    expect(readTeam).not.toHaveBeenCalled()
    expect(reportable).not.toHaveBeenCalled()
  })

  it.each(["finished", "cancelled"] as const)(
    "賽事為 %s：沒有「檢舉」，也不查我的隊伍",
    async (status) => {
      signInAs()
      mockTournament(tournament({ status }))
      mockAccepted(accepted())
      const { myTeams } = mockMyTeam()
      renderApp("/tournaments/t-1/teams")

      await screen.findByText("晨鳥隊")
      await settle()
      expect(screen.queryByRole("button", { name: ROW_REPORT_TEXT })).toBeNull()
      expect(screen.queryByText(ROW_REPORTED_TEXT)).toBeNull()
      expect(myTeams).not.toHaveBeenCalled()
    },
  )
})

describe("S2 總覽的已正取隊數", () => {
  it("開放報名：顯示「已正取 3／16 隊」", async () => {
    mockTournament(tournament())
    mockAccepted(accepted())
    renderApp("/tournaments/t-1")

    expect(await screen.findByText("已正取 3／16 隊")).toBeInTheDocument()
  })

  it("優先期內照實顯示 0", async () => {
    mockTournament(tournament({ capacity: 8 }))
    mockAccepted(accepted([], at(60_000)))
    renderApp("/tournaments/t-1")

    expect(await screen.findByText("已正取 0／8 隊")).toBeInTheDocument()
  })

  it.each([
    "upcoming",
    "closed",
    "published",
    "ongoing",
    "finished",
    "cancelled",
  ] as const)("賽事為 %s 時不顯示，也不查名單", async (status) => {
    mockTournament(tournament({ status, registration_start: at(60_000) }))
    const list = mockAccepted(accepted())
    renderApp("/tournaments/t-1")

    await screen.findByRole("heading", { level: 1, name: "期中盃" })
    await settle()
    expect(screen.queryByText(/已正取/)).toBeNull()
    expect(list).not.toHaveBeenCalled()
  })

  it("名單載入失敗：不顯示這一行", async () => {
    mockTournament(tournament())
    const list = vi
      .spyOn(RegistrationService, "listAcceptedTeams")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/tournaments/t-1")

    await screen.findByRole("heading", { level: 1, name: "期中盃" })
    await vi.waitFor(() => expect(list).toHaveBeenCalled())
    await settle()
    expect(screen.queryByText(/已正取/)).toBeNull()
  })
})
