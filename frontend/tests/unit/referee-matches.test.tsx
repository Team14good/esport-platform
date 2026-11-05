import { configure, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type RefereeMatch,
  type RefereeTournamentMatches,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import { identityIcon } from "@/features/identity/identity-icons"
import { renderApp, signInAs } from "./auth-fixtures"
import { httpError } from "./helpers"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

const URL = "/me/referee"

function match(overrides: Partial<RefereeMatch> = {}): RefereeMatch {
  return {
    id: "m-1",
    code: "M1",
    round_no: 1,
    slot_no: 1,
    is_third_place: false,
    team_a: { id: "a", name: "甲隊" },
    team_b: { id: "b", name: "乙隊" },
    source_a: null,
    source_b: null,
    bye_a: false,
    bye_b: false,
    scheduled_at: "2026-11-10T12:00:00Z",
    status: "scheduled",
    outcome: null,
    winner_id: null,
    wins_a: 0,
    wins_b: 0,
    round_name: "4 強",
    both_checked_in: false,
    ...overrides,
  }
}

const GROUPS: RefereeTournamentMatches[] = [
  {
    tournament: { id: "t-1", name: "臺大秋季盃" },
    matches: [
      match({ id: "m-1", code: "M1", both_checked_in: true }),
      match({
        id: "m-2",
        code: "M2",
        team_a: { id: "c", name: "丙隊" },
        team_b: { id: "d", name: "丁隊" },
        status: "live",
      }),
      match({
        id: "m-3",
        code: "M3",
        round_name: "決賽",
        team_a: null,
        team_b: null,
        source_a: "M1 勝者",
        source_b: "M2 勝者",
        scheduled_at: "2026-11-11T12:00:00Z",
      }),
    ],
  },
  {
    tournament: { id: "t-2", name: "清大春季盃" },
    matches: [
      match({
        id: "m-9",
        code: "M4",
        is_third_place: true,
        round_name: "季軍賽",
        status: "confirmed",
        // 兩隊都已報到，但已不是待開打：不標「可開始」
        both_checked_in: true,
      }),
    ],
  },
]

type ListResult = Awaited<
  ReturnType<typeof CompetitionService.listMyRefereeMatches>
>

function mockList(data: RefereeTournamentMatches[]) {
  return vi
    .spyOn(CompetitionService, "listMyRefereeMatches")
    .mockResolvedValue({ data } as ListResult)
}

describe("S13 我執法的場次", () => {
  it("依賽事分組，每場顯示場次、輪次、對戰、時間與狀態，整列連到 S4", async () => {
    mockList(GROUPS)
    signInAs()
    renderApp(URL)

    const first = await screen.findByRole("region", { name: "臺大秋季盃" })
    const rows = within(first).getAllByRole("listitem")
    expect(rows).toHaveLength(3)

    const m1 = within(rows[0]).getByRole("link")
    expect(m1).toHaveAttribute("href", "/tournaments/t-1/matches/m-1")
    expect(m1).toHaveTextContent("M1")
    expect(m1).toHaveTextContent("4 強")
    expect(m1).toHaveTextContent("甲隊 vs 乙隊")
    expect(m1).toHaveTextContent(formatMatchDateTime("2026-11-10T12:00:00Z"))

    expect(within(rows[1]).getByText("進行中")).toBeInTheDocument()
    // 待定：顯示來源說明
    expect(within(rows[2]).getByRole("link")).toHaveTextContent(
      "M1 勝者 vs M2 勝者",
    )
    expect(within(rows[2]).getByText("待開打")).toBeInTheDocument()

    const second = screen.getByRole("region", { name: "清大春季盃" })
    const third = within(second).getByRole("link")
    expect(third).toHaveAttribute("href", "/tournaments/t-2/matches/m-9")
    expect(third).toHaveTextContent("季軍賽")
    expect(within(second).getByText("已確認")).toBeInTheDocument()
  })

  it("待開打且兩隊都已報到才標「可開始」", async () => {
    mockList(GROUPS)
    signInAs()
    renderApp(URL)

    await screen.findByRole("region", { name: "臺大秋季盃" })
    // M1 可開始；M3 待開打但未報到；季軍賽已確認（即使 both_checked_in）
    expect(screen.getAllByText("可開始")).toHaveLength(1)
    const m1 = screen.getByText("可開始").closest("a") as HTMLElement
    expect(within(m1).getByText("可開始")).toBeInTheDocument()
    expect(within(m1).queryByText("待開打")).not.toBeInTheDocument()
  })

  it("沒有指派時顯示空狀態", async () => {
    mockList([])
    signInAs()
    renderApp(URL)

    expect(
      await screen.findByText("主辦方還沒有指派場次給你。"),
    ).toBeInTheDocument()
    expect(screen.queryByRole("region")).not.toBeInTheDocument()
  })

  it("載入失敗顯示錯誤，按「重新載入」會重抓", async () => {
    const spy = vi
      .spyOn(CompetitionService, "listMyRefereeMatches")
      .mockRejectedValueOnce(
        httpError(409, {
          detail: { code: "SOME_ERROR", message: "暫時無法載入場次。" },
        }),
      )
      .mockResolvedValue({ data: GROUPS } as ListResult)
    signInAs()
    renderApp(URL)

    expect(await screen.findByText("暫時無法載入場次。")).toBeInTheDocument()
    const retry = screen.getByRole("button", { name: "重新載入" })
    await userEvent.click(retry)

    await screen.findByRole("region", { name: "臺大秋季盃" })
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  })

  it("未登入導向登入頁，不呼叫 API", async () => {
    const spy = mockList([])
    const router = renderApp(URL)

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
    expect(spy).not.toHaveBeenCalled()
  })

  it("身分圖示：裁判有專屬圖示", () => {
    expect(identityIcon("referee")).not.toBe(identityIcon("unknown"))
  })
})
