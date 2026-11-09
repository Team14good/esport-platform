import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  configure,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  DisputesService,
  type ReportRead,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { publicBracketQueryKey } from "@/features/competition/bracket-queries"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { managedMatchesQueryOptions } from "@/features/competition/organizer-matches-queries"
import {
  openDisputesQueryOptions,
  tournamentAppealsQueryOptions,
} from "@/features/disputes/organizer-queries"
import {
  NO_OPEN_REPORTS_TEXT,
  ReportsPage,
} from "@/features/disputes/ReportsPage"
import {
  DISMISS_TEXT,
  DISQUALIFY_TEXT,
  RECORD_SUBSTANTIATED_TEXT,
  REPORT_REASON_LABEL,
} from "@/features/disputes/ResolveReportDialogs"
import { myTournamentQueryOptions } from "@/features/tournaments/organizer-queries"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
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
const REPORTS_URL = "/organizer/tournaments/t-1/reports"

const TOURNAMENT = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "ongoing",
  mode: "custom",
  game_name: "特戰英豪",
  capacity: 8,
  registration_start: "2026-10-01T00:00:00Z",
  registration_end: "2026-10-10T00:00:00Z",
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

function report(overrides: Partial<ReportRead> = {}): ReportRead {
  return {
    id: "r-1",
    tournament_id: "t-1",
    reporter_team_id: "a",
    reporter_team_name: "甲隊",
    reported_team_id: "b",
    reported_team_name: "乙隊",
    filed_by: "u-1",
    filed_at: "2026-10-26T12:10:00Z",
    description: "乙隊隊員不是本校學生。",
    has_attachment: false,
    status: "open",
    reason: null,
    handled_by: null,
    handled_at: null,
    ...overrides,
  }
}

type ListResult = Awaited<
  ReturnType<typeof DisputesService.listTournamentReports>
>
type ResolveResult = Awaited<ReturnType<typeof DisputesService.resolveReport>>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>

function mockList(reports: ReportRead[]) {
  return vi
    .spyOn(DisputesService, "listTournamentReports")
    .mockResolvedValue({ data: reports } as ListResult)
}

function mockResolve() {
  return vi
    .spyOn(DisputesService, "resolveReport")
    .mockResolvedValue({ data: report() } as ResolveResult)
}

function open(status: TournamentRead["status"] = "ongoing") {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: { ...TOURNAMENT, status },
  } as ReadResult)
  signInAs({ account: ORGANIZER })
  return renderApp(REPORTS_URL)
}

function tableRows() {
  const table = within(
    document.querySelector("[data-slot=data-table]") as HTMLElement,
  ).getByRole("table", { name: "檢舉" })
  return within(table).getAllByRole("row").slice(1)
}

async function firstRow() {
  await screen.findByRole("table", { name: "檢舉" })
  return tableRows()[0]
}

