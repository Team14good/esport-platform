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
  type PublicTournament,
  type TournamentStatus,
  TournamentsService,
} from "@/client"
import {
  EXPIRE_TIMEOUT_TEXT,
  EXPIRED_TEXT,
} from "@/components/common/Countdown"
import { REGISTRATION_OPENING_TEXT } from "@/features/tournaments/TournamentOverview"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

type ListResult = Awaited<
  ReturnType<typeof TournamentsService.listPublicTournaments>
>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readPublicTournament>
>

// 裝置時間：台北 2025/10/10（五）20:00
const NOW = new Date("2025-10-10T12:00:00Z")
const HOUR = 60 * 60 * 1000

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

function mockList(data: PublicTournament[]) {
  return vi
    .spyOn(TournamentsService, "listPublicTournaments")
    .mockResolvedValue({ data } as unknown as ListResult)
}

function mockRead(...responses: PublicTournament[]) {
  const spy = vi.spyOn(TournamentsService, "readPublicTournament")
  for (const data of responses.slice(0, -1)) {
    spy.mockResolvedValueOnce({ data } as unknown as ReadResult)
  }
  spy.mockResolvedValue({
    data: responses[responses.length - 1],
  } as unknown as ReadResult)
  return spy
}

function renderList(data: PublicTournament[]) {
  mockList(data)
  return renderApp("/")
}

