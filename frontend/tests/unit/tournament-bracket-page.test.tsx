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
  CompetitionService,
  type PublicBracket,
  type PublicTournament,
  TournamentsService,
} from "@/client"
import { BRACKET_PENDING_TEXT } from "@/features/competition/BracketPending"
import { createBracketFixture } from "@/features/competition/bracket-fixtures"
import { BRACKET_ABSENT_TEXT } from "@/features/competition/TournamentBracketPage"
import { BRACKET_POLL_INTERVAL_MS } from "@/features/competition/use-bracket-polling"
import { renderApp } from "./auth-fixtures"
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
type ReadBracketResult = Awaited<
  ReturnType<typeof CompetitionService.readPublicBracket>
>

// 裝置時間：台北 2025/10/10（五）20:00
const NOW = new Date("2025-10-10T12:00:00Z")

function tournament(
  overrides: Partial<PublicTournament> = {},
): PublicTournament {
  return {
    id: "t-1",
    name: "期中盃",
    status: "published",
    game_name: "特戰英豪",
    capacity: 16,
    // 台北 10/12（日）19:00 ～ 10/17（五）19:00，10/18（六）19:00 開賽
    registration_start: "2025-10-12T11:00:00Z",
    priority_end: "2025-10-13T11:00:00Z",
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

function bracket(teamCount = 8): PublicBracket {
  return {
    ...createBracketFixture({ teamCount, scenario: "scheduled" }),
    tournament_id: "t-1",
  }
}

function mockBracket(data: PublicBracket) {
  return vi
    .spyOn(CompetitionService, "readPublicBracket")
    .mockResolvedValue({ data } as unknown as ReadBracketResult)
}

const BRACKET_NOT_FOUND = httpError(404, {
  detail: { code: "BRACKET_NOT_FOUND", message: "這場賽事還沒有對戰表。" },
})

function mockNotDrawn() {
  return vi
    .spyOn(CompetitionService, "readPublicBracket")
    .mockRejectedValue(BRACKET_NOT_FOUND)
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免第一個測試因冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await Promise.all([
    import("@/features/tournaments/TournamentPage"),
    import("@/features/competition/TournamentBracketPage"),
  ])
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe("S3 對戰表", () => {
  it("從 S2 點「對戰表」分頁：網址改為 /bracket、分頁為選取狀態、顯示對戰樹", async () => {
    mockTournament(tournament())
    const read = mockBracket(bracket())
    const router = renderApp("/tournaments/t-1")

    const tab = await screen.findByRole("tab", { name: "對戰表" })
    expect(screen.getByRole("tab", { name: "總覽" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    await userEvent.click(tab)

    await vi.waitFor(() =>
      expect(router.state.location.pathname).toBe("/tournaments/t-1/bracket"),
    )
    expect(
      await screen.findByRole("tab", { name: "對戰表", selected: true }),
    ).toBeInTheDocument()
    const panel = screen.getByRole("tabpanel")
    expect(
      await within(panel).findByText("8 強", { exact: false }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledWith({ path: { tournament_id: "t-1" } })
    await vi.waitFor(() => expect(document.title).toBe("期中盃 · FLOW"))
  })

  it("場次卡整張連到該場 S4", async () => {
    mockTournament(tournament())
    const data = bracket()
    mockBracket(data)
    renderApp("/tournaments/t-1/bracket")

    const first = data.matches.find((m) => m.code === "M1")
    if (first === undefined) throw new Error("fixture 沒有 M1")
    const links = await screen.findAllByRole("link", { name: /^M1/ })
    expect(links[0]).toHaveAttribute(
      "href",
      `/tournaments/t-1/matches/${first.id}`,
    )
  })

  it.each([
    ["尚未開放", "upcoming"],
    ["開放報名", "open"],
  ] as const)(
    "%s、尚未抽籤：空狀態＋報名截止倒數，不算連線中斷",
    async (_, status) => {
      mockTournament(tournament({ status }))
      const read = mockNotDrawn()
      renderApp("/tournaments/t-1/bracket")

      expect(await screen.findByText(BRACKET_PENDING_TEXT)).toBeInTheDocument()
      const timer = await screen.findByRole("timer")
      expect(timer).toHaveTextContent("剩 6 天 23 小時")
      expect(screen.getByText("報名截止")).toBeInTheDocument()
      expect(read).toHaveBeenCalled()
      expect(screen.queryByText(/連線中斷/)).toBeNull()
    },
  )

  it("報名截止、尚未抽籤：空狀態＋「抽籤準備中」，沒有倒數", async () => {
    mockTournament(tournament({ status: "closed" }))
    mockNotDrawn()
    renderApp("/tournaments/t-1/bracket")

    expect(await screen.findByText(BRACKET_PENDING_TEXT)).toBeInTheDocument()
    expect(screen.getByText("抽籤準備中")).toBeInTheDocument()
    expect(screen.queryByRole("timer")).toBeNull()
  })

  it.each([
    ["已取消", "cancelled"],
    ["已結束（資料不一致）", "finished"],
  ] as const)(
    "%s、沒有對戰表：「這場賽事沒有對戰表。」，沒有倒數",
    async (_, status) => {
      mockTournament(tournament({ status }))
      mockNotDrawn()
      renderApp("/tournaments/t-1/bracket")

      expect(await screen.findByText(BRACKET_ABSENT_TEXT)).toBeInTheDocument()
      expect(screen.queryByText(BRACKET_PENDING_TEXT)).toBeNull()
      expect(screen.queryByRole("timer")).toBeNull()
      if (status === "cancelled") {
        expect(screen.getByRole("alert")).toHaveTextContent("此賽事已取消")
      }
    },
  )

  it("第一次載入對戰表就失敗（非 404）：顯示連線中斷 banner", async () => {
    mockTournament(tournament())
    vi.spyOn(CompetitionService, "readPublicBracket").mockRejectedValue(
      httpError(500, "Internal Server Error"),
    )
    renderApp("/tournaments/t-1/bracket")

    expect(await screen.findByText("連線中斷，正在重試")).toBeInTheDocument()
    expect(screen.queryByText(BRACKET_PENDING_TEXT)).toBeNull()
  })

  it("已取消又連線失敗：只顯示「此賽事已取消」一則 banner", async () => {
    mockTournament(tournament({ status: "cancelled" }))
    const read = vi
      .spyOn(CompetitionService, "readPublicBracket")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/tournaments/t-1/bracket")

    expect(await screen.findByRole("alert")).toHaveTextContent("此賽事已取消")
    await vi.waitFor(() => expect(read).toHaveBeenCalled())
    // 等失敗進到 query 狀態並重新渲染（未取消的同樣條件會出現連線中斷，見上一個測試）
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(screen.queryByText(/連線中斷/)).toBeNull()
    expect(document.querySelectorAll("[data-slot=page-banner]")).toHaveLength(1)
  })

  it("不存在的賽事：404 頁", async () => {
    vi.spyOn(TournamentsService, "readPublicTournament").mockRejectedValue(
      httpError(404, {
        detail: { code: "TOURNAMENT_NOT_FOUND", message: "找不到這場賽事。" },
      }),
    )
    mockNotDrawn()
    renderApp("/tournaments/no-such/bracket")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
  })

  it("id 格式錯誤（422）：404 頁，不重試", async () => {
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockRejectedValue(httpError(422, { detail: [] }))
    mockNotDrawn()
    renderApp("/tournaments/not-a-uuid/bracket")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("賽事首次載入 500：重試後顯示錯誤，按「重新載入」重抓", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] })
    vi.setSystemTime(NOW)
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({
        data: tournament(),
      } as unknown as ReadTournamentResult)
    mockBracket(bracket())
    renderApp("/tournaments/t-1/bracket")

    // 沿用全站規則重試 3 次（間隔 1、2、4 秒）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    vi.useRealTimers()
    expect(read).toHaveBeenCalledTimes(4)

    const user = userEvent.setup()
    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    expect(
      await screen.findByRole("heading", { level: 1, name: "期中盃" }),
    ).toBeInTheDocument()
  })

  it("非 BRACKET_NOT_FOUND 的 404（例如路由不存在）當成連線失敗，不顯示「尚未抽籤」", async () => {
    mockTournament(tournament())
    vi.spyOn(CompetitionService, "readPublicBracket").mockRejectedValue(
      httpError(404, { detail: "Not Found" }),
    )
    renderApp("/tournaments/t-1/bracket")

    expect(await screen.findByText("連線中斷，正在重試")).toBeInTheDocument()
    expect(screen.queryByText(BRACKET_PENDING_TEXT)).toBeNull()
  })

  it("從 S3 進入 S4：分頁標題換成場次的標題，不被 S3 還原成舊標題", async () => {
    // 開發模式的 S4 只認假對戰樹的賽事 id
    mockTournament(tournament({ id: "tournament-fixture" }))
    mockBracket({
      ...createBracketFixture({ teamCount: 32, scenario: "in_progress" }),
    })
    const router = renderApp("/tournaments/tournament-fixture/bracket")
    await vi.waitFor(() => expect(document.title).toBe("期中盃 · FLOW"))

    await act(() =>
      router.navigate({
        to: "/tournaments/$tournamentId/matches/$matchId",
        params: { tournamentId: "tournament-fixture", matchId: "match-M3" },
      }),
    )

    await vi.waitFor(() => expect(document.title).toMatch(/^32 強 · M3 · /))
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)))
    expect(document.title).toMatch(/^32 強 · M3 · /)
  })
})

describe("S3 輪詢", () => {
  beforeEach(() => {
    vi.useFakeTimers({
      toFake: [
        "Date",
        "setInterval",
        "clearInterval",
        "setTimeout",
        "clearTimeout",
      ],
      // 路由與頁面模組的載入要靠真實時間推進；輪詢間隔仍以 advanceTimersByTimeAsync 快轉
      shouldAdvanceTime: true,
    })
    vi.setSystemTime(NOW)
  })

  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms)
    })
  }

  it("抽籤後下一次輪詢出現對戰樹，並重抓賽事更新標題列的狀態", async () => {
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockResolvedValueOnce({
        data: tournament({ status: "closed" }),
      } as unknown as ReadTournamentResult)
      .mockResolvedValue({
        data: tournament({ status: "published" }),
      } as unknown as ReadTournamentResult)
    vi.spyOn(CompetitionService, "readPublicBracket")
      .mockRejectedValueOnce(BRACKET_NOT_FOUND)
      .mockResolvedValue({ data: bracket() } as unknown as ReadBracketResult)
    renderApp("/tournaments/t-1/bracket")
    expect(await screen.findByText("抽籤準備中")).toBeInTheDocument()

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(screen.queryByText(BRACKET_PENDING_TEXT)).toBeNull()
    expect(screen.getAllByRole("link", { name: /^M1/ }).length).toBeGreaterThan(
      0,
    )
    await advance(0)
    expect(read).toHaveBeenCalledTimes(2)
    expect(screen.getByText("賽程已公布")).toBeInTheDocument()
  })

  it("已顯示對戰樹後連續失敗 3 次：保留對戰樹，頁頂顯示連線中斷與最後更新時間", async () => {
    mockTournament(tournament())
    vi.spyOn(CompetitionService, "readPublicBracket")
      .mockResolvedValueOnce({
        data: bracket(),
      } as unknown as ReadBracketResult)
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/tournaments/t-1/bracket")
    expect(
      (await screen.findAllByRole("link", { name: /^M1/ })).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByText(/連線中斷/)).toBeNull()

    await advance(BRACKET_POLL_INTERVAL_MS * 2)
    expect(screen.queryByText(/連線中斷/)).toBeNull()
    await advance(BRACKET_POLL_INTERVAL_MS)

    // 最後一次成功是台北 20:00:00（NOW）
    expect(
      screen.getByText("連線中斷，正在重試 · 最後更新 20:00:00"),
    ).toBeInTheDocument()
    expect(screen.getAllByRole("link", { name: /^M1/ }).length).toBeGreaterThan(
      0,
    )
  })

  it("尚未抽籤時一次暫時失敗：維持空狀態與倒數，連續 3 次才顯示連線中斷", async () => {
    mockTournament(tournament({ status: "open" }))
    vi.spyOn(CompetitionService, "readPublicBracket")
      .mockRejectedValueOnce(BRACKET_NOT_FOUND)
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/tournaments/t-1/bracket")
    expect(await screen.findByText(BRACKET_PENDING_TEXT)).toBeInTheDocument()

    await advance(BRACKET_POLL_INTERVAL_MS * 2)
    expect(screen.getByText(BRACKET_PENDING_TEXT)).toBeInTheDocument()
    expect(screen.getByRole("timer")).toBeInTheDocument()
    expect(screen.queryByText(/連線中斷/)).toBeNull()

    await advance(BRACKET_POLL_INTERVAL_MS)
    expect(screen.getByText(/^連線中斷，正在重試/)).toBeInTheDocument()
    expect(screen.getByText(BRACKET_PENDING_TEXT)).toBeInTheDocument()
  })

  it("報名截止倒數歸零：重抓賽事，轉為報名截止後顯示「抽籤準備中」", async () => {
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockResolvedValueOnce({
        data: tournament({
          status: "open",
          registration_end: new Date(NOW.getTime() + 1000).toISOString(),
        }),
      } as unknown as ReadTournamentResult)
      .mockResolvedValue({
        data: tournament({ status: "closed" }),
      } as unknown as ReadTournamentResult)
    mockNotDrawn()
    renderApp("/tournaments/t-1/bracket")
    expect(await screen.findByRole("timer")).toHaveTextContent("00:01")

    await advance(1000)
    await advance(0)
    expect(read).toHaveBeenCalledTimes(2)
    expect(screen.getByText("抽籤準備中")).toBeInTheDocument()
    expect(screen.queryByRole("timer")).toBeNull()
  })
})