describe("S33 檢舉：列表", () => {
  it("側欄有「檢舉」；欄位、隊伍、說明、提出時間與狀態", async () => {
    mockList([report()])
    open()

    const row = await firstRow()
    expect(
      within(
        document.querySelector("[data-slot=backoffice-sidebar]") as HTMLElement,
      ).getByRole("link", { name: "檢舉" }),
    ).toHaveAttribute("href", REPORTS_URL)
    const table = screen.getByRole("table", { name: "檢舉" })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "檢舉人隊伍",
      "被檢舉隊伍",
      "說明",
      "附件",
      "提出時間",
      "狀態",
      "操作",
    ])
    const cells = within(row).getAllByRole("cell")
    expect(cells[0].textContent).toBe("甲隊")
    expect(cells[1].textContent).toBe("乙隊")
    expect(cells[2].textContent).toBe("乙隊隊員不是本校學生。")
    expect(cells[3].textContent).toBe("—")
    expect(cells[4].textContent).toBe(
      formatMatchDateTime("2026-10-26T12:10:00Z"),
    )
    expect(within(cells[5]).getByText("待處理")).toBeInTheDocument()
    expect(
      within(cells[6]).getByRole("button", { name: DISMISS_TEXT }),
    ).toBeInTheDocument()
    expect(
      within(cells[6]).getByRole("button", { name: DISQUALIFY_TEXT }),
    ).toBeInTheDocument()
  })

  it("沒有任何檢舉：空狀態", async () => {
    mockList([])
    open()

    expect(await screen.findByText(NO_OPEN_REPORTS_TEXT)).toBeInTheDocument()
  })

  it("已結案的檢舉沒有操作，顯示狀態與理由；沒有未結案時顯示空狀態文字", async () => {
    mockList([
      report({ status: "substantiated", reason: "學生證不符" }),
      report({ id: "r-2", status: "dismissed", reason: "證據不足" }),
    ])
    open()

    const row = await firstRow()
    expect(within(row).getByText("屬實")).toBeInTheDocument()
    expect(within(row).getByText("處理理由：學生證不符")).toBeInTheDocument()
    expect(within(row).queryByRole("button", { name: DISMISS_TEXT })).toBeNull()
    expect(within(tableRows()[1]).getByText("已駁回")).toBeInTheDocument()
    expect(screen.getByText(NO_OPEN_REPORTS_TEXT)).toBeInTheDocument()
  })

  it("查看附件：點擊當下開新分頁，下載檢舉附件", async () => {
    const user = userEvent.setup()
    mockList([report({ has_attachment: true })])
    const tab = {
      opener: window as Window | null,
      location: { href: "" },
      close: vi.fn(),
    }
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window)
    const download = vi
      .spyOn(DisputesService, "downloadReportAttachment")
      .mockResolvedValue({
        data: new Blob(["x"], { type: "image/png" }),
      } as unknown as Awaited<
        ReturnType<typeof DisputesService.downloadReportAttachment>
      >)
    URL.createObjectURL = vi.fn(() => "blob:attachment")
    URL.revokeObjectURL = vi.fn()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: "查看附件" }))

    expect(download).toHaveBeenCalledWith({ path: { report_id: "r-1" } })
    await waitFor(() => expect(tab.location.href).toBe("blob:attachment"))
    expect(tab.opener).toBeNull()
  })

  it("非主辦方（403）：顯示無權限畫面", async () => {
    vi.spyOn(DisputesService, "listTournamentReports").mockRejectedValue(
      httpError(403, {
        detail: { code: "TOURNAMENT_OWNER_REQUIRED", message: "不是你的賽事" },
      }),
    )
    open()

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
  })
})

