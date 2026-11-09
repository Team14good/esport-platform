import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  type AppealState,
  DisputesService,
  type PublicMatchDetail,
} from "@/client"
import { MatchAppealWindow } from "@/features/competition/MatchAppealWindow"
import {
  ALREADY_FILED_TEXT,
  APPEAL_FILED_TOAST,
  AppealPanel,
  appealEntry,
  DEADLINE_PASSED_TEXT,
  FILE_APPEAL_TEXT,
} from "@/features/disputes/AppealPanel"
import { ACCESS_TOKEN_STORAGE_KEY } from "@/features/identity/auth"
import { httpError } from "./helpers"
import { matchDetail } from "./match-detail-fixture"

type ReadStateResult = Awaited<
  ReturnType<typeof DisputesService.readAppealState>
>
type FileAppealResult = Awaited<ReturnType<typeof DisputesService.fileAppeal>>

const DEADLINE = "2026-10-18T06:22:00Z"

function appealMatch(overrides: Partial<PublicMatchDetail> = {}) {
  return matchDetail({
    status: "appeal_window",
    outcome: "played",
    winner_id: "team-a",
    wins_a: 2,
    appeal_deadline: DEADLINE,
    ...overrides,
  })
}

function appealState(overrides: Partial<AppealState> = {}): AppealState {
  return {
    can_file: true,
    already_filed: false,
    deadline: DEADLINE,
    reason: null,
    ...overrides,
  }
}

function mockState(state: AppealState) {
  return vi.spyOn(DisputesService, "readAppealState").mockResolvedValue({
    data: state,
  } as unknown as ReadStateResult)
}

function signIn() {
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "token-1")
}

function renderPanel(detail: PublicMatchDetail = appealMatch()) {
  const refresh = vi.fn().mockResolvedValue(undefined)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <AppealPanel detail={detail} refresh={refresh} />
    </QueryClientProvider>,
  )
  return { refresh }
}

describe("申訴入口的顯示條件", () => {
  it("可以提出：按鈕可按、沒有說明", () => {
    expect(appealEntry(appealState())).toEqual({ disabled: false, note: null })
  })

  it("本隊已申訴：停用並寫「本隊已對此場次提出申訴」（期限過後也一樣）", () => {
    const filed = { disabled: true, note: ALREADY_FILED_TEXT }
    expect(
      appealEntry(
        appealState({
          can_file: false,
          already_filed: true,
          reason: "already_filed",
        }),
      ),
    ).toEqual(filed)
    expect(
      appealEntry(
        appealState({
          can_file: false,
          already_filed: true,
          reason: "deadline_passed",
        }),
      ),
    ).toEqual(filed)
  })

  it("期限已過：停用並寫「已截止」", () => {
    expect(
      appealEntry(appealState({ can_file: false, reason: "deadline_passed" })),
    ).toEqual({ disabled: true, note: DEADLINE_PASSED_TEXT })
  })

  it("不是隊長、場次不能申訴、狀態還沒回來：不顯示按鈕", () => {
    expect(
      appealEntry(appealState({ can_file: false, reason: "not_captain" })),
    ).toBeNull()
    expect(
      appealEntry(
        appealState({
          can_file: false,
          reason: "not_appealable",
          deadline: null,
        }),
      ),
    ).toBeNull()
    expect(appealEntry(undefined)).toBeNull()
  })
})

