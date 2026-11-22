import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRouter } from "@tanstack/react-router"
import {
  configure,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
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
  type OrganizerRegistration,
  type OrganizerRegistrationMember,
  RegistrationService,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import {
  FILTERED_EMPTY_TEXT,
  NO_REGISTRATIONS_TEXT,
  REJECT_DESCRIPTIONS,
  useRankScreenshotImage,
} from "@/features/registration/organizer-registrations"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { routeTree } from "@/routeTree.gen"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const URL_BASE = "/organizer/tournaments/t-1/registrations"
const REASON = "段位截圖與申報段位不符"

const TOURNAMENT = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "政大校園盃",
  status: "open",
  mode: "campus",
  game_name: "特戰英豪",
  capacity: 8,
  registration_start: "2026-10-01T00:00:00Z",
  // 報名截止在未來：退回對話框為可重送的內文（截止時間已過的情況另測）
  registration_end: "2099-10-10T00:00:00Z",
  priority_end: "2026-10-05T00:00:00Z",
  start_at: "2026-10-26T11:00:00Z",
  round_interval_minutes: 180,
  bo: 3,
  starters: 5,
  substitutes: 2,
  forfeit_minutes: 15,
  appeal_minutes: 30,
  livestream_url: null,
} as unknown as TournamentRead

function memberOf(
  id: string,
  name: string,
  overrides: Partial<OrganizerRegistrationMember> = {},
): OrganizerRegistrationMember {
  return {
    account_id: id,
    display_name: name,
    role: "player",
    game_account_id: `${name}#TW`,
    rank_tier: "鑽石",
    has_rank_screenshot: true,
    rank_screenshot_version: `v-${id}`,
    ...overrides,
  }
}

function registration(
  overrides: Partial<OrganizerRegistration> = {},
): OrganizerRegistration {
  return {
    registration_id: "r-1",
    team_id: "team-1",
    team_name: "夜貓隊",
    status: "accepted",
    submitted_at: "2026-10-03T10:00:00Z",
    avg_rank_score: 25.5,
    backfilled: false,
    rejectable: true,
    reject_reason: null,
    waitlist_position: null,
    waitlist_reason: null,
    representative_backfill: null,
    waitlist_phase: null,
    members: [
      memberOf("acc-1", "阿哲", { role: "captain" }),
      memberOf("acc-2", "小芸", {
        has_rank_screenshot: false,
        rank_screenshot_version: null,
      }),
    ],
    ...overrides,
  }
}

type ListResult = Awaited<
  ReturnType<typeof RegistrationService.listOrganizerRegistrations>
>
type RejectResult = Awaited<
  ReturnType<typeof RegistrationService.rejectRegistration>
>
type DownloadResult = Awaited<
  ReturnType<typeof RegistrationService.downloadRankScreenshot>
>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>

function mockList(items: OrganizerRegistration[]) {
  return vi
    .spyOn(RegistrationService, "listOrganizerRegistrations")
    .mockResolvedValue({
      data: { items, total: items.length, page: 1, page_size: 20 },
    } as ListResult)
}

function mockDownload() {
  return vi
    .spyOn(RegistrationService, "downloadRankScreenshot")
    .mockResolvedValue({
      data: new Blob(["png"], { type: "image/png" }),
    } as unknown as DownloadResult)
}

function open(
  url = URL_BASE,
  status: TournamentRead["status"] = "open",
  overrides: Partial<TournamentRead> = {},
) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: { ...TOURNAMENT, status, ...overrides },
  } as ReadResult)
  signInAs({ account: ORGANIZER })
  return renderApp(url)
}

function tableRows() {
  const table = within(
    document.querySelector("[data-slot=data-table]") as HTMLElement,
  ).getByRole("table", { name: "報名清單" })
  return within(table).getAllByRole("row").slice(1)
}

async function firstRow() {
  await screen.findByRole("table", { name: "報名清單" })
  return tableRows()[0]
}

// 路由以 autoCodeSplitting 延遲載入：先載入 S29，第一個測試才不會因冷啟動逾時
beforeAll(async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  await router.loadRouteChunk(
    router.routesByPath["/organizer/tournaments/$tournamentId/registrations"],
  )
}, 30_000)

let objectUrlCount = 0