describe("S33 檢舉：處理", () => {
  it("駁回檢舉：理由必填，確認鈕重複動作名，送出 substantiated=false", async () => {
    const user = userEvent.setup()
    const list = mockList([report()])
    const resolve = mockResolve()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: DISMISS_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    const confirm = within(dialog).getByRole("button", { name: DISMISS_TEXT })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText(REPORT_REASON_LABEL), "   ")
    expect(confirm).toBeDisabled()
    await user.type(
      within(dialog).getByLabelText(REPORT_REASON_LABEL),
      "證據不足",
    )
    await user.click(confirm)

    await waitFor(() =>
      expect(resolve).toHaveBeenCalledWith({
        path: { report_id: "r-1" },
        body: { substantiated: false, reason: "證據不足" },
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(list.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("取消資格：destructive，確認鈕重複動作名，送出 substantiated=true", async () => {
    const user = userEvent.setup()
    mockList([report()])
    const resolve = mockResolve()
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: DISQUALIFY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    expect(
      within(dialog).getByRole("heading", { name: "取消 乙隊 的資格" }),
    ).toBeInTheDocument()
    const confirm = within(dialog).getByRole("button", {
      name: DISQUALIFY_TEXT,
    })
    expect(confirm).toBeDisabled()
    expect(confirm.className).toContain("destructive")
    await user.type(
      within(dialog).getByLabelText(REPORT_REASON_LABEL),
      "學生證不符",
    )
    await user.click(confirm)

    await waitFor(() =>
      expect(resolve).toHaveBeenCalledWith({
        path: { report_id: "r-1" },
        body: { substantiated: true, reason: "學生證不符" },
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  it.each(["finished", "cancelled"] as const)(
    "賽事%s：「取消資格」改為「記錄屬實」",
    async (status) => {
      const user = userEvent.setup()
      mockList([report()])
      const resolve = mockResolve()
      open(status)

      const row = await firstRow()
      // 賽事狀態載入後按鈕才改為「記錄屬實」
      await within(row).findByRole("button", {
        name: RECORD_SUBSTANTIATED_TEXT,
      })
      expect(
        within(row).queryByRole("button", { name: DISQUALIFY_TEXT }),
      ).toBeNull()
      await user.click(
        within(row).getByRole("button", { name: RECORD_SUBSTANTIATED_TEXT }),
      )
      const dialog = await screen.findByRole("alertdialog")
      await user.type(
        within(dialog).getByLabelText(REPORT_REASON_LABEL),
        "查證屬實",
      )
      await user.click(
        within(dialog).getByRole("button", { name: RECORD_SUBSTANTIATED_TEXT }),
      )

      await waitFor(() =>
        expect(resolve).toHaveBeenCalledWith({
          path: { report_id: "r-1" },
          body: { substantiated: true, reason: "查證屬實" },
        }),
      )
    },
  )

  it("取消資格被拒（對手未定）：留在對話框顯示伺服器訊息", async () => {
    const user = userEvent.setup()
    mockList([report()])
    vi.spyOn(DisputesService, "resolveReport").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "DISQUALIFY_OPPONENT_PENDING",
          message: "對手尚未確定，請等對手確定後再取消資格。",
        },
      }),
    )
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: DISQUALIFY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.type(
      within(dialog).getByLabelText(REPORT_REASON_LABEL),
      "學生證不符",
    )
    await user.click(
      within(dialog).getByRole("button", { name: DISQUALIFY_TEXT }),
    )

    expect(
      await within(dialog).findByText(
        "對手尚未確定，請等對手確定後再取消資格。",
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
  })

  it("取消資格成功後重抓 S32、S27、S30 與公開對戰樹", async () => {
    const user = userEvent.setup()
    mockList([report()])
    mockResolve()
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries")
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: DISQUALIFY_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.type(
      within(dialog).getByLabelText(REPORT_REASON_LABEL),
      "學生證不符",
    )
    invalidate.mockClear()
    await user.click(
      within(dialog).getByRole("button", { name: DISQUALIFY_TEXT }),
    )

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey)
    for (const key of [
      tournamentAppealsQueryOptions("t-1").queryKey,
      openDisputesQueryOptions("t-1").queryKey,
      myTournamentQueryOptions("t-1").queryKey,
      managedMatchesQueryOptions("t-1").queryKey,
      publicBracketQueryKey("t-1"),
    ]) {
      expect(keys).toContainEqual(key)
    }
  })

  it("處理被拒：仍重抓 S33 列表", async () => {
    const user = userEvent.setup()
    const list = mockList([report()])
    vi.spyOn(DisputesService, "resolveReport").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REPORT_ALREADY_RESOLVED",
          message: "這筆檢舉已經處理過了。",
        },
      }),
    )
    open()

    const row = await firstRow()
    await user.click(within(row).getByRole("button", { name: DISMISS_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.type(
      within(dialog).getByLabelText(REPORT_REASON_LABEL),
      "證據不足",
    )
    const callsBefore = list.mock.calls.length
    await user.click(within(dialog).getByRole("button", { name: DISMISS_TEXT }))

    expect(
      await within(dialog).findByText("這筆檢舉已經處理過了。"),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(list.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it("賽事狀態未知（載入中）：屬實按鈕停用，駁回檢舉可用", async () => {
    mockList([report()])
    vi.spyOn(TournamentsService, "readMyTournament").mockImplementation(
      (() => new Promise(() => {})) as never,
    )
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ReportsPage tournamentId="t-1" />
      </QueryClientProvider>,
    )

    const row = await firstRow()
    expect(
      within(row).getByRole("button", { name: DISQUALIFY_TEXT }),
    ).toBeDisabled()
    expect(
      within(row).getByRole("button", { name: DISMISS_TEXT }),
    ).toBeEnabled()
  })
})
