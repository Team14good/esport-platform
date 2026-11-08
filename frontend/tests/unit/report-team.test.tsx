import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  DisputesService,
  type MyTeamCard,
  RegistrationService,
  type RegistrationStatus,
  type ReportableTeam,
  type ReportRead,
  type TeamDetail,
  type TournamentStatus,
} from "@/client"
import {
  ALL_REPORTED_TEXT,
  REPORT_DIALOG_DESCRIPTION,
  ReportTeamDialog,
  type ReportTeamDialogProps,
} from "@/features/disputes/ReportTeamDialog"
import {
  REPORT_ENTRY_TEXT,
  REPORT_FILED_TOAST,
  ReportTeamEntry,
} from "@/features/disputes/ReportTeamEntry"
import { createQueryClient } from "@/lib/query-client"
import { signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type ReadTeamResult = Awaited<ReturnType<typeof RegistrationService.readTeam>>
type ReportableResult = Awaited<
  ReturnType<typeof DisputesService.listReportableTeams>
>
type FileReportResult = Awaited<ReturnType<typeof DisputesService.fileReport>>

const TOURNAMENT_ID = "t-1"
const DESKTOP_WIDTH = window.innerWidth

function setViewport(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  })
}

beforeEach(() => {
  // jsdom 沒有 matchMedia；useIsMobile 只用它監聽變化，寬度看 innerWidth
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  URL.createObjectURL = vi.fn(() => "blob:preview")
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  setViewport(DESKTOP_WIDTH)
})

function card(status: RegistrationStatus = "accepted"): MyTeamCard {
  return {
    team_id: "team-a",
    team_name: "夜貓隊",
    tournament_id: TOURNAMENT_ID,
    tournament_name: "期中盃",
    game_name: "特戰英豪",
    registration_status: status,
    waitlist_position: null,
    waitlist_reason: null,
    representative_backfill: null,
    waitlist_phase: null,
  }
}

function teamDetail(role: "captain" | "player"): TeamDetail {
  return { id: "team-a", my_role: role } as TeamDetail
}

const TEAMS: ReportableTeam[] = [
  { id: "team-b", name: "晨鳥隊", has_open_report: false },
  { id: "team-c", name: "午後隊", has_open_report: true },
]

function mockApis({
  cards = [card()],
  role = "captain",
  teams = TEAMS,
}: {
  cards?: MyTeamCard[]
  role?: "captain" | "player"
  teams?: ReportableTeam[] | Error
} = {}) {
  const myTeams = vi
    .spyOn(RegistrationService, "listMyTeams")
    .mockResolvedValue({ data: cards } as MyTeamsResult)
  const readTeam = vi
    .spyOn(RegistrationService, "readTeam")
    .mockResolvedValue({ data: teamDetail(role) } as ReadTeamResult)
  const reportable = vi.spyOn(DisputesService, "listReportableTeams")
  if (teams instanceof Error) reportable.mockRejectedValue(teams)
  else reportable.mockResolvedValue({ data: teams } as ReportableResult)
  return { myTeams, readTeam, reportable }
}

function renderEntry(
  status: TournamentStatus = "open",
  client: QueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
) {
  render(
    <QueryClientProvider client={client}>
      <ReportTeamEntry tournamentId={TOURNAMENT_ID} tournamentStatus={status} />
    </QueryClientProvider>,
  )
  return client
}

/** 等所有查詢結束，再確認沒有出現入口（避免只是還在載入）。 */
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 50))
}

function pngFile(name = "proof.png") {
  return new File(["png"], name, { type: "image/png" })
}

