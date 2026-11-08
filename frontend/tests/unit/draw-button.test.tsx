import { QueryClient } from "@tanstack/react-query"
import { act, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type DrawStatus,
  type TournamentRead,
  TournamentsService,
} from "@/client"
import { managedMatchesQueryOptions } from "@/features/competition/organizer-matches-queries"
import { myTournamentsQueryOptions } from "@/features/tournaments/organizer-queries"
import { FORBIDDEN_FALLBACK_MESSAGE } from "@/lib/api-error"
import { ACCOUNT, renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

const ORGANIZER = { ...ACCOUNT, is_organizer: true }
const URL = "/organizer/tournaments/t-1"

const OPEN = {
  id: "t-1",
  organizer_id: ORGANIZER.id,
  name: "臺大秋季盃",
  status: "open",
  mode: "campus",
  capacity: 8,
  registration_start: "2026-11-03T04:00:00Z",
  priority_end: "2026-11-04T04:00:00Z",
  registration_end: "2026-11-09T15:00:00Z",
  start_at: "2026-11-10T11:00:00Z",
  round_interval_minutes: 150,
  forfeit_minutes: 15,
  appeal_minutes: 30,
  livestream_url: null,
  game_id: "game-val",
  game_name: "特戰英豪",
  starters: 5,
  substitutes: 1,
  bo: 3,
  game_minutes: 40,
  score_type: "rounds",
  rank_tiers: [],
} as TournamentRead
const CLOSED: TournamentRead = { ...OPEN, status: "closed" }
const PUBLISHED: TournamentRead = { ...OPEN, status: "published" }

const CAN_DRAW: DrawStatus = { can_draw: true, reason: null, expected_teams: 4 }
const NOT_ENOUGH: DrawStatus = {
  can_draw: false,
  reason: "not_enough_teams",
  expected_teams: 1,
}
const DRAWN: DrawStatus = {
  can_draw: false,
  reason: "already_drawn",
  expected_teams: null,
}

type ReadResult = Awaited<
  ReturnType<typeof TournamentsService.readMyTournament>
>
type StatusResult = Awaited<
  ReturnType<typeof CompetitionService.readDrawStatus>
>

// 依序回傳各份資料，超過準備的次數就一直回傳最後一份
function mockTournament(...tournaments: TournamentRead[]) {
  const spy = vi.spyOn(TournamentsService, "readMyTournament")
  for (const data of tournaments) {
    spy.mockResolvedValueOnce({ data } as ReadResult)
  }
  spy.mockResolvedValue({
    data: tournaments[tournaments.length - 1],
  } as ReadResult)
  return spy
}

function mockStatus(...statuses: DrawStatus[]) {
  const spy = vi.spyOn(CompetitionService, "readDrawStatus")
  for (const data of statuses) {
    spy.mockResolvedValueOnce({ data } as StatusResult)
  }
  spy.mockResolvedValue({ data: statuses[statuses.length - 1] } as StatusResult)
  return spy
}

function open() {
  signInAs({ account: ORGANIZER })
  return renderApp(URL)
}

async function drawButton() {
  await screen.findByRole("heading", { name: "臺大秋季盃" })
  return within(await screen.findByRole("region", { name: "抽籤" })).getByRole(
    "button",
    { name: "抽籤" },
  )
}

describe("S27 抽籤按鈕", () => {
  it("開放報名中可抽籤：確認框寫會結束報名；成功提示「已完成抽籤」，按鈕消失", async () => {
    const user = userEvent.setup()
    const success = vi.spyOn(toast, "success")
    const read = mockTournament(OPEN)
    const status = mockStatus(CAN_DRAW, DRAWN)
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries")
    const draw = vi
      .spyOn(CompetitionService, "draw")
      .mockResolvedValue({ data: {} } as never)
    open()

    const button = await drawButton()
    expect(button).toBeEnabled()
    expect(status).toHaveBeenCalledWith({ path: { tournament_id: "t-1" } })
    await user.click(button)
    const dialog = await screen.findByRole("alertdialog", { name: "抽籤" })
    expect(
      within(dialog).getByText("抽籤只能執行一次，會立即結束報名。"),
    ).toBeInTheDocument()
    // 抽籤後重抓賽事：賽程已公布
    const readsBefore = read.mock.calls.length
    read.mockResolvedValue({ data: PUBLISHED } as ReadResult)
    await user.click(within(dialog).getByRole("button", { name: "抽籤" }))

    await waitFor(() => expect(draw).toHaveBeenCalledTimes(1))
    expect(draw.mock.calls[0][0]).toMatchObject({
      path: { tournament_id: "t-1" },
    })
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith("已完成抽籤", expect.anything()),
    )
    // 重抓抽籤狀態與賽事：已抽籤不顯示按鈕，徽章變成賽程已公布
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "抽籤" })).toBeNull(),
    )
    expect(status.mock.calls.length).toBeGreaterThanOrEqual(2)
    // S25 賽事列表與 S30 場次列表也標記為過期
    expect(invalidate).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: myTournamentsQueryOptions().queryKey,
      }),
    )
    expect(invalidate).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: managedMatchesQueryOptions("t-1").queryKey,
      }),
    )
    await waitFor(() =>
      expect(read.mock.calls.length).toBeGreaterThan(readsBefore),
    )
    expect(await screen.findByText("賽程已公布")).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  it("報名截止：確認框寫「抽籤只能執行一次。」；取消不抽籤", async () => {
    const user = userEvent.setup()
    mockTournament(CLOSED)
    mockStatus(CAN_DRAW)
    const draw = vi.spyOn(CompetitionService, "draw")
    open()

    await user.click(await drawButton())
    const dialog = await screen.findByRole("alertdialog", { name: "抽籤" })
    expect(within(dialog).getByText("抽籤只能執行一次。")).toBeInTheDocument()
    expect(
      within(dialog).queryByText("抽籤只能執行一次，會立即結束報名。"),
    ).toBeNull()
    await user.click(within(dialog).getByRole("button", { name: "取消" }))

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(draw).not.toHaveBeenCalled()
  })

  it.each([
    ["not_enough_teams", "正取不足 2 隊，無法抽籤", 1],
    ["start_passed", "開賽時間已過，無法抽籤", null],
  ] as const)("%s：按鈕停用，下方寫原因", async (reason, text, expected) => {
    mockTournament(OPEN)
    mockStatus({ can_draw: false, reason, expected_teams: expected })
    open()

    const button = await drawButton()
    expect(button).toBeDisabled()
    const note = screen.getByText(text)
    expect(button).toHaveAttribute("aria-describedby", note.id)
  })

  it.each(["already_drawn", "not_drawable"] as const)(
    "%s：不顯示按鈕",
    async (reason) => {
      mockTournament(OPEN)
      const status = mockStatus({
        can_draw: false,
        reason,
        expected_teams: null,
      })
      open()

      await screen.findByRole("heading", { name: "臺大秋季盃" })
      await waitFor(() => expect(status).toHaveBeenCalled())
      // 等狀態回應並讓畫面更新完，再確認仍沒有按鈕
      await status.mock.results[0].value
      await act(async () => {})
      expect(screen.queryByRole("region", { name: "抽籤" })).toBeNull()
      expect(screen.queryByRole("button", { name: "抽籤" })).toBeNull()
    },
  )

  it("按下時已不足（409）：錯誤 Toast 顯示後端訊息，重抓狀態後停用並寫原因", async () => {
    const user = userEvent.setup()
    const error = vi.spyOn(toast, "error")
    const read = mockTournament(OPEN)
    const status = mockStatus(CAN_DRAW, NOT_ENOUGH)
    vi.spyOn(CompetitionService, "draw").mockRejectedValue(
      httpError(409, {
        detail: {
          code: "NOT_ENOUGH_TEAMS",
          message: "正取不足 2 隊，無法抽籤",
        },
      }),
    )
    open()

    await user.click(await drawButton())
    const dialog = await screen.findByRole("alertdialog", { name: "抽籤" })
    const readsBefore = read.mock.calls.length
    const statusBefore = status.mock.calls.length
    await user.click(within(dialog).getByRole("button", { name: "抽籤" }))

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        "正取不足 2 隊，無法抽籤",
        expect.anything(),
      ),
    )
    // 失敗後重抓賽事與抽籤狀態
    await waitFor(() =>
      expect(read.mock.calls.length).toBeGreaterThan(readsBefore),
    )
    await waitFor(() =>
      expect(status.mock.calls.length).toBeGreaterThan(statusBefore),
    )
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    const region = await screen.findByRole("region", { name: "抽籤" })
    expect(
      await within(region).findByText("正取不足 2 隊，無法抽籤"),
    ).toBeInTheDocument()
    expect(within(region).getByRole("button", { name: "抽籤" })).toBeDisabled()
  })

  it("抽籤狀態載入失敗：顯示「無法取得抽籤狀態」與重新載入，重試成功後出現按鈕", async () => {
    const user = userEvent.setup()
    mockTournament(OPEN)
    const status = vi
      .spyOn(CompetitionService, "readDrawStatus")
      .mockRejectedValue(httpError(500, "Internal Server Error"))
    open()

    // 預設重試 3 次（約 7 秒）後才會進入錯誤狀態
    expect(
      await screen.findByText("無法取得抽籤狀態", undefined, {
        timeout: 15000,
      }),
    ).toBeInTheDocument()
    // 頁面其他內容仍在，也沒有抽籤按鈕
    expect(
      screen.getByRole("heading", { name: "臺大秋季盃" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "抽籤" })).toBeNull()

    const callsBefore = status.mock.calls.length
    status.mockResolvedValue({ data: CAN_DRAW } as StatusResult)
    await user.click(screen.getByRole("button", { name: "重新載入" }))

    expect(await drawButton()).toBeEnabled()
    expect(status.mock.calls.length).toBeGreaterThan(callsBefore)
    expect(screen.queryByText("無法取得抽籤狀態")).toBeNull()
    expect(
      screen.getByRole("heading", { name: "臺大秋季盃" }),
    ).toBeInTheDocument()
  }, 30000)

  it("別人的賽事（403）：沿用後台的 403 頁，不查抽籤狀態", async () => {
    vi.spyOn(TournamentsService, "readMyTournament").mockRejectedValue(
      httpError(403, {
        detail: {
          code: "TOURNAMENT_OWNER_REQUIRED",
          message: "只有賽事主辦方可以執行這個操作",
        },
      }),
    )
    const status = vi.spyOn(CompetitionService, "readDrawStatus")
    open()

    expect(
      await screen.findByRole("heading", { name: FORBIDDEN_FALLBACK_MESSAGE }),
    ).toBeInTheDocument()
    expect(status).not.toHaveBeenCalled()
  })
})
