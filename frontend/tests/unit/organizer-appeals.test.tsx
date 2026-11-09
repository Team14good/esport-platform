import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  configure,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  type AppealGroup,
  type AppealItem,
  DisputesService,
  type OpenDisputes,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { AppealResultBadge } from "@/features/disputes/AppealResultBadge"
import {
  NO_OPEN_APPEALS_TEXT,
  POPUP_BLOCKED_TEXT,
} from "@/features/disputes/AppealsPage"
import {
  CORRECT_TEXT,
  GO_TO_MATCHES_TEXT,
  NO_VALID_TIME_TEXT,
  REASON_LABEL,
  REMATCH_TEXT,
  REPLAY_BLOCKED_TEXT,
  UPHOLD_TEXT,
} from "@/features/disputes/ResolveAppealDialogs"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"
import { matchDetail } from "./match-detail-fixture"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const APPEALS_URL = "/organizer/tournaments/t-1/appeals"

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

function appeal(overrides: Partial<AppealItem> = {}): AppealItem {
  return {
    id: "ap-1",
    tournament_id: "t-1",
    match_id: "m-1",
    team_id: "a",
    team_name: "甲隊",
    filed_by: "u-1",
    filed_at: "2026-10-26T12:10:00Z",
    description: "第二局對方使用了禁用角色。",
    has_attachment: false,
    status: "open",
    decision: null,
    reason: null,
    handled_by: null,
    handled_at: null,
    ...overrides,
  }
}

function group(overrides: Partial<AppealGroup> = {}): AppealGroup {
  return {
    match_id: "m-1",
    match_code: "M1",
    round_name: "8 強",
    is_third_place: false,
    scheduled_at: "2026-10-26T11:00:00Z",
    match_status: "appealed",
    outcome: "played",
    winner_id: "a",
    wins_a: 2,
    wins_b: 0,
    score_type: "win_loss",
    best_of: 3,
    games: [
      { game_no: 1, winner_side: "a", score_a: null, score_b: null },
      { game_no: 2, winner_side: "a", score_a: null, score_b: null },
    ],
    team_a: { id: "a", name: "甲隊" },
    team_b: { id: "b", name: "乙隊" },
    has_open: true,
    appeals: [
      appeal(),
      appeal({
        id: "ap-2",
        team_id: "b",
        team_name: "乙隊",
        filed_at: "2026-10-26T12:15:00Z",
        has_attachment: true,
      }),
    ],
    ...overrides,
  }
}

const PLAYED = group()
const FORFEIT = group({
  match_id: "m-2",
  match_code: "M2",
  outcome: "forfeit",
  games: [],
  wins_a: 0,
  appeals: [appeal({ id: "ap-3", match_id: "m-2", team_name: "丙隊" })],
  team_a: { id: "c", name: "丙隊" },
  team_b: { id: "d", name: "丁隊" },
})

const DOUBLE_FORFEIT = group({
  match_id: "m-3",
  match_code: "M3",
  outcome: "double_forfeit",
  winner_id: null,
  games: [],
  wins_a: 0,
  appeals: [appeal({ id: "ap-4", match_id: "m-3" })],
})

const HANDLED_ELSEWHERE = group({
  has_open: false,
  match_status: "confirmed",
  appeals: [
    appeal({
      status: "closed",
      decision: "upheld",
      reason: "另一個分頁處理",
      handled_at: "2026-10-26T12:30:00Z",
    }),
  ],
})

type ListResult = Awaited<
  ReturnType<typeof DisputesService.listTournamentAppeals>
>
type ResolveResult = Awaited<ReturnType<typeof DisputesService.resolveAppeals>>
type WindowResult = Awaited<ReturnType<typeof DisputesService.readReplayWindow>>
type OpenResult = Awaited<ReturnType<typeof DisputesService.readOpenDisputes>>
type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>
type AppealResult = Awaited<ReturnType<typeof DisputesService.readAppealResult>>

function mockList(groups: AppealGroup[]) {
  return vi
    .spyOn(DisputesService, "listTournamentAppeals")
    .mockResolvedValue({ data: groups } as ListResult)
}