describe("S2「檢舉隊伍」入口", () => {
  it.each(["pending", "accepted", "waitlisted", "drawn"] as const)(
    "%s 隊伍的隊長看得到",
    async (status) => {
      signInAs()
      mockApis({ cards: [card(status)] })
      renderEntry("ongoing")

      expect(
        await screen.findByRole("button", { name: REPORT_ENTRY_TEXT }),
      ).toBeInTheDocument()
    },
  )

  it("隊員看不到，也不呼叫 reportable-teams", async () => {
    signInAs()
    const { readTeam, reportable } = mockApis({ role: "player" })
    renderEntry()

    await waitFor(() => expect(readTeam).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
    expect(reportable).not.toHaveBeenCalled()
  })

  it("組隊中的隊長看不到，也不查隊伍", async () => {
    signInAs()
    const { myTeams, readTeam, reportable } = mockApis({
      cards: [card("forming")],
    })
    renderEntry()

    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
    expect(readTeam).not.toHaveBeenCalled()
    expect(reportable).not.toHaveBeenCalled()
  })

  it("其他賽事的隊伍不算", async () => {
    signInAs()
    const { myTeams, reportable } = mockApis({
      cards: [{ ...card(), tournament_id: "t-other" }],
    })
    renderEntry()

    await waitFor(() => expect(myTeams).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
    expect(reportable).not.toHaveBeenCalled()
  })

  it("觀眾（未登入）看不到，也不查我的隊伍", async () => {
    const { myTeams } = mockApis()
    renderEntry()

    await settle()
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
    expect(myTeams).not.toHaveBeenCalled()
  })

  it.each(["finished", "cancelled"] as const)(
    "賽事為 %s 時不顯示，也不查詢",
    async (status) => {
      signInAs()
      const { myTeams } = mockApis()
      renderEntry(status)

      await settle()
      expect(
        screen.queryByRole("button", { name: REPORT_ENTRY_TEXT }),
      ).toBeNull()
      expect(myTeams).not.toHaveBeenCalled()
    },
  )

  it("隊長但可檢舉的隊伍為空：不顯示", async () => {
    signInAs()
    const { reportable } = mockApis({ teams: [] })
    renderEntry()

    await waitFor(() => expect(reportable).toHaveBeenCalled())
    await settle()
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
  })

  it("reportable-teams 回 403 時不重試、不顯示（全站預設會重試 403）", async () => {
    signInAs()
    const { reportable } = mockApis({
      teams: httpError(403, {
        detail: {
          code: "TEAM_CAPTAIN_REQUIRED",
          message: "只有隊長可以使用這個功能。",
        },
      }),
    })
    renderEntry("open", createQueryClient())

    await waitFor(() => expect(reportable).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 1500))
    expect(reportable).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
  })

  it("送出成功：關閉對話框、Toast「已送出檢舉」，並重新取得檢舉對象", async () => {
    const user = userEvent.setup()
    signInAs()
    const { reportable } = mockApis()
    const fileReport = vi
      .spyOn(DisputesService, "fileReport")
      .mockResolvedValue({ data: {} as ReportRead } as FileReportResult)
    const success = vi.spyOn(toast, "success")
    renderEntry()

    await user.click(
      await screen.findByRole("button", { name: REPORT_ENTRY_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出檢舉" })
    expect(within(dialog).getByText(REPORT_DIALOG_DESCRIPTION)).toBeVisible()
    await user.click(within(dialog).getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(within(dialog).getByLabelText("說明"), "  隊員不同校  ")
    const file = pngFile()
    await user.upload(within(dialog).getByLabelText("截圖（選填）"), file)
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(REPORT_FILED_TOAST),
    )
    expect(fileReport).toHaveBeenCalledTimes(1)
    const options = fileReport.mock.calls[0][0]
    expect(options.path).toEqual({ tournament_id: TOURNAMENT_ID })
    expect(options.body).toEqual({
      reported_team_id: "team-b",
      description: "隊員不同校",
      attachment: file,
    })
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "提出檢舉" })).toBeNull(),
    )
    await waitFor(() => expect(reportable).toHaveBeenCalledTimes(2))
  })

  it("伺服器錯誤顯示在對話框內；REPORT_NOT_ALLOWED 另外重新取得我的隊伍與賽事", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApis()
    vi.spyOn(DisputesService, "fileReport").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REPORT_NOT_ALLOWED",
          message: "賽事已結束，不能提出檢舉。",
        },
      }),
    )
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidate = vi.spyOn(client, "invalidateQueries")
    renderEntry("open", client)

    await user.click(
      await screen.findByRole("button", { name: REPORT_ENTRY_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出檢舉" })
    await user.click(within(dialog).getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(within(dialog).getByLabelText("說明"), "隊員不同校")
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    expect(
      await within(dialog).findByText("賽事已結束，不能提出檢舉。"),
    ).toBeInTheDocument()
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey)
    expect(keys).toEqual(
      expect.arrayContaining([
        ["disputes", "reportable-teams", TOURNAMENT_ID],
        ["registration", "my-teams"],
        ["tournaments", "public", "detail", TOURNAMENT_ID],
      ]),
    )
  })

  it("其他錯誤只重新取得檢舉對象", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApis()
    vi.spyOn(DisputesService, "fileReport").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "REPORT_ALREADY_FILED",
          message: "已檢舉這支隊伍，主辦方處理中。",
        },
      }),
    )
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidate = vi.spyOn(client, "invalidateQueries")
    renderEntry("open", client)

    await user.click(
      await screen.findByRole("button", { name: REPORT_ENTRY_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出檢舉" })
    await user.click(within(dialog).getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(within(dialog).getByLabelText("說明"), "隊員不同校")
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    expect(
      await within(dialog).findByText("已檢舉這支隊伍，主辦方處理中。"),
    ).toBeInTheDocument()
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey)
    expect(keys).toEqual([["disputes", "reportable-teams", TOURNAMENT_ID]])
  })
})