beforeEach(() => {
  // jsdom 沒有 matchMedia；useIsMobile 只用它監聽變化，寬度看 innerWidth
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  objectUrlCount = 0
  URL.createObjectURL = vi.fn(() => {
    objectUrlCount += 1
    return `blob:rank-${objectUrlCount}`
  })
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("S29 報名清單：列表", () => {
  it("側欄「報名清單」在「總覽」之後；列出隊伍、狀態、送出時間、平均段位積分與操作", async () => {
    mockList([
      registration(),
      registration({
        registration_id: "r-2",
        team_id: "team-2",
        team_name: "晨鳥隊",
        status: "waitlisted",
        waitlist_position: 1,
        waitlist_reason: null,
        representative_backfill: true,
        waitlist_phase: "first_come",
      }),
      registration({
        registration_id: "r-3",
        team_id: "team-3",
        team_name: "午後隊",
        status: "rejected",
        rejectable: false,
        reject_reason: REASON,
      }),
    ])
    open()

    const row = await firstRow()
    const nav = screen.getAllByRole("link").map((link) => link.textContent)
    expect(nav.indexOf("報名清單")).toBe(nav.indexOf("總覽") + 1)
    expect(within(row).getByText("夜貓隊")).toBeInTheDocument()
    expect(within(row).getByText("正取")).toBeInTheDocument()
    expect(within(row).getByText("25.50")).toBeInTheDocument()
    expect(
      within(row).getByRole("button", { name: "段位截圖" }),
    ).toBeInTheDocument()
    expect(
      within(row).getByRole("button", { name: "退回報名" }),
    ).toBeInTheDocument()
    const [, waitlisted, rejected] = tableRows()
    expect(within(waitlisted).getByText("候補第 1 位")).toBeInTheDocument()
    expect(
      within(waitlisted).getByText("本校代表隊已退出，由本校遞補"),
    ).toBeInTheDocument()
    expect(within(rejected).getByText("退回")).toBeInTheDocument()
    expect(
      within(rejected).getByText(`退回原因：${REASON}`),
    ).toBeInTheDocument()
    expect(within(rejected).queryByRole("button", { name: "退回報名" })).toBe(
      null,
    )
  })

  it("沒有報名：「還沒有隊伍報名。」＋「複製賽事頁連結」", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    mockList([])
    open()

    expect(await screen.findByText(NO_REGISTRATIONS_TEXT)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "複製賽事頁連結" }))

    expect(await navigator.clipboard.readText()).toBe(
      `${window.location.origin}/tournaments/t-1`,
    )
    expect(success).toHaveBeenCalledWith("已複製", expect.anything())
  })

  it("篩選寫在網址並帶給 API；沒有符合的報名時顯示篩選的空狀態", async () => {
    const list = mockList([])
    open(`${URL_BASE}?status=accepted`)

    expect(await screen.findByText(FILTERED_EMPTY_TEXT)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "複製賽事頁連結" })).toBe(null)
    expect(list).toHaveBeenCalledWith({
      path: { tournament_id: "t-1" },
      query: { status: "accepted", page: 1 },
    })
  })

  it("非主辦方（403）：顯示無權限畫面", async () => {
    vi.spyOn(
      RegistrationService,
      "listOrganizerRegistrations",
    ).mockRejectedValue(
      httpError(403, {
        detail: { code: "TOURNAMENT_OWNER_REQUIRED", message: "沒有權限" },
      }),
    )
    open()

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
  })
})

