import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type DrawStatus,
  type PublicBracket,
  type TournamentRead,
} from "@/client"
import { DrawButton } from "@/features/competition/DrawButton"
import { httpError } from "./helpers"

const BASE = {
  id: "t-1",
  name: "臺大秋季盃",
  status: "published",
} as unknown as TournamentRead

const NOTICE = "因前一輪 BO 數較多已順延開始時間，請到場次管理確認。"

function drawn(delayedRounds: number[]): DrawStatus {
  return {
    can_draw: false,
    reason: "already_drawn",
    expected_teams: null,
    delayed_rounds: delayedRounds,
  }
}

function mockStatus(data: DrawStatus) {
  return vi
    .spyOn(CompetitionService, "readDrawStatus")
    .mockResolvedValue({ data } as never)
}

// 8 隊：3 輪（8 強、4 強、決賽）
function mockBracket() {
  return vi.spyOn(CompetitionService, "readPublicBracket").mockResolvedValue({
    data: { rounds: 3, round_names: ["8 強", "4 強", "決賽"] } as PublicBracket,
  } as never)
}

function renderButton(tournament: TournamentRead) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <DrawButton tournament={tournament} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe("S27 順延提示", () => {
  it("有順延：顯示一則提示，列出順延的輪次名稱", async () => {
    mockStatus(drawn([2, 3]))
    mockBracket()
    renderButton(BASE)

    const note = await screen.findByText(/第 2 輪（4 強）、第 3 輪（決賽）/)
    expect(note).toHaveTextContent(NOTICE)
    expect(screen.getAllByRole("status")).toHaveLength(1)
    expect(note).toHaveAttribute("role", "status")
  })

  it("進行中的賽事也顯示", async () => {
    mockStatus(drawn([2]))
    mockBracket()
    renderButton({ ...BASE, status: "ongoing" })

    expect(
      await screen.findByText(`第 2 輪（4 強）${NOTICE}`),
    ).toBeInTheDocument()
  })

  it("賽程（對戰樹）讀取失敗：不顯示提示，也不顯示錯誤", async () => {
    mockStatus(drawn([2]))
    const bracket = vi
      .spyOn(CompetitionService, "readPublicBracket")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderButton(BASE)

    await waitFor(() => expect(bracket).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByRole("status")).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("沒有順延：不顯示提示", async () => {
    const spy = mockStatus(drawn([]))
    renderButton(BASE)

    await waitFor(() => expect(spy).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByRole("status")).toBeNull()
  })

  it.each(["open", "closed"] as const)(
    "尚未抽籤（%s）：照舊顯示抽籤按鈕，不顯示提示",
    async (state) => {
      mockStatus({
        can_draw: true,
        reason: null,
        expected_teams: 4,
        delayed_rounds: [],
      })
      const bracket = mockBracket()
      renderButton({ ...BASE, status: state })

      expect(
        await screen.findByRole("button", { name: "抽籤" }),
      ).toBeInTheDocument()
      expect(screen.queryByRole("status")).toBeNull()
      expect(bracket).not.toHaveBeenCalled()
    },
  )

  it.each(["finished", "cancelled"] as const)(
    "賽事 %s：不顯示提示、不查抽籤狀態",
    async (state) => {
      const spy = mockStatus(drawn([2, 3]))
      renderButton({ ...BASE, status: state })

      await act(async () => {})
      expect(screen.queryByRole("status")).toBeNull()
      expect(spy).not.toHaveBeenCalled()
    },
  )

  it("抽籤狀態讀取失敗：不顯示提示也不顯示錯誤", async () => {
    const spy = vi
      .spyOn(CompetitionService, "readDrawStatus")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    renderButton(BASE)

    await waitFor(() => expect(spy).toHaveBeenCalled())
    await act(async () => {})
    expect(screen.queryByRole("status")).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })
})