function mockResolve() {
  return vi
    .spyOn(DisputesService, "resolveAppeals")
    .mockResolvedValue({ data: [] } as unknown as ResolveResult)
}

function open(url = APPEALS_URL) {
  vi.spyOn(TournamentsService, "readMyTournament").mockResolvedValue({
    data: TOURNAMENT,
  } as ReadResult)
  signInAs({ account: ORGANIZER })
  return renderApp(url)
}

function tableRows() {
  const table = within(
    document.querySelector("[data-slot=data-table]") as HTMLElement,
  ).getByRole("table", { name: "申訴" })
  return within(table).getAllByRole("row").slice(1)
}

async function rowOf(code: string) {
  await screen.findByRole("table", { name: "申訴" })
  const row = tableRows().find((r) =>
    within(r).getAllByRole("cell")[0].textContent?.startsWith(code),
  )
  if (!row) throw new Error(`找不到 ${code} 那一列`)
  return row
}

describe("S32 申訴：列表", () => {
  it("側欄有「申訴」；欄位、隊伍與提出時間、狀態", async () => {
    mockList([PLAYED, FORFEIT])
    open()

    const row = await rowOf("M1")
    expect(
      within(
        document.querySelector("[data-slot=backoffice-sidebar]") as HTMLElement,
      ).getByRole("link", { name: "申訴" }),
    ).toHaveAttribute("href", APPEALS_URL)
    const table = within(
      document.querySelector("[data-slot=data-table]") as HTMLElement,
    ).getByRole("table", { name: "申訴" })
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "場次",
      "提出隊伍",
      "提出時間",
      "狀態與決定",
      "說明與附件",
      "操作",
    ])
    const cells = within(row).getAllByRole("cell")
    expect(cells[1].textContent).toBe("甲隊乙隊")
    expect(
      within(cells[2]).getByText(formatMatchDateTime("2026-10-26T12:15:00Z")),
    ).toBeInTheDocument()
    expect(within(cells[3]).getByText("待處理")).toBeInTheDocument()
  })

  it("「重新比賽」只出現在棄權的場次；「更正結果」只出現在正常完賽的場次", async () => {
    mockList([PLAYED, FORFEIT])
    open()

    const played = await rowOf("M1")
    expect(
      within(played).getByRole("button", { name: UPHOLD_TEXT }),
    ).toBeInTheDocument()
    expect(
      within(played).getByRole("button", { name: CORRECT_TEXT }),
    ).toBeInTheDocument()
    expect(
      within(played).queryByRole("button", { name: REMATCH_TEXT }),
    ).toBeNull()

    const forfeit = await rowOf("M2")
    expect(
      within(forfeit).getByRole("button", { name: REMATCH_TEXT }),
    ).toBeInTheDocument()
    expect(
      within(forfeit).queryByRole("button", { name: CORRECT_TEXT }),
    ).toBeNull()
  })

  it("重新比賽後再申訴：列中只列本輪未結案的申訴，不混入上一輪已結案的", async () => {
    mockList([
      group({
        appeals: [
          appeal({
            id: "ap-old",
            team_id: "b",
            team_name: "乙隊",
            filed_at: "2026-10-26T12:10:00Z",
            status: "closed",
            decision: "rematch",
            reason: "重賽",
            handled_at: "2026-10-26T12:30:00Z",
          }),
          appeal({
            id: "ap-new",
            team_id: "b",
            team_name: "乙隊",
            filed_at: "2026-10-27T12:10:00Z",
          }),
        ],
      }),
    ])
    open()

    const cells = within(await rowOf("M1")).getAllByRole("cell")
    expect(cells[1].textContent).toBe("乙隊")
    expect(cells[2].textContent).toBe(
      formatMatchDateTime("2026-10-27T12:10:00Z"),
    )
  })

  it("雙方棄權的場次：有「重新比賽」，沒有「更正結果」", async () => {
    mockList([DOUBLE_FORFEIT])
    open()

    const row = await rowOf("M3")
    expect(
      within(row).getByRole("button", { name: REMATCH_TEXT }),
    ).toBeInTheDocument()
    expect(within(row).queryByRole("button", { name: CORRECT_TEXT })).toBeNull()
  })

  it.each([
    ["重新比賽後提出的申訴較晚處理", true],
    ["較晚處理的申訴排在前面", false],
  ])(
    "兩輪處理：狀態顯示最後一次處理的決定，與 S4 一致（%s）",
    async (_label, rematchFirst) => {
      const rematch = appeal({
        id: "ap-r",
        team_id: "b",
        team_name: "乙隊",
        status: "closed",
        decision: "rematch",
        reason: "重賽",
        handled_at: "2026-10-26T12:30:00Z",
      })
      const upheld = appeal({
        id: "ap-u",
        status: "closed",
        decision: "upheld",
        reason: "維持",
        handled_at: "2026-10-27T12:30:00Z",
      })
      mockList([
        group({
          has_open: false,
          match_status: "confirmed",
          appeals: rematchFirst ? [rematch, upheld] : [upheld, rematch],
        }),
      ])
      open()

      const row = await rowOf("M1")
      const status = within(row).getAllByRole("cell")[3]
      expect(status.textContent).toBe("維持原結果")
    },
  )

  it("已結案的場次沒有操作，顯示決定；沒有未結案申訴時顯示空狀態文字", async () => {
    mockList([
      group({
        has_open: false,
        match_status: "confirmed",
        appeals: [
          appeal({
            status: "closed",
            decision: "corrected",
            reason: "登錄錯誤",
          }),
        ],
      }),
    ])
    open()

    const row = await rowOf("M1")
    expect(within(row).getByText("更正結果")).toBeInTheDocument()
    expect(within(row).queryByRole("button", { name: UPHOLD_TEXT })).toBeNull()
    expect(screen.getByText(NO_OPEN_APPEALS_TEXT)).toBeInTheDocument()
  })

  it("沒有任何申訴：空狀態", async () => {
    mockList([])
    open()

    expect(await screen.findByText(NO_OPEN_APPEALS_TEXT)).toBeInTheDocument()
  })

  it("查看說明：列出每筆申訴，有附件時可查看附件", async () => {
    const user = userEvent.setup()
    mockList([PLAYED])
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "查看說明" }))
    const dialog = await screen.findByRole("dialog")
    expect(
      within(dialog).getAllByText("第二局對方使用了禁用角色。"),
    ).toHaveLength(2)
    expect(
      within(dialog).getAllByRole("button", { name: "查看附件" }),
    ).toHaveLength(1)
  })

  it("查看附件：點擊當下就開新分頁（避免被擋），下載完成後導到附件", async () => {
    const user = userEvent.setup()
    mockList([PLAYED])
    const tab = {
      opener: window as Window | null,
      location: { href: "" },
      close: vi.fn(),
    }
    const windowOpen = vi
      .spyOn(window, "open")
      .mockReturnValue(tab as unknown as Window)
    let finishDownload: (blob: Blob) => void = () => {}
    const download = vi
      .spyOn(DisputesService, "downloadAppealAttachment")
      .mockImplementation(
        (() =>
          new Promise((resolve) => {
            finishDownload = (blob) => resolve({ data: blob })
          })) as unknown as typeof DisputesService.downloadAppealAttachment,
      )
    URL.createObjectURL = vi.fn(() => "blob:attachment")
    URL.revokeObjectURL = vi.fn()
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "查看說明" }))
    const dialog = await screen.findByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "查看附件" }))

    // 下載還沒完成，分頁已經開了
    expect(windowOpen).toHaveBeenCalledTimes(1)
    expect(windowOpen.mock.calls[0][0]).toBe("")
    expect(tab.opener).toBeNull()
    expect(download).toHaveBeenCalledWith({ path: { appeal_id: "ap-2" } })
    expect(tab.location.href).toBe("")

    finishDownload(new Blob(["x"], { type: "image/png" }))
    await waitFor(() => expect(tab.location.href).toBe("blob:attachment"))
    expect(tab.close).not.toHaveBeenCalled()
  })

  async function clickViewAttachment() {
    const user = userEvent.setup()
    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: "查看說明" }))
    const dialog = await screen.findByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "查看附件" }))
  }

  it("查看附件：瀏覽器擋下新分頁（window.open 回 null）時顯示提示，不下載", async () => {
    mockList([PLAYED])
    vi.spyOn(window, "open").mockReturnValue(null)
    const download = vi.spyOn(DisputesService, "downloadAppealAttachment")
    const toastError = vi.spyOn(toast, "error")
    open()

    await clickViewAttachment()

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        POPUP_BLOCKED_TEXT,
        expect.anything(),
      ),
    )
    expect(download).not.toHaveBeenCalled()
  })

  it("查看附件：下載失敗時關閉剛開的分頁並顯示錯誤", async () => {
    mockList([PLAYED])
    const tab = {
      opener: window as Window | null,
      location: { href: "" },
      close: vi.fn(),
    }
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window)
    vi.spyOn(DisputesService, "downloadAppealAttachment").mockRejectedValue(
      httpError(404, {
        detail: { code: "FILE_NOT_FOUND", message: "找不到這個檔案" },
      }),
    )
    const toastError = vi.spyOn(toast, "error")
    open()

    await clickViewAttachment()

    await waitFor(() => expect(tab.close).toHaveBeenCalled())
    expect(toastError).toHaveBeenCalledWith("找不到這個檔案", expect.anything())
    expect(tab.location.href).toBe("")
  })

  it("非主辦方（403）：顯示無權限畫面", async () => {
    vi.spyOn(DisputesService, "listTournamentAppeals").mockRejectedValue(
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

describe("S32 申訴：處理", () => {
  it("維持原結果：理由必填，確認鈕重複動作名，送出決定與理由", async () => {
    const user = userEvent.setup()
    const list = mockList([PLAYED])
    const resolve = mockResolve()
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: UPHOLD_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    const confirm = within(dialog).getByRole("button", { name: UPHOLD_TEXT })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "   ")
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "證據不足")
    expect(confirm).toBeEnabled()
    const readTournament = vi.mocked(TournamentsService.readMyTournament)
    const tournamentReads = readTournament.mock.calls.length
    await user.click(confirm)

    await waitFor(() =>
      expect(resolve).toHaveBeenCalledWith({
        path: { tournament_id: "t-1", match_id: "m-1" },
        body: { decision: "upheld", reason: "證據不足" },
      }),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(list.mock.calls.length).toBeGreaterThanOrEqual(2)
    // 決賽處理後賽事會轉為已結束：主辦方賽事詳情也要重抓
    await waitFor(() =>
      expect(readTournament.mock.calls.length).toBeGreaterThan(tournamentReads),
    )
  })

  it("雙方棄權：確認文字寫雙方都不晉級，不寫勝隊晉級", async () => {
    const user = userEvent.setup()
    mockList([DOUBLE_FORFEIT])
    open()

    const row = await rowOf("M3")
    await user.click(within(row).getByRole("button", { name: UPHOLD_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    expect(dialog.textContent).toContain("雙方都不晉級")
    expect(dialog.textContent).not.toContain("勝隊晉級")
  })

  it("更正結果、重新比賽：填理由前確認鈕停用", async () => {
    const user = userEvent.setup()
    mockList([PLAYED, FORFEIT])
    vi.spyOn(DisputesService, "readReplayWindow").mockResolvedValue({
      data: {
        can_reschedule: true,
        reason: null,
        earliest: "2026-10-26T12:00:00Z",
        latest: null,
      },
    } as WindowResult)
    open()

    await user.click(
      within(await rowOf("M1")).getByRole("button", { name: CORRECT_TEXT }),
    )
    const correct = await screen.findByRole("alertdialog")
    // 各局已預填完整，只差理由
    const correctConfirm = within(correct).getByRole("button", {
      name: CORRECT_TEXT,
    })
    expect(correctConfirm).toBeDisabled()
    await user.type(within(correct).getByLabelText(REASON_LABEL), "  ")
    expect(correctConfirm).toBeDisabled()
    await user.type(within(correct).getByLabelText(REASON_LABEL), "更正")
    expect(correctConfirm).toBeEnabled()
    await user.click(within(correct).getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())

    await user.click(
      within(await rowOf("M2")).getByRole("button", { name: REMATCH_TEXT }),
    )
    const rematch = await screen.findByRole("alertdialog")
    fireEvent.change(
      await within(rematch).findByLabelText("重新比賽的時間（台北時間）"),
      { target: { value: "2026-10-26T21:00" } },
    )
    const rematchConfirm = within(rematch).getByRole("button", {
      name: REMATCH_TEXT,
    })
    expect(rematchConfirm).toBeDisabled()
    await user.type(within(rematch).getByLabelText(REASON_LABEL), "重賽")
    expect(rematchConfirm).toBeEnabled()
  })

  it("另一個分頁已處理（409 NO_OPEN_APPEALS）：錯誤 Toast 顯示伺服器訊息，列表重抓後顯示最新狀態", async () => {
    const user = userEvent.setup()
    const message = "這場比賽沒有待處理的申訴。"
    const list = mockList([PLAYED])
    vi.spyOn(DisputesService, "resolveAppeals").mockImplementation((() => {
      // 另一個分頁已維持原結果：之後重抓的列表沒有未結案申訴
      list.mockResolvedValue({ data: [HANDLED_ELSEWHERE] } as ListResult)
      return Promise.reject(
        httpError(409, { detail: { code: "NO_OPEN_APPEALS", message } }),
      )
    }) as unknown as typeof DisputesService.resolveAppeals)
    const toastError = vi.spyOn(toast, "error")
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: UPHOLD_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "維持")
    await user.click(within(dialog).getByRole("button", { name: UPHOLD_TEXT }))

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(message, expect.anything()),
    )
    // 列表重抓後這一列沒有操作，對話框跟著關閉
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    const updated = await rowOf("M1")
    expect(within(updated).getByText("維持原結果")).toBeInTheDocument()
    expect(
      within(updated).queryByRole("button", { name: UPHOLD_TEXT }),
    ).toBeNull()
  })

  it.each([
    ["正常完賽", PLAYED, "M1", "目前結果：甲隊 2：0 乙隊，甲隊 勝。"],
    [
      "一方棄權",
      { ...FORFEIT, winner_id: "c" },
      "M2",
      "目前結果：丁隊 棄權，丙隊 勝。",
    ],
    [
      "雙方棄權",
      { ...FORFEIT, outcome: "double_forfeit", winner_id: null },
      "M2",
      "目前結果：雙方棄權。",
    ],
  ] as const)(
    "處理前在對話框看到目前結果（%s）",
    async (_label, fixture, code, text) => {
      const user = userEvent.setup()
      mockList([fixture as AppealGroup])
      open()

      const row = await rowOf(code)
      await user.click(within(row).getByRole("button", { name: UPHOLD_TEXT }))
      const dialog = await screen.findByRole("alertdialog")
      expect(within(dialog).getByText(text)).toBeInTheDocument()
    },
  )

  it("更正結果、重新比賽的對話框也列出目前結果", async () => {
    const user = userEvent.setup()
    mockList([PLAYED, { ...FORFEIT, winner_id: "c" }])
    vi.spyOn(DisputesService, "readReplayWindow").mockResolvedValue({
      data: {
        can_reschedule: true,
        reason: null,
        earliest: "2026-10-26T12:00:00Z",
        latest: null,
      },
    } as WindowResult)
    open()

    await user.click(
      within(await rowOf("M1")).getByRole("button", { name: CORRECT_TEXT }),
    )
    const correct = await screen.findByRole("alertdialog")
    expect(
      within(correct).getByText("目前結果：甲隊 2：0 乙隊，甲隊 勝。"),
    ).toBeInTheDocument()
    await user.click(within(correct).getByRole("button", { name: "取消" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())

    await user.click(
      within(await rowOf("M2")).getByRole("button", { name: REMATCH_TEXT }),
    )
    const rematch = await screen.findByRole("alertdialog")
    expect(
      within(rematch).getByText("目前結果：丁隊 棄權，丙隊 勝。"),
    ).toBeInTheDocument()
  })

  it("更正結果：預填目前各局，依勝負型態改成整組新的各局", async () => {
    const user = userEvent.setup()
    mockList([PLAYED])
    const resolve = mockResolve()
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: CORRECT_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    expect(
      within(dialog).getByRole("button", { name: "第 1 局 甲隊 勝" }),
    ).toHaveAttribute("aria-pressed", "true")
    await user.click(
      within(dialog).getByRole("button", { name: "第 2 局 乙隊 勝" }),
    )
    await user.click(within(dialog).getByRole("button", { name: "新增一局" }))
    const confirm = within(dialog).getByRole("button", { name: CORRECT_TEXT })
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "比分登錄錯誤")
    // 第 3 局還沒選勝方：不能送出
    expect(confirm).toBeDisabled()
    await user.click(
      within(dialog).getByRole("button", { name: "第 3 局 乙隊 勝" }),
    )
    expect(
      within(dialog).getByRole("button", { name: "新增一局" }),
    ).toBeDisabled()
    await user.click(confirm)

    await waitFor(() =>
      expect(resolve).toHaveBeenCalledWith({
        path: { tournament_id: "t-1", match_id: "m-1" },
        body: {
          decision: "corrected",
          reason: "比分登錄錯誤",
          games: [
            { winner_side: "a" },
            { winner_side: "b" },
            { winner_side: "b" },
          ],
        },
      }),
    )
  })

  it("更正結果被拒（未分勝負）：留在對話框顯示伺服器訊息", async () => {
    const user = userEvent.setup()
    mockList([PLAYED])
    vi.spyOn(DisputesService, "resolveAppeals").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "SERIES_NOT_DECIDED",
          message: "任一隊拿到 2 勝後才能送出。",
        },
      }),
    )
    const toastError = vi.spyOn(toast, "error")
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: CORRECT_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    await user.click(
      within(dialog).getByRole("button", { name: "刪除最後一局" }),
    )
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "更正")
    await user.click(within(dialog).getByRole("button", { name: CORRECT_TEXT }))

    expect(
      await within(dialog).findByText("任一隊拿到 2 勝後才能送出。"),
    ).toBeInTheDocument()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    // 只有 NO_OPEN_APPEALS 另外用 Toast；其他錯誤只在對話框顯示，不重複
    expect(toastError).not.toHaveBeenCalled()
  })

  it("更正結果（回合數型態）：輸入兩隊回合數", async () => {
    const user = userEvent.setup()
    mockList([
      group({
        score_type: "rounds",
        games: [
          { game_no: 1, winner_side: "a", score_a: 13, score_b: 5 },
          { game_no: 2, winner_side: "a", score_a: 13, score_b: 7 },
        ],
      }),
    ])
    const resolve = mockResolve()
    open()

    const row = await rowOf("M1")
    await user.click(within(row).getByRole("button", { name: CORRECT_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    const second = within(dialog).getByLabelText("第 2 局 甲隊 回合數")
    expect(second).toHaveValue(13)
    await user.clear(second)
    await user.type(second, "11")
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "更正")
    await user.click(within(dialog).getByRole("button", { name: CORRECT_TEXT }))

    await waitFor(() => expect(resolve).toHaveBeenCalled())
    expect(resolve.mock.calls[0][0].body.games).toEqual([
      { score_a: 13, score_b: 5 },
      { score_a: 11, score_b: 7 },
    ])
  })

  it("重新比賽：在允許範圍內選時間，送出 UTC 時間", async () => {
    const user = userEvent.setup()
    mockList([FORFEIT])
    const resolve = mockResolve()
    vi.spyOn(DisputesService, "readReplayWindow").mockResolvedValue({
      data: {
        can_reschedule: true,
        reason: null,
        earliest: "2026-10-26T12:00:00Z",
        latest: "2026-10-26T14:00:00Z",
      },
    } as WindowResult)
    open()

    const row = await rowOf("M2")
    await user.click(within(row).getByRole("button", { name: REMATCH_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    const input = await within(dialog).findByLabelText(
      "重新比賽的時間（台北時間）",
    )
    expect(input).toHaveAttribute("min", "2026-10-26T20:00")
    expect(input).toHaveAttribute("max", "2026-10-26T22:00")
    const confirm = within(dialog).getByRole("button", { name: REMATCH_TEXT })
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "重新比賽")
    expect(confirm).toBeDisabled()
    fireEvent.change(input, { target: { value: "2026-10-26T21:00" } })
    await user.click(confirm)

    await waitFor(() =>
      expect(resolve).toHaveBeenCalledWith({
        path: { tournament_id: "t-1", match_id: "m-2" },
        body: {
          decision: "rematch",
          reason: "重新比賽",
          replay_at: "2026-10-26T13:00:00.000Z",
        },
      }),
    )
  })

  it("重新比賽沒有可選時間（RESCHEDULE_NO_VALID_TIME）：顯示後端訊息與「前往場次管理」", async () => {
    const user = userEvent.setup()
    mockList([FORFEIT])
    const replayWindow = vi
      .spyOn(DisputesService, "readReplayWindow")
      .mockResolvedValue({
        data: {
          can_reschedule: true,
          reason: null,
          earliest: "2026-10-26T12:00:00Z",
          latest: null,
        },
      } as WindowResult)
    vi.spyOn(DisputesService, "resolveAppeals").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "RESCHEDULE_NO_VALID_TIME",
          message: "這場目前沒有可選的時間（最早 2026/10/26 20:00）。",
        },
      }),
    )
    open()

    const row = await rowOf("M2")
    await user.click(within(row).getByRole("button", { name: REMATCH_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    const input = await within(dialog).findByLabelText(
      "重新比賽的時間（台北時間）",
    )
    fireEvent.change(input, { target: { value: "2026-10-26T21:00" } })
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "重賽")
    await user.click(within(dialog).getByRole("button", { name: REMATCH_TEXT }))

    expect(
      await within(dialog).findByText(
        "這場目前沒有可選的時間（最早 2026/10/26 20:00）。",
      ),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByRole("link", { name: GO_TO_MATCHES_TEXT }),
    ).toHaveAttribute("href", "/organizer/tournaments/t-1/matches")
    // RESCHEDULE_* 409 後重抓時間範圍
    await waitFor(() => expect(replayWindow).toHaveBeenCalledTimes(2))
  })

  it("重賽時間範圍為空（no_valid_time）：顯示提示與「前往場次管理」，不能送出", async () => {
    const user = userEvent.setup()
    mockList([FORFEIT])
    const resolve = mockResolve()
    vi.spyOn(DisputesService, "readReplayWindow").mockResolvedValue({
      data: {
        can_reschedule: false,
        reason: "no_valid_time",
        earliest: "2026-10-26T12:00:00Z",
        latest: "2026-10-26T11:00:00Z",
      },
    } as WindowResult)
    open()

    const row = await rowOf("M2")
    await user.click(within(row).getByRole("button", { name: REMATCH_TEXT }))
    const dialog = await screen.findByRole("alertdialog")
    expect(await within(dialog).findByText(NO_VALID_TIME_TEXT)).toBeVisible()
    expect(
      within(dialog).getByRole("link", { name: GO_TO_MATCHES_TEXT }),
    ).toHaveAttribute("href", "/organizer/tournaments/t-1/matches")
    await user.type(within(dialog).getByLabelText(REASON_LABEL), "重賽")
    expect(
      within(dialog).getByRole("button", { name: REMATCH_TEXT }),
    ).toBeDisabled()
    expect(resolve).not.toHaveBeenCalled()
  })

  it.each(["match_not_reschedulable", "tournament_not_reschedulable"] as const)(
    "重賽時間範圍回傳 %s（例如已在其他分頁處理）：顯示說明，不能送出",
    async (reason) => {
      const user = userEvent.setup()
      mockList([FORFEIT])
      const resolve = mockResolve()
      vi.spyOn(DisputesService, "readReplayWindow").mockResolvedValue({
        data: { can_reschedule: false, reason, earliest: null, latest: null },
      } as WindowResult)
      open()

      const row = await rowOf("M2")
      await user.click(within(row).getByRole("button", { name: REMATCH_TEXT }))
      const dialog = await screen.findByRole("alertdialog")
      expect(
        await within(dialog).findByText(REPLAY_BLOCKED_TEXT[reason] as string),
      ).toBeInTheDocument()
      expect(
        within(dialog).queryByLabelText("重新比賽的時間（台北時間）"),
      ).toBeNull()
      await user.type(within(dialog).getByLabelText(REASON_LABEL), "重賽")
      const confirm = within(dialog).getByRole("button", { name: REMATCH_TEXT })
      expect(confirm).toBeDisabled()
      expect(resolve).not.toHaveBeenCalled()
    },
  )
})

describe("S27 待處理清單", () => {
  it("顯示待處理數，依處理期限由近到遠，點選進 S32", async () => {
    const disputes: OpenDisputes = {
      appeals: 2,
      reports: 0,
      earliest_deadline: "2026-10-26T13:00:00Z",
      // 故意把期限較晚的放前面
      items: [
        {
          kind: "appeal",
          id: "ap-1",
          match_id: "m-1",
          match_code: "M1",
          filed_at: "2026-10-26T12:10:00Z",
          deadline: "2026-10-26T14:00:00Z",
        },
        {
          kind: "appeal",
          id: "ap-9",
          match_id: "m-7",
          match_code: "M7",
          filed_at: "2026-10-26T12:00:00Z",
          deadline: "2026-10-26T13:00:00Z",
        },
      ],
    }
    vi.spyOn(DisputesService, "readOpenDisputes").mockResolvedValue({
      data: disputes,
    } as OpenResult)
    open("/organizer/tournaments/t-1")

    await screen.findByRole("heading", { name: "待處理" })
    await waitFor(() =>
      expect(
        document.querySelectorAll("[data-slot=open-dispute]"),
      ).toHaveLength(2),
    )
    const items = [
      ...document.querySelectorAll<HTMLElement>("[data-slot=open-dispute]"),
    ]
    expect(items.map((item) => item.textContent?.split("提出")[0])).toEqual([
      "申訴 · M7",
      "申訴 · M1",
    ])
    expect(items[0]).toHaveAttribute("href", APPEALS_URL)
    expect(
      within(items[0]).getByText(
        `處理期限 ${formatMatchDateTime("2026-10-26T13:00:00Z")}`,
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(/待處理申訴/).textContent).toContain("2")
  })
})

describe("S4 申訴處理結果", () => {
  function renderBadge(
    decision: "upheld" | "corrected" | "disqualified" | null,
    status: "confirmed" | "appealed" = "confirmed",
  ) {
    const spy = vi
      .spyOn(DisputesService, "readAppealResult")
      .mockResolvedValue({ data: { decision } } as AppealResult)
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <AppealResultBadge detail={matchDetail({ status })} />
      </QueryClientProvider>,
    )
    return spy
  }

  it.each([
    ["upheld", "維持原結果"],
    ["corrected", "更正結果"],
    ["disqualified", "取消資格"],
  ] as const)(
    "已確認且經申訴處理（%s）：顯示「%s」",
    async (decision, text) => {
      renderBadge(decision)
      expect(await screen.findByText(text)).toBeInTheDocument()
    },
  )

  it("未經申訴處理：不顯示", async () => {
    const spy = renderBadge(null)
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(screen.queryByText("維持原結果")).toBeNull()
    expect(screen.queryByText("更正結果")).toBeNull()
  })

  it("場次不是已確認：不查詢", () => {
    const spy = renderBadge("upheld", "appealed")
    expect(spy).not.toHaveBeenCalled()
  })
})