// 路由元件是拆分後延遲載入的；先載入頁面模組，避免第一個測試在並行執行時
// 因為冷啟動轉譯超過 findBy 的 1 秒等待
beforeAll(async () => {
  await Promise.all([
    import("@/features/tournaments/TournamentList"),
    import("@/features/tournaments/TournamentPage"),
  ])
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe("S1 賽事列表", () => {
  it("沒有賽事：「目前沒有公開的賽事。」", async () => {
    renderApp("/")

    expect(await screen.findByText("目前沒有公開的賽事。")).toBeInTheDocument()
    await vi.waitFor(() => expect(document.title).toBe("賽事 · FLOW"))
  })

  it("依狀態分組：進行中 → 開放報名 → 尚未開放 → 報名截止 → 賽程已公布 → 已結束 → 已取消，空的組不顯示", async () => {
    const statuses: TournamentStatus[] = [
      "cancelled",
      "finished",
      "upcoming",
      "ongoing",
      "open",
      "closed",
    ]
    renderList(
      statuses.map((status) =>
        tournament({ id: `t-${status}`, name: `${status} 盃`, status }),
      ),
    )

    await screen.findByText("ongoing 盃")
    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.getAttribute("aria-label"))
    expect(headings).toEqual([
      "進行中（1 場）",
      "開放報名（1 場）",
      "尚未開放（1 場）",
      "報名截止（1 場）",
      "已結束（1 場）",
      "已取消（1 場）",
    ])
    expect(
      screen.getByRole("heading", { level: 2, name: "進行中（1 場）" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "賽程已公布" })).toBeNull()
  })

  it("組內依開賽時間由近到遠；已結束、已取消由新到舊", async () => {
    renderList([
      tournament({ id: "o-late", name: "晚開盃", start_at: at(72 * HOUR) }),
      tournament({ id: "o-soon", name: "早開盃", start_at: at(24 * HOUR) }),
      tournament({
        id: "f-old",
        name: "舊的結束盃",
        status: "finished",
        start_at: at(-72 * HOUR),
      }),
      tournament({
        id: "f-new",
        name: "新的結束盃",
        status: "finished",
        start_at: at(-24 * HOUR),
      }),
    ])

    const open = await screen.findByRole("region", { name: "開放報名" })
    expect(
      within(open)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["早開盃", "晚開盃"])
    const finished = screen.getByRole("region", { name: "已結束" })
    expect(
      within(finished)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["新的結束盃", "舊的結束盃"])
  })

  it("每筆顯示遊戲、名額、報名期間、開賽時間、狀態；整張連到 S2", async () => {
    renderList([tournament()])

    const link = await screen.findByRole("link", { name: /期中盃/ })
    expect(link).toHaveAttribute("href", "/tournaments/t-1")
    expect(link).toHaveTextContent("開放報名")
    expect(link).toHaveTextContent("特戰英豪")
    expect(link).toHaveTextContent("16 隊")
    expect(link).toHaveTextContent("10/12（日）19:00 ～ 10/17（五）19:00")
    expect(link).toHaveTextContent("10/18（六）19:00")
    expect(link).not.toHaveTextContent("報名開始")
  })

  it("尚未開放另顯示報名開始時間；已取消標示「已取消」", async () => {
    renderList([
      tournament({ id: "t-up", name: "未開盃", status: "upcoming" }),
      tournament({ id: "t-x", name: "取消盃", status: "cancelled" }),
    ])

    const upcoming = await screen.findByRole("link", { name: /未開盃/ })
    expect(upcoming).toHaveTextContent("報名開始10/12（日）19:00")
    const cancelled = screen.getByRole("link", { name: /取消盃/ })
    expect(cancelled).toHaveTextContent("已取消")
  })

  it("API 失敗：顯示錯誤，按「重新載入」重抓", async () => {
    const user = userEvent.setup()
    const list = vi
      .spyOn(TournamentsService, "listPublicTournaments")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({ data: [] } as unknown as ListResult)
    renderApp("/")

    await user.click(await screen.findByRole("button", { name: "重新載入" }))

    expect(await screen.findByText("目前沒有公開的賽事。")).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})

describe("S2 賽事頁", () => {
  it("標題列、總覽分頁與賽事資訊；未登入也能看", async () => {
    mockRead(tournament({ status: "published" }))
    renderApp("/tournaments/t-1")

    expect(
      await screen.findByRole("heading", { level: 1, name: "期中盃" }),
    ).toBeInTheDocument()
    await vi.waitFor(() => expect(document.title).toBe("期中盃 · FLOW"))
    expect(screen.getByRole("tab", { name: "總覽" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    const panel = screen.getByRole("tabpanel")
    expect(panel).toHaveTextContent("賽程已公布")
    expect(panel).toHaveTextContent("特戰英豪")
    expect(panel).toHaveTextContent("16 隊")
    expect(panel).toHaveTextContent("10/12（日）19:00 ～ 10/17（五）19:00")
    expect(panel).toHaveTextContent("10/18（六）19:00")
    expect(panel).toHaveTextContent("3 小時")
    expect(screen.queryByRole("link", { name: /觀看直播/ })).toBeNull()
    expect(screen.queryByRole("timer")).toBeNull()
  })

  it("有直播連結：「觀看直播」另開分頁", async () => {
    mockRead(tournament({ livestream_url: "https://twitch.tv/flow" }))
    renderApp("/tournaments/t-1")

    const live = await screen.findByRole("link", { name: /觀看直播/ })
    expect(live).toHaveAttribute("href", "https://twitch.tv/flow")
    expect(live).toHaveAttribute("target", "_blank")
    expect(live).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("尚未開放、未登入：報名開始倒數（muted），沒有「建立隊伍」", async () => {
    mockRead(tournament({ status: "upcoming" }))
    renderApp("/tournaments/t-1")

    const timer = await screen.findByRole("timer")
    expect(timer).toHaveTextContent("剩 1 天 23 小時")
    expect(timer.closest("[data-slot=countdown]")).toHaveAttribute(
      "data-variant",
      "muted",
    )
    expect(screen.getByText("報名開始")).toBeInTheDocument()
    // 報名開始倒數下方寫「開放報名」，不是「截止」
    expect(screen.getByText("10/12（日）19:00 開放報名")).toBeInTheDocument()
    expect(screen.queryByText("10/12（日）19:00 截止")).toBeNull()
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("尚未開放、已登入：「建立隊伍」停用並寫開放報名時間", async () => {
    signInAs()
    mockRead(tournament({ status: "upcoming" }))
    renderApp("/tournaments/t-1")

    const button = await screen.findByRole("button", { name: "建立隊伍" })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription("10/12（日）19:00 開放報名")
  })

  it("開放報名、超過 24 小時：報名截止倒數為 muted", async () => {
    mockRead(tournament({ registration_end: at(50 * HOUR) }))
    renderApp("/tournaments/t-1")

    const timer = await screen.findByRole("timer")
    expect(timer).toHaveTextContent("剩 2 天 2 小時")
    expect(timer.closest("[data-slot=countdown]")).toHaveAttribute(
      "data-variant",
      "muted",
    )
    expect(screen.getByText("報名截止")).toBeInTheDocument()
  })

  it("開放報名最後 24 小時：「剩 5 小時 0 分」，appeal 變體", async () => {
    mockRead(tournament({ registration_end: at(5 * HOUR) }))
    renderApp("/tournaments/t-1")

    const timer = await screen.findByRole("timer")
    expect(timer).toHaveTextContent("剩 5 小時 0 分")
    expect(timer.closest("[data-slot=countdown]")).toHaveAttribute(
      "data-variant",
      "appeal",
    )
    // 「建立隊伍」的啟用按鈕由 3.1 接上
    expect(screen.queryByRole("button", { name: "建立隊伍" })).toBeNull()
  })

  it("報名截止：「抽籤準備中」", async () => {
    mockRead(tournament({ status: "closed" }))
    renderApp("/tournaments/t-1")

    expect(await screen.findByText("抽籤準備中")).toBeInTheDocument()
    expect(screen.queryByRole("timer")).toBeNull()
  })

  it("已取消：destructive banner「此賽事已取消」，不顯示倒數", async () => {
    mockRead(tournament({ status: "cancelled" }))
    renderApp("/tournaments/t-1")

    const banner = await screen.findByRole("alert")
    expect(banner).toHaveTextContent("此賽事已取消")
    expect(screen.getAllByRole("alert")).toHaveLength(1)
    expect(screen.queryByRole("timer")).toBeNull()
  })

  it("離開 S2 回到 S1：分頁標題還原成「賽事 · FLOW」", async () => {
    mockRead(tournament())
    const router = renderApp("/tournaments/t-1")
    await vi.waitFor(() => expect(document.title).toBe("期中盃 · FLOW"))

    await act(() => router.navigate({ to: "/" }))

    expect(await screen.findByText("目前沒有公開的賽事。")).toBeInTheDocument()
    await vi.waitFor(() => expect(document.title).toBe("賽事 · FLOW"))
  })

  it("不存在的賽事：404 頁", async () => {
    vi.spyOn(TournamentsService, "readPublicTournament").mockRejectedValue(
      httpError(404, {
        detail: { code: "TOURNAMENT_NOT_FOUND", message: "找不到這場賽事。" },
      }),
    )
    renderApp("/tournaments/no-such")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
  })

  it("id 格式錯誤（422）：404 頁，不重試", async () => {
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockRejectedValue(httpError(422, { detail: [] }))
    renderApp("/tournaments/not-a-uuid")

    expect(
      await screen.findByRole("heading", { name: "找不到這個頁面。" }),
    ).toBeInTheDocument()
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("首次載入 500：重試後顯示錯誤，按「重新載入」重抓", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] })
    vi.setSystemTime(NOW)
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockRejectedValueOnce(httpError(500, "Internal Server Error"))
      .mockResolvedValue({
        data: tournament({ status: "published" }),
      } as unknown as ReadResult)
    renderApp("/tournaments/t-1")

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
    expect(read).toHaveBeenCalledTimes(5)
  })

  it("倒數歸零後重抓失敗：保留畫面上的賽事，不重試", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    vi.setSystemTime(NOW)
    const read = vi
      .spyOn(TournamentsService, "readPublicTournament")
      .mockResolvedValueOnce({
        data: tournament({ status: "upcoming", registration_start: at(1000) }),
      } as unknown as ReadResult)
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderApp("/tournaments/t-1")
    expect(await screen.findByRole("timer")).toHaveTextContent("00:01")

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(
      await screen.findByText(REGISTRATION_OPENING_TEXT),
    ).toBeInTheDocument()
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2))

    act(() => {
      vi.advanceTimersByTime(5000)
    })
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(3))

    // 每次重抓失敗只抓一次（不重試），畫面仍是原本的賽事
    expect(
      screen.getByRole("heading", { level: 1, name: "期中盃" }),
    ).toBeInTheDocument()
    expect(screen.getByText(REGISTRATION_OPENING_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "重新載入" })).toBeNull()
  })

  it("倒數歸零 2 分鐘狀態仍未改變：顯示逾時提示並停止重抓", async () => {
    vi.useFakeTimers({
      toFake: [
        "Date",
        "setInterval",
        "clearInterval",
        "setTimeout",
        "clearTimeout",
      ],
    })
    vi.setSystemTime(NOW)
    const read = mockRead(
      tournament({ status: "upcoming", registration_start: at(1000) }),
    )
    renderApp("/tournaments/t-1")
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByRole("timer")).toHaveTextContent("00:01")

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.getByText(REGISTRATION_OPENING_TEXT)).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2 * 60 * 1000)
    })

    expect(screen.getByText(EXPIRE_TIMEOUT_TEXT)).toBeInTheDocument()
    expect(screen.queryByText(REGISTRATION_OPENING_TEXT)).toBeNull()
    const calls = read.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60 * 1000)
    })
    expect(read).toHaveBeenCalledTimes(calls)
  })

  it("倒數歸零：顯示「已截止 · 系統處理中」並重抓，狀態改變後換成新狀態的畫面", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    vi.setSystemTime(NOW)
    const read = mockRead(
      tournament({ status: "upcoming", registration_start: at(2000) }),
      tournament({ status: "upcoming", registration_start: at(2000) }),
      tournament({ status: "open", registration_start: at(2000) }),
    )
    renderApp("/tournaments/t-1")
    expect(await screen.findByRole("timer")).toHaveTextContent("00:02")

    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(
      await screen.findByText(REGISTRATION_OPENING_TEXT),
    ).toBeInTheDocument()
    // 報名開始倒數歸零不是「已截止」
    expect(screen.queryByText(EXPIRED_TEXT)).toBeNull()
    // 歸零時立即重抓一次（仍是尚未開放），5 秒後再抓一次（已開放報名）
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2))

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(await screen.findByText("報名截止")).toBeInTheDocument()
    expect(screen.getByRole("timer")).toHaveTextContent("剩 6 天 22 小時")
    expect(read).toHaveBeenCalledTimes(3)
  })
})