describe("S29 報名清單：分頁", () => {
  /** 共 21 筆：第 1 頁 20 筆、第 2 頁 1 筆；超出的頁碼回空的 items（total 照實）。 */
  function mockPaged() {
    return vi
      .spyOn(RegistrationService, "listOrganizerRegistrations")
      .mockImplementation((async (options: {
        query?: { page?: number; status?: string }
      }) => {
        const pageNo = options.query?.page ?? 1
        const items =
          pageNo === 1
            ? Array.from({ length: 20 }, (_, i) =>
                registration({
                  registration_id: `r-${i}`,
                  team_id: `team-${i}`,
                  team_name: `第一頁隊${i}`,
                }),
              )
            : pageNo === 2
              ? [
                  registration({
                    registration_id: "r-last",
                    team_id: "team-last",
                    team_name: "最後一隊",
                  }),
                ]
              : []
        return {
          data: { items, total: 21, page: pageNo, page_size: 20 },
        } as ListResult
      }) as never)
  }

  it("網址頁碼超出：以 replace 導回最後一頁", async () => {
    mockPaged()
    const router = open(`${URL_BASE}?page=9`)

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ page: 2 }),
    )
    expect(await screen.findAllByText("最後一隊")).not.toHaveLength(0)
    expect(screen.queryByText(NO_REGISTRATIONS_TEXT)).toBeNull()
    // replace：歷史紀錄裡沒有留下 page=9
    expect(router.history.length).toBe(1)
  })

  it("下一頁寫入 { page: 2 }；在第 2 頁換篩選回到第 1 頁並保留 status", async () => {
    const user = userEvent.setup()
    const list = mockPaged()
    const router = open()

    await firstRow()
    expect(tableRows()).toHaveLength(20)
    await user.click(screen.getByRole("button", { name: "下一頁" }))
    await screen.findAllByText("最後一隊")
    expect(router.state.location.search).toEqual({ page: 2 })

    await user.click(screen.getByRole("combobox", { name: "狀態" }))
    await user.click(await screen.findByRole("option", { name: "正取" }))

    await waitFor(() =>
      expect(router.state.location.search).toEqual({ status: "accepted" }),
    )
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({
        path: { tournament_id: "t-1" },
        query: { status: "accepted", page: 1 },
      }),
    )
  })
})

describe("S29 段位截圖檢視器", () => {
  it("預設第一位（隊長），翻到下一位顯示「未上傳」，首末按鈕停用", async () => {
    const user = userEvent.setup()
    mockList([registration()])
    const download = mockDownload()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "段位截圖" }))
    const dialog = await screen.findByTestId("rank-screenshot-dialog")
    expect(within(dialog).getByText("夜貓隊・段位截圖")).toBeInTheDocument()
    expect(
      within(dialog).getByText("阿哲・遊戲 ID：阿哲#TW・申報段位：鑽石"),
    ).toBeInTheDocument()
    expect(await within(dialog).findByRole("img")).toHaveAttribute(
      "src",
      "blob:rank-1",
    )
    expect(download).toHaveBeenCalledWith({
      path: {
        tournament_id: "t-1",
        registration_id: "r-1",
        account_id: "acc-1",
      },
    })
    expect(within(dialog).getByText("1／2")).toBeInTheDocument()
    const previous = within(dialog).getByRole("button", { name: "上一位" })
    const next = within(dialog).getByRole("button", { name: "下一位" })
    expect(previous).toBeDisabled()
    expect(next).toBeEnabled()

    await user.click(next)

    expect(within(dialog).getByText("2／2")).toBeInTheDocument()
    expect(within(dialog).getByText("未上傳")).toBeInTheDocument()
    expect(within(dialog).queryByRole("img")).toBe(null)
    expect(
      within(dialog).getByRole("button", { name: "下一位" }),
    ).toBeDisabled()
    expect(within(dialog).getByRole("button", { name: "上一位" })).toBeEnabled()
    expect(download).toHaveBeenCalledTimes(1)
  })

  it("從檢視器按「退回報名」：先關閉檢視器再開確認對話框", async () => {
    const user = userEvent.setup()
    mockList([registration()])
    mockDownload()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "段位截圖" }))
    const dialog = await screen.findByTestId("rank-screenshot-dialog")
    await user.click(within(dialog).getByRole("button", { name: "退回報名" }))

    const confirm = await screen.findByRole("alertdialog")
    expect(confirm).toHaveAccessibleName("退回報名")
    await waitFor(() =>
      expect(screen.queryByTestId("rank-screenshot-dialog")).toBe(null),
    )
  })

  it("不可退回的報名：檢視器沒有「退回報名」", async () => {
    const user = userEvent.setup()
    mockList([registration({ status: "withdrawn", rejectable: false })])
    mockDownload()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "段位截圖" }))
    const dialog = await screen.findByTestId("rank-screenshot-dialog")
    expect(within(dialog).queryByRole("button", { name: "退回報名" })).toBe(
      null,
    )
  })
})