describe("AppealPanel", () => {
  it("未登入：不查詢申訴狀態、不顯示按鈕", () => {
    const read = mockState(appealState())
    renderPanel()

    expect(read).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: FILE_APPEAL_TEXT })).toBeNull()
  })

  it("場次不在申訴期／申訴中：不查詢", () => {
    signIn()
    const read = mockState(appealState())
    renderPanel(appealMatch({ status: "confirmed", appeal_deadline: null }))

    expect(read).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: FILE_APPEAL_TEXT })).toBeNull()
  })

  it("不是隊長：查詢後不顯示按鈕", async () => {
    signIn()
    const read = mockState(
      appealState({ can_file: false, reason: "not_captain" }),
    )
    renderPanel()

    await waitFor(() => expect(read).toHaveBeenCalled())
    expect(read).toHaveBeenCalledWith({
      path: { tournament_id: "t1", match_id: "match-M3" },
    })
    expect(screen.queryByRole("button", { name: FILE_APPEAL_TEXT })).toBeNull()
  })

  it.each([
    [
      "本隊已申訴",
      appealState({
        can_file: false,
        already_filed: true,
        reason: "already_filed",
      }),
      ALREADY_FILED_TEXT,
    ],
    [
      "已截止",
      appealState({ can_file: false, reason: "deadline_passed" }),
      DEADLINE_PASSED_TEXT,
    ],
  ])("%s：按鈕停用並顯示說明", async (_name, state, note) => {
    signIn()
    mockState(state)
    renderPanel()

    const button = await screen.findByRole("button", { name: FILE_APPEAL_TEXT })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription(note)
  })

  it("說明必填：空白送出顯示欄位錯誤，不呼叫 API", async () => {
    const user = userEvent.setup()
    signIn()
    mockState(appealState())
    const file = vi.spyOn(DisputesService, "fileAppeal")
    renderPanel()

    await user.click(
      await screen.findByRole("button", { name: FILE_APPEAL_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出申訴" })
    await user.type(within(dialog).getByLabelText("申訴說明"), "   ")
    await user.click(within(dialog).getByRole("button", { name: "送出申訴" }))

    expect(
      await within(dialog).findByText("請輸入申訴說明"),
    ).toBeInTheDocument()
    expect(file).not.toHaveBeenCalled()
  })

  it("送出成功：帶說明與截圖呼叫 API，顯示成功 Toast、關閉對話框並重抓 S4", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    signIn()
    mockState(appealState())
    const file = vi
      .spyOn(DisputesService, "fileAppeal")
      .mockResolvedValue({ data: {} } as unknown as FileAppealResult)
    const { refresh } = renderPanel()

    await user.click(
      await screen.findByRole("button", { name: FILE_APPEAL_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出申訴" })
    await user.type(
      within(dialog).getByLabelText("申訴說明"),
      "第二局比分登錄錯誤",
    )
    const screenshot = new File([new Uint8Array([0x89, 0x50])], "proof.png", {
      type: "image/png",
    })
    await user.upload(within(dialog).getByLabelText("截圖（選填）"), screenshot)
    await user.click(within(dialog).getByRole("button", { name: "送出申訴" }))

    await waitFor(() => expect(refresh).toHaveBeenCalled())
    expect(file).toHaveBeenCalledTimes(1)
    const [options] = file.mock.calls[0]
    expect(options.path).toEqual({ tournament_id: "t1", match_id: "match-M3" })
    expect(options.body).toEqual({
      description: "第二局比分登錄錯誤",
      attachment: screenshot,
    })
    expect(success).toHaveBeenCalledWith(APPEAL_FILED_TOAST, expect.anything())
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("送出失敗：以錯誤 Toast 顯示伺服器訊息，對話框與內容保留，並重抓狀態", async () => {
    const user = userEvent.setup()
    const error = vi.spyOn(toast, "error")
    signIn()
    mockState(appealState())
    vi.spyOn(DisputesService, "fileAppeal").mockRejectedValue(
      httpError(409, {
        detail: { code: "APPEAL_DEADLINE_PASSED", message: "申訴期已截止。" },
      }),
    )
    const { refresh } = renderPanel()

    await user.click(
      await screen.findByRole("button", { name: FILE_APPEAL_TEXT }),
    )
    const dialog = await screen.findByRole("dialog", { name: "提出申訴" })
    await user.type(within(dialog).getByLabelText("申訴說明"), "比分有誤")
    await user.click(within(dialog).getByRole("button", { name: "送出申訴" }))

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith("申訴期已截止。", expect.anything()),
    )
    expect(refresh).toHaveBeenCalled()
    expect(screen.getByRole("dialog", { name: "提出申訴" })).toBeInTheDocument()
    expect(within(dialog).getByLabelText("申訴說明")).toHaveValue("比分有誤")
  })
})

describe("場次版本改變時的舊狀態", () => {
  it("新狀態回來前不顯示可按的按鈕（不讓舊的 can_file 閃回）", async () => {
    signIn()
    let resolveNext: (value: unknown) => void = () => {}
    const read = vi
      .spyOn(DisputesService, "readAppealState")
      .mockResolvedValueOnce({
        data: appealState(),
      } as unknown as ReadStateResult)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNext = resolve
          }) as unknown as ReturnType<typeof DisputesService.readAppealState>,
      )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const refresh = vi.fn().mockResolvedValue(undefined)
    const view = (detail: PublicMatchDetail) => (
      <QueryClientProvider client={queryClient}>
        <AppealPanel detail={detail} refresh={refresh} />
      </QueryClientProvider>
    )
    const { rerender } = render(view(appealMatch()))
    const button = await screen.findByRole("button", { name: FILE_APPEAL_TEXT })
    expect(button).toBeEnabled()

    // 本隊送出後場次轉為申訴中：版本改變，新狀態還在路上
    rerender(
      view(
        appealMatch({ status: "appealed", updated_at: "2026-10-18T05:30:00Z" }),
      ),
    )
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2))
    expect(
      screen.getByRole("button", { name: FILE_APPEAL_TEXT }),
    ).toBeDisabled()

    resolveNext({
      data: appealState({
        can_file: false,
        already_filed: true,
        reason: "already_filed",
      }),
    })
    expect(await screen.findByText(ALREADY_FILED_TEXT)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: FILE_APPEAL_TEXT }),
    ).toBeDisabled()
  })
})

describe("申訴期區塊的申訴中與插槽", () => {
  it("申訴中：寫「申訴處理中」，倒數照常顯示，插槽在下方", () => {
    render(
      <MatchAppealWindow
        detail={{ status: "appealed", appeal_deadline: DEADLINE }}
        countdown={<span>倒數</span>}
        action={<button type="button">提出申訴</button>}
      />,
    )

    const region = screen.getByRole("region", { name: "申訴期" })
    expect(within(region).getByText("申訴處理中")).toBeInTheDocument()
    expect(within(region).getByText("倒數")).toBeInTheDocument()
    expect(
      within(region).getByRole("button", { name: "提出申訴" }),
    ).toBeInTheDocument()
  })

  it("申訴期：沒有「申訴處理中」", () => {
    render(
      <MatchAppealWindow
        detail={{ status: "appeal_window", appeal_deadline: DEADLINE }}
      />,
    )

    expect(screen.queryByText("申訴處理中")).toBeNull()
  })
})