function renderDialog(props: Partial<ReportTeamDialogProps> = {}) {
  const onSubmit = vi.fn<ReportTeamDialogProps["onSubmit"]>(() =>
    Promise.resolve(),
  )
  render(
    <ReportTeamDialog
      open
      onOpenChange={() => {}}
      teams={TEAMS}
      onSubmit={onSubmit}
      {...props}
    />,
  )
  return { onSubmit }
}

describe("S20 提出檢舉", () => {
  it("桌機用 Dialog、手機用底部 Sheet", () => {
    setViewport(1280)
    const { unmount } = render(
      <ReportTeamDialog
        open
        onOpenChange={() => {}}
        teams={TEAMS}
        onSubmit={() => Promise.resolve()}
      />,
    )
    expect(screen.getByTestId("report-team-dialog")).toBeInTheDocument()
    expect(screen.queryByTestId("report-team-sheet")).toBeNull()
    unmount()

    setViewport(375)
    renderDialog()
    expect(screen.getByTestId("report-team-sheet")).toBeInTheDocument()
    expect(screen.queryByTestId("report-team-dialog")).toBeNull()
  })

  it("已檢舉處理中的隊伍標示並停用；只有「送出檢舉」，沒有「取消」", async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    const reported = await screen.findByRole("option", {
      name: "午後隊・已檢舉・處理中",
    })
    expect(reported).toHaveAttribute("aria-disabled", "true")
    expect(screen.getByRole("option", { name: "晨鳥隊" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    )
    expect(screen.queryByRole("button", { name: "取消" })).toBeNull()
  })

  it("全部對象都已檢舉：顯示說明並停用「送出檢舉」", () => {
    renderDialog({
      teams: [{ id: "team-c", name: "午後隊", has_open_report: true }],
    })

    expect(screen.getByText(ALL_REPORTED_TEXT)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "送出檢舉" })).toBeDisabled()
  })

  it("沒選對象、說明空白：逐欄顯示錯誤，不送出", async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderDialog()

    await user.type(screen.getByLabelText("說明"), "   ")
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))

    expect(await screen.findByText("請輸入說明。")).toBeInTheDocument()
    expect(screen.getByText("請選擇檢舉對象。")).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("字數以 code point 計（emoji 算一個字）；超過 1000 字不送出", async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderDialog()
    const textarea = screen.getByLabelText("說明")

    await user.type(textarea, "😀😀")
    expect(screen.getByText("2／1000")).toBeInTheDocument()

    await user.clear(textarea)
    await user.click(textarea)
    await user.paste("字".repeat(1001))
    expect(screen.getByText("1001／1000")).toBeInTheDocument()
    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))

    expect(await screen.findByText("說明須為 1～1000 字。")).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("1000 個 emoji 可以送出", async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderDialog()

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.click(screen.getByLabelText("說明"))
    await user.paste("😀".repeat(1000))
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).toEqual({
      reported_team_id: "team-b",
      description: "😀".repeat(1000),
      attachment: null,
    })
  })

  it("截圖格式不符：選檔時就顯示錯誤，不留檔案", async () => {
    const user = userEvent.setup({ applyAccept: false })
    renderDialog()

    await user.upload(
      screen.getByLabelText("截圖（選填）"),
      new File(["gif"], "anim.gif", { type: "image/gif" }),
    )

    expect(screen.getByText("只接受 JPG 或 PNG 圖片")).toBeInTheDocument()
    expect(screen.queryByTestId("screenshot-preview")).toBeNull()
  })

  it("伺服器回 413：錯誤顯示在截圖欄下方", async () => {
    const user = userEvent.setup()
    renderDialog({
      onSubmit: () =>
        Promise.reject(
          httpError(413, {
            detail: { code: "FILE_TOO_LARGE", message: "圖片不能超過 5 MB" },
          }),
        ),
    })

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(screen.getByLabelText("說明"), "隊員不同校")
    await user.upload(screen.getByLabelText("截圖（選填）"), pngFile())
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))

    expect(await screen.findByText("圖片不能超過 5 MB")).toBeInTheDocument()
  })

  it("伺服器回說明欄位錯誤（422）：顯示在說明欄下方", async () => {
    const user = userEvent.setup()
    renderDialog({
      onSubmit: () =>
        Promise.reject(
          httpError(422, {
            detail: [
              {
                type: "REPORT_DESCRIPTION_INVALID",
                loc: ["body", "description"],
                msg: "說明須為 1～1000 字。",
              },
            ],
          }),
        ),
    })

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(screen.getByLabelText("說明"), "隊員不同校")
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))

    expect(await screen.findByText("說明須為 1～1000 字。")).toBeInTheDocument()
  })

  it("上傳中顯示進度", () => {
    renderDialog({ uploadProgress: 42 })

    expect(screen.getByText("上傳中 42%")).toBeInTheDocument()
  })

  it("送出中按 Esc 不會關閉；送出完成後才能關閉", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    let finish: () => void = () => {}
    renderDialog({
      onOpenChange,
      onSubmit: () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    })

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(screen.getByLabelText("說明"), "隊員不同校")
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "送出檢舉" })).toBeDisabled(),
    )

    await user.keyboard("{Escape}")
    expect(onOpenChange).not.toHaveBeenCalled()

    finish()
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "送出檢舉" })).toBeEnabled(),
    )
    await user.keyboard("{Escape}")
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

