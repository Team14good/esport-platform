import { configure, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import {
  CompetitionService,
  type MyTeamCard,
  type NextMatch,
  RegistrationService,
} from "@/client"
import { formatMatchDateTime } from "@/features/competition/match-time"
import {
  AWAITING_RESULT_TEXT,
  LIVE_TEXT,
} from "@/features/competition/NextMatchRow"
import { renderApp, signInAs } from "./auth-fixtures"

vi.mock("@tanstack/react-router-devtools", () => ({
  TanStackRouterDevtools: () => null,
}))
vi.mock("@tanstack/react-query-devtools", () => ({
  ReactQueryDevtools: () => null,
}))

// 第一次載入路由要轉譯整棵路由樹，預設 1 秒在冷啟動時不夠
configure({ asyncUtilTimeout: 5000 })

type MyTeamsResult = Awaited<ReturnType<typeof RegistrationService.listMyTeams>>
type NextMatchesResult = Awaited<
  ReturnType<typeof CompetitionService.listMyNextMatches>
>

const MINUTE = 60 * 1000
const iso = (ms: number) => new Date(ms).toISOString()

const CARD: MyTeamCard = {
  team_id: "team-1",
  team_name: "夜貓隊",
  tournament_id: "tour-1",
  tournament_name: "政大校園盃",
  game_name: "特戰英豪",
  registration_status: "drawn",
  waitlist_position: null,
  waitlist_reason: null,
  representative_backfill: null,
  waitlist_phase: null,
}

/** 預設：夜貓隊（a 方）對晨鳥隊，2 小時後開打、報到未開放。 */
function nextMatch(overrides: Partial<NextMatch> = {}): NextMatch {
  const scheduled = Date.now() + 120 * MINUTE
  return {
    id: "m-5",
    code: "M5",
    round_no: 2,
    slot_no: 1,
    is_third_place: false,
    team_a: { id: "team-1", name: "夜貓隊" },
    team_b: { id: "team-9", name: "晨鳥隊" },
    source_a: null,
    source_b: null,
    bye_a: false,
    bye_b: false,
    scheduled_at: iso(scheduled),
    status: "scheduled",
    outcome: null,
    winner_id: null,
    wins_a: 0,
    wins_b: 0,
    team_id: "team-1",
    round_name: "4 強",
    check_in_opens_at: iso(scheduled - 30 * MINUTE),
    forfeit_deadline: iso(scheduled + 15 * MINUTE),
    ...overrides,
  }
}

function render(matches: NextMatch[], cards: MyTeamCard[] = [CARD]) {
  signInAs()
  vi.spyOn(RegistrationService, "listMyTeams").mockResolvedValue({
    data: cards,
  } as MyTeamsResult)
  const spy = vi
    .spyOn(CompetitionService, "listMyNextMatches")
    .mockResolvedValue({ data: matches } as NextMatchesResult)
  renderApp("/me/teams")
  return spy
}

const findRow = () => screen.findByRole("link", { name: /下一場/ })

describe("S12 下一場列", () => {
  it("兩隊已定、報到未開放：對手、時間與「報到開放」倒數，連到 S4", async () => {
    const match = nextMatch()
    render([match])

    const row = await findRow()
    expect(row).toHaveAttribute("href", "/tournaments/tour-1/matches/m-5")
    expect(row).toHaveTextContent(
      `下一場 vs 晨鳥隊 · ${formatMatchDateTime(match.scheduled_at)}`,
    )
    expect(within(row).getByText("4 強 · M5")).toBeInTheDocument()
    const countdown = row.querySelector("[data-slot=countdown]")
    expect(countdown).toHaveAttribute("data-variant", "muted")
    expect(within(row).getByText("報到開放")).toBeInTheDocument()
  })

  it("本隊在 b 方：對手取 a 方", async () => {
    render([
      nextMatch({
        team_a: { id: "team-9", name: "晨鳥隊" },
        team_b: { id: "team-1", name: "夜貓隊" },
      }),
    ])

    expect(await findRow()).toHaveTextContent("下一場 vs 晨鳥隊")
  })

  it("報到已開放：倒數換成「距預定開始」（live）", async () => {
    const scheduled = Date.now() + 10 * MINUTE
    render([
      nextMatch({
        scheduled_at: iso(scheduled),
        check_in_opens_at: iso(scheduled - 30 * MINUTE),
        forfeit_deadline: iso(scheduled + 15 * MINUTE),
      }),
    ])

    const row = await findRow()
    expect(within(row).getByText("距預定開始")).toBeInTheDocument()
    expect(row.querySelector("[data-slot=countdown]")).toHaveAttribute(
      "data-variant",
      "live",
    )
  })

  it("過了預定時間：倒數換成「棄權期限」（appeal）", async () => {
    const scheduled = Date.now() - 5 * MINUTE
    render([
      nextMatch({
        scheduled_at: iso(scheduled),
        check_in_opens_at: iso(scheduled - 30 * MINUTE),
        forfeit_deadline: iso(scheduled + 15 * MINUTE),
      }),
    ])

    const row = await findRow()
    expect(within(row).getByText("棄權期限")).toBeInTheDocument()
    expect(row.querySelector("[data-slot=countdown]")).toHaveAttribute(
      "data-variant",
      "appeal",
    )
  })

  it("對手未定：「vs 待定」＋來源文字，只有「報到開放」倒數", async () => {
    render([
      nextMatch({
        team_b: null,
        source_b: "M6 勝者",
        forfeit_deadline: null,
      }),
    ])

    const row = await findRow()
    expect(row).toHaveTextContent("下一場 vs 待定 ·")
    expect(within(row).getByText("對手：M6 勝者")).toBeInTheDocument()
    expect(within(row).getByText("報到開放")).toBeInTheDocument()
  })

  it("對手未定且已過報到開放時間：不顯示倒數", async () => {
    const scheduled = Date.now() + 10 * MINUTE
    render([
      nextMatch({
        team_b: null,
        source_b: "M6 勝者",
        scheduled_at: iso(scheduled),
        check_in_opens_at: iso(scheduled - 30 * MINUTE),
        forfeit_deadline: null,
      }),
    ])

    const row = await findRow()
    expect(row.querySelector("[data-slot=countdown]")).toBeNull()
  })

  it("進行中：「比賽進行中」，不顯示倒數", async () => {
    render([nextMatch({ status: "live", forfeit_deadline: null })])

    const row = await findRow()
    const text = within(row).getByText(LIVE_TEXT)
    expect(text).toHaveClass("text-status-live")
    expect(row.querySelector("[data-slot=countdown]")).toBeNull()
    expect(row).toHaveAttribute("href", "/tournaments/tour-1/matches/m-5")
  })

  it.each(["appeal_window", "appealed"] as const)(
    "%s：「等待結果確認」",
    async (status) => {
      render([nextMatch({ status, forfeit_deadline: null })])

      const row = await findRow()
      expect(within(row).getByText(AWAITING_RESULT_TEXT)).toHaveClass(
        "text-muted-foreground",
      )
      expect(row.querySelector("[data-slot=countdown]")).toBeNull()
    },
  )

  it("倒數歸零：重抓下一場，並換到下一個倒數階段", async () => {
    // 留 3 秒：冷啟動時第一次轉譯可能超過 1.5 秒，報到開放會在斷言前就過了
    const scheduled = Date.now() + 30 * MINUTE + 3000
    const spy = render([
      nextMatch({
        scheduled_at: iso(scheduled),
        check_in_opens_at: iso(scheduled - 30 * MINUTE),
        forfeit_deadline: iso(scheduled + 15 * MINUTE),
      }),
    ])

    const row = await findRow()
    expect(within(row).getByText("報到開放")).toBeInTheDocument()
    expect(spy).toHaveBeenCalledTimes(1)

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
    expect(await within(row).findByText("距預定開始")).toBeInTheDocument()
  })

  it("季軍賽：輪次只寫「季軍賽」", async () => {
    render([
      nextMatch({ is_third_place: true, round_name: "季軍賽", code: "M8" }),
    ])

    const row = await findRow()
    expect(within(row).getByText("季軍賽")).toBeInTheDocument()
  })

  it("沒有下一場（已淘汰、賽事已結束）：不顯示下一場列", async () => {
    render([])

    expect(
      await screen.findByRole("link", { name: /夜貓隊/ }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /下一場/ })).toBeNull()
  })

  it("沒有已參賽隊伍：不查詢下一場", async () => {
    const spy = render([], [{ ...CARD, registration_status: "accepted" }])

    expect(
      await screen.findByRole("link", { name: /夜貓隊/ }),
    ).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it("每隊只顯示自己的下一場", async () => {
    render(
      [nextMatch({ team_id: "team-1" })],
      [CARD, { ...CARD, team_id: "team-2", team_name: "晨光隊" }],
    )

    await findRow()
    expect(screen.getAllByRole("link", { name: /下一場/ })).toHaveLength(1)
    const mine = screen.getByRole("link", { name: /夜貓隊/ }).closest("li")
    const other = screen.getByRole("link", { name: /晨光隊/ }).closest("li")
    if (!mine || !other) throw new Error("卡片應在 li 裡")
    expect(within(mine).getByRole("link", { name: /下一場/ })).toBeVisible()
    expect(within(other).queryByRole("link", { name: /下一場/ })).toBeNull()
  })
})