describe("S29 退回報名", () => {
  it("報名期間：可重送的內文，原因必填；成功後送出原因、重抓清單並 Toast", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const list = mockList([registration()])
    const reject = vi
      .spyOn(RegistrationService, "rejectRegistration")
      .mockResolvedValue({
        data: registration({ status: "rejected", rejectable: false }),
      } as RejectResult)
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "退回報名" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(dialog).toHaveAccessibleDescription(REJECT_DESCRIPTIONS.open)
    const confirm = within(dialog).getByRole("button", { name: "退回報名" })
    expect(confirm).toBeDisabled()
    const reason = within(dialog).getByLabelText("退回原因")
    expect(reason).toHaveAttribute("maxlength", "200")
    await user.type(reason, "   ")
    expect(confirm).toBeDisabled()
    await user.type(reason, REASON)
    await user.click(confirm)

    await waitFor(() =>
      expect(reject).toHaveBeenCalledWith({
        path: { tournament_id: "t-1", registration_id: "r-1" },
        body: { reason: REASON },
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBe(null))
    expect(success).toHaveBeenCalledWith("已退回報名", expect.anything())
    await waitFor(() =>
      expect(list.mock.calls.length).toBeGreaterThanOrEqual(2),
    )
  })

  it("報名截止後：不可重送的內文", async () => {
    const user = userEvent.setup()
    mockList([registration()])
    open(URL_BASE, "closed")

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "退回報名" }))
    const dialog = await screen.findByRole("alertdialog")
    await waitFor(() =>
      expect(dialog).toHaveAccessibleDescription(REJECT_DESCRIPTIONS.closed),
    )
  })

  it("截止時間已過、賽事仍為開放報名：不可重送的內文", async () => {
    const user = userEvent.setup()
    mockList([registration()])
    open(URL_BASE, "open", { registration_end: "2026-10-10T00:00:00Z" })

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "退回報名" }))
    const dialog = await screen.findByRole("alertdialog")
    await waitFor(() =>
      expect(dialog).toHaveAccessibleDescription(REJECT_DESCRIPTIONS.closed),
    )
  })

  it("被拒（409）：留在對話框顯示伺服器訊息，並重抓清單", async () => {
    const user = userEvent.setup()
    const list = mockList([registration()])
    vi.spyOn(RegistrationService, "rejectRegistration").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REGISTRATION_NOT_REJECTABLE",
          message: "這支隊伍的報名目前不能退回。",
        },
      }),
    )
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "退回報名" }))
    const dialog = await screen.findByRole("alertdialog")
    await user.type(within(dialog).getByLabelText("退回原因"), REASON)
    await user.click(within(dialog).getByRole("button", { name: "退回報名" }))

    expect(
      await within(dialog).findByText("這支隊伍的報名目前不能退回。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    await waitFor(() =>
      expect(list.mock.calls.length).toBeGreaterThanOrEqual(2),
    )
  })
})

describe("useRankScreenshotImage", () => {
  function Harness({ member }: { member: OrganizerRegistrationMember }) {
    const { url } = useRankScreenshotImage("t-1", "r-1", member)
    return <output data-testid="url">{url ?? "none"}</output>
  }

  it("換截圖（版本改變）後重新下載，不顯示舊圖", async () => {
    let resolveSecond: (value: unknown) => void = () => {}
    const second = new Promise<unknown>((resolve) => {
      resolveSecond = resolve
    }) as unknown as ReturnType<
      typeof RegistrationService.downloadRankScreenshot
    >
    const download = vi
      .spyOn(RegistrationService, "downloadRankScreenshot")
      .mockResolvedValueOnce({
        data: new Blob(["old"]),
      } as unknown as DownloadResult)
      .mockReturnValueOnce(second)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const member = memberOf("acc-1", "阿哲")
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <Harness member={member} />
      </QueryClientProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId("url")).toHaveTextContent("blob:rank-1"),
    )

    rerender(
      <QueryClientProvider client={queryClient}>
        <Harness member={{ ...member, rank_screenshot_version: "v-new" }} />
      </QueryClientProvider>,
    )

    expect(screen.getByTestId("url")).toHaveTextContent("none")
    await waitFor(() => expect(download).toHaveBeenCalledTimes(2))
    resolveSecond({ data: new Blob(["new"]) })
    await waitFor(() =>
      expect(screen.getByTestId("url")).toHaveTextContent("blob:rank-2"),
    )
  })
})