/** 開 S20、選晨鳥隊、填說明；回傳對話框。 */
async function openAndFill(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    await screen.findByRole("button", { name: REPORT_ENTRY_TEXT }),
  )
  const dialog = await screen.findByRole("dialog", { name: "提出檢舉" })
  await user.click(within(dialog).getByRole("combobox", { name: "檢舉對象" }))
  await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
  await user.type(within(dialog).getByLabelText("說明"), "隊員不同校")
  return dialog
}

describe("S20 送出流程（入口層）", () => {
  it("附截圖：上傳進度顯示在對話框內", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApis()
    const progress: number[] = []
    const fileReport = vi
      .spyOn(DisputesService, "fileReport")
      .mockImplementation(async (options) => {
        options.onUploadProgress?.({
          loaded: 1,
          total: 4,
          bytes: 1,
          lengthComputable: true,
        })
        await waitFor(() =>
          expect(screen.getByText("上傳中 25%")).toBeInTheDocument(),
        )
        progress.push(25)
        return { data: {} as ReportRead } as never
      })
    renderEntry()

    const dialog = await openAndFill(user)
    await user.upload(within(dialog).getByLabelText("截圖（選填）"), pngFile())
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "提出檢舉" })).toBeNull(),
    )
    expect(progress).toEqual([25])
    expect(fileReport).toHaveBeenCalledWith(
      expect.objectContaining({ onUploadProgress: expect.any(Function) }),
    )
  })

  it("沒附截圖：不帶 onUploadProgress", async () => {
    const user = userEvent.setup()
    signInAs()
    mockApis()
    const fileReport = vi
      .spyOn(DisputesService, "fileReport")
      .mockResolvedValue({ data: {} as ReportRead } as FileReportResult)
    renderEntry()

    const dialog = await openAndFill(user)
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    await waitFor(() => expect(fileReport).toHaveBeenCalledTimes(1))
    expect(fileReport.mock.calls[0][0].onUploadProgress).toBeUndefined()
    expect(fileReport.mock.calls[0][0].body?.attachment).toBeUndefined()
  })

  it("REPORT_NOT_ALLOWED 後我的隊伍不再符合條件：對話框仍開著並顯示錯誤，關閉後入口消失", async () => {
    const user = userEvent.setup()
    signInAs()
    const { myTeams } = mockApis()
    vi.spyOn(DisputesService, "fileReport").mockImplementation(async () => {
      // 重新取得時本隊已撤回
      myTeams.mockResolvedValue({ data: [card("withdrawn")] } as MyTeamsResult)
      throw httpError(409, {
        detail: {
          code: "REPORT_NOT_ALLOWED",
          message: "本隊的報名尚未送出或已不在賽事中，不能提出檢舉。",
        },
      })
    })
    renderEntry()

    const dialog = await openAndFill(user)
    await user.click(within(dialog).getByRole("button", { name: "送出檢舉" }))

    expect(
      await within(dialog).findByText(
        "本隊的報名尚未送出或已不在賽事中，不能提出檢舉。",
      ),
    ).toBeInTheDocument()
    await waitFor(() => expect(myTeams).toHaveBeenCalledTimes(2))
    await settle()
    // 入口按鈕已隱藏，但對話框、錯誤與輸入都還在
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
    expect(screen.getByRole("dialog", { name: "提出檢舉" })).toBeInTheDocument()
    expect(
      screen.getByText("本隊的報名尚未送出或已不在賽事中，不能提出檢舉。"),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("說明")).toHaveValue("隊員不同校")

    await user.keyboard("{Escape}")
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "提出檢舉" })).toBeNull(),
    )
    expect(screen.queryByRole("button", { name: REPORT_ENTRY_TEXT })).toBeNull()
  })

  it("清單為空時不顯示「這些隊伍都已檢舉」", () => {
    renderDialog({ teams: [] })

    expect(screen.queryByText(ALL_REPORTED_TEXT)).toBeNull()
  })

  it("關閉再開啟：清掉對象、說明、截圖與伺服器錯誤", async () => {
    const user = userEvent.setup()
    const props = {
      onOpenChange: () => {},
      teams: TEAMS,
      onSubmit: () =>
        Promise.reject(
          httpError(409, {
            detail: {
              code: "REPORT_ALREADY_FILED",
              message: "已檢舉這支隊伍，主辦方處理中。",
            },
          }),
        ),
    }
    const { rerender } = render(<ReportTeamDialog open {...props} />)

    await user.click(screen.getByRole("combobox", { name: "檢舉對象" }))
    await user.click(await screen.findByRole("option", { name: "晨鳥隊" }))
    await user.type(screen.getByLabelText("說明"), "隊員不同校")
    await user.upload(screen.getByLabelText("截圖（選填）"), pngFile())
    expect(screen.getByTestId("screenshot-preview")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "送出檢舉" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "已檢舉這支隊伍，主辦方處理中。",
    )

    rerender(<ReportTeamDialog open={false} {...props} />)
    rerender(<ReportTeamDialog open {...props} />)

    expect(
      screen.getByRole("combobox", { name: "檢舉對象" }),
    ).toHaveTextContent("選擇隊伍")
    expect(screen.getByLabelText("說明")).toHaveValue("")
    expect(screen.queryByTestId("screenshot-preview")).toBeNull()
    expect(screen.getByTestId("screenshot-dropzone")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).toBeNull()
  })
})
